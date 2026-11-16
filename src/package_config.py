"""
打包配置：把 package_cfg.json 一次读成值，加载时校验完所有字段
"""
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from .dependency_layout import LAYOUT_KEYS, DependencyLayout, LayoutError, load_layout

OUTPUT_DIR_ENV = "FNTV_MPV_OUTPUT_DIR"


class ConfigError(Exception):
    """package_cfg.json 不存在或不合法"""


@dataclass(frozen=True)
class GithubRelease:
    owner: str
    repo: str
    version: str
    filename_pattern: str
    format: str


@dataclass(frozen=True)
class LocalDir:
    path: Path


@dataclass(frozen=True)
class LocalArchive:
    path: Path


Source = Union[GithubRelease, LocalDir, LocalArchive]


@dataclass(frozen=True)
class DependencySpec:
    display_name: str
    version: str
    source: Source
    enabled: bool = True


@dataclass(frozen=True)
class PackageConfig:
    project_name: str
    output_dir: Path
    temp_dir: Path
    github_proxy: str
    enable_proxy: bool
    dependencies: Mapping[str, DependencySpec]
    archive_layout: DependencyLayout

    @property
    def enabled_dependencies(self) -> Mapping[str, DependencySpec]:
        return {name: dep for name, dep in self.dependencies.items() if dep.enabled}

    @property
    def disabled_dependencies(self) -> Mapping[str, DependencySpec]:
        return {name: dep for name, dep in self.dependencies.items() if not dep.enabled}


def load_package_config(path: Union[str, Path], output_dir: Optional[str] = None) -> PackageConfig:
    """
    读 package_cfg.json；配置里的相对路径按它所在的目录解析

    输出目录的优先级：output_dir 参数 > 环境变量 FNTV_MPV_OUTPUT_DIR > config.output_dir；
    前两者是命令行给的，按当前工作目录解析。

    Raises:
        ConfigError: 文件不存在、不是 JSON，或有字段缺失、多余、写错
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"配置文件不存在: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件 {path} 不是合法的 JSON: {e}") from e
    base_dir = path.resolve().parent

    if not isinstance(data, Mapping):
        raise ConfigError(f"配置文件 {path} 必须是 JSON 对象")
    _reject_unknown_keys("配置文件", data, _TOP_LEVEL_KEYS)
    project_name = _text("配置文件", data, "name")
    settings = _mapping("配置文件", data, "config")
    _reject_unknown_keys("config", settings, _SETTINGS_KEYS)
    raw_dependencies = _mapping("配置文件", data, "dependencies")

    dependencies = {name: _dependency(name, dep, base_dir) for name, dep in raw_dependencies.items()}
    try:
        layout = load_layout(raw_dependencies, base_dir / _text("config", settings, "custom_config_dir"))
    except LayoutError as e:
        raise ConfigError(str(e)) from e
    layout = replace(layout, placements={name: placement for name, placement in layout.placements.items()
                                         if dependencies[name].enabled})
    configured_output_dir = base_dir / _text("config", settings, "output_dir")
    enable_proxy = settings.get("enable_proxy", False)
    if not isinstance(enable_proxy, bool):
        raise ConfigError(f"config 的 enable_proxy 必须是 true 或 false: {enable_proxy!r}")
    return PackageConfig(
        project_name=project_name,
        output_dir=_output_dir_override(output_dir) or configured_output_dir,
        temp_dir=base_dir / _text("config", settings, "temp_dir"),
        github_proxy=_optional_text("config", settings, "github_proxy"),
        enable_proxy=enable_proxy,
        dependencies=dependencies,
        archive_layout=layout,
    )


_TOP_LEVEL_KEYS = {"name", "version", "description", "config", "dependencies"}
_SETTINGS_KEYS = {"output_dir", "temp_dir", "custom_config_dir", "github_proxy", "enable_proxy"}


def _output_dir_override(output_dir: Optional[str]) -> Optional[Path]:
    value = output_dir or os.environ.get(OUTPUT_DIR_ENV)
    return Path(value) if value else None


def _mapping(where: str, value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    mapping = value.get(key)
    if not isinstance(mapping, Mapping):
        raise ConfigError(f"{where} 的 {key} 必须是对象: {mapping!r}")
    return mapping


_GITHUB_RELEASES = re.compile(r"https://github\.com/([^/]+)/([^/]+)/releases/?")


_GITHUB_KEYS = {"url", "filename_pattern", "format"}
_DEPENDENCY_KEYS = {"name", "version", "enabled", "local_path"} | _GITHUB_KEYS | LAYOUT_KEYS


def _dependency(name: str, dep: Any, base_dir: Path) -> DependencySpec:
    if not isinstance(dep, Mapping):
        raise ConfigError(f"依赖 {name} 必须是对象: {dep!r}")
    _reject_unknown_keys(f"依赖 {name}", dep, _DEPENDENCY_KEYS)
    enabled = dep.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"依赖 {name} 的 enabled 必须是 true 或 false: {enabled!r}")
    if ("url" in dep) == ("local_path" in dep):
        raise ConfigError(f"依赖 {name} 必须且只能写 url 和 local_path 其中之一："
                          "url 或 local_path 决定它从哪来")
    source = _local_source(name, dep, base_dir) if "local_path" in dep else _github_release(name, dep)
    return DependencySpec(display_name=_text(f"依赖 {name}", dep, "name"),
                           version=_text(f"依赖 {name}", dep, "version"), source=source,
                           enabled=enabled)


def _local_source(name: str, dep: Mapping[str, Any], base_dir: Path) -> Source:
    github_only = sorted(_GITHUB_KEYS & set(dep))
    if github_only:
        raise ConfigError(f"依赖 {name} 是本地来源，不用 {', '.join(github_only)}")
    path = base_dir / _text(f"依赖 {name}", dep, "local_path")
    if path.is_dir():
        return LocalDir(path)
    if path.is_file():
        return LocalArchive(path)
    raise ConfigError(f"依赖 {name} 的 local_path 不存在: {path}")


def _github_release(name: str, dep: Mapping[str, Any]) -> GithubRelease:
    where = f"依赖 {name}"
    url = _text(where, dep, "url")
    match = _GITHUB_RELEASES.fullmatch(url)
    if match is None:
        raise ConfigError(f"{where} 的 url 必须是 GitHub Release 页面 "
                          f"https://github.com/<owner>/<repo>/releases；本地包请写 local_path: {url}")
    owner, repo = match.groups()
    return GithubRelease(owner=owner, repo=repo, version=_text(where, dep, "version"),
                         filename_pattern=_text(where, dep, "filename_pattern"),
                         format=_text(where, dep, "format"))


def _reject_unknown_keys(where: str, value: Mapping[str, Any], allowed: set):
    unknown = set(value) - allowed
    if unknown:
        raise ConfigError(f"{where} 有不认识的字段 {sorted(unknown)}，只能写 {sorted(allowed)}")


def _text(where: str, value: Mapping[str, Any], key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text:
        raise ConfigError(f"{where} 的 {key} 必须是非空字符串: {text!r}")
    return text


def _optional_text(where: str, value: Mapping[str, Any], key: str) -> str:
    text = value.get(key, "")
    if not isinstance(text, str):
        raise ConfigError(f"{where} 的 {key} 必须是字符串: {text!r}")
    return text
