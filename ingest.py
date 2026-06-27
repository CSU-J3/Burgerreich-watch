"""Ingest: run the collectors, store and dedup their Observations.

One of the two files in this repo that touch the store (serve.py is the other).
It calls watchcore's store and dedup stages over the collector output:

  collectors -> watchcore.store.upsert (exact dedup on obs_id, stamps
  schema_version / first_seen / last_seen / content_hash) -> watchcore.dedup
  (MinHash near-dup, assigns cluster_id).

The store, dedup, and query logic itself lives in watchcore, not here. This
module only wires Burgerreich's collectors into those shared stages.

Placeholder until Phase 3 (watchcore store + dedup) and the collectors
(Phases 1-2) exist.
"""


def main() -> None:
    raise NotImplementedError("ingest wiring lands in Phase 3")


if __name__ == "__main__":
    main()
