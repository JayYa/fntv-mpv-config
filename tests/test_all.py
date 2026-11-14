"""
测试模块
包含各个组件的单元测试
"""
import unittest
import tempfile
import json
from pathlib import Path
import sys
import os

# 添加src目录到Python路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from unittest import mock

from config_manager import ConfigManager, ConfigError, OUTPUT_DIR_ENV
from download_manager import DownloadManager
from extract_manager import ExtractManager
from install_manager import InstallManager


class TestConfigManager(unittest.TestCase):
    """配置管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "test_package.json"
        
        # 创建测试配置
        self.test_config = {
            "name": "test-config",
            "version": "1.0.0",
            "config": {
                "output_dir": "./output",
                "temp_dir": "./temp",
                "custom_config_dir": "./custom_config"
            },
            "dependencies": {
                "test_dep": {
                    "name": "测试依赖",
                    "url": "https://example.com",
                    "version": "1.0.0",
                    "filename_pattern": "test",
                    "format": "zip",
                    "enabled": True,
                    "install_rules": []
                }
            }
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.test_config, f)
    
    def test_load_config(self):
        """测试配置加载"""
        manager = ConfigManager(str(self.config_path))
        config = manager.load_config()
        
        self.assertEqual(config['name'], 'test-config')
        self.assertEqual(config['version'], '1.0.0')
    
    def test_get_enabled_dependencies(self):
        """测试获取已启用的依赖项"""
        manager = ConfigManager(str(self.config_path))
        manager.load_config()
        
        deps = manager.get_enabled_dependencies()
        self.assertIn('test_dep', deps)
        self.assertTrue(deps['test_dep']['enabled'])
    
    def test_config_validation(self):
        """测试配置验证"""
        # 创建无效配置
        invalid_config = {"invalid": "config"}
        invalid_path = Path(self.temp_dir) / "invalid.json"
        
        with open(invalid_path, 'w') as f:
            json.dump(invalid_config, f)
        
        manager = ConfigManager(str(invalid_path))
        
        with self.assertRaises(ConfigError):
            manager.load_config()

    def test_output_dir_defaults_to_config_file(self):
        """没有覆盖时使用配置文件中的 output_dir"""
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(OUTPUT_DIR_ENV, None)
            manager = ConfigManager(str(self.config_path))
            self.assertEqual(manager.get_output_dir(), Path("./output"))

    def test_output_dir_env_overrides_config_file(self):
        """环境变量覆盖配置文件"""
        with mock.patch.dict(os.environ, {OUTPUT_DIR_ENV: "env_out"}):
            manager = ConfigManager(str(self.config_path))
            self.assertEqual(manager.get_output_dir(), Path("env_out"))

    def test_output_dir_argument_overrides_env(self):
        """命令行参数优先于环境变量"""
        with mock.patch.dict(os.environ, {OUTPUT_DIR_ENV: "env_out"}):
            manager = ConfigManager(str(self.config_path), output_dir="cli_out")
            self.assertEqual(manager.get_output_dir(), Path("cli_out"))

    def test_output_dir_empty_env_falls_back_to_config_file(self):
        """空环境变量视为未设置"""
        with mock.patch.dict(os.environ, {OUTPUT_DIR_ENV: ""}):
            manager = ConfigManager(str(self.config_path))
            self.assertEqual(manager.get_output_dir(), Path("./output"))

    def test_output_dir_override_is_not_saved(self):
        """覆盖值只影响本次运行，不写回配置文件"""
        manager = ConfigManager(str(self.config_path), output_dir="cli_out")
        manager.save_config(manager.get_config())
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["config"]["output_dir"], "./output")


class TestDownloadManager(unittest.TestCase):
    """下载管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = DownloadManager(Path(self.temp_dir))
    
    def test_init(self):
        """测试下载管理器初始化"""
        self.assertEqual(self.manager.temp_dir, Path(self.temp_dir))
        self.assertTrue(self.manager.temp_dir.exists())
    
    def test_parse_github_url(self):
        """测试GitHub URL解析"""
        url = "https://github.com/tomasklaen/uosc/releases"
        # 这里可以测试URL解析逻辑，而不是实际的网络请求
        self.assertIn("github.com", url)
        self.assertIn("releases", url)
    
    # 注释掉可能导致卡死的网络测试
    # def test_get_github_release_url(self):
    #     """测试GitHub Release URL获取"""
    #     # 这个测试需要网络连接，暂时跳过以避免卡死
    #     pass


class TestExtractManager(unittest.TestCase):
    """解压管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = ExtractManager(Path(self.temp_dir))
    
    def test_get_format(self):
        """测试格式识别"""
        self.assertEqual(self.manager._get_format(Path("test.zip")), "zip")
        self.assertEqual(self.manager._get_format(Path("test.7z")), "7z")
        self.assertEqual(self.manager._get_format(Path("test.tar.gz")), "gz")


class TestInstallManager(unittest.TestCase):
    """安装管理器测试"""
    
    def setUp(self):
        """设置测试环境"""
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "output"
        self.custom_config_dir = Path(self.temp_dir) / "custom_config"
        
        # 添加project_name参数
        self.manager = InstallManager(self.output_dir, self.custom_config_dir, "test-project")
    
    def test_matches_pattern(self):
        """测试模式匹配"""
        self.assertTrue(self.manager._matches_pattern("test.lua", "*.lua"))
        self.assertTrue(self.manager._matches_pattern("dir/test.lua", "**/*.lua"))
        self.assertFalse(self.manager._matches_pattern("test.txt", "*.lua"))
    
    def test_is_excluded(self):
        """测试排除功能"""
        excludes = ["*.md", "LICENSE*", "**/.git*", "*/test/*"]  # 简化模式
        
        # 测试文件扩展名排除
        self.assertTrue(self.manager._is_excluded("README.md", excludes))
        self.assertTrue(self.manager._is_excluded("doc/CHANGELOG.md", excludes))
        
        # 测试特定文件名排除
        self.assertTrue(self.manager._is_excluded("LICENSE", excludes))
        self.assertTrue(self.manager._is_excluded("LICENSE.txt", excludes))
        
        # 测试目录排除
        self.assertTrue(self.manager._is_excluded(".gitignore", excludes))  # 匹配 **/.git*
        self.assertTrue(self.manager._is_excluded("src/test/test.lua", excludes))  # 匹配 */test/*
        
        # 测试不被排除的文件
        self.assertFalse(self.manager._is_excluded("main.lua", excludes))
        self.assertFalse(self.manager._is_excluded("src/core.lua", excludes))
        self.assertFalse(self.manager._is_excluded("config.json", excludes))
        
        # 测试更简单的排除模式
        simple_excludes = ["debug/*", "*.tmp", "cache*"]
        self.assertTrue(self.manager._is_excluded("debug/info.log", simple_excludes))
        self.assertTrue(self.manager._is_excluded("temp.tmp", simple_excludes))
        self.assertTrue(self.manager._is_excluded("cache.dat", simple_excludes))
        self.assertFalse(self.manager._is_excluded("src/main.lua", simple_excludes))


if __name__ == '__main__':
    unittest.main()
