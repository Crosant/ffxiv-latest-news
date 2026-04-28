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
    "Starlight", "Moogle Treasure", "Irregular Tomestone"
]


def fetch_api(category: str, region: str = "na") -> List[Dict]:
    try:
        url = f"{LODESTONE_API}/{category}?region={region}"
        print(f"📡 Fetching {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f" ✗ Error fetching {category} ({region}): {e}")
        return []


def fetch_all_regions(category: str) -> Dict[str, List[Dict]]:
    """Fetch the given category from every supported Lodestone region."""
    return {region: fetch_api(category, region) for region in REGIONS}


def _lodestone_path(url: str) -> Optional[str]:
    """
    Extract the article path after the regional subdomain from a Lodestone URL.

    Example:
        "https://na.finalfantasyxiv.com/lodestone/news/detail/abc123"
        → "/lodestone/news/detail/abc123"

    The path segment (including the article ID) is identical across all Lodestone
    regions for the same article, making it a reliable cross-region match key.
    """
    m = re.match(r"https://\w+\.finalfantasyxiv\.com(/lodestone/.+)", url)
    return m.group(1) if m else None


def build_regional_urls(
    na_url: str, region_items: Dict[str, List[Dict]]
) -> Dict[str, Optional[str]]:
    """
    For a given canonical (NA) article URL, find the corresponding URL for each
    supported region by looking up that article's path in each region's feed data.

    Matching is done by comparing the article path (e.g. /lodestone/news/detail/{id}),
    which Square Enix keeps consistent across Lodestone regions.  A region URL is
    only emitted when the article actually appears in that region's fetched feed;
    no URL is fabricated by blind hostname substitution.  If an article is absent
    from a region's feed the value is null.
    """
    target_path = _lodestone_path(na_url)
    urls: Dict[str, Optional[str]] = {}
    for region in REGIONS:
        urls[region] = None
        if target_path is None:
            continue
        for item in region_items.get(region, []):
            if _lodestone_path(item.get("url", "")) == target_path:
                urls[region] = item["url"]
                break
    return urls


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


def parse_maintenance(
    maint_by_region: Dict[str, List[Dict]], now: int
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """
    Select the most-recently published upcoming and last completed
    "All Worlds Maintenance" entries and annotate them with per-region URLs.

    maint_by_region is a mapping of region → list of items as returned by
    fetch_all_regions("maintenance").  The NA feed is used as the canonical
    source; other regions are matched by article path to populate urls.
    """
    current, last = None, None
    na_items = maint_by_region.get("na", [])

    for item in na_items:
        if "All Worlds Maintenance" not in item.get("title", ""):
            continue

        try:
            start_ts = int(
                datetime.fromisoformat(
                    item["start"].replace("Z", "+00:00")
                ).timestamp()
            )
            end_ts = int(
                datetime.fromisoformat(
                    item["end"].replace("Z", "+00:00")
                ).timestamp()
            )
            pub_ts = int(
                datetime.fromisoformat(
                    item["time"].replace("Z", "+00:00")
                ).timestamp()
            )

            m_data = {
                "title": item["title"],
                "start": start_ts,
                "end": end_ts,
                "pub": pub_ts,
                # Deprecated – use urls instead.  Kept for one version of
                # backward compatibility; will be removed in a future release.
                "url": item["url"],
                "urls": build_regional_urls(item["url"], maint_by_region),
            }

            if end_ts > now:
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
    print("FFXIV Latest News Updater v2.1.0")
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
    # by article path to build the per-region urls object.
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

        evt = {
            "title": title,
            "start": start,
            "end": end,
            # Deprecated – use urls instead.  Kept for one version of
            # backward compatibility; will be removed in a future release.
            "url": item["url"],
            "urls": build_regional_urls(item["url"], topics_by_region),
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
        "version": "2.1.0",
        "lastUpdated": now,
        "source": "lodestonenews.com",
        "maintenance": current_maint,
        "lastMaintenance": last_maint,
        "events": sorted(events, key=lambda x: x["start"]),
        "lastEvent": last_event,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {OUTPUT_FILE}")
    print(f"   Events active: {len(events)}")
    print(f"   Maintenance: {'Yes' if current_maint else 'None'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
