"""Collector configuration: feed URLs, grade baselines, and the keyword maps.

Project-specific, so it lives in Burgerreich (not watchcore). Collectors read
these values; they do not hardcode feed lists or grades in their bodies.
"""

from urllib.parse import quote

# --------------------------------------------------------------------------
# DVIDS collector
# --------------------------------------------------------------------------

# Deep DVIDS press-release feed.
#
# IMPORTANT: the `q=CENTCOM` query param is COSMETIC. DVIDS public RSS does NOT
# honor q / unit / keyword / country filters — verified empirically:
# rss/unit/USCENTCOM, rss/unit/USEUCOM, and rss/unit/<nonsense> all return the
# byte-identical DoD-wide firehose. This URL is chosen ONLY because it is the
# deepest feed in time (~3 months of press releases), so releases are not
# dropped between 6-hour runs. ALL CENTCOM-theater scoping is the client-side
# allowlist below (CENTCOM_THEATER_KEYWORDS) — do not mistake `q=CENTCOM` for a
# working server-side filter and do not lean on it.
DVIDS_FEED_URL = "https://www.dvidshub.net/rss/search?q=CENTCOM"

# Keep only DVIDS news/press-release items. Their RSS guid is prefixed `news:`;
# imagery (`image:`), audio (`audio:`), and untyped numeric guids are dropped.
DVIDS_PRESS_RELEASE_GUID_PREFIX = "news:"

# Admiralty grade baseline for DVIDS: official DoD release. Reliability B
# (usually reliable), credibility 2 (probably true). A later detect stage may
# revise upward on corroboration; that is out of scope here.
DVIDS_RELIABILITY = "B"
DVIDS_CREDIBILITY = 2

# CENTCOM-theater allowlist. Matched case-insensitively on word boundaries
# (so "oman" != "woman", "isis" != "crisis") against title + summary. An item
# must hit at least one term to be kept.
#
# Tightened to drop the bio-magnet bare country terms (jordan, afghanistan,
# pakistan, egypt, lebanon) that produced surname/biography false positives,
# while keeping the active-conflict countries and unambiguous theater signals.
# This deliberately keeps soft posture matches (e.g. "Operation Epic ..."
# deployment returns that mention Iran) — missing real posture movement is worse
# than an occasional soft match. Tune this list here, not in the collector.
CENTCOM_THEATER_KEYWORDS = [
    # commands / forces
    "centcom", "central command", "fifth fleet", "5th fleet",
    "navcent", "arcent", "afcent", "marcent", "soccent",
    "naval forces central", "combined maritime forces",
    "task force 51", "ctf 150", "ctf 152", "ctf 153",
    # active-conflict countries / CENTCOM AOR (kept despite soft-match risk)
    "iran", "iranian", "iraq", "syria", "yemen", "bahrain", "qatar",
    "kuwait", "saudi", "united arab emirates", "uae", "oman",
    # waterways
    "persian gulf", "arabian gulf", "arabian sea", "gulf of oman",
    "gulf of aden", "red sea", "strait of hormuz",
    "bab al-mandab", "bab el-mandeb",
    # actors
    "houthi", "irgc", "hezbollah", "isis", "daesh", "islamic state",
]

# Rule-based obs_type map (intentionally dumb; the detect stage refines later).
# Precedence is domain-first: an item that hits a naval/air/ground term takes
# that domain even if it also reads as movement; only items with no domain hit
# but a disposition/movement hit become "posture"; everything else is "other".
# This matches the schema spec's own worked example (a carrier *transit* is
# classified "naval", not "posture").
OBS_TYPE_KEYWORDS = {
    "naval": [
        "navy", "naval", "ship", "uss", "carrier", "strike group", "destroyer",
        "frigate", "cruiser", "fleet", "maritime", "sailor", "warship",
        "submarine", "amphibious", "fifth fleet",
    ],
    "air": [
        "air force", "aircraft", "fighter", "f-15", "f-16", "f-22", "f-35",
        "squadron", "sortie", "airstrike", "air strike", "airman", "airmen",
        "wing", "bomber", "drone", "uav", "tanker", "refuel", "b-2", "b-52",
    ],
    "ground": [
        "army", "soldier", "infantry", "brigade", "division", "armor",
        "artillery", "ground forces", "battalion", "marine", "cavalry",
        "paratrooper",
    ],
    "posture": [
        "deploy", "deployment", "posture", "buildup", "build-up", "reinforce",
        "transfer of authority", "arrive", "arrival", "return home",
        "returns home", "reposition", "mobiliz", "force protection",
        "deter", "deterrence", "presence", "exercise",
    ],
}


# --------------------------------------------------------------------------
# News RSS collector
# --------------------------------------------------------------------------

# Aggregated-news baseline: reliability C (fairly reliable), credibility 3
# (possibly true) — lower than DVIDS, since these are secondary reporting. A
# named reputable outlet can be bumped per feed via the optional reliability /
# credibility keys in NEWS_FEEDS below.
NEWS_RELIABILITY = "C"
NEWS_CREDIBILITY = 3


def _google_news(query: str) -> str:
    """Google News RSS search feed for a query. The query IS the CENTCOM-theater
    scope — no client-side allowlist is applied to news (unlike DVIDS), because
    each query is theater-specific."""
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"


# Feed list. Each entry: name, url, and optional per-feed grade override
# (defaults to the C/3 baseline). Google News populates the outlet via the RSS
# <source> element, so `publisher` resolves per item; the feed `name` is only a
# publisher fallback for direct-outlet feeds (e.g. USNI) that carry no <source>.
NEWS_FEEDS = [
    {"name": "Google News: CENTCOM",
     "url": _google_news('"U.S. Central Command" OR CENTCOM')},
    {"name": "Google News: Fifth Fleet",
     "url": _google_news('"Fifth Fleet" OR "Combined Maritime Forces"')},
    {"name": "Google News: Strait of Hormuz",
     "url": _google_news('"Strait of Hormuz" OR "Persian Gulf"')},
    {"name": "Google News: Red Sea / Houthi",
     "url": _google_news('"Red Sea" Houthi')},
    {"name": "Google News: Iran strike",
     "url": _google_news('Iran U.S. military strike')},
    {"name": "Google News: Iraq / Syria",
     "url": _google_news('Iraq OR Syria U.S. military')},
    {"name": "Google News: Yemen / Houthi",
     "url": _google_news('Yemen Houthi')},
    # Named reputable defense outlet (direct feed, no <source> element, so
    # publisher falls back to this name). Bumped above the aggregated baseline.
    {"name": "USNI News", "url": "https://news.usni.org/feed",
     "reliability": "B", "credibility": 2},
]
