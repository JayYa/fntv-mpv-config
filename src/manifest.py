"""
MPV 归档清单 fntv-manifest.json

清单放在安装包根目录，列出 portable_config 下每个文件的 sha256 和归属（role），
客户端靠它按 conffile 方式同步用户配置。格式见 JayYa/fntv-electron#219。
"""
import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Set, Tuple

if TYPE_CHECKING:
    from .dependency_layout import DependencyLayout

MANIFEST_NAME = "fntv-manifest.json"
DEFAULT_HISTORY_PATH = Path(__file__).parent.parent / "manifest-history.json"
FORMAT_VERSION = 1
PORTABLE_CONFIG = "portable_config"
DEFAULTS_CONF = "fntv/defaults.conf"

ROLES = ("managed", "config", "seed")
ROLES_KEPT_BY_CLIENT = ("config", "seed")

PROVIDES = {
    "smart-skip.origin-from-play-url": 1,
}


class ManifestError(Exception):
    def __init__(self, errors: Iterable[str]):
        self.errors = list(errors)
        super().__init__("；".join(self.errors))


@dataclass(frozen=True)
class ManifestFile:
    path: str
    sha256: str
    role: str
    known_hashes: Tuple[str, ...]


@dataclass(frozen=True)
class ObsoleteFile:
    path: str
    known_hashes: Tuple[str, ...]


@dataclass(frozen=True)
class Manifest:
    archive_version: str
    components: Mapping[str, str]
    managed_dirs: Tuple[str, ...]
    files: Tuple[ManifestFile, ...]
    obsolete: Tuple[ObsoleteFile, ...] = ()
    provides: Mapping[str, int] = field(default_factory=lambda: dict(PROVIDES))

    @classmethod
    def parse(cls, data: bytes, where: str) -> "Manifest":
        """
        读入清单并校验结构；一次报出全部结构错误

        Raises:
            ManifestError: 不是 JSON，或结构不合格式（每条错误都以 where 开头）
        """
        try:
            raw = json.loads(data.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ManifestError([f"{where} 不是合法的 JSON: {e}"]) from e
        if not isinstance(raw, dict):
            raise ManifestError([f"{where} 应为 JSON 对象"])
        errors = _Errors(where)
        if raw.get("formatVersion") != FORMAT_VERSION:
            errors.add(f"formatVersion 应为 {FORMAT_VERSION}，实际为 {raw.get('formatVersion')!r}")
        archive_version = raw.get("archiveVersion")
        if not _is_str(archive_version):
            errors.add(f"archiveVersion 应为非空字符串，实际为 {archive_version!r}")
        components = raw.get("components")
        if not (isinstance(components, dict) and components
                and all(_is_str(k) and isinstance(v, str) for k, v in components.items())):
            errors.add("components 应为非空对象，值为版本字符串")
            components = {}
        provides = raw.get("provides")
        if not (isinstance(provides, dict)
                and all(isinstance(v, int) and not isinstance(v, bool) for v in provides.values())):
            errors.add("provides 应为对象，值为整数版本")
            provides = {}
        managed_dirs = raw.get("managedDirs")
        if not _is_str_list(managed_dirs):
            errors.add("managedDirs 应为字符串数组")
            managed_dirs = []
        file_entries = list(_unique_entries_with_path(raw.get("files"), "files", "缺少 files 列表", errors))
        files = _parse_files(file_entries, errors)
        listed_paths = {path for path, _ in file_entries}
        obsolete = _parse_obsolete(raw.get("obsolete"), listed_paths, errors)
        errors.raise_if_any()
        return cls(archive_version=archive_version, components=dict(components),
                   managed_dirs=tuple(managed_dirs), files=files, obsolete=obsolete,
                   provides=dict(provides))

    def to_bytes(self) -> bytes:
        data = {
            "formatVersion": FORMAT_VERSION,
            "archiveVersion": self.archive_version,
            "components": dict(self.components),
            "provides": dict(self.provides),
            "managedDirs": list(self.managed_dirs),
            "files": [{"path": f.path, "sha256": f.sha256, "role": f.role,
                       "knownHashes": list(f.known_hashes)} for f in self.files],
            "obsolete": [{"path": o.path, "knownHashes": list(o.known_hashes)} for o in self.obsolete],
        }
        return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


class _Errors:
    def __init__(self, where: str):
        self.where = where
        self.messages: List[str] = []

    def add(self, message: str):
        self.messages.append(f"{self.where}: {message}")

    def raise_if_any(self):
        if self.messages:
            raise ManifestError(self.messages)


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _unique_entries_with_path(entries: Any, section: str, missing: str,
                              errors: _Errors) -> Iterator[Tuple[str, dict]]:
    if not isinstance(entries, list):
        errors.add(missing)
        return
    seen: Set[str] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or not _is_str(entry.get("path")):
            errors.add(f"{section}[{i}] 应为带 path 的对象")
            continue
        path = entry["path"]
        if path in seen:
            errors.add(f"{section} 里 {path} 重复出现")
            continue
        seen.add(path)
        yield path, entry


def _parse_files(entries: List[Tuple[str, dict]], errors: _Errors) -> Tuple[ManifestFile, ...]:
    files: List[ManifestFile] = []
    for path, entry in entries:
        sha256, role, known = entry.get("sha256"), entry.get("role"), entry.get("knownHashes")
        valid = True
        if not _is_str(sha256):
            errors.add(f"{path} 缺少 sha256")
            valid = False
        if role not in ROLES:
            errors.add(f"{path} 的 role 不合法: {role!r}")
            valid = False
        if not _is_str_list(known) or sha256 not in known:
            errors.add(f"{path} 的 knownHashes 应为包含本次 sha256 的数组")
            valid = False
        if valid:
            files.append(ManifestFile(path, sha256, role, tuple(known)))
    return tuple(files)


def _parse_obsolete(entries: Any, listed_paths: Set[str], errors: _Errors) -> Tuple[ObsoleteFile, ...]:
    obsolete: List[ObsoleteFile] = []
    for path, entry in _unique_entries_with_path(entries, "obsolete", "obsolete 应为数组", errors):
        if path in listed_paths:
            errors.add(f"{path} 同时出现在 files 和 obsolete 里")
        known = entry.get("knownHashes")
        if not _is_str_list(known):
            errors.add(f"obsolete 里 {path} 的 knownHashes 应为字符串数组")
            continue
        obsolete.append(ObsoleteFile(path, tuple(known)))
    return tuple(obsolete)


def write_manifest(archive_root: Path, manifest: Manifest) -> Path:
    path = Path(archive_root) / MANIFEST_NAME
    path.write_bytes(manifest.to_bytes())
    return path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def portable_config_entries(z: zipfile.ZipFile) -> Iterator[Tuple[str, bytes]]:
    """安装包里 portable_config 下的每个文件：(相对 portable_config 的正斜杠路径, 内容)"""
    prefix = PORTABLE_CONFIG + "/"
    for info in z.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith(prefix) and not name.endswith("/"):
            yield name[len(prefix):], z.read(info)


@dataclass(frozen=True)
class HistoryFile:
    role: str
    hashes: Tuple[str, ...]


@dataclass(frozen=True)
class ManifestHistory:
    archives: Tuple[str, ...] = ()
    files: Mapping[str, HistoryFile] = field(default_factory=dict)


def load_history(path: Path) -> ManifestHistory:
    """
    读取提交在仓库里的历史哈希（manifest-history.json）

    Raises:
        ManifestError: 读不出文件，或结构不对
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ManifestError([f"读取历史哈希 {path} 失败: {e}"]) from e
    errors = _Errors(str(path))
    archives = raw.get("archives") if isinstance(raw, dict) else None
    files = raw.get("files") if isinstance(raw, dict) else None
    if not _is_str_list(archives):
        errors.add("archives 应为字符串数组")
    if not (isinstance(files, dict) and all(
            isinstance(entry, dict) and entry.get("role") in ROLES and _is_str_list(entry.get("hashes"))
            for entry in files.values())):
        errors.add(f"files 应为对象，值为 {{\"role\": {'/'.join(ROLES)}, \"hashes\": sha256 数组}}")
    errors.raise_if_any()
    return ManifestHistory(tuple(archives), {
        p: HistoryFile(entry["role"], tuple(entry["hashes"])) for p, entry in files.items()})


@dataclass(frozen=True)
class KnownHashes:
    hashes: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    roles: Mapping[str, str] = field(default_factory=dict)
    previously_obsolete: FrozenSet[str] = frozenset()

    @classmethod
    def merge(cls, history: Optional[ManifestHistory] = None,
              previous_manifest: Optional[Manifest] = None) -> "KnownHashes":
        known: Dict[str, Set[str]] = {}
        roles: Dict[str, str] = {}
        previously_obsolete: Set[str] = set()
        if history:
            for path, entry in history.files.items():
                known.setdefault(path, set()).update(entry.hashes)
                roles[path] = entry.role
        if previous_manifest:
            for f in previous_manifest.files:
                known.setdefault(f.path, set()).update(f.known_hashes)
                known[f.path].add(f.sha256)
                roles[f.path] = f.role
            for o in previous_manifest.obsolete:
                known.setdefault(o.path, set()).update(o.known_hashes)
                previously_obsolete.add(o.path)
        return cls({path: frozenset(h) for path, h in known.items()}, roles, frozenset(previously_obsolete))

    def of(self, path: str) -> Set[str]:
        return set(self.hashes.get(path, ()))

    def is_obsolete_candidate(self, path: str) -> bool:
        return path in self.previously_obsolete or self.roles.get(path) not in ROLES_KEPT_BY_CLIENT


def build_manifest(portable_config_dir: Path, archive_version: str,
                   components: Dict[str, str], layout: "DependencyLayout",
                   known: Optional[KnownHashes] = None) -> Manifest:
    """
    扫描 portable_config 目录生成清单

    Args:
        layout: 依赖布局，给出每个文件的归属和清单的 managedDirs
        known: 已知哈希，并进 knownHashes 和 obsolete；None 时视为没有历史
    """
    known = known or KnownHashes()
    portable_config_dir = Path(portable_config_dir)
    files: List[ManifestFile] = []
    for item in sorted(portable_config_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(portable_config_dir).as_posix()
        digest = sha256_file(item)
        files.append(ManifestFile(rel, digest, layout.role_of(rel), tuple(sorted(known.of(rel) | {digest}))))

    files.sort(key=lambda f: f.path)
    current = {f.path for f in files}
    obsolete = tuple(
        ObsoleteFile(path, tuple(sorted(hashes)))
        for path, hashes in sorted(known.hashes.items())
        if path not in current and known.is_obsolete_candidate(path)
    )
    return Manifest(archive_version=archive_version, components=dict(components),
                    managed_dirs=tuple(layout.manifest_managed_dirs), files=tuple(files), obsolete=obsolete)
