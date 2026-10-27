#!/usr/bin/env python3
"""Restore native Slide, including installations that needed a fresh QML URL."""
import subprocess

import dbus


PLUGIN = "skip-empty-spaces-smooth"


def restore():
    bus = dbus.SessionBus()
    obj = bus.get_object("org.kde.KWin", "/Effects")
    effects = dbus.Interface(obj, "org.kde.kwin.Effects")
    properties = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    owned = [str(name) for name in properties.Get("org.kde.kwin.Effects", "loadedEffects")
             if str(name) == PLUGIN or str(name).startswith(PLUGIN + "-runtime-")]
    for name in set(owned + [PLUGIN]):
        subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Plugins",
                        "--key", name + "Enabled", "false"], check=True)
        if name in owned:
            effects.unloadEffect(name)
    subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Plugins",
                    "--key", "slideEnabled", "true"], check=True)
    if not effects.isEffectLoaded("slide") and not effects.loadEffect("slide"):
        raise RuntimeError("Native Slide could not be loaded")
    print("Native Slide restored; no desktop order or window assignments changed.")


if __name__ == "__main__":
    restore()
