"""DVIDS press-release collector.

One job: fetch DVIDS press releases, keep the CENTCOM-theater ones, and map each
to a validated watchcore Observation. No side effects — it does not store,
dedup, cluster, or serve. The store stage fills content_hash / cluster_id /
first_seen / last_seen; the detect stage refines obs_type and grade later.

Scope is built in three steps (all config-driven, see config.py):
  1. press-release filter  — keep only items whose guid is prefixed `news:`
  2. CENTCOM-theater filter — keep only items hitting the theater allowlist
  3. map survivors to Observation with obs_id via the watchcore helper
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import feedparser
from watchcore import Observation, Source

from . import config
from ._http import fetch_text

COLLECTOR = "dvids"

# Word-boundary alternation over the theater allowlist. The (?<![a-z0-9]) /
# (?![a-z0-9]) guards make "oman" not match "woman" and "isis" not match
# "crisis", while still matching hyphenated/spaced phrases.
_THEATER_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(re.escape(k) for k in config.CENTCOM_THEATER_KEYWORDS)
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text or "")).strip()


def _is_theater(text: str) -> bool:
    return _THEATER_RE.search(text) is not None


def _classify(text: str) -> str:
    """Rule-based obs_type. Domain-first, then posture, else other."""
    low = text.lower()
    for obs_type, keywords in config.OBS_TYPE_KEYWORDS.items():
        if any(kw in low for kw in keywords):
            return obs_type
    return "other"


def _observed_at(entry: feedparser.FeedParserDict) -> datetime | None:
    """Publish time as an aware UTC datetime. feedparser normalizes
    published_parsed to UTC, so build the datetime directly in UTC."""
    pp = entry.get("published_parsed")
    if not pp:
        return None
    return datetime(pp.tm_year, pp.tm_mon, pp.tm_mday,
                    pp.tm_hour, pp.tm_min, pp.tm_sec, tzinfo=timezone.utc)


def _to_observation(
    entry: feedparser.FeedParserDict, fetched_at: datetime
) -> Observation | None:
    """Map one feed entry to an Observation, or None if it is filtered out."""
    guid = entry.get("id", "") or ""
    if not guid.startswith(config.DVIDS_PRESS_RELEASE_GUID_PREFIX):
        return None  # not a press release (imagery / audio / untyped)

    title = _normalize(entry.get("title", ""))
    if not title:
        return None

    summary = _normalize(entry.get("summary", ""))
    if not _is_theater(f"{title} {summary}"):
        return None  # outside the CENTCOM theater

    observed_at = _observed_at(entry)
    if observed_at is None:
        return None  # no publish time -> cannot place on the timeline

    link = entry.get("link") or None
    # raw: the source payload, made JSON-safe (struct_time etc. -> str) so the
    # store can persist it unchanged downstream.
    raw = json.loads(json.dumps(dict(entry), default=str))

    return Observation(
        obs_id=Observation.make_id(
            COLLECTOR, observed_at, native_id=guid, url=link, title=title
        ),
        source=Source(
            collector=COLLECTOR,
            source_type="rss",
            publisher=None,  # DVIDS RSS carries no reliable per-item command
            url=link,
            native_id=guid,
        ),
        fetched_at=fetched_at,
        observed_at=observed_at,
        obs_type=_classify(f"{title} {summary}"),
        title=title,
        reliability=config.DVIDS_RELIABILITY,
        credibility=config.DVIDS_CREDIBILITY,
        raw=raw,
        summary=summary or None,
    )


def collect() -> list[Observation]:
    """Fetch the feed and return the CENTCOM-theater press releases as
    Observations. A failed fetch or a bad item is logged and skipped; it never
    raises out of here."""
    fetched_at = datetime.now(timezone.utc)
    try:
        body = fetch_text(config.DVIDS_FEED_URL)
    except Exception as err:  # noqa: BLE001
        print(f"[dvids] feed fetch failed: {err}")
        return []

    feed = feedparser.parse(body)
    observations: list[Observation] = []
    for entry in feed.entries:
        try:
            obs = _to_observation(entry, fetched_at)
        except Exception as err:  # noqa: BLE001 — one bad item must not kill the run
            print(f"[dvids] skipped item {entry.get('id', '?')}: {err}")
            continue
        if obs is not None:
            observations.append(obs)
    return observations


if __name__ == "__main__":
    obs = collect()
    print(f"[dvids] {len(obs)} CENTCOM-theater press releases")
    for o in obs[:10]:
        print(f"  {o.observed_at:%Y-%m-%d} {o.grade_code()} {o.obs_type:8} {o.title[:80]}")
