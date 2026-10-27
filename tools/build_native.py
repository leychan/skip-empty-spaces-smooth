#!/usr/bin/env python3
"""Build native modules against the local KWin SDK; never install system files."""
from pathlib import Path
import subprocess


def build_native(root, build):
    directory = root / "dist" / ("native-" + build[:12])
    subprocess.run(["cmake", "-S", str(root / "native"), "-B", str(directory),
                    "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release", "-DSPACES_BUILD=" + build],
                   check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["cmake", "--build", str(directory), "-j", "2"], check=True)
    subprocess.run(["ctest", "--test-dir", str(directory), "--output-on-failure"], check=True)
    return directory
