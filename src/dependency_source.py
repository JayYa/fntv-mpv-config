import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path

from .download_manager import DownloadManager
from .extract import extract_archive
from .package_config import GithubRelease, LocalDir, Source

CONTENT_DIRNAME = "content"
RECORD_FILENAME = "source.json"


class FetchError(Exception):
    """拿不到依赖的内容目录"""


class DependencySource:
    """
    给依赖名和它的来源，返回它的内容目录。

    暂存目录的布局只有这里知道：temp/<依赖名>/ 下放下载的压缩包和它的来源记录，
    temp/<依赖名>/content/ 放解压结果。本地文件夹直接当内容目录，不复制。
    """

    def __init__(self, temp_dir: Path, downloader: DownloadManager, offline: bool = False):
        """
        Args:
            temp_dir: 暂存目录，整个归这个 module 管
            downloader: 下载 GitHub Release 资产；离线模式下不调用
            offline: 离线模式，不访问网络，GitHub Release 依赖只用 temp 里上次下载、来源与本次一致的压缩包
        """
        self.temp_dir = Path(temp_dir)
        self.offline = offline
        self._downloader = downloader
        self.logger = logging.getLogger(__name__)

    def fetch(self, name: str, source: Source) -> Path:
        """
        返回依赖的内容目录：压缩包解压后去掉单一外层根目录；本地文件夹原样返回

        Raises:
            FetchError: 本地路径不存在、离线模式下没有缓存、下载或解压失败
        """
        try:
            if isinstance(source, GithubRelease):
                archive = self._cached_archive(name, source) if self.offline \
                    else self._download(name, source)
                return self._unpack(name, archive)
            if not source.path.exists():
                raise FetchError(f"本地路径不存在: {source.path}")
            if isinstance(source, LocalDir):
                self.logger.info(f"{name} 使用本地文件夹: {source.path}")
                return source.path
            return self._unpack(name, source.path)
        except FetchError:
            raise
        except Exception as e:
            raise FetchError(f"获取 {name} 失败: {e}") from e

    def _archive_dir(self, name: str) -> Path:
        return self.temp_dir / name

    def _download(self, name: str, release: GithubRelease) -> Path:
        archive_dir = self._archive_dir(name)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive = self._downloader.download(name, release, archive_dir)
        record = {"source": asdict(release), "archive": archive.name, "size": archive.stat().st_size}
        (archive_dir / RECORD_FILENAME).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8", newline="\n")
        for stale in archive_dir.iterdir():
            if stale.is_file() and stale.name != RECORD_FILENAME and stale != archive:
                stale.unlink()
        return archive

    def _cached_archive(self, name: str, release: GithubRelease) -> Path:
        archive_dir = self._archive_dir(name)
        record_path = archive_dir / RECORD_FILENAME
        rerun = "先不带 --skip-download、带 --skip-cleanup 构建一次"
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            cached_release = GithubRelease(**record["source"])
            archive = archive_dir / Path(record["archive"]).name
            size = record["size"]
        except (OSError, ValueError, KeyError, TypeError):
            raise FetchError(f"离线模式下 {archive_dir} 里没有可用的来源记录；{rerun}") from None
        if cached_release != release:
            raise FetchError(
                f"离线模式下 {name} 缓存的是 {_describe(cached_release)}，"
                f"打包配置要的是 {_describe(release)}；{rerun}")
        if not archive.is_file() or archive.stat().st_size != size:
            raise FetchError(f"离线模式下 {archive} 不在或大小变了，和来源记录对不上；{rerun}")
        self.logger.info(f"{name} 使用缓存的压缩包: {archive}")
        return archive

    def _unpack(self, name: str, archive: Path) -> Path:
        content_dir = self._archive_dir(name) / CONTENT_DIRNAME
        if content_dir.exists():
            shutil.rmtree(content_dir)
        extract_archive(archive, content_dir)
        return _without_single_root(content_dir)


def remove_temp_dir(temp_dir: Path):
    """删掉整个暂存目录"""
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        logging.getLogger(__name__).info(f"已删除临时目录: {temp_dir}")


def _describe(release: GithubRelease) -> str:
    return f"{release.repo_path} {release.version}（{release.filename_pattern}{release.archive_suffix}）"


def _without_single_root(unpacked_dir: Path) -> Path:
    entries = list(unpacked_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return unpacked_dir
