#!/usr/bin/env python3
"""
注释禁令的棘轮检查：项目自己的 Python 和 Lua 代码里不写注释

已有的注释记在 comment-baseline.json 里，每个文件的注释数只能减少不能增加。
注释删掉后要用 --update 把基线一起降下来，否则检查失败，基线因此只降不升。

不算注释的：Python 文件首行的 shebang，Lua 文件开头的许可证块。
不检查的：上游原样保留的 thumbfast 和 types/ 下的 mpv 类型桩。

用法:
  python check_comments.py            检查
  python check_comments.py --update   注释删掉后降低基线
  python check_comments.py --list     列出剩下的每条注释
"""
import argparse
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent
BASELINE_PATH = PROJECT_ROOT / "comment-baseline.json"
CHECKED_PATTERNS = ("*.py", "*.lua")
UPSTREAM_PREFIXES = ("local_packages/thumbfast/", "types/")
LUA_LONG_BRACKET = re.compile(r"\[(=*)\[")

Comment = Tuple[int, str]


def python_comments(source: str) -> List[Comment]:
    comments = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        if tok.start == (1, 0) and tok.string.startswith("#!"):
            continue
        comments.append((tok.start[0], tok.string))
    return comments


def _long_bracket_end(source: str, open_match: re.Match) -> int:
    close = "]" + open_match.group(1) + "]"
    end = source.find(close, open_match.end())
    return len(source) if end < 0 else end + len(close)


def lua_comments(source: str) -> List[Comment]:
    comments = []
    i, line = 0, 1
    while i < len(source):
        if source.startswith("--", i):
            long_open = LUA_LONG_BRACKET.match(source, i + 2)
            if long_open:
                end = _long_bracket_end(source, long_open)
            else:
                end = source.find("\n", i)
                end = len(source) if end < 0 else end
            text = source[i:end]
            is_license_header = bool(long_open) and not source[:i].strip() and "License" in text
            if not is_license_header:
                comments.append((line, text))
        elif source[i] in "\"'":
            quote, end = source[i], i + 1
            while end < len(source) and source[end] not in (quote, "\n"):
                end += 2 if source[end] == "\\" else 1
            end = min(end + 1, len(source))
        elif long_string := LUA_LONG_BRACKET.match(source, i):
            end = _long_bracket_end(source, long_string)
        else:
            end = i + 1
        line += source.count("\n", i, end)
        i = end
    return comments


def find_comments(path: str, source: str) -> List[Comment]:
    if path.endswith(".py"):
        return python_comments(source)
    if path.endswith(".lua"):
        return lua_comments(source)
    raise ValueError(f"不检查这种文件: {path}")


def checked_files() -> List[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "--", *CHECKED_PATTERNS],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True, encoding="utf-8",
    ).stdout.split()
    return sorted(path for path in tracked if not path.startswith(UPSTREAM_PREFIXES))


def collect_comments() -> Dict[str, List[Comment]]:
    found = {}
    for path in checked_files():
        comments = find_comments(path, (PROJECT_ROOT / path).read_text(encoding="utf-8"))
        if comments:
            found[path] = comments
    return found


def ratchet_errors(counts: Dict[str, int], baseline: Dict[str, int]) -> List[str]:
    errors = []
    for path in sorted(set(counts) | set(baseline)):
        count, allowed = counts.get(path, 0), baseline.get(path, 0)
        if count > allowed:
            errors.append(f"{path}: {count} 条注释，基线只允许 {allowed} 条。不要写注释，决策写进 docs/adr/")
        elif count < allowed:
            errors.append(f"{path}: 注释从 {allowed} 条减到 {count} 条，运行 python check_comments.py --update 降低基线")
    return errors


def lowered_baseline(counts: Dict[str, int], baseline: Dict[str, int]) -> Dict[str, int]:
    grown = [path for path, count in counts.items() if count > baseline.get(path, 0)]
    if grown:
        raise ValueError("基线只降不升，这些文件的注释比基线多: " + ", ".join(sorted(grown)))
    return {path: count for path, count in sorted(counts.items()) if count}


def load_baseline() -> Dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="注释禁令的棘轮检查")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true", help="注释删掉后降低基线")
    mode.add_argument("--list", action="store_true", help="列出剩下的每条注释")
    args = parser.parse_args(argv)

    found = collect_comments()
    counts = {path: len(comments) for path, comments in found.items()}
    baseline = load_baseline()

    if args.list:
        for path, comments in found.items():
            for line, text in comments:
                print(f"{path}:{line}: {text.splitlines()[0]}")
        print(f"共 {sum(counts.values())} 条注释")
        return 0

    if args.update:
        try:
            new_baseline = lowered_baseline(counts, baseline)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        BASELINE_PATH.write_text(json.dumps(new_baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"基线已更新：{sum(new_baseline.values())} 条注释")
        return 0

    errors = ratchet_errors(counts, baseline)
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
