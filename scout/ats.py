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

# company -> "ats:status" for boards whose last fetch failed (read by the scan summary)
ERRORS: dict[str, str] = {}


def _fail(company: str, ats_name: str, status) -> None:
    ERRORS[company] = f"{ats_name}:{status}"


# ---------------------------------------------------------------- fetchers


def greenhouse(slug: str, company: str) -> list[dict] | None:
    status, data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false")
    if status != 200 or not isinstance(data, dict) or "jobs" not in data:
        _fail(company, "greenhouse", status)
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
        _fail(company, "lever", status)
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
        _fail(company, "ashby", status)
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
        _fail(company, "workable", status)
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
        _fail(company, "smartrecruiters", status)
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
        _fail(company, "recruitee", status)
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
_COMEET_HREF = re.compile(r"https://www\.comeet\.com?/jobs/([A-Za-z0-9-]+)/([A-Z0-9.]+)", re.I)
# The embeddable widget: careers.js?company=X&token=<hex>&uid=<A1.B23>
# careers.js?company=X&token=<hex>&uid=<A1.B23>   or   COMEET.init({"token": "<HEX>", "company-uid": "A1.B23", ...})
_COMEET_UID = re.compile(r"""(?:[?&]uid=|["']?(?:company[-_]?)?uid["']?\s*:\s*["'])([A-Z0-9]+\.[A-Z0-9]+)""", re.I)
_COMEET_TOKEN = re.compile(r"""(?:[?&]token=|["']?token["']?\s*:\s*["'])([0-9A-Fa-f]{16,})""", re.I)
# The Comeet WordPress plugin renders positions server-side as /careers/co/<location>/<UID>/<slug>/all links.
_COMEET_WP = re.compile(r"""href=["']([^"']*/co/([a-z0-9-]+)/([A-Z0-9]{2}\.[A-Z0-9]{3})/([a-z0-9-]+)/all/?)["']""", re.I)


def _comeet_creds(page: str) -> tuple[str, str] | None:
    m = _COMEET_API.search(page or "")
    if m:
        return m.group(1), m.group(2)
    u, t = _COMEET_UID.search(page or ""), _COMEET_TOKEN.search(page or "")
    if u and t and "comeet" in (page or "").lower():
        return u.group(1), t.group(1)
    return None


def _comeet_wp(page: str, careers_url: str, company: str) -> list[dict] | None:
    """Parse positions rendered by the Comeet WordPress plugin (no API token needed)."""
    seen, out = set(), []
    for m in _COMEET_WP.finditer(page or ""):
        href, loc, uid, slug = m.groups()
        if uid in seen:
            continue
        seen.add(uid)
        if href.startswith("/"):
            root = re.match(r"https?://[^/]+", careers_url)
            href = (root.group(0) if root else "") + href
        out.append(
            {
                "company": company,
                "title": slug.replace("-", " ").title(),
                "location": loc.replace("-", " ").title(),
                "url": href,
                "posted": "",
                "source": f"comeet-wp:{uid}",
            }
        )
    return out or None


def comeet(careers_url: str, company: str) -> list[dict] | None:
    """Comeet has no guessable public API; read the company's careers page,
    find the embedded careers-api token, then call it."""
    status, page = get(careers_url, timeout=12)
    if status != 200 or not page:
        _fail(company, "comeet-page", status)
        return None
    creds = _comeet_creds(page)
    if not creds:
        wp = _comeet_wp(page, careers_url, company)
        if wp:
            return wp
        # Some sites embed only the hosted board link; follow it once.
        h = _COMEET_HREF.search(page)
        if not h:
            _fail(company, "comeet-page", "no token")
            return None
        status, page = get(f"https://www.comeet.com/jobs/{h.group(1)}/{h.group(2)}", timeout=12)
        creds = _comeet_creds(page)
        if not creds:
            _fail(company, "comeet-page", "no token")
            return None
    uid, token = creds
    data = None
    for host in ("www.comeet.co", "www.comeet.com"):
        status, data = get_json(f"https://{host}/careers-api/2.0/company/{uid}/positions?token={token}&details=false")
        if status == 200 and isinstance(data, list):
            break
    if not isinstance(data, list):
        # API refused the token: fall back to the positions rendered in the page (WordPress plugin).
        wp = _comeet_wp(page, careers_url, company)
        if wp:
            return wp
        _fail(company, "comeet-api", status)
        return None
    out = []
    for j in data:
        loc = j.get("location") or {}
        out.append(
            {
                "company": company,
                "title": j.get("name", ""),
                "location": ", ".join(filter(None, [loc.get("city"), loc.get("country")])) or loc.get("name", ""),
                "url": j.get("url_active_page") or j.get("url_comeet_hosted_page") or j.get("position_url") or "",
                "posted": (j.get("time_updated") or j.get("updated_time") or j.get("time_created") or "")[:10],
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


# ATS fingerprints found in a company's own careers page (embeds / links).
_SNIFF = [
    ("greenhouse", re.compile(r"(?:boards|job-boards|boards-api)\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?([a-z0-9-]+)", re.I)),
    ("greenhouse", re.compile(r"greenhouse\.io/embed/job_board/js\?for=([a-z0-9-]+)", re.I)),
    ("lever", re.compile(r"jobs\.lever\.co/([a-z0-9-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-z0-9-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([a-z0-9-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9]+)", re.I)),
    ("recruitee", re.compile(r"https?://([a-z0-9-]+)\.recruitee\.com", re.I)),
]
_CAREERS_LINK = re.compile(r"""href=["']([^"']*(?:career|jobs|join-us|joinus|work-with-us|open-positions|positions)[^"']*)["']""", re.I)
_BAD_SLUGS = {"embed", "www", "jobs", "careers", "api", "boards", "job-boards", "v1"}


def website_candidates(name: str) -> list[str]:
    base = re.sub(r"\b(ltd|inc|llc|gmbh|co|corp|israel)\b\.?", "", name.lower())
    joined = re.sub(r"[^a-z0-9]+", "", base)
    if not joined:
        return []
    return [f"https://www.{joined}.com", f"https://{joined}.com", f"https://www.{joined}.io", f"https://{joined}.ai", f"https://www.{joined}.co.il"]


def sniff_page(page: str) -> tuple[str, str] | None:
    """Return (ats, slug) if a known ATS is embedded or linked in the page."""
    for ats_name, rx in _SNIFF:
        for m in rx.finditer(page or ""):
            slug = m.group(1)
            if slug.lower() not in _BAD_SLUGS:
                return ats_name, slug
    return None


_SCRIPT_SRC = re.compile(r"""<script[^>]+src=["']([^"']+\.js[^"']*)["']""", re.I)


def _page_hit(page: str, url: str, name: str) -> dict | None:
    hit = sniff_page(page)
    if hit:
        ats_name, slug = hit
        res = FETCHERS[ats_name](slug, name)
        if res is not None and (ats_name not in ("smartrecruiters", "workable") or res):
            return {"name": name, "ats": ats_name, "slug": slug}
    if _comeet_creds(page) or _COMEET_HREF.search(page) or _COMEET_WP.search(page):
        if comeet(url, name) is not None:
            return {"name": name, "ats": "comeet", "careers_url": url}
    return None


def _script_urls(page: str, base: str) -> list[str]:
    root = re.match(r"https?://[^/]+", base)
    root = root.group(0) if root else ""
    out = []
    for m in _SCRIPT_SRC.finditer(page or ""):
        src = html.unescape(m.group(1))
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            src = root + src
        elif not src.startswith("http"):
            src = base.rsplit("/", 1)[0] + "/" + src
        if root and src.startswith(root) and src not in out:
            out.append(src)
    # Bundles that mention careers/jobs first, then the rest.
    out.sort(key=lambda u: (not re.search(r"career|job|position", u, re.I), len(u)))
    return out[:6]


def sniff_site(name: str, website: str | None = None, careers_url: str | None = None) -> dict | None:
    """Fetch the company's careers page(s) (and their JS bundles) and look for an embedded ATS."""
    pages: list[str] = [careers_url] if careers_url else []
    sites = [website] if website else website_candidates(name)
    for site in sites:
        status, home = get(site, timeout=8, retries=0)
        if status != 200 or not home or len(home) < 2000:
            continue
        hit = _page_hit(home, site, name)
        if hit:
            return hit
        cand = [site.rstrip("/") + "/careers"]
        for m in _CAREERS_LINK.finditer(home):
            href = html.unescape(m.group(1))
            if href.startswith("/"):
                href = site.rstrip("/") + href
            if href.startswith("http") and "wp-json" not in href and not href.endswith((".css", ".png", ".jpg", ".svg")) and href not in cand:
                cand.append(href)
        pages.extend(c for c in cand[:3] if c not in pages)
    budget = 12
    for url in pages:
        if budget <= 0:
            break
        budget -= 1
        status, page = get(url, timeout=10, retries=0)
        if status != 200 or not page:
            continue
        hit = _page_hit(page, url, name)
        if hit:
            return hit
        # JS-rendered careers pages (Nuxt/Next): the board token usually sits in a same-origin bundle.
        for js_url in _script_urls(page, url)[:4]:
            if budget <= 0:
                break
            budget -= 1
            st, js = get(js_url, timeout=8, retries=0)
            if st == 200 and js:
                hit = _page_hit(js, url, name)
                if hit:
                    return hit
    return None


def discover(name: str, careers_url: str | None = None, website: str | None = None) -> dict | None:
    """Try each ATS with each slug candidate, then the company's own site; return a resolved entry or None."""
    if careers_url:
        res = comeet(careers_url, name)
        if res is not None:
            return {"name": name, "ats": "comeet", "careers_url": careers_url}
    for ats_name in PROBE_ORDER:
        fn = FETCHERS[ats_name]
        for slug in slug_candidates(name):
            res = fn(slug, name)
            if res is None:
                continue
            # SmartRecruiters (any slug) and Workable (some slugs) answer 200 + [] for unknown accounts:
            # only a non-empty board proves the slug.
            if ats_name in ("smartrecruiters", "workable") and not res:
                continue
            return {"name": name, "ats": ats_name, "slug": slug}
    return sniff_site(name, website, careers_url)


# ------------------------------------------------------------- diagnostics

_KW = ("comeet", "greenhouse", "lever.co", "ashby", "workable", "smartrecruiters", "recruitee", "bamboohr", "jazz", "teamtailor",
       "personio", "workday", "successfactors", "icims", "taleo", "rippling", "gem.com", "jobvite", "breezy", "freshteam", "zoho")


def _show_page(url: str, label: str = "GET") -> str | None:
    status, page = get(url, timeout=15)
    print(f"{label} {url} -> {status}, {len(page or '')} chars")
    if not page:
        return None
    print("  sniff:", sniff_page(page), " comeet creds:", _comeet_creds(page), " hosted:", bool(_COMEET_HREF.search(page)),
          " comeet-wp links:", len(_COMEET_WP.findall(page)))
    low = page.lower()
    for kw in _KW:
        start, shown = 0, 0
        while shown < 4:
            i = low.find(kw, start)
            if i < 0:
                break
            print(f"  '{kw}' @{i}: ...{page[max(0, i-100):i+220]!r}")
            start, shown = i + len(kw), shown + 1
    return page


def diagnose(target: str, careers_url: str | None = None) -> None:
    """Print what discovery sees for a URL or a company name (run in Actions, where the network is open)."""
    if target.startswith("http"):
        _show_page(target)
        return
    if target.startswith("jsearch:"):
        from . import jsearch
        jsearch.probe(target[len("jsearch:"):].strip())
        return
    name = target
    print(f"discover({name!r}) slugs={slug_candidates(name)}")
    for ats_name in PROBE_ORDER:
        hits = []
        for slug in slug_candidates(name):
            res = FETCHERS[ats_name](slug, name)
            hits.append(f"{slug}={'-' if res is None else len(res)}")
        print(f"  {ats_name}: {' '.join(hits)}")
    for site in website_candidates(name):
        status, home = get(site, timeout=8, retries=0)
        print(f"  site {site} -> {status}, {len(home or '')} chars")
        if status != 200 or not home:
            continue
        links = []
        for m in _CAREERS_LINK.finditer(home):
            href = html.unescape(m.group(1))
            if href.startswith("/"):
                href = site.rstrip("/") + href
            if href.startswith("http") and "wp-json" not in href and href not in links:
                links.append(href)
        for url in ([site.rstrip("/") + "/careers"] + links)[:4]:
            _show_page(url, "   page")
        break
    if careers_url:
        _show_page(careers_url, "careers_url")
