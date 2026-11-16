"""
MPV 归档清单 fntv-manifest.json

清单放在归档根目录，列出 portable_config 下每个文件的 sha256 和归属（role），
客户端靠它按 conffile 方式同步用户配置。格式见 JayYa/fntv-electron#219。
"""
import fnmatch
import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Mapping, Optional, Set, Tuple

MANIFEST_NAME = "fntv-manifest.json"
# 提交在仓库里的历史哈希
DEFAULT_HISTORY_PATH = Path(__file__).parent.parent / "manifest-history.json"
FORMAT_VERSION = 1
PORTABLE_CONFIG = "portable_config"

ROLES = ("managed", "config", "seed")

# 归属规则：按顺序匹配相对 portable_config 的正斜杠路径，先命中的生效
ROLE_RULES = [
    ("scripts/*", "managed"),
    ("fonts/*", "managed"),
    ("shaders/*", "managed"),
    ("fntv/defaults.conf", "managed"),
    ("mpv.conf", "config"),
    ("input.conf", "config"),
    ("danmaku-history.json", "seed"),
]

# 整目录托管、客户端整体替换的目录
MANAGED_DIRS = ["scripts/uosc", "scripts/uosc_danmaku", "scripts/smart_skip"]

# 归档提供给客户端的能力：能力名 -> 版本
PROVIDES = {
    # smart_skip 从播放地址取 Proxy 的 scheme、主机和端口（a5e1137 起）
    "smart-skip.origin-from-play-url": 1,
}


# mpv.conf 分层：默认值在托管的 fntv/defaults.conf 的 [fntv-defaults] 段里，
# 薄 mpv.conf 的前两个有效行是 include 它和 profile=fntv-defaults，用户设置写在后面。
#
# 为什么要 profile 段（附带 MPV 55d3feb45 实测，见 options/parse_configfile.c 和
# m_config_frontend.c）：配置文件顶层的选项先存进 default profile，读完整个文件才按顺序应用；
# include 在应用时才读入目标文件，目标文件的顶层选项追加到 default profile 末尾，
# 于是排在外层文件所有行之后，默认值反而覆盖用户设置。放进命名段再用 profile= 立即应用，
# 默认值就在 include 行的位置生效，后面的用户设置覆盖它。
DEFAULTS_CONF = "fntv/defaults.conf"
DEFAULTS_PROFILE = "fntv-defaults"
INCLUDE_LINE = 'include="~~/fntv/defaults.conf"'

# 客户端依赖的路径（相对 portable_config）：各托管插件的入口脚本和分层的 mpv 配置
REQUIRED_PATHS = [
    "scripts/uosc/main.lua",
    "scripts/uosc_danmaku/main.lua",
    "scripts/smart_skip/main.lua",
    "scripts/thumbfast.lua",
    "mpv.conf",
    DEFAULTS_CONF,
]


class ManifestError(Exception):
    """清单生成错误"""


def write_manifest(archive_root: Path, manifest: dict) -> Path:
    """把清单写到归档根目录（与 mpv.exe、portable_config 同级）"""
    path = Path(archive_root) / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def role_of(path: str) -> Optional[str]:
    """返回相对 portable_config 的路径的归属，没有规则命中时返回 None"""
    parts = path.split("/")
    if len(parts) == 2 and parts[0] == "script-opts" and parts[1].endswith(".conf"):
        return "config"
    for pattern, role in ROLE_RULES:
        if fnmatch.fnmatchcase(path, pattern):
            return role
    return None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_history(path: Path) -> dict:
    """读取提交在仓库里的历史哈希（manifest-history.json）"""
    with open(path, "r", encoding="utf-8") as f:
        history = json.load(f)
    if not isinstance(history.get("files"), dict):
        raise ManifestError(f"{path} 缺少 files 对象")
    return history


def history_from_archives(archives: List[Tuple[str, Path]]) -> dict:
    """
    从历史归档 zip 算出每个 portable_config 路径出现过的全部哈希

    Args:
        archives: (Release tag, zip 路径) 列表，按发布顺序

    Returns:
        {"archives": [tag...], "files": {路径: [排序去重的 sha256...]}}
    """
    files: Dict[str, Set[str]] = {}
    prefix = PORTABLE_CONFIG + "/"
    for _tag, zip_path in archives:
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith(prefix) and not name.endswith("/"):
                    files.setdefault(name[len(prefix):], set()).add(sha256_bytes(z.read(info)))
    return {
        "archives": [tag for tag, _ in archives],
        "files": {path: sorted(hashes) for path, hashes in sorted(files.items())},
    }


@dataclass(frozen=True)
class KnownHashes:
    """
    已知哈希：提交的历史哈希与上一版清单合并后，每个路径出现过的全部 sha256

    清单生成把它们并进 knownHashes 和 obsolete，契约测试检查它们只增不减。
    """
    hashes: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    previously_obsolete: FrozenSet[str] = frozenset()

    @classmethod
    def merge(cls, history: Optional[dict] = None,
              previous_manifest: Optional[dict] = None) -> "KnownHashes":
        """合并提交的历史（load_history 的结果）和上一版清单"""
        known: Dict[str, Set[str]] = {}
        previously_obsolete: Set[str] = set()
        if history:
            for path, hashes in history.get("files", {}).items():
                known.setdefault(path, set()).update(hashes)
        if previous_manifest:
            for entry in previous_manifest.get("files", []):
                known.setdefault(entry["path"], set()).update(entry.get("knownHashes", []))
                known[entry["path"]].add(entry["sha256"])
            for entry in previous_manifest.get("obsolete", []):
                known.setdefault(entry["path"], set()).update(entry.get("knownHashes", []))
                previously_obsolete.add(entry["path"])
        return cls({path: frozenset(h) for path, h in known.items()}, frozenset(previously_obsolete))

    @classmethod
    def load(cls, history_path: Optional[Path] = None,
             previous_manifest_path: Optional[Path] = None) -> "KnownHashes":
        """
        从文件读取已知哈希

        Args:
            history_path: 历史哈希文件，None 时用仓库根目录的 manifest-history.json
            previous_manifest_path: 上一版 Release 的 fntv-manifest.json，None 时只用历史哈希
        """
        history = load_history(Path(history_path) if history_path else DEFAULT_HISTORY_PATH)
        previous_manifest = None
        if previous_manifest_path:
            with open(previous_manifest_path, "r", encoding="utf-8") as f:
                previous_manifest = json.load(f)
        return cls.merge(history, previous_manifest)

    def of(self, path: str) -> Set[str]:
        return set(self.hashes.get(path, ()))

    def is_obsolete_candidate(self, path: str) -> bool:
        """本次没有的历史路径是否进 obsolete：托管文件进，config/seed 不进（客户端一律保留）"""
        return path in self.previously_obsolete or role_of(path) not in ("config", "seed")


def build_manifest(portable_config_dir: Path, archive_version: str,
                   components: Dict[str, str], known: Optional[KnownHashes] = None) -> dict:
    """
    扫描 portable_config 目录生成清单

    Args:
        known: 已知哈希，并进 knownHashes 和 obsolete；None 时视为没有历史

    Raises:
        ManifestError: 有文件没有归属
    """
    known = known or KnownHashes()
    portable_config_dir = Path(portable_config_dir)
    files: List[dict] = []
    unclassified: List[str] = []
    for item in sorted(portable_config_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(portable_config_dir).as_posix()
        role = role_of(rel)
        if role is None:
            unclassified.append(rel)
            continue
        digest = sha256_file(item)
        files.append({
            "path": rel, "sha256": digest, "role": role,
            "knownHashes": sorted(known.of(rel) | {digest}),
        })
    if unclassified:
        raise ManifestError(f"以下文件没有归属规则: {', '.join(unclassified)}")

    files.sort(key=lambda f: f["path"])
    current = {f["path"] for f in files}
    obsolete = [
        {"path": path, "knownHashes": sorted(hashes)}
        for path, hashes in sorted(known.hashes.items())
        if path not in current and known.is_obsolete_candidate(path)
    ]
    return {
        "formatVersion": FORMAT_VERSION,
        "archiveVersion": archive_version,
        "components": dict(components),
        "provides": dict(PROVIDES),
        "managedDirs": list(MANAGED_DIRS),
        "files": files,
        "obsolete": obsolete,
    }


def _effective_lines(data: bytes) -> List[str]:
    """mpv 配置文件里去掉注释和空行后的行（足够判断分层结构，不是完整的 mpv 解析）"""
    text = data.decode("utf-8-sig", errors="replace")
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if not line.startswith(("include", "[")):
            line = line.split("#", 1)[0].strip()
        lines.append(line)
    return lines


def check_mpv_conf_layering(mpv_conf: bytes, defaults_conf: bytes) -> List[str]:
    """检查 mpv.conf 分层：include 在最前、带 ~~/，紧跟 profile=fntv-defaults；默认值在命名段里"""
    errors = []
    lines = _effective_lines(mpv_conf)
    first = lines[0] if lines else ""
    if not first.startswith("include"):
        errors.append(f"mpv.conf 的首个有效行应为 {INCLUDE_LINE}，实际为 {first!r}"
                      "（include 必须在任何 [profile] 段和设置之前）")
    else:
        value = first[len("include"):].strip().lstrip("=").strip().strip("\"'")
        if not value.startswith("~~/"):
            errors.append(f"mpv.conf 的 include 路径必须带 ~~/ 前缀，实际为 {value!r}")
        elif value != "~~/" + DEFAULTS_CONF:
            errors.append(f"mpv.conf 的 include 应指向 ~~/{DEFAULTS_CONF}，实际为 {value!r}")
    if len(lines) < 2 or lines[1].replace(" ", "") != f"profile={DEFAULTS_PROFILE}":
        errors.append(f"mpv.conf 的 include 行后应紧跟 profile={DEFAULTS_PROFILE}，"
                      "否则默认值会排在用户设置之后生效")
    defaults = _effective_lines(defaults_conf)
    if not defaults or defaults[0] != f"[{DEFAULTS_PROFILE}]":
        errors.append(f"{DEFAULTS_CONF} 的设置必须全部写在 [{DEFAULTS_PROFILE}] 段里，"
                      f"首个有效行应为 [{DEFAULTS_PROFILE}]")
    return errors


def check_archive(zip_path: Path, archive_version: Optional[str] = None,
                  known: Optional[KnownHashes] = None) -> List[str]:
    """
    检查打包产出的 zip 和其中的清单是否一致、是否满足客户端依赖

    Args:
        zip_path: 安装包路径
        archive_version: 期望的 archiveVersion（本次 Release tag），None 时不检查
        known: 已知哈希；其中每个哈希都必须还在清单里（只增不减），None 时视为没有历史

    Returns:
        错误列表，空列表表示通过
    """
    known = known or KnownHashes()
    errors: List[str] = []
    with zipfile.ZipFile(zip_path) as z:
        names = [n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")]
        if MANIFEST_NAME not in names:
            return [f"归档根目录缺少 {MANIFEST_NAME}"]
        try:
            manifest = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            return [f"{MANIFEST_NAME} 不是合法的 JSON: {e}"]

        prefix = PORTABLE_CONFIG + "/"
        zip_hashes = {}
        layered = {}
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith(prefix) and not name.endswith("/"):
                rel = name[len(prefix):]
                data = z.read(info)
                zip_hashes[rel] = sha256_bytes(data)
                if rel in ("mpv.conf", DEFAULTS_CONF):
                    layered[rel] = data

    if "mpv.conf" in layered and DEFAULTS_CONF in layered:
        errors.extend(check_mpv_conf_layering(layered["mpv.conf"], layered[DEFAULTS_CONF]))

    if manifest.get("formatVersion") != FORMAT_VERSION:
        errors.append(f"formatVersion 应为 {FORMAT_VERSION}，实际为 {manifest.get('formatVersion')!r}")
    if archive_version is not None and manifest.get("archiveVersion") != archive_version:
        errors.append(
            f"archiveVersion 应为 {archive_version}，实际为 {manifest.get('archiveVersion')!r}"
        )
    if not isinstance(manifest.get("components"), dict) or not manifest["components"]:
        errors.append("components 应为非空对象")

    provides = manifest.get("provides") or {}
    for key, version in PROVIDES.items():
        if not isinstance(provides.get(key), int) or provides[key] < version:
            errors.append(f"provides 缺少 {key}（至少版本 {version}）")

    managed_dirs = manifest.get("managedDirs") or []
    for d in MANAGED_DIRS:
        if d not in managed_dirs:
            errors.append(f"managedDirs 缺少 {d}")

    seen = set()
    for entry in manifest.get("files") or []:
        path = entry.get("path")
        if path in seen:
            errors.append(f"清单里 {path} 重复出现")
            continue
        seen.add(path)
        if path not in zip_hashes:
            errors.append(f"清单列出的 {path} 不在 zip 的 {PORTABLE_CONFIG} 里")
        elif entry.get("sha256") != zip_hashes[path]:
            errors.append(f"{path} 的 sha256 与 zip 内容不符")
        role = entry.get("role")
        if role not in ROLES:
            errors.append(f"{path} 的 role 不合法: {role!r}")
        elif role != role_of(path):
            errors.append(f"{path} 的 role 应为 {role_of(path)!r}，实际为 {role!r}")
        entry_known = entry.get("knownHashes")
        if not isinstance(entry_known, list) or entry.get("sha256") not in entry_known:
            errors.append(f"{path} 的 knownHashes 应包含本次 sha256")

    for path in sorted(set(zip_hashes) - seen):
        errors.append(f"zip 里的 {PORTABLE_CONFIG}/{path} 没有出现在清单里")

    for path in REQUIRED_PATHS:
        if path not in zip_hashes:
            errors.append(f"缺少客户端依赖的路径 {PORTABLE_CONFIG}/{path}")

    obsolete_entries = manifest.get("obsolete")
    if not isinstance(obsolete_entries, list):
        errors.append("obsolete 应为数组")
        obsolete_entries = []
    obsolete = {}
    for entry in obsolete_entries:
        path = entry.get("path")
        if path in seen:
            errors.append(f"{path} 同时出现在 files 和 obsolete 里")
        if path in obsolete:
            errors.append(f"obsolete 里 {path} 重复出现")
        obsolete[path] = set(entry.get("knownHashes") or [])

    # knownHashes 只增不减：历史和上一版清单里的每个哈希都还在
    current_known = {
        f.get("path"): set(f.get("knownHashes") or []) for f in manifest.get("files") or []
    }
    for path, hashes in sorted(known.hashes.items()):
        if path in current_known:
            have = current_known[path]
        elif path in obsolete:
            have = obsolete[path]
        elif known.is_obsolete_candidate(path):
            errors.append(f"历史托管路径 {path} 本次没有，应出现在 obsolete 里")
            continue
        else:
            continue
        for h in sorted(hashes - have):
            errors.append(f"{path} 的 knownHashes 丢了历史哈希 {h}")
    return errors


def check_manifest_asset(zip_path: Path, asset_path: Path) -> List[str]:
    """
    契约测试：Release 单独上传的清单资产必须存在，且与 zip 根目录里的清单逐字节相同

    Returns:
        错误列表，空列表表示通过
    """
    asset_path = Path(asset_path)
    if not asset_path.is_file():
        return [f"Release 要上传的 {MANIFEST_NAME} 不存在: {asset_path}"]
    with zipfile.ZipFile(zip_path) as z:
        if MANIFEST_NAME not in z.namelist():
            return [f"安装包根目录缺少 {MANIFEST_NAME}"]
        if asset_path.read_bytes() != z.read(MANIFEST_NAME):
            return [f"Release 要上传的 {asset_path} 与 zip 里的 {MANIFEST_NAME} 不同"]
    return []
