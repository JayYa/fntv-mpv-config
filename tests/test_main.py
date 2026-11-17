import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.main import create_cli_parser, main, parse_args


class TestParseArgs(unittest.TestCase):
    def parse(self, argv):
        return parse_args(create_cli_parser(), argv)

    def assert_exits(self, argv):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                self.parse(argv)

    def test_package_timestamp_is_checked_while_parsing(self):
        self.assertEqual(self.parse(["--package-timestamp", "20261110_224319"]).package_timestamp,
                         "20261110_224319")
        self.assertIsNone(self.parse([]).package_timestamp)
        self.assert_exits(["--package-timestamp", "2026-11-10"])

    def test_result_file_needs_a_package(self):
        self.assertEqual(self.parse(["--result-file", "r.json"]).result_file, "r.json")
        self.assertIsNone(self.parse([]).result_file)
        for skip in ["--skip-package", "--skip-install"]:
            with self.subTest(skip=skip):
                self.assert_exits(["--result-file", "r.json", skip])

    def test_previous_manifest_comes_from_a_release_or_a_file_but_not_both(self):
        self.assertEqual(self.parse(["--previous-release", "JayYa/fntv-mpv-config"]).previous_release,
                         "JayYa/fntv-mpv-config")
        self.assertEqual(self.parse(["--previous-manifest", "m.json"]).previous_manifest, "m.json")
        self.assert_exits(["--previous-release", "JayYa/fntv-mpv-config",
                           "--previous-manifest", "m.json"])

    def test_deps_subset_cannot_be_packaged(self):
        self.assert_exits(["--deps", "uosc"])
        for skip in ["--skip-package", "--skip-install"]:
            with self.subTest(skip=skip):
                self.assertEqual(self.parse(["--deps", "uosc", skip]).deps, ["uosc"])


class TestCommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "plugin").mkdir()
        self.config_path = self.tmp / "package_cfg.json"
        self.write_config({
            "uosc": {"name": "uosc插件", "version": "5.13.0",
                     "url": "https://github.com/tomasklaen/uosc/releases",
                     "filename_pattern": "uosc", "format": "zip",
                     "install_to": "portable_config/scripts/uosc"},
            "plugin": {"name": "本地插件", "version": "local", "local_path": "plugin",
                       "install_to": "portable_config/scripts/plugin"},
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, dependencies):
        self.config_path.write_text(json.dumps({
            "name": "fntv-mpv",
            "config": {"output_dir": "out", "temp_dir": "temp", "custom_config_dir": "custom_config"},
            "dependencies": dependencies,
        }), encoding="utf-8")

    def run_main(self, *args):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            try:
                main(["--config", str(self.config_path), *args])
                code = 0
            except SystemExit as e:
                code = e.code
        return code, out.getvalue()

    def test_list_shows_every_dependency_and_where_it_comes_from(self):
        code, out = self.run_main("--list")

        self.assertEqual(code, 0)
        self.assertIn("uosc: uosc插件 5.13.0", out)
        self.assertIn("tomasklaen/uosc", out)
        self.assertIn("plugin: 本地插件 local", out)
        self.assertIn("本地文件夹", out)

    def test_list_marks_disabled_dependencies(self):
        self.write_config({
            "plugin": {"name": "本地插件", "version": "local", "local_path": "plugin",
                       "install_to": "portable_config/scripts/plugin", "enabled": False},
        })

        code, out = self.run_main("--list")

        self.assertEqual(code, 0)
        self.assertIn("plugin: 本地插件 local", out)
        self.assertIn("已停用", out)

    def test_list_fails_on_a_bad_config(self):
        self.write_config({"uosc": {"enabled": "yes"}})

        code, out = self.run_main("--list")

        self.assertEqual(code, 1)
        self.assertIn("enabled", out)

    def test_naming_a_disabled_dependency_fails(self):
        self.write_config({
            "plugin": {"name": "本地插件", "version": "local", "local_path": "plugin",
                       "install_to": "portable_config/scripts/plugin", "enabled": False},
        })

        code, out = self.run_main("--deps", "plugin", "nope", "--skip-package", "--skip-download")

        self.assertEqual(code, 1)
        self.assertIn("没有这些依赖项: nope", out)
        self.assertIn("这些依赖项已停用: plugin", out)

    def test_clean_fails_on_a_bad_config(self):
        self.config_path.write_text("{", encoding="utf-8")

        code, _ = self.run_main("--clean", "temp")

        self.assertEqual(code, 1)

    def test_unknown_dependency_name_fails(self):
        code, out = self.run_main("--deps", "nope", "--skip-package", "--skip-download")

        self.assertEqual(code, 1)
        self.assertIn("nope", out)

    def test_enable_and_disable_are_gone(self):
        with mock.patch("sys.stderr", io.StringIO()):
            for flag in ("--enable", "--disable"):
                with self.subTest(flag=flag):
                    code, _ = self.run_main(flag, "uosc")
                    self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
