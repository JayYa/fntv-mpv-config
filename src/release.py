import json
import os
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import List, Mapping, NamedTuple, Optional, Tuple

RELEASE_NOTES_TEMPLATE = Path(__file__).parent.parent / "templates" / "release-notes.md"
RELEASE_NOTES_NAME = "release-notes.md"

TREE_DEPTH = 3

ICU_ROOT_PUNCTUATION_ORDER = " _-,;:!?.'\"()[]{}@*/\\&#%`^+<=>|~$"
FILE_ATTRIBUTE_HIDDEN = 0x2

DIR_COMMENTS = {
    "portable_config": "便携式配置目录",
    "mpv": "MPV配置目录",
    "scripts": "插件脚本目录",
    "script-opts": "插件配置目录",
    "fonts": "字体文件目录",
    "cache": "缓存目录",
    "uosc": "uosc插件",
    "uosc_danmaku": "弹幕插件",
    "elements": "UI元素",
    "lib": "库文件",
    "bin": "二进制文件",
    "intl": "国际化文件",
}

FILE_COMMENTS = {
    "mpv.exe": "MPV播放器主程序",
    "mpv.com": "MPV命令行版本",
    "input.conf": "快捷键配置",
    "mpv.conf": "MPV主配置",
    "uosc.conf": "uosc插件配置",
    "uosc_danmaku.conf": "弹幕插件配置",
    "fonts.conf": "字体配置",
    "d3dcompiler_43.dll": "依赖库",
    "main.lua": "主脚本",
}

SUFFIX_COMMENTS = {
    ".lua": "Lua脚本",
    ".otf": "字体文件",
    ".ttf": "字体文件",
    ".dll": "依赖库",
    ".exe": "可执行文件",
}


class Dependency(NamedTuple):
    name: str
    version: str


@dataclass(frozen=True)
class PackageArchive:
    path: Path
    manifest_asset_path: Path
    archive_version: str
    timestamp: str


@dataclass(frozen=True)
class BuildResult:
    """
    一次构建的结果

    不打包（--skip-package / --skip-install）时 package 是 None。
    """
    output_dir: Path
    project_dir: Path
    processed_dependencies: Tuple[Dependency, ...] = ()
    package: Optional[PackageArchive] = None


def write_build_result(result: BuildResult, path: Path,
                       env: Optional[Mapping[str, str]] = None) -> Path:
    """
    写出构建结果 JSON，并在同一目录写出发布说明

    Args:
        result: 打过包的构建结果
        path: 结果 JSON 的路径
        env: 读取 GitHub 环境变量的映射，None 时用 os.environ

    Returns:
        结果 JSON 的路径

    Raises:
        ValueError: 构建没有产出安装包
    """
    package = result.package
    if package is None:
        raise ValueError("构建没有产出安装包，无法写出构建结果")
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    notes_path = path.parent / RELEASE_NOTES_NAME
    notes_path.write_text(render_release_notes(result, env), encoding="utf-8", newline="\n")
    data = {
        "archiveVersion": package.archive_version,
        "timestamp": package.timestamp,
        "outputDir": str(result.output_dir),
        "packagePath": str(package.path),
        "manifestAssetPath": str(package.manifest_asset_path),
        "releaseNotesPath": str(notes_path),
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                    newline="\n")
    return path


def render_release_notes(result: BuildResult, env: Optional[Mapping[str, str]] = None) -> str:
    """
    生成 Release 说明（Markdown）

    提交、分支和链接来自 GitHub Actions 的标准环境变量；缺少时省略对应的行。

    Raises:
        ValueError: 构建没有产出安装包
    """
    package = result.package
    if package is None:
        raise ValueError("构建没有产出安装包，无法生成 Release 说明")
    env = os.environ if env is None else env
    sha = env.get("GITHUB_SHA")
    branch = env.get("GITHUB_REF_NAME")
    server = env.get("GITHUB_SERVER_URL")
    repo = env.get("GITHUB_REPOSITORY")

    build_info = ""
    if branch:
        build_info += f"🔧 构建分支: {branch}\n"
    if sha:
        build_info += f"📝 提交ID: {sha}\n"

    links = ""
    if server and repo:
        base = f"{server}/{repo}"
        links = "\n## 🔗 相关链接\n"
        if sha:
            links += f"- 📖 [使用文档]({base}/blob/{sha}/README.md)\n"
        links += f"- 🐛 [问题反馈]({base}/issues)\n"
        links += f"- 🔄 [配置更新]({base}/releases)\n"

    dependencies = "\n".join(
        f"- 🔧 {name} ({version})" if version else f"- 🔧 {name}"
        for name, version in result.processed_dependencies
    )

    template = Template(RELEASE_NOTES_TEMPLATE.read_text(encoding="utf-8"))
    return template.substitute(
        timestamp=package.timestamp,
        build_info=build_info,
        dependencies=dependencies,
        package_name=Path(package.path).name,
        directory_tree=_directory_tree(Path(result.project_dir)),
        links=links,
    )


def _directory_tree(root: Path) -> str:
    lines = [f"{root.name}/"]
    _tree_lines(root, "", 0, lines)
    return "\n".join(lines)


def _tree_lines(directory: Path, prefix: str, depth: int, lines: List[str]) -> None:
    if depth >= TREE_DEPTH:
        return
    items = sorted((p for p in directory.iterdir() if not _is_hidden(p)),
                   key=lambda p: _icu_collation_key(p.name))
    for i, item in enumerate(items):
        last = i == len(items) - 1
        branch = prefix + ("└──" if last else "├──")
        if item.is_dir():
            lines.append(_with_comment(f"{branch} {item.name}/", DIR_COMMENTS.get(item.name.lower())))
            _tree_lines(item, prefix + ("    " if last else "│   "), depth + 1, lines)
        else:
            comment = FILE_COMMENTS.get(item.name.lower()) or SUFFIX_COMMENTS.get(item.suffix.lower())
            lines.append(_with_comment(f"{branch} {item.name}", comment))


def _icu_collation_key(name: str) -> List[Tuple[int, object]]:
    key = []
    for ch in name.lower():
        rank = ICU_ROOT_PUNCTUATION_ORDER.find(ch)
        if rank >= 0:
            key.append((0, rank))
        elif ch.isdigit():
            key.append((1, ch))
        else:
            key.append((2, ch))
    return key


def _is_hidden(path: Path) -> bool:
    return bool(getattr(path.stat(), "st_file_attributes", 0) & FILE_ATTRIBUTE_HIDDEN)


def _with_comment(text: str, comment: Optional[str]) -> str:
    return f"{text} # {comment}" if comment else text
