"""
MPV播放器和插件管理工具

这个包提供了一个完整的MPV配置管理解决方案，包括：
- 自动下载MPV播放器和插件
- 智能解压和安装
- 自定义配置管理
- 打包输出功能
"""

__version__ = "1.0.0"
__author__ = "MPV Config Manager"

from .build import BuildFailed, BuildScope, build
from .main import main

__all__ = ['BuildFailed', 'BuildScope', 'build', 'main']
