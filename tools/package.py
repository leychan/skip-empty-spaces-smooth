#!/usr/bin/env python3
"""Package the QML effect without native plugins or KWin binary changes."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
destination = root / "dist" / "skip-empty-spaces-smooth.zip"
destination.parent.mkdir(parents=True, exist_ok=True)
files = [root / "metadata.json", root / "README.md", root / "LICENSE"]
files += sorted((root / "contents").rglob("*"))
with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
    for path in files:
        if path.is_file():
            archive.write(path, path.relative_to(root))
print(destination)
