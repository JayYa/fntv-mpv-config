"""依赖布局（dependency layout）：每个依赖在安装包里的位置、入口文件和托管目录，外加基础配置"""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .manifest import DEFAULTS_CONF, PORTABLE_CONFIG

# 不属于任何依赖、客户端也离不开的基础配置文件（相对安装包根目录）
BASE_REQUIRED_PATHS = (f"{PORTABLE_CONFIG}/mpv.conf", f"{PORTABLE_CONFIG}/{DEFAULTS_CONF}")


class LayoutError(Exception):
    """package_cfg.json 里的依赖布局不合法"""


# custom_config 下基础配置所在的子目录；其余子目录按依赖名挂靠
BASE_CONFIG_DIR = "base"

# 一个要装进 portable_config 的配置文件：(源文件, 相对 portable_config 的目标路径)
ConfigFile = Tuple[Path, str]


@dataclass(frozen=True)
class Placement:
    """一个依赖在安装包里的位置；除 custom_config 的目标外，路径都相对安装包根目录"""
    name: str
    install_to: Optional[str]
    install_rules: Tuple[Dict[str, Any], ...]
    excludes: Tuple[str, ...]
    entry: Optional[str]
    managed_dir: Optional[str]
    custom_config: Tuple[ConfigFile, ...] = ()


@dataclass(frozen=True)
class DependencyLayout:
    placements: Mapping[str, Placement]
    base_config: Tuple[ConfigFile, ...] = ()

    @property
    def required_paths(self) -> List[str]:
        """契约测试要求安装包里有的文件（相对安装包根目录）：每个依赖的入口文件和基础配置"""
        entries = [p.entry for p in self.placements.values() if p.entry is not None]
        return entries + list(BASE_REQUIRED_PATHS)

    @property
    def managed_dirs(self) -> List[str]:
        """清单的 managedDirs：客户端整体替换的目录（相对 portable_config）"""
        prefix = PORTABLE_CONFIG + "/"
        return [p.managed_dir[len(prefix):] for p in self.placements.values()
                if p.managed_dir is not None]


def load_layout(dependencies: Mapping[str, Mapping[str, Any]], custom_config_dir: Path) -> DependencyLayout:
    """
    从 package_cfg.json 的 dependencies 读出依赖布局；启用与否都算

    custom_config_dir/base 下的文件是基础配置，custom_config_dir/<依赖名> 下的跟着该依赖装，
    都按相对路径装进 portable_config。

    Raises:
        LayoutError: 有依赖的布局不合法，或两份配置要装到同一个路径
    """
    custom_config_dir = Path(custom_config_dir)
    if BASE_CONFIG_DIR in dependencies:
        raise LayoutError(f"依赖不能叫 {BASE_CONFIG_DIR}：custom_config/{BASE_CONFIG_DIR} 是基础配置")
    base_config = _config_files(custom_config_dir / BASE_CONFIG_DIR)
    owners = {dest: f"custom_config/{BASE_CONFIG_DIR}" for _src, dest in base_config}
    placements = {}
    for name, config in dependencies.items():
        custom_config = _config_files(custom_config_dir / name)
        for _src, dest in custom_config:
            if dest in owners:
                raise LayoutError(f"{owners[dest]} 和 custom_config/{name} 都要装 "
                                  f"{PORTABLE_CONFIG}/{dest}")
            owners[dest] = f"custom_config/{name}"
        placements[name] = _placement(name, config, custom_config)
    return DependencyLayout(placements, base_config)


def _config_files(config_dir: Path) -> Tuple[ConfigFile, ...]:
    if not config_dir.is_dir():
        return ()
    return tuple((path, path.relative_to(config_dir).as_posix())
                 for path in sorted(config_dir.rglob("*")) if path.is_file())


def _placement(name: str, config: Mapping[str, Any],
               custom_config: Tuple[ConfigFile, ...]) -> Placement:
    install_to = config.get("install_to")
    rules = config.get("custom_install_rules")
    if (install_to is None) == (rules is None):
        raise LayoutError(f"依赖 {name} 必须且只能写 install_to 和 custom_install_rules 其中之一")
    if rules is not None and "exclude_files" in config:
        raise LayoutError(f"依赖 {name} 用 custom_install_rules 安装，exclude_files 不会生效，"
                          "请写进规则的 exclude")
    if install_to is not None:
        install_to = _archive_path(name, "install_to", install_to)
    for rule in rules or ():
        _archive_path(name, "custom_install_rules 的 to", rule.get("to", ""))

    entry = config.get("entry")
    if entry is not None:
        entry = _archive_path(name, "entry", entry)
    managed_dir = config.get("managed_dir")
    if managed_dir is not None:
        managed_dir = _archive_path(name, "managed_dir", managed_dir)
        if not managed_dir.startswith(PORTABLE_CONFIG + "/"):
            raise LayoutError(f"依赖 {name} 的 managed_dir 必须在 {PORTABLE_CONFIG}/ 下: {managed_dir}")
        if entry is None or not entry.startswith(managed_dir + "/"):
            raise LayoutError(f"依赖 {name} 的 managed_dir {managed_dir} 必须包含它的 entry")
    return Placement(name=name, install_to=install_to, install_rules=tuple(rules or ()),
                     excludes=tuple(config.get("exclude_files", ())),
                     entry=entry, managed_dir=managed_dir, custom_config=custom_config)


def _archive_path(name: str, field: str, value: str) -> str:
    """校验相对安装包根目录的路径，返回去掉多余 ./ 和结尾 / 的正斜杠形式"""
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise LayoutError(f"依赖 {name} 的 {field} 必须是安装包内的相对路径: {value!r}")
    return str(path)
