import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, List, Mapping, NamedTuple, Optional, Tuple

from .manifest import DEFAULTS_CONF, PORTABLE_CONFIG

BASE_REQUIRED_PATHS = (f"{PORTABLE_CONFIG}/mpv.conf", f"{PORTABLE_CONFIG}/{DEFAULTS_CONF}")

LAYOUT_KEYS = frozenset({"install_to", "custom_install_rules", "exclude_files", "entry", "managed_dir"})


class LayoutError(Exception):
    """package_cfg.json 里的依赖布局不合法"""


BASE_CONFIG_DIR = "base"

class ConfigFile(NamedTuple):
    source: Path
    portable_config_path: str


@dataclass(frozen=True)
class InstallRule:
    content_path: str
    project_path: str
    filters: Tuple[str, ...]
    excludes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class Placement:
    name: str
    install_rules: Tuple[InstallRule, ...]
    entry: Optional[str]
    managed_dir: Optional[str]
    custom_config: Tuple[ConfigFile, ...] = ()


@dataclass(frozen=True)
class DependencyLayout:
    placements: Mapping[str, Placement]
    base_config: Tuple[ConfigFile, ...] = ()

    @property
    def required_paths(self) -> List[str]:
        entries = [p.entry for p in self.placements.values() if p.entry is not None]
        return entries + list(BASE_REQUIRED_PATHS)

    @property
    def manifest_managed_dirs(self) -> List[str]:
        prefix = PORTABLE_CONFIG + "/"
        return [p.managed_dir[len(prefix):] for p in self.placements.values()
                if p.managed_dir is not None]


def load_layout(dependencies: Mapping[str, Mapping[str, Any]], custom_config_dir: Path) -> DependencyLayout:
    """
    从 package_cfg.json 的 dependencies 读出依赖布局；只看安装相关的字段，其它字段由打包配置校验

    custom_config_dir/base 下的文件是基础配置，custom_config_dir/<依赖名> 下的跟着该依赖装，
    都按相对路径装进 portable_config。

    Raises:
        LayoutError: 有依赖的布局不合法，或两份配置要装到同一个路径
    """
    custom_config_dir = Path(custom_config_dir)
    if BASE_CONFIG_DIR in dependencies:
        raise LayoutError(f"依赖不能叫 {BASE_CONFIG_DIR}：custom_config/{BASE_CONFIG_DIR} 是基础配置")
    base_config = _config_files(custom_config_dir / BASE_CONFIG_DIR)
    owners = {f.portable_config_path: f"custom_config/{BASE_CONFIG_DIR}" for f in base_config}
    placements = {}
    for name, config in dependencies.items():
        custom_config = _config_files(custom_config_dir / name)
        for f in custom_config:
            if f.portable_config_path in owners:
                raise LayoutError(f"{owners[f.portable_config_path]} 和 custom_config/{name} 都要装 "
                                  f"{PORTABLE_CONFIG}/{f.portable_config_path}")
            owners[f.portable_config_path] = f"custom_config/{name}"
        placements[name] = _placement(name, config, custom_config)
    return DependencyLayout(placements, base_config)


def _config_files(config_dir: Path) -> Tuple[ConfigFile, ...]:
    if not config_dir.is_dir():
        return ()
    return tuple(ConfigFile(path, path.relative_to(config_dir).as_posix())
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
        install_rules = (InstallRule(
            content_path=".",
            project_path=_archive_path(name, "install_to", install_to),
            filters=_ALL_FILES,
            excludes=_patterns(name, "exclude_files", config.get("exclude_files", [])),
        ),)
    else:
        if not isinstance(rules, list) or not rules:
            raise LayoutError(f"依赖 {name} 的 custom_install_rules 必须是非空列表: {rules!r}")
        install_rules = tuple(_install_rule(name, rule) for rule in rules)

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
    return Placement(name=name, install_rules=install_rules,
                     entry=entry, managed_dir=managed_dir, custom_config=custom_config)


_ALL_FILES = ("**/*",)
_RULE_KEYS = {"from", "to", "filter", "exclude"}


def _install_rule(name: str, rule: Any) -> InstallRule:
    if not isinstance(rule, Mapping):
        raise LayoutError(f"依赖 {name} 的安装规则必须是对象: {rule!r}")
    unknown = set(rule) - _RULE_KEYS
    if unknown:
        raise LayoutError(f"依赖 {name} 的安装规则有不认识的字段 {sorted(unknown)}，"
                          f"只能写 {sorted(_RULE_KEYS)}")
    filters = _patterns(name, "安装规则的 filter", rule.get("filter", list(_ALL_FILES)))
    if not filters:
        raise LayoutError(f"依赖 {name} 的安装规则的 filter 不能为空")
    return InstallRule(
        content_path=_relative_path(name, "安装规则的 from", rule.get("from", ""), "内容目录内"),
        project_path=_archive_path(name, "安装规则的 to", rule.get("to", "")),
        filters=filters,
        excludes=_patterns(name, "安装规则的 exclude", rule.get("exclude", [])),
    )


def _patterns(name: str, field: str, value: Any) -> Tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(p, str) and p for p in value):
        raise LayoutError(f"依赖 {name} 的 {field} 必须是非空字符串的列表: {value!r}")
    patterns = tuple(p.replace("\\", "/") for p in value)
    for p in patterns:
        if p.startswith("!") or p.endswith("/") or p.startswith("/"):
            raise LayoutError(f"依赖 {name} 的 {field} 不支持以 ! 或 / 开头、以 / 结尾的模式: {p!r}")
        try:
            pattern_matcher(p)
        except re.error as e:
            raise LayoutError(f"依赖 {name} 的 {field} 有写错的模式 {p!r}: {e}") from e
    return patterns


def _archive_path(name: str, field: str, value: str) -> str:
    return _relative_path(name, field, value, "安装包内")


def _relative_path(name: str, field: str, value: str, inside: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise LayoutError(f"依赖 {name} 的 {field} 必须是{inside}的相对路径: {value!r}")
    return str(path)


def pattern_matcher(pattern: str) -> Callable[[str], bool]:
    """
    把安装规则的一个模式变成判断函数，参数是相对规则 from 的 / 分隔路径。

    不含 / 的模式比文件名；含 / 的比整条路径，* ? [...] 不跨 /，** 匹配任意层目录（含零层）。
    """
    if "/" not in pattern:
        regex = re.compile(_segment_regex(pattern))
        return lambda rel: regex.fullmatch(rel.rsplit("/", 1)[-1]) is not None
    parts = pattern.split("/")
    pieces = []
    for i, part in enumerate(parts):
        last = i == len(parts) - 1
        if part == "**":
            pieces.append(".+" if last else "(?:[^/]+/)*")
        else:
            pieces.append(_segment_regex(part) + ("" if last else "/"))
    regex = re.compile("".join(pieces))
    return lambda rel: regex.fullmatch(rel) is not None


def _segment_regex(segment: str) -> str:
    out = []
    i = 0
    while i < len(segment):
        c = segment[i]
        end = _closing_bracket(segment, i) if c == "[" else None
        if c == "*":
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif end is not None:
            body = segment[i + 1:end]
            negate = body.startswith("!")
            body = body[1:] if negate else body
            out.append("[" + ("^" if negate else "") + body.replace("\\", "\\\\").replace("[", "\\[") + "]")
            i = end
        else:
            out.append(re.escape(c))
        i += 1
    return "".join(out)


def _closing_bracket(segment: str, open_at: int) -> Optional[int]:
    first_member = open_at + 2 if segment.startswith("!", open_at + 1) else open_at + 1
    first_member_is_a_bracket = segment.startswith("]", first_member)
    end = segment.find("]", first_member + first_member_is_a_bracket)
    return None if end == -1 else end
