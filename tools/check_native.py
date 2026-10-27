#!/usr/bin/env python3
"""Verify the loaded native renderer; optionally benchmark or compare a still frame."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time

import dbus


def check(output, benchmark=False, compare=False, crop=None):
    bus = dbus.SessionBus()
    obj = bus.get_object("org.kde.KWin", "/Effects")
    effects = dbus.Interface(obj, "org.kde.kwin.Effects")
    properties = dbus.Interface(obj, "org.freedesktop.DBus.Properties")
    loaded = [str(s) for s in properties.Get("org.kde.kwin.Effects", "loadedEffects")]
    native = [s for s in loaded if s.startswith("skip-empty-spaces-native-")]
    wrappers = [s for s in loaded if s == "skip-empty-spaces-smooth" or s.startswith("skip-empty-spaces-smooth-runtime-")]
    if len(native) != 1 or len(wrappers) != 1:
        raise RuntimeError("Expected one native renderer and one package entry: " + repr((native, wrappers)))

    def info(name):
        return dict(line.split(": ", 1) for line in str(effects.supportInformation(name)).splitlines() if ": " in line)

    wrapper = info(wrappers[0])
    renderer = info(native[0])
    assert wrapper.get("nativeLoaded") == "true", wrapper
    assert wrapper.get("nativeId") == native[0], wrapper
    assert wrapper.get("buildId") == renderer.get("buildId"), (wrapper, renderer)
    assert renderer.get("renderer") == "native-window-scene", renderer
    assert not effects.isEffectLoaded("slide"), "Two desktop renderers are enabled"
    api = dbus.Interface(bus.get_object("org.kde.KWin", "/OccupiedSpaces"), "org.kde.kwin.OccupiedSpaces")
    report = {"wrapper": wrappers[0], "renderer": native[0], "build": renderer["buildId"], "verified": True}
    if (benchmark or compare) and renderer.get("screenLocked") == "true":
        raise RuntimeError("The session is locked; unlock before running a visual benchmark or screenshot comparison")
    if benchmark:
        since = int(time.time() * 1000)
        if not api.benchmark(output):
            raise RuntimeError("Renderer is busy or output is unavailable")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            state = info(native[0])
            if state.get("screenLocked") == "true":
                raise RuntimeError("The session locked during the benchmark")
            if state.get("active") == "false": break
            time.sleep(.01)
        else:
            raise RuntimeError("Benchmark did not finish")
        events = [r for r in json.loads(state["traceLog"]) if r["time"] >= since]
        start = next(r["time"] for r in events if r["event"] == "release")
        end = next(r["time"] for r in events if r["event"] == "finish")
        report["benchmark"] = {"duration_ms": end - start, "compositor_frames": int(state["frames"]),
            "render_passes_per_second": round(int(state["frames"]) * 1000 / (end - start), 1),
            "finalProgress": float(state["progress"])}
        assert float(state["progress"]) == 0, state
    if compare:
        before = Path(tempfile.gettempdir()) / "occupied-spaces-before.png"
        during = Path(tempfile.gettempdir()) / "occupied-spaces-native.png"
        subprocess.run(["flameshot", "full", "--path", str(before)], check=True, capture_output=True)
        if not api.preview(output, 0.0):
            raise RuntimeError("Renderer is busy or output is unavailable")
        try:
            time.sleep(.12)
            subprocess.run(["flameshot", "full", "--path", str(during)], check=True, capture_output=True)
        finally:
            api.endPreview()
        report["comparison"] = {"before": str(before), "native": str(during)}
        if crop:
            from PIL import Image, ImageChops, ImageStat
            a, b = [Image.open(path).convert("RGB").crop(crop) for path in (before, during)]
            report["comparison"]["crop"] = crop
            report["comparison"]["mean_pixel_difference"] = ImageStat.Stat(ImageChops.difference(a, b)).mean
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="eDP-1")
    parser.add_argument("--benchmark", action="store_true", help="Animate back to the current desktop without changing it")
    parser.add_argument("--compare", action="store_true", help="Compare the real desktop with a native zero-offset preview")
    parser.add_argument("--crop", help="Optional screenshot pixel region x1,y1,x2,y2 for --compare (requires Pillow)")
    args = parser.parse_args()
    crop = tuple(map(int, args.crop.split(","))) if args.crop else None
    if crop and (len(crop) != 4 or crop[2] <= crop[0] or crop[3] <= crop[1]):
        parser.error("crop must contain x1,y1,x2,y2")
    check(args.output, args.benchmark, args.compare, crop)
