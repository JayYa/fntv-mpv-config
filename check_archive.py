#!/usr/bin/env python3
"""
归档契约测试：检查打包产出的 zip 与其中的 fntv-manifest.json 是否一致

用法:
  python check_archive.py <mpv-package-*.zip> --archive-version fntv-mpv-v<时间戳>

任何一条检查失败时退出码为 1。
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from manifest import check_archive, load_history  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MPV 归档契约测试")
    parser.add_argument("zip_path", help="安装包 zip 路径")
    parser.add_argument("--archive-version", help="期望的 archiveVersion（本次 Release tag）")
    parser.add_argument("--history", default=str(Path(__file__).parent / "manifest-history.json"),
                        help="历史哈希文件（默认: 仓库根目录的 manifest-history.json）")
    parser.add_argument("--previous-manifest",
                        help="上一版 Release 的 fntv-manifest.json；它的哈希也必须都还在")
    parser.add_argument("--manifest-asset",
                        help="Release 要单独上传的 fntv-manifest.json；必须存在且与 zip 里的相同")
    args = parser.parse_args()

    previous = None
    if args.previous_manifest:
        with open(args.previous_manifest, "r", encoding="utf-8") as f:
            previous = json.load(f)
    errors = check_archive(Path(args.zip_path), archive_version=args.archive_version,
                           history=load_history(Path(args.history)),
                           previous_manifest=previous)
    if args.manifest_asset:
        asset = Path(args.manifest_asset)
        if not asset.is_file():
            errors.append(f"Release 要上传的 fntv-manifest.json 不存在: {asset}")
        else:
            with zipfile.ZipFile(args.zip_path) as z:
                if asset.read_bytes() != z.read("fntv-manifest.json"):
                    errors.append(f"Release 要上传的 {asset} 与 zip 里的 fntv-manifest.json 不同")
    if errors:
        print(f"契约测试失败（{len(errors)} 项）:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"契约测试通过: {args.zip_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
