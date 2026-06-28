"""Ingest: run the collectors, store and dedup their Observations.

Pure orchestration. The store (Parquet upsert on obs_id) and the two-stage dedup
live in watchcore; this only wires Burgerreich's collectors into those shared
stages:

  collectors -> watchcore.store.ParquetStore.ingest (exact dedup on obs_id;
  stamps schema_version / first_seen / last_seen / content_hash)
  -> watchcore.dedup.assign_clusters (stage-one content_hash + stage-two MinHash
  near-dup, assigns cluster_id).

No store/dedup/query logic lives here.
"""
from __future__ import annotations

from pathlib import Path

from watchcore.dedup import assign_clusters
from watchcore.store import ParquetStore

from collectors import dvids, news

# Committed Parquet store. Lives outside docs/ (which GitHub Pages serves); the
# Phase 4 serve stage reads it to produce docs/data/*.json.
STORE_ROOT = Path(__file__).parent / "store"


def main() -> None:
    observations = dvids.collect() + news.collect()
    store = ParquetStore(STORE_ROOT)
    ing = store.ingest(observations)
    ded = assign_clusters(store)
    print(
        f"[ingest] {ing['rows_in']} collected, {ing['unique_obs_ids']} unique, "
        f"{len(ing['partitions_written'])} partitions written | "
        f"dedup: {ded['clusters']} clusters over {ded['rows']} rows "
        f"(threshold {ded['threshold']})"
    )


if __name__ == "__main__":
    main()
