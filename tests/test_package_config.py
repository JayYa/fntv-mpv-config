import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.package_config import (OUTPUT_DIR_ENV, ConfigError, GithubRelease, LocalArchive,
                                LocalDir, load_package_config)

PROJECT_ROOT = Path(__file__).parent.parent

UOSC = {
    "name": "uosc插件", "version": "5.13.0",
    "url": "https://github.com/tomasklaen/uosc/releases",
    "filename_pattern": "uosc", "format": "zip",
    "install_to": "portable_config/scripts/uosc",
}


def without_install(dep):
    return {k: v for k, v in dep.items() if k != "install_to"}


class TestLoadPackageConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config_path = self.tmp / "package_cfg.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, dependencies=None, config=None, **top):
        data = {
            "name": "fntv-mpv",
            "config": config if config is not None else {
                "output_dir": "out", "temp_dir": "temp", "custom_config_dir": "custom_config",
            },
            "dependencies": dependencies if dependencies is not None else {"uosc": UOSC},
            **top,
        }
        self.config_path.write_text(json.dumps(data), encoding="utf-8")
        return self.config_path

    def load(self, **kwargs):
        return load_package_config(self.write(**kwargs))

    def assertRejected(self, pattern, **kwargs):
        with self.assertRaisesRegex(ConfigError, pattern):
            self.load(**kwargs)

    def test_github_release_dependency(self):
        config = self.load()

        uosc = config.dependencies["uosc"]
        self.assertEqual((uosc.display_name, uosc.version), ("uosc插件", "5.13.0"))
        self.assertEqual(uosc.source, GithubRelease(
            owner="tomasklaen", repo="uosc", version="5.13.0", filename_pattern="uosc", format="zip"))
        self.assertIn("uosc", config.archive_layout.placements)

    def test_local_folder_and_archive_resolve_against_the_config_dir(self):
        (self.tmp / "pkgs" / "plugin").mkdir(parents=True)
        (self.tmp / "pkgs" / "plugin.zip").write_bytes(b"")
        local = {"name": "插件", "version": "local", "install_to": "portable_config/scripts/x"}

        config = self.load(dependencies={
            "folder": {**local, "local_path": "./pkgs/plugin"},
            "archive": {**local, "local_path": "pkgs/plugin.zip"},
        })

        self.assertEqual(config.dependencies["folder"].source, LocalDir(self.tmp.resolve() / "pkgs" / "plugin"))
        self.assertEqual(config.dependencies["archive"].source,
                         LocalArchive(self.tmp.resolve() / "pkgs" / "plugin.zip"))

    def test_dependencies_are_enabled_unless_they_say_otherwise(self):
        mpv = {"name": "mpv", "version": "20261108", "url": "https://github.com/a/mpv/releases",
               "filename_pattern": "mpv", "format": "7z", "install_to": ".", "entry": "mpv.exe"}

        config = self.load(dependencies={"uosc": UOSC, "mpv": {**mpv, "enabled": False}})

        self.assertTrue(config.dependencies["uosc"].enabled)
        self.assertFalse(config.dependencies["mpv"].enabled)
        self.assertEqual(list(config.enabled_dependencies), ["uosc"])
        self.assertEqual(list(config.disabled_dependencies), ["mpv"])
        self.assertEqual(list(config.archive_layout.placements), ["uosc"])
        self.assertNotIn("mpv.exe", config.archive_layout.required_paths)

    def test_disabled_dependencies_are_still_checked(self):
        disabled = {**UOSC, "enabled": False}
        cases = {
            "enabled 必须是 true 或 false": {**UOSC, "enabled": "no"},
            "local_path 不存在": {"name": "x", "version": "local", "enabled": False,
                                  "local_path": "missing", "install_to": "."},
            "install_to": without_install(disabled),
            "sha256": {**disabled, "sha256": "x"},
        }
        for pattern, dep in cases.items():
            with self.subTest(pattern=pattern):
                self.assertRejected(pattern, dependencies={"dep": dep})

    def test_unsupported_archive_formats_are_rejected(self):
        (self.tmp / "plugin.lua").write_text("--")
        cases = {
            "format 只能是": {**UOSC, "format": "gz"},
            "不是支持的压缩包": {"name": "x", "version": "local", "local_path": "plugin.lua",
                          "install_to": "."},
        }
        for pattern, dep in cases.items():
            with self.subTest(pattern=pattern):
                self.assertRejected(pattern, dependencies={"dep": dep})

    def test_bad_dependency_entries_are_rejected(self):
        (self.tmp / "plugin").mkdir()
        local = {"name": "x", "version": "local", "local_path": "plugin", "install_to": "."}
        without = lambda d, key: {k: v for k, v in d.items() if k != key}
        cases = {
            "custom_install_rule": {**UOSC, "custom_install_rule": []},
            "只能写 url 和 local_path 其中之一": {**UOSC, "local_path": "plugin"},
            "url 或 local_path": without(UOSC, "url"),
            "GitHub Release": {**UOSC, "url": "./local_packages/uosc"},
            "filename_pattern": without(UOSC, "filename_pattern"),
            "format": without(UOSC, "format"),
            "本地.*不用 format": {**local, "format": "zip"},
            "sha256": {**local, "sha256": "x"},
            "name": without(UOSC, "name"),
            "version": {**UOSC, "version": ""},
        }
        for pattern, dep in cases.items():
            with self.subTest(pattern=pattern):
                self.assertRejected(pattern, dependencies={"dep": dep})

    def test_layout_errors_are_config_errors(self):
        self.assertRejected("install_to", dependencies={"uosc": without_install(UOSC)})

    def test_bad_top_level_and_settings_are_rejected(self):
        settings = {"output_dir": "out", "temp_dir": "temp", "custom_config_dir": "custom_config"}
        cases = {
            "temp_dir": dict(config={k: v for k, v in settings.items() if k != "temp_dir"}),
            "output_dir": dict(config={k: v for k, v in settings.items() if k != "output_dir"}),
            "custom_config_dir": dict(config={k: v for k, v in settings.items()
                                              if k != "custom_config_dir"}),
            "github_proxy": dict(config={**settings, "github_proxy": 1}),
            "的 config": dict(config=[]),
            "的 name": dict(name=""),
            "proxy": dict(config={**settings, "proxy": "x"}),
            "enable_proxy": dict(config={**settings, "enable_proxy": "yes"}),
            "homepage": dict(homepage="x"),
            "dependencies": dict(dependencies=[]),
        }
        for pattern, kwargs in cases.items():
            with self.subTest(pattern=pattern):
                self.assertRejected(pattern, **kwargs)

    def test_unreadable_files_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, "不存在"):
            load_package_config(self.tmp / "missing.json")
        self.config_path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "JSON"):
            load_package_config(self.config_path)
        self.config_path.write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "对象"):
            load_package_config(self.config_path)

    def test_settings_resolve_against_the_config_dir(self):
        config = self.load(config={"output_dir": "../out", "temp_dir": "./temp",
                                   "custom_config_dir": "custom_config",
                                   "github_proxy": "https://ghfast.top", "enable_proxy": True})

        self.assertEqual(config.project_name, "fntv-mpv")
        self.assertEqual(config.temp_dir, self.tmp.resolve() / "temp")
        self.assertEqual(config.output_dir, self.tmp.resolve() / ".." / "out")
        self.assertEqual((config.github_proxy, config.enable_proxy), ("https://ghfast.top", True))

    def test_proxy_settings_may_be_empty_or_omitted(self):
        settings = {"output_dir": "out", "temp_dir": "temp", "custom_config_dir": "custom_config"}

        self.assertEqual(self.load(config={**settings, "github_proxy": ""}).github_proxy, "")
        omitted = self.load(config=settings)
        self.assertEqual((omitted.github_proxy, omitted.enable_proxy), ("", False))

    def test_output_dir_precedence(self):
        path = self.write()
        with mock.patch.dict(os.environ, {OUTPUT_DIR_ENV: ""}):
            self.assertEqual(load_package_config(path).output_dir, self.tmp.resolve() / "out")
        with mock.patch.dict(os.environ, {OUTPUT_DIR_ENV: "env_out"}):
            self.assertEqual(load_package_config(path).output_dir, Path("env_out"))
            self.assertEqual(load_package_config(path, output_dir="cli_out").output_dir, Path("cli_out"))

    def test_repository_config_loads(self):
        config = load_package_config(PROJECT_ROOT / "package_cfg.json")

        self.assertEqual(list(config.dependencies),
                         ["mpv", "uosc", "uosc_danmaku", "smart_skip", "thumbfast"])
        self.assertEqual(config.dependencies["smart_skip"].source,
                         LocalDir(PROJECT_ROOT.resolve() / "local_packages" / "smart_skip"))

    def test_missing_local_path_is_rejected(self):
        self.assertRejected("nowhere", dependencies={"x": {
            "name": "x", "version": "local", "local_path": "nowhere", "install_to": "."}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
