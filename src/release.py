"""
构建结果：一次构建交给发布步骤的全部事实

发布步骤（.github/workflows/daily-build.yml）只读构建结果，不自行推导安装包名、tag 或时间戳。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class BuildResult:
    """
    一次构建的结果

    不打包（--skip-package / --skip-install）时，安装包相关字段都是 None。
    """
    output_dir: Path
    project_dir: Path
    # 本次实际处理的依赖：(显示名, 版本)，按处理顺序
    dependencies: List[Tuple[str, str]] = field(default_factory=list)
    timestamp: Optional[str] = None
    archive_version: Optional[str] = None
    package_path: Optional[Path] = None
    manifest_asset_path: Optional[Path] = None
