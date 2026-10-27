#!/usr/bin/env python3
"""Briefly preview a two-page frame without switching desktops, then remove it."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


def preview(output=None, progress=0.4):
    root = Path(__file__).resolve().parent.parent
    plugin = "skip-empty-preview-" + uuid.uuid4().hex
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    effects = dbus.Interface(bus.get_object("org.kde.KWin", "/Effects"), "org.kde.kwin.Effects")
    loop = GLib.MainLoop()
    reports = []
    capture = Path(tempfile.gettempdir()) / (plugin + ".png")

    def screenshot():
        try:
            subprocess.run(["flameshot", "full", "--path", str(capture)],
                           check=True, timeout=8, capture_output=True)
        except (subprocess.SubprocessError, FileNotFoundError) as error:
            print("Screenshot unavailable:", str(error), flush=True)
        loop.quit()
        return False

    class Receiver(dbus.service.Object):
        @dbus.service.method("org.codex.SmoothSpacesPreview", in_signature="s", out_signature="")
        def Report(self, value):
            reports.append(json.loads(str(value)))
            if len(reports) == 1:
                GLib.timeout_add(250, screenshot)

    name = dbus.service.BusName("org.codex.SmoothSpacesPreview", bus)
    receiver = Receiver(bus, "/preview")
    addition = r'''
    property KWin.DBusCall previewReport: KWin.DBusCall {
        service: "org.codex.SmoothSpacesPreview"
        path: "/preview"
        dbusInterface: "org.codex.SmoothSpacesPreview"
        method: "Report"
    }
    property Timer previewReady: Timer {
        interval: 80
        repeat: true
        onTriggered: {
            var view = root.viewForScreen(root.activeGesture.output);
            if (!view || !view.rootItem || view.rootItem.width < 1) return;
            previewReady.stop();
            root.previewReport.arguments = [JSON.stringify({
                output: root.activeGesture.output.name,
                origin: root.activeGesture.origin.name,
                visualTarget: root.activeGesture.target.name,
                skippedNativeTarget: root.activeGesture.nativeTarget.name,
                width: view.rootItem.width, height: view.rootItem.height,
                progress: root.progress,
                horizontalGap: root.horizontalGap,
                slideBackground: root.slideBackground,
                animationTimeFactor: root.animationTimeFactor,
                outputScale: root.activeGesture.output.devicePixelRatio,
                renderScale: view.rootItem.previewDpr
            })];
            root.previewReport.call();
        }
    }
    property Timer previewStop: Timer {
        interval: 3000
        onTriggered: root.abort()
    }
    Component.onCompleted: Qt.callLater(function () {
        root.activeGesture = Navigation.plan(KWin.Workspace, 1);
        if (!root.activeGesture) return;
        var selected = __OUTPUT__;
        if (selected) {
            var screen = KWin.Workspace.screens.find(function(s) { return s.name === selected; });
            if (!screen) return;
            root.activeGesture.output = screen;
            root.activeGesture.origin = KWin.Workspace.currentDesktopForScreen(screen);
            root.activeGesture.target = KWin.Workspace.desktops.find(function(d) {
                return d !== root.activeGesture.origin && Navigation.occupied(KWin.Workspace, d, screen, KWin.Workspace.currentActivity);
            }) || root.activeGesture.origin;
        }
        root.progress = __PROGRESS__;
        root.tracking = true;
        root.visible = true;
        previewReady.start();
        previewStop.start();
    })
'''.replace("__OUTPUT__", json.dumps(output)).replace("__PROGRESS__", json.dumps(progress))
    installed = False
    with tempfile.TemporaryDirectory(prefix=plugin) as directory:
        temporary = Path(directory)
        shutil.copytree(root / "contents", temporary / "contents")
        metadata = json.loads((root / "metadata.json").read_text())
        metadata["KPlugin"]["Id"] = plugin
        metadata["KPlugin"]["EnabledByDefault"] = False
        (temporary / "metadata.json").write_text(json.dumps(metadata))
        main = temporary / "contents/ui/main.qml"
        source = main.read_text()
        end = source.rfind("}")
        main.write_text(source[:end] + addition + source[end:])
        view = temporary / "contents/ui/SlideView.qml"
        source = view.read_text().replace("id: view", "id: view\n    readonly property real previewDpr: Window.window ? Window.window.devicePixelRatio : 0")
        view.write_text(source)
        try:
            subprocess.run(["kpackagetool6", "--type", "KWin/Effect", "--install", str(temporary)],
                           check=True, capture_output=True)
            installed = True
            if not effects.loadEffect(plugin):
                raise RuntimeError("Preview effect could not load")
            GLib.timeout_add_seconds(6, loop.quit)
            loop.run()
            if not reports:
                raise RuntimeError("No rendered view was created")
            print(json.dumps({"render": reports[0], "screenshot": str(capture) if capture.exists() else None},
                             ensure_ascii=False))
        finally:
            effects.unloadEffect(plugin)
            if installed:
                subprocess.run(["kpackagetool6", "--type", "KWin/Effect", "--remove", plugin],
                               check=True, capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Output name; defaults to the active screen")
    parser.add_argument("--progress", type=float, default=0.4, help="Frozen swipe progress between 0 and 1")
    args = parser.parse_args()
    if not 0 <= args.progress <= 1:
        parser.error("progress must be between 0 and 1")
    preview(args.output, args.progress)
