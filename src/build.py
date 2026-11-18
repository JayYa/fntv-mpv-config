import logging
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

import requests

from .dependency_source import DependencySource, FetchError
from .download_manager import DownloadManager
from .install_manager import InstallError, InstallManager
from .manifest import KnownHashes, ManifestError
from .package_archive import ContractTestFailed, PackageArchive, build_package_archive
from .package_config import DependencySpec, PackageConfig
from .previous_manifest import PreviousManifest, PreviousManifestError, load_known_hashes
from .release import BuildResult, Dependency

logger = logging.getLogger(__name__)


class BuildScope(Enum):
    FETCH = "fetch"
    INSTALL = "install"
    PACKAGE = "package"


class BuildFailed(Exception):
    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


def build(config: PackageConfig, scope: BuildScope = BuildScope.PACKAGE, *,
          dependencies: Optional[Sequence[str]] = None, offline: bool = False,
          keep_temp: bool = False, package_timestamp: Optional[str] = None,
          history_path: Optional[Path] = None, previous: Optional[PreviousManifest] = None,
          session: Optional[requests.Session] = None) -> BuildResult:
    """
    按构建范围做一次构建

    安装前先清空 project 目录，安装包里只有本次安装的文件。成功时删掉临时目录（keep_temp 时保留），
    失败时总是保留，方便排查或离线重跑。

    Args:
        dependencies: 只处理这些依赖，None 表示全部启用的依赖；只处理一部分时不能完整打包
        offline: GitHub Release 依赖只用临时目录里上次下载的压缩包，没有就失败
        package_timestamp: 构建时间戳（yyyyMMdd_HHmmss），None 时用当前北京时间
        history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
        previous: 上一版清单从哪来，None 时只用历史哈希
        session: 访问 GitHub 用的 HTTP 会话，None 时新建
        package_timestamp、history_path、previous 只在完整打包时用到。

    Raises:
        BuildFailed: 依赖名不对、准备 project 目录或取依赖、安装失败、读不到已知哈希、写不出安装包或没通过契约测试
    """
    targets = _target_dependencies(config, dependencies, scope)
    logger.info(f"将处理以下依赖项: {list(targets)}")

    downloader = DownloadManager(config.github_proxy, config.enable_proxy, session=session)
    source = DependencySource(config.temp_dir, offline=offline, downloader=downloader)
    installer = InstallManager(config.output_dir, config.project_name)

    known = _known_hashes(history_path, previous, downloader) if scope is BuildScope.PACKAGE else None

    installing = scope is not BuildScope.FETCH
    if installing:
        try:
            installer.reset_project_dir()
            installer.install_base_config(config.archive_layout)
        except OSError as e:
            raise BuildFailed([f"准备 project 目录失败: {e}"]) from e
    for name, entry in targets.items():
        try:
            content_dir = source.fetch(name, entry.source)
            if installing:
                installer.install_dependency(config.archive_layout.placements[name], content_dir)
        except (FetchError, InstallError, OSError) as e:
            raise BuildFailed([f"处理依赖项 {name} 失败: {e}"]) from e

    result = BuildResult(
        output_dir=installer.base_output_dir.resolve(),
        project_dir=installer.output_dir.resolve(),
        processed_dependencies=_release_dependencies(targets),
        disabled_dependencies=_release_dependencies(config.disabled_dependencies),
    )
    if scope is BuildScope.PACKAGE:
        result = replace(result, package=_package(config, installer, known, package_timestamp))

    if not keep_temp:
        try:
            source.clean()
        except OSError as e:
            logger.warning(f"清理临时目录失败: {e}")
    return result


def _target_dependencies(config: PackageConfig, names: Optional[Sequence[str]],
                         scope: BuildScope) -> Dict[str, DependencySpec]:
    enabled = config.enabled_dependencies
    if names is None:
        return dict(enabled)
    unknown = [name for name in names if name not in config.dependencies]
    disabled = [name for name in names if name in config.disabled_dependencies]
    problems = []
    if unknown:
        problems.append(f"没有这些依赖项: {', '.join(unknown)}")
    if disabled:
        problems.append(f"这些依赖项已停用: {', '.join(disabled)}，要处理请先在 package_cfg.json 里把 enabled 改成 true")
    if problems:
        hint = f"可选: {', '.join(enabled)}"
        if config.disabled_dependencies:
            hint += f"；已停用: {', '.join(config.disabled_dependencies)}"
        raise BuildFailed(problems + [hint])
    if scope is BuildScope.PACKAGE:
        raise BuildFailed(["只处理一部分依赖时打出的安装包不完整，不能完整打包；"
                           "请改为只取依赖或只安装"])
    return {name: enabled[name] for name in names}


def _known_hashes(history_path: Optional[Path], previous: Optional[PreviousManifest],
                  downloader: DownloadManager) -> KnownHashes:
    try:
        return load_known_hashes(history_path, previous, downloader)
    except PreviousManifestError as e:
        raise BuildFailed([str(e)]) from e
    except ManifestError as e:
        raise BuildFailed(e.errors) from e


def _package(config: PackageConfig, installer: InstallManager, known: KnownHashes,
             timestamp: Optional[str]) -> PackageArchive:
    components = {name: entry.version for name, entry in config.enabled_dependencies.items()}
    try:
        package = build_package_archive(installer.output_dir, components, known,
                                        config.archive_layout, timestamp=timestamp)
    except ContractTestFailed as e:
        raise BuildFailed([f"契约测试失败: {error}" for error in e.errors]) from e
    except OSError as e:
        raise BuildFailed([f"写出安装包失败: {e}"]) from e
    logger.info(f"安装包已创建并通过契约测试: {package.path}（{package.archive_version}）")
    return package


def _release_dependencies(dependencies: Mapping[str, DependencySpec]) -> Tuple[Dependency, ...]:
    return tuple(Dependency(entry.display_name, entry.version) for entry in dependencies.values())
