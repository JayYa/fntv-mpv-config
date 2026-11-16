import logging
import shutil
from pathlib import Path
from typing import Optional

from .download_manager import DownloadManager
from .extract_manager import ExtractManager
from .package_config import GithubRelease, LocalDir, Source

CONTENT_DIRNAME = "content"


class FetchError(Exception):
    """拿不到依赖的内容目录"""


class DependencySource:
    """
    给依赖名和它的来源，返回它的内容目录。

    暂存目录的布局只有这里知道：temp/<依赖名>/ 下放下载的压缩包，
    temp/<依赖名>/content/ 放解压结果。本地文件夹直接当内容目录，不复制。
    """

    def __init__(self, temp_dir: Path, proxy_url: str = "",
                 enable_proxy: bool = False, offline: bool = False,
                 downloader: Optional[DownloadManager] = None):
        """
        Args:
            temp_dir: 暂存目录，整个归这个 module 管
            proxy_url: GitHub 代理地址
            enable_proxy: 是否启用代理
            offline: 离线模式，不访问网络，GitHub Release 依赖只用 temp 里上次下载的压缩包
            downloader: 替换网络下载器（测试用）；None 时第一次下载才按代理设置创建
        """
        self.temp_dir = Path(temp_dir)
        self.proxy_url = proxy_url
        self.enable_proxy = enable_proxy
        self.offline = offline
        self._downloader = downloader
        self.extractor = ExtractManager()
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

    def clean(self):
        """删掉整个暂存目录"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            self.logger.info(f"已删除临时目录: {self.temp_dir}")

    def _archive_dir(self, name: str) -> Path:
        return self.temp_dir / name

    def _download(self, name: str, release: GithubRelease) -> Path:
        archive_dir = self._archive_dir(name)
        archive_dir.mkdir(parents=True, exist_ok=True)
        if self._downloader is None:
            self._downloader = DownloadManager(self.proxy_url, self.enable_proxy)
        archive = self._downloader.download(name, release, archive_dir)
        for stale in archive_dir.iterdir():
            if stale.is_file() and stale != archive:
                stale.unlink()
        return archive

    def _cached_archive(self, name: str, release: GithubRelease) -> Path:
        archive_dir = self._archive_dir(name)
        suffix = f".{release.format}"
        cached = sorted(p for p in archive_dir.glob(f"*{suffix}") if p.is_file()) \
            if archive_dir.is_dir() else []
        if len(cached) != 1:
            raise FetchError(
                f"离线模式下 {archive_dir} 里应有且仅有一个 *{suffix} 压缩包，实际 {len(cached)} 个；"
                f"先不带 --skip-download、带 --skip-cleanup 构建一次")
        self.logger.info(f"{name} 使用缓存的压缩包: {cached[0]}")
        return cached[0]

    def _unpack(self, name: str, archive: Path) -> Path:
        content_dir = self._archive_dir(name) / CONTENT_DIRNAME
        if content_dir.exists():
            shutil.rmtree(content_dir)
        self.extractor.extract_archive(archive, content_dir)
        return self.extractor.find_content_dir(content_dir)
