"""Serve: query the store and write the JSON the dashboard reads.

The query helpers are reusable and live in watchcore; the view *shape* is
Burgerreich's and lives here. This module asks watchcore for the stored
Observations (reverse-chronological on ``observed_at``, each near-dup cluster
collapsed to its highest-grade representative) and writes the one view the
dashboard actually fetches:

  - docs/data/feed.json   (main reverse-chronological feed, grade on every item)

Time axis: ``observed_at`` drives both the feed order and the dashboard chart,
never fetch time.

Orphaned views are deliberately NOT produced here (Phase 4 decision). The store
has no Observation equivalent for casualty tallies, equipment-loss counts, a
Middle-East troop headcount, or the Doomsday Clock, so those views are dropped
rather than faked — and their dashboard panels are retired in index.html rather
than left showing frozen seed numbers as if live. fleet.json (vessel positions,
pending an AIS collector) and commanders.json (a COCOM org-chart, pending a
roster scrape) are kept as documented stubs, not regenerated here.

No store, DuckDB, or query logic lives in this file — only the feed's field
mapping.
"""
from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from watchcore.query import select_observations
from watchcore.store import ParquetStore

STORE_ROOT = Path(__file__).parent / "store"
DATA_DIR = Path(__file__).parent / "docs" / "data"

# The whole watch is CENTCOM-theater scoped (DVIDS theater allowlist + CENTCOM
# news queries), so every stored observation files under the dashboard's CENTCOM
# tab. This is an honest constant, not a faked field — there is no other theater
# in the store to disambiguate.
COCOM = "centcom"


def _iso_utc(dt) -> str:
    """``observed_at`` is stored naive-UTC; emit an explicit ``...Z`` so the
    dashboard's ``.replace('Z', ' UTC')`` formats it correctly."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _source(row) -> dict:
    src = row["source"]
    return json.loads(src) if isinstance(src, str) else (src or {})


def _feed_item(row) -> dict:
    src = _source(row)
    return {
        "date": _iso_utc(row["observed_at"]),   # time axis + reverse-chron order
        "title": row["title"],
        "url": src.get("url"),
        "source": src.get("publisher") or src.get("collector"),
        "tag": row["obs_type"],
        "cocom": COCOM,
        # Provenance + Admiralty grade — rendered per item, the thing that makes
        # this a graded intel feed rather than a plain news list.
        "grade": f"{row['reliability']}{int(row['credibility'])}",
        "reliability": row["reliability"],
        "credibility": int(row["credibility"]),
    }


def build_feed() -> list[dict]:
    store = ParquetStore(STORE_ROOT)
    rows = select_observations(store, collapse_clusters=True, reverse_chron=True)
    return [_feed_item(r) for r in rows]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    feed = build_feed()
    out = DATA_DIR / "feed.json"
    out.write_text(json.dumps(feed, indent=2), encoding="utf-8")
    print(f"[serve] wrote {len(feed)} feed items to {out}")


if __name__ == "__main__":
    main()
