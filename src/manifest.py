"""
MPV 归档清单 fntv-manifest.json

清单放在归档根目录，列出 portable_config 下每个文件的 sha256 和归属（role），
客户端靠它按 conffile 方式同步用户配置。格式见 JayYa/fntv-electron#219。
"""
import fnmatch
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

MANIFEST_NAME = "fntv-manifest.json"
FORMAT_VERSION = 1
PORTABLE_CONFIG = "portable_config"

ROLES = ("managed", "config", "seed")

# 归属规则：按顺序匹配相对 portable_config 的正斜杠路径，先命中的生效
ROLE_RULES = [
    ("scripts/*", "managed"),
    ("fonts/*", "managed"),
    ("shaders/*", "managed"),
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


# 客户端依赖的路径（相对 portable_config）：各托管插件的入口脚本
REQUIRED_PATHS = [
    "scripts/uosc/main.lua",
    "scripts/uosc_danmaku/main.lua",
    "scripts/smart_skip/main.lua",
    "scripts/thumbfast.lua",
]


class ManifestError(Exception):
    """清单生成错误"""


def archive_version_for(timestamp: str) -> str:
    """安装包时间戳对应的 Release tag，也是清单的 archiveVersion"""
    return f"fntv-mpv-v{timestamp}"


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


def build_manifest(portable_config_dir: Path, archive_version: str,
                   components: Dict[str, str]) -> dict:
    """
    扫描 portable_config 目录生成清单

    Raises:
        ManifestError: 有文件没有归属
    """
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
        files.append({"path": rel, "sha256": digest, "role": role, "knownHashes": [digest]})
    if unclassified:
        raise ManifestError(f"以下文件没有归属规则: {', '.join(unclassified)}")

    files.sort(key=lambda f: f["path"])
    return {
        "formatVersion": FORMAT_VERSION,
        "archiveVersion": archive_version,
        "components": dict(components),
        "provides": dict(PROVIDES),
        "managedDirs": list(MANAGED_DIRS),
        "files": files,
        "obsolete": [],
    }


def check_archive(zip_path: Path, archive_version: Optional[str] = None) -> List[str]:
    """
    契约测试：检查打包产出的 zip 和其中的清单是否一致、是否满足客户端依赖

    Args:
        zip_path: 安装包路径
        archive_version: 期望的 archiveVersion（本次 Release tag），None 时不检查

    Returns:
        错误列表，空列表表示通过
    """
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
        for info in z.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith(prefix) and not name.endswith("/"):
                zip_hashes[name[len(prefix):]] = sha256_bytes(z.read(info))

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
        known = entry.get("knownHashes")
        if not isinstance(known, list) or entry.get("sha256") not in known:
            errors.append(f"{path} 的 knownHashes 应包含本次 sha256")

    for path in sorted(set(zip_hashes) - seen):
        errors.append(f"zip 里的 {PORTABLE_CONFIG}/{path} 没有出现在清单里")

    for path in REQUIRED_PATHS:
        if path not in zip_hashes:
            errors.append(f"缺少客户端依赖的路径 {PORTABLE_CONFIG}/{path}")

    if not isinstance(manifest.get("obsolete"), list):
        errors.append("obsolete 应为数组")
    return errors
