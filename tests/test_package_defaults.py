"""Regression tests for production package pins and first-install defaults."""

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent


class TestPackageDefaults(unittest.TestCase):
    """Keep release inputs reproducible and free of user viewing data."""

    def test_mpv_uses_available_official_release(self):
        config = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))

        dependency = config["dependencies"]["mpv"]
        self.assertEqual(dependency["version"], "v0.42.0")
        self.assertEqual(
            dependency["url"],
            "https://github.com/mpv-player/mpv/releases",
        )

    def test_vc_runtime_ships_next_to_mpv(self):
        """官方 MSVC 构建的 mpv.exe 动态链接这三个 DLL，Windows 不自带。"""
        config = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))

        dependency = config["dependencies"]["vc_runtime"]
        self.assertTrue(dependency["enabled"])
        self.assertEqual(
            dependency["custom_install_rules"],
            [{"from": "", "to": "", "filter": ["*.dll"]}],
        )
        runtime_dir = PROJECT_ROOT / dependency["local_path"]
        for dll in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            self.assertTrue((runtime_dir / dll).is_file(), dll)

    def test_uosc_uses_latest_stable_release(self):
        config = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))

        dependency = config["dependencies"]["uosc"]
        self.assertEqual(dependency["version"], "5.13.0")
        self.assertEqual(
            dependency["url"],
            "https://github.com/tomasklaen/uosc/releases",
        )

    def test_uosc_danmaku_uses_latest_stable_release(self):
        config = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))

        dependency = config["dependencies"]["uosc_danmaku"]
        self.assertEqual(dependency["version"], "v2.1.0")
        self.assertEqual(
            dependency["url"],
            "https://github.com/Tony15246/uosc_danmaku/releases",
        )

    def test_danmaku_history_contains_only_the_visibility_default(self):
        history_path = (
            PROJECT_ROOT
            / "custom_config"
            / "uosc_danmaku"
            / "danmaku-history.json"
        )
        history = json.loads(history_path.read_text(encoding="utf-8"))

        self.assertEqual(history, {"show_danmaku": True})


if __name__ == "__main__":
    unittest.main(verbosity=2)
