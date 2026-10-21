"""RemoteDesktop portal against a fake portal on a private D-Bus session."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("gi")

HERE = Path(__file__).resolve().parent


@pytest.fixture
def private_bus(tmp_path, monkeypatch):
    if not Path("/usr/bin/dbus-daemon").exists():
        pytest.skip("dbus-daemon not installed")
    daemon = subprocess.Popen(["dbus-daemon", "--session", "--nofork", "--print-address"],
                              stdout=subprocess.PIPE, text=True)
    address = daemon.stdout.readline().strip()
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    # Gio caches the session bus once anything (e.g. GTK in an earlier test)
    # opened it, ignoring the address above: connect to the private one directly.
    from gi.repository import Gio

    flags = (Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
             | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION)
    monkeypatch.setattr(Gio, "bus_get_sync", lambda _type, *_: Gio.DBusConnection.new_for_address_sync(
        address, flags, None, None))
    log = tmp_path / "calls.jsonl"
    mock = subprocess.Popen([sys.executable, str(HERE / "portal_mock.py"), str(log)],
                            stdout=subprocess.PIPE, text=True, env={**os.environ})
    assert mock.stdout.readline().strip() == "ready"
    yield log
    mock.kill()
    daemon.kill()


def test_session_keys_and_restore_token(private_bus, tmp_path, monkeypatch):
    from ai_toolbox import portal

    monkeypatch.setattr(portal, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(portal, "TOKEN_FILE", tmp_path / "state" / "token")
    remote = portal.RemoteDesktop()
    assert remote.available()

    remote.send_shortcut("v", terminal=True)
    remote.send_shortcut("v", terminal=False)  # reuses the session

    calls = [json.loads(line) for line in private_bus.read_text().splitlines()]
    methods = [c["method"] for c in calls]
    assert methods[:3] == ["CreateSession", "SelectDevices", "Start"]
    assert methods.count("CreateSession") == 1
    keys = [c["args"][2:] for c in calls if c["method"] == "NotifyKeyboardKeysym"]
    assert keys == [list(e) for e in portal.shortcut_events("v", True) + portal.shortcut_events("v", False)]
    assert (tmp_path / "state" / "token").read_text() == "token-123"

    # A new session (e.g. after a restart) restores without the dialog.
    portal.RemoteDesktop().send_shortcut("c", terminal=False)
    calls = [json.loads(line) for line in private_bus.read_text().splitlines()]
    selects = [c for c in calls if c["method"] == "SelectDevices"]
    assert selects[-1]["restore_token"] == "token-123"
