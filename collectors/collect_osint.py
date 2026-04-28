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

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("[COLLECTOR] pip install requests beautifulsoup4 lxml --break-system-packages")
    sys.exit(1)

DATA_DIR = Path(__file__).parent.parent / "docs" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "BURGERREICH-watch/2.0 (OSINT; dasdemarc.substack.com)"}
NOW = datetime.now(timezone.utc).isoformat()

def fetch(url, timeout=30, retries=2):
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt == retries:
                raise
            wait = 5 * (attempt + 1)
            print(f"  ⟳ Retry {attempt+1}/{retries} in {wait}s — {e}")
            time.sleep(wait)

def save(filename, data):
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  → Saved: {path}")


# ══════════════════════════════════════════════════════════════
# 1. FLEET POSITIONS — USNI Fleet Tracker
# ══════════════════════════════════════════════════════════════
def collect_fleet():
    print("\n[1/6] FLEET POSITIONS — USNI Fleet Tracker")
    
    # Find latest tracker post
    index = fetch("https://news.usni.org/category/fleet-tracker")
    soup = BeautifulSoup(index, "lxml")
    
    link = None
    for a in soup.find_all("a", href=True):
        if "fleet-and-marine-tracker" in a["href"]:
            link = a["href"]
            break
    
    if not link:
        print("  ✗ Could not find latest tracker URL")
        return
    
    print(f"  Fetching: {link}")
    body = BeautifulSoup(fetch(link), "lxml").get_text(separator="\n")
    
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
    
    body = BeautifulSoup(fetch("https://en.wikipedia.org/wiki/2026_Iran_war"), "lxml").get_text()
    
    # Find US KIA
    kia = None
    for p in [r'(\d+)\s+(?:U\.?S\.?|American|United States)\s+(?:service members?|soldiers?|troops?|military personnel)\s+(?:have been\s+)?killed',
              r'(\d+)\s+killed\s+in\s+action',
              r'(\d+)\s+US\s+(?:troops?\s+)?(?:have\s+)?(?:been\s+)?killed']:
        m = re.search(p, body, re.IGNORECASE)
        if m: kia = m.group(1); break
    
    # Find US WIA — tight patterns first, broad last
    wia = None
    for p in [r'(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+(?:service members?|military personnel|troops?)\s+(?:have been\s+)?(?:wounded|injured)',
              r'approximately\s+(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+.*?(?:wounded|injured)',
              r'(\d+[\+]?)\s+(?:U\.?S\.?|American)\s+.*?(?:wounded|injured)']:
        m = re.search(p, body, re.IGNORECASE)
        if m: wia = m.group(1); break
    
    result = {
        "updated": NOW,
        "source": "Wikipedia / CENTCOM",
        "us_kia_confirmed": kia,
        "us_wia_confirmed": wia,
        "operations": [
            {"name": "Operation Epic Fury", "kia": kia or "13", "wia": wia or "348", "period": "Feb 28, 2026–present"},
            {"name": "Tower 22 (Jordan)", "kia": "3", "wia": "47", "period": "Jan 28, 2024"},
            {"name": "Syria ISIS Ambush", "kia": "3", "wia": "3", "period": "Dec 14, 2025"},
        ]
    }
    
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
    
    body = BeautifulSoup(
        fetch("https://en.wikipedia.org/wiki/2026_United_States_military_buildup_in_the_Middle_East"), 
        "lxml"
    ).get_text()
    
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
    
    result = {
        "updated": NOW,
        "source": "Wikipedia — 2026 US military buildup in the Middle East",
        "total_middle_east": total,
        "deployments_mentioned": deployments
    }
    
    save("posture.json", result)
    print(f"  ✓ Total troops: {total}, deployments found: {len(deployments)}")


# ══════════════════════════════════════════════════════════════
# 5. COMMANDERS — .mil leadership pages
# ══════════════════════════════════════════════════════════════
def collect_commanders():
    print("\n[5/6] COMMANDERS — .mil leadership pages")
    
    pages = [
        ("centcom", "https://www.centcom.mil/ABOUT-US/LEADERSHIP/"),
        ("eucom", "https://www.eucom.mil/about-us/leadership/combatant-commander"),
        ("indopacom", "https://www.pacom.mil/Leadership/Commander/"),
        ("northcom", "https://www.northcom.mil/Leadership/Commander/"),
        ("africom", "https://www.africom.mil/about-the-command/leadership/commander"),
        ("southcom", "https://www.southcom.mil/Leadership/Commander/"),
        ("stratcom", "https://www.stratcom.mil/Leadership/Commander/"),
        ("socom", "https://www.socom.mil/about/leadership"),
    ]
    
    commanders = {}
    for cocom, url in pages:
        try:
            body = BeautifulSoup(fetch(url), "lxml").get_text()
            # Look for general/admiral name patterns
            for p in [r'((?:Gen(?:eral)?|Adm(?:iral)?|GEN|ADM)\.?\s+[\w\.\s\-\']+?)(?:\n|,|Commander)',
                      r'((?:Gen|Adm)\.?\s+[\w\.\s]+?)(?:\s+is\s+the|\s+assumed|\s+serves)',
                      r'Commander[,:\s]+((?:Gen|Adm)\.?\s+[\w\.\s]+?)(?:\n|,|\.)']:
                m = re.search(p, body)
                if m:
                    name = m.group(1).strip()[:60]
                    commanders[cocom] = {"name": name, "url": url}
                    break
            if cocom not in commanders:
                commanders[cocom] = {"name": "check manually", "url": url}
        except Exception as e:
            commanders[cocom] = {"name": f"error: {e}", "url": url}
    
    result = {"updated": NOW, "commanders": commanders}
    save("commanders.json", result)
    print(f"  ✓ {len([c for c in commanders.values() if 'error' not in c['name']])} commanders found")


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
