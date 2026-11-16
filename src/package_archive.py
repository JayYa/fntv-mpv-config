"""安装包（package archive）的构建与契约测试"""
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .manifest import (MANIFEST_NAME, PORTABLE_CONFIG, KnownHashes, build_manifest,
                       check_archive, check_manifest_asset, write_manifest)

__all__ = [
    "ContractTestFailed", "KnownHashes", "PackageArchive", "build_package_archive",
    "contract_test", "is_package_archive_name", "remove_package_archives",
    "validate_package_timestamp",
]

TIMESTAMP_REGEX = r"\d{8}_\d{6}"
PACKAGE_TIMESTAMP_PATTERN = re.compile(TIMESTAMP_REGEX)
PACKAGE_ARCHIVE_PREFIX = "mpv-package-"
PACKAGE_ARCHIVE_NAME = re.compile(re.escape(PACKAGE_ARCHIVE_PREFIX) + TIMESTAMP_REGEX + r"\.zip")

# 构建时间戳一律用北京时间。中国没有夏令时，固定 UTC+8 即可，不依赖 Windows 上缺失的时区库
BEIJING = timezone(timedelta(hours=8), "Asia/Shanghai")


@dataclass(frozen=True)
class PackageArchive:
    path: Path
    manifest_asset_path: Path
    archive_version: str
    timestamp: str


class ContractTestFailed(Exception):
    """安装包没通过契约测试，不能发版"""

    def __init__(self, errors: List[str]):
        super().__init__(f"契约测试失败（{len(errors)} 项）")
        self.errors = errors


def validate_package_timestamp(timestamp: str) -> str:
    """
    校验构建时间戳格式（yyyyMMdd_HHmmss，与 Release tag 的时间部分相同）

    Raises:
        ValueError: 格式不符
    """
    if not PACKAGE_TIMESTAMP_PATTERN.fullmatch(timestamp):
        raise ValueError(f"构建时间戳格式应为 yyyyMMdd_HHmmss，实际为: {timestamp!r}")
    return timestamp


def is_package_archive_name(name: str) -> bool:
    """文件名是不是 build_package_archive 产出的安装包"""
    return PACKAGE_ARCHIVE_NAME.fullmatch(name) is not None


def remove_package_archives(output_dir: Path) -> List[Path]:
    """删掉输出目录里 build_package_archive 产出的安装包和清单资产，返回删掉的文件"""
    removed = []
    for item in sorted(Path(output_dir).iterdir()):
        if item.is_file() and (is_package_archive_name(item.name) or item.name == MANIFEST_NAME):
            item.unlink()
            removed.append(item)
    return removed


def build_package_archive(project_dir: Path, components: Dict[str, str], known: KnownHashes,
                          timestamp: Optional[str] = None) -> PackageArchive:
    """
    给 project 目录生成清单、打成安装包，并跑契约测试

    清单写进 project 目录（因而进 zip 根目录），也写到 zip 旁边作为 Release 的清单资产；
    安装包 mpv-package-<时间戳>.zip 放在 project 目录的父目录。

    Args:
        project_dir: 含 mpv.exe 和 portable_config 的目录
        components: 清单的 components，依赖项名 -> 版本
        known: 已知哈希
        timestamp: 构建时间戳（yyyyMMdd_HHmmss），None 时用当前北京时间

    Raises:
        ValueError: 时间戳格式不符
        ManifestError: portable_config 里有文件没有归属
        ContractTestFailed: 安装包没通过契约测试
    """
    if timestamp is None:
        timestamp = datetime.now(BEIJING).strftime("%Y%m%d_%H%M%S")
    validate_package_timestamp(timestamp)
    project_dir = Path(project_dir).resolve()
    archive_version = f"fntv-mpv-v{timestamp}"

    manifest = build_manifest(project_dir / PORTABLE_CONFIG, archive_version, components, known)
    write_manifest(project_dir, manifest)
    zip_path = project_dir.parent / f"{PACKAGE_ARCHIVE_PREFIX}{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for file_path in sorted(project_dir.rglob("*")):
            if file_path.is_file():
                z.write(file_path, file_path.relative_to(project_dir).as_posix())
    asset_path = write_manifest(project_dir.parent, manifest)

    errors = contract_test(zip_path, known, archive_version=archive_version,
                           manifest_asset=asset_path)
    if errors:
        raise ContractTestFailed(errors)
    return PackageArchive(path=zip_path, manifest_asset_path=asset_path,
                          archive_version=archive_version, timestamp=timestamp)


def contract_test(zip_path: Path, known: KnownHashes, archive_version: Optional[str] = None,
                  manifest_asset: Optional[Path] = None) -> List[str]:
    """
    契约测试：安装包与其中的清单一致、满足客户端依赖、已知哈希只增不减

    Args:
        zip_path: 安装包路径
        known: 已知哈希
        archive_version: 期望的归档版本（本次 Release tag），None 时不检查
        manifest_asset: Release 单独上传的清单资产，必须与 zip 里的逐字节相同；None 时不检查

    Returns:
        错误列表，空列表表示通过
    """
    errors = check_archive(Path(zip_path), archive_version=archive_version, known=known)
    if manifest_asset is not None:
        errors += check_manifest_asset(Path(zip_path), Path(manifest_asset))
    return errors
