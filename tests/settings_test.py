import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("smooth_settings", Path(__file__).resolve().parent.parent / "tools/sync_settings.py")
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class SettingsTests(unittest.TestCase):
    def reader(self, values):
        return lambda filename, group, key, default: values.get((filename, group, key), str(default))

    def test_reads_native_geometry_background_and_global_animation_speed(self):
        reader = self.reader({
            ("kwinrc", "Effect-slide", "HorizontalGap"): "72",
            ("kwinrc", "Effect-slide", "SlideBackground"): "false",
            ("kdeglobals", "KDE", "AnimationDurationFactor"): "1.5",
        })
        self.assertEqual(settings.native_settings(reader), {
            "HorizontalGap": "72", "SlideBackground": "false", "AnimationTimeFactor": "1.5"})

    def test_explicit_kwin_speed_override_including_zero_is_preserved(self):
        reader = self.reader({
            ("kdeglobals", "KDE", "AnimationDurationFactor"): "2",
            ("kwinrc", "KDE", "AnimationDurationFactor"): "0",
        })
        self.assertEqual(settings.native_settings(reader)["AnimationTimeFactor"], "0.0")

    def test_invalid_settings_fall_back_to_finite_native_defaults(self):
        reader = self.reader({
            ("kwinrc", "Effect-slide", "HorizontalGap"): "invalid",
            ("kwinrc", "KDE", "AnimationDurationFactor"): "nan",
        })
        self.assertEqual(settings.native_settings(reader), {
            "HorizontalGap": "45", "SlideBackground": "true", "AnimationTimeFactor": "1.0"})


if __name__ == "__main__":
    unittest.main()
