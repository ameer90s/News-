"""How many distinct items does the batch produce per real event?  Usage: python3 -I war_test.py <project> [--show]"""
import sys
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from core import sources as S
from war_fixture import build_raw, now, EVENTS

raw, truth = build_raw()
items = S.build_items(raw, 48, now)
by_ev = {}
for it in items:
    evs = {truth[s["url"]] for s in it["sources"]}
    for e in evs:
        by_ev.setdefault(e, []).append(it)
print(f"{len(raw)} headlines -> {len(items)} items")
print("\nitems per event (ideal = 1 for Arabic variants):")
for ev, rows in EVENTS.items():
    n_ar = sum(1 for r in rows if not r[1].isascii())
    its = by_ev.get(ev, [])
    print(f"  {ev:12s} headlines={len(rows)} (ar={n_ar}) -> items={len(its)}   sizes={[len(i['sources']) for i in its]}")
mixed = [it for it in items if len({truth[s['url']] for s in it['sources']}) > 1]
print("\nitems mixing different events (false merges):", len(mixed))
for it in mixed:
    print("  MIXED:", it["title"][:60], {truth[s['url']] for s in it['sources']})
if "--show" in sys.argv:
    print("\ntop 12 by importance:")
    for k, it in enumerate(items[:12], 1):
        print(f" {k:2d}. [{it['uae_impact']:3d}] imp={it['importance']:6.1f} {it['scope'][:3]} {it['domain'][:4]} n={len(it['sources'])} | {(it['title'] or '(EN) '+it['sources'][0]['title'])[:70]}")

# ---- assertions
fails = 0
def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond: fails += 1

print()
check("no false merges between different events", not mixed, [i["title"][:40] for i in mixed])
check("51 headlines collapse to <= 40 items", len(items) <= 40, len(items))
check("Arabic variants of the 96-hour strike story collapse to <= 3 items", len([i for i in by_ev["strike96"] if i["title"]]) <= 3, [len(i["sources"]) for i in by_ev["strike96"]])
cnn = [i for i in items if any(s["url"].startswith("https://cnn.com/") for s in i["sources"])]
check("English CNN headline joined the Arabic story (cross-language merge)", cnn and cnn[0]["title"] and len(cnn[0]["sources"]) >= 3, cnn and (cnn[0]["title"], len(cnn[0]["sources"])))
check("Hormuz Arabic variants collapse to <= 3 items", len([i for i in by_ev["hormuz"] if i["title"]]) <= 3)
top10 = items[:10]
per_event = {}
for it in top10:
    for e in {truth[s["url"]] for s in it["sources"]}:
        per_event[e] = per_event.get(e, 0) + 1
check("top 10: no event appears more than twice", max(per_event.values()) <= 2, per_event)
check("top 10: at least 7 different events", len(per_event) >= 7, per_event)
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
