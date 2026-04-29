#!/usr/bin/env python3
"""
BURGERREICH_watch@ Full OSINT Collector v2

Automates everything scrapable. Outputs JSON that the dashboard reads on load.

WHAT THIS AUTOMATES:
  1. Fleet positions — USNI Fleet Tracker (weekly)
  2. Casualties — Wikipedia Iran war page (continuous)
  3. Equipment losses — Atlantic Council tracker (continuous)
  4. Troop posture — Wikipedia military buildup page
  5. Commander names — .mil leadership pages
  6. Doomsday Clock — Bulletin of Atomic Scientists

WHAT STAYS MANUAL:
  - Unconfirmed entries (editorial judgment)
  - Contractor wartime surge numbers (no source)
  - Your flash brief bullets

Outputs to docs/data/:
  fleet.json, casualties.json, losses.json, posture.json, 
  commanders.json, doomsday.json, collector_status.json
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows consoles default to cp1252 and choke on the arrow/check glyphs below.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

try:
    import requests
    import feedparser
    from bs4 import BeautifulSoup
except ImportError:
    print("[COLLECTOR] pip install -r collectors/requirements.txt")
    sys.exit(1)

try:
    from curl_cffi import requests as cffi_requests
    HAVE_CURL_CFFI = True
except ImportError:
    HAVE_CURL_CFFI = False

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rung 1: realistic browser headers. Mirrors Chrome 132 on macOS.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
NOW = datetime.now(timezone.utc).isoformat()


def fetch(url, timeout=30):
    """
    Fallback ladder for HTTP fetches.
      Rung 1: requests.get with realistic browser headers.
      Rung 2: curl_cffi with Chrome TLS fingerprint impersonation.
    Caller applies Rung 3 (write null + notes) on raise.
    """
    rung1_err = None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        rung1_err = e
        print(f"  ↻ Rung 1 failed ({type(e).__name__}: {str(e)[:80]}); escalating to curl_cffi")

    if not HAVE_CURL_CFFI:
        raise RuntimeError(f"curl_cffi unavailable; rung 1 failed: {rung1_err}")

    # Single profile: chrome131 cleared every .mil leadership page that 403'd on rung 1
    # during a 2026-04-28 probe (centcom, indopacom, northcom, southcom, stratcom).
    # No site has been observed where chrome131 fails but an older profile succeeds,
    # so trying multiple profiles just doubles latency on a true rung-3 failure.
    try:
        resp = cffi_requests.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome131")
        resp.raise_for_status()
        return resp.text
    except Exception as rung2_err:
        raise RuntimeError(f"Rung 1+2 both failed: rung1={rung1_err}; rung2={rung2_err}")

def save(filename, data):
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  → Saved: {path}")


# Wikipedia article bodies end with sections that are pure citation/footnote
# noise. Numbers buried in those sections frequently match casualty/troop
# regexes by accident (e.g. a footnote titled "12 US troops wounded in
# Iranian strike on Saudi base" being matched as cumulative WIA). Stripping
# these sections before regex matching prevents that whole class of misfire.
_WIKI_NOISE_HEADINGS = ("References", "Notes", "Citations", "External links",
                        "See also", "Further reading", "Bibliography", "Sources")


def _strip_wiki_noise(soup):
    """Mutate a Wikipedia BeautifulSoup tree to remove the first noise section
    heading (h2/h3) and every sibling after it within the same parent.

    Operates on the soup tree rather than text because Wikipedia's table of
    contents lists every section name (including "References", "See also")
    as plain text — text-level matching catches the TOC entry, not the real
    heading 100k+ chars later.
    """
    for heading in soup.find_all(['h2', 'h3']):
        text = re.sub(r'\[edit\]\s*$', '', heading.get_text().strip()).strip()
        if text in _WIKI_NOISE_HEADINGS:
            sib = heading.find_next_sibling()
            while sib:
                nxt = sib.find_next_sibling()
                sib.decompose()
                sib = nxt
            heading.decompose()
            return soup
    return soup


def _plausible_int(value, lo, hi):
    """Return value unchanged if it parses to an int in [lo, hi]; else None."""
    if value is None:
        return None
    try:
        n = int(re.sub(r'[^\d]', '', str(value)))
    except (ValueError, TypeError):
        return None
    return value if lo <= n <= hi else None


# ══════════════════════════════════════════════════════════════
# 1. FLEET POSITIONS — USNI Fleet Tracker
# ══════════════════════════════════════════════════════════════
def _empty_fleet(source_url, notes):
    """Rung-3 placeholder: keeps fleet.json present so the dashboard's overlay merge succeeds."""
    return {"updated": NOW, "source_url": source_url, "battle_force": None,
            "deployed": None, "underway": None, "carriers": [], "args": [], "notes": notes}


def collect_fleet():
    print("\n[1/6] FLEET POSITIONS — USNI Fleet Tracker")

    # Discover the latest tracker post via RSS. The HTML category page returns
    # markup the previous scrape couldn't navigate; the per-category feed is
    # permissive and structurally stable.
    rss_url = "https://news.usni.org/category/fleet-tracker/feed"
    try:
        feed = feedparser.parse(fetch(rss_url))
    except Exception as e:
        save("fleet.json", _empty_fleet(rss_url, f"rss fetch failed: {str(e)[:140]}"))
        print(f"  ✗ rung 3 (RSS fetch failed: {str(e)[:80]})")
        return

    if not feed.entries:
        save("fleet.json", _empty_fleet(rss_url, "rss feed had no entries"))
        print("  ✗ rung 3 (RSS feed empty)")
        return

    link = feed.entries[0].link
    print(f"  Latest tracker: {link}")

    try:
        body = BeautifulSoup(fetch(link), "lxml").get_text(separator="\n")
    except Exception as e:
        save("fleet.json", _empty_fleet(link, f"article fetch failed: {str(e)[:140]}"))
        print(f"  ✗ rung 3 (article fetch failed: {str(e)[:80]})")
        return
    
    carriers = []
    # Pattern: "USS [Name] (CVN-XX) is [in/operating/underway] [location]"
    for m in re.finditer(
        r'(?:Aircraft\s+)?(?:[Cc]arrier\s+)?(USS\s+[\w\.\s]+?)\s*\((CVN-\d+)\)\s+(?:is|was|arrived|departed|returned|operating)\s+(?:\w+\s+)?(?:in\s+)?(?:the\s+)?([\w\s,\-]+?)(?:\.|,|$)',
        body, re.MULTILINE
    ):
        hull = m.group(2).strip()
        if not any(c["hull"] == hull for c in carriers):
            loc = m.group(3).strip()[:60]
            ctx = body[max(0,m.start()-200):m.end()+200].lower()
            status = "DEPLOYED"
            if "homeport" in ctx or ("arrived" in ctx and ("norfolk" in loc.lower() or "san diego" in loc.lower() or "bremerton" in loc.lower() or "yokosuka" in loc.lower())):
                status = "HOMEPORT"
            elif "maintenance" in ctx or "overhaul" in ctx:
                status = "MAINTENANCE"
            elif "en route" in ctx or "transit" in ctx or ("underway" in ctx and "deploy" not in ctx):
                status = "TRANSIT"
            carriers.append({"name": m.group(1).strip(), "hull": hull, "location": loc, "status": status})
    
    args = []
    for m in re.finditer(
        r'(USS\s+[\w\.\s]+?)\s*\((LH[AD]-\d+)\)\s+(?:is|was|arrived|departed|operating)\s+(?:\w+\s+)?(?:in\s+)?(?:the\s+)?([\w\s,\-]+?)(?:\.|,|$)',
        body, re.MULTILINE
    ):
        hull = m.group(2).strip()
        if not any(a["hull"] == hull for a in args):
            loc = m.group(3).strip()[:60]
            ctx = body[max(0,m.start()-200):m.end()+200].lower()
            status = "DEPLOYED" if ("deploy" in ctx or "operating" in ctx or "en route" in ctx) else "HOMEPORT"
            args.append({"name": m.group(1).strip(), "hull": hull, "location": loc, "status": status})
    
    # Battle force numbers
    bf = re.search(r'Total Battle Force.*?(\d+)\s*\(', body)
    dep = re.search(r'Deployed.*?(\d+)', body)
    uw = re.search(r'Underway.*?(\d+)', body)
    
    result = {
        "updated": NOW, "source_url": link,
        "battle_force": bf.group(1) if bf else None,
        "deployed": dep.group(1) if dep else None,
        "underway": uw.group(1) if uw else None,
        "carriers": carriers, "args": args
    }
    
    save("fleet.json", result)
    print(f"  ✓ {len(carriers)} carriers, {len(args)} ARGs")


# ══════════════════════════════════════════════════════════════
# 2. CASUALTIES — Wikipedia 2026 Iran war
# ══════════════════════════════════════════════════════════════
def collect_casualties():
    print("\n[2/6] CASUALTIES — Wikipedia")

    url = "https://en.wikipedia.org/wiki/2026_Iran_war"
    try:
        soup = BeautifulSoup(fetch(url), "lxml")
    except Exception as e:
        # Source unreachable. Emit null fields + notes; drop operations entirely
        # so the dashboard's seed data carries the section. We do NOT bake in
        # fixture values here — fake-live numbers are worse than missing data.
        save("casualties.json", {
            "updated": NOW,
            "source": "Wikipedia / CENTCOM",
            "source_url": url,
            "us_kia_confirmed": None,
            "us_wia_confirmed": None,
            "notes": f"source unavailable: {str(e)[:140]}",
        })
        print(f"  ✗ rung 3 (fetch failed: {str(e)[:80]})")
        return

    body = _strip_wiki_noise(soup).get_text()

    # Find US KIA
    kia = None
    for p in [r'(\d+)\s+(?:U\.?S\.?|American|United States)\s+(?:service members?|soldiers?|troops?|military personnel|servicemen)\s+(?:have been\s+|had been\s+)?killed',
              r'(\d+)\s+killed\s+in\s+action',
              r'(\d+)\s+US\s+(?:troops?\s+)?(?:have\s+)?(?:been\s+)?killed']:
        m = re.search(p, body, re.IGNORECASE)
        if m: kia = m.group(1); break

    # Find US WIA — tight patterns first, broad last
    wia = None
    for p in [r'(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+(?:service members?|military personnel|troops?|servicemen)\s+(?:have been\s+|had been\s+)?(?:wounded|injured)',
              r'(?:about|approximately)\s+(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+\w+\s+(?:have|had)\s+been\s+(?:wounded|injured)',
              r'(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+.*?(?:wounded|injured)']:
        m = re.search(p, body, re.IGNORECASE)
        if m: wia = m.group(1); break

    # Plausibility gate: cumulative US KIA/WIA in any single conflict above
    # 10,000 would be unprecedented since Vietnam — anything higher is almost
    # certainly a regex hit on an unrelated number (year, page count, etc.).
    out_of_range = []
    if kia is not None and _plausible_int(kia, 0, 10000) is None:
        out_of_range.append(f"kia={kia!r}")
        kia = None
    if wia is not None and _plausible_int(wia, 0, 10000) is None:
        out_of_range.append(f"wia={wia!r}")
        wia = None

    # Epic Fury numbers come from `kia`/`wia` only — no fallback. If parsing
    # fails the entry still emits with nulls; the dashboard merges over seed.
    # Tower 22 and Syria entries are historical (2024–2025), not live.
    result = {
        "updated": NOW,
        "source": "Wikipedia / CENTCOM",
        "us_kia_confirmed": kia,
        "us_wia_confirmed": wia,
        "operations": [
            {"name": "Operation Epic Fury", "kia": kia, "wia": wia, "period": "Feb 28, 2026–present"},
            {"name": "Tower 22 (Jordan)", "kia": "3", "wia": "47", "period": "Jan 28, 2024"},
            {"name": "Syria ISIS Ambush", "kia": "3", "wia": "3", "period": "Dec 14, 2025"},
        ]
    }
    if out_of_range:
        result["notes"] = "values out of plausible range (0-10000); nulled: " + ", ".join(out_of_range)

    save("casualties.json", result)
    print(f"  ✓ KIA: {kia}, WIA: {wia}")


# ══════════════════════════════════════════════════════════════
# 3. EQUIPMENT LOSSES — Atlantic Council
# ══════════════════════════════════════════════════════════════
def collect_losses():
    print("\n[3/6] EQUIPMENT LOSSES — Atlantic Council")
    
    url = "https://www.atlanticcouncil.org/commentary/trackers-and-data-visualizations/tracking-us-military-assets-in-the-iran-war/"
    body = BeautifulSoup(fetch(url), "lxml").get_text()
    
    items = []
    patterns = [
        (r'(?:lost|destroyed)\s+(\w+)\s+MQ-9', "MQ-9 Reaper", "DESTROYED"),
        (r'(\d+)\s+F-15E', "F-15E Strike Eagle", "DESTROYED"),
        (r'KC-135.*?crash', "KC-135 Stratotanker", "DESTROYED"),
        (r'F-35A.*?(?:damaged|struck|hit)', "F-35A Lightning II", "DAMAGED"),
        (r'(\d+)\s+(?:AN/TPY-2|THAAD)', "AN/TPY-2 THAAD Radar", "HIT"),
        (r'AN/FPS-132.*?(?:struck|hit)', "AN/FPS-132 Radar", "DESTROYED"),
        (r'E-3.*?(?:destroyed|damaged|struck)', "E-3 Sentry AWACS", "DESTROYED"),
        (r'Ford.*?(?:fire|repair|Souda)', "USS Ford (CVN-78)", "DAMAGED"),
    ]
    
    word_nums = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,
                 "eight":8,"nine":9,"ten":10,"eleven":11,"twelve":12,"thirteen":13}
    
    for pat, equip, status in patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            try:
                q = m.group(1)
            except (IndexError, AttributeError):
                q = "1"
            qty = word_nums.get(q.lower(), int(q) if q.isdigit() else 1)
            items.append({"type": equip, "qty": qty, "status": status})
    
    cost = re.search(r'\$(\d+\.?\d*)\s*billion', body, re.IGNORECASE)
    
    result = {
        "updated": NOW, "source_url": url,
        "items": items,
        "total_cost": f"${cost.group(1)}B" if cost else "unknown"
    }
    
    save("losses.json", result)
    print(f"  ✓ {len(items)} loss entries, cost: {result['total_cost']}")


# ══════════════════════════════════════════════════════════════
# 4. TROOP POSTURE — Wikipedia military buildup page
# ══════════════════════════════════════════════════════════════
def collect_posture():
    print("\n[4/6] TROOP POSTURE — Wikipedia buildup page")

    url = "https://en.wikipedia.org/wiki/2026_United_States_military_buildup_in_the_Middle_East"
    try:
        soup = BeautifulSoup(fetch(url), "lxml")
    except Exception as e:
        # Source unreachable. Drop deployments_mentioned entirely so the
        # dashboard's seed data carries the section.
        save("posture.json", {
            "updated": NOW,
            "source": "Wikipedia — 2026 US military buildup in the Middle East",
            "source_url": url,
            "total_middle_east": None,
            "notes": f"source unavailable: {str(e)[:140]}",
        })
        print(f"  ✗ rung 3 (fetch failed: {str(e)[:80]})")
        return

    body = _strip_wiki_noise(soup).get_text()

    # Find total troop count
    total = None
    for p in [r'(\d{2},?\d{3})\s+(?:American|U\.?S\.?)\s+troops',
              r'(?:over|more than|at least)\s+(\d{2},?\d{3})\s+(?:troops|service members)',
              r'(\d{2},?\d{3})\s+U\.?S\.?\s+troops\s+(?:are\s+)?(?:now\s+)?(?:actively\s+)?(?:deployed|supporting)']:
        m = re.search(p, body, re.IGNORECASE)
        if m: total = m.group(1); break
    
    # Find specific deployments mentioned
    deployments = []
    deploy_patterns = [
        (r'82nd Airborne.*?(?:deployed|arriving|arrived)', "82nd Airborne Division"),
        (r'(?:USS\s+)?Tripoli.*?(?:arrived|entered|deployed)', "Tripoli ARG"),
        (r'(?:USS\s+)?Boxer.*?(?:deployed|departed)', "Boxer ARG"),
        (r'F-22.*?(?:deployed|stationed)\s+(?:to|at)\s+([\w\s]+)', "F-22 Raptors"),
        (r'F-15E.*?(?:relocated|deployed|moved)\s+(?:to|from)', "F-15E Strike Eagles"),
        (r'Patriot.*?(?:deployed|battery)', "Patriot Battery"),
        (r'THAAD.*?(?:deployed|repositioned)', "THAAD System"),
        (r'B-52.*?(?:deployed|rotation|Diego Garcia)', "B-52 Bombers"),
    ]
    
    for pat, name in deploy_patterns:
        m = re.search(pat, body, re.IGNORECASE)
        if m:
            ctx = body[max(0,m.start()-50):m.end()+100].strip()[:120]
            deployments.append({"asset": name, "context": ctx})
    
    # Plausibility gate: a US troop buildup in a single theater is realistically
    # 1k–1M people. Anything outside that window is almost certainly a regex
    # hit on a year, body count, dollar figure, etc.
    posture_notes = None
    if total is not None and _plausible_int(total, 1000, 1000000) is None:
        posture_notes = f"total_middle_east={total!r} out of plausible range (1000-1000000); nulled"
        total = None

    result = {
        "updated": NOW,
        "source": "Wikipedia — 2026 US military buildup in the Middle East",
        "total_middle_east": total,
        "deployments_mentioned": deployments
    }
    if posture_notes:
        result["notes"] = posture_notes

    save("posture.json", result)
    print(f"  ✓ Total troops: {total}, deployments found: {len(deployments)}")


# ══════════════════════════════════════════════════════════════
# 5. COMMANDERS — .mil leadership pages
# ══════════════════════════════════════════════════════════════
BAD_NAME_TOKENS = ("FOIA", "USAF", "CSAF")

def _validate_commander_name(name):
    """Reject obvious garbage: newlines, error strings, all-caps acronyms, missing space."""
    if not isinstance(name, str) or not name.strip():
        return False
    if "\n" in name or "\r" in name:
        return False
    if name.lower().startswith("error:"):
        return False
    if " " not in name.strip():
        return False
    for tok in BAD_NAME_TOKENS:
        if tok in name:
            return False
    return True


def collect_commanders():
    print("\n[5/6] COMMANDERS — .mil leadership pages")

    # URL paper trail. Each replacement was verified by probing the old URL
    # (404/redirect/wrong page) and the new URL (200 + extractable name).
    #   eucom    https://www.eucom.mil/about-us/leadership/combatant-commander
    #         -> https://www.eucom.mil/about-the-command/leadership/commander           (replaced 2026-04-28: old path 404)
    #   southcom https://www.southcom.mil/Leadership/Commander/
    #         -> https://www.southcom.mil/About/Leadership/Commander/                   (replaced 2026-04-28: old path 404; canonical lives under /About/)
    #   stratcom https://www.stratcom.mil/Leadership/Commander/
    #         -> https://www.stratcom.mil/About/Leadership/Commander/                   (replaced 2026-04-28: old path 404; canonical lives under /About/)
    #   socom    https://www.socom.mil/about/leadership
    #         -> https://www.socom.mil/Leadership                                       (replaced 2026-04-28: old path served a generic landing page with no commander bio)
    pages = [
        ("centcom", "https://www.centcom.mil/ABOUT-US/LEADERSHIP/"),
        ("eucom", "https://www.eucom.mil/about-the-command/leadership/commander"),
        ("indopacom", "https://www.pacom.mil/Leadership/Commander/"),
        ("northcom", "https://www.northcom.mil/Leadership/Commander/"),
        ("africom", "https://www.africom.mil/about-the-command/leadership/commander"),
        ("southcom", "https://www.southcom.mil/About/Leadership/Commander/"),
        ("stratcom", "https://www.stratcom.mil/About/Leadership/Commander/"),
        ("socom", "https://www.socom.mil/Leadership"),
    ]

    # Match: TITLE + first name + (optional middle initial/name) + last name. Single line only — [ \t] not \s.
    name_re = re.compile(
        r'\b((?:General|Admiral|Gen\.|Adm\.|GEN|ADM)'
        r'[ \t]+[A-Z][A-Za-z\.\-\']{1,30}'
        r'(?:[ \t]+[A-Z][A-Za-z\.\-\']{0,30}){1,3})\b'
    )

    commanders = {}
    for cocom, url in pages:
        try:
            html = fetch(url)
        except Exception as e:
            # Rung 3: drop the source.
            commanders[cocom] = {"name": None, "url": url, "notes": f"fetch failed: {str(e)[:140]}"}
            print(f"  ✗ {cocom}: rung 3 (fetch failed)")
            continue

        try:
            text = BeautifulSoup(html, "lxml").get_text(separator="\n")
        except Exception as e:
            commanders[cocom] = {"name": None, "url": url, "notes": f"parse failed: {str(e)[:140]}"}
            print(f"  ✗ {cocom}: rung 3 (parse failed)")
            continue

        name = None
        for m in name_re.finditer(text):
            candidate = m.group(1).strip()
            if _validate_commander_name(candidate):
                name = candidate
                break

        if name:
            commanders[cocom] = {"name": name, "url": url}
            print(f"  ✓ {cocom}: {name}")
        else:
            commanders[cocom] = {"name": None, "url": url, "notes": "no valid name pattern matched"}
            print(f"  ✗ {cocom}: rung 3 (no name pattern matched)")

    found = sum(1 for c in commanders.values() if c.get("name"))
    dropped = len(pages) - found
    if dropped >= 2:
        print(f"  ⚠  {dropped}/{len(pages)} sources on rung 3 — possible broader issue")

    result = {"updated": NOW, "commanders": commanders}
    save("commanders.json", result)
    print(f"  ✓ {found}/{len(pages)} commanders found")


# ══════════════════════════════════════════════════════════════
# 6. DOOMSDAY CLOCK — Bulletin of Atomic Scientists
# ══════════════════════════════════════════════════════════════
def collect_doomsday():
    print("\n[6/6] DOOMSDAY CLOCK — Bulletin of Atomic Scientists")
    
    try:
        body = BeautifulSoup(
            fetch("https://thebulletin.org/doomsday-clock/"), "lxml"
        ).get_text()
        
        # Look for seconds/minutes to midnight
        seconds = None
        for p in [r'(\d+)\s+seconds?\s+(?:to|before)\s+midnight',
                  r'Clock.*?(\d+)\s+seconds']:
            m = re.search(p, body, re.IGNORECASE)
            if m: seconds = m.group(1); break
        
        result = {
            "updated": NOW,
            "seconds_to_midnight": seconds,
            "source": "Bulletin of the Atomic Scientists"
        }
        
        save("doomsday.json", result)
        print(f"  ✓ {seconds}s to midnight")
    except Exception as e:
        print(f"  ✗ Error: {e}")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("BURGERREICH_watch@ Full OSINT Collector v2")
    print(f"Time: {NOW}")
    print("=" * 60)
    
    errors = []
    collectors = [
        ("Fleet", collect_fleet),
        ("Casualties", collect_casualties),
        ("Losses", collect_losses),
        ("Posture", collect_posture),
        ("Commanders", collect_commanders),
        ("Doomsday", collect_doomsday),
    ]
    
    for name, fn in collectors:
        try:
            fn()
        except Exception as e:
            print(f"  ✗ {name} ERROR: {e}")
            errors.append(f"{name}: {e}")
    
    # Status file
    save("collector_status.json", {
        "last_run": NOW,
        "errors": errors,
        "collectors": [c[0] for c in collectors],
        "next_manual": [
            "Unconfirmed entries (all categories)",
            "Contractor wartime surge numbers",
            "Flash brief BLUF bullets",
            "Ship coordinates (lat/lng for new positions)",
        ]
    })
    
    print("\n" + "=" * 60)
    print(f"Done. {len(collectors) - len(errors)}/{len(collectors)} succeeded.")
    if errors:
        print(f"Errors: {', '.join(errors)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
