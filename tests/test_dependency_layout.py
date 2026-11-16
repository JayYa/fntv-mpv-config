"""依赖布局（dependency layout）：每个依赖在安装包里的位置、入口文件和托管目录"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dependency_layout import LayoutError, load_layout

PROJECT_ROOT = Path(__file__).parent.parent


class TestLoadLayout(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.custom = self.tmp / "custom_config"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def load(self, dependencies):
        return load_layout(dependencies, self.custom)

    def test_dependency_needs_exactly_one_of_install_to_and_rules(self):
        rules = [{"from": "", "to": "portable_config/scripts", "filter": ["x.lua"]}]
        for config in ({}, {"install_to": ".", "custom_install_rules": rules}):
            with self.subTest(config=config):
                with self.assertRaisesRegex(LayoutError, "plugin"):
                    self.load({"plugin": config})

    def test_exclude_files_only_go_with_install_to(self):
        rules = [{"from": "", "to": "portable_config/scripts", "filter": ["x.lua"]}]

        with self.assertRaisesRegex(LayoutError, "exclude_files"):
            self.load({"plugin": {"custom_install_rules": rules, "exclude_files": ["*.md"]}})

    def test_managed_dir_must_be_in_portable_config_and_hold_the_entry(self):
        bad = [
            {"entry": "portable_config/scripts/a/main.lua", "managed_dir": "portable_config/scripts/b"},
            {"entry": "portable_config/scripts/ab/main.lua", "managed_dir": "portable_config/scripts/a"},
            {"managed_dir": "portable_config/scripts/a"},
            {"entry": "mpv.exe", "managed_dir": "."},
        ]
        for extra in bad:
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(LayoutError, "plugin"):
                    self.load({"plugin": {"install_to": "portable_config/scripts/a", **extra}})

    def test_paths_stay_inside_the_package_archive(self):
        for extra in ({"install_to": "../x"}, {"install_to": "/abs"},
                      {"install_to": ".", "entry": "a/../../mpv.exe"}):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(LayoutError, "plugin"):
                    self.load({"plugin": extra})

    def write_custom(self, files):
        for rel in files:
            path = self.custom / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rel, encoding="utf-8")

    def test_base_config_and_dependency_configs_land_in_portable_config(self):
        self.write_custom(["base/mpv.conf", "base/fntv/defaults.conf", "uosc/script-opts/uosc.conf"])

        layout = self.load({"uosc": {"install_to": "portable_config/scripts/uosc"}})

        self.assertEqual(sorted(dest for _src, dest in layout.base_config),
                         ["fntv/defaults.conf", "mpv.conf"])
        self.assertEqual([(src.read_text(encoding="utf-8"), dest)
                          for src, dest in layout.placements["uosc"].custom_config],
                         [("uosc/script-opts/uosc.conf", "script-opts/uosc.conf")])

    def test_two_configs_for_the_same_path_are_rejected(self):
        self.write_custom(["base/script-opts/uosc.conf", "uosc/script-opts/uosc.conf"])

        with self.assertRaisesRegex(LayoutError, "script-opts/uosc.conf"):
            self.load({"uosc": {"install_to": "portable_config/scripts/uosc"}})

    def test_no_dependency_may_be_named_after_the_base_config(self):
        with self.assertRaisesRegex(LayoutError, "base"):
            self.load({"base": {"install_to": "portable_config/scripts/base"}})

    def test_repository_config_requires_every_client_entry(self):
        dependencies = json.loads((PROJECT_ROOT / "package_cfg.json").read_text(encoding="utf-8"))["dependencies"]

        layout = load_layout(dependencies, PROJECT_ROOT / "custom_config")

        self.assertEqual(sorted(layout.required_paths), [
            "mpv.exe",
            "portable_config/fntv/defaults.conf",
            "portable_config/mpv.conf",
            "portable_config/scripts/smart_skip/main.lua",
            "portable_config/scripts/thumbfast.lua",
            "portable_config/scripts/uosc/main.lua",
            "portable_config/scripts/uosc_danmaku/main.lua",
        ])
        self.assertEqual(sorted(layout.managed_dirs),
                         ["scripts/smart_skip", "scripts/uosc", "scripts/uosc_danmaku"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
