#!/usr/bin/env python3
"""Background lock check.

    python3 tools/verify_bg.py           # compare against tools/bg.lock (exit 1 on any change)
    python3 tools/verify_bg.py --update  # only when you INTENTIONALLY change the background

It hashes (1) the background file that the BG-LOCK block references (public/bg-news.svg) and (2) the CSS block
between BG-LOCK-START / BG-LOCK-END in style.css.
To change the background: save the new art under a NEW file name (so installed Service Workers never serve a stale copy),
point the BG-LOCK block and SHELL in sw.js at it, then run --update.
"""
import hashlib
import json
import pathlib
import re
import sys

root = pathlib.Path(__file__).resolve().parent.parent
lock = root / "tools" / "bg.lock"


def current():
    css = (root / "public" / "style.css").read_text(encoding="utf-8")
    m = re.search(r"/\* BG-LOCK-START \*/(.*?)/\* BG-LOCK-END \*/", css, re.S)
    if not m:
        sys.exit("BG-LOCK block missing from style.css")
    f = re.search(r'url\("/([^"?]+)"\)', m.group(1))
    if not f:
        sys.exit("BG-LOCK block does not reference a background file")
    svg = (root / "public" / f.group(1)).read_bytes()
    return {f.group(1): hashlib.sha256(svg).hexdigest(), "style.css BG-LOCK block": hashlib.sha256(m.group(1).strip().encode()).hexdigest()}


cur = current()
if "--update" in sys.argv:
    lock.write_text(json.dumps(cur, indent=2), encoding="utf-8")
    print("lock updated:", cur)
    sys.exit(0)
old = json.loads(lock.read_text(encoding="utf-8"))
bad = [k for k in cur if cur[k] != old.get(k)]
for k in cur:
    print(("OK      " if k not in bad else "CHANGED ") + k + "  " + cur[k][:16])
sys.exit(1 if bad else 0)
