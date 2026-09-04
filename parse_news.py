#!/usr/bin/env python3
import json
import requests
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, List

# --- Configuration ---
LODESTONE_API = "https://lodestonenews.com/news"
OUTPUT_FILE = "LatestNews.json"
RETENTION_DAYS = 30

# Supported Lodestone regions in the order they appear in the output.
REGIONS = ["na", "eu", "jp", "fr", "de"]

SEASONAL_KEYWORDS = [
    "Valentione", "Heavensturn", "Little Ladies", "Hatching",
    "Make It Rain", "Moonfire", "The Rising", "All Saints",
    "Starlight", "Moogle Treasure", "Irregular Tomestone",
    "Maiden's Rhapsody", "Returns",
]

# How long (seconds) a maintenance with no announced end time is still
# considered ongoing after its start.  Emergency maintenances rarely last more
# than a few hours; after this window a null-end entry is treated as completed
# so a stale article cannot block newer maintenances indefinitely.
NO_END_ONGOING_WINDOW = 86400  # 24 hours


def fetch_api(category: str, locale: str = "na") -> List[Dict]:
    try:
        url = f"{LODESTONE_API}/{category}?locale={locale}"
        print(f"📡 Fetching {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f" ✗ Error fetching {category} ({locale}): {e}")
        return []


def fetch_all_regions(category: str) -> Dict[str, List[Dict]]:
    """Fetch the given category from every supported Lodestone region."""
    return {region: fetch_api(category, region) for region in REGIONS}


def _parse_ts(iso: str) -> Optional[int]:
    """Parse an ISO-8601 datetime string (with optional trailing Z) to a UNIX timestamp."""
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except Exception:
        return None


# Maximum seconds between two articles' publish times to consider them the
# same maintenance announcement across regions when a region's article carries
# no maintenance window.  lodestonenews.com only extracts start/end times for
# the na, eu and de locales, so jp/fr maintenance articles never have a window
# and must be matched by publish time instead.  Square Enix publishes an
# announcement to all regions nearly simultaneously; the candidate closest in
# publish time within this window is used, which also keeps original and
# follow-up articles (same type, hours apart) paired correctly.
_MAINT_PUB_MATCH_WINDOW = 86400  # 24 hours


def build_maintenance_regional_matches(
    start_ts: int,
    end_ts: Optional[int],
    m_type: str,
    pub_ts: int,
    region_items: Dict[str, List[Dict]],
) -> Dict[str, Optional[Dict]]:
    """
    Find the Lodestone maintenance article for each region.

    Primary key — the (start_ts, end_ts) pair plus the maintenance
    classification.  Lodestone article IDs differ across regions, so the URL
    path cannot be used as a match key.  The maintenance window (start and end
    times) is identical for all regions since Square Enix takes every region
    down simultaneously, making it a reliable cross-region identifier.
    However, several distinct maintenance articles (e.g. Companion App or Mog
    Station maintenance) often share the exact same window as the All Worlds
    maintenance, so a candidate must additionally classify to the same
    maintenance type (see classify_maintenance) as the discovered article.

    Fallback key — publish-time proximity.  lodestonenews.com only extracts
    start/end times for the na, eu and de locales, so jp/fr articles never
    carry a window (na/eu/de articles can also lack one when the upstream
    parser fails).  Among same-type candidates with no window at all, the one
    whose publish time is closest to the discovery article's publish time
    (within _MAINT_PUB_MATCH_WINDOW) is used.  Candidates that carry a
    different window are never considered: they belong to a different
    maintenance.

    A region article is only emitted when a match is found in that region's
    feed; nothing is fabricated.

    end_ts may be None (emergency maintenances are often announced without an
    end time); in that case a window match requires the region item to also
    lack an end time.
    """
    matches: Dict[str, Optional[Dict]] = {}
    for region in REGIONS:
        matches[region] = None
        candidates = [
            item
            for item in region_items.get(region, [])
            if classify_maintenance(item.get("title", "")) == m_type
        ]

        for item in candidates:
            s = _parse_ts(item.get("start") or "")
            e = _parse_ts(item.get("end") or "")
            if s == start_ts and e == end_ts:
                matches[region] = item
                break

        if matches[region] is not None:
            continue

        best, best_delta = None, None
        for item in candidates:
            item_start = _parse_ts(item.get("start") or "")
            item_end = _parse_ts(item.get("end") or "")
            if item_start is not None or item_end is not None:
                continue
            item_pub = _parse_ts(item.get("time") or "")
            if item_pub is None:
                continue
            delta = abs(item_pub - pub_ts)
            if delta <= _MAINT_PUB_MATCH_WINDOW and (
                best_delta is None or delta < best_delta
            ):
                best, best_delta = item, delta
        matches[region] = best
    return matches


# Maximum seconds between two articles' publish times to consider them the same
# seasonal-event announcement across regions.  24 hours is generous but safe:
# seasonal events are infrequent, so no two distinct events will be published
# within this window at the same time.
_TOPIC_MATCH_WINDOW = 86400  # 24 hours


def build_topic_regional_matches(
    na_pub_ts: int, region_items: Dict[str, List[Dict]]
) -> Dict[str, Optional[Dict]]:
    """
    Find the Lodestone topics/event article for each region by matching on
    publication timestamp.

    Lodestone article IDs and titles both differ across regions (titles are
    localised into Japanese, French, German, etc.), so neither can be used as a
    reliable cross-region key.  Square Enix publishes the same seasonal-event
    announcement to all regions within a short window; matching on publish time
    within ±24 hours is therefore reliable for the infrequent seasonal events
    tracked by this tool.  A region article is only emitted when a sufficiently
    close match is found in that region's feed; nothing is fabricated.
    """
    matches: Dict[str, Optional[Dict]] = {}
    for region in REGIONS:
        matches[region] = None
        for item in region_items.get(region, []):
            pub_ts = _parse_ts(item.get("time", ""))
            if pub_ts is not None and abs(pub_ts - na_pub_ts) <= _TOPIC_MATCH_WINDOW:
                matches[region] = item
                break
    return matches


def regional_urls(matches: Dict[str, Optional[Dict]]) -> Dict[str, Optional[str]]:
    """Extract the per-region URL map from a per-region article match map."""
    return {region: (m["url"] if m else None) for region, m in matches.items()}


def pick_title(matches: Dict[str, Optional[Dict]], fallback: str) -> str:
    """
    Return the article title from the EU feed, falling back to the given
    (discovery-source) title when no EU match was found.
    """
    eu_match = matches.get("eu")
    if eu_match and eu_match.get("title"):
        return eu_match["title"]
    return fallback


def load_existing_output(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            print(" ⚠️ Existing output is not a JSON object; regenerating")
            return None
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f" ⚠️ Could not read existing output: {e}")
        return None


def strip_last_updated(data: Dict) -> Dict:
    return {k: v for k, v in data.items() if k != "lastUpdated"}


def scrape_event_dates(url: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        print(f"    🌐 Initial URL: {url}")

        # Follow redirects / "Read on" to land on the special page
        content = ""
        for hop in range(3):
            response = requests.get(url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            content = response.text
            url = response.url

            if "/lodestone/special/" in url:
                print(f"    ✅ On special page (hop {hop}): {url}")
                break

            # Direct special-page link in the HTML
            special_match = re.search(
                r'href="(https://[^"]*finalfantasyxiv\.com/lodestone/special/[^"]+)"',
                content,
            )
            if special_match:
                url = special_match.group(1)
                print(f"    🔗 Hop {hop + 1}: Direct special link → {url}")
                continue

            # "Read on" link (sqex.to or direct)
            read_on_href = re.search(
                r'href="(https://(?:sqex\.to|[^"]*finalfantasyxiv\.com)/[^"]+)"[^>]*>[^<]*[Rr]ead\s+on',
                content,
            )
            if not read_on_href:
                read_on_href = re.search(
                    r"[Rr]ead\s+on[^<]*<[^>]+href=\"([^\"]+)\"",
                    content,
                )
            if not read_on_href:
                read_on_href = re.search(
                    r'href="(https://sqex\.to/[^"]+)"',
                    content,
                )

            if read_on_href:
                url = read_on_href.group(1)
                print(f"    🔗 Hop {hop + 1}: Read on link → {url}")
                continue

            print(f"    ⚠️ Hop {hop + 1}: No onward link found at {url}")
            break

        # Parse the meta description on the special page
        meta_match = re.search(
            r'<meta name="description" content="[^"]*?'
            r'From\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)'
            r'(?:\s*\((\w+)\))?'  # optional start TZ
            r'\s+to\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)'
            r'\s*\((\w+)\)',
            content,
            re.IGNORECASE,
        )

        if not meta_match:
            print("    ✗ Meta description date pattern not found")
            return None, None

        (
            start_date,
            start_time,
            start_mer,
            start_tz,
            end_date,
            end_time,
            end_mer,
            end_tz,
        ) = meta_match.groups()

        # Normalize AM/PM
        start_mer = start_mer.replace(".", "").upper()
        end_mer = end_mer.replace(".", "").upper()

        # If start timezone is missing (Hatching-tide), assume same as end
        if not start_tz:
            start_tz = end_tz

        tz_map = {"PST": 8, "PDT": 7, "EST": 5, "EDT": 4}
        s_offset = tz_map.get(start_tz.upper(), 8)
        e_offset = tz_map.get(end_tz.upper(), 8)

        # Parse as UTC-naive, then treat as UTC and shift by offset
        s_dt = datetime.strptime(
            f"{start_date} {start_time} {start_mer}",
            "%B %d, %Y %I:%M %p",
        ).replace(tzinfo=timezone.utc)
        e_dt = datetime.strptime(
            f"{end_date} {end_time} {end_mer}",
            "%B %d, %Y %I:%M %p",
        ).replace(tzinfo=timezone.utc)

        s_ts = int((s_dt + timedelta(hours=s_offset)).timestamp())
        e_ts = int((e_dt + timedelta(hours=e_offset)).timestamp())

        print(
            f"    ✅ Parsed from meta: {start_date} ({start_tz}) → "
            f"{end_date} ({end_tz})"
        )
        return s_ts, e_ts

    except Exception as e:
        print(f"    ✗ Scrape error: {e}")
        return None, None


# Localised Lodestone title patterns identifying "All Worlds" scheduled
# maintenances and emergency maintenances.  The lodestonenews.com feed returns
# each region's article with its localised title (English for na/eu, Japanese
# for jp, French for fr, German for de), so classification must recognise
# every supported language for cross-region matching to work.  Each entry is a
# tuple of lowercase substrings that must all be present in the title.
_SCHEDULED_PATTERNS = [
    ("all worlds maintenance",),             # na / eu
    ("全ワールド", "メンテナンス"),            # jp
    ("maintenance", "tous les mondes"),      # fr
    ("maintenance", "ensemble des mondes"),  # fr (alternate wording)
    ("wartung", "aller welten"),             # de
    ("wartungsarbeiten", "allen welten"),    # de (alternate wording)
]

_EMERGENCY_PATTERNS = [
    ("emergency", "maintenance"),  # na / eu
    ("緊急メンテナンス",),           # jp
    ("臨時メンテナンス",),           # jp (unscheduled maintenance)
    ("maintenance", "urgence"),    # fr
    ("notfallwartung",),           # de
]


def classify_maintenance(title: str) -> Optional[str]:
    """
    Classify a maintenance article title in any supported Lodestone language.

    Returns "scheduled" for regular "All Worlds Maintenance" announcements,
    "emergency" for emergency maintenances (e.g. "Emergency Maintenance (Aug. 7)"
    or "[Chaos] Emergency Server Maintenance"), and None for anything else.
    Emergency patterns are checked first because localised emergency titles also
    contain the scheduled-maintenance keywords (e.g. the Japanese
    "全ワールド 緊急メンテナンス作業のお知らせ" contains "全ワールド" and
    "メンテナンス", and the German "Notfallwartung aller Welten" contains
    "wartung" and "aller welten").
    """
    lower = title.lower()
    for pattern in _EMERGENCY_PATTERNS:
        if all(part in lower for part in pattern):
            return "emergency"
    for pattern in _SCHEDULED_PATTERNS:
        if all(part in lower for part in pattern):
            return "scheduled"
    return None


def parse_maintenance(
    maint_by_region: Dict[str, List[Dict]], now: int
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Select the most-recently published upcoming and last completed
    "All Worlds Maintenance" / emergency maintenance entries and annotate them
    with per-region URLs.

    maint_by_region is a mapping of region → list of items as returned by
    fetch_all_regions("maintenance").  All regions are scanned (NA first, so it
    remains the canonical source for discovery when an article exists in
    multiple regions); entries seen in multiple regions are deduplicated by
    their maintenance window (start/end timestamp pair).
    The reported title is taken from the EU article whenever one exists,
    falling back to the discovery source's title otherwise.
    This ensures emergency maintenances announced only on EU/JP/etc. feeds are
    still detected.
    """
    current, last = None, None
    seen_windows: set = set()

    for region in REGIONS:
        for item in maint_by_region.get(region, []):
            m_type = classify_maintenance(item.get("title", ""))
            if m_type is None:
                continue

            try:
                start_ts = _parse_ts(item.get("start") or "")
                if start_ts is None:
                    continue
                # Emergency maintenances are often announced without an end
                # time; treat a missing end as "ongoing".
                end_ts = _parse_ts(item.get("end") or "")
                pub_ts = _parse_ts(item.get("time") or "")
                if pub_ts is None:
                    continue

                if (start_ts, end_ts) in seen_windows:
                    continue
                seen_windows.add((start_ts, end_ts))

                m_matches = build_maintenance_regional_matches(
                    start_ts, end_ts, m_type, pub_ts, maint_by_region
                )
                m_data = {
                    "title": pick_title(m_matches, item["title"]),
                    "type": m_type,
                    "start": start_ts,
                    "end": end_ts,
                    "pub": pub_ts,
                    # Deprecated – use urls instead.  Kept for one version of
                    # backward compatibility; will be removed in a future release.
                    "url": item["url"],
                    "urls": regional_urls(m_matches),
                }

                if end_ts is not None:
                    ongoing = end_ts > now
                else:
                    # No announced end: treat as ongoing only within a bounded
                    # window after the start so stale articles age out.
                    ongoing = now - start_ts <= NO_END_ONGOING_WINDOW
                if ongoing:
                    if not current or pub_ts > current["pub"]:
                        current = m_data
                else:
                    if not last or pub_ts > last["pub"]:
                        last = m_data

            except Exception as e:
                print(
                    f" ✗ Maintenance parse error for '{item.get('title', '')}': {e}"
                )
                continue

    if current:
        current = {k: v for k, v in current.items() if k != "pub"}
    if last:
        last = {k: v for k, v in last.items() if k != "pub"}

    return current, last


def main() -> None:
    print("=" * 60)
    print("FFXIV Latest News Updater v2.2.1")
    print("=" * 60)

    now = int(datetime.now(timezone.utc).timestamp())

    print("\n📡 Fetching all regions…")
    maint_by_region = fetch_all_regions("maintenance")
    topics_by_region = fetch_all_regions("topics")

    print("\n🔧 Processing Maintenance...")
    current_maint, last_maint = parse_maintenance(maint_by_region, now)
    if current_maint:
        print(f"  ✅ Current: {current_maint['title']}")
    else:
        print("  ℹ️ No upcoming maintenance found")
    if last_maint:
        print(f"  ✅ Last: {last_maint['title']}")

    print("\n🎉 Processing Events...")
    events: List[Dict] = []
    last_event: Optional[Dict] = None
    cutoff = now - (RETENTION_DAYS * 86400)

    # Use NA as canonical source for event discovery; other regions are matched
    # by publication timestamp to build the per-region urls object.  The title
    # is taken from the matched EU article (falling back to NA's title if no
    # EU match is found).
    na_topics = topics_by_region.get("na", [])

    for item in na_topics:
        title = item.get("title", "")
        if not any(kw.lower() in title.lower() for kw in SEASONAL_KEYWORDS):
            continue

        print(f"  📅 Checking: {title}")
        start, end = scrape_event_dates(item["url"])

        if not start or not end:
            print("    ⚠️ Skipping — could not parse dates")
            continue

        na_pub_ts = _parse_ts(item.get("time", ""))
        t_matches = (
            build_topic_regional_matches(na_pub_ts, topics_by_region)
            if na_pub_ts is not None
            else {r: None for r in REGIONS}
        )

        evt = {
            "title": pick_title(t_matches, title),
            "start": start,
            "end": end,
            # Deprecated – use urls instead.  Kept for one version of
            # backward compatibility; will be removed in a future release.
            "url": item["url"],
            "urls": regional_urls(t_matches),
            "category": "seasonal",
        }

        if end > now:
            events.append(evt)
            print("    ✅ Active event added")
        elif end > cutoff:
            if not last_event or end > last_event["end"]:
                last_event = evt
                print("    ✅ Stored as lastEvent")

    output = {
        "version": "2.2.1",
        "source": "lodestonenews.com",
        "maintenance": current_maint,
        "lastMaintenance": last_maint,
        "events": sorted(events, key=lambda x: x["start"]),
        "lastEvent": last_event,
    }

    existing_output = load_existing_output(OUTPUT_FILE)
    if existing_output and strip_last_updated(existing_output) == output:
        print(f"\nℹ️ No meaningful changes detected; leaving {OUTPUT_FILE} unchanged")
        print(f"   Events active: {len(output['events'])}")
        print(f"   Maintenance: {'Yes' if current_maint else 'None'}")
        print("=" * 60)
        return

    output["lastUpdated"] = now

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {OUTPUT_FILE}")
    print(f"   Events active: {len(events)}")
    print(f"   Maintenance: {'Yes' if current_maint else 'None'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
