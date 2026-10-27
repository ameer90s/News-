"""«رادار الأخبار» edition → Mirsad.

The Radar is a daily analytical brief written by Claude after reading the articles themselves (three domains × three
levels: UAE / region / world, ~10 stories per domain, with analysis, risks, opportunities, UAE implications, outlook and a
watch list). Its latest edition is stored as one JSON file, `data/radar/latest.json`, in the Radar's own format.

While that edition is fresh (default: younger than 36 hours) Mirsad uses it as its curated core:
  * its stories become news items (Arabic title, summary, original sources, «why it matters for the UAE») that merge with
    the live headlines about the same event instead of repeating them (see sources.build_items);
  * its executive overview and per-domain analysis feed «الصورة الكبرى» / «التحليل المتكامل» (see `block`).
When the file is missing, malformed or stale, nothing here applies and Mirsad behaves exactly as before.

Replace the file to publish a new edition: `python3 tools/radar_import.py <edition.json>` validates and copies it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

from . import classify as C
from . import registry as REG

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADAR_FILE = os.environ.get("RADAR_FILE") or os.path.join(ROOT, "data", "radar", "latest.json")
MAX_AGE_H = float(os.environ.get("RADAR_MAX_AGE_H", "36"))

SCOPE = {"uae": "local", "region": "regional", "world": "international"}
DOMAIN = {"politics": "political", "economy": "economic", "military": "military"}
DOMAIN_ORDER = ("politics", "economy", "military")
RISK = {"منخفض": "low", "متوسط": "mid", "مرتفع": "high"}

_CITE = re.compile(r"\[(\d+(?:\s*[,،]\s*\d+)*)\]")
_cache: dict = {"mtime": None, "path": None, "ed": None}


# ------------------------------------------------------------------ helpers

def strip_refs(text: str) -> str:
    """Remove the [3][5] story markers (the Radar cites stories by number inside its analysis)."""
    t = _CITE.sub("", text or "")
    t = re.sub(r"\s+([،.؛:)])", r"\1", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def refs_in(text: str) -> list[int]:
    out: list[int] = []
    for m in _CITE.findall(text or ""):
        for n in re.split(r"\s*[,،]\s*", m):
            if n.isdigit() and int(n) not in out:
                out.append(int(n))
    return out


def story_key(ed_id: str, dom: str, ref: int) -> str:
    """Stable identity of a Radar story inside the news pipeline (its item id is sha1(key)[:12])."""
    return f"radar:{ed_id}:{dom}:{ref}"


def item_id(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def _s(v, limit: int = 1200) -> str:
    return re.sub(r"[ \t]+", " ", v).strip()[:limit] if isinstance(v, str) else ""


def _list(v, limit: int = 8, size: int = 600) -> list[str]:
    return [x for x in (_s(i, size) for i in (v if isinstance(v, list) else [])[:limit]) if x]


def _http_url(u) -> str | None:
    return u if isinstance(u, str) and re.match(r"https?://[^\s]+$", u.strip()) else None


def _when(ed: dict) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(ed.get("created_at")))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------- load

def _validate(raw) -> dict | None:
    """Normalise an edition; None when it is not usable. Unknown fields are ignored, missing ones tolerated."""
    if not isinstance(raw, dict) or not isinstance(raw.get("domains"), dict):
        return None
    when = _when(raw)
    if when is None:
        return None
    domains: dict = {}
    for dom in DOMAIN_ORDER:
        d = raw["domains"].get(dom)
        if not isinstance(d, dict):
            continue
        stories = []
        for st in (d.get("stories") if isinstance(d.get("stories"), list) else [])[:14]:
            if not isinstance(st, dict):
                continue
            title, ref = _s(st.get("title"), 300), st.get("ref")
            srcs = []
            for s in (st.get("sources") if isinstance(st.get("sources"), list) else [])[:4]:
                if isinstance(s, dict) and _http_url(s.get("url")):
                    srcs.append({"name": _s(s.get("name"), 80) or "المصدر", "url": s["url"].strip()})
            if (isinstance(ref, int) and not isinstance(ref, bool) and title and C.is_arabic(title)
                    and st.get("level") in SCOPE and srcs):
                stories.append({"ref": ref, "level": st["level"], "title": title, "summary": _s(st.get("summary"), 500),
                                "when": _s(st.get("when"), 30), "uae_related": bool(st.get("uae_related")), "sources": srcs})
        if not stories:
            continue
        kd = []
        for k in (d.get("key_developments") if isinstance(d.get("key_developments"), list) else [])[:6]:
            if isinstance(k, dict) and isinstance(k.get("ref"), int):
                kd.append({"ref": k["ref"], "title": _s(k.get("title"), 200), "significance": _s(k.get("significance"), 400)})
        lv = d.get("levels") if isinstance(d.get("levels"), dict) else {}
        domains[dom] = {
            "headline": _s(d.get("headline"), 500), "summary": _s(d.get("summary"), 1600),
            "risk_level": _s(d.get("risk_level"), 12), "confidence": _s(d.get("confidence"), 12),
            "levels": {k: _s(lv.get(k), 900) for k in ("uae", "region", "world")},
            "comparison": _s(d.get("comparison"), 1200), "key_developments": kd,
            "uae_implications": _list(d.get("uae_implications")), "risks": _list(d.get("risks")),
            "opportunities": _list(d.get("opportunities")), "market_impact": _list(d.get("market_impact")),
            "outlook": _s(d.get("outlook"), 900), "watch_list": _list(d.get("watch_list")), "stories": stories,
        }
    if len(domains) < 2:
        return None
    ex = raw.get("executive") if isinstance(raw.get("executive"), dict) else {}
    figures = []
    for f in (raw.get("figures") if isinstance(raw.get("figures"), list) else [])[:12]:
        if isinstance(f, dict) and _s(f.get("label")) and _s(f.get("value"), 40):
            figures.append({"label": _s(f["label"], 90), "value": _s(f["value"], 40), "change": _s(f.get("change"), 30),
                            "dir": f.get("dir") if f.get("dir") in ("up", "down", "flat") else "flat"})
    return {
        "id": when.astimezone(timezone.utc).strftime("%Y%m%d%H%M"),
        "created": when, "label_ar": _s(raw.get("label_ar"), 80), "window_hours": raw.get("window_hours") if isinstance(raw.get("window_hours"), int) else 24,
        "executive": {"headline": _s(ex.get("headline"), 300), "overview": _s(ex.get("overview"), 2600),
                      "top_priorities": _list(ex.get("top_priorities"), 6), "cross_links": _list(ex.get("cross_links"), 6),
                      "next_48h": _list(ex.get("next_48h"), 6)},
        "figures": figures, "changes_since_last": _list(raw.get("changes_since_last"), 6),
        "domains": domains,
    }


def load() -> dict | None:
    """The edition on disk (cached by file mtime), or None."""
    try:
        mt = os.stat(RADAR_FILE).st_mtime
    except OSError:
        _cache.update(mtime=None, path=None, ed=None)
        return None
    if _cache["mtime"] == mt and _cache["path"] == RADAR_FILE:
        return _cache["ed"]
    ed = None
    try:
        with open(RADAR_FILE, encoding="utf-8") as f:
            ed = _validate(json.load(f))
    except (OSError, ValueError):
        ed = None
    _cache.update(mtime=mt, path=RADAR_FILE, ed=ed)
    return ed


def age_hours(ed: dict, now: datetime | None = None) -> float:
    return max(0.0, ((now or datetime.now(timezone.utc)) - ed["created"]).total_seconds() / 3600.0)


def current(now: datetime | None = None) -> dict | None:
    """The edition when it exists and is still fresh."""
    ed = load()
    return ed if ed is not None and age_hours(ed, now) <= MAX_AGE_H else None


def status(now: datetime | None = None) -> dict:
    """For /api/health: lets the owner check that the file shipped with the deployment and how old it is."""
    ed = load()
    if ed is None:
        return {"found": os.path.exists(RADAR_FILE), "valid": False}
    a = age_hours(ed, now)
    return {"found": True, "valid": True, "edition": ed["id"], "age_hours": round(a, 1), "fresh": a <= MAX_AGE_H}


# ------------------------------------------------------- stories → news items

def _signals(d: dict) -> dict[int, dict]:
    """What the Radar's own analysis says about each story: cited in the UAE implications / risks / opportunities /
    market impact, listed as a key development. These are the Radar's judgement of how much a story matters here."""
    sig: dict[int, dict] = {}

    def at(ref: int) -> dict:
        return sig.setdefault(ref, {"impl": [], "risk": 0, "opp": 0, "mkt": 0, "key": None})

    for line in d["uae_implications"]:
        for r in refs_in(line):
            at(r)["impl"].append(strip_refs(line))
    for line in d["risks"]:
        for r in refs_in(line):
            at(r)["risk"] += 1
    for line in d["opportunities"]:
        for r in refs_in(line):
            at(r)["opp"] += 1
    for line in d["market_impact"]:
        for r in refs_in(line):
            at(r)["mkt"] += 1
    for k in d["key_developments"]:
        at(k["ref"])["key"] = k["significance"] or True
    return sig


def candidates(ed: dict, now: datetime) -> list[dict]:
    """The edition's stories as raw candidates for sources.build_items (published = the edition time)."""
    out: list[dict] = []
    pub = min(ed["created"].astimezone(timezone.utc), now)
    for dom in DOMAIN_ORDER:
        d = ed["domains"].get(dom)
        if not d:
            continue
        sig = _signals(d)
        for st in d["stories"]:
            s = sig.get(st["ref"], {})
            first = st["sources"][0]
            scope = SCOPE[st["level"]]
            key = story_key(ed["id"], dom, st["ref"])
            n_cited = len(s.get("impl", [])) + s.get("risk", 0) + s.get("opp", 0) + s.get("mkt", 0)
            why = (s["impl"][0] if s.get("impl") else (s["key"] if isinstance(s.get("key"), str) else ""))
            out.append({
                "title": st["title"], "url": first["url"], "source": first["name"], "published": pub, "hint": scope,
                "host": REG.host_of(first["url"]),
                "radar": {
                    "key": key, "domain": DOMAIN[dom], "scope": scope, "summary": st["summary"], "when": st["when"],
                    "ref": st["ref"], "text": st["title"], "why": strip_refs(why) if why else "",
                    "sources": st["sources"], "uae_related": st["uae_related"],
                    "cited": n_cited, "impl": bool(s.get("impl")), "risk": s.get("risk", 0) > 0, "key_dev": bool(s.get("key")),
                },
            })
    return out


def impact_of(rd: dict, n_sources: int) -> tuple[int, str]:
    """0-100 potential impact on the UAE for a Radar story.

    Starts from the same headline heuristic as every other story (so the numbers stay comparable across the page), then
    adds what the Radar's own analysis says about the story: a key development, cited in the UAE implications, risks or
    opportunities, directly about the UAE."""
    base, why = C.assess(rd["text"], rd["scope"], n_sources)
    bonus = (8 if rd["key_dev"] else 0) + (10 if rd["impl"] else 0) + (5 if rd["risk"] else 0) \
        + (4 if rd["cited"] and not rd["impl"] and not rd["risk"] else 0) + (5 if rd["uae_related"] else 0)
    impact = int(max(5, min(96, base + bonus)))
    return impact, rd["why"] or (why if impact > 33 else "")


# ---------------------------------------------------- analysis for the page

def block(ed: dict, ids: dict[str, str]) -> dict:
    """Edition → JSON for the page. `ids` maps story keys to item ids so that «[3]» can open story 3."""
    domains = {}
    for dom in DOMAIN_ORDER:
        d = ed["domains"].get(dom)
        if not d:
            continue
        refs = {}
        for st in d["stories"]:
            iid = ids.get(story_key(ed["id"], dom, st["ref"]))
            if iid:
                refs[str(st["ref"])] = iid
        domains[DOMAIN[dom]] = {
            **{k: v for k, v in d.items() if k != "stories"},
            "risk": RISK.get(d["risk_level"], "none"), "refs": refs,
        }
    return {
        "id": ed["id"], "created_at": ed["created"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "label_ar": ed["label_ar"], "window_hours": ed["window_hours"], "executive": ed["executive"],
        "figures": ed["figures"], "changes_since_last": ed["changes_since_last"], "domains": domains,
    }
