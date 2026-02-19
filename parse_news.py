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

SEASONAL_KEYWORDS = [
    "Valentione", "Heavensturn", "Little Ladies", "Hatching",
    "Make It Rain", "Moonfire", "The Rising", "All Saints",
    "Starlight", "Moogle Treasure", "Irregular Tomestone"
]


def fetch_api(category: str) -> List[Dict]:
    try:
        url = f"{LODESTONE_API}/{category}"
        print(f"📡 Fetching {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"  ✗ Error fetching {category}: {e}")
        return []


def scrape_event_dates(url: str) -> Tuple[Optional[int], Optional[int]]:
    try:
        print(f"    🌐 Initial URL: {url}")

        for hop in range(3):
            response = requests.get(url, timeout=15, allow_redirects=True)
            response.raise_for_status()
            content = response.text
            url = response.url

            if '/lodestone/special/' in url:
                print(f"    ✅ On special page (hop {hop}): {url}")
                break

            special_match = re.search(
                r'href="(https://[^"]*finalfantasyxiv\.com/lodestone/special/[^"]+)"',
                content
            )
            if special_match:
                url = special_match.group(1)
                print(f"    🔗 Hop {hop + 1}: Direct special link → {url}")
                continue

            read_on_href = re.search(
                r'href="(https://(?:sqex\.to|[^"]*finalfantasyxiv\.com)/[^"]+)"[^>]*>[^<]*[Rr]ead\s+on',
                content
            )
            if not read_on_href:
                read_on_href = re.search(
                    r'[Rr]ead\s+on[^<]*<[^>]+href="([^"]+)"',
                    content
                )
            if not read_on_href:
                read_on_href = re.search(r'href="(https://sqex\.to/[^"]+)"', content)

            if read_on_href:
                url = read_on_href.group(1)
                print(f"    🔗 Hop {hop + 1}: Read on link → {url}")
                continue

            print(f"    ⚠️ Hop {hop + 1}: No onward link found at {url}")
            break

        meta_match = re.search(
            r'<meta name="description" content="[^"]*'
            r'[Ff]rom\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)\s*\((\w+)\)'
            r'\s+to\s+'
            r'\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)\s*\((\w+)\)',
            content,
            re.IGNORECASE
        )

        if not meta_match:
            print(f"    ✗ Meta description date pattern not found")
            return None, None

        start_date, start_time, start_mer, start_tz, \
        end_date,   end_time,   end_mer,   end_tz = meta_match.groups()

        tz_map = {"PST": 8, "PDT": 7, "EST": 5, "EDT": 4}
        s_offset = tz_map.get(start_tz.upper(), 8)
        e_offset = tz_map.get(end_tz.upper(), 8)

        # Parse as UTC-naive, then manually shift to UTC using the timezone offset
        # Without .replace(tzinfo=timezone.utc), Python assumes your LOCAL timezone
        # (your PC is EST = UTC-5) and applies that on top, making times 5 hours wrong
        s_dt = datetime.strptime(
            f"{start_date} {start_time} {start_mer.replace('.', '').upper()}",
            "%B %d, %Y %I:%M %p"
        ).replace(tzinfo=timezone.utc)

        e_dt = datetime.strptime(
            f"{end_date} {end_time} {end_mer.replace('.', '').upper()}",
            "%B %d, %Y %I:%M %p"
        ).replace(tzinfo=timezone.utc)

        s_ts = int((s_dt + timedelta(hours=s_offset)).timestamp())
        e_ts = int((e_dt + timedelta(hours=e_offset)).timestamp())

        print(f"    ✅ {start_date} ({start_tz}) → {end_date} ({end_tz})")
        return s_ts, e_ts

    except Exception as e:
        print(f"    ✗ Scrape error: {e}")
        return None, None


def parse_maintenance(maint_list: List[Dict], now: int) -> Tuple[Optional[Dict], Optional[Dict]]:
    current, last = None, None

    for item in maint_list:
        if "All Worlds Maintenance" not in item.get('title', ''):
            continue

        try:
            start_ts = int(datetime.fromisoformat(
                item['start'].replace('Z', '+00:00')
            ).timestamp())
            end_ts = int(datetime.fromisoformat(
                item['end'].replace('Z', '+00:00')
            ).timestamp())
            pub_ts = int(datetime.fromisoformat(
                item['time'].replace('Z', '+00:00')  # 'time' = publication date
            ).timestamp())

            m_data = {
                'title': item['title'],
                'start': start_ts,
                'end': end_ts,
                'pub': pub_ts,
                'url': item['url']
            }

            if end_ts > now:
                if not current or pub_ts > current['pub']:
                    current = m_data
            else:
                if not last or pub_ts > last['pub']:
                    last = m_data

        except Exception as e:
            print(f"  ✗ Maintenance parse error for '{item.get('title', '')}': {e}")
            continue

    if current:
        current = {k: v for k, v in current.items() if k != 'pub'}
    if last:
        last = {k: v for k, v in last.items() if k != 'pub'}

    return current, last



def main():
    print("=" * 60)
    print("FFXIV Latest News Updater v2.0.0")
    print("=" * 60)

    now = int(datetime.now(timezone.utc).timestamp())

    topics = fetch_api("topics")
    maint_list = fetch_api("maintenance")

    print("\n🔧 Processing Maintenance...")
    current_maint, last_maint = parse_maintenance(maint_list, now)
    if current_maint:
        print(f"  ✅ Current: {current_maint['title']}")
    else:
        print(f"  ℹ️ No upcoming maintenance found")
    if last_maint:
        print(f"  ✅ Last: {last_maint['title']}")

    print("\n🎉 Processing Events...")
    events, last_event = [], None
    cutoff = now - (RETENTION_DAYS * 86400)

    for item in topics:
        title = item.get('title', '')
        if not any(kw.lower() in title.lower() for kw in SEASONAL_KEYWORDS):
            continue

        print(f"  📅 Checking: {title}")
        start, end = scrape_event_dates(item['url'])

        if not start or not end:
            print(f"    ⚠️ Skipping — could not parse dates")
            continue

        evt = {
            'title': title,
            'start': start,
            'end': end,
            'url': item['url'],
            'category': 'seasonal'
        }

        if end > now:
            events.append(evt)
            print(f"    ✅ Active event added")
        elif end > cutoff:
            if not last_event or end > last_event['end']:
                last_event = evt
                print(f"    ✅ Stored as lastEvent")

    output = {
        "version": "2.0.0",
        "lastUpdated": now,
        "source": "lodestonenews.com",
        "maintenance": current_maint,
        "lastMaintenance": last_maint,
        "events": sorted(events, key=lambda x: x['start']),
        "lastEvent": last_event
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {OUTPUT_FILE}")
    print(f"   Events active: {len(events)}")
    print(f"   Maintenance: {'Yes' if current_maint else 'None'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
