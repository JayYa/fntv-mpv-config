import logging
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

import py7zr

SEVEN_ZIP_CANDIDATES = (
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "7z",
)

logger = logging.getLogger(__name__)


class ExtractError(Exception):
    pass


def _extract_zip(archive_path: Path, extract_to: Path):
    with zipfile.ZipFile(archive_path) as z:
        z.extractall(extract_to)


def _extract_tar(archive_path: Path, extract_to: Path):
    with tarfile.open(archive_path, "r:*") as tar:
        tar.extractall(extract_to, filter="data")


def _extract_7z(archive_path: Path, extract_to: Path):
    try:
        # 传文件对象而不是路径：传路径时 py7zr 并行解压，会按文件名另开一个不关闭的句柄，
        # 解压报错（如 BCJ2）后它要等 GC 才释放，Windows 上 temp 就删不掉
        with open(archive_path, 'rb') as f, py7zr.SevenZipFile(f, mode='r') as z:
            z.extractall(extract_to)
    except Exception as e:
        if "BCJ2 filter is not supported" not in str(e):
            raise
        logger.warning("py7zr 不支持该压缩格式，改用 7-Zip 命令行工具")
        _extract_with_7zip_cli(archive_path, extract_to)


def _extract_with_7zip_cli(archive_path: Path, extract_to: Path):
    seven_zip = next((c for c in SEVEN_ZIP_CANDIDATES if shutil.which(c)), None)
    if seven_zip is None:
        raise ExtractError("找不到 7-Zip 命令行工具，请安装 7-Zip")
    try:
        subprocess.run([seven_zip, "x", str(archive_path), f"-o{extract_to}", "-y"],
                       capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise ExtractError(f"7-Zip 解压失败: {e.stderr}") from e


def _extract_rar(archive_path: Path, extract_to: Path):
    try:
        import rarfile
    except ImportError as e:
        raise ExtractError("解压 RAR 需要安装 rarfile 库") from e
    with rarfile.RarFile(archive_path) as rf:
        rf.extractall(extract_to)


_EXTRACTORS = {
    "zip": _extract_zip,
    "7z": _extract_7z,
    "rar": _extract_rar,
    "tar": _extract_tar,
    "tar.gz": _extract_tar,
    "tar.bz2": _extract_tar,
    "tar.xz": _extract_tar,
}

ARCHIVE_FORMATS = tuple(_EXTRACTORS)
ARCHIVE_FORMATS_TEXT = ", ".join(ARCHIVE_FORMATS)


def archive_format(path: Path) -> Optional[str]:
    name = path.name.lower()
    matches = [f for f in ARCHIVE_FORMATS if name.endswith("." + f)]
    return max(matches, key=len) if matches else None


def extract_archive(archive_path: Path, extract_to: Path):
    """
    Raises:
        ExtractError: 文件不存在、格式不支持或解压失败
    """
    if not archive_path.is_file():
        raise ExtractError(f"压缩文件不存在: {archive_path}")
    file_format = archive_format(archive_path)
    if file_format is None:
        raise ExtractError(f"不支持的压缩格式: {archive_path.name}，只支持 {ARCHIVE_FORMATS_TEXT}")

    extract_to.mkdir(parents=True, exist_ok=True)
    logger.info(f"解压 {archive_path} 到 {extract_to}")
    try:
        _EXTRACTORS[file_format](archive_path, extract_to)
    except ExtractError:
        raise
    except Exception as e:
        raise ExtractError(f"解压 {archive_path.name} 失败: {e}") from e
