"""
安装包（package archive）的构建与契约测试

调用方只需要这里的 interface；清单格式、归属规则和各项检查是 manifest.py 里的实现。
"""
from pathlib import Path
from typing import List, Optional

from .manifest import KnownHashes, check_archive, check_manifest_asset

__all__ = ["KnownHashes", "contract_test"]


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
