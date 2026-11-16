"""
解压管理模块
负责处理不同格式的压缩文件解压
"""
import os
import zipfile
import py7zr
from typing import Union
from pathlib import Path
import logging


class ExtractError(Exception):
    """解压错误异常"""
    pass


class ExtractManager:
    """解压管理器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 支持的格式和对应的处理函数
        self.extractors = {
            'zip': self._extract_zip,
            '7z': self._extract_7z,
            'rar': self._extract_rar,
            'tar': self._extract_tar,
            'gz': self._extract_tar,
            'bz2': self._extract_tar,
            'xz': self._extract_tar
        }
    
    def extract_archive(self, archive_path: Path, extract_to: Path) -> Path:
        """
        解压压缩文件

        Args:
            archive_path: 压缩文件路径
            extract_to: 解压目标目录

        Returns:
            解压后的目录路径

        Raises:
            ExtractError: 解压失败
        """
        if not archive_path.exists():
            raise ExtractError(f"压缩文件不存在: {archive_path}")

        extract_to = Path(extract_to)
        extract_to.mkdir(parents=True, exist_ok=True)
        
        # 获取文件格式
        file_format = self._get_format(archive_path)
        
        self.logger.info(f"开始解压 {archive_path} 到 {extract_to}")
        
        try:
            if file_format in self.extractors:
                self.extractors[file_format](archive_path, extract_to)
            else:
                raise ExtractError(f"不支持的压缩格式: {file_format}")
            
            self.logger.info(f"解压完成: {extract_to}")
            return extract_to
            
        except Exception as e:
            raise ExtractError(f"解压失败: {e}")
    
    def _get_format(self, archive_path: Path) -> str:
        """
        获取压缩文件格式
        
        Args:
            archive_path: 压缩文件路径
            
        Returns:
            文件格式
        """
        suffix = archive_path.suffix.lower().lstrip('.')
        
        # 处理特殊情况
        if archive_path.name.endswith('.tar.gz'):
            return 'gz'
        elif archive_path.name.endswith('.tar.bz2'):
            return 'bz2'
        elif archive_path.name.endswith('.tar.xz'):
            return 'xz'
        
        return suffix
    
    def _extract_zip(self, archive_path: Path, extract_to: Path):
        """解压ZIP文件"""
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    
    def _extract_7z(self, archive_path: Path, extract_to: Path):
        """解压7Z文件"""
        try:
            # 自己打开文件：py7zr 在构造时报错（如 BCJ2）会泄漏句柄，Windows 上之后删不掉 temp
            with open(archive_path, 'rb') as f, py7zr.SevenZipFile(f, mode='r') as z:
                z.extractall(extract_to)
        except Exception as e:
            error_msg = str(e)
            if "BCJ2 filter is not supported" in error_msg:
                self.logger.warning(f"py7zr 不支持该压缩格式，尝试使用 7-Zip 命令行工具")
                self._extract_with_7zip_cli(archive_path, extract_to)
            else:
                raise ExtractError(f"解压失败: {e}")
    
    def _extract_with_7zip_cli(self, archive_path: Path, extract_to: Path):
        """使用 7-Zip 命令行工具解压"""
        import subprocess
        import shutil
        
        # 查找 7z.exe
        seven_zip_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            "7z.exe"  # 在 PATH 中
        ]
        
        seven_zip_exe = None
        for path in seven_zip_paths:
            if shutil.which(path) or (Path(path).exists() if Path(path).is_absolute() else False):
                seven_zip_exe = path
                break
        
        if not seven_zip_exe:
            raise ExtractError("无法找到 7-Zip 命令行工具，请安装 7-Zip 或使用其他压缩格式")
        
        try:
            # 执行解压命令
            cmd = [seven_zip_exe, "x", str(archive_path), f"-o{extract_to}", "-y"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            self.logger.info(f"使用 7-Zip 成功解压到: {extract_to}")
        except subprocess.CalledProcessError as e:
            raise ExtractError(f"7-Zip 解压失败: {e.stderr}")
        except Exception as e:
            raise ExtractError(f"执行 7-Zip 失败: {e}")
    
    def _extract_rar(self, archive_path: Path, extract_to: Path):
        """解压RAR文件"""
        try:
            import rarfile
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(extract_to)
        except ImportError:
            raise ExtractError("需要安装rarfile库来处理RAR文件")
    
    def _extract_tar(self, archive_path: Path, extract_to: Path):
        """解压TAR相关文件"""
        import tarfile
        
        mode = 'r'
        if archive_path.name.endswith('.gz'):
            mode = 'r:gz'
        elif archive_path.name.endswith('.bz2'):
            mode = 'r:bz2'
        elif archive_path.name.endswith('.xz'):
            mode = 'r:xz'
        
        with tarfile.open(archive_path, mode) as tar:
            tar.extractall(extract_to)
    
    def find_content_dir(self, extract_path: Path) -> Path:
        """
        查找解压后的实际内容目录
        
        有些压缩文件解压后会有一个包含所有内容的根目录，
        这个方法用于找到实际的内容目录
        
        Args:
            extract_path: 解压目录
            
        Returns:
            实际内容目录
        """
        if not extract_path.exists():
            raise ExtractError(f"解压目录不存在: {extract_path}")
        
        # 列出解压目录的内容
        contents = list(extract_path.iterdir())
        
        # 如果只有一个目录，且该目录名包含版本信息或与压缩文件名相似
        if len(contents) == 1 and contents[0].is_dir():
            return contents[0]
        
        # 否则返回解压目录本身
        return extract_path
