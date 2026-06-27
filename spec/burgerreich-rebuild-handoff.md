# Burgerreich-watch rebuild — Claude Code handoff

Hand this file to Claude Code as the build spec. It rebuilds Burgerreich-watch as the first project that imports `watchcore`. Work it in phases, one propose-plan / approve / read-diffs cycle each. Do not start a phase until the prior phase's acceptance check passes.

## Goal

Replace the dead `.mil` RSS pipeline with two live collectors (DVIDS, news RSS) that emit `Observation` records, store them in a Parquet store queried by DuckDB, dedup them, and serve the JSON the existing static dashboard reads. End state: the same dashboard, fed by a real time-series store instead of overwritten flat JSON, with provenance and an Admiralty grade on every record, charting on `observed_at` rather than scrape time.

## The boundary (read before writing anything)

`watchcore` is the engine. Burgerreich is one consumer. The split only works if reusable code lands in `watchcore` and only project-specific code stays in Burgerreich. Getting this wrong is the main failure mode for this build.

- **Goes into `watchcore`** (these become its first real pipeline stages, beyond the `Observation` model already there): the Parquet store with upsert-on-`obs_id`, the two-stage dedup, and the query helpers. Every future watch reuses them, so they do not belong in a repo named after one watch.
- **Stays in Burgerreich**: the two collectors, their source and grade config, the cron workflow, the view shapes, and the dashboard.
- **The one rule** from the schema spec: a collector turns one source item into one valid `Observation` and touches nothing else. No collector writes to the store, computes a cluster, or knows the feed shape. If a collector reaches for any of that, the concern belongs in `watchcore`.

When in doubt about where a piece goes, ask: would the next watch (Fleet-watch, the next one) need it? If yes, it goes in `watchcore`.

## Prerequisites

- `watchcore` pushed to `CSU-J3/watchcore`.
- Burgerreich depends on it: `watchcore[dedup] @ git+https://github.com/CSU-J3/watchcore` in `requirements.txt`.
- Python 3.10+. `curl_cffi` for collector fetches (browser impersonation, already in use).
- Dedup parameters are already settled in the schema spec: exact `content_hash` first, then MinHash over 3-word shingles with Jaccard `>= 0.7`. Reuse those, do not re-decide them.

## Phases

### Phase 0 — Restructure and depend on watchcore

- Add `watchcore[dedup]` as a dependency.
- Delete the duplicate root `index.html`. `site/index.html` is the only dashboard.
- Lay out the repo per the layout section below.
- Remove the old GitHub Pages deploy workflow. Burgerreich serves from Vercel now, which auto-deploys on each commit.

Acceptance: `python -c "import watchcore"` succeeds; the dashboard still serves from `site/` on Vercel with no behavior change.

### Phase 1 — DVIDS collector

Build `collectors/dvids.py`. One job: fetch DVIDS press releases, map each item to an `Observation`, return a list. No side effects.

Field mapping:

- `source`: `collector="dvids"`, `source_type="rss"` (switch to `"api"` only if the keyed DVIDS API gets wired later), `publisher` from the issuing command, `url` the item link, `native_id` the RSS guid or DVIDS asset id.
- `fetched_at` = now in UTC. `observed_at` = the item's publish date in UTC. Never conflate the two.
- `obs_type`: rule-based keyword map for now. Force-disposition items default to `"posture"`; clearly domain-specific items get `"naval"`, `"air"`, or `"ground"`; everything else `"other"`. Keep the classifier dumb; the detect stage refines later and is out of scope here.
- `title` and `summary` from the item, normalized.
- `reliability` / `credibility`: the configured baseline (DVIDS is official DoD, see the grade table). Read it from config, do not hardcode in the collector.
- `raw`: the untouched parsed item.
- `obs_id`: set it by calling the core helper `Observation.make_id(collector, observed_at, native_id=..., url=..., title=...)`. The collector calls the helper so the id scheme stays in `watchcore`; it does not invent a UUID and does not leave it blank. Leave `content_hash`, `cluster_id`, `first_seen`, and `last_seen` unset; the store stage fills those.

Hardening: `curl_cffi` with impersonation, a timeout, and retry with backoff. A failed item is logged and skipped, never allowed to kill the run.

Acceptance: run the collector standalone and get a list of `Observation`s that pass validation. Run it twice over the same items and the `obs_id`s are identical across runs.

### Phase 2 — News RSS collector

Build `collectors/news.py`. Same contract, different source.

- `source`: `collector="news_rss"`, `source_type="rss"`, `publisher` the outlet, `url` the link, `native_id` the guid.
- Pull from the configured feed list (Google News RSS queries for the watch's topics, or named defense outlets). The feed list lives in config, not in the collector body.
- Same rule-based `obs_type` map.
- `reliability` / `credibility`: aggregated-news baseline (lower than DVIDS, see the table). A named reputable outlet can be bumped per feed in config.
- Same hardening, same `obs_id`-via-helper rule, `raw` is the parsed item.

Acceptance: standalone run yields valid `Observation`s, and near-duplicate stories across feeds appear in the output. They get clustered in Phase 3, not here.

### Phase 3 — Store and dedup (build these in watchcore)

These land in `watchcore` because every watch needs them. Burgerreich imports them.

`watchcore/store.py`:

- Persisted store is Parquet, partitioned by `observed_at` date (`observed_at_date=YYYY-MM-DD/`), columns per the schema spec's storage mapping, with `source`, `geo`, `entities`, and `raw` as JSON. The partitioned Parquet is what gets committed; DuckDB reads it directly, so there is no separate database file to commit and no single blob getting rewritten every run.
- Ingest is an upsert keyed on `obs_id`: read the affected date partition, merge by `obs_id`, write it back. Re-ingesting the same item updates `last_seen` and never duplicates. This is stage-one (exact) dedup, for free.
- On write: stamp `schema_version`, set `first_seen` when the row is new, set `last_seen` always, and compute `content_hash` via `Observation.make_content_hash`.

`watchcore/dedup.py`:

- Stage-two near-dup. Build a MinHash signature over 3-word shingles of the normalized `title` plus `summary`, run MinHashLSH, and group records with Jaccard `>= 0.7` into one `cluster_id`. Uses `datasketch`, already in the `dedup` extra.
- Assign and propagate `cluster_id`. The highest-grade member can represent the cluster downstream.

Acceptance: ingest the same batch twice and the partition row count is unchanged. Two near-identical stories from different feeds share a `cluster_id`. `content_hash` is equal for text that normalizes the same.

### Phase 4 — Serve (query the store, write the JSON the dashboard reads)

The queries are reusable and belong in `watchcore`; the view shapes are Burgerreich's. Put the query helpers in `watchcore` and the view assembly in Burgerreich's `serve.py`.

- Query the store and write the JSON `site/index.html` already fetches: `feed.json` (the main reverse-chronological feed) and the typed views, derived by filtering on `obs_type`. Drop any view you no longer want rather than faking data for it.
- The dashboard keeps fetching `data/feed.json` by relative path, so the frontend barely changes. If a view's shape changed, edit the fetch in `site/index.html` only.

Acceptance: `serve.py` writes valid JSON, the dashboard renders from it locally, and the time axis is driven by `observed_at`.

### Phase 5 — Cron wiring

- One GitHub Actions workflow on the existing 6-hour schedule: run both collectors, ingest into the store, run dedup, run serve, then commit the updated Parquet partitions and the generated JSON.
- Vercel auto-deploys on the commit, same as it does today.

Acceptance: the scheduled run completes the full chain end to end, and a manual dispatch produces updated partitions, updated JSON, and a green Vercel deploy.

## Grade baselines (config, not hardcoded)

| Collector | reliability | credibility | reason |
|---|---|---|---|
| `dvids` | B | 2 | official DoD release |
| `news_rss` | C | 3 | aggregated reporting, varies by outlet |

Per-feed override is allowed (bump a named reputable outlet). Raising a grade when a second source corroborates is the detect stage's job and is out of scope here.

## Proposed repo layout (Burgerreich)

```
Burgerreich-watch/
  collectors/
    __init__.py
    dvids.py          # emits Observation[], no side effects
    news.py           # emits Observation[], no side effects
    config.py         # feed URLs + per-collector grade baselines
  ingest.py           # calls watchcore store + dedup over collector output
  serve.py            # calls watchcore queries, writes site/data/*.json
  site/
    index.html        # the only dashboard (root duplicate deleted)
    data/             # generated JSON, committed
  .github/workflows/
    collect.yml       # 6-hour cron: collect -> ingest -> dedup -> serve -> commit
  requirements.txt    # includes watchcore[dedup]
```

`ingest.py` and `serve.py` are the only files that touch the store. Collectors stay thin.

## Out of scope (later passes)

- The detect stage: movement and change detection, corroboration grade bumps.
- Additional collectors (AIS, ADS-B).
- A store interface that swaps DuckDB/Parquet for SQLite per project. `watchcore` can grow that when a second consumer needs it, not now.

## Definition of done

- Both collectors emit validation-passing `Observation`s with `fetched_at` and `observed_at` kept separate and the correct baseline grades.
- Re-running ingest does not duplicate (`obs_id` idempotency holds), and near-dups share a `cluster_id`.
- The dashboard renders from store-derived JSON and charts on `observed_at`.
- The 6-hour cron runs the full chain and deploys on Vercel.
- Nothing reusable was written inside Burgerreich that belonged in `watchcore`.

## One decision baked in

The persisted store is partitioned Parquet committed to the repo, with DuckDB reading it directly, rather than a committed DuckDB file. This keeps history durable across runs while making each run append mostly new date-partition files instead of rewriting one growing blob. If you would rather persist the store elsewhere (an artifact, external object storage), change it in Phase 3 and Phase 5; nothing upstream of the store depends on the choice.
