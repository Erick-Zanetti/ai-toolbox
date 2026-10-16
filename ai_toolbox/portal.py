"""Send key presses through the XDG RemoteDesktop portal (GNOME, KDE).

The first use shows the desktop's permission dialog; the restore token it
returns is saved so later sessions start without asking. Inside the daemon
the session stays open, so pastes are immediate.

Spec: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

PORTAL = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
REMOTE = "org.freedesktop.portal.RemoteDesktop"
REQUEST = "org.freedesktop.portal.Request"

KEYBOARD = 1
PERSIST_UNTIL_REVOKED = 2
KEYSYMS = {"ctrl": 0xFFE3, "shift": 0xFFE1, "c": 0x0063, "v": 0x0076}

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "ai-toolbox"
TOKEN_FILE = STATE_DIR / "portal-restore-token"

DIALOG_TIMEOUT_S = 60
CALL_TIMEOUT_S = 5


class PortalError(Exception):
    pass


def shortcut_events(key: str, terminal: bool) -> list[tuple[int, int]]:
    """(keysym, pressed) sequence for Ctrl[+Shift]+key."""
    mods = ["ctrl"] + (["shift"] if terminal else [])
    events = [(KEYSYMS[m], 1) for m in mods]
    events += [(KEYSYMS[key], 1), (KEYSYMS[key], 0)]
    events += [(KEYSYMS[m], 0) for m in reversed(mods)]
    return events


class RemoteDesktop:
    """One portal session, created on first use and reused afterwards."""

    def __init__(self) -> None:
        from gi.repository import Gio

        self._bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self._session: str | None = None

    # ── D-Bus plumbing ──────────────────────────────────────────────────────

    def available(self) -> bool:
        from gi.repository import GLib

        try:
            self._call("org.freedesktop.DBus.Properties", "Get",
                       GLib.Variant("(ss)", (REMOTE, "version")))
            return True
        except PortalError:
            return False

    def _call(self, interface: str, method: str, params, timeout_s: float = CALL_TIMEOUT_S):
        from gi.repository import Gio, GLib

        try:
            return self._bus.call_sync(PORTAL, PORTAL_PATH, interface, method, params, None,
                                       Gio.DBusCallFlags.NONE, int(timeout_s * 1000), None)
        except GLib.Error as err:
            raise PortalError(err.message) from err

    def _request(self, method: str, build_params, timeout_s: float = CALL_TIMEOUT_S) -> dict:
        """Portal calls answer through a Request object's Response signal.
        Subscribe to the predictable request path first, then call."""
        from gi.repository import Gio, GLib

        token = "atb_" + secrets.token_hex(6)
        sender = self._bus.get_unique_name()[1:].replace(".", "_")
        path = f"{PORTAL_PATH}/request/{sender}/{token}"
        loop = GLib.MainLoop.new(GLib.MainContext.get_thread_default(), False)
        reply: dict = {}

        def on_response(_bus, _sender, _path, _iface, _signal, params) -> None:
            code, results = params.unpack()
            reply.update(code=code, results=results)
            loop.quit()

        def on_timeout() -> bool:
            reply["timed_out"] = True
            loop.quit()
            return False

        sub = self._bus.signal_subscribe(PORTAL, REQUEST, "Response", path, None,
                                         Gio.DBusSignalFlags.NONE, on_response)
        timer = GLib.timeout_add(int(timeout_s * 1000), on_timeout)
        try:
            self._call(REMOTE, method, build_params(token), timeout_s)
            loop.run()
        finally:
            self._bus.signal_unsubscribe(sub)
            if "timed_out" not in reply:
                GLib.source_remove(timer)
        if "code" not in reply:
            raise PortalError(f"{method}: no answer from the portal")
        if reply["code"] != 0:
            raise PortalError(f"{method}: cancelled or denied ({reply['code']})")
        return reply["results"]

    # ── Session ─────────────────────────────────────────────────────────────

    def _start_session(self) -> str:
        from gi.repository import GLib

        created = self._request("CreateSession", lambda token: GLib.Variant("(a{sv})", ({
            "handle_token": GLib.Variant("s", token),
            "session_handle_token": GLib.Variant("s", "atb_s" + secrets.token_hex(4)),
        },)))
        session = created["session_handle"]

        options = {
            "types": GLib.Variant("u", KEYBOARD),
            "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED),
        }
        saved = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""
        if saved:
            options["restore_token"] = GLib.Variant("s", saved)
        self._request("SelectDevices", lambda token: GLib.Variant(
            "(oa{sv})", (session, {**options, "handle_token": GLib.Variant("s", token)})))

        started = self._request("Start", lambda token: GLib.Variant(
            "(osa{sv})", (session, "", {"handle_token": GLib.Variant("s", token)})),
            timeout_s=DIALOG_TIMEOUT_S)
        if started.get("restore_token"):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            TOKEN_FILE.write_text(started["restore_token"])
            TOKEN_FILE.chmod(0o600)
        return session

    def send_shortcut(self, key: str, terminal: bool) -> None:
        from gi.repository import GLib

        if self._session is None:
            self._session = self._start_session()
        try:
            for keysym, state in shortcut_events(key, terminal):
                self._call(REMOTE, "NotifyKeyboardKeysym", GLib.Variant(
                    "(oa{sv}iu)", (self._session, {}, keysym, state)))
        except PortalError:
            self._session = None  # closed by the desktop: start over next time
            raise


_instance: RemoteDesktop | None = None
_available: bool | None = None


def send_shortcut(key: str, terminal: bool) -> bool:
    """Ctrl[+Shift]+key through the portal; False when it is not available."""
    global _instance, _available
    try:
        if _instance is None:
            _instance = RemoteDesktop()
        if _available is None:
            _available = _instance.available()
        if not _available:
            return False
        _instance.send_shortcut(key, terminal)
        return True
    except (PortalError, ImportError):
        return False
