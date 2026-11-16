#!/usr/bin/env python3
"""
MPV配置管理工具运行脚本
提供简单的命令行接口
"""

import sys
from pathlib import Path

# 添加src目录到Python路径
current_dir = Path(__file__).parent
src_dir = current_dir / 'src'
sys.path.insert(0, str(src_dir))

from src.main import main

if __name__ == '__main__':
    main()
