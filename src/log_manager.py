"""
日志管理模块
提供统一的日志配置和管理
"""
import logging
import sys
from pathlib import Path
from typing import Optional


class LogManager:
    """日志管理器"""
    
    def __init__(self, log_level: str = "INFO", log_file: Optional[Path] = None):
        """
        初始化日志管理器
        
        Args:
            log_level: 日志级别
            log_file: 日志文件路径
        """
        self.log_level = getattr(logging, log_level.upper())
        self.log_file = log_file
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志配置"""
        # 创建根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # 清除现有的处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # 文件处理器（如果指定了日志文件）
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        获取指定名称的日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            日志器实例
        """
        return logging.getLogger(name)
