#!/usr/bin/env python3
"""
FFXIV Latest News Parser
Fetches maintenance and seasonal events from lodestonenews.com
Scrapes Lodestone pages for accurate event start/end dates
"""

import json
import requests
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple, List, Dict

# Configuration
LODESTONE_API = "https://lodestonenews.com/news"
OUTPUT_FILE = "LatestNews.json"

# Event detection keywords
SEASONAL_KEYWORDS = [
    "Valentione", "Heavensturn", "Little Ladies", "Hatching",
    "Make It Rain", "Moonfire", "The Rising", "All Saints", 
    "Starlight", "Moogle Treasure", "Irregular Tomestone"
]


def fetch_api(category: str) -> List[Dict]:
    """Fetch data from lodestonenews.com API"""
    try:
        url = f"{LODESTONE_API}/{category}"
        print(f"  Fetching {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"  ✓ Got {len(data)} items")
        return data
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return []


def scrape_event_dates(url: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Scrape Lodestone event page for start/end dates.
    
    The Topics detail pages often have a "Read on" link to the actual event page.
    We need to follow that link to find the dates.
    
    Returns (start_timestamp, end_timestamp) or (None, None)
    """
    try:
        print(f"    Scraping: {url}")
        
        # Step 1: Fetch the summary page
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        content = response.text
        
        # Step 2: Look for "Read on" link or direct event page link
        # Pattern: href="https://sqex.to/xxxxx" or direct lodestone special page
        read_on_match = re.search(r'href="(https://sqex\.to/[^"]+)"', content)
        special_page_match = re.search(r'href="(https://[^"]*finalfantasyxiv\.com/lodestone/special/[^"]+)"', content)
        
        actual_event_url = None
        
        if special_page_match:
            actual_event_url = special_page_match.group(1)
            print(f"    ℹ️  Found direct event page: {actual_event_url}")
        elif read_on_match:
            sqex_url = read_on_match.group(1)
            print(f"    ℹ️  Following redirect: {sqex_url}")
            
            # Follow the sqex.to redirect
            redirect_response = requests.get(sqex_url, timeout=15, allow_redirects=True)
            actual_event_url = redirect_response.url
            print(f"    ℹ️  Redirected to: {actual_event_url}")
            content = redirect_response.text
        else:
            # Maybe the dates are directly on this page
            print(f"    ℹ️  No redirect found, checking current page")
        
        # If we found a different URL, fetch it
        if actual_event_url and actual_event_url != url:
            response = requests.get(actual_event_url, timeout=15)
            response.raise_for_status()
            content = response.text
        
        # Step 3: Now scrape for dates with multiple patterns
        
        # Pattern 1: Full "from...to" format with periods in a.m./p.m.
        pattern1 = (
            r'from\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+(a\.m\.|p\.m\.)\s+\((\w+)\)\s+'
            r'to\s+\w+,\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+:\d+)\s+(a\.m\.|p\.m\.)'
        )
        
        # Pattern 2: "...until..." format without periods
        pattern2 = (
            r'(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+(?::\d+)?)\s+(am|pm)\s+\((\w+)\)\s+'
            r'(?:until|to)\s+(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+(?::\d+)?)\s+(am|pm)'
        )
        
        # Pattern 3: Just dates with "to" (fallback)
        pattern3 = (
            r'(\w+,\s+)?(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+(?::\d+)?)\s+(am|pm|a\.m\.|p\.m\.)\s+\((\w+)\)\s+'
            r'(?:to|until)\s+(\w+,\s+)?(\w+\s+\d+,\s+\d{4})\s+at\s+(\d+(?::\d+)?)\s+(am|pm|a\.m\.|p\.m\.)'
        )
        
        match = None
        pattern_used = None
        
        # Try pattern 1
        match = re.search(pattern1, content, re.IGNORECASE)
        if match:
            pattern_used = 1
            start_date = match.group(1)
            start_time = match.group(2)
            start_meridiem = match.group(3).replace('.', '').upper()
            timezone_str = match.group(4).upper()
            end_date = match.group(5)
            end_time = match.group(6)
            end_meridiem = match.group(7).replace('.', '').upper()
        
        # Try pattern 2
        if not match:
            match = re.search(pattern2, content, re.IGNORECASE)
            if match:
                pattern_used = 2
                start_date = match.group(1)
                start_time = match.group(2) if ':' in match.group(2) else f"{match.group(2)}:00"
                start_meridiem = match.group(3).upper()
                timezone_str = match.group(4).upper()
                end_date = match.group(5)
                end_time = match.group(6) if ':' in match.group(6) else f"{match.group(6)}:00"
                end_meridiem = match.group(7).upper()
        
        # Try pattern 3
        if not match:
            match = re.search(pattern3, content, re.IGNORECASE)
            if match:
                pattern_used = 3
                start_date = match.group(2)
                start_time = match.group(3) if ':' in match.group(3) else f"{match.group(3)}:00"
                start_meridiem = match.group(4).replace('.', '').upper()
                timezone_str = match.group(5).upper()
                end_date = match.group(7)
                end_time = match.group(8) if ':' in match.group(8) else f"{match.group(8)}:00"
                end_meridiem = match.group(9).replace('.', '').upper()
        
        if not match:
            print(f"    ✗ No date pattern found on page")
            return None, None
        
        print(f"    ℹ️  Using pattern {pattern_used}")
        
        # Ensure time has minutes
        if ':' not in start_time:
            start_time = f"{start_time}:00"
        if ':' not in end_time:
            end_time = f"{end_time}:00"
        
        # Parse datetimes
        start_dt = datetime.strptime(
            f"{start_date} {start_time} {start_meridiem}", 
            "%B %d, %Y %I:%M %p"
        )
        end_dt = datetime.strptime(
            f"{end_date} {end_time} {end_meridiem}", 
            "%B %d, %Y %I:%M %p"
        )
        
        # Convert to UTC
        tz_offsets = {
            "PST": 8, "PDT": 7,
            "EST": 5, "EDT": 4,
            "JST": -9, "CET": -1, "CEST": -2
        }
        offset_hours = tz_offsets.get(timezone_str, 8)
        
        start_utc = start_dt + timedelta(hours=offset_hours)
        end_utc = end_dt + timedelta(hours=offset_hours)
        
        start_ts = int(start_utc.timestamp())
        end_ts = int(end_utc.timestamp())
        
        print(f"    ✓ Start: {start_utc.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"    ✓ End:   {end_utc.strftime('%Y-%m-%d %H:%M UTC')}")
        
        return start_ts, end_ts
        
    except Exception as e:
        print(f"    ✗ Scrape error: {e}")
        return None, None


def parse_maintenance(data: List[Dict]) -> Optional[Dict]:
    """Parse maintenance announcements"""
    now = int(datetime.now(timezone.utc).timestamp())
    
    for item in data:
        title = item.get('title', '')
        description = item.get('description', '')
        url = item.get('url', '')
        
        # Only process "All Worlds Maintenance"
        if "All Worlds Maintenance" not in title:
            continue
        
        # Parse date range from description
        # Format: "Wed, Feb 4 9:00 PM to Thu, Feb 5 2:00 AM (PST)"
        pattern = r'(\w+,\s+\w+\s+\d+\s+\d+:\d+\s+(?:AM|PM)).*?to\s+(\w+,\s+\w+\s+\d+\s+\d+:\d+\s+(?:AM|PM))\s+\((\w+)\)'
        match = re.search(pattern, description)
        
        if not match:
            continue
        
        try:
            current_year = datetime.now().year
            start_str, end_str, tz = match.groups()
            
            # Parse datetimes (Lodestone doesn't include year in maintenance announcements)
            start_dt = datetime.strptime(f"{start_str} {current_year}", "%a, %b %d %I:%M %p %Y")
            end_dt = datetime.strptime(f"{end_str} {current_year}", "%a, %b %d %I:%M %p %Y")
            
            # Handle year rollover
            if end_dt < start_dt:
                end_dt = end_dt.replace(year=current_year + 1)
            
            # Convert to UTC
            offset = {"PST": 8, "PDT": 7, "EST": 5, "EDT": 4}.get(tz, 8)
            start_utc = start_dt + timedelta(hours=offset)
            end_utc = end_dt + timedelta(hours=offset)
            
            start_ts = int(start_utc.timestamp())
            end_ts = int(end_utc.timestamp())
            
            # Only return if maintenance hasn't ended
            if end_ts > now:
                print(f"  ✓ {title}")
                return {
                    "title": title,
                    "start": start_ts,
                    "end": end_ts,
                    "url": url
                }
                
        except Exception as e:
            print(f"  ✗ Parse error: {e}")
            continue
    
    return None


def parse_events(data: List[Dict], existing_events: List[Dict]) -> List[Dict]:
    """Parse seasonal events from Topics"""
    now = int(datetime.now(timezone.utc).timestamp())
    events = []
    processed_urls = set()
    
    # Keep existing non-expired events
    for event in existing_events:
        if event.get('end', 0) > now:
            events.append(event)
            processed_urls.add(event['url'])
            print(f"  ✓ Keeping: {event['title']}")
    
    # Check for new events in Topics
    for item in data:
        title = item.get('title', '')
        description = item.get('description', '')
        url = item.get('url', '')
        
        # Skip if already processed
        if url in processed_urls:
            continue
        
        # Check if this is a seasonal event
        if not any(kw.lower() in title.lower() for kw in SEASONAL_KEYWORDS):
            continue
        
        print(f"  🆕 New event: {title}")
        
        # Scrape Lodestone page for dates
        start, end = scrape_event_dates(url)
        
        if start and end and end > now:
            category = "seasonal"
            if "moogle" in title.lower() or "tomestone" in title.lower():
                category = "event"
            
            events.append({
                "title": title,
                "category": category,
                "start": start,
                "end": end,
                "url": url,
                "description": description[:150]
            })
            processed_urls.add(url)
            print(f"    ✓ Added to events")
        else:
            print(f"    ✗ Skipped (no dates or expired)")
    
    # Sort by start date
    return sorted(events, key=lambda x: x['start'])


def load_existing_data() -> Dict:
    """Load existing LatestNews.json if it exists"""
    output_path = Path(OUTPUT_FILE)
    if output_path.exists():
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load existing file: {e}")
    
    return {
        "version": "2.0.0",
        "lastUpdated": 0,
        "source": "lodestonenews.com",
        "maintenance": None,
        "events": []
    }


def main():
    print("=" * 60)
    print("FFXIV Latest News Updater")
    print("=" * 60)
    
    # Load existing data
    existing_data = load_existing_data()
    
    # Fetch from API
    print("\n📡 Fetching from lodestonenews.com API...")
    maintenance_data = fetch_api("maintenance")
    topics_data = fetch_api("topics")
    
    # Parse maintenance
    print("\n🔧 Processing maintenance...")
    maintenance = parse_maintenance(maintenance_data)
    if not maintenance:
        print("  ℹ️  No upcoming maintenance")
    
    # Parse events
    print("\n🎉 Processing events...")
    events = parse_events(topics_data, existing_data.get('events', []))
    
    # Build output
    output = {
        "version": "2.0.0",
        "lastUpdated": int(datetime.now(timezone.utc).timestamp()),
        "source": "lodestonenews.com",
        "maintenance": maintenance,
        "events": events
    }
    
    # Write to file
    output_path = Path(OUTPUT_FILE)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"\n✅ Wrote {OUTPUT_FILE}")
    print(f"   Maintenance: {maintenance['title'] if maintenance else 'None'}")
    print(f"   Active Events: {len(events)}")
    for event in events:
        end_date = datetime.fromtimestamp(event['end'], tz=timezone.utc)
        print(f"     - {event['title']} (until {end_date.strftime('%b %d')})")
    print("=" * 60)


if __name__ == "__main__":
    main()
