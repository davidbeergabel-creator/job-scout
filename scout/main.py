"""job-scout — collect senior roles in Israel from company ATS boards and
JSearch, keep a seen-set, write new ones to data/ and (optionally) Notion.

Usage:
  python -m scout.main discover            # resolve ATS slugs for unresolved companies
  python -m scout.main scan [--no-jsearch] # fetch, filter, dedupe, write
  python -m scout.main all
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import ats, jsearch, notion
from .filters import clean_title, dedupe_key, relevant

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WATCHLIST = ROOT / "watchlist.json"
RESOLVED = DATA / "watchlist.resolved.json"
SEEN = DATA / "seen.json"
POSTINGS = DATA / "postings.json"
REJECTED = DATA / "rejected.sample.json"


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except ValueError:
            return default
    return default


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


# ------------------------------------------------------------------ discover


def cmd_discover(limit: int | None = None, retry_days: int = 6) -> None:
    """Resolve each watchlist company to an ATS board. Unresolved companies are re-probed once
    retry_days have passed (the weekly run therefore re-probes everything still unresolved)."""
    watch = load_json(WATCHLIST, {"companies": []})["companies"]
    resolved = load_json(RESOLVED, {})
    today = date.today().isoformat()
    todo = []
    for c in watch:
        name = c["name"]
        r = resolved.get(name)
        if c.get("ats"):  # manually mapped in watchlist.json wins
            resolved[name] = {**c, "checked": today}
            continue
        if r and r.get("ats") in ("smartrecruiters", "workable") and not r.get("verified"):
            # An earlier bug accepted SmartRecruiters'/Workable's empty answer for unknown slugs; re-probe those now.
            todo.append(c)
            continue
        if r and r.get("ats"):
            continue
        if r and r.get("checked") and (date.today() - date.fromisoformat(r["checked"])).days < retry_days:
            continue
        todo.append(c)
    if limit:
        todo = todo[:limit]
    print(f"discover: {len(todo)} companies to probe, {sum(1 for v in resolved.values() if v.get('ats'))} already resolved")

    def probe(c):
        return c["name"], ats.discover(c["name"], c.get("careers_url"), c.get("website"))

    found = 0
    with ThreadPoolExecutor(max_workers=12) as ex:
        for fut in as_completed([ex.submit(probe, c) for c in todo]):
            name, entry = fut.result()
            if entry:
                found += 1
                resolved[name] = {**entry, "checked": today, "verified": True}
                print(f"  + {name}: {entry['ats']} {entry.get('slug') or entry.get('careers_url')}")
            else:
                resolved[name] = {"name": name, "checked": today}
    save_json(RESOLVED, resolved)
    print(f"discover: resolved {found} new; total {sum(1 for v in resolved.values() if v.get('ats'))}")


# ---------------------------------------------------------------------- scan


def cmd_scan(use_jsearch: bool = True, max_age_days: int = 45) -> None:
    resolved = load_json(RESOLVED, {})
    entries = [v for v in resolved.values() if v.get("ats")]
    print(f"scan: {len(entries)} ATS boards")
    raw: list[dict] = []
    failed: list[str] = []

    # Workable rate-limits bursts; keep its boards to two at a time with a pause between calls.
    throttle = {"workable": threading.Semaphore(1)}

    def fetch_one(e):
        sem = throttle.get(e.get("ats"))
        if sem is None:
            return ats.fetch(e)
        with sem:
            res = ats.fetch(e)
            time.sleep(2.0)
            return res

    ats.ERRORS.clear()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, e): e["name"] for e in entries}
        for fut in as_completed(futs):
            res = fut.result()
            if res is None:
                failed.append(f"{futs[fut]} ({ats.ERRORS.get(futs[fut], '?')})")
            else:
                raw.extend(res)
    errors = len(failed)
    print(f"scan: {len(raw)} postings from ATS ({errors} boards failed: {', '.join(sorted(failed))})")

    js_stats = None
    if use_jsearch:
        js = jsearch.run()
        js_stats = dict(jsearch.LAST)
        print(f"scan: {len(js)} postings from JSearch {js_stats}")
        raw.extend(js)

    seen = load_json(SEEN, {})
    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=max_age_days)).isoformat()
    new, rejected = [], []
    current_keys = set()
    for p in raw:
        p["title"] = clean_title(p.get("title", ""))
        keep, why = relevant(p.get("title", ""), p.get("location", ""))
        if not keep:
            if len(rejected) < 40:
                rejected.append({**p, "why": why})
            continue
        if p.get("posted") and p["posted"] < cutoff:
            continue
        key = dedupe_key(p["company"], p["title"])
        current_keys.add(key)
        if key in seen:
            continue
        p["found"] = today
        seen[key] = {"first_seen": today, "url": p.get("url", ""), "company": p["company"], "title": p["title"]}
        new.append(p)

    # Drop seen entries that disappeared from every board for 60+ days (keeps the file small).
    for k, v in list(seen.items()):
        if k not in current_keys and v.get("first_seen", today) < (date.today() - timedelta(days=60)).isoformat():
            seen.pop(k)

    save_json(SEEN, seen)
    save_json(POSTINGS, sorted([p for p in raw if relevant(p.get("title", ""), p.get("location", ""))[0]],
                               key=lambda p: (p.get("posted") or "", p["company"])))
    save_json(REJECTED, rejected)
    if new:
        save_json(DATA / f"new-{today}.json", new)

    summary = {"run": datetime.now(timezone.utc).isoformat(timespec="seconds"), "boards": len(entries),
               "raw": len(raw), "relevant": len(current_keys), "new": len(new), "board_errors": errors,
               "failed_boards": sorted(failed), "jsearch": js_stats}
    if notion.enabled() and new:
        summary["notion"] = notion.push(new)
    else:
        summary["notion"] = "skipped (no NOTION_TOKEN)" if not notion.enabled() else "nothing new"
    save_json(DATA / "last-run.json", summary)
    print("scan:", json.dumps(summary))
    for p in new:
        print(f"  NEW {p['company']} — {p['title']} ({p.get('location','')}) {p.get('url','')}")

    # GitHub Actions step summary
    gs = os.environ.get("GITHUB_STEP_SUMMARY")
    if gs:
        with open(gs, "a") as f:
            f.write(f"## job-scout {today}\n\n{len(new)} new relevant postings out of {len(raw)} collected from {len(entries)} boards"
                    f"{' + JSearch' if use_jsearch else ''}. Notion: {summary['notion']}\n\n")
            for p in new:
                f.write(f"- **{p['company']}** — {p['title']} ({p.get('location','')}) [{p.get('posted','')}]({p.get('url','')})\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["discover", "scan", "all", "diagnose"])
    ap.add_argument("--no-jsearch", action="store_true")
    ap.add_argument("--diagnose", default="", help="URL or company name to inspect (prints what discovery sees)")
    ap.add_argument("--limit", type=int, default=None, help="discover: probe at most N companies")
    ap.add_argument("--retry-days", type=int, default=6, help="discover: re-probe unresolved companies checked more than N days ago (0 = all)")
    a = ap.parse_args(argv)
    if a.cmd in ("discover", "all"):
        cmd_discover(limit=a.limit, retry_days=a.retry_days)
    if a.cmd == "diagnose":
        watch = {c["name"]: c for c in load_json(WATCHLIST, {"companies": []})["companies"]}
        for t in [x.strip() for x in a.diagnose.split("|") if x.strip()]:
            ats.diagnose(t, (watch.get(t) or {}).get("careers_url"))
        return
    if a.cmd in ("scan", "all"):
        cmd_scan(use_jsearch=not a.no_jsearch)


if __name__ == "__main__":
    sys.exit(main())
