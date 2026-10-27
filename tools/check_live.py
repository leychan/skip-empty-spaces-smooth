#!/usr/bin/env python3
"""Compile a temporary copy inside KWin and inspect its actual QML objects.

Uses the distro Python's dbus-python and PyGObject. Does not move windows,
switch desktops, change settings or start unrelated KWin scripts.
"""
import json
from pathlib import Path
import shutil
import tempfile
import uuid
from xml.etree import ElementTree

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


def check():
    root = Path(__file__).resolve().parent.parent
    plugin = "skip-empty-spaces-smooth-check-" + uuid.uuid4().hex
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    received = []

    class Receiver(dbus.service.Object):
        @dbus.service.method("org.codex.SkipEmptySpacesCheck", in_signature="s", out_signature="")
        def Report(self, value):
            received.append(json.loads(str(value)))
            GLib.idle_add(loop.quit)

    name = dbus.service.BusName("org.codex.SkipEmptySpacesCheck", bus)
    receiver = Receiver(bus, "/check")
    scripting = dbus.Interface(
        bus.get_object("org.kde.KWin", "/Scripting", introspect=False),
        "org.kde.kwin.Scripting",
    )
    probe = r'''
import QtQuick
import org.kde.kwin 3.0 as KWin
import "contents/code/navigation.js" as Navigation
QtObject {
    id: probeRoot
    property var motionRoot: null
    property var pendingReport: null
    property KWin.DBusCall probeReport: KWin.DBusCall {
        service: "org.codex.SkipEmptySpacesCheck"
        path: "/check"
        dbusInterface: "org.codex.SkipEmptySpacesCheck"
        method: "Report"
    }
    property Timer motionProbe: Timer {
        interval: 200
        onTriggered: {
            stop();
            probeRoot.pendingReport.springProgress = probeRoot.motionRoot.progress;
            probeRoot.motionRoot.abort();
            probeRoot.probeReport.arguments = [JSON.stringify(probeRoot.pendingReport)];
            probeRoot.probeReport.call();
        }
    }
    Component.onCompleted: {
            var result;
            try {
            var component = Qt.createComponent("contents/ui/main.qml");
            if (component.status !== Component.Ready) throw new Error(component.errorString());
            var root = component.createObject(probeRoot);
            if (!root) throw new Error(component.errorString());
            var handlers = [];
            for (var i = 0; i < root.gestures.count; ++i) {
                var handler = root.gestures.objectAt(i);
                handlers.push({ fingers: handler.fingerCount, direction: handler.direction,
                    step: handler.modelData.step, device: handler.deviceType });
            }
            var capture = Navigation.plan(KWin.Workspace, 1);
            root.activeGesture = capture;
            root.progress = 0.4;
            var viewComponent = Qt.createComponent("contents/ui/SlideView.qml");
            if (viewComponent.status !== Component.Ready) throw new Error(viewComponent.errorString());
            var view = viewComponent.createObject(probeRoot, {
                controller: root, screen: KWin.Workspace.activeScreen, width: 960, height: 540
            });
            if (!view) throw new Error(viewComponent.errorString());
            result = {
                handlers: handlers,
                hasPerScreenSetter: typeof KWin.Workspace.setCurrentDesktopForScreen === "function",
                viewReady: view.moving,
                capture: capture ? {
                    output: capture.output.name, origin: capture.origin.name,
                    target: capture.target.name, nativeTarget: capture.nativeTarget.name,
                    desktops: capture.layout.length, wraps: capture.wraps,
                    occupiedHere: Navigation.occupied(KWin.Workspace, capture.origin,
                        capture.output, capture.activity)
                } : null
            };
            } catch (error) {
                result = { error: String(error) };
            }
            if (result.error) {
                probeRoot.probeReport.arguments = [JSON.stringify(result)];
                probeRoot.probeReport.call();
            } else {
                probeRoot.motionRoot = root;
                probeRoot.pendingReport = result;
                root.startSettling(1);
                // This probe has no displayed SceneView. Feed the same
                // elapsed interval that a live output supplies before sync.
                var started = root.lastFrameTime;
                root.advanceFrame(started + 200);
                var position = root.progress;
                root.advanceFrame(started + 200);
                root.advanceFrame(started + 190);
                result.outputClockSafe = root.progress === position && root.lastFrameTime === started + 200;
                probeRoot.motionProbe.start();
            }
    }
}
'''
    with tempfile.TemporaryDirectory(prefix="skip-empty-spaces-check-") as temporary:
        contents = Path(temporary) / "contents"
        shutil.copytree(root / "contents", contents)
        main = Path(temporary) / "probe.qml"
        main.write_text(probe)
        loaded = []
        try:
            # KWin 6.7 allocates IDs from the current script count. After earlier
            # unloads that can collide with an existing D-Bus object. Keep inert
            # instances loaded until we obtain a genuinely unused object path.
            for attempt in range(32):
                xml = bus.get_object("org.kde.KWin", "/Scripting").Introspect(
                    dbus_interface="org.freedesktop.DBus.Introspectable")
                existing = {node.attrib["name"] for node in ElementTree.fromstring(str(xml)).findall("node")}
                candidate = plugin + "-" + str(attempt)
                script_id = scripting.loadDeclarativeScript(str(main), candidate, signature="ss")
                if script_id < 0:
                    raise RuntimeError("KWin refused the temporary QML script")
                loaded.append(candidate)
                if "Script" + str(script_id) not in existing:
                    break
            else:
                raise RuntimeError("Could not allocate an unused KWin D-Bus object")
            script = dbus.Interface(
                bus.get_object("org.kde.KWin", "/Scripting/Script" + str(script_id)),
                "org.kde.kwin.Script",
            )
            script.run()
            GLib.timeout_add_seconds(10, loop.quit)
            loop.run()
            if not received:
                raise RuntimeError("QML did not report readiness; check KWin's warnings")
            report = received[0]
            assert "error" not in report, report
            assert report["hasPerScreenSetter"], report
            assert report["viewReady"], report
            assert report["outputClockSafe"], report
            assert 0.4 < report["springProgress"] < 1, report
            assert sorted((h["fingers"], h["step"]) for h in report["handlers"]) == [
                (3, -1), (3, 1), (4, -1), (4, 1)
            ], report
            assert len({h["direction"] for h in report["handlers"]}) == 2, report
            print(json.dumps(report, ensure_ascii=False))
        finally:
            for candidate in reversed(loaded):
                scripting.unloadScript(candidate)


if __name__ == "__main__":
    check()
