"""Fetch postings from the public job-board APIs of the common applicant
tracking systems, and discover which ATS a company uses by probing slug
candidates.

Each fetcher returns a list of dicts:
  {company, title, location, url, posted, source, description}
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from .http import get, get_json, post_json

# ---------------------------------------------------------------- fetchers


def greenhouse(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    if status != 200 or not isinstance(data, dict) or "jobs" not in data:
        return None
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "company": company,
                "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""),
                "posted": (j.get("updated_at") or j.get("first_published") or "")[:10],
                "source": f"greenhouse:{slug}",
            }
        )
    return out


def lever(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if status != 200 or not isinstance(data, list):
        return None
    out = []
    for j in data:
        cats = j.get("categories") or {}
        ts = j.get("createdAt")
        posted = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat() if ts else ""
        out.append(
            {
                "company": company,
                "title": j.get("text", ""),
                "location": ", ".join(filter(None, [cats.get("location"), cats.get("team")])),
                "url": j.get("hostedUrl", ""),
                "posted": posted,
                "source": f"lever:{slug}",
            }
        )
    return out


def ashby(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    if status != 200 or not isinstance(data, dict) or "jobs" not in data:
        return None
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "company": company,
                "title": j.get("title", ""),
                "location": j.get("location", "") or ("Remote" if j.get("isRemote") else ""),
                "url": j.get("jobUrl", ""),
                "posted": (j.get("publishedAt") or "")[:10],
                "source": f"ashby:{slug}",
            }
        )
    return out


def workable(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://www.workable.com/api/accounts/{slug}?details=false")
    if status != 200 or not isinstance(data, dict) or "jobs" not in data:
        return None
    out = []
    for j in data.get("jobs", []):
        loc = ", ".join(filter(None, [j.get("city"), j.get("country")]))
        out.append(
            {
                "company": company,
                "title": j.get("title", ""),
                "location": loc or ("Remote" if j.get("telecommuting") else ""),
                "url": j.get("url", ""),
                "posted": (j.get("published_on") or j.get("created_at") or "")[:10],
                "source": f"workable:{slug}",
            }
        )
    return out


def smartrecruiters(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    if status != 200 or not isinstance(data, dict) or "content" not in data:
        return None
    out = []
    for j in data.get("content", []):
        loc = j.get("location") or {}
        out.append(
            {
                "company": company,
                "title": j.get("name", ""),
                "location": ", ".join(filter(None, [loc.get("city"), loc.get("country")])),
                "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                "posted": (j.get("releasedDate") or "")[:10],
                "source": f"smartrecruiters:{slug}",
            }
        )
    return out


def recruitee(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://{slug}.recruitee.com/api/offers/")
    if status != 200 or not isinstance(data, dict) or "offers" not in data:
        return None
    out = []
    for j in data.get("offers", []):
        out.append(
            {
                "company": company,
                "title": j.get("title", ""),
                "location": j.get("location", "") or j.get("city", ""),
                "url": j.get("careers_url", ""),
                "posted": (j.get("published_at") or j.get("created_at") or "")[:10],
                "source": f"recruitee:{slug}",
            }
        )
    return out


_COMEET_API = re.compile(r"careers-api/2\.0/company/([A-Z0-9.]+)/positions\?token=([0-9a-f]+)", re.I)
_COMEET_HREF = re.compile(r"https://www\.comeet\.com/jobs/([A-Za-z0-9-]+)/([A-Z0-9.]+)", re.I)


def comeet(careers_url: str, company: str) -> list[dict] | None:
    """Comeet has no guessable public API; read the company's careers page,
    find the embedded careers-api token, then call it."""
    status, page = get(careers_url)
    if status != 200 or not page:
        return None
    m = _COMEET_API.search(page)
    if not m:
        # Some sites embed only the hosted board link; follow it once.
        h = _COMEET_HREF.search(page)
        if not h:
            return None
        status, page = get(f"https://www.comeet.com/jobs/{h.group(1)}/{h.group(2)}")
        m = _COMEET_API.search(page or "")
        if not m:
            return None
    uid, token = m.group(1), m.group(2)
    status, data = get_json(f"https://www.comeet.com/careers-api/2.0/company/{uid}/positions?token={token}&details=false")
    if status != 200 or not isinstance(data, list):
        return None
    out = []
    for j in data:
        loc = j.get("location") or {}
        out.append(
            {
                "company": company,
                "title": j.get("name", ""),
                "location": ", ".join(filter(None, [loc.get("city"), loc.get("country")])) or loc.get("name", ""),
                "url": j.get("url_active_page", ""),
                "posted": (j.get("updated_time") or "")[:10],
                "source": f"comeet:{uid}",
            }
        )
    return out


FETCHERS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "ashby": ashby,
    "workable": workable,
    "smartrecruiters": smartrecruiters,
    "recruitee": recruitee,
}


def fetch(entry: dict) -> list[dict] | None:
    """entry: {name, ats, slug} or {name, ats: 'comeet', careers_url}."""
    ats = entry.get("ats")
    if ats == "comeet":
        return comeet(entry.get("careers_url", ""), entry["name"])
    fn = FETCHERS.get(ats)
    if not fn or not entry.get("slug"):
        return None
    return fn(entry["slug"], entry["name"])


# -------------------------------------------------------------- discovery

PROBE_ORDER = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee")


def slug_candidates(name: str) -> list[str]:
    base = name.lower().strip()
    base = re.sub(r"\b(ltd|inc|llc|gmbh|co|corp|technologies|technology|labs|ai|io|software|systems)\b\.?", "", base)
    base = re.sub(r"[^a-z0-9 ]+", " ", base).strip()
    joined = base.replace(" ", "")
    hyphen = base.replace(" ", "-")
    raw = re.sub(r"[^a-z0-9]+", "", name.lower())
    rawh = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    cands = [joined, hyphen, raw, rawh, joined + "ai", joined + "io", joined + "hq", joined + "careers"]
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def discover(name: str, careers_url: str | None = None) -> dict | None:
    """Try each ATS with each slug candidate; return a resolved entry or None."""
    if careers_url and "comeet" in careers_url:
        res = comeet(careers_url, name)
        if res is not None:
            return {"name": name, "ats": "comeet", "careers_url": careers_url}
    for ats in PROBE_ORDER:
        fn = FETCHERS[ats]
        for slug in slug_candidates(name):
            res = fn(slug, name)
            if res is not None:
                return {"name": name, "ats": ats, "slug": slug}
    if careers_url:
        res = comeet(careers_url, name)
        if res is not None:
            return {"name": name, "ats": "comeet", "careers_url": careers_url}
    return None
