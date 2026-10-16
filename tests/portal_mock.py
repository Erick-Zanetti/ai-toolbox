"""A fake org.freedesktop.portal.RemoteDesktop for tests: answers every
request with success and logs the calls (one JSON line each) to argv[1]."""

import json
import sys

from gi.repository import Gio, GLib

LOG = sys.argv[1]
XML = """
<node>
  <interface name="org.freedesktop.portal.RemoteDesktop">
    <method name="CreateSession"><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="SelectDevices"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="Start"><arg type="o" direction="in"/><arg type="s" direction="in"/><arg type="a{sv}" direction="in"/><arg type="o" direction="out"/></method>
    <method name="NotifyKeyboardKeysym"><arg type="o" direction="in"/><arg type="a{sv}" direction="in"/><arg type="i" direction="in"/><arg type="u" direction="in"/></method>
    <property name="version" type="u" access="read"/>
  </interface>
</node>
"""
SESSION = "/org/freedesktop/portal/desktop/session/test/s1"


def log(entry: dict) -> None:
    with open(LOG, "a") as fh:
        fh.write(json.dumps(entry) + "\n")


def on_call(conn, sender, path, iface, method, params, invocation):
    args = params.unpack()
    log({"method": method, "args": [a if not isinstance(a, dict) else sorted(a) for a in args],
         "restore_token": (args[1].get("restore_token") if method == "SelectDevices" else None)})
    if method == "NotifyKeyboardKeysym":
        invocation.return_value(None)
        return
    options = args[-1]
    token = options["handle_token"]
    request = f"/org/freedesktop/portal/desktop/request/{sender[1:].replace('.', '_')}/{token}"
    invocation.return_value(GLib.Variant("(o)", (request,)))
    results = {}
    if method == "CreateSession":
        results["session_handle"] = GLib.Variant("s", SESSION)
    if method == "Start":
        results["devices"] = GLib.Variant("u", 1)
        results["restore_token"] = GLib.Variant("s", "token-123")
    GLib.idle_add(lambda: (conn.emit_signal(sender, request, "org.freedesktop.portal.Request",
                                            "Response", GLib.Variant("(ua{sv})", (0, results)))
                           , False)[1])


def get_property(conn, sender, path, iface, name):
    return GLib.Variant("u", 2)


def on_bus(conn, _name):
    info = Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0]
    conn.register_object("/org/freedesktop/portal/desktop", info, on_call, get_property, None)


def on_name(_conn, _name):
    print("ready", flush=True)


Gio.bus_own_name(Gio.BusType.SESSION, "org.freedesktop.portal.Desktop",
                 Gio.BusNameOwnerFlags.NONE, on_bus, on_name, None)
GLib.MainLoop().run()
