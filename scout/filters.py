"""Title, seniority and location filters for the job scout.

The net is deliberately wide: anything senior in sales, partnerships, GTM,
growth, business, operations, AI or general management in Israel. Scoring
(the rubric) is done later by Claude; this module only decides what gets
collected.
"""
from __future__ import annotations

import html
import re

SENIORITY = re.compile(
    r"\b(vp|vice[\s-]president|svp|evp|chief|c[a-z]o|head of|head,|director|general manager|"
    r"\bgm\b|managing director|president|founder|co-founder|country manager|site lead|"
    r"\bcro\b|\bcbo\b|\bcoo\b|\bcmo\b|\bcpo\b|\bcco\b|\bcso\b)\b",
    re.I,
)

DOMAIN = re.compile(
    r"\b(sales|partnership|partnerships|alliance|alliances|business development|\bbd\b|bizdev|"
    r"go[\s-]to[\s-]market|gtm|growth|revenue|commercial|operations|ops|ecosystem|channel|channels|"
    r"customer|customers|client|clients|account|accounts|marketing|product marketing|strategy|"
    r"strategic|business|israel|emea|international|global|enterprise|ai|artificial intelligence|"
    r"transformation|practice|services|solutions|delivery|expansion|market|markets|"
    r"chief business|chief revenue|chief operating|chief commercial|general manager)\b",
    re.I,
)

# Roles that match the seniority regex but are not for David.
EXCLUDE = re.compile(
    r"\b(engineering|engineer|r&d|research|software|backend|frontend|full[\s-]stack|devops|sre|"
    r"security research|data science|machine learning engineer|ml engineer|qa|quality assurance|"
    r"finance|financial|accounting|controller|legal|counsel|hr|human resources|people|talent|"
    r"recruit|design|ux|ui|it\b|infrastructure|hardware|algorithm|architect|developer|"
    r"scientist|clinical|regulatory|medical director|nurse|physician|intern|student|junior)\b",
    re.I,
)

ISRAEL = re.compile(
    r"\b(israel|tel[\s-]aviv|herzliya|herzliyya|ra'?anana|raanana|haifa|jerusalem|petah[\s-]tikva|"
    r"netanya|rosh[\s-]ha'?ayin|yokneam|yoqneam|be'?er[\s-]sheva|hod[\s-]hasharon|kfar[\s-]saba|"
    r"ramat[\s-]gan|bnei[\s-]brak|rehovot|caesarea|modi'?in|hadera|holon|or[\s-]yehuda|"
    r"airport city|\bil\b|ils)\b",
    re.I,
)


def is_senior(title: str) -> bool:
    return bool(SENIORITY.search(title or ""))


C_LEVEL_IN_DOMAIN = re.compile(r"\b(coo|cro|cbo|cco|cmo|gm|general manager|managing director|country manager|site lead)\b", re.I)


def in_domain(title: str) -> bool:
    t = title or ""
    return bool(DOMAIN.search(t) or C_LEVEL_IN_DOMAIN.search(t))


def is_excluded(title: str) -> bool:
    t = title or ""
    # "Director of Sales Engineering" is excluded, "VP Sales" is not.
    return bool(EXCLUDE.search(t)) and not re.search(
        r"\b(vp|head of|chief|director)\s+(of\s+)?(sales|partnerships?|alliances|business development|"
        r"gtm|go[\s-]to[\s-]market|growth|revenue|customer success|operations)\b",
        t,
        re.I,
    )


# "IL" is also Illinois: a US-flavoured location only counts if "Israel" is spelled out.
NOT_ISRAEL = re.compile(
    r"\b(united states|usa|u\.s\.|illinois|chicago|us[\s-]+remote|remote[\s-]+us|north america)\b", re.I
)


def in_israel(location: str, remote_ok: bool = True) -> bool:
    loc = location or ""
    if NOT_ISRAEL.search(loc) and not re.search(r"\bisrael\b", loc, re.I):
        return False
    if ISRAEL.search(loc):
        return True
    return False


def relevant(title: str, location: str) -> tuple[bool, str]:
    """Return (keep, reason)."""
    if not title:
        return False, "no title"
    if not is_senior(title):
        return False, "not senior"
    if is_excluded(title):
        return False, "excluded function"
    if not in_domain(title):
        return False, "outside domain"
    if location and not in_israel(location):
        return False, "not Israel"
    return True, "ok"


_TAGS = re.compile(r"<[^>]+>")


def clean_title(title: str) -> str:
    """Some boards wrap titles in HTML (e.g. '<p>\nVP Operations \n</p>')."""
    t = html.unescape(_TAGS.sub(" ", title or ""))
    return re.sub(r"\s+", " ", t).strip()


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def dedupe_key(company: str, title: str) -> str:
    return f"{normalize(company)}|{normalize(title)}"
