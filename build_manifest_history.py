#!/usr/bin/env python3
"""
从历史 Release 的 zip 生成 manifest-history.json（清单 knownHashes 的历史部分）

只收录本 fork 发过的归档，不收录上游 QiaoKes 的归档。复现方法：

  mkdir <新的空目录> && cd <该目录>
  for t in fntv-mpv-v20260826_013404 fntv-mpv-v20261108_203006 \
           fntv-mpv-v20261108_233327 fntv-mpv-v20261110_224319 \
           fntv-mpv-v20261114_223600; do
    gh release download "$t" -R JayYa/fntv-mpv-config -p '*.zip' -D "$t"
  done
  python <仓库>/build_manifest_history.py -o <仓库>/manifest-history.json \
    fntv-mpv-v20260826_013404=fntv-mpv-v20260826_013404/mpv-package-20260825_173358.zip \
    ...（每个 tag=zip 一项，按发布顺序）

输出确定：同样的输入得到逐字节相同的文件。
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from manifest import history_from_archives  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="从历史归档生成 manifest-history.json")
    parser.add_argument("archives", nargs="+", metavar="TAG=ZIP",
                        help="Release tag 和对应 zip 路径，按发布顺序")
    parser.add_argument("-o", "--output", required=True, help="输出文件")
    args = parser.parse_args()

    pairs = []
    for item in args.archives:
        tag, sep, zip_path = item.partition("=")
        if not sep or not tag or not zip_path:
            parser.error(f"参数应为 TAG=ZIP: {item}")
        pairs.append((tag, Path(zip_path)))

    history = history_from_archives(pairs)
    history = {
        "description": "本 fork 发过的 MPV 归档中每个 portable_config 路径出现过的 sha256；"
                       "由 build_manifest_history.py 生成，只增不减",
        **history,
    }
    Path(args.output).write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"已写入 {args.output}: {len(history['archives'])} 个归档，{len(history['files'])} 个路径")
    return 0


if __name__ == "__main__":
    sys.exit(main())
