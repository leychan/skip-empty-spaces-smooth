#!/usr/bin/env python3
"""Copy native Slide preferences into the occupied-space renderer."""
import argparse
import json
import math
import subprocess


PLUGIN = "skip-empty-spaces-smooth"


def read_value(filename, group, key, default):
    return subprocess.check_output([
        "kreadconfig6", "--file", filename, "--group", group,
        "--key", key, "--default", str(default),
    ], text=True).strip()


def native_settings(reader=read_value):
    try:
        gap = max(0, int(reader("kwinrc", "Effect-slide", "HorizontalGap", 45)))
    except ValueError:
        gap = 45
    background = reader("kwinrc", "Effect-slide", "SlideBackground", "true").lower() == "true"
    global_factor = reader("kdeglobals", "KDE", "AnimationDurationFactor", 1)
    try:
        factor = float(reader("kwinrc", "KDE", "AnimationDurationFactor", global_factor))
        if not math.isfinite(factor):
            factor = 1.0
        factor = max(0.0, factor)
    except ValueError:
        factor = 1.0
    return {"HorizontalGap": str(gap), "SlideBackground": "true" if background else "false",
            "AnimationTimeFactor": str(factor)}


def sync(reconfigure=True, plugin=None):
    if plugin is None:
        import dbus
        obj = dbus.SessionBus().get_object("org.kde.KWin", "/Effects")
        properties = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        active = [str(name) for name in properties.Get("org.kde.kwin.Effects", "loadedEffects")
                  if str(name) == PLUGIN or str(name).startswith(PLUGIN + "-runtime-")]
        plugin = active[0] if len(active) == 1 else PLUGIN
    settings = native_settings()
    for destination in {plugin, PLUGIN}:
        for key, value in settings.items():
            subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Effect-" + destination,
                            "--key", key, value], check=True)
    if reconfigure:
        subprocess.run(["qdbus6", "org.kde.KWin", "/Effects", "org.kde.kwin.Effects.reconfigureEffect", plugin], check=True)
        import dbus
        obj = dbus.SessionBus().get_object("org.kde.KWin", "/Effects")
        properties = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
        effects = dbus.Interface(obj, "org.kde.kwin.Effects")
        for name in properties.Get("org.kde.kwin.Effects", "loadedEffects"):
            if str(name).startswith("skip-empty-spaces-native-"):
                effects.reconfigureEffect(name)
    print(json.dumps(settings))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-reconfigure", action="store_true")
    parser.add_argument("--plugin", help="Exact runtime ID; otherwise discover the running build")
    options = parser.parse_args()
    sync(reconfigure=not options.no_reconfigure, plugin=options.plugin)
