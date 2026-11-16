import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.main import main


class TestCommandLine(unittest.TestCase):
    """管理命令经 main(argv) 测：输出和退出码"""

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
        """返回 (退出码, 输出)；正常结束时退出码为 0"""
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

    def test_list_fails_on_a_bad_config(self):
        self.write_config({"uosc": {"enabled": True}})

        code, out = self.run_main("--list")

        self.assertEqual(code, 1)
        self.assertIn("ADR-0001", out)

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
