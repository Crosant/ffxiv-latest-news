# FFXIV Latest News API

Automated JSON API providing FFXIV maintenance schedules and seasonal events.

## 📡 API Endpoint

```
https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json
```

## 📋 Response Format

```json
{
  "version": "2.2.0",
  "lastUpdated": 1739692800,
  "source": "lodestonenews.com",
  "maintenance": {
    "title": "All Worlds Maintenance (Feb. 16)",
    "type": "scheduled",
    "start": 1739692800,
    "end": 1739703600,
    "url": "https://na.finalfantasyxiv.com/lodestone/news/detail/...",
    "urls": {
      "na": "https://na.finalfantasyxiv.com/lodestone/news/detail/...",
      "eu": "https://eu.finalfantasyxiv.com/lodestone/news/detail/...",
      "jp": "https://jp.finalfantasyxiv.com/lodestone/news/detail/...",
      "fr": "https://fr.finalfantasyxiv.com/lodestone/news/detail/...",
      "de": "https://de.finalfantasyxiv.com/lodestone/news/detail/..."
    }
  },
  "events": [
    {
      "title": "Valentione's Day (2026)",
      "category": "seasonal",
      "start": 1738483200,
      "end": 1739692740,
      "url": "https://na.finalfantasyxiv.com/lodestone/topics/detail/...",
      "urls": {
        "na": "https://na.finalfantasyxiv.com/lodestone/topics/detail/...",
        "eu": "https://eu.finalfantasyxiv.com/lodestone/topics/detail/...",
        "jp": "https://jp.finalfantasyxiv.com/lodestone/topics/detail/...",
        "fr": "https://fr.finalfantasyxiv.com/lodestone/topics/detail/...",
        "de": "https://de.finalfantasyxiv.com/lodestone/topics/detail/..."
      }
    }
  ]
}
```

### Fields

- **version** (string): API format version
- **lastUpdated** (number): UNIX timestamp of the last meaningful data update (UTC)
- **source** (string): Data source attribution
- **maintenance** (object|null): Next upcoming or ongoing maintenance, or null if none
  - **maintenance.title** (string): Maintenance title, taken from the EU Lodestone article (falls back to the discovery region's title if no EU match is found)
  - **maintenance.type** (string): `"scheduled"` for regular All Worlds maintenances, `"emergency"` for emergency maintenances
  - **maintenance.start** (number): Start time (UNIX timestamp, UTC)
  - **maintenance.end** (number|null): End time (UNIX timestamp, UTC); `null` when no end time has been announced yet (common for emergency maintenances). Consumers should handle `null` and use `start` vs current time to distinguish upcoming vs in-progress maintenances.
  - **maintenance.url** (string): ⚠️ *Deprecated* – NA Lodestone URL; use `urls.na` instead
  - **maintenance.urls** (object): Per-region Lodestone URLs (see [Regions](#-regions))
- **lastMaintenance** (object|null): Most recent completed maintenance (same shape as `maintenance`)
- **events** (array): Active and upcoming seasonal events
  - **events[].title** (string): Event title, taken from the EU Lodestone article (falls back to the NA title if no EU match is found)
  - **events[].category** (string): `"seasonal"`
  - **events[].start** (number): Start time (UNIX timestamp, UTC)
  - **events[].end** (number): End time (UNIX timestamp, UTC)
  - **events[].url** (string): ⚠️ *Deprecated* – NA Lodestone URL; use `urls.na` instead
  - **events[].urls** (object): Per-region Lodestone URLs (see [Regions](#-regions))
- **lastEvent** (object|null): Most recently expired seasonal event (same shape as events items)

### 🌍 Regions

Each `urls` object contains a key for every supported Lodestone region.
A value of `null` means that article was not found in that region's feed.

| Key | Lodestone Region |
|-----|-----------------|
| `na` | North America |
| `eu` | Europe |
| `jp` | Japan |
| `fr` | France |
| `de` | Germany |

> **Example** – reading the EU maintenance link:
> ```js
> const euUrl = data.maintenance.urls.eu;
> ```

### ⚠️ Deprecation Notice (v2.1.0)

The top-level `url` field on maintenance and event objects is **deprecated** and will be
removed in a future major version.  Migrate to `urls.na` (or whichever region your users
are in) as soon as convenient.

```js
// Before (deprecated)
const link = event.url;

// After
const link = event.urls.eu ?? event.urls.na;
```

## 🔄 Update Schedule

- **Every 6 hours** via GitHub Actions
- Fetches from [lodestonenews.com](https://lodestonenews.com) API for **all 5 regions**
- Matches articles across regions using content-aware keys (not article ID or hostname substitution):
  - *Maintenance*: matched by `(start_ts, end_ts)` **and** maintenance classification — several distinct articles (e.g. Companion App maintenance) can share the same window
  - *Events/Topics*: matched by publication timestamp within ±24 hours
- Detects both scheduled ("All Worlds Maintenance") and emergency maintenances, scanning **all** region feeds so region-specific emergency announcements (e.g. EU-only) are not missed
- Follows "Read on" links to scrape actual event dates from Lodestone special pages
- Automatically removes expired events

## 🚀 Usage Examples

### JavaScript

```javascript
fetch('https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json')
  .then(res => res.json())
  .then(data => {
    // Pick the EU region URL, falling back to NA
    function regionUrl(item, region = 'eu') {
      return item?.urls?.[region] ?? item?.urls?.na ?? null;
    }

    if (data.maintenance) {
      const start = new Date(data.maintenance.start * 1000);
      const end   = new Date(data.maintenance.end   * 1000);
      console.log(`Maintenance: ${data.maintenance.title}`);
      console.log(`${start.toLocaleString()} – ${end.toLocaleString()}`);
      console.log(`EU link: ${regionUrl(data.maintenance, 'eu')}`);
    }

    data.events.forEach(event => {
      const endDate = new Date(event.end * 1000);
      console.log(`${event.title} – ends ${endDate.toLocaleDateString()}`);
      console.log(`EU link: ${regionUrl(event, 'eu')}`);
    });
  });
```

### Python

```python
import requests
from datetime import datetime

response = requests.get(
    'https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json'
)
data = response.json()

def region_url(item, region='eu'):
    """Return the Lodestone link for the requested region, falling back to NA."""
    urls = item.get('urls') or {}
    return urls.get(region) or urls.get('na')

if data['maintenance']:
    m = data['maintenance']
    start = datetime.fromtimestamp(m['start'])
    end   = datetime.fromtimestamp(m['end'])
    print(f"Maintenance: {m['title']}")
    print(f"{start} – {end}")
    print(f"EU link: {region_url(m, 'eu')}")

for event in data['events']:
    end_date = datetime.fromtimestamp(event['end'])
    print(f"{event['title']} – ends {end_date.strftime('%B %d, %Y')}")
    print(f"EU link: {region_url(event, 'eu')}")
```

### C# (.NET)

```csharp
using System.Net.Http;
using System.Text.Json;

var client = new HttpClient();
var json = await client.GetStringAsync(
    "https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json"
);

using var doc = JsonDocument.Parse(json);
var root = doc.RootElement;

string? RegionUrl(JsonElement item, string region = "eu")
{
    if (item.TryGetProperty("urls", out var urls))
    {
        if (urls.TryGetProperty(region, out var r) && r.ValueKind == JsonValueKind.String)
            return r.GetString();
        if (urls.TryGetProperty("na", out var na) && na.ValueKind == JsonValueKind.String)
            return na.GetString();
    }
    return null;
}

// Check maintenance
if (root.GetProperty("maintenance").ValueKind != JsonValueKind.Null)
{
    var maintenance = root.GetProperty("maintenance");
    var title = maintenance.GetProperty("title").GetString();
    var start = DateTimeOffset.FromUnixTimeSeconds(maintenance.GetProperty("start").GetInt64());
    var end   = DateTimeOffset.FromUnixTimeSeconds(maintenance.GetProperty("end").GetInt64());
    Console.WriteLine($"Maintenance: {title}");
    Console.WriteLine($"{start} – {end}");
    Console.WriteLine($"EU link: {RegionUrl(maintenance, "eu")}");
}

// List events
foreach (var eventItem in root.GetProperty("events").EnumerateArray())
{
    var title   = eventItem.GetProperty("title").GetString();
    var endTs   = eventItem.GetProperty("end").GetInt64();
    var endDate = DateTimeOffset.FromUnixTimeSeconds(endTs);
    Console.WriteLine($"{title} – ends {endDate:MMMM dd, yyyy}");
    Console.WriteLine($"EU link: {RegionUrl(eventItem, "eu")}");
}
```

## 🛠️ How It Works

1. **GitHub Actions** runs `parse_news.py` every 6 hours
2. Script fetches from lodestonenews.com Topics and Maintenance APIs **for all 5 regions**
3. Articles are matched across regions using content-aware keys — no article IDs or blind hostname substitution:
   - *Maintenance*: matched by `(start_ts, end_ts)` plus maintenance classification — the window is global, but other maintenance articles (Companion App, Mog Station, …) can share it
   - *Events/Topics*: matched by publication timestamp within a ±24 h window
4. For seasonal events:
   - Detects events by keywords (Valentione's, Heavensturn, etc.)
   - Follows "Read on" redirect links (`sqex.to` → actual event page)
   - Scrapes event dates from Lodestone special pages
   - Filters out expired events
5. Commits `LatestNews.json` to repository
6. Available immediately via GitHub raw URL

## 📅 Supported Events

- Valentione's Day
- Heavensturn
- Little Ladies' Day
- Hatching-tide
- Make It Rain Campaign
- Moonfire Faire
- The Rising
- All Saints' Wake
- Starlight Celebration
- Moogle Treasure Trove
- Irregular Tomestones campaigns

## 🌐 Regional URL Notes

Square Enix publishes each news/maintenance article to all Lodestone regions, but with
**different article IDs** per region.  The generator therefore cannot match by URL path.
Instead it uses content-aware keys fetched independently from each region's feed:

- **Maintenance** — matched by `(start_ts, end_ts)`.  Global maintenances share the
  exact same window across all regions, making this a precise identifier.
- **Events/Topics** — matched by publication timestamp within ±24 hours.  Seasonal
  events are infrequent enough that no two distinct events are ever published within
  that window simultaneously.

If a region's feed is temporarily unavailable or does not carry a particular article,
the corresponding `urls` value will be `null` rather than a fabricated URL.

## 🤝 Credits

- **Data Source**: [Lodestone News](https://lodestonenews.com) by [@MattAntonelli](https://github.com/mattantonelli)
- **Built For**: 
  - [XIVToDo](https://xivtodo.com) - FFXIV task tracker
  - [Time Memoria v2](https://github.com/LegendsOfTheGame/TimeMemoriaV2) - FFXIV Dalamud plugin

## 📜 License

This project is open source. Data is aggregated from official Square Enix Lodestone announcements.

## 🐛 Issues & Contributions

Found a bug or want to add support for more event types? Open an issue or PR!
