import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dependency_layout import LayoutError, load_layout
from src.package_config import load_package_config

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

    def test_install_rules_that_would_silently_misbehave_are_rejected(self):
        good = {"from": "", "to": "portable_config/scripts", "filter": ["x.lua"]}
        bad = [
            {**good, "excludes": ["*.md"]},
            {**good, "from": "../outside"},
            {**good, "from": "/abs"},
            {**good, "filter": []},
            {**good, "filter": "x.lua"},
            {**good, "filter": ["!x.lua"]},
            {**good, "filter": ["scripts/"]},
            {**good, "exclude": ["!keep.md"]},
            {**good, "filter": ["[z-a].lua"]},
        ]
        for rule in bad:
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(LayoutError, "plugin"):
                    self.load({"plugin": {"custom_install_rules": [rule]}})
        for rules in ([], {}, ["scripts"]):
            with self.subTest(rules=rules):
                with self.assertRaisesRegex(LayoutError, "plugin"):
                    self.load({"plugin": {"custom_install_rules": rules}})

    def test_install_to_exclude_files_are_checked_like_rule_excludes(self):
        with self.assertRaisesRegex(LayoutError, "plugin"):
            self.load({"plugin": {"install_to": ".", "exclude_files": ["doc/"]}})

    def test_managed_dir_must_be_in_portable_config(self):
        with self.assertRaisesRegex(LayoutError, "plugin 的 managed_dir 必须在 portable_config/ 下"):
            self.load({"plugin": {"install_to": "portable_config/scripts/a",
                                  "entry": "scripts/a/main.lua", "managed_dir": "scripts/a"}})

    def test_managed_dir_must_hold_the_entry(self):
        bad = [
            {"entry": "portable_config/scripts/a/main.lua", "managed_dir": "portable_config/scripts/b"},
            {"entry": "portable_config/scripts/ab/main.lua", "managed_dir": "portable_config/scripts/a"},
            {"managed_dir": "portable_config/scripts/a"},
        ]
        for extra in bad:
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(LayoutError, "plugin 的 managed_dir .* 必须包含它的 entry"):
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

        self.assertEqual(sorted(f.portable_config_path for f in layout.base_config),
                         ["fntv/defaults.conf", "mpv.conf"])
        self.assertEqual([(src.read_text(encoding="utf-8"), dest)
                          for src, dest, _role in layout.placements["uosc"].custom_config],
                         [("uosc/script-opts/uosc.conf", "script-opts/uosc.conf")])

    def test_two_configs_for_the_same_path_are_rejected(self):
        self.write_custom(["base/script-opts/uosc.conf", "uosc/script-opts/uosc.conf"])

        with self.assertRaisesRegex(LayoutError, "script-opts/uosc.conf"):
            self.load({"uosc": {"install_to": "portable_config/scripts/uosc"}})

    def test_custom_config_files_are_config_and_dependency_files_are_managed(self):
        self.write_custom(["base/mpv.conf", "uosc/script-opts/uosc.conf"])

        layout = self.load({"uosc": {"install_to": "portable_config/scripts/uosc"}})

        self.assertEqual(layout.role_of("mpv.conf"), "config")
        self.assertEqual(layout.role_of("script-opts/uosc.conf"), "config")
        self.assertEqual(layout.role_of("scripts/uosc/main.lua"), "managed")
        self.assertEqual(layout.role_of("fonts/uosc_icons.otf"), "managed")

    def test_custom_config_roles_other_than_config_are_declared_by_pattern(self):
        self.write_custom(["base/mpv.conf", "base/shaders/a.glsl", "base/shaders/b.glsl",
                           "uosc_danmaku/danmaku-history.json"])

        layout = load_layout(
            {"uosc_danmaku": {"install_to": "portable_config/scripts/uosc_danmaku",
                              "config_roles": {"danmaku-history.json": "seed"}}},
            self.custom, base_config_roles={"shaders/**": "managed"})

        self.assertEqual(layout.role_of("mpv.conf"), "config")
        self.assertEqual(layout.role_of("shaders/a.glsl"), "managed")
        self.assertEqual(layout.role_of("shaders/b.glsl"), "managed")
        self.assertEqual(layout.role_of("danmaku-history.json"), "seed")

    def test_declared_roles_must_name_a_role_and_match_a_file(self):
        self.write_custom(["base/mpv.conf", "uosc/script-opts/uosc.conf"])
        uosc = {"install_to": "portable_config/scripts/uosc"}
        bad = [
            ({"uosc": {**uosc, "config_roles": {"script-opts/*.conf": "config"}}}, {}, "uosc"),
            ({"uosc": {**uosc, "config_roles": {"script-opts/*.conf": "user"}}}, {}, "uosc"),
            ({"uosc": {**uosc, "config_roles": {"nothing.conf": "seed"}}}, {}, "nothing.conf"),
            ({"uosc": {**uosc, "config_roles": ["script-opts/*.conf"]}}, {}, "uosc"),
            ({"uosc": uosc}, {"mpv.conf/": "managed"}, "base"),
            ({"uosc": uosc}, {"shaders/**": "managed"}, "shaders"),
        ]
        for dependencies, base_roles, fragment in bad:
            with self.subTest(dependencies=dependencies, base_roles=base_roles):
                with self.assertRaisesRegex(LayoutError, fragment):
                    load_layout(dependencies, self.custom, base_config_roles=base_roles)

    def test_config_inside_a_managed_dir_must_be_declared_managed(self):
        self.write_custom(["uosc/scripts/uosc/user.conf", "base/scripts/uosc/extra.conf"])
        uosc = {"install_to": "portable_config/scripts/uosc", "entry": "portable_config/scripts/uosc/main.lua",
                "managed_dir": "portable_config/scripts/uosc"}

        with self.assertRaisesRegex(LayoutError, "scripts/uosc/user.conf"):
            load_layout({"uosc": uosc}, self.custom, base_config_roles={"extra.conf": "managed"})
        with self.assertRaisesRegex(LayoutError, "scripts/uosc/extra.conf"):
            load_layout({"uosc": {**uosc, "config_roles": {"user.conf": "managed"}}}, self.custom)
        with self.assertRaisesRegex(LayoutError, "scripts/uosc/user.conf"):
            load_layout({"uosc": {**uosc, "config_roles": {"user.conf": "seed"}}}, self.custom,
                        base_config_roles={"extra.conf": "managed"})

        layout = load_layout({"uosc": {**uosc, "config_roles": {"user.conf": "managed"}}}, self.custom,
                             base_config_roles={"extra.conf": "managed"})
        self.assertEqual(layout.role_of("scripts/uosc/user.conf"), "managed")

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
        self.assertEqual(sorted(layout.manifest_managed_dirs),
                         ["scripts/smart_skip", "scripts/uosc", "scripts/uosc_danmaku"])

    def test_repository_config_keeps_the_roles_the_client_already_knows(self):
        layout = load_package_config(PROJECT_ROOT / "package_cfg.json").archive_layout

        self.assertEqual({path: layout.role_of(path) for path in [
            "mpv.conf", "input.conf", "fntv/defaults.conf", "shaders/Anime4K_Clamp_Highlights.glsl",
            "script-opts/uosc.conf", "script-opts/thumbfast.conf", "script-opts/uosc_danmaku.conf",
            "danmaku-history.json", "scripts/uosc/main.lua", "scripts/thumbfast.lua", "fonts/uosc_icons.otf",
        ]}, {
            "mpv.conf": "config",
            "input.conf": "config",
            "fntv/defaults.conf": "managed",
            "shaders/Anime4K_Clamp_Highlights.glsl": "managed",
            "script-opts/uosc.conf": "config",
            "script-opts/thumbfast.conf": "config",
            "script-opts/uosc_danmaku.conf": "config",
            "danmaku-history.json": "seed",
            "scripts/uosc/main.lua": "managed",
            "scripts/thumbfast.lua": "managed",
            "fonts/uosc_icons.otf": "managed",
        })


if __name__ == "__main__":
    unittest.main(verbosity=2)
