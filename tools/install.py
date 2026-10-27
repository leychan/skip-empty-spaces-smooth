#!/usr/bin/env python3
"""Install the continuous QML animation, with rollback and no global script start."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import dbus


PLUGIN = "skip-empty-spaces-smooth"
OLD = "skip-empty-spaces"


def setting(key, value):
    subprocess.run(["kwriteconfig6", "--file", "kwinrc", "--group", "Plugins",
                    "--key", key + "Enabled", "true" if value else "false"], check=True)


def restore_previous_script(bus, scripting, data):
    """Restart the installed legacy package without a sibling source checkout."""
    if scripting.isScriptLoaded(OLD):
        return
    package = next((data / folder / OLD for folder in ("kwin-wayland/scripts", "kwin/scripts")
                    if (data / folder / OLD / "metadata.json").is_file()), None)
    if package is None:
        raise RuntimeError("Cannot locate the previously installed skip handler")
    metadata = json.loads((package / "metadata.json").read_text())
    declarative = metadata.get("X-Plasma-API") == "declarativescript"
    relative = metadata.get("X-Plasma-MainScript", "ui/main.qml" if declarative else "code/main.js")
    source = (package / "contents" / relative).resolve()
    if not source.is_relative_to(package.resolve()) or not source.is_file():
        raise RuntimeError("Invalid main file in the installed legacy package")
    service = bus.get_object("org.kde.KWin", "/Scripting")

    def paths():
        xml = service.Introspect(dbus_interface="org.freedesktop.DBus.Introspectable")
        return {node.attrib["name"] for node in ElementTree.fromstring(str(xml)).findall("node")}

    padding = []
    loaded = False
    try:
        with tempfile.TemporaryDirectory(prefix="skip-empty-spaces-restore-") as temporary:
            noop = Path(temporary) / "noop.js"
            noop.write_text("// Temporary ID reservation; never started.\n")
            for _ in range(32):
                name = OLD + "-reserve-" + uuid.uuid4().hex
                reserved = scripting.loadScript(str(noop), name, signature="ss")
                if reserved < 0:
                    raise RuntimeError("Cannot reserve a KWin script ID")
                padding.append(name)
                if "Script" + str(reserved + 1) not in paths():
                    break
            else:
                raise RuntimeError("Cannot allocate an unused KWin object ID")
            before = paths()
            loader = scripting.loadDeclarativeScript if declarative else scripting.loadScript
            script_id = loader(str(source), OLD, signature="ss")
            loaded = script_id >= 0
            if not loaded or "Script" + str(script_id) in before:
                raise RuntimeError("Cannot safely reload the previous skip handler")
            script = dbus.Interface(bus.get_object("org.kde.KWin", "/Scripting/Script" + str(script_id)),
                                    "org.kde.kwin.Script")
            script.run()
    except Exception:
        if loaded:
            scripting.unloadScript(OLD)
        raise
    finally:
        for name in reversed(padding):
            scripting.unloadScript(name)


def is_owned(name):
    return name == PLUGIN or name.startswith(PLUGIN + "-runtime-")


def verify_build(information, build):
    return "buildId: " + build in str(information).splitlines()


def runtime_archive(source, destination, plugin):
    with ZipFile(source) as original, ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == "metadata.json":
                metadata = json.loads(data)
                metadata["KPlugin"]["Id"] = plugin
                data = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
            archive.writestr(item.filename, data)


def install(enable=True):
    root = Path(__file__).resolve().parent.parent
    subprocess.run(["/usr/bin/python3", str(root / "tools/package.py")], check=True)
    archive = root / "dist" / (PLUGIN + ".zip")
    data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    effect_root = data / "kwin/effects"
    with ZipFile(archive) as package:
        build = json.loads(package.read("metadata.json"))["X-SkipEmptySpaces-Build"]
    bus = dbus.SessionBus()
    effects = dbus.Interface(bus.get_object("org.kde.KWin", "/Effects"), "org.kde.kwin.Effects")
    scripting = dbus.Interface(bus.get_object("org.kde.KWin", "/Scripting", introspect=False), "org.kde.kwin.Scripting")
    properties = dbus.Interface(bus.get_object("org.kde.KWin", "/Effects"), "org.freedesktop.DBus.Properties")
    previous = [str(name) for name in properties.Get("org.kde.kwin.Effects", "loadedEffects") if is_owned(str(name))]
    installed_before = [path.name for path in effect_root.iterdir()
                        if is_owned(path.name) and (path / "metadata.json").is_file()] if effect_root.exists() else []
    slide_loaded = bool(effects.isEffectLoaded("slide"))
    old_loaded = bool(scripting.isScriptLoaded(OLD))
    for name in previous:
        effects.unloadEffect(name)
    active = PLUGIN
    attempted = []

    def load(name, archive):
        mode = "--upgrade" if (effect_root / name).exists() else "--install"
        subprocess.run(["kpackagetool6", "--type", "KWin/Effect", mode, str(archive)], check=True)
        subprocess.run(["/usr/bin/python3", str(root / "tools/sync_settings.py"),
                        "--no-reconfigure", "--plugin", name], check=True)
        attempted.append(name)
        if not effects.loadEffect(name):
            raise RuntimeError("KWin could not compile/load the new QML effect")

    try:
        load(active, archive)
        if not verify_build(effects.supportInformation(active), build):
            # KWin shares a QQmlEngine across reloads. The stable path can still
            # instantiate an old component after its files were upgraded. A
            # content-addressed package gives every changed QML/JS file a fresh URL.
            effects.unloadEffect(active)
            active = PLUGIN + "-runtime-" + build[:12]
            hot_archive = root / "dist" / (active + ".zip")
            runtime_archive(archive, hot_archive, active)
            load(active, hot_archive)
        if not verify_build(effects.supportInformation(active), build):
            raise RuntimeError("KWin is running a stale QML build; refusing to report success")
        if enable:
            # The replacement supplies both the live gesture and ordinary desktop
            # animation. Only one renderer and one release handler may own it.
            if old_loaded:
                scripting.unloadScript(OLD)
                deadline = time.monotonic() + 2
                while scripting.isScriptLoaded(OLD):
                    if time.monotonic() > deadline:
                        raise RuntimeError("Previous skip handler did not unload")
                    time.sleep(0.02)
            effects.unloadEffect("slide")
            setting(OLD, False)
            setting("slide", False)
            for name in set(installed_before + attempted):
                setting(name, name == active)
            assert effects.isEffectLoaded(active)
            assert not effects.isEffectLoaded("slide")
            assert not scripting.isScriptLoaded(OLD)
            # Keep one user-visible effect entry, even after a same-session hot update.
            for name in set(installed_before + attempted) - {active}:
                if (effect_root / name).exists():
                    result = subprocess.run(["kpackagetool6", "--type", "KWin/Effect", "--remove", name],
                                            capture_output=True, text=True)
                    if result.returncode:
                        print("Previous package remains installed but disabled:", name)
        else:
            effects.unloadEffect(active)
            for name in previous:
                effects.loadEffect(name)
        print(json.dumps({"installed": str(effect_root / active), "activeId": active,
                          "buildVerified": build, "loaded": enable,
                          "replacesNativeSlide": enable}, ensure_ascii=False))
    except Exception:
        for name in attempted:
            effects.unloadEffect(name)
        if slide_loaded:
            effects.loadEffect("slide")
        for name in previous:
            effects.loadEffect(name)
        # Before the enable stage, no settings have changed. An interrupted
        # migration is restored to the known native renderer and old skip handler.
        if enable:
            setting("slide", slide_loaded)
            setting(OLD, old_loaded)
            for name in set(attempted + previous):
                setting(name, name in previous)
            if old_loaded:
                restore_previous_script(bus, scripting, data)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-only", action="store_true", help="Load inactive effect without replacing the working renderer")
    arguments = parser.parse_args()
    install(enable=not arguments.stage_only)
