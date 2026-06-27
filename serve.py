"""Serve: query the store and write the JSON the dashboard reads.

The query helpers are reusable and live in watchcore; the view shapes are
Burgerreich's and live here. This module queries the store via watchcore's
helpers and writes the JSON files the static dashboard fetches:

  - docs/data/feed.json   (main reverse-chronological feed)
  - the typed views, derived by filtering on obs_type

Output goes to docs/data/ (the dashboard stays at docs/ this pass; the
site/ rename and Vercel move are a later, separate step). The time axis is
driven by observed_at, not fetch time.

Placeholder until Phase 4.
"""

DATA_DIR = "docs/data"


def main() -> None:
    raise NotImplementedError("serve assembly lands in Phase 4")


if __name__ == "__main__":
    main()
