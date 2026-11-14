"""
配置管理模块
负责读取和验证 package_cfg.json 配置文件
"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

# 覆盖 package_cfg.json 中 config.output_dir 的环境变量
OUTPUT_DIR_ENV = "FNTV_MPV_OUTPUT_DIR"


class ConfigError(Exception):
    """配置错误异常"""
    pass


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = "package_cfg.json", output_dir: Optional[str] = None):
        """
        初始化配置管理器

        Args:
            config_path: 配置文件路径
            output_dir: 输出目录覆盖值（命令行 --output-dir），优先于环境变量和配置文件
        """
        self.config_path = Path(config_path)
        self.output_dir_override = output_dir
        self._config = None
        
    def load_config(self) -> Dict[str, Any]:
        """
        加载配置文件
        
        Returns:
            配置字典
            
        Raises:
            ConfigError: 配置文件不存在或格式错误
        """
        if not self.config_path.exists():
            raise ConfigError(f"配置文件不存在: {self.config_path}")
            
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self._config = json.load(f)
            self._validate_config()
            return self._config
        except json.JSONDecodeError as e:
            raise ConfigError(f"配置文件格式错误: {e}")
    
    def _validate_config(self):
        """验证配置文件格式"""
        if not isinstance(self._config, dict):
            raise ConfigError("配置文件必须是JSON对象")
            
        required_keys = ['name', 'version', 'config', 'dependencies']
        for key in required_keys:
            if key not in self._config:
                raise ConfigError(f"缺少必需的配置项: {key}")
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        if self._config is None:
            self.load_config()
        if self._config is None:
            raise ConfigError("配置未加载")
        return self._config
    
    def get_output_dir(self) -> Path:
        """
        获取输出目录

        优先级：命令行 --output-dir > 环境变量 FNTV_MPV_OUTPUT_DIR > package_cfg.json 的 config.output_dir
        """
        if self.output_dir_override:
            return Path(self.output_dir_override)
        env_output_dir = os.environ.get(OUTPUT_DIR_ENV)
        if env_output_dir:
            return Path(env_output_dir)
        return Path(self.get_config()['config']['output_dir'])
    
    def get_temp_dir(self) -> Path:
        """获取临时目录"""
        return Path(self.get_config()['config']['temp_dir'])
    
    def get_custom_config_dir(self) -> Path:
        """获取自定义配置目录"""
        return Path(self.get_config()['config']['custom_config_dir'])
    
    def get_project_name(self) -> str:
        """获取项目名称"""
        return self.get_config()['name']
    
    def get_github_proxy(self) -> str:
        """获取GitHub代理地址"""
        config = self.get_config()['config']
        return config.get('github_proxy', '')
    
    def is_proxy_enabled(self) -> bool:
        """检查是否启用代理"""
        config = self.get_config()['config']
        return config.get('enable_proxy', False)
    
    def get_enabled_dependencies(self) -> Dict[str, Dict[str, Any]]:
        """获取已启用的依赖项"""
        dependencies = self.get_config()['dependencies']
        return {name: dep for name, dep in dependencies.items() if dep.get('enabled', True)}
    
    def get_dependency(self, name: str) -> Dict[str, Any]:
        """
        获取指定依赖项配置
        
        Args:
            name: 依赖项名称
            
        Returns:
            依赖项配置
            
        Raises:
            ConfigError: 依赖项不存在
        """
        dependencies = self.get_config()['dependencies']
        if name not in dependencies:
            raise ConfigError(f"依赖项不存在: {name}")
        return dependencies[name]
    
    def save_config(self, config: Dict[str, Any]):
        """
        保存配置到文件
        
        Args:
            config: 配置字典
        """
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self._config = config
        except Exception as e:
            raise ConfigError(f"保存配置文件失败: {e}")
