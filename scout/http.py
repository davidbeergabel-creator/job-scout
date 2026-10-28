"""Tiny HTTP helper on the standard library (no third-party dependencies)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

UA = "job-scout/1.0 (+https://github.com/davidbeergabel-creator/job-scout)"


def get(url: str, headers: dict | None = None, timeout: int = 20, retries: int = 2):
    """GET a URL. Returns (status, body_text). Never raises on HTTP errors."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            return e.code, body
        except Exception:  # network error, timeout, bad SSL
            if attempt < retries:
                time.sleep(1.0)
                continue
            return 0, ""
    return 0, ""


def get_json(url: str, headers: dict | None = None, timeout: int = 20):
    status, body = get(url, headers, timeout)
    if status != 200 or not body:
        return status, None
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 20):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace") or "null")
        except Exception:
            return e.code, None
    except Exception:
        return 0, None
