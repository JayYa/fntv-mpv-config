"""
下载管理模块
负责从GitHub等源下载文件
"""
import os
import re
import requests
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging
from tqdm import tqdm


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
    
    def __init__(self, temp_dir: Path, proxy_url: str = "", enable_proxy: bool = False):
        """
        初始化下载管理器
        
        Args:
            temp_dir: 临时下载目录
            proxy_url: GitHub代理地址
            enable_proxy: 是否启用代理
        """
        self.temp_dir = Path(temp_dir)
        self.proxy_url = proxy_url.rstrip('/')  # 移除末尾的斜杠
        self.enable_proxy = enable_proxy
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)
        
        # 创建临时目录
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def download_dependency(self, name: str, config: Dict[str, Any]) -> Path:
        """
        下载依赖项，支持网络下载和本地文件
        
        Args:
            name: 依赖项名称
            config: 依赖项配置
            
        Returns:
            下载文件的路径
            
        Raises:
            DownloadError: 下载失败
        """
        self.logger.info(f"开始处理 {name}")
        
        try:
            # 检查是否为本地文件
            if self._is_local_file(config):
                return self._handle_local_file(name, config)
            
            # 网络下载逻辑
            return self._handle_network_download(name, config)
            
        except Exception as e:
            raise DownloadError(f"处理 {name} 失败: {e}")
    
    def _is_local_file(self, config: Dict[str, Any]) -> bool:
        """
        检查配置是否指向本地文件
        
        Args:
            config: 依赖项配置
            
        Returns:
            是否为本地文件
        """
        url = config.get('url', '')
        local_path = config.get('local_path', '')
        
        # 如果配置了 local_path，或者 url 是本地路径
        return bool(local_path) or (url and not url.startswith(('http://', 'https://')))
    
    def _handle_local_file(self, name: str, config: Dict[str, Any]) -> Path:
        """
        处理本地文件或文件夹
        
        Args:
            name: 依赖项名称
            config: 依赖项配置
            
        Returns:
            本地文件的路径或解压目录的路径（如果是文件夹）
        """
        # 优先使用 local_path，否则使用 url
        local_path_str = config.get('local_path') or config.get('url', '')
        
        if not local_path_str:
            raise DownloadError(f"{name} 没有指定本地文件路径")
        
        local_path = Path(local_path_str)
        
        # 如果是相对路径，相对于项目根目录
        if not local_path.is_absolute():
            # 获取项目根目录（假设临时目录在项目根目录下）
            project_root = self.temp_dir.parent
            local_path = project_root / local_path
        
        # 检查路径是否存在
        if not local_path.exists():
            raise DownloadError(f"本地路径不存在: {local_path}")
        
        if local_path.is_file():
            # 处理压缩包文件
            return self._handle_local_archive(name, local_path, config)
        elif local_path.is_dir():
            # 处理已解压的文件夹
            return self._handle_local_directory(name, local_path, config)
        else:
            raise DownloadError(f"不支持的本地路径类型: {local_path}")
    
    def _handle_local_archive(self, name: str, local_path: Path, config: Dict[str, Any]) -> Path:
        """
        处理本地压缩包文件
        
        Args:
            name: 依赖项名称
            local_path: 本地压缩包路径
            config: 依赖项配置
            
        Returns:
            复制到临时目录的压缩包路径
        """
        self.logger.info(f"使用本地压缩包: {local_path}")
        
        # 为了保持与网络下载的一致性，将文件复制到临时目录
        target_filename = self._get_filename_from_local_path(local_path, config)
        target_path = self.temp_dir / target_filename
        
        # 如果目标文件已存在且内容相同，跳过复制
        if target_path.exists() and self._files_are_same(local_path, target_path):
            self.logger.info(f"{name} 本地压缩包已存在于临时目录，跳过复制")
            return target_path
        
        # 复制文件到临时目录
        import shutil
        shutil.copy2(local_path, target_path)
        self.logger.info(f"已复制本地压缩包到: {target_path}")
        
        return target_path
    
    def _handle_local_directory(self, name: str, local_path: Path, config: Dict[str, Any]) -> Path:
        """
        处理本地已解压的文件夹
        
        Args:
            name: 依赖项名称
            local_path: 本地文件夹路径
            config: 依赖项配置
            
        Returns:
            复制到临时目录的文件夹路径
        """
        self.logger.info(f"使用本地文件夹: {local_path}")
        
        # 为已解压文件夹创建目标目录名
        target_dirname = self._get_directory_name_from_config(name, config)
        target_path = self.temp_dir / f"{target_dirname}_extracted"
        
        # 如果目标目录已存在，检查是否需要更新
        if target_path.exists():
            if self._directory_is_newer(local_path, target_path):
                self.logger.info(f"本地文件夹有更新，重新复制到: {target_path}")
                import shutil
                shutil.rmtree(target_path)
            else:
                self.logger.info(f"{name} 本地文件夹已存在于临时目录，跳过复制")
                return target_path
        
        # 复制整个文件夹到临时目录
        import shutil
        shutil.copytree(local_path, target_path)
        self.logger.info(f"已复制本地文件夹到: {target_path}")
        
        return target_path
    
    def _get_directory_name_from_config(self, name: str, config: Dict[str, Any]) -> str:
        """
        从配置获取目录名
        
        Args:
            name: 依赖项名称
            config: 依赖项配置
            
        Returns:
            目录名
        """
        # 如果配置中指定了文件名模式，使用它
        if 'filename_pattern' in config:
            version = config.get('version', 'local')
            pattern = config['filename_pattern']
            # 替换版本占位符
            return pattern.format(version=version)
        
        # 否则使用依赖项名称
        return name
    
    def _directory_is_newer(self, source_dir: Path, target_dir: Path) -> bool:
        """
        检查源目录是否比目标目录更新
        
        Args:
            source_dir: 源目录
            target_dir: 目标目录
            
        Returns:
            源目录是否更新
        """
        try:
            # 简单比较：获取源目录中最新文件的修改时间
            source_latest = max(
                (f.stat().st_mtime for f in source_dir.rglob('*') if f.is_file()),
                default=0
            )
            
            # 获取目标目录的创建时间
            target_created = target_dir.stat().st_ctime
            
            return source_latest > target_created
        except:
            # 如果出错，默认认为需要更新
            return True
    
    def _handle_network_download(self, name: str, config: Dict[str, Any]) -> Path:
        """
        处理网络下载
        
        Args:
            name: 依赖项名称
            config: 依赖项配置
            
        Returns:
            下载文件的路径
        """
        # 获取下载URL
        download_url = self._get_download_url(config)
        if not download_url:
            raise DownloadError(f"无法获取 {name} 的下载链接")

        # 确定文件名
        filename = self._get_filename(config, download_url)
        file_path = self.temp_dir / filename

        # 如果文件已存在且大小正确，跳过下载
        if file_path.exists() and self._verify_file(file_path, download_url):
            self.logger.info(f"{name} 文件已存在，跳过下载")
            return file_path

        # 下载文件
        self.logger.info(f"从 {download_url} 下载到 {file_path}")
        self._download_file(download_url, file_path)

        self.logger.info(f"{name} 下载完成")
        return file_path
    
    def _get_filename_from_local_path(self, local_path: Path, config: Dict[str, Any]) -> str:
        """
        从本地路径和配置获取目标文件名
        
        Args:
            local_path: 本地文件路径
            config: 依赖项配置
            
        Returns:
            目标文件名
        """
        # 如果配置中指定了文件名模式，使用它
        if 'filename_pattern' in config:
            version = config.get('version', 'local')
            file_format = config.get('format', local_path.suffix.lstrip('.'))
            pattern = config['filename_pattern']
            
            # 替换版本占位符
            filename = pattern.format(version=version)
            
            # 如果没有扩展名，添加格式
            if '.' not in filename:
                filename = f"{filename}.{file_format}"
                
            return filename
        
        # 否则使用原文件名
        return local_path.name
    
    def _files_are_same(self, file1: Path, file2: Path) -> bool:
        """
        检查两个文件是否相同
        
        Args:
            file1: 文件1
            file2: 文件2
            
        Returns:
            是否相同
        """
        try:
            # 简单比较文件大小和修改时间
            stat1 = file1.stat()
            stat2 = file2.stat()
            return stat1.st_size == stat2.st_size and abs(stat1.st_mtime - stat2.st_mtime) < 1
        except:
            return False
    
    def _get_download_url(self, config: Dict[str, Any]) -> Optional[str]:
        """
        获取下载URL
        
        Args:
            config: 依赖项配置
            
        Returns:
            下载URL
        """
        base_url = config['url']
        version = config['version']
        filename_pattern = config['filename_pattern']
        file_format = config['format']
        
        if 'github.com' in base_url and '/releases' in base_url:
            return self._get_github_release_url(base_url, version, filename_pattern, file_format)
        else:
            # 其他下载源的处理可以在这里扩展
            raise DownloadError(f"不支持的下载源: {base_url}")
    
    def _get_github_release_url(self, base_url: str, version: str, filename_pattern: str, file_format: str) -> Optional[str]:
        """
        获取GitHub Release的下载URL
        
        Args:
            base_url: GitHub仓库URL
            version: 版本号
            filename_pattern: 文件名模式
            file_format: 文件格式
            
        Returns:
            下载URL
        """
        # 提取仓库信息
        repo_match = re.search(r'github\.com/([^/]+)/([^/]+)', base_url)
        if not repo_match:
            self.logger.error(f"无法解析GitHub仓库URL: {base_url}")
            return None
            
        owner, repo = repo_match.groups()
        self.logger.info(f"解析出仓库: {owner}/{repo}")
        
        # 根据具体的仓库构建准确的文件名
        if owner == "shinchiro" and repo == "mpv-winbuild-cmake":
            # MPV的文件名需要从GitHub API获取实际的文件名
            filename = self._get_github_asset_filename(owner, repo, version, filename_pattern, file_format)
        else:
            # 通用处理：尝试从GitHub API获取匹配的文件名
            filename = self._get_github_asset_filename(owner, repo, version, filename_pattern, file_format)
        
        # 构建直接下载链接
        download_url = f"https://github.com/{owner}/{repo}/releases/download/{version}/{filename}"
        
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
    
    def _get_filename(self, config: Dict[str, Any], download_url: str) -> str:
        """
        确定下载文件名
        
        Args:
            config: 依赖项配置
            download_url: 下载URL
            
        Returns:
            文件名
        """
        # 从URL中提取文件名
        filename = download_url.split('/')[-1]
        
        # 如果文件名不包含格式，添加格式
        if not filename.endswith(f".{config['format']}"):
            filename = f"{config['filename_pattern']}.{config['format']}"
        
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
    
    def cleanup(self):
        """清理临时文件"""
        try:
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir)
        except Exception as e:
            self.logger.warning(f"清理临时文件失败: {e}")
