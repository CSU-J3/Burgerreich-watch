"""News RSS collector.

Pulls the configured CENTCOM-theater RSS feeds (Google News theater queries plus
named defense outlets), maps each item to a watchcore Observation, and returns
the list. Pure — no store, dedup, or clustering. Near-duplicate stories across
feeds come out unclustered (cluster_id=None); Phase 3 clusters them in watchcore.

The feed queries define scope, so no client-side theater allowlist is applied
here (unlike DVIDS, whose feed is a DoD-wide firehose). obs_type uses the same
shared classifier and grades come from each feed's config baseline/override.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import feedparser
from watchcore import Observation, Source

from . import config
from ._common import classify, normalize
from ._http import fetch_text

COLLECTOR = "news_rss"


def _observed_at(entry: feedparser.FeedParserDict) -> datetime | None:
    """Publish time as an aware UTC datetime (feedparser normalizes to UTC)."""
    pp = entry.get("published_parsed")
    if not pp:
        return None
    return datetime(pp.tm_year, pp.tm_mon, pp.tm_mday,
                    pp.tm_hour, pp.tm_min, pp.tm_sec, tzinfo=timezone.utc)


def _publisher(entry: feedparser.FeedParserDict, feed_name: str) -> str:
    """Outlet from the Google News <source> element; fall back to the feed name
    only for direct-outlet feeds that carry no <source> (e.g. USNI). This never
    masks an unresolved Google News source — those always populate."""
    src = entry.get("source")
    title = src.get("title") if isinstance(src, dict) else None
    return (title or "").strip() or feed_name


def _to_observation(
    entry: feedparser.FeedParserDict, feed: dict, fetched_at: datetime
) -> Observation | None:
    """Map one feed entry to an Observation, or None if it cannot be placed."""
    title = normalize(entry.get("title", ""))
    if not title:
        return None

    observed_at = _observed_at(entry)
    if observed_at is None:
        return None  # no publish time -> cannot place on the timeline

    summary = normalize(entry.get("summary", ""))
    link = entry.get("link") or None
    guid = entry.get("id") or link or title
    raw = json.loads(json.dumps(dict(entry), default=str))

    return Observation(
        obs_id=Observation.make_id(
            COLLECTOR, observed_at, native_id=guid, url=link, title=title
        ),
        source=Source(
            collector=COLLECTOR,
            source_type="rss",
            publisher=_publisher(entry, feed["name"]),
            url=link,
            native_id=guid,
        ),
        fetched_at=fetched_at,
        observed_at=observed_at,
        obs_type=classify(f"{title} {summary}"),
        title=title,
        reliability=feed.get("reliability", config.NEWS_RELIABILITY),
        credibility=feed.get("credibility", config.NEWS_CREDIBILITY),
        raw=raw,
        summary=summary or None,
    )


def collect() -> list[Observation]:
    """Fetch every configured feed and return all items as Observations. A failed
    feed or a bad item is logged and skipped; it never raises out of here."""
    fetched_at = datetime.now(timezone.utc)
    observations: list[Observation] = []
    for feed in config.NEWS_FEEDS:
        try:
            body = fetch_text(feed["url"])
        except Exception as err:  # noqa: BLE001 — one bad feed must not kill the run
            print(f"[news_rss] feed fetch failed ({feed['name']}): {err}")
            continue
        parsed = feedparser.parse(body)
        for entry in parsed.entries:
            try:
                obs = _to_observation(entry, feed, fetched_at)
            except Exception as err:  # noqa: BLE001 — one bad item must not kill the run
                print(f"[news_rss] skipped item ({feed['name']}, {entry.get('id', '?')}): {err}")
                continue
            if obs is not None:
                observations.append(obs)
    return observations


if __name__ == "__main__":
    obs = collect()
    print(f"[news_rss] {len(obs)} items from {len(config.NEWS_FEEDS)} feeds")
    for o in obs[:10]:
        print(f"  {o.observed_at:%Y-%m-%d} {o.grade_code()} {o.obs_type:8} "
              f"[{o.source.publisher}] {o.title[:70]}")
