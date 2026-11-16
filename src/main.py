"""
主程序模块
协调各个模块的工作，提供命令行界面
"""
import argparse
import sys
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

from .dependency_source import DependencySource
from .install_manager import InstallManager
from .log_manager import LogManager
from .package_archive import (ContractTestFailed, KnownHashes, build_package_archive,
                              remove_package_archives, validate_package_timestamp)
from .package_config import (ConfigError, DependencySpec, GithubRelease, LocalDir, PackageConfig,
                             load_package_config)
from .release import BuildResult, Dependency, write_build_result


class MPVConfigManager:
    """MPV配置管理器主类"""

    def __init__(self, config_path: str = "package_cfg.json", log_level: str = "INFO",
                 output_dir: Optional[str] = None):
        """
        Args:
            config_path: 配置文件路径
            log_level: 日志级别
            output_dir: 输出目录覆盖值，None 时依次取环境变量 FNTV_MPV_OUTPUT_DIR 和配置文件
        """
        self.log_manager = LogManager(log_level)
        self.logger = self.log_manager.get_logger(__name__)
        self.config_path = config_path
        self.output_dir_override = output_dir

    def run(self, dependencies: Optional[List[str]] = None,
            skip_download: bool = False,
            skip_install: bool = False,
            create_package: bool = True,
            cleanup: bool = True,
            package_timestamp: Optional[str] = None,
            history_path: Optional[str] = None,
            previous_manifest_path: Optional[str] = None) -> Optional[BuildResult]:
        """
        运行主流程

        安装前先清空 project 目录，安装包里只有本次安装的文件。

        Args:
            dependencies: 要处理的依赖项名称列表，None 表示处理全部依赖
            skip_download: 离线模式，GitHub Release 依赖只用 temp 里上次下载的压缩包，没有就失败
            skip_install: 跳过安装步骤
            create_package: 是否创建安装包
            cleanup: 是否清理临时文件
            package_timestamp: 安装包资产名的时间戳（yyyyMMdd_HHmmss），None 时用当前北京时间
            history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
            previous_manifest_path: 上一版 Release 的 fntv-manifest.json，None 时只用历史哈希

        Returns:
            成功时返回构建结果，失败时返回 None
        """
        try:
            self.logger.info("开始MPV配置管理流程")

            config = self._load()
            self.logger.info(f"配置加载完成: {config.project_name}")

            source = self._dependency_source(config, offline=skip_download)
            installer = self._installer(config)

            target_dependencies = _target_dependencies(config, dependencies)
            self.logger.info(f"将处理以下依赖项: {list(target_dependencies)}")

            if not skip_install:
                installer.reset_project_dir()
                installer.install_base_config(config.archive_layout)
            for dep_name, entry in target_dependencies.items():
                try:
                    content_dir = source.fetch(dep_name, entry.source)
                    if not skip_install:
                        installer.install_dependency(config.archive_layout.placements[dep_name], content_dir)
                except Exception as e:
                    self.logger.error(f"处理依赖项 {dep_name} 失败: {e}")
                    return None

            result = BuildResult(
                output_dir=installer.base_output_dir.resolve(),
                project_dir=installer.output_dir.resolve(),
                processed_dependencies=_release_dependencies(target_dependencies),
                disabled_dependencies=_release_dependencies(config.disabled_dependencies),
            )

            if create_package and not skip_install:
                known = KnownHashes.load(history_path, previous_manifest_path)
                if previous_manifest_path:
                    self.logger.info(f"并入上一版清单: {previous_manifest_path}")
                components = {name: entry.version for name, entry in config.enabled_dependencies.items()}
                try:
                    package = build_package_archive(installer.output_dir, components, known,
                                                    config.archive_layout, timestamp=package_timestamp)
                except ContractTestFailed as e:
                    for error in e.errors:
                        self.logger.error(f"契约测试失败: {error}")
                    return None
                self.logger.info(f"安装包已创建并通过契约测试: {package.path}（{package.archive_version}）")
                result = replace(result, package=package)

            if cleanup:
                try:
                    source.clean()
                except OSError as e:
                    self.logger.warning(f"清理临时目录失败: {e}")

            self.logger.info("MPV配置管理流程完成")
            return result

        except Exception as e:
            self.logger.error(f"运行失败: {e}")
            return None

    def list_dependencies(self):
        """
        列出所有依赖项和它们的来源

        Raises:
            ConfigError: 配置文件不合法
        """
        config = self._load()
        self.logger.info("依赖项:")
        for name, entry in config.dependencies.items():
            disabled_note = "" if entry.enabled else "，已停用"
            self.logger.info(f"  - {name}: {entry.display_name} {entry.version}（{_describe(entry)}{disabled_note}）")

    def clean_directories(self, clean_temp: bool = True, clean_output: bool = False):
        """
        清理下载和构建目录

        Args:
            clean_temp: 删掉整个临时目录
            clean_output: 删掉 project 目录、输出目录里的安装包和清单资产；输出目录里的其它东西不动

        Raises:
            ConfigError: 配置文件不合法
            OSError: 删除失败
        """
        config = self._load()
        if clean_temp:
            self._dependency_source(config).clean()

        if clean_output:
            if not config.output_dir.exists():
                self.logger.info(f"输出目录不存在: {config.output_dir}")
                return
            self._installer(config).remove_project_dir()
            for path in remove_package_archives(config.output_dir):
                self.logger.info(f"已删除文件: {path.name}")

    def _load(self) -> PackageConfig:
        return load_package_config(self.config_path, self.output_dir_override)

    @staticmethod
    def _dependency_source(config: PackageConfig, offline: bool = False) -> DependencySource:
        return DependencySource(config.temp_dir, proxy_url=config.github_proxy,
                                enable_proxy=config.enable_proxy, offline=offline)

    @staticmethod
    def _installer(config: PackageConfig) -> InstallManager:
        return InstallManager(config.output_dir, config.project_name)


def _target_dependencies(config: PackageConfig,
                         names: Optional[List[str]]) -> Dict[str, DependencySpec]:
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
        raise ConfigError("；".join(problems + [hint]))
    return {name: enabled[name] for name in names}


def _release_dependencies(dependencies: Mapping[str, DependencySpec]) -> Tuple[Dependency, ...]:
    return tuple(Dependency(entry.display_name, entry.version) for entry in dependencies.values())


def _describe(entry: DependencySpec) -> str:
    source = entry.source
    if isinstance(source, GithubRelease):
        return f"GitHub Release {source.owner}/{source.repo}"
    kind = "本地文件夹" if isinstance(source, LocalDir) else "本地压缩包"
    return f"{kind} {source.path}"


def _package_timestamp_arg(value: str) -> str:
    """argparse 类型函数：启动时就拒绝格式错误的时间戳，避免构建完才失败"""
    try:
        return validate_package_timestamp(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def create_cli_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="MPV播放器和插件管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python -m src.main                          # 处理全部依赖项
  python -m src.main --deps mpv uosc --skip-package  # 只处理指定的依赖项，不打包
  python -m src.main --list                   # 检查配置并列出所有依赖项
  python -m src.main --skip-download          # 离线构建，用上次 --skip-cleanup 留下的压缩包
  python -m src.main --skip-install           # 只下载，不安装
  python -m src.main --skip-package           # 跳过打包步骤
  python -m src.main --clean temp             # 删掉临时目录
  python -m src.main --clean output           # 删掉 project 目录、安装包和清单资产
  python -m src.main --clean all              # 两者都删
        """
    )

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
        help='要处理的依赖项名称列表；必须同时带 --skip-package 或 --skip-install'
    )

    parser.add_argument(
        '--skip-download',
        action='store_true',
        help='离线模式：不访问网络，GitHub Release 依赖只用临时目录里上次下载的压缩包'
             '（上次构建需带 --skip-cleanup），没有就失败；离线构建结束时同样会删掉临时目录，'
             '要连续离线构建就每次都带 --skip-cleanup'
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
             '不传则用当前北京时间'
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
        '--result-file',
        help='打包成功后把构建结果写成 JSON 到这个路径，同目录写出 release-notes.md；'
             '不能与 --skip-package / --skip-install 同用'
    )

    parser.add_argument(
        '--skip-cleanup',
        action='store_true',
        help='不清理临时文件'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='检查配置并列出所有依赖项；配置不合法时以退出码 1 结束'
    )

    parser.add_argument(
        '--clean',
        choices=['temp', 'output', 'all'],
        help='清理目录 (temp: 整个临时目录, output: project 目录、安装包和清单资产, all: 两者)'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='日志级别 (默认: INFO)'
    )

    return parser


def parse_args(parser: argparse.ArgumentParser, argv: Optional[List[str]] = None) -> argparse.Namespace:
    """解析参数，并拒绝互相矛盾的组合"""
    args = parser.parse_args(argv)
    if args.result_file and (args.skip_package or args.skip_install):
        parser.error("--result-file 需要打包，不能与 --skip-package / --skip-install 同用")
    if args.deps is not None and not (args.skip_package or args.skip_install):
        parser.error("--deps 只装一部分依赖，打出的安装包不完整；请同时带 --skip-package 或 --skip-install")
    return args


def main(argv: Optional[List[str]] = None):
    """
    命令行入口；argv 不含程序名，None 时读 sys.argv

    任何命令失败都以退出码 1 结束，参数错误以 2 结束。
    """
    parser = create_cli_parser()
    args = parse_args(parser, argv)

    try:
        manager = MPVConfigManager(args.config, args.log_level, args.output_dir)

        if args.list:
            manager.list_dependencies()
        elif args.clean:
            manager.clean_directories(clean_temp=args.clean in ('temp', 'all'),
                                      clean_output=args.clean in ('output', 'all'))
        else:
            result = manager.run(
                dependencies=args.deps,
                skip_download=args.skip_download,
                skip_install=args.skip_install,
                create_package=not args.skip_package,
                cleanup=not args.skip_cleanup,
                package_timestamp=args.package_timestamp,
                history_path=args.manifest_history,
                previous_manifest_path=args.previous_manifest
            )

            if result is None:
                sys.exit(1)
            if args.result_file:
                path = write_build_result(result, Path(args.result_file))
                print(f"构建结果已写入: {path}")

    except KeyboardInterrupt:
        print("\n操作被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"程序运行失败: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
