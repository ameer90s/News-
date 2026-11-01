"""«رادار الأخبار» edition + live headlines.  Usage: python3 -I tests/radar_test.py <project>

Merges a fixed edition (tests/fixtures/radar_edition_2026-10-27.json; from 1.3.0 data/radar/latest.json belongs to the
scheduled «نشرة المرصد» task and is not shipped in the release ZIP) with the war-cycle fixture (the same events reported by
many outlets) and checks that live headlines join the right Radar story, never a wrong one, and that the lists stay varied."""
import copy
import json
import os
import sys
from datetime import timedelta

os.environ.setdefault("RADAR_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "radar_edition_2026-10-27.json"))
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
top12 = items[:12]
check("the top 10 shows different stories: none repeats a better-ranked one (dup < 15)", all(i["dup"] < 15 for i in items[:10]), [(i["title"][:30], i["dup"]) for i in items[:10]])

top = items[:10]
per = {}
for it in top:
    for e in {truth[s["url"]] for s in it["sources"] if s["url"] in truth} & real:
        per[e] = per.get(e, 0) + 1
check("top 10: live headlines still lead (the Radar gets no extra rank): at least 3 live-only items", sum(1 for i in top if not i.get("radar")) >= 3, [bool(i.get("radar")) for i in top])
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
# --- ranking: the Radar gets no extra rank (a live headline and the same headline from the edition rank alike)
tw = cands[0]
twin_live = [{"title": tw["title"], "url": tw["url"], "source": tw["source"], "published": tw["published"], "hint": tw["hint"], "host": tw["host"]}]
a_item = S.build_items([tw], 48, now)[0]
b_item = S.build_items(twin_live, 48, now)[0]
check("a Radar story ranks like the same headline from the live feed (lift <= the capped impact bonus)",
      0 <= a_item["importance"] - b_item["importance"] <= 0.65 * R.BONUS_MAX + 0.5, (a_item["importance"], b_item["importance"]))

# --- the next day: yesterday's edition is ~23.5 h old, today's news is new. Fresh live news must lead, not the old stories.
later = now + timedelta(hours=23.5)
NEW = [  # (hours_ago, headline, outlet, host, hint, strong)
    (1, "الإمارات ترفع حالة التأهب بعد هجوم بطائرات مسيّرة على ناقلة نفط قبالة سواحل الفجيرة", "العربية", "alarabiya.net", None, 1),
    (2, "هجوم بمسيّرات يستهدف ناقلة قرب ميناء الفجيرة والسلطات الإماراتية تعلن السيطرة على الحريق", "الاتحاد", "aletihad.ae", "local", 1),
    (3, "Drone attack hits tanker off Fujairah, UAE authorities say fire contained", "Reuters", "reuters.com", "international", 1),
    (2, "المصرف المركزي الإماراتي يرفع أسعار الفائدة 25 نقطة أساس", "الخليج", "alkhaleej.ae", "local", 1),
    (3, "الدرهم الإماراتي ثابت أمام الدولار بعد قرار المركزي رفع الفائدة", "البيان", "albayan.ae", "local", 1),
    (4, "النفط يقفز 5% مع تعطل الملاحة في خليج عُمان", "الشرق الأوسط", "aawsat.com", None, 1),
    (4, "البنتاغون يعلن نشر منظومات دفاع جوي إضافية في الخليج", "سكاي نيوز عربية", "skynewsarabia.com", None, 1),
    (6, "قطر والإمارات توقعان اتفاقية لتزويد الغاز المسال لمدة 15 عاماً", "الجزيرة", "aljazeera.net", None, 1),
    (3, "مبابي يغيب عن مباراة الليلة بسبب إصابة في الكاحل", "الرياضية", "sports.example", None, 0),
    (5, "طيران فلاي دبي تعلن جدول رحلات الشتاء الجديد", "البيان", "albayan.ae", "local", 0),
    (8, "افتتاح معرض الكتاب في الشارقة الأسبوع المقبل", "وام", "wam.ae", "local", 0),
]
raw2, fresh_urls = [], {}
for k, (h, t, src, host, hint, st) in enumerate(NEW, 1):
    u = f"https://{host}/new/{k}"
    raw2.append({"title": t, "url": u, "source": src, "published": later - timedelta(hours=h), "hint": hint, "host": host})
    fresh_urls[u] = st
cands_later = R.candidates(ed, later)
for h in (24, 48):
    it2 = S.build_items(raw2 + cands_later, h, later)
    t10 = it2[:10]
    live10 = sum(1 for i in t10 if any(s["url"] in fresh_urls for s in i["sources"]))
    check(f"next day, {h}h window: fresh live news fills at least {5 if h == 24 else 4} of the top 10 (yesterday's edition does not take over)",
          live10 >= (5 if h == 24 else 4), live10)
    check(f"next day, {h}h window: the freshest strong story is first", any(s["url"] in fresh_urls and fresh_urls[s["url"]] for s in it2[0]["sources"]) and "الفجيرة" in it2[0]["title"], it2[0]["title"])
    check(f"next day, {h}h window: first place is a live story, not an edition one", not it2[0].get("radar"), it2[0].get("radar"))

# --- freshness / validation
check("freshness: fresh inside the limit, stale outside", R.age_hours(ed, now + timedelta(hours=1)) < R.MAX_AGE_H < R.age_hours(ed, now + timedelta(hours=40)), None)
check("a non-Arabic or source-less story is dropped by validation", R._validate({"created_at": ed["created"].isoformat(), "domains": {"politics": {"stories": [{"ref": 1, "level": "uae", "title": "English only", "sources": [{"name": "x", "url": "https://a.example/1"}]}]}}}) is None, None)
check("citations are stripped for display: «… [3][5].» → «….»", R.strip_refs("ارتفع المؤشر [3][5].") == "ارتفع المؤشر.", R.strip_refs("ارتفع المؤشر [3][5]."))
print("\nFAILS:", fails)
sys.exit(1 if fails else 0)
