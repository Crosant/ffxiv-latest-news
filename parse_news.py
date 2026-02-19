#!/usr/bin/env python3
import json
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
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
    """Surgical scraper that ignores image alt-text and finds the 2026 dates."""
    try:
        print(f"    🌐 Initial URL: {url}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text

        # 1. Follow redirect to Special Site (where the real code lives)
        special_match = re.search(r'href="(https://[^"]*finalfantasyxiv\.com/lodestone/special/[^"]+)"', content)
        if special_match:
            url = special_match.group(1)
            print(f"    🔗 Jumping to Special Page: {url}")
            response = requests.get(url, timeout=15)
            content = response.text

        # 2. TARGETED: Isolate the visible date paragraph <p class="na">
        # This completely bypasses the 2015 image alt text
        p_match = re.search(r'<p class="na">.*?</p>', content, re.DOTALL | re.IGNORECASE)
        if not p_match:
            print(f"    ⚠️ Warning: Date paragraph (<p class='na'>) not found")
            return None, None
            
        # Clean tags (like <br />) so regex doesn't choke
        clean_text = re.sub(r'<[^>]+>', ' ', p_match.group(0))

        # 3. Flexible regex for the "From... to..." pattern
        pattern = (
            r'[Ff]rom\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)\s*'
            r'to\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+([ap]\.m\.)\s+\((\w+)\)'
        )
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if not match:
            print(f"    ✗ Date pattern failed inside the targeted block.")
            return None, None

        start_date, start_time, start_mer, end_date, end_time, end_mer, tz = match.groups()
        s_mer, e_mer = start_mer.replace('.', '').upper(), end_mer.replace('.', '').upper()
        
        s_dt = datetime.strptime(f"{start_date} {start_time} {s_mer}", "%B %d, %Y %I:%M %p")
        e_dt = datetime.strptime(f"{end_date} {end_time} {e_mer}", "%B %d, %Y %I:%M %p")

        # UTC-8 for PST, etc.
        tz_map = {"PST": 8, "PDT": 7, "EST": 5, "EDT": 4}
        offset = tz_map.get(tz.upper(), 8)
        
        return int((s_dt + timedelta(hours=offset)).timestamp()), int((e_dt + timedelta(hours=offset)).timestamp())
    except Exception as e:
        print(f"    ✗ Scrape error: {e}")
        return None, None

def parse_maintenance(maint_list: List[Dict], now: int) -> Tuple[Optional[Dict], Optional[Dict]]:
    current, last = None, None
    for item in maint_list:
        if "All Worlds Maintenance" not in item.get('title', ''): continue
        description = item.get('description', '')
        if not description: continue

        # Extract EST/EDT time directly to avoid the 8:10 vs 3:10 bug
        pattern = r'to\s+\w+,\s+\w+\s+\d+\s+(\d+:\d+\s+[APM]+)\s+\((\w+)\)'
        match = re.search(pattern, description)
        if not match: continue
        
        try:
            time_str, tz_name = match.groups()
            year = datetime.now().year
            date_match = re.search(r'(\w+\s+\d+)', description)
            date_str = date_match.group(1)

            e_dt = datetime.strptime(f"{date_str} {time_str} {year}", "%b %d %I:%M %p %Y")
            offset = {"PST": 8, "PDT": 7, "EST": 5, "EDT": 4}.get(tz_name.upper(), 8)
            e_ts = int((e_dt + timedelta(hours=offset)).timestamp())

            m_data = {"title": item['title'], "start": e_ts - 14400, "end": e_ts, "url": item['url']}
            if e_ts > now:
                if not current: current = m_data
            else:
                if not last or e_ts > last['end']: last = m_data
        except: continue
    return current, last

def main():
    print("=" * 60 + "\nFFXIV Latest News Updater - PRODUCTION FIX\n" + "=" * 60)
    now = int(datetime.now(timezone.utc).timestamp())
    topics, maint_list = fetch_api("topics"), fetch_api("maintenance")
    
    current_maint, last_maint = parse_maintenance(maint_list, now)
    
    events, last_event = [], None
    cutoff = now - (RETENTION_DAYS * 86400)
    
    print("\n🎉 Processing Events...")
    for item in topics:
        if any(kw.lower() in item.get('title', '').lower() for kw in SEASONAL_KEYWORDS):
            print(f"  📅 Checking: {item['title']}")
            start, end = scrape_event_dates(item['url'])
            if start and end:
                evt = {"title": item['title'], "start": start, "end": end, "url": item['url'], "category": "seasonal"}
                if end > now:
                    events.append(evt)
                    print(f"    ✅ Added as Active")
                elif end > cutoff:
                    if not last_event or end > last_event['end']:
                        last_event = evt
                        print(f"    ✅ Added as Last Event")

    output = {
        "version": "2.0.0",
        "lastUpdated": now,
        "maintenance": current_maint,
        "lastMaintenance": last_maint,
        "events": sorted(events, key=lambda x: x['start']),
        "lastEvent": last_event
    }

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Wrote {OUTPUT_FILE}\n" + "=" * 60)

if __name__ == "__main__":
    main()