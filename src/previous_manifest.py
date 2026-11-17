"""上一版清单（previous manifest）：从哪取、怎么校验、怎么并进已知哈希"""
import json
import logging
import tempfile
from pathlib import Path
from typing import NamedTuple, Optional, Union

from .download_manager import DownloadError, DownloadManager
from .manifest import DEFAULT_HISTORY_PATH, MANIFEST_NAME, KnownHashes, load_history

logger = logging.getLogger(__name__)


class PreviousRelease(NamedTuple):
    """从这个仓库（owner/repo）最新一版 Release 取清单"""
    repo_path: str


class PreviousManifestFile(NamedTuple):
    path: Path


PreviousManifest = Union[PreviousRelease, PreviousManifestFile]


class PreviousManifestError(Exception):
    """指定了上一版清单却拿不到，或拿到的不是这版 Release 的清单"""


def load_known_hashes(history_path: Optional[Path] = None,
                      previous: Optional[PreviousManifest] = None,
                      downloader: Optional[DownloadManager] = None) -> KnownHashes:
    """
    读取历史哈希文件，并入上一版清单

    Args:
        history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
        previous: 上一版清单从哪来，None 时只用历史哈希
        downloader: 从 Release 取清单用的下载器，None 时按默认设置创建

    Raises:
        PreviousManifestError: 读不到上一版清单、它缺少 files 列表，或它不属于那版 Release
    """
    history = load_history(Path(history_path) if history_path else DEFAULT_HISTORY_PATH)
    if previous is None:
        return KnownHashes.merge(history)
    try:
        if isinstance(previous, PreviousRelease):
            manifest = _from_release(previous.repo_path, downloader or DownloadManager())
        else:
            manifest = _from_file(Path(previous.path))
    except (DownloadError, OSError, ValueError) as e:
        raise PreviousManifestError(f"读取上一版清单失败: {e}") from e
    return KnownHashes.merge(history, manifest)


def _from_release(repo_path: str, downloader: DownloadManager) -> dict:
    with tempfile.TemporaryDirectory() as dest_dir:
        tag, path = downloader.latest_release_asset(repo_path, MANIFEST_NAME, Path(dest_dir))
        where = f"{repo_path} 的 Release {tag} 里的 {MANIFEST_NAME}"
        manifest = _parse(path, where)
    if manifest.get("archiveVersion") != tag:
        raise PreviousManifestError(f"{where} 属于 {manifest.get('archiveVersion')}，不是这个 Release")
    logger.info(f"并入上一版清单: {repo_path} {tag}")
    return manifest


def _from_file(path: Path) -> dict:
    manifest = _parse(path, str(path))
    logger.info(f"并入上一版清单: {path}")
    return manifest


def _parse(path: Path, where: str) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), list):
        raise PreviousManifestError(f"{where} 缺少 files 列表")
    return manifest
