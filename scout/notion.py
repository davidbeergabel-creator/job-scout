"""Write new postings into the Notion tracker (Companies + Roles).

Uses the Notion API with data sources (API version 2025-09-03). The Roles
row is created unscored (Status "New", Source "Scan"); the Claude scheduled
scan fills the five rubric scores, the rationale and the warm path.

Env: NOTION_TOKEN (internal integration shared with the "Job Search" page).
"""
from __future__ import annotations

import os
import time

from .http import post_json

API = "https://api.notion.com/v1"
VERSION = "2025-09-03"

COMPANIES_DS = os.environ.get("NOTION_COMPANIES_DS", "22a24b9c-cb4f-43b2-82d5-18d711f6710a")
ROLES_DS = os.environ.get("NOTION_ROLES_DS", "87363ba5-a3f3-4b9c-ab08-0d5d3c687748")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN'].strip()}",
        "Notion-Version": VERSION,
    }


def enabled() -> bool:
    return bool(os.environ.get("NOTION_TOKEN", "").strip())


def _rt(text: str) -> dict:
    return {"rich_text": [{"type": "text", "text": {"content": (text or "")[:1900]}}]}


def _query(ds: str, payload: dict) -> list[dict]:
    status, data = post_json(f"{API}/data_sources/{ds}/query", payload, _headers())
    if status != 200 or not isinstance(data, dict):
        return []
    return data.get("results", [])


def find_company(name: str) -> str | None:
    res = _query(COMPANIES_DS, {"filter": {"property": "Name", "title": {"equals": name}}, "page_size": 1})
    return res[0]["id"] if res else None


def create_company(p: dict) -> str | None:
    props = {
        "Name": {"title": [{"type": "text", "text": {"content": p["company"][:200]}}]},
        "Status": {"select": {"name": "Target"}},
        "Hiring signals": _rt(f"Posting found by job-scout on {p.get('found', '')}: {p.get('title', '')}"),
        "Notes": _rt(f"Auto-created by job-scout from {p.get('source', '')}."),
    }
    status, data = post_json(
        f"{API}/pages",
        {"parent": {"type": "data_source_id", "data_source_id": COMPANIES_DS}, "properties": props},
        _headers(),
    )
    return data.get("id") if status == 200 and isinstance(data, dict) else None


def role_exists(url: str, company: str, title: str) -> bool:
    if url:
        res = _query(ROLES_DS, {"filter": {"property": "Posting", "url": {"equals": url}}, "page_size": 1})
        if res:
            return True
    res = _query(
        ROLES_DS,
        {
            "filter": {
                "and": [
                    {"property": "Role", "title": {"equals": title}},
                    {"property": "Notes", "rich_text": {"contains": company}},
                ]
            },
            "page_size": 1,
        },
    )
    return bool(res)


def create_role(p: dict, company_id: str) -> str | None:
    notes = (
        f"Company: {p['company']} | Location: {p.get('location', '')} | Posted: {p.get('posted', '')} | "
        f"Source: {p.get('source', '')}\n{p.get('description', '')}"
    )
    props = {
        "Role": {"title": [{"type": "text", "text": {"content": p["title"][:200]}}]},
        "Company": {"relation": [{"id": company_id}]},
        "Status": {"select": {"name": "New"}},
        "Source": {"select": {"name": "Scan"}},
        "Notes": _rt(notes),
        "Next step": _rt("Unscored — the Claude scan scores it with the rubric and finds the warm path"),
    }
    if p.get("url"):
        props["Posting"] = {"url": p["url"][:2000]}
    if p.get("found"):
        props["Found on"] = {"date": {"start": p["found"]}}
    status, data = post_json(
        f"{API}/pages",
        {"parent": {"type": "data_source_id", "data_source_id": ROLES_DS}, "properties": props},
        _headers(),
    )
    return data.get("id") if status == 200 and isinstance(data, dict) else None


def push(postings: list[dict]) -> dict:
    """Create Companies/Roles rows for postings not already in Notion."""
    created, skipped, failed = 0, 0, 0
    cache: dict[str, str] = {}
    for p in postings:
        if role_exists(p.get("url", ""), p["company"], p["title"]):
            skipped += 1
            continue
        cid = cache.get(p["company"]) or find_company(p["company"]) or create_company(p)
        if not cid:
            failed += 1
            continue
        cache[p["company"]] = cid
        if create_role(p, cid):
            created += 1
        else:
            failed += 1
        time.sleep(0.35)  # Notion rate limit: ~3 requests/second
    return {"created": created, "skipped": skipped, "failed": failed}
