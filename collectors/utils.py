"""
Shared utilities for Burgerreich Watch collectors.
"""

import json
import os
import hashlib
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MAX_ITEMS = 50  # Keep last 50 items per feed


def make_id(text: str) -> str:
    """Generate a short deterministic ID from text."""
    return hashlib.md5(text.encode()).hexdigest()[:12]


def normalize_date(date_str: str) -> str:
    """Try to normalize a date string to ISO format."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # feedparser provides time_struct; handle string fallback
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return date_str


def load_existing(filename: str) -> list:
    """Load existing JSON data file, return empty list if missing."""
    filepath = DATA_DIR / filename
    if filepath.exists():
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_data(filename: str, items: list):
    """Save items to JSON, deduplicating by ID and capping at MAX_ITEMS."""
    existing = load_existing(filename)

    # Merge: new items take priority
    seen_ids = set()
    merged = []
    for item in items + existing:
        item_id = item.get("id", make_id(item.get("title", "")))
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            merged.append(item)

    # Sort by date descending, cap
    merged.sort(key=lambda x: x.get("date", ""), reverse=True)
    merged = merged[:MAX_ITEMS]

    filepath = DATA_DIR / filename
    with open(filepath, "w") as f:
        json.dump(merged, f, indent=2)

    print(f"[OK] {filename}: {len(merged)} items saved")


# Rung 1: realistic browser headers. Mirrors Chrome 132 on macOS.
# Same header set as collect_osint.py — .mil RSS endpoints (centcom, eucom,
# pacom, africom, stratcom) sit on the same DoD CDN that TLS-fingerprints the
# leadership pages, so the same ladder applies.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

try:
    from curl_cffi import requests as _cffi_requests
    _HAVE_CURL_CFFI = True
except ImportError:
    _HAVE_CURL_CFFI = False


def _fetch_text(url: str, timeout: int = 30) -> str:
    """Rung 1 (requests + browser headers) → Rung 2 (curl_cffi chrome131).
    Raises RuntimeError if both rungs fail."""
    import requests

    rung1_err = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        rung1_err = e
        print(f"  ↻ Rung 1 failed ({type(e).__name__}: {str(e)[:80]}); escalating to curl_cffi")

    if not _HAVE_CURL_CFFI:
        raise RuntimeError(f"curl_cffi unavailable; rung 1 failed: {rung1_err}")

    try:
        resp = _cffi_requests.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome131")
        resp.raise_for_status()
        return resp.text
    except Exception as rung2_err:
        raise RuntimeError(f"Rung 1+2 both failed: rung1={rung1_err}; rung2={rung2_err}")


def fetch_rss(url: str, timeout: int = 30) -> list:
    """Fetch and parse an RSS feed, return list of entries."""
    import feedparser
    try:
        body = _fetch_text(url, timeout=timeout)
        return feedparser.parse(body).entries
    except Exception as e:
        print(f"[ERR] RSS fetch failed for {url}: {e}")
        return []


def fetch_page(url: str, timeout: int = 30) -> str:
    """Fetch a web page, return HTML text."""
    try:
        return _fetch_text(url, timeout=timeout)
    except Exception as e:
        print(f"[ERR] Page fetch failed for {url}: {e}")
        return ""


def classify_tag(title: str, summary: str = "") -> str:
    """Auto-classify an item into a feed tag based on keywords."""
    text = (title + " " + summary).lower()
    if any(w in text for w in ["strike", "engage", "intercept", "attack", "airstrike", "missile"]):
        return "alert"
    if any(w in text for w in ["ship", "carrier", "fleet", "naval", "maritime", "vessel", "navy"]):
        return "naval"
    if any(w in text for w in ["aircraft", "bomber", "fighter", "squadron", "air force", "flight", "f-35", "f-16", "b-52", "b-2"]):
        return "air"
    if any(w in text for w in ["exercise", "drill", "training", "bilateral", "multilateral", "balikatan", "cope"]):
        return "exercise"
    if any(w in text for w in ["deploy", "posture", "reposition", "rotate", "surge", "reinforce"]):
        return "posture"
    if any(w in text for w in ["soldier", "troop", "brigade", "battalion", "infantry", "army", "marine"]):
        return "ground"
    return "posture"
