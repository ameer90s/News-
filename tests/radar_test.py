"""«رادار الأخبار» edition + live headlines.  Usage: python3 -I tests/radar_test.py <project>

Merges the shipped edition (data/radar/latest.json) with the war-cycle fixture (the same events reported by many outlets)
and checks that live headlines join the right Radar story, never a wrong one, and that the lists stay varied."""
import copy
import json
import sys
from datetime import timedelta

sys.path.insert(0, sys.argv[1])
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from core import radar as R, sources as S
from war_fixture import build_raw, now, EVENTS

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, "" if cond else extra)
    if not cond:
        fails += 1


ed = R.load()
check("the shipped edition loads and validates", ed is not None and len(ed["domains"]) == 3, None)
n_stories = sum(len(d["stories"]) for d in ed["domains"].values())
cands = R.candidates(ed, now)
check(f"{n_stories} stories become candidates", len(cands) == n_stories, len(cands))
check("candidate keys are unique and ids are stable", len({R.item_id(c["radar"]["key"]) for c in cands}) == n_stories, None)

raw, truth = build_raw()
items = S.build_items(raw + cands, 48, now)
rit = [i for i in items if i.get("radar")]
check("every Radar story survives as its own item (none lost, none merged together)", len(rit) == n_stories, len(rit))
check("item ids are the Radar keys' ids", {i["id"] for i in rit} == {R.item_id(c["radar"]["key"]) for c in cands}, None)

real = {e for e in EVENTS}
mixed = []
for it in rit:
    evs = {truth[s["url"]] for s in it["sources"] if s["url"] in truth} & real
    if len(evs) > 1:
        mixed.append((it["title"][:40], evs))
check("no Radar story absorbed headlines of two different events (no false merge)", not mixed, mixed)
attached = sum(1 for it in rit for s in it["sources"] if s["url"] in truth)
check("most live headlines about Radar events joined their Radar story", attached >= 25, attached)
check("a Radar story keeps its own sources first, with live ones after", all(it["sources"][0]["url"].startswith("https://") for it in rit), None)
radar_events = {truth[s["url"]] for it in rit for s in it["sources"] if s["url"] in truth} & real
left = [it for it in items[:12] if not it.get("radar") and ({truth.get(s["url"]) for s in it["sources"]} & radar_events)]
check("live headlines that repeat a Radar event do not sit in the top 12", not left, [i["title"] for i in left])

top = items[:10]
per = {}
for it in top:
    for e in {truth[s["url"]] for s in it["sources"] if s["url"] in truth} & real:
        per[e] = per.get(e, 0) + 1
check("top 10: at least 7 Radar stories", sum(1 for i in top if i.get("radar")) >= 7, [bool(i.get("radar")) for i in top])
check("top 10: no event more than twice", per and max(per.values()) <= 2, per)
check("top 10: at least 6 different events", len(per) >= 6, per)
check("Radar summaries and dates are carried", all(i["summary"] and i["when"] for i in rit), None)
check("Radar items are never classified by the keyword guess (scope/domain come from the Radar)", {i["domain"] for i in rit} == {"political", "economic", "military"} and {i["scope"] for i in rit} == {"local", "regional", "international"}, None)

# --- the edition alone (both live feeds down)
solo = S.build_items(R.candidates(ed, now), 72, now)
check("edition alone: all stories served", len(solo) == n_stories, len(solo))
# --- the same article cited by two domains stays two stories
twin = json.load(open(R.RADAR_FILE, encoding="utf-8"))
st0 = twin["domains"]["politics"]["stories"][0]
dup = copy.deepcopy(st0); dup["ref"] = 99; dup["title"] = "قصة أخرى مختلفة تمامًا عن موضوع آخر في المجال العسكري"
twin["domains"]["military"]["stories"].append(dup)
twin = R._validate(twin)
sol2 = S.build_items(R.candidates(twin, now), 72, now)
check("same article cited in two domains: both stories kept", len(sol2) == n_stories + 1, len(sol2))
# --- window: an edition older than the window contributes no stories
old = S.build_items(R.candidates(ed, now + timedelta(hours=30)), 24, now + timedelta(hours=30))
check("24h window: an edition from 30h ago contributes nothing", not [i for i in old if i.get("radar")], None)
# --- freshness / validation
check("freshness: fresh inside the limit, stale outside", R.age_hours(ed, now + timedelta(hours=1)) < R.MAX_AGE_H < R.age_hours(ed, now + timedelta(hours=40)), None)
check("a non-Arabic or source-less story is dropped by validation", R._validate({"created_at": ed["created"].isoformat(), "domains": {"politics": {"stories": [{"ref": 1, "level": "uae", "title": "English only", "sources": [{"name": "x", "url": "https://a.example/1"}]}]}}}) is None, None)
check("citations are stripped for display: «… [3][5].» → «….»", R.strip_refs("ارتفع المؤشر [3][5].") == "ارتفع المؤشر.", R.strip_refs("ارتفع المؤشر [3][5]."))
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
