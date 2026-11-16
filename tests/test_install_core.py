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
from src.install_manager import InstallManager


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
        empty_content = Path(self.temp_dir) / "content"
        empty_content.mkdir()
        self.install_manager.install_dependency(self.layout.placements["uosc_danmaku"], empty_content)

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
