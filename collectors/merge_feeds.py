"""
Merge all COCOM collector outputs into a single unified feed.
Outputs: docs/data/feed.json (combined, sorted by date)
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
FEED_FILES = ["centcom.json", "eucom.json", "indopacom.json", "africom.json", "stratcom.json"]
OUTPUT = DATA_DIR / "feed.json"
MAX_ITEMS = 100


def merge():
    all_items = []
    for fname in FEED_FILES:
        fpath = DATA_DIR / fname
        if fpath.exists():
            try:
                with open(fpath) as f:
                    items = json.load(f)
                    all_items.extend(items)
                    print(f"  {fname}: {len(items)} items")
            except (json.JSONDecodeError, IOError) as e:
                print(f"  {fname}: ERROR - {e}")
        else:
            print(f"  {fname}: not found (collector may not have run)")

    # Deduplicate by ID
    seen = set()
    unique = []
    for item in all_items:
        iid = item.get("id", "")
        if iid and iid not in seen:
            seen.add(iid)
            unique.append(item)

    # Sort by date descending
    unique.sort(key=lambda x: x.get("date", ""), reverse=True)
    unique = unique[:MAX_ITEMS]

    with open(OUTPUT, "w") as f:
        json.dump(unique, f, indent=2)

    print(f"\n[OK] feed.json: {len(unique)} items merged")


if __name__ == "__main__":
    merge()
