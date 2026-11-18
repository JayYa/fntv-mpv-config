import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from .build import BuildFailed, BuildScope, build, clean
from .log_setup import setup_logging
from .package_archive import validate_package_timestamp
from .package_config import ConfigError, DependencySpec, GithubRelease, LocalDir, PackageConfig, load_package_config
from .previous_manifest import PreviousManifest, PreviousManifestFile, PreviousRelease
from .release import write_build_result

logger = logging.getLogger(__name__)


def list_dependencies(config: PackageConfig):
    logger.info("依赖项:")
    for name, entry in config.dependencies.items():
        disabled_note = "" if entry.enabled else "，已停用"
        logger.info(f"  - {name}: {entry.display_name} {entry.version}（{_describe(entry)}{disabled_note}）")


def _describe(entry: DependencySpec) -> str:
    source = entry.source
    if isinstance(source, GithubRelease):
        return f"GitHub Release {source.repo_path}"
    kind = "本地文件夹" if isinstance(source, LocalDir) else "本地压缩包"
    return f"{kind} {source.path}"


def _scope(args: argparse.Namespace) -> BuildScope:
    if args.skip_install:
        return BuildScope.FETCH
    if args.skip_package:
        return BuildScope.INSTALL
    return BuildScope.PACKAGE


def _previous_manifest(args: argparse.Namespace) -> Optional[PreviousManifest]:
    if args.previous_release:
        return PreviousRelease(args.previous_release)
    if args.previous_manifest:
        return PreviousManifestFile(Path(args.previous_manifest))
    return None


def _package_timestamp_arg(value: str) -> str:
    """argparse 类型函数：启动时就拒绝格式错误的时间戳，避免构建完才失败"""
    try:
        return validate_package_timestamp(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


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
             '（上次构建需带 --skip-cleanup），没有、或它的来源与打包配置不一致（例如改了版本）就失败；'
             '离线构建结束时同样会删掉临时目录，'
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

    previous = parser.add_mutually_exclusive_group()
    previous.add_argument(
        '--previous-release',
        metavar='OWNER/REPO',
        help='从这个仓库最新一版 Release 下载上一版清单，它的 knownHashes 和 obsolete 并入本次清单；'
             '那版 Release 没有清单或清单不属于它时构建失败'
    )
    previous.add_argument(
        '--previous-manifest',
        help='上一版清单的本地文件；它的 knownHashes 和 obsolete 并入本次清单，读不出清单时构建失败'
    )

    parser.add_argument(
        '--result-file',
        help='打包成功后把构建结果写成 JSON 到这个路径，同目录写出 release-notes.md；'
             '不能与 --skip-package / --skip-install 同用'
    )

    parser.add_argument(
        '--skip-cleanup',
        action='store_true',
        help='不清理临时文件；构建失败时临时目录总是保留'
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
    return args


def main(argv: Optional[List[str]] = None):
    """
    命令行入口；argv 不含程序名，None 时读 sys.argv

    配置不合法、构建失败、清理失败都以退出码 1 结束，参数错误以 2 结束。
    """
    parser = create_cli_parser()
    args = parse_args(parser, argv)
    setup_logging(args.log_level)

    try:
        config = load_package_config(args.config, args.output_dir)

        if args.list:
            list_dependencies(config)
        elif args.clean:
            try:
                clean(config, temp=args.clean in ('temp', 'all'), output=args.clean in ('output', 'all'))
            except OSError as e:
                print(f"清理失败: {e}")
                sys.exit(1)
        else:
            logger.info(f"开始构建 {config.project_name}")
            result = build(
                config, _scope(args),
                dependencies=args.deps,
                offline=args.skip_download,
                keep_temp=args.skip_cleanup,
                package_timestamp=args.package_timestamp,
                history_path=Path(args.manifest_history) if args.manifest_history else None,
                previous=_previous_manifest(args),
            )
            logger.info("构建完成")
            if args.result_file:
                path = write_build_result(result, Path(args.result_file))
                print(f"构建结果已写入: {path}")

    except BuildFailed as e:
        print(f"构建失败（{len(e.errors)} 项）:")
        for error in e.errors:
            print(f"  - {error}")
        sys.exit(1)
    except ConfigError as e:
        print(f"配置错误: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n操作被用户中断")
        sys.exit(1)


if __name__ == '__main__':
    main()
