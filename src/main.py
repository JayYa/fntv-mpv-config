"""
主程序模块
协调各个模块的工作，提供命令行界面
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .config_manager import ConfigManager, ConfigError
from .download_manager import DownloadManager, DownloadError
from .extract_manager import ExtractManager, ExtractError
from .install_manager import InstallManager, InstallError, validate_package_timestamp
from .log_manager import LogManager
from .manifest import (archive_version_for, build_manifest, check_archive, load_history,
                       write_manifest)

# 提交在仓库里的历史哈希
DEFAULT_HISTORY_PATH = Path(__file__).parent.parent / "manifest-history.json"


class MPVConfigManager:
    """MPV配置管理器主类"""
    
    def __init__(self, config_path: str = "package_cfg.json", log_level: str = "INFO",
                 output_dir: Optional[str] = None):
        """
        初始化MPV配置管理器

        Args:
            config_path: 配置文件路径
            log_level: 日志级别
            output_dir: 输出目录覆盖值，None 时依次取环境变量 FNTV_MPV_OUTPUT_DIR 和配置文件
        """
        # 初始化日志
        self.log_manager = LogManager(log_level)
        self.logger = self.log_manager.get_logger(__name__)

        # 初始化配置管理器
        self.config_manager = ConfigManager(config_path, output_dir)
        
        # 其他管理器将在需要时初始化
        self.download_manager = None
        self.extract_manager = None
        self.install_manager = None
    
    def run(self, dependencies: Optional[List[str]] = None, 
            skip_download: bool = False, 
            skip_install: bool = False,
            create_package: bool = True,
            cleanup: bool = True,
            package_timestamp: Optional[str] = None,
            history_path: Optional[str] = None,
            previous_manifest_path: Optional[str] = None) -> bool:
        """
        运行主流程
        
        Args:
            dependencies: 要处理的依赖项名称列表，None表示处理所有启用的依赖项
            skip_download: 跳过下载步骤
            skip_install: 跳过安装步骤
            create_package: 是否创建安装包
            cleanup: 是否清理临时文件
            package_timestamp: 安装包资产名的时间戳（yyyyMMdd_HHmmss），None 时用本机当前时间
            history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
            previous_manifest_path: 上一版 Release 的 fntv-manifest.json，None 时只用历史哈希

        Returns:
            是否成功
        """
        try:
            self.logger.info("开始MPV配置管理流程")
            
            # 加载配置
            config = self.config_manager.load_config()
            self.logger.info(f"配置加载完成: {config['name']} v{config['version']}")
            
            # 初始化管理器
            self._initialize_managers()
            
            # 获取要处理的依赖项
            target_dependencies = self._get_target_dependencies(dependencies)
            self.logger.info(f"将处理以下依赖项: {list(target_dependencies.keys())}")
            
            # 处理每个依赖项
            extracted_paths = {}
            for dep_name, dep_config in target_dependencies.items():
                try:
                    if not skip_download and self.download_manager and self.extract_manager:
                        # 下载（或处理本地文件/文件夹）
                        downloaded_file = self.download_manager.download_dependency(dep_name, dep_config)
                        
                        # 检查是否为已解压的文件夹（文件名以_extracted结尾）
                        if downloaded_file.name.endswith('_extracted') and downloaded_file.is_dir():
                            # 本地文件夹，直接使用，跳过解压
                            self.logger.info(f"{dep_name} 使用本地文件夹，跳过解压")
                            content_path = downloaded_file
                        else:
                            # 压缩包文件，需要解压
                            extracted_path = self.extract_manager.extract_archive(downloaded_file)
                            content_path = self.extract_manager.find_extracted_content(extracted_path)
                        
                        extracted_paths[dep_name] = content_path
                    elif skip_download:
                        # 如果跳过下载，尝试在temp目录中查找已解压的内容
                        temp_dir = self.config_manager.get_temp_dir()
                        possible_paths = [
                            temp_dir / f"{dep_name}_extracted",
                            temp_dir / dep_name,
                            temp_dir / f"extracted_{dep_name}",
                            Path("local_packages") / dep_name  # 也检查 local_packages 目录
                        ]
                        for path in possible_paths:
                            if path.exists():
                                extracted_paths[dep_name] = path
                                self.logger.info(f"找到 {dep_name} 的解压内容: {path}")
                                break
                        else:
                            self.logger.warning(f"跳过下载模式下未找到 {dep_name} 的解压内容，将仅安装自定义配置")
                    
                    if not skip_install and self.install_manager:
                        # 安装（如果没有解压内容，仅安装自定义配置）
                        content_path = extracted_paths.get(dep_name, None)
                        self.install_manager.install_dependency(dep_name, dep_config, content_path)
                
                except Exception as e:
                    self.logger.error(f"处理依赖项 {dep_name} 失败: {e}")
                    if not self._should_continue_on_error():
                        return False
            
            # 生成清单、创建安装包，然后对安装包跑契约测试
            if create_package and not skip_install and self.install_manager:
                if package_timestamp is None:
                    package_timestamp = self.install_manager._get_timestamp()
                archive_version = archive_version_for(package_timestamp)
                history = load_history(Path(history_path) if history_path else DEFAULT_HISTORY_PATH)
                previous_manifest = None
                if previous_manifest_path:
                    with open(previous_manifest_path, 'r', encoding='utf-8') as f:
                        previous_manifest = json.load(f)
                    self.logger.info(
                        f"并入上一版清单: {previous_manifest.get('archiveVersion', previous_manifest_path)}"
                    )
                manifest = build_manifest(
                    self.install_manager.portable_config_dir,
                    archive_version,
                    self._get_components(),
                    history=history,
                    previous_manifest=previous_manifest,
                )
                write_manifest(self.install_manager.output_dir, manifest)
                self.logger.info(f"清单已生成: {archive_version}，{len(manifest['files'])} 个文件")

                package_path = self.install_manager.create_package(package_timestamp)
                self.logger.info(f"安装包已创建: {package_path}")

                errors = check_archive(package_path, archive_version=archive_version,
                                       history=history, previous_manifest=previous_manifest)
                if errors:
                    for error in errors:
                        self.logger.error(f"契约测试失败: {error}")
                    return False
                self.logger.info("契约测试通过")

                # Release 单独上传的清单资产：放在 zip 旁边，路径与项目名子目录无关
                asset_path = write_manifest(package_path.parent, manifest)
                self.logger.info(f"清单资产已写入: {asset_path}")
            
            # 清理临时文件
            if cleanup:
                self._cleanup()
            
            self.logger.info("MPV配置管理流程完成")
            return True
            
        except Exception as e:
            self.logger.error(f"运行失败: {e}")
            return False
    
    def _initialize_managers(self):
        """初始化各个管理器"""
        temp_dir = self.config_manager.get_temp_dir()
        output_dir = self.config_manager.get_output_dir()
        custom_config_dir = self.config_manager.get_custom_config_dir()
        
        # 获取代理配置
        proxy_url = self.config_manager.get_github_proxy()
        enable_proxy = self.config_manager.is_proxy_enabled()
        
        # 获取项目名称用于创建子目录
        project_name = self.config_manager.get_project_name()
        
        self.download_manager = DownloadManager(temp_dir, proxy_url, enable_proxy)
        self.extract_manager = ExtractManager(temp_dir)
        self.install_manager = InstallManager(output_dir, custom_config_dir, project_name)
    
    def _get_target_dependencies(self, dependencies: Optional[List[str]]) -> dict:
        """
        获取目标依赖项
        
        Args:
            dependencies: 指定的依赖项列表
            
        Returns:
            目标依赖项字典
        """
        all_dependencies = self.config_manager.get_enabled_dependencies()
        
        if dependencies is None:
            return all_dependencies
        
        target_dependencies = {}
        for dep_name in dependencies:
            if dep_name in all_dependencies:
                target_dependencies[dep_name] = all_dependencies[dep_name]
            else:
                self.logger.warning(f"依赖项 {dep_name} 不存在或未启用")
        
        return target_dependencies
    
    def _get_components(self) -> dict:
        """清单的 components：已启用的依赖项名 -> package_cfg.json 里的版本"""
        return {
            name: str(dep.get('version', ''))
            for name, dep in self.config_manager.get_enabled_dependencies().items()
        }

    def _should_continue_on_error(self) -> bool:
        """是否在错误时继续执行"""
        # 可以从配置文件读取，这里默认返回False
        return False
    
    def _cleanup(self):
        """清理临时文件"""
        try:
            if self.download_manager:
                self.download_manager.cleanup()
            if self.extract_manager:
                # extract_manager的清理在install完成后自动进行
                pass
        except Exception as e:
            self.logger.warning(f"清理失败: {e}")
    
    def list_dependencies(self):
        """列出所有依赖项"""
        try:
            dependencies = self.config_manager.get_enabled_dependencies()
            
            self.logger.info("可用的依赖项:")
            for name, config in dependencies.items():
                status = "启用" if config.get('enabled', True) else "禁用"
                self.logger.info(f"  - {name}: {config['name']} {config['version']} ({status})")
                
        except Exception as e:
            self.logger.error(f"列出依赖项失败: {e}")
    
    def enable_dependency(self, name: str):
        """启用依赖项"""
        try:
            config = self.config_manager.get_config()
            if name in config['dependencies']:
                config['dependencies'][name]['enabled'] = True
                self.config_manager.save_config(config)
                self.logger.info(f"已启用依赖项: {name}")
            else:
                self.logger.error(f"依赖项不存在: {name}")
        except Exception as e:
            self.logger.error(f"启用依赖项失败: {e}")
    
    def disable_dependency(self, name: str):
        """禁用依赖项"""
        try:
            config = self.config_manager.get_config()
            if name in config['dependencies']:
                config['dependencies'][name]['enabled'] = False
                self.config_manager.save_config(config)
                self.logger.info(f"已禁用依赖项: {name}")
            else:
                self.logger.error(f"依赖项不存在: {name}")
        except Exception as e:
            self.logger.error(f"禁用依赖项失败: {e}")
    
    def clean_directories(self, clean_temp: bool = True, clean_output: bool = False):
        """
        清理下载和构建目录
        
        Args:
            clean_temp: 是否清理临时目录（下载的文件和解压的内容）
            clean_output: 是否清理输出目录（构建的安装包）
        """
        import shutil
        
        try:
            if clean_temp:
                temp_dir = self.config_manager.get_temp_dir()
                if temp_dir.exists():
                    self._clean_temp_directory(temp_dir)
                else:
                    self.logger.info(f"临时目录不存在: {temp_dir}")
            
            if clean_output:
                output_dir = self.config_manager.get_output_dir()
                if output_dir.exists():
                    self._clean_output_directory(output_dir)
                else:
                    self.logger.info(f"输出目录不存在: {output_dir}")
                    
        except Exception as e:
            self.logger.error(f"清理目录失败: {e}")
    
    def _clean_temp_directory(self, temp_dir: Path):
        """
        智能清理临时目录，只删除构建相关文件
        """
        import shutil
        
        # 定义要删除的文件类型和目录
        build_file_extensions = {'.7z', '.zip', '.tar', '.gz', '.bz2', '.xz', '.rar'}
        build_directory_patterns = {'extracted_', '_extracted', 'download_'}
        
        cleaned_files = 0
        cleaned_dirs = 0
        
        for item in temp_dir.iterdir():
            should_delete = False
            
            if item.is_file():
                # 删除压缩包文件
                if item.suffix.lower() in build_file_extensions:
                    should_delete = True
                # 删除临时下载文件
                elif item.name.startswith(('temp_', 'download_', 'cache_')):
                    should_delete = True
                
                if should_delete:
                    item.unlink()
                    self.logger.info(f"已删除文件: {item.name}")
                    cleaned_files += 1
                    
            elif item.is_dir():
                # 删除解压目录
                if any(pattern in item.name for pattern in build_directory_patterns):
                    should_delete = True
                # 删除以依赖项名称命名的目录（解压后的内容）
                elif self._is_dependency_directory(item.name):
                    should_delete = True
                    
                if should_delete:
                    shutil.rmtree(item)
                    self.logger.info(f"已删除目录: {item.name}")
                    cleaned_dirs += 1
        
        self.logger.info(f"临时目录清理完成: 删除了 {cleaned_files} 个文件和 {cleaned_dirs} 个目录")
    
    def _clean_output_directory(self, output_dir: Path):
        """
        智能清理输出目录，只删除构建产物
        """
        import shutil
        
        # 动态获取项目名称作为构建产物目录
        project_name = self.config_manager.get_project_name()
        build_products = {project_name}  # 主要的构建产物目录
        
        cleaned_files = 0
        cleaned_dirs = 0
        
        for item in output_dir.iterdir():
            should_delete = False
            
            if item.is_file():
                # 只删除构建生成的压缩包
                if self._is_build_generated_archive(item):
                    should_delete = True
                    
                if should_delete:
                    item.unlink()
                    self.logger.info(f"已删除文件: {item.name}")
                    cleaned_files += 1
                    
            elif item.is_dir():
                # 删除构建产物目录
                if item.name in build_products:
                    should_delete = True
                # 删除版本化的构建目录
                elif item.name.startswith(('mpv-', f'{project_name}-')):
                    should_delete = True
                    
                if should_delete:
                    shutil.rmtree(item)
                    self.logger.info(f"已删除目录: {item.name}")
                    cleaned_dirs += 1
        
        self.logger.info(f"输出目录清理完成: 删除了 {cleaned_files} 个文件和 {cleaned_dirs} 个目录")
    
    def _is_build_generated_archive(self, file_path: Path) -> bool:
        """
        检查文件是否为构建生成的压缩包
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否为构建生成的压缩包
        """
        # 只识别压缩包文件
        if file_path.suffix.lower() not in {'.zip', '.7z', '.tar', '.gz', '.bz2', '.xz'}:
            return False
        
        filename = file_path.name
        
        # 动态获取项目名称
        project_name = self.config_manager.get_project_name()
        
        # 构建生成的压缩包文件名模式
        build_patterns = [
            'mpv-package-',                    # InstallManager.create_package() 生成的文件
            f'{project_name}-',                # 项目相关的压缩包
            f'{project_name}-config-',         # 配置包
        ]
        
        # 检查是否匹配构建模式
        for pattern in build_patterns:
            if filename.startswith(pattern):
                return True
        
        # 时间戳模式检查 (YYYYMMDD_HHMMSS)
        import re
        timestamp_pattern = r'.*-\d{8}_\d{6}\.(zip|7z|tar|gz|bz2|xz)$'
        if re.match(timestamp_pattern, filename):
            return True
            
        return False
    
    def _is_dependency_directory(self, dir_name: str) -> bool:
        """
        检查目录名是否为依赖项目录
        """
        try:
            config = self.config_manager.load_config()
            dependency_names = list(config.get('dependencies', {}).keys())
            return dir_name in dependency_names
        except:
            return False


def _package_timestamp_arg(value: str) -> str:
    """argparse 类型函数：启动时就拒绝格式错误的时间戳，避免构建完才失败"""
    try:
        return validate_package_timestamp(value)
    except InstallError as e:
        raise argparse.ArgumentTypeError(str(e))


def create_cli_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="MPV播放器和插件管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python -m src.main                          # 处理所有启用的依赖项
  python -m src.main --deps mpv uosc          # 只处理指定的依赖项
  python -m src.main --list                   # 列出所有依赖项
  python -m src.main --enable uosc_danmaku    # 启用指定依赖项
  python -m src.main --disable uosc_danmaku   # 禁用指定依赖项
  python -m src.main --skip-download          # 跳过下载，直接安装
  python -m src.main --skip-install           # 只下载，不安装
  python -m src.main --skip-package           # 跳过打包步骤
  python -m src.main --clean temp             # 智能清理临时文件（压缩包、解压目录等）
  python -m src.main --clean output           # 智能清理构建产物（fntv-mpv-config目录、包文件等）
  python -m src.main --clean all              # 智能清理所有构建相关文件

注意: --clean 命令现在使用智能清理，只删除构建相关的文件，保留用户自定义内容
        """
    )
    
    # 主要操作参数
    parser.add_argument(
        '--config', '-c',
        default='package_cfg.json',
        help='配置文件路径 (默认: package_cfg.json)'
    )
    
    parser.add_argument(
        '--output-dir',
        help='输出目录，覆盖环境变量 FNTV_MPV_OUTPUT_DIR 和配置文件中的 config.output_dir'
    )

    parser.add_argument(
        '--deps', '--dependencies',
        nargs='*',
        help='要处理的依赖项名称列表'
    )
    
    # 控制选项
    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='跳过下载步骤'
    )
    
    parser.add_argument(
        '--skip-install',
        action='store_true',
        help='跳过安装步骤'
    )
    
    parser.add_argument(
        '--skip-package',
        action='store_true',
        help='跳过打包步骤'
    )
    
    parser.add_argument(
        '--package-timestamp',
        type=_package_timestamp_arg,
        help='安装包文件名 mpv-package-<时间戳>.zip 中的时间戳，格式 yyyyMMdd_HHmmss；'
             'CI 传入 Release tag 的时间，不传则用本机当前时间'
    )

    parser.add_argument(
        '--manifest-history',
        help='历史哈希文件（默认: 仓库根目录的 manifest-history.json）'
    )

    parser.add_argument(
        '--previous-manifest',
        help='上一版 Release 的 fntv-manifest.json；它的 knownHashes 和 obsolete 并入本次清单'
    )

    parser.add_argument(
        '--skip-cleanup',
        action='store_true',
        help='不清理临时文件'
    )
    
    # 管理操作
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出所有依赖项'
    )
    
    parser.add_argument(
        '--enable',
        help='启用指定的依赖项'
    )
    
    parser.add_argument(
        '--disable',
        help='禁用指定的依赖项'
    )
    
    parser.add_argument(
        '--clean',
        choices=['temp', 'output', 'all'],
        help='智能清理目录 (temp: 构建临时文件, output: 构建产物, all: 全部构建文件)'
    )
    
    # 日志选项
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )
    
    return parser


def main():
    """主函数"""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    try:
        # 创建管理器实例
        manager = MPVConfigManager(args.config, args.log_level, args.output_dir)
        
        # 执行相应的操作
        if args.list:
            manager.list_dependencies()
        elif args.enable:
            manager.enable_dependency(args.enable)
        elif args.disable:
            manager.disable_dependency(args.disable)
        elif args.clean:
            # 处理清理命令
            if args.clean == 'temp':
                manager.clean_directories(clean_temp=True, clean_output=False)
            elif args.clean == 'output':
                manager.clean_directories(clean_temp=False, clean_output=True)
            elif args.clean == 'all':
                manager.clean_directories(clean_temp=True, clean_output=True)
        else:
            # 执行主流程
            success = manager.run(
                dependencies=args.deps,
                skip_download=args.skip_download,
                skip_install=args.skip_install,
                create_package=not (args.skip_package),
                cleanup=not args.skip_cleanup,
                package_timestamp=args.package_timestamp,
                history_path=args.manifest_history,
                previous_manifest_path=args.previous_manifest
            )
            
            if not success:
                sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"程序运行失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
