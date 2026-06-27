"""Collector configuration: feed URLs and per-collector grade baselines.

Project-specific, so it stays in Burgerreich (not watchcore). Populated in
Phase 1-2:

  - DVIDS source config and its baseline grade (B / 2, official DoD release).
  - News RSS feed list and the aggregated-news baseline (C / 3), with per-feed
    overrides allowed for named reputable outlets.

Grade baselines come from the handoff's grade table; they are config values,
never hardcoded inside a collector body.
"""

# TODO(Phase 1): DVIDS_CONFIG with baseline reliability=B, credibility=2.
# TODO(Phase 2): NEWS_FEEDS list with aggregated baseline reliability=C,
#                credibility=3, plus per-feed grade overrides.
