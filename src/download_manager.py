"""
下载管理模块
负责从 GitHub Release 下载依赖的压缩包
"""
import os
import requests
from typing import Dict
from pathlib import Path
import logging
from tqdm import tqdm

from .package_config import GithubRelease


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
    """下载错误异常"""
    pass


class DownloadManager:
    """下载管理器"""

    def __init__(self, proxy_url: str = "", enable_proxy: bool = False):
        """
        初始化下载管理器

        Args:
            proxy_url: GitHub代理地址
            enable_proxy: 是否启用代理
        """
        self.proxy_url = proxy_url.rstrip('/')  # 移除末尾的斜杠
        self.enable_proxy = enable_proxy
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)

    def download(self, name: str, release: GithubRelease, dest_dir: Path) -> Path:
        """
        把依赖的压缩包下载到 dest_dir；同名且大小一致的文件已存在时不重复下载

        Returns:
            下载文件的路径

        Raises:
            DownloadError: 下载失败
        """
        self.logger.info(f"开始下载 {name}")
        try:
            download_url = self._get_github_release_url(release)
            file_path = Path(dest_dir) / self._get_filename(release, download_url)

            if file_path.exists() and self._verify_file(file_path, download_url):
                self.logger.info(f"{name} 文件已存在，跳过下载")
                return file_path

            self.logger.info(f"从 {download_url} 下载到 {file_path}")
            self._download_file(download_url, file_path)
            self.logger.info(f"{name} 下载完成")
            return file_path
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"下载 {name} 失败: {e}") from e

    def _get_github_release_url(self, release: GithubRelease) -> str:
        filename = self._get_github_asset_filename(release.owner, release.repo, release.version,
                                                   release.filename_pattern, release.format)
        download_url = (f"https://github.com/{release.owner}/{release.repo}"
                        f"/releases/download/{release.version}/{filename}")

        # 如果启用代理，添加代理前缀
        if self.enable_proxy and self.proxy_url:
            download_url = f"{self.proxy_url}/{download_url}"

        self.logger.info(f"构建的下载链接: {download_url}")
        return download_url

    def _get_github_asset_filename(self, owner: str, repo: str, version: str, filename_pattern: str, file_format: str) -> str:
        """
        动态获取GitHub Release中匹配的文件名

        Args:
            owner: 仓库所有者
            repo: 仓库名
            version: 版本号
            filename_pattern: 文件名模式
            file_format: 文件格式

        Returns:
            实际的文件名
        """
        try:
            # 构建GitHub API URL来获取release信息
            api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{version}"

            # 如果启用代理，需要直接访问API而不通过代理
            response = requests.get(api_url, headers=github_api_headers(), timeout=10)
            response.raise_for_status()

            release_info = response.json()
            assets = release_info.get('assets', [])

            # 基于filename_pattern查找匹配的文件
            if '{version}' in filename_pattern:
                pattern_base = filename_pattern.format(version=version)
            else:
                pattern_base = filename_pattern

            # 策略1: 精确匹配完整文件名（包含扩展名）
            target_filename = f"{pattern_base}.{file_format}"
            for asset in assets:
                if asset['name'] == target_filename:
                    self.logger.info(f"找到精确匹配的文件: {asset['name']}")
                    return asset['name']

            # 策略2: 匹配模式开头且格式正确的文件
            for asset in assets:
                asset_name = asset['name']
                if asset_name.startswith(pattern_base) and asset_name.endswith(f'.{file_format}'):
                    self.logger.info(f"找到模式匹配的文件: {asset_name}")
                    return asset_name

            # 策略3: 更宽松的匹配 - 检查是否包含主要关键词
            pattern_keywords = pattern_base.replace('-', ' ').replace('_', ' ').split()
            for asset in assets:
                asset_name = asset['name']
                if asset_name.endswith(f'.{file_format}'):
                    # 检查是否包含所有关键词
                    asset_lower = asset_name.lower()
                    if all(keyword.lower() in asset_lower for keyword in pattern_keywords if keyword):
                        self.logger.info(f"找到关键词匹配的文件: {asset_name}")
                        return asset_name

            # 策略4: 如果只有一个匹配格式的文件，就使用它
            matching_format_assets = [asset for asset in assets if asset['name'].endswith(f'.{file_format}')]
            if len(matching_format_assets) == 1:
                self.logger.info(f"找到唯一格式匹配的文件: {matching_format_assets[0]['name']}")
                return matching_format_assets[0]['name']

            # 如果都没找到，使用默认命名
            self.logger.warning(f"未找到匹配的文件，使用默认命名: {target_filename}")
            return target_filename

        except Exception as e:
            self.logger.warning(f"获取GitHub文件名失败: {e}，使用默认命名")
            # 降级到基本命名
            if '{version}' in filename_pattern:
                base_name = filename_pattern.format(version=version)
            else:
                base_name = filename_pattern
            return f"{base_name}.{file_format}"

    def _get_filename(self, release: GithubRelease, download_url: str) -> str:
        filename = download_url.split('/')[-1]
        if not filename.endswith(f".{release.format}"):
            filename = f"{release.filename_pattern}.{release.format}"
        return filename

    def _verify_file(self, file_path: Path, download_url: str) -> bool:
        """
        验证文件是否有效

        Args:
            file_path: 文件路径
            download_url: 下载URL

        Returns:
            是否有效
        """
        try:
            # 简单的大小验证
            response = self.session.head(download_url)
            remote_size = int(response.headers.get('content-length', 0))
            local_size = file_path.stat().st_size

            return remote_size == 0 or local_size == remote_size
        except:
            return False

    def _download_file(self, url: str, file_path: Path, chunk_size: int = 8192):
        """
        下载文件

        Args:
            url: 下载URL
            file_path: 保存路径
            chunk_size: 块大小
        """
        response = self.session.get(url, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))

        # 创建进度条
        # 优化进度条显示，增强兼容性
        progress_bar = tqdm(
            total=total_size,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            desc=file_path.name,
            disable=total_size == 0,  # 如果无法获取总大小，禁用进度条
            ascii=False,  # 使用Unicode字符以更好显示
            ncols=100,  # 增加宽度以更好显示
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]'
        )

        try:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        progress_bar.update(len(chunk))
        finally:
            progress_bar.close()

        # 下载完成后记录日志
        if total_size > 0:
            self.logger.info(f"下载完成: {file_path.name} ({total_size / 1024 / 1024:.1f} MB)")
        else:
            self.logger.info(f"下载完成: {file_path.name}")

