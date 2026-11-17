import logging
import os
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

import requests
from tqdm import tqdm

from .package_config import GithubRelease

API_TIMEOUT = 10
DOWNLOAD_TIMEOUT = (10, 60)


def github_api_headers() -> Dict[str, str]:
    """
    GitHub API 请求头。设置了 GITHUB_TOKEN（CI 中由 workflow 传入）或 GH_TOKEN 时带上认证，
    避免匿名请求按 IP 计的 60 次/小时额度在共享 runner 上被耗尽（403 rate limit）
    """
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


class DownloadError(Exception):
    pass


class Asset(NamedTuple):
    name: str
    url: str
    size: int


class DownloadManager:
    def __init__(self, asset_proxy_url: str = "", enable_proxy: bool = False,
                 session: Optional[requests.Session] = None):
        self.asset_proxy_url = asset_proxy_url.rstrip('/')
        self.enable_proxy = enable_proxy
        self.session = session or requests.Session()
        self.logger = logging.getLogger(__name__)

    def download(self, name: str, release: GithubRelease, dest_dir: Path) -> Path:
        """
        把依赖的压缩包下载到 dest_dir；同名且大小与 Release 资产一致的文件已存在时不重复下载

        Raises:
            DownloadError: 读不到 Release、选不出唯一资产、下载失败或大小不符
        """
        try:
            asset = select_asset(release, self._release_assets(release))
            file_path = Path(dest_dir) / asset.name
            if file_path.is_file() and file_path.stat().st_size == asset.size:
                self.logger.info(f"{name} 已下载过 {asset.name}，跳过下载")
                return file_path
            url = self._proxied(asset.url)
            self.logger.info(f"下载 {name}: {url}")
            self._download_file(url, file_path, asset.size)
            return file_path
        except (DownloadError, requests.RequestException, OSError, ValueError, KeyError) as e:
            raise DownloadError(f"下载 {name} 失败: {e}") from e

    def _release_assets(self, release: GithubRelease) -> List[Asset]:
        api_url = f"https://api.github.com/repos/{release.repo_path}/releases/tags/{release.version}"
        response = self.session.get(api_url, headers=github_api_headers(), timeout=API_TIMEOUT)
        if response.status_code in (403, 429):
            raise DownloadError(f"GitHub API 拒绝请求（HTTP {response.status_code}），多半是限流；"
                                f"设置 GITHUB_TOKEN 后重试: {api_url}")
        if response.status_code == 404:
            raise DownloadError(f"{release.repo_path} 没有 tag 为 {release.version} 的 Release")
        response.raise_for_status()
        return [Asset(a["name"], a["browser_download_url"], a["size"])
                for a in response.json().get("assets", [])]

    def _proxied(self, url: str) -> str:
        if self.enable_proxy and self.asset_proxy_url:
            return f"{self.asset_proxy_url}/{url}"
        return url

    def _download_file(self, url: str, file_path: Path, expected_size: int):
        partial = file_path.with_name(file_path.name + ".part")
        try:
            response = self.session.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
            response.raise_for_status()
            with open(partial, 'wb') as f, tqdm(total=expected_size, unit='B', unit_scale=True,
                                                unit_divisor=1024, desc=file_path.name, ncols=100) as progress:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    f.write(chunk)
                    progress.update(len(chunk))
            written = partial.stat().st_size
            if written != expected_size:
                raise DownloadError(f"{file_path.name} 下载了 {written} 字节，Release 上是 {expected_size} 字节")
            partial.replace(file_path)
        finally:
            partial.unlink(missing_ok=True)


def select_asset(release: GithubRelease, assets: List[Asset]) -> Asset:
    """
    名字等于 <filename_pattern>.<format> 的资产优先；没有时取唯一以 filename_pattern 开头、
    以 .<format> 结尾的资产。filename_pattern 里的 {version} 换成 version。

    Raises:
        DownloadError: 没有匹配的资产，或匹配的不止一个
    """
    base, suffix = release.asset_prefix, release.archive_suffix
    for asset in assets:
        if asset.name == base + suffix:
            return asset
    matches = [a for a in assets if a.name.startswith(base) and a.name.endswith(suffix)]
    if len(matches) == 1:
        return matches[0]
    where = f"{release.repo_path} {release.version}"
    if matches:
        raise DownloadError(f"{where} 里有 {len(matches)} 个资产匹配 {base}*{suffix}，"
                            f"请把 filename_pattern 写得更具体: {[a.name for a in matches]}")
    raise DownloadError(f"{where} 里没有匹配 {base}*{suffix} 的资产，"
                        f"现有资产: {[a.name for a in assets]}")
