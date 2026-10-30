"""LinkedIn public job search (the "guest" endpoint behind linkedin.com/jobs/search).
No login, no key. Returns up to 25 cards per query; we ask for the past week in Israel.
LinkedIn may rate-limit datacenter IPs (429/999) — stats go to data/last-run.json so a
silent failure is visible.
"""
from __future__ import annotations

import html
import re
import time
import urllib.parse

from .http import get

GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

DEFAULT_QUERIES = [
    "VP Sales",
    "VP Partnerships",
    "VP Business Development",
    "Chief Revenue Officer",
    "Chief Business Officer",
    "General Manager",
    "VP GTM",
    "VP Operations",
    "Head of Partnerships",
    "Head of Sales",
    "VP Growth",
    "Head of AI",
]

LAST: dict = {"requests": 0, "results": 0, "statuses": []}

_CARD = re.compile(r"<li>.*?</li>", re.S)
_LINK = re.compile(r'href="(https://[a-z]{2,3}\.linkedin\.com/jobs/view/[^"?]+)', re.I)
_TITLE = re.compile(r'base-search-card__title[^>]*>\s*(.*?)\s*<', re.S)
_COMPANY = re.compile(r'base-search-card__subtitle[^>]*>.*?<a[^>]*>\s*(.*?)\s*</a>|base-search-card__subtitle[^>]*>\s*(.*?)\s*<', re.S)
_LOC = re.compile(r'job-search-card__location[^>]*>\s*(.*?)\s*<', re.S)
_DATE = re.compile(r'<time[^>]*datetime="(\d{4}-\d{2}-\d{2})"')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
}


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse(page: str) -> list[dict]:
    out = []
    for card in _CARD.findall(page or ""):
        link = _LINK.search(card)
        title = _TITLE.search(card)
        if not link or not title:
            continue
        comp = _COMPANY.search(card)
        company = _clean((comp.group(1) or comp.group(2)) if comp else "")
        loc = _LOC.search(card)
        date = _DATE.search(card)
        out.append(
            {
                "company": company,
                "title": _clean(title.group(1)),
                "location": _clean(loc.group(1)) if loc else "Israel",
                "url": link.group(1),
                "posted": date.group(1) if date else "",
                "source": "linkedin",
            }
        )
    return out


def search(query: str, location: str = "Israel", days: int = 7, start: int = 0) -> list[dict]:
    params = {"keywords": query, "location": location, "f_TPR": f"r{days * 86400}", "start": start, "position": 1, "pageNum": 0}
    url = f"{GUEST}?{urllib.parse.urlencode(params)}"
    status, body = get(url, headers=HEADERS, timeout=20, retries=1)
    LAST["requests"] += 1
    LAST["statuses"].append(status)
    if status != 200 or not body:
        LAST.setdefault("error", f"{status}: {(body or '')[:120]}")
        return []
    return parse(body)


def run(queries: list[str] | None = None) -> list[dict]:
    LAST.clear()
    LAST.update({"requests": 0, "results": 0, "statuses": []})
    out, seen = [], set()
    for q in queries or DEFAULT_QUERIES:
        for p in search(q):
            if p["url"] in seen:
                continue
            seen.add(p["url"])
            out.append(p)
        time.sleep(1.5)
    LAST["results"] = len(out)
    return out
