"""JSearch (RapidAPI) — aggregated LinkedIn / Indeed / Glassdoor / Google Jobs
postings. Needs RAPIDAPI_KEY. Each query costs one request; keep the list
short and run it once a day.
"""
from __future__ import annotations

import os
import urllib.parse

from .http import get_json

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
LAST = {"requests": 0, "results": 0, "statuses": []}


def search(query: str, key: str, date_posted: str = "week", pages: int = 1) -> list[dict]:
    q = urllib.parse.quote(f"{query} in Israel")
    url = (
        f"https://{HOST}/search?query={q}&page=1&num_pages={pages}"
        f"&country=il&date_posted={date_posted}"
    )
    status, data = get_json(url, headers={"x-rapidapi-key": key, "x-rapidapi-host": HOST})
    LAST["requests"] += 1
    LAST["statuses"].append(status)
    if status != 200 or not isinstance(data, dict):
        return []
    out = []
    for j in data.get("data", []) or []:
        loc = ", ".join(filter(None, [j.get("job_city"), j.get("job_state"), j.get("job_country")]))
        out.append(
            {
                "company": j.get("employer_name", ""),
                "title": j.get("job_title", ""),
                "location": loc or ("Remote" if j.get("job_is_remote") else ""),
                "url": j.get("job_apply_link") or j.get("job_google_link") or "",
                "posted": (j.get("job_posted_at_datetime_utc") or "")[:10],
                "source": f"jsearch:{j.get('job_publisher', '')}",
                "description": (j.get("job_description") or "")[:600],
            }
        )
    return out


def run(queries: list[str] | None = None, date_posted: str = "week") -> list[dict]:
    key = os.environ.get("RAPIDAPI_KEY", "").strip()
    LAST.update({"requests": 0, "results": 0, "statuses": [], "key": bool(key)})
    if not key:
        return []
    out = []
    for q in queries or DEFAULT_QUERIES:
        out.extend(search(q, key, date_posted))
    LAST["results"] = len(out)
    return out
