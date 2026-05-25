#!/usr/bin/env python3
"""
FFXIV Lodestone Maintenance Feed Parser

Fetches the latest maintenance information from lodestonenews.com RSS feed
and outputs it in a simple JSON format for consumption by plugins and tools.
"""

import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime
from urllib.request import urlopen
from urllib.error import URLError

RSS_FEED_URL = "https://lodestonenews.com/feed/na.xml"

def fetch_rss_feed():
    """Download the RSS feed from lodestonenews.com"""
    try:
        with urlopen(RSS_FEED_URL, timeout=30) as response:
            return response.read().decode('utf-8')
    except URLError as e:
        print(f"Error fetching RSS feed: {e}")
        return None

def parse_maintenance_date(description):
    """
    Parse maintenance window from description text.
    
    Example input:
    "Wed, Feb 4 9:00 PM to Thu, Feb 5 2:00 AM (PST)<br>Thu, Feb 5 12:00 AM to Thu, Feb 5 5:00 AM (EST)"
    
    We'll use the PST times as the canonical source.
    Returns: (start_timestamp, end_timestamp) as UNIX timestamps
    """
    # Extract PST time range (before <br>)
    pst_match = re.search(r'([A-Za-z]+, [A-Za-z]+ \d+ \d+:\d+ [AP]M) to ([A-Za-z]+, [A-Za-z]+ \d+ \d+:\d+ [AP]M) \(PST\)', description)
    
    if not pst_match:
        print(f"Could not parse maintenance times from: {description}")
        return None, None
    
    start_str = pst_match.group(1)
    end_str = pst_match.group(2)
    
    # Parse dates - they include day of week which we need to strip
    # Format: "Wed, Feb 4 9:00 PM"
    try:
        # Remove day of week, parse the rest
        start_clean = re.sub(r'^\w+, ', '', start_str)
        end_clean = re.sub(r'^\w+, ', '', end_str)
        
        # Get current year (Lodestone doesn't include year in descriptions)
        current_year = datetime.now().year
        
        # Parse as if current year
        start_dt = datetime.strptime(f"{start_clean} {current_year}", "%b %d %I:%M %p %Y")
        end_dt = datetime.strptime(f"{end_clean} {current_year}", "%b %d %I:%M %p %Y")
        
        # Convert PST to UTC (PST is UTC-8)
        from datetime import timedelta
        start_dt_utc = start_dt + timedelta(hours=8)
        end_dt_utc = end_dt + timedelta(hours=8)
        
        # If end is before start, it crossed midnight - add a day to end
        if end_dt_utc < start_dt_utc:
            end_dt_utc += timedelta(days=1)
        
        # Convert to UNIX timestamps
        start_ts = int(start_dt_utc.timestamp())
        end_ts = int(end_dt_utc.timestamp())
        
        return start_ts, end_ts
        
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        return None, None

def find_next_maintenance(rss_content):
    """
    Parse RSS feed and find the next scheduled maintenance.
    Returns maintenance info or None if no maintenance scheduled.
    """
    try:
        root = ET.fromstring(rss_content)
        
        # Find all items in the feed
        for item in root.findall('.//item'):
            title_elem = item.find('title')
            category_elem = item.find('category')
            description_elem = item.find('description')
            link_elem = item.find('link')
            
            if title_elem is None or category_elem is None:
                continue
            
            title = title_elem.text
            category = category_elem.text
            
            # Look for maintenance items
            if category == 'Maintenance' and title.startswith('All Worlds Maintenance'):
                description = description_elem.text if description_elem is not None else ""
                url = link_elem.text if link_elem is not None else ""
                
                # Parse the maintenance window
                start_ts, end_ts = parse_maintenance_date(description)
                
                if start_ts and end_ts:
                    # Check if this maintenance is in the future or ongoing
                    now = int(datetime.now().timestamp())
                    
                    if end_ts > now:  # Maintenance hasn't ended yet
                        return {
                            'title': title,
                            'start': start_ts,
                            'end': end_ts,
                            'url': url
                        }
        
        # No future maintenance found
        return None
        
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return None

def generate_output(maintenance_info):
    """
    Generate the output JSON structure.
    """
    output = {
        'version': '1.0.0',
        'lastUpdated': int(datetime.now().timestamp()),
        'source': 'lodestonenews.com',
        'maintenance': None
    }
    
    if maintenance_info:
        output['maintenance'] = maintenance_info
    
    return output

def main():
    print("Fetching FFXIV Lodestone maintenance information...")
    
    # Fetch RSS feed
    rss_content = fetch_rss_feed()
    if not rss_content:
        print("Failed to fetch RSS feed")
        return
    
    # Parse for maintenance
    maintenance = find_next_maintenance(rss_content)
    
    # Generate output
    output = generate_output(maintenance)
    
    # Save to file
    with open('LatestNews.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    # Print summary
    if maintenance:
        start_date = datetime.fromtimestamp(maintenance['start']).strftime('%Y-%m-%d %I:%M %p UTC')
        end_date = datetime.fromtimestamp(maintenance['end']).strftime('%Y-%m-%d %I:%M %p UTC')
        print(f"✓ Found maintenance: {maintenance['title']}")
        print(f"  Start: {start_date}")
        print(f"  End: {end_date}")
    else:
        print("✓ No scheduled maintenance found")
    
    print("✓ LatestNews.json updated successfully")

if __name__ == '__main__':
    main()
