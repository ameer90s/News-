#!/usr/bin/env python3
"""Bump the release version everywhere it must change together.

    python3 tools/bump_version.py 1.0.1

Updates: ?v= on style.css / app.js (index.html), the sw.js registration URL (app.js),
VERSION in sw.js (new cache name -> old caches are deleted on activate).
It never touches the background block in style.css or the background file (bg-news.svg).
"""
import pathlib
import re
import sys

if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
    sys.exit("usage: bump_version.py X.Y.Z")
v = sys.argv[1]
pub = pathlib.Path(__file__).resolve().parent.parent / "public"


def sub(name, pattern, repl):
    p = pub / name
    s = p.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, s)
    if n == 0:
        sys.exit(f"pattern not found in {name}: {pattern}")
    p.write_text(new, encoding="utf-8")
    print(f"{name}: {n} change(s)")


sub("index.html", r"/style\.css\?v=[\d.]+", f"/style.css?v={v}")
sub("index.html", r"/app\.js\?v=[\d.]+", f"/app.js?v={v}")
sub("app.js", r"/sw\.js\?v=[\d.]+", f"/sw.js?v={v}")
sub("app.js", r"^/\* مرصد الإمارات الذكي — v[\d.]+ \*/", f"/* مرصد الإمارات الذكي — v{v} */")
sub("style.css", r"^/\* مرصد الإمارات الذكي — v[\d.]+ \*/", f"/* مرصد الإمارات الذكي — v{v} */")
sub("sw.js", r"const VERSION = '[\d.]+';", f"const VERSION = '{v}';")
print("done -> now run: python3 tools/verify_bg.py")
