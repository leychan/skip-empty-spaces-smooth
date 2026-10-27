"""Rollback must use the installed package and avoid existing KWin object IDs."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile


class FakeKWin:
    def __init__(self):
        self.next_id = 2
        self.paths = {"Script2"}
        self.loaded = {}
        self.ran = []

    def isScriptLoaded(self, name):
        return name in self.loaded

    def loadScript(self, path, name, signature):
        assert signature == "ss" and Path(path).is_file()
        number = self.next_id
        self.next_id += 1
        registered = "Script" + str(number) not in self.paths
        self.loaded[name] = (number, registered)
        if registered:
            self.paths.add("Script" + str(number))
        return number

    loadDeclarativeScript = loadScript

    def unloadScript(self, name):
        number, registered = self.loaded.pop(name)
        if registered:
            self.paths.remove("Script" + str(number))

    def get_object(self, service, path):
        assert service == "org.kde.KWin"
        if path == "/Scripting":
            return SimpleNamespace(Introspect=lambda **_: "<node>" + "".join(
                '<node name="' + name + '"/>' for name in self.paths) + "</node>")
        number = int(path.rsplit("Script", 1)[1])
        return SimpleNamespace(run=lambda: self.ran.append(number))


class RollbackTests(unittest.TestCase):
    def setUp(self):
        fake_dbus = SimpleNamespace(Interface=lambda obj, interface: obj)
        path = Path(__file__).resolve().parent.parent / "tools/install.py"
        spec = importlib.util.spec_from_file_location("smooth_install_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", {"dbus": fake_dbus}):
            spec.loader.exec_module(self.module)

    def package(self, data, relative="code/main.js"):
        package = data / "kwin/scripts/skip-empty-spaces"
        (package / "contents/code").mkdir(parents=True)
        (package / "contents/code/main.js").write_text("// previously installed handler\n")
        (package / "metadata.json").write_text(json.dumps({
            "X-Plasma-API": "javascript", "X-Plasma-MainScript": relative}))

    def test_restore_uses_installed_source_and_never_runs_a_colliding_object(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            self.package(data)
            kwin = FakeKWin()
            self.module.restore_previous_script(kwin, kwin, data)
            self.assertEqual(kwin.ran, [3])
            self.assertEqual(set(kwin.loaded), {"skip-empty-spaces"})
            self.assertEqual(kwin.paths, {"Script2", "Script3"})

    def test_invalid_installed_main_file_does_not_start_any_script(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            self.package(data, "../../../outside.js")
            kwin = FakeKWin()
            with self.assertRaisesRegex(RuntimeError, "Invalid main file"):
                self.module.restore_previous_script(kwin, kwin, data)
            self.assertEqual(kwin.ran, [])
            self.assertEqual(kwin.loaded, {})

    def test_old_or_wrong_qml_build_cannot_be_reported_as_updated(self):
        build = "c" * 64
        self.assertFalse(self.module.verify_build("duration: 180\n", build))
        self.assertFalse(self.module.verify_build("buildId: " + "d" * 64, build))
        self.assertTrue(self.module.verify_build("effect:\nbuildId: " + build + "\nprogress: 1", build))

    def test_fresh_runtime_package_preserves_code_and_verified_build(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.zip"
            fresh = Path(directory) / "fresh.zip"
            with ZipFile(original, "w") as package:
                package.writestr("metadata.json", json.dumps({
                    "KPlugin": {"Id": "skip-empty-spaces-smooth"}, "X-SkipEmptySpaces-Build": "c" * 64}))
                package.writestr("contents/ui/main.qml", "// verified code")
            runtime = "skip-empty-spaces-smooth-runtime-cccccccccccc"
            self.module.runtime_archive(original, fresh, runtime)
            with ZipFile(fresh) as package:
                metadata = json.loads(package.read("metadata.json"))
                self.assertEqual(metadata["KPlugin"]["Id"], runtime)
                self.assertEqual(metadata["X-SkipEmptySpaces-Build"], "c" * 64)
                self.assertEqual(package.read("contents/ui/main.qml"), b"// verified code")

    def test_native_renderer_must_match_the_wrapper_build(self):
        build = "a" * 64
        wrapper = "buildId: " + build + "\nnativeLoaded: true\nnativeId: skip-empty-spaces-native-" + build[:12]
        renderer = "renderer: native-window-scene\nbuildId: " + build
        self.assertTrue(self.module.verify_native(wrapper, renderer, build))
        self.assertFalse(self.module.verify_native(wrapper.replace("true", "false"), renderer, build))
        self.assertFalse(self.module.verify_native(wrapper, renderer.replace(build, "b" * 64), build))
        self.assertFalse(self.module.verify_native(wrapper.replace(build[:12], "c" * 12), renderer, build))

    def test_cleanup_only_targets_this_effect_and_its_generated_runtime_ids(self):
        self.assertTrue(self.module.is_owned("skip-empty-spaces-smooth"))
        self.assertTrue(self.module.is_owned("skip-empty-spaces-smooth-runtime-cccccccccccc"))
        self.assertFalse(self.module.is_owned("slide"))
        self.assertFalse(self.module.is_owned("skip-empty-spaces-smooth-external"))


if __name__ == "__main__":
    unittest.main()
