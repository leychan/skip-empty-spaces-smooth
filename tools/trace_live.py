#!/usr/bin/env python3
"""Read recent gesture lifecycle events from the running effect (no screenshots)."""
import json

import dbus


def read_trace():
    bus = dbus.SessionBus()
    object_ = bus.get_object("org.kde.KWin", "/Effects")
    properties = dbus.Interface(object_, "org.freedesktop.DBus.Properties")
    effects = dbus.Interface(object_, "org.kde.kwin.Effects")
    loaded = properties.Get("org.kde.kwin.Effects", "loadedEffects")
    native = [str(name) for name in loaded if str(name).startswith("skip-empty-spaces-native-")]
    found = False
    for name in native or loaded:
        if not native and str(name) != "skip-empty-spaces-smooth" and not str(name).startswith("skip-empty-spaces-smooth-runtime-"):
            continue
        found = True
        information = str(effects.supportInformation(name))
        line = next((line for line in information.splitlines() if line.startswith("traceLog: ")), None)
        if line is None:
            raise RuntimeError("The loaded build does not have lifecycle diagnostics")
        rows = json.loads(line.removeprefix("traceLog: "))
        first = rows[0]["time"] if rows else 0
        for row in rows:
            row["relative_ms"] = row["time"] - first
        print(json.dumps({"effect": str(name), "events": rows}, ensure_ascii=False, indent=2))
    if not found:
        raise RuntimeError("The smooth spaces effect is not loaded")


if __name__ == "__main__":
    read_trace()
