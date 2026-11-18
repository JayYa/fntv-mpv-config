import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Set

from .dependency_layout import DependencyLayout
from .manifest import (DEFAULTS_CONF, MANIFEST_NAME, PORTABLE_CONFIG, PROVIDES, KnownHashes, Manifest,
                       ManifestError, portable_config_entries, sha256_bytes)

# mpv.conf 分层：默认值在托管的 fntv/defaults.conf 的 [fntv-defaults] 段里，
# 薄 mpv.conf 的前两个有效行是 include 它和 profile=fntv-defaults，用户设置写在后面。
#
# 为什么要 profile 段（附带 MPV 55d3feb45 实测，见 options/parse_configfile.c 和
# m_config_frontend.c）：配置文件顶层的选项先存进 default profile，读完整个文件才按顺序应用；
# include 在应用时才读入目标文件，目标文件的顶层选项追加到 default profile 末尾，
# 于是排在外层文件所有行之后，默认值反而覆盖用户设置。放进命名段再用 profile= 立即应用，
# 默认值就在 include 行的位置生效，后面的用户设置覆盖它。
DEFAULTS_PROFILE = "fntv-defaults"
INCLUDE_LINE = 'include="~~/fntv/defaults.conf"'


def contract_test(zip_path: Path, known: KnownHashes, layout: DependencyLayout,
                  archive_version: Optional[str] = None,
                  manifest_asset: Optional[Path] = None) -> List[str]:
    """
    契约测试：安装包与其中的清单一致、满足客户端依赖、已知哈希只增不减

    清单结构不对时只报结构错误，不再做一致性检查。

    Args:
        zip_path: 安装包路径
        known: 已知哈希；其中每个哈希都必须还在清单里
        layout: 依赖布局，给出必须有的入口文件、基础配置和托管目录
        archive_version: 期望的归档版本（本次 Release tag），None 时不检查
        manifest_asset: Release 单独上传的清单资产，必须与 zip 里的逐字节相同；None 时不检查

    Returns:
        错误列表，空列表表示通过
    """
    with zipfile.ZipFile(zip_path) as z:
        names = {n.replace("\\", "/") for n in z.namelist() if not n.endswith("/")}
        if MANIFEST_NAME not in names:
            return [f"安装包根目录缺少 {MANIFEST_NAME}"]
        manifest_bytes = z.read(MANIFEST_NAME)
        portable = dict(portable_config_entries(z))
    try:
        manifest = Manifest.parse(manifest_bytes, MANIFEST_NAME)
    except ManifestError as e:
        return e.errors

    errors = _check_archive(manifest, names, portable, known, layout, archive_version)
    if manifest_asset is not None:
        errors += _check_manifest_asset(manifest_bytes, Path(manifest_asset))
    return errors


def _check_archive(manifest: Manifest, names: Set[str], portable: Dict[str, bytes], known: KnownHashes,
                   layout: DependencyLayout, archive_version: Optional[str]) -> List[str]:
    errors: List[str] = []
    if "mpv.conf" in portable and DEFAULTS_CONF in portable:
        errors.extend(_check_mpv_conf_layering(portable["mpv.conf"], portable[DEFAULTS_CONF]))

    if archive_version is not None and manifest.archive_version != archive_version:
        errors.append(f"archiveVersion 应为 {archive_version}，实际为 {manifest.archive_version!r}")

    for key, version in PROVIDES.items():
        if manifest.provides.get(key, 0) < version:
            errors.append(f"provides 缺少 {key}（至少版本 {version}）")

    for d in layout.manifest_managed_dirs:
        if d not in manifest.managed_dirs:
            errors.append(f"managedDirs 缺少 {d}")
    errors.extend(_check_managed_dirs(manifest, layout, names))

    for f in manifest.files:
        if f.path not in portable:
            errors.append(f"清单列出的 {f.path} 不在 zip 的 {PORTABLE_CONFIG} 里")
        elif f.sha256 != sha256_bytes(portable[f.path]):
            errors.append(f"{f.path} 的 sha256 与 zip 内容不符")

    listed = {f.path for f in manifest.files}
    for path in sorted(set(portable) - listed):
        errors.append(f"zip 里的 {PORTABLE_CONFIG}/{path} 没有出现在清单里")

    for path in layout.required_paths:
        if path not in names:
            errors.append(f"缺少客户端依赖的路径 {path}")

    errors.extend(_check_known_hashes_kept(manifest, known))
    return errors


def _check_managed_dirs(manifest: Manifest, layout: DependencyLayout, names: Set[str]) -> List[str]:
    errors = []
    entry_of = {p.managed_dir[len(PORTABLE_CONFIG) + 1:]: p.entry
                for p in layout.placements.values() if p.managed_dir is not None}
    for d in manifest.managed_dirs:
        if entry_of.get(d) not in names:
            errors.append(f"托管目录 {d} 不是哪个依赖的 managed_dir，或它的入口文件不在 zip 里，"
                          "客户端会整体替换它")
        for f in manifest.files:
            if f.path.startswith(d + "/") and f.role != "managed":
                errors.append(f"{f.path} 在托管目录 {d} 里，role 应为 'managed'，实际为 {f.role!r}")
    return errors


def _check_known_hashes_kept(manifest: Manifest, known: KnownHashes) -> List[str]:
    errors = []
    current_known = {f.path: set(f.known_hashes) for f in manifest.files}
    obsolete = {o.path: set(o.known_hashes) for o in manifest.obsolete}
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


def _check_manifest_asset(manifest_bytes: bytes, asset_path: Path) -> List[str]:
    if not asset_path.is_file():
        return [f"Release 要上传的 {MANIFEST_NAME} 不存在: {asset_path}"]
    if asset_path.read_bytes() != manifest_bytes:
        return [f"Release 要上传的 {asset_path} 与 zip 里的 {MANIFEST_NAME} 不同"]
    return []


def _lines_without_comments(data: bytes) -> List[str]:
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


def _check_mpv_conf_layering(mpv_conf: bytes, defaults_conf: bytes) -> List[str]:
    errors = []
    lines = _lines_without_comments(mpv_conf)
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
    defaults = _lines_without_comments(defaults_conf)
    if not defaults or defaults[0] != f"[{DEFAULTS_PROFILE}]":
        errors.append(f"{DEFAULTS_CONF} 的设置必须全部写在 [{DEFAULTS_PROFILE}] 段里，"
                      f"首个有效行应为 [{DEFAULTS_PROFILE}]")
    return errors
