# FFXIV Latest News API

**Automated FFXIV Lodestone maintenance tracking** - A simple, public JSON API that provides the latest server maintenance information for Final Fantasy XIV.

## 🎯 What This Does

This service automatically fetches maintenance information from [Lodestone News](https://lodestonenews.com) every 6 hours and provides it in a clean, easy-to-consume JSON format.

**Perfect for:**
- FFXIV plugins and tools
- Discord bots
- Community websites
- Personal projects

## 📡 API Endpoint

```
https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json
```

## 📋 JSON Format

```json
{
  "version": "1.0.0",
  "lastUpdated": 1738783200,
  "source": "lodestonenews.com",
  "maintenance": {
    "title": "All Worlds Maintenance (Feb. 5)",
    "start": 1738749600,
    "end": 1738767600,
    "url": "https://na.finalfantasyxiv.com/lodestone/news/detail/..."
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | API format version (for breaking changes) |
| `lastUpdated` | number | UNIX timestamp when data was last updated |
| `source` | string | Data source attribution |
| `maintenance` | object\|null | Next scheduled maintenance, or `null` if none |
| `maintenance.title` | string | Maintenance title from Lodestone |
| `maintenance.start` | number | UNIX timestamp (UTC) when maintenance starts |
| `maintenance.end` | number | UNIX timestamp (UTC) when maintenance ends |
| `maintenance.url` | string | Link to official Lodestone announcement |

## 🚀 Usage Examples

### JavaScript / TypeScript

```javascript
fetch('https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json')
  .then(response => response.json())
  .then(data => {
    if (data.maintenance) {
      const startDate = new Date(data.maintenance.start * 1000);
      console.log(`Maintenance: ${data.maintenance.title}`);
      console.log(`Starts: ${startDate.toLocaleString()}`);
    } else {
      console.log('No scheduled maintenance');
    }
  });
```

### Python

```python
import requests
from datetime import datetime

response = requests.get('https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json')
data = response.json()

if data['maintenance']:
    start = datetime.fromtimestamp(data['maintenance']['start'])
    print(f"Maintenance: {data['maintenance']['title']}")
    print(f"Starts: {start.strftime('%Y-%m-%d %I:%M %p')}")
else:
    print('No scheduled maintenance')
```

### C# (.NET)

```csharp
using System.Net.Http;
using System.Text.Json;

var client = new HttpClient();
var response = await client.GetStringAsync("https://raw.githubusercontent.com/LegendsOfTheGame/ffxiv-latest-news/main/LatestNews.json");
var data = JsonSerializer.Deserialize<JsonElement>(response);

if (data.GetProperty("maintenance").ValueKind != JsonValueKind.Null)
{
    var maintenance = data.GetProperty("maintenance");
    var title = maintenance.GetProperty("title").GetString();
    var start = DateTimeOffset.FromUnixTimeSeconds(maintenance.GetProperty("start").GetInt64());
    
    Console.WriteLine($"Maintenance: {title}");
    Console.WriteLine($"Starts: {start.ToLocalTime()}");
}
else
{
    Console.WriteLine("No scheduled maintenance");
}
```

## ⚙️ How It Works

1. **GitHub Actions** runs `parse_maintenance.py` every 6 hours
2. Script fetches the [Lodestone News RSS feed](https://lodestonenews.com/feed/na.xml)
3. Parses for maintenance entries (category="Maintenance", title starts with "All Worlds Maintenance")
4. Extracts start/end times from the description
5. Commits updated `LatestNews.json` to this repository
6. GitHub serves the file via raw URL (CDN-backed)

## 🔄 Update Frequency

- **Automatic:** Every 6 hours via GitHub Actions cron schedule
- **Manual:** Can be triggered manually via GitHub Actions interface
- **Emergency:** For emergency maintenance, trigger manually or wait up to 6 hours

## 🤝 Contributing

Found a bug or have a feature request? [Open an issue](https://github.com/LegendsOfTheGame/ffxiv-latest-news/issues)!

## 📜 License

This project is open source and available for anyone to use. Data is sourced from [lodestonenews.com](https://lodestonenews.com) which aggregates official Square Enix Lodestone announcements.

## 🙏 Credits

- Data source: [Lodestone News](https://lodestonenews.com)
- Original Lodestone: [FINAL FANTASY XIV, The Lodestone](https://na.finalfantasyxiv.com/lodestone/)
- Inspiration: [XIVToDo](https://xivtodo.com) by [@bourgeoisor](https://github.com/bourgeoisor)

---

**Built for the FFXIV community** 💙
