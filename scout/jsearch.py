"""JSearch (RapidAPI) — aggregated LinkedIn / Indeed / Glassdoor / Google Jobs
postings. Needs RAPIDAPI_KEY. Each query costs one request; keep the list
short and run it once a day.
"""
from __future__ import annotations

import os
import urllib.parse

import json

from .http import get

HOST = "jsearch.p.rapidapi.com"

# Six queries x one daily run ~= 180 requests/month, inside the free RapidAPI plan.
# Add more (or raise pages) if David moves to a paid tier.
DEFAULT_QUERIES = [
    "VP Sales",
    "VP Partnerships",
    "VP Business Development",
    "Chief Revenue Officer",
    "General Manager Israel",
    "VP GTM",
]

# Stats of the last run(), written to data/last-run.json by the scan.
LAST: dict = {"requests": 0, "results": 0, "statuses": []}


def _pick(j: dict, *keys, default=""):
    for k in keys:
        v = j.get(k)
        if v:
            return v
    return default


def _normalize(j: dict) -> dict:
    loc = ", ".join(filter(None, [_pick(j, "job_city", "city"), _pick(j, "job_state", "state"), _pick(j, "job_country", "country")]))
    return {
        "company": _pick(j, "employer_name", "employer", "company_name", "company"),
        "title": _pick(j, "job_title", "title"),
        "location": loc or _pick(j, "job_location", "location") or ("Remote" if j.get("job_is_remote") else ""),
        "url": _pick(j, "job_apply_link", "apply_link", "job_google_link", "url", "link"),
        "posted": str(_pick(j, "job_posted_at_datetime_utc", "job_posted_at", "posted_at", "date_posted"))[:10],
        "source": f"jsearch:{_pick(j, 'job_publisher', 'publisher')}",
        "description": str(_pick(j, "job_description", "description"))[:600],
    }


def search(query: str, key: str, date_posted: str = "week", pages: int = 1) -> list[dict]:
    """JSearch v5 moved to /search-v2 (listings under data.jobs, cursor paging); /search answers 404.
    Try v2 first, then the legacy path, and remember the first error for the run summary."""
    q = urllib.parse.quote(f"{query} in Israel")
    params = f"query={q}&page=1&num_pages={pages}&country=il&date_posted={date_posted}"
    for path in ("search-v2", "search"):
        url = f"https://{HOST}/{path}?{params}"
        status, body = get(url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST})
        LAST["requests"] += 1
        LAST["statuses"].append(f"{path}:{status}")
        if status == 404:
            LAST.setdefault("error", f"{path} {status}: {(body or '')[:160]}")
            continue
        if status != 200:
            LAST.setdefault("error", f"{path} {status}: {(body or '')[:200]}")
            return []
        try:
            data = json.loads(body)
        except ValueError:
            LAST.setdefault("error", f"{path} {status}: non-JSON body")
            return []
        if not isinstance(data, dict):
            return []
        payload = data.get("data")
        jobs = payload.get("jobs") if isinstance(payload, dict) else payload
        jobs = jobs if isinstance(jobs, list) else []
        if jobs and "sample_keys" not in LAST:
            LAST["sample_keys"] = sorted(jobs[0].keys())[:40]
        LAST["endpoint"] = path
        return [_normalize(j) for j in jobs if isinstance(j, dict)]
    return []


def run(queries: list[str] | None = None, date_posted: str = "week") -> list[dict]:
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    LAST.clear()
    LAST.update({"requests": 0, "results": 0, "statuses": [], "key": bool(key), "key_len": len(key)})
    if not key:
        return []
    out = []
    for q in queries or DEFAULT_QUERIES:
        out.extend(search(q, key, date_posted))
    LAST["results"] = len(out)
    return out
