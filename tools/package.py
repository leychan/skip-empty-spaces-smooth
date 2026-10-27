#!/usr/bin/env python3
"""Package the QML effect without native plugins or KWin binary changes."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
destination = root / "dist" / "skip-empty-spaces-smooth.zip"
destination.parent.mkdir(parents=True, exist_ok=True)
files = [root / "metadata.json", root / "README.md", root / "LICENSE"]
files += sorted((root / "contents").rglob("*"))
fingerprint = hashlib.sha256()
for path in [root / "metadata.json"] + sorted((root / "contents").rglob("*")):
    if path.is_file():
        fingerprint.update(str(path.relative_to(root)).encode())
        fingerprint.update(b"\0")
        fingerprint.update(path.read_bytes())
build = fingerprint.hexdigest()
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in files:
        if path.is_file():
            name = str(path.relative_to(root))
            data = path.read_bytes()
            if name == "metadata.json":
                metadata = json.loads(data)
                metadata["X-SkipEmptySpaces-Build"] = build
                data = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
            elif name == "contents/ui/main.qml":
                data = data.replace(b"@SKIP_EMPTY_BUILD@", build.encode())
            archive.writestr(name, data)
print(destination)
