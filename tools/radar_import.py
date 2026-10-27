#!/usr/bin/env python3
"""Check a «رادار الأخبار» edition and install it as data/radar/latest.json.

    python3 tools/radar_import.py path/to/edition.json          # validate + install
    python3 tools/radar_import.py path/to/edition.json --check  # validate only

The file is the Radar's own edition JSON (created_at, label_ar, executive, figures, changes_since_last, domains{politics,
economy, military}). Upload data/radar/latest.json to GitHub and Vercel redeploys; the app uses the edition for 36 hours
(RADAR_MAX_AGE_H) and falls back to its normal behaviour after that.
"""
import json
import pathlib
import shutil
import sys
from datetime import datetime, timezone

root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from core import radar  # noqa: E402

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 1:
    sys.exit(__doc__)
src = pathlib.Path(args[0])
try:
    raw = json.loads(src.read_text(encoding="utf-8"))
except (OSError, ValueError) as e:
    sys.exit(f"cannot read {src}: {e}")
ed = radar._validate(raw)
if ed is None:
    sys.exit("NOT USABLE: needs created_at, at least two domains with Arabic stories (ref, level, title, sources with https links)")

age = (datetime.now(timezone.utc) - ed["created"]).total_seconds() / 3600
print(f"edition  {ed['id']}  {ed['label_ar']}  (age {age:.1f} h; the app uses it for {radar.MAX_AGE_H:.0f} h)")
problems = 0
for dom in radar.DOMAIN_ORDER:
    d = ed["domains"].get(dom)
    if not d:
        print(f"  {dom:9s} MISSING")
        problems += 1
        continue
    lv = {k: sum(1 for s in d["stories"] if s["level"] == k) for k in ("uae", "region", "world")}
    refs = [s["ref"] for s in d["stories"]]
    print(f"  {dom:9s} {len(d['stories']):2d} stories {lv}  risk={d['risk_level'] or '-'}  "
          f"analysis: summary={'y' if d['summary'] else 'n'} risks={len(d['risks'])} opportunities={len(d['opportunities'])} "
          f"uae_implications={len(d['uae_implications'])} watch={len(d['watch_list'])}")
    cited = set()
    for blob in [d["headline"], d["summary"], d["comparison"], d["outlook"], *d["levels"].values(), *d["risks"], *d["opportunities"],
                 *d["uae_implications"], *d["market_impact"], *d["watch_list"]]:
        cited.update(radar.refs_in(blob))
    dead = sorted(c for c in cited if c not in refs)
    if dead:
        print(f"            ! citations to stories that do not exist: {dead}")
        problems += 1
    if len(d["stories"]) < 6:
        print("            ! fewer than 6 stories")
        problems += 1
print(f"  figures={len(ed['figures'])}  priorities={len(ed['executive']['top_priorities'])}  "
      f"headline={'y' if ed['executive']['headline'] else 'n (derived from the overview)'}")
if age > radar.MAX_AGE_H:
    print(f"  ! this edition is already older than {radar.MAX_AGE_H:.0f} h: the app would ignore it")
    problems += 1
if "--check" in sys.argv:
    sys.exit(1 if problems else 0)
dst = root / "data" / "radar" / "latest.json"
dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(src, dst)
print(f"installed -> {dst.relative_to(root)}" + ("  (with warnings above)" if problems else ""))
