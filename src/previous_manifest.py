import logging
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional, Union

from .download_manager import DownloadError, DownloadManager
from .manifest import DEFAULT_HISTORY_PATH, MANIFEST_NAME, KnownHashes, Manifest, ManifestError, load_history

logger = logging.getLogger(__name__)


class PreviousRelease(NamedTuple):
    """从这个仓库（owner/repo）最新一版 Release 取清单"""
    repo_path: str


class PreviousManifestFile(NamedTuple):
    path: Path


PreviousManifest = Union[PreviousRelease, PreviousManifestFile]


class PreviousManifestError(Exception):
    pass


def load_known_hashes(history_path: Optional[Path] = None,
                      previous: Optional[PreviousManifest] = None,
                      downloader: Optional[DownloadManager] = None) -> KnownHashes:
    """
    读取历史哈希文件，并入上一版清单

    Args:
        history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
        previous: 上一版清单从哪来，None 时只用历史哈希
        downloader: 从 Release 取清单用的下载器，None 时新建一个不走代理的

    Raises:
        ManifestError: 历史哈希文件读不出或结构不对
        PreviousManifestError: 读不到上一版清单、它的结构不对，或它不属于那版 Release
    """
    history = load_history(Path(history_path) if history_path else DEFAULT_HISTORY_PATH)
    if previous is None:
        return KnownHashes.merge(history)
    try:
        if isinstance(previous, PreviousRelease):
            manifest = _from_release(previous.repo_path, downloader or DownloadManager())
        else:
            manifest = _from_file(previous.path)
    except (DownloadError, OSError, ManifestError) as e:
        raise PreviousManifestError(f"读取上一版清单失败: {e}") from e
    return KnownHashes.merge(history, manifest)


def _from_release(repo_path: str, downloader: DownloadManager) -> Manifest:
    with tempfile.TemporaryDirectory() as dest_dir:
        asset = downloader.latest_release_asset(repo_path, MANIFEST_NAME, Path(dest_dir))
        where = f"{repo_path} 的 Release {asset.tag} 里的 {MANIFEST_NAME}"
        manifest = Manifest.parse(asset.path.read_bytes(), where)
    if manifest.archive_version != asset.tag:
        raise ManifestError([f"{where} 属于 {manifest.archive_version}，不是这个 Release"])
    logger.info(f"并入上一版清单: {repo_path} {asset.tag}")
    return manifest


def _from_file(path: Path) -> Manifest:
    manifest = Manifest.parse(Path(path).read_bytes(), str(path))
    logger.info(f"并入上一版清单: {path}")
    return manifest
