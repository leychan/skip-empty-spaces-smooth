#!/usr/bin/env python3
"""Build and package the native renderer, or package the legacy QML diagnostics."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--qml-only", action="store_true", help="Package the legacy QML renderer for diagnostics")
args = parser.parse_args()
destination = root / "dist" / "skip-empty-spaces-smooth.zip"
destination.parent.mkdir(parents=True, exist_ok=True)
files = [root / "metadata.json", root / "README.md", root / "LICENSE"]
files += sorted((root / "contents").rglob("*"))
fingerprint = hashlib.sha256()
sources = [root / "metadata.json"] + sorted((root / "contents").rglob("*"))
if not args.qml_only:
    sources += sorted((root / "native").rglob("*"))
for path in sources:
    if path.is_file():
        fingerprint.update(str(path.relative_to(root)).encode())
        fingerprint.update(b"\0")
        fingerprint.update(path.read_bytes())
build = fingerprint.hexdigest()
native = None
if not args.qml_only:
    from build_native import build_native
    native = build_native(root, build)
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in files:
        if path.is_file():
            name = str(path.relative_to(root))
            data = path.read_bytes()
            if name == "metadata.json":
                metadata = json.loads(data)
                metadata["X-SkipEmptySpaces-Build"] = build
                if native:
                    metadata["X-SkipEmptySpaces-Renderer"] = "native"
                data = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
            elif name == "contents/ui/main.qml":
                if native:
                    data = (root / "contents/ui/NativeMain.qml").read_bytes()
                data = data.replace(b"@SKIP_EMPTY_BUILD@", build.encode())
            archive.writestr(name, data)
    if native:
        archive.write(native / "qml/libspacesbootstrap.so", "contents/native/libspacesbootstrap.so")
        archive.writestr("contents/native/qmldir", "plugin spacesbootstrap\n")
        renderer = "skip-empty-spaces-native-" + build[:12] + ".so"
        archive.write(native / "plugins/kwin/effects/plugins" / renderer,
                      "contents/plugins/kwin/effects/plugins/" + renderer)
print(destination)
