# Burgerreich Watch

Open-source US military force tracking dashboard.

All data sourced from publicly available OSINT and official DoD releases.  
**NOT AFFILIATED WITH DoD OR ANY GOVERNMENT ENTITY.**

Part of [das_DEMARC](https://dasdemarc.substack.com).

---

## Structure

```
docs/
  index.html          # Dashboard (single-file, GitHub Pages)
  data/               # Collector JSON output (auto-updated)
    feed.json          # Merged feed from all collectors
    centcom.json       # CENTCOM press releases
    eucom.json         # EUCOM news
    indopacom.json     # INDOPACOM news
    africom.json       # AFRICOM press releases
    stratcom.json      # STRATCOM news

collectors/
  utils.py             # Shared utilities (RSS fetch, dedup, classify)
  collect_centcom.py   # CENTCOM collector
  collect_eucom.py     # EUCOM collector
  collect_indopacom.py # INDOPACOM collector
  collect_africom.py   # AFRICOM collector
  collect_stratcom.py  # STRATCOM collector
  merge_feeds.py       # Merges all feeds into feed.json
  requirements.txt     # Python dependencies

.github/workflows/
  deploy.yml           # GitHub Pages deployment (on push to main)
  collect.yml          # Scheduled collector runs (every 6 hours)
```

## Deployment

1. Create repo on GitHub
2. Push this code to `main`
3. Go to **Settings → Pages → Source → GitHub Actions**
4. The `deploy.yml` workflow handles the rest

## Collectors

Collectors run automatically every 6 hours via GitHub Actions.

They pull RSS feeds from combatant command websites, classify items by type (naval, air, ground, posture, exercise, alert), and output JSON to `docs/data/`.

The dashboard loads `data/feed.json` via background fetch. If the fetch fails (e.g., local preview without a server), it falls back to embedded seed data.

### Manual run

```bash
pip install -r collectors/requirements.txt
python collectors/collect_centcom.py
python collectors/collect_eucom.py
python collectors/collect_indopacom.py
python collectors/collect_africom.py
python collectors/collect_stratcom.py
python collectors/merge_feeds.py
```

### Adding a new collector

1. Copy any existing collector (e.g., `collect_centcom.py`)
2. Update `FEED_URL`, `COCOM`, `SOURCE`, `OUTPUT`
3. Add the new collector step to `.github/workflows/collect.yml`
4. Add the output filename to `FEED_FILES` in `merge_feeds.py`

## Data Sources

- [CENTCOM](https://www.centcom.mil/) — US Central Command
- [EUCOM](https://www.eucom.mil/) — US European Command
- [INDOPACOM](https://www.pacom.mil/) — US Indo-Pacific Command
- [AFRICOM](https://www.africom.mil/) — US Africa Command
- [STRATCOM](https://www.stratcom.mil/) — US Strategic Command
- [USNI News](https://news.usni.org/) — Fleet Tracker
- [ADS-B Exchange](https://globe.adsbexchange.com/) — Aircraft tracking
- [OHCHR](https://www.ohchr.org/) — Civilian casualty data
- [CSIS](https://www.csis.org/) — Casualty estimates
- [Gaza Health Ministry](https://www.moh.gov.ps/) — Gaza death toll

## License

Data is sourced from public records and open-source intelligence.  
Dashboard code is open source.
