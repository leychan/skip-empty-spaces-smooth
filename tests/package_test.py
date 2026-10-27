"""Check that an arbitrary standalone checkout produces a complete KWin package."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile


class PackageTests(unittest.TestCase):
    def test_standalone_checkout_from_unrelated_working_directory(self):
        source = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            checkout = parent / "independent checkout"
            checkout.mkdir()
            for filename in ("metadata.json", "README.md", "LICENSE"):
                shutil.copy2(source / filename, checkout / filename)
            shutil.copytree(source / "contents", checkout / "contents")
            (checkout / "tools").mkdir()
            shutil.copy2(source / "tools/package.py", checkout / "tools/package.py")
            command = [sys.executable, str(checkout / "tools/package.py")]
            subprocess.run(command, cwd=parent, check=True, capture_output=True)
            archive = checkout / "dist/skip-empty-spaces-smooth.zip"
            self.assertTrue(archive.is_file())
            self.assertFalse((parent / "outputs").exists())
            with ZipFile(archive) as package:
                self.assertIsNone(package.testzip())
                self.assertEqual(json.loads(package.read("metadata.json"))["KPackageStructure"], "KWin/Effect")
                self.assertEqual(package.read("contents/ui/main.qml"), (source / "contents/ui/main.qml").read_bytes())
                self.assertTrue({"README.md", "LICENSE", "contents/code/navigation.js",
                                 "contents/ui/DesktopPage.qml", "contents/ui/SlideView.qml"}.issubset(package.namelist()))
                self.assertFalse(any(name.startswith(("/", "../", "tools/", "tests/")) for name in package.namelist()))
            (checkout / "README.md").write_text("Updated documentation\n")
            subprocess.run(command, cwd=parent, check=True, capture_output=True)
            with ZipFile(archive) as package:
                self.assertEqual(package.read("README.md"), b"Updated documentation\n")


if __name__ == "__main__":
    unittest.main()
