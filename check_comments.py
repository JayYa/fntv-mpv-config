#!/usr/bin/env python3
"""
注释禁令的检查：项目自己的 Python 和 Lua 代码里不写注释，发现一条就列出位置并失败

不算注释的：Python 文件首行的 shebang，Lua 文件开头的许可证块。
不检查的：上游原样保留的 thumbfast 和 types/ 下的 mpv 类型桩。
"""
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent
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


def main() -> int:
    found = collect_comments()
    for path, comments in found.items():
        for line, text in comments:
            print(f"{path}:{line}: {text.splitlines()[0]}", file=sys.stderr)
    if found:
        print("不要写注释：起个好名字代替解释，决策写进 docs/adr/，需要注释辩护的 hack 开 issue", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
