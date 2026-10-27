#!/usr/bin/env python3
"""Measure offscreen view renders during a temporary swipe, without changing desktops.

These are QQuickWindow render callbacks, not monitor presentation timestamps.
The temporary effect and its package are removed even if the probe fails.
"""
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


def summarize(samples):
    intervals = sorted(samples[i][0] - samples[i - 1][0] for i in range(1, len(samples)))
    elapsed = samples[-1][0] - samples[0][0] if len(samples) > 1 else 0
    changes = sum(samples[i][1] != samples[i - 1][1] for i in range(1, len(samples)))
    return {
        "renders": len(samples), "elapsed_ms": elapsed,
        "renders_per_second": round((len(samples) - 1) * 1000 / elapsed, 1) if elapsed else None,
        "motion_updates_per_second": round(changes * 1000 / elapsed, 1) if elapsed else None,
        "interval_p50_ms": intervals[len(intervals) // 2] if intervals else None,
        "interval_p95_ms": intervals[int((len(intervals) - 1) * .95)] if intervals else None,
        "interval_max_ms": max(intervals) if intervals else None,
    }


def benchmark(output=None, driver="settle", cancel=False):
    root = Path(__file__).resolve().parent.parent
    plugin = "skip-empty-benchmark-" + uuid.uuid4().hex
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    effects = dbus.Interface(bus.get_object("org.kde.KWin", "/Effects"), "org.kde.kwin.Effects")
    loop = GLib.MainLoop()
    reports = []

    class Receiver(dbus.service.Object):
        @dbus.service.method("org.codex.SmoothSpacesBenchmark", in_signature="s", out_signature="")
        def Report(self, value):
            reports.append(json.loads(str(value)))
            loop.quit()

    name = dbus.service.BusName("org.codex.SmoothSpacesBenchmark", bus)
    receiver = Receiver(bus, "/benchmark")
    addition = r'''
    property bool measuring: false
    property real probeElapsed: 0
    property int probeTicks: 0
    property var renderSamples: ({})
    property real probeStarted: 0
    function recordRender(screen) {
        if (!measuring) return;
        if (!renderSamples[screen]) renderSamples[screen] = [];
        renderSamples[screen].push([Date.now(), root.progress]);
    }
    property KWin.DBusCall probeReport: KWin.DBusCall {
        service: "org.codex.SmoothSpacesBenchmark"
        path: "/benchmark"
        dbusInterface: "org.codex.SmoothSpacesBenchmark"
        method: "Report"
    }
    property Timer probeWarmup: Timer {
        interval: 350
        onTriggered: {
            root.measuring = true;
            root.probeStarted = Date.now();
            if (__DRIVER__ === "timeline") root.probeAnimation.start();
            if (__DRIVER__ === "settle") {
                root.tracking = false;
                root.startSettling(__CANCEL__ ? 0 : 1);
            }
            root.probeStop.start();
        }
    }
    property FrameAnimation probeAnimation: FrameAnimation {
        onTriggered: {
            root.probeTicks++;
            root.probeElapsed += frameTime;
            root.progress = 0.1 + 0.8 * Math.min(root.probeElapsed / 2, 1);
        }
    }
    property Timer probeStop: Timer {
        interval: 2000
        onTriggered: root.completeProbe()
    }
    function completeProbe() {
        if (!root.measuring) return;
        root.measuring = false;
        root.probeAnimation.stop();
        root.probeStop.stop();
        root.probeReport.arguments = [JSON.stringify({
            output: __OUTPUT__ || "active",
            driver: __DRIVER__, cancel: __CANCEL__,
            duration_ms: Date.now() - root.probeStarted,
            finalProgress: root.progress,
            clockTicks: root.probeTicks,
            clockElapsed: root.probeElapsed,
            samples: root.renderSamples
        })];
        root.probeReport.call();
        root.abort();
    }
    onVisibleChanged: if (!visible && measuring) Qt.callLater(root.completeProbe)
    Component.onCompleted: Qt.callLater(function () {
        var selectedOutput = __OUTPUT__;
        var plan = Navigation.plan(KWin.Workspace, 1);
        if (!plan) return;
        if (selectedOutput) {
            var screen = KWin.Workspace.screens.find(function(s) { return s.name === selectedOutput; });
            if (!screen) return;
            plan.output = screen;
            plan.origin = KWin.Workspace.currentDesktopForScreen(screen);
            plan.target = KWin.Workspace.desktops.find(function(d) {
                return d !== plan.origin && Navigation.occupied(KWin.Workspace, d, screen, plan.activity);
            }) || plan.origin;
        }
        root.activeGesture = plan;
        root.progress = __CANCEL__ ? 0.65 : 0.1;
        root.tracking = true;
        root.visible = true;
        root.probeWarmup.start();
    })
'''.replace("__OUTPUT__", json.dumps(output)).replace("__DRIVER__", json.dumps(driver)).replace("__CANCEL__", json.dumps(cancel))
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
        source = view.read_text()
        end = source.rfind("}")
        observer = '''
    Connections {
        target: view.Window.window
        function onAfterRendering() { controller.recordRender(view.screen.name); }
    }
'''
        if driver == "render":
            observer = '''
    property real probeStart: 0
    Connections {
        target: view.Window.window
        function onAfterRendering() {
            controller.recordRender(view.screen.name);
            if (view.moving) view.KWin.SceneView.scheduleRepaint();
        }
        function onAfterAnimating() {
            if (!view.moving || !controller.measuring) return;
            var now = Date.now();
            if (!view.probeStart) view.probeStart = now;
            controller.progress = 0.1 + 0.8 * Math.min((now - view.probeStart) / 2000, 1);
        }
    }
'''
        view.write_text(source[:end] + observer + source[end:])
        try:
            subprocess.run(["kpackagetool6", "--type", "KWin/Effect", "--install", str(temporary)],
                           check=True, capture_output=True)
            installed = True
            if not effects.loadEffect(plugin):
                raise RuntimeError("Benchmark effect could not load")
            GLib.timeout_add_seconds(7, loop.quit)
            loop.run()
            if not reports:
                raise RuntimeError("No render report received")
            report = reports[0]
            report["views"] = {key: summarize(value) for key, value in report.pop("samples").items()}
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            effects.unloadEffect(plugin)
            if installed:
                subprocess.run(["kpackagetool6", "--type", "KWin/Effect", "--remove", plugin],
                               check=True, capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Output name; defaults to the active screen")
    parser.add_argument("--driver", choices=("settle", "timeline", "render"), default="settle",
                        help="Production settling, independent clock sweep, or render-paced sweep")
    parser.add_argument("--cancel", action="store_true", help="Measure settling back to the origin")
    args = parser.parse_args()
    benchmark(args.output, args.driver, args.cancel)
