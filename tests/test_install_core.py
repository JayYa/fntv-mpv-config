"""
安装管理器功能测试
测试自定义安装规则和默认安装功能
"""
import json
import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import io
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.dependency_layout import load_layout
from src.install_manager import InstallError, InstallManager


class TestInstallManagerCore(unittest.TestCase):
    """安装管理器核心功能测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_dir = Path(self.temp_dir)
        
        # 创建源文件结构
        self.source_dir = self.test_dir / "source"
        self.source_dir.mkdir()
        (self.source_dir / "main.lua").write_text("-- Main script")
        (self.source_dir / "config.json").write_text('{"key": "value"}')
        (self.source_dir / "README.md").write_text("# Documentation")
        
        # 创建子目录
        scripts_dir = self.source_dir / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "helper.lua").write_text("-- Helper script")
        (scripts_dir / "data.txt").write_text("test data")
        
        # 创建安装管理器
        self.install_manager = InstallManager(
            output_dir=self.test_dir / "output",
            project_name="test-config"
        )
    
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_project_name_must_be_one_directory_level(self):
        for bad in ["", ".", "..", "a/b", "../x"]:
            with self.subTest(name=bad):
                with self.assertRaises(ValueError):
                    InstallManager(self.test_dir / "output", bad)

    def test_reset_project_dir_keeps_the_rest_of_the_output_dir(self):
        output = self.test_dir / "output"
        (output / "test-config" / "stale").mkdir(parents=True)
        (output / "other.txt").write_text("keep")

        self.install_manager.reset_project_dir()

        self.assertFalse((output / "test-config" / "stale").exists())
        self.assertTrue(self.install_manager.portable_config_dir.is_dir())
        self.assertEqual((output / "other.txt").read_text(), "keep")

    def install(self, config):
        layout = load_layout({"test_plugin": config}, self.test_dir / "custom_config")
        self.install_manager.install_dependency(layout.placements["test_plugin"], self.source_dir)

    def test_install_to_copies_the_content_dir_with_excludes(self):
        self.install({"install_to": "portable_config/scripts/test_plugin", "exclude_files": ["*.md"]})

        target_dir = self.install_manager.output_dir / "portable_config" / "scripts" / "test_plugin"
        
        # 验证包含的文件
        self.assertTrue((target_dir / "main.lua").exists())
        self.assertTrue((target_dir / "config.json").exists())
        self.assertTrue((target_dir / "scripts" / "helper.lua").exists())
        self.assertTrue((target_dir / "scripts" / "data.txt").exists())
        
        # 验证排除的文件
        self.assertFalse((target_dir / "README.md").exists())
        
        # 验证文件内容
        content = (target_dir / "main.lua").read_text()
        self.assertEqual(content, "-- Main script")

    def test_install_to_dot_puts_the_content_at_the_archive_root(self):
        self.install({"install_to": ".", "exclude_files": ["*.md"]})

        root = self.install_manager.output_dir
        self.assertEqual((root / "main.lua").read_text(), "-- Main script")
        self.assertTrue((root / "scripts" / "helper.lua").exists())
        self.assertFalse((root / "README.md").exists())
        self.assertFalse((root / "portable_config" / "scripts").exists())

    def test_custom_install_rule_basic(self):
        """测试基本自定义安装规则"""
        self.install({"custom_install_rules": [{
            "from": "scripts",
            "to": "portable_config/scripts/test_plugin",
            "filter": ["**/*.lua"]  # 只复制lua文件
        }]})

        # 验证文件安装到正确位置
        target_path = self.install_manager.output_dir / "portable_config" / "scripts" / "test_plugin"
        
        # 验证lua文件已复制
        self.assertTrue((target_path / "helper.lua").exists())
        
        # 验证非lua文件被过滤
        self.assertFalse((target_path / "data.txt").exists())
        
        # 验证文件内容
        content = (target_path / "helper.lua").read_text()
        self.assertEqual(content, "-- Helper script")
    
    def test_custom_install_rule_root_copy(self):
        """测试根目录复制规则"""
        self.install({"custom_install_rules": [{
            "from": ".",
            "to": "portable_config/scripts/test_plugin",
            "filter": ["**/*.lua", "**/*.json"]  # 复制lua和json文件
        }]})

        # 验证文件安装到正确位置
        target_path = self.install_manager.output_dir / "portable_config" / "scripts" / "test_plugin"
        
        # 验证根目录文件
        self.assertTrue((target_path / "main.lua").exists())
        self.assertTrue((target_path / "config.json").exists())
        
        # 验证子目录文件
        self.assertTrue((target_path / "scripts" / "helper.lua").exists())
        
        # 验证过滤生效
        self.assertFalse((target_path / "README.md").exists())
        self.assertFalse((target_path / "scripts" / "data.txt").exists())

    def write_source(self, files):
        for rel in files:
            path = self.source_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rel)

    def installed(self, target):
        root = self.install_manager.output_dir / target
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())

    def test_patterns_without_a_slash_match_file_names_at_any_depth(self):
        self.write_source(["docs/CHANGELOG.md", "docs/LICENSE.txt", "docs/guide.txt"])

        self.install({"install_to": "out", "exclude_files": ["*.md", "LICENSE*"]})

        self.assertEqual(self.installed("out"), [
            "config.json", "docs/guide.txt", "main.lua", "scripts/data.txt", "scripts/helper.lua",
        ])

    def test_patterns_with_a_slash_are_anchored_at_the_rule_source(self):
        self.write_source(["scripts/deep/x.lua", "vendor/scripts/y.lua"])

        self.install({"custom_install_rules": [
            {"from": ".", "to": "one", "filter": ["scripts/*"]},
            {"from": ".", "to": "any", "filter": ["scripts/**/*.lua"]},
        ]})

        self.assertEqual(self.installed("one"), ["scripts/data.txt", "scripts/helper.lua"])
        self.assertEqual(self.installed("any"), ["scripts/deep/x.lua", "scripts/helper.lua"])

    def test_question_marks_classes_and_leading_double_stars(self):
        self.write_source(["a1.lua", "a2.lua", "ab.lua", "[x].lua", "vendor/deep/z.json"])

        self.install({"custom_install_rules": [
            {"from": ".", "to": "digits", "filter": ["a[0-9].lua"]},
            {"from": ".", "to": "not_digit", "filter": ["a[!0-9].lua"]},
            {"from": ".", "to": "one_char", "filter": ["a?.lua"], "exclude": ["a1.*"]},
            {"from": ".", "to": "literal", "filter": ["[[]x].lua"]},
            {"from": ".", "to": "json", "filter": ["**/deep/*.json", "**\\config.json"]},
        ]})

        self.assertEqual(self.installed("digits"), ["a1.lua", "a2.lua"])
        self.assertEqual(self.installed("not_digit"), ["ab.lua"])
        self.assertEqual(self.installed("one_char"), ["a2.lua", "ab.lua"])
        self.assertEqual(self.installed("literal"), ["[x].lua"])
        self.assertEqual(self.installed("json"), ["config.json", "vendor/deep/z.json"])

    def test_a_rule_whose_source_is_missing_fails_the_install(self):
        with self.assertRaisesRegex(InstallError, "test_plugin.*fonts"):
            self.install({"custom_install_rules": [{"from": "fonts", "to": "portable_config/fonts"}]})

    def test_a_filter_that_installs_nothing_fails_the_install(self):
        for rule in ({"from": ".", "to": "x", "filter": ["*.lua", "*.dll"]},
                     {"from": ".", "to": "x", "filter": ["*.md"], "exclude": ["README*"]}):
            with self.subTest(rule=rule):
                with self.assertRaisesRegex(InstallError, "test_plugin"):
                    self.install({"custom_install_rules": [rule]})

    def test_two_dependencies_installing_the_same_file_fail_the_install(self):
        layout = load_layout({
            "a": {"install_to": "portable_config/scripts"},
            "b": {"custom_install_rules": [{"from": "scripts", "to": "portable_config/scripts",
                                            "filter": ["helper.lua"]}]},
        }, self.test_dir / "custom_config")
        self.install_manager.install_dependency(layout.placements["a"], self.source_dir / "scripts")

        with self.assertRaisesRegex(InstallError, "portable_config/scripts/helper.lua"):
            self.install_manager.install_dependency(layout.placements["b"], self.source_dir)

    def test_paths_that_differ_only_in_case_are_the_same_file(self):
        with self.assertRaisesRegex(InstallError, "test_plugin 的两条安装规则"):
            self.install({"custom_install_rules": [
                {"from": "scripts", "to": "Out", "filter": ["helper.lua"]},
                {"from": "scripts", "to": "out", "filter": ["helper.lua"]},
            ]})

    def test_custom_config_may_replace_a_file_the_dependency_ships(self):
        custom = self.test_dir / "custom_config" / "test_plugin" / "scripts" / "test_plugin" / "main.lua"
        custom.parent.mkdir(parents=True)
        custom.write_text("-- customised")

        self.install({"install_to": "portable_config/scripts/test_plugin"})

        installed = self.install_manager.portable_config_dir / "scripts" / "test_plugin" / "main.lua"
        self.assertEqual(installed.read_text(), "-- customised")


class TestPackageTimestampCli(unittest.TestCase):
    """--package-timestamp 在解析参数时就校验"""

    def test_valid_timestamp_parsed(self):
        from src.main import create_cli_parser
        args = create_cli_parser().parse_args(["--package-timestamp", "20261110_224319"])
        self.assertEqual(args.package_timestamp, "20261110_224319")

    def test_timestamp_defaults_to_none(self):
        from src.main import create_cli_parser
        self.assertIsNone(create_cli_parser().parse_args([]).package_timestamp)

    def test_malformed_timestamp_exits(self):
        from src.main import create_cli_parser
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                create_cli_parser().parse_args(["--package-timestamp", "2026-11-10"])


class TestRepositoryCustomConfig(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        repo = Path(__file__).parent.parent
        self.custom_config_dir = repo / "custom_config"
        dependencies = json.loads((repo / "package_cfg.json").read_text(encoding="utf-8"))["dependencies"]
        self.layout = load_layout(dependencies, self.custom_config_dir)
        self.install_manager = InstallManager(
            output_dir=Path(self.temp_dir) / "output",
            project_name="test-config",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_base_config_installed_without_any_dependency(self):
        self.install_manager.install_base_config(self.layout)

        portable = self.install_manager.portable_config_dir
        for rel in ("mpv.conf", "input.conf", "fntv/defaults.conf"):
            self.assertEqual((portable / rel).read_bytes(),
                             (self.custom_config_dir / "base" / rel).read_bytes())

    def test_uosc_danmaku_config_installed_from_dependency_dir(self):
        content = Path(self.temp_dir) / "content"
        content.mkdir()
        (content / "main.lua").write_text("-- danmaku")
        self.install_manager.install_dependency(self.layout.placements["uosc_danmaku"], content)

        portable = self.install_manager.portable_config_dir
        self.assertEqual(
            (portable / "script-opts" / "uosc_danmaku.conf").read_bytes(),
            (self.custom_config_dir / "uosc_danmaku" / "script-opts" / "uosc_danmaku.conf").read_bytes(),
        )
        self.assertEqual(
            (portable / "danmaku-history.json").read_bytes(),
            (self.custom_config_dir / "uosc_danmaku" / "danmaku-history.json").read_bytes(),
        )

    def test_custom_config_root_holds_only_dependency_dirs(self):
        """custom_config 根目录下的散文件不会被安装，出现即视为放错位置"""
        stray_files = [p.name for p in self.custom_config_dir.iterdir() if p.is_file()]
        self.assertEqual(stray_files, [])


if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
