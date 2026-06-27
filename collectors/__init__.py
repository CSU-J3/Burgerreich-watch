"""Burgerreich-watch collectors.

Each collector turns one source item into one valid watchcore ``Observation``
and touches nothing else: no storage, no dedup, no cluster computation. That is
the one rule from the schema spec. The store, dedup, and query stages live in
watchcore; ingest.py and serve.py are the only files here that touch them.

Collectors land in later phases:
  - dvids.py  (Phase 1)
  - news.py   (Phase 2)
  - config.py (feed list + grade baselines, Phase 1-2)
"""
