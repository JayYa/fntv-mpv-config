"""
安装管理器功能测试
测试自定义安装规则和默认安装功能
"""
import unittest
import tempfile
import shutil
from pathlib import Path
import sys
import io
import zipfile
from datetime import datetime
from unittest import mock

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from install_manager import InstallManager, InstallError


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
            custom_config_dir=self.test_dir / "custom_config",
            project_name="test-config"
        )
    
    def tearDown(self):
        """清理测试环境"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_default_installation(self):
        """测试默认安装功能"""
        dep_name = "test_plugin"
        excludes = ["*.md"]  # 排除markdown文件
        
        # 执行默认安装
        self.install_manager._install_extracted_files_default(
            dep_name, self.source_dir, excludes
        )
        
        # 验证文件已安装到正确位置（插件安装到portable_config/scripts/下）
        target_dir = self.install_manager.output_dir / "portable_config" / "scripts" / dep_name
        
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
    
    def test_custom_install_rule_basic(self):
        """测试基本自定义安装规则"""
        rule = {
            "from": "scripts",
            "to": "portable_config/scripts/test_plugin",
            "filter": ["**/*.lua"]  # 只复制lua文件
        }
        
        dep_name = "test_plugin"
        
        # 执行自定义安装
        self.install_manager._apply_custom_config_rule(
            dep_name, rule, self.source_dir
        )
        
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
        rule = {
            "from": ".",
            "to": "portable_config/scripts/test_plugin",
            "filter": ["**/*.lua", "**/*.json"]  # 复制lua和json文件
        }
        
        dep_name = "test_plugin"
        
        # 执行自定义安装
        self.install_manager._apply_custom_config_rule(
            dep_name, rule, self.source_dir
        )
        
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


class TestCreatePackageName(unittest.TestCase):
    """安装包资产名的时间戳"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.install_manager = InstallManager(
            output_dir=Path(self.temp_dir) / "output",
            custom_config_dir=Path(self.temp_dir) / "custom_config",
            project_name="test-config",
        )
        (self.install_manager.output_dir / "mpv.exe").write_text("stub")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_given_timestamp_names_package(self):
        package = self.install_manager.create_package("20261110_224319")

        self.assertEqual(package.name, "mpv-package-20261110_224319.zip")
        self.assertEqual(package.parent, self.install_manager.base_output_dir)
        with zipfile.ZipFile(package) as zf:
            self.assertEqual(zf.namelist(), ["mpv.exe"])

    def test_default_timestamp_uses_local_time(self):
        fixed = datetime(2026, 11, 14, 9, 8, 7)
        with mock.patch("install_manager.datetime") as fake_datetime:
            fake_datetime.now.return_value = fixed
            package = self.install_manager.create_package()

        self.assertEqual(package.name, "mpv-package-20261114_090807.zip")

    def test_malformed_timestamp_rejected(self):
        for bad in ["2026-11-10", "20261110_2243", "20261110_224319\n", "../x"]:
            with self.subTest(bad=bad):
                with self.assertRaises(InstallError):
                    self.install_manager.create_package(bad)
        self.assertEqual(list(self.install_manager.base_output_dir.glob("*.zip")), [])


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
    """用仓库里真实的 custom_config 安装，确认弹幕配置走按依赖目录复制的路径"""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.custom_config_dir = Path(__file__).parent.parent / "custom_config"
        self.install_manager = InstallManager(
            output_dir=Path(self.temp_dir) / "output",
            custom_config_dir=self.custom_config_dir,
            project_name="test-config",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_uosc_danmaku_config_installed_from_dependency_dir(self):
        self.install_manager.install_dependency("uosc_danmaku", {}, None)

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
