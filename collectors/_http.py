"""Shared HTTP fetch hardening for Burgerreich collectors.

curl_cffi with browser-TLS impersonation, a timeout, and retry with backoff.
This is project-local collector hardening (how Burgerreich talks to its
sources); it is NOT reusable-core, so it stays here rather than in watchcore.

A fetch that exhausts its retries raises RuntimeError. Collectors catch it and
log-and-skip so one bad fetch never kills a run.
"""
from __future__ import annotations

import time

from curl_cffi import requests

# Rung-1/2 browser headers, matching the ladder already used elsewhere in the
# repo. curl_cffi's `impersonate` supplies the matching TLS fingerprint.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml,application/xml,text/xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_text(
    url: str,
    *,
    timeout: int = 30,
    retries: int = 3,
    backoff: float = 1.5,
    impersonate: str = "chrome131",
) -> str:
    """GET `url` and return the response body, retrying transient failures.

    Raises RuntimeError if every attempt fails.
    """
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(
                url, headers=HEADERS, timeout=timeout, impersonate=impersonate
            )
            resp.raise_for_status()
            return resp.text
        except Exception as err:  # noqa: BLE001 — curl_cffi raises varied types
            last_err = err
            if attempt < retries - 1:
                time.sleep(backoff ** (attempt + 1))
    raise RuntimeError(f"fetch failed after {retries} attempts for {url}: {last_err}")
