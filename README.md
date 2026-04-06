# Warcry Scraper

Scrapy project to crawl the entire Warcrier.net website and export all Warcry rules, lists, and battle information in searchable and ChatGPT-friendly formats.

## Quick Start

### 1. Set up the environment

If you encounter an error activating the virtual environment due to PowerShell execution policy, you may need to adjust it first. Run the following command in PowerShell (you might need to run as Administrator):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then proceed with creating and activating the environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Crawl the full website

```powershell
cd C:\Users\walte\Documents\Warcry\Scraper\Warcry_Scraper
.\.venv\Scripts\python.exe -m scrapy crawl warcrier_full -o warcry_scrapy_full.json
```

This crawls all `/docs/*` pages on warcrier.net and saves raw output to `warcry_scrapy_full.json` (~2.1 MB).

### 3. Generate the LLM Markdown export

```powershell
.\.venv\Scripts\python.exe scripts/export.py
```

This reads `warcry_scrapy_full.json` and writes a ChatGPT-ready file with enhanced formatting:
- **`warcry_chat_ready.txt`** — Markdown format grouped by page, with classified types and structured fighter stats

### 4. Search the database (optional)

Find specific content before sharing with ChatGPT:

```powershell
.\.venv\Scripts\python.exe scripts/search.py "warband" --max-results 20
```

Output formats:
- Markdown: `--chat-ready output.md`

## Output Files

| File | Size | Records | Description |
|------|------|---------|-----|
| `warcry_chat_ready.txt` | 2.4 MB | 3,828 | Markdown format grouped by page, with types and structured fighter stats |

**After running `export.py`:**
- Fighter profiles have structured `fighter_stats` with Move/Toughness/Wounds/Weapons/Points/Faction
- All records classified by type: `fighter_profile`, `rule`, `battleplan`, `ability`, `misc`
- Cleaned data: "Fighters" summary rows removed (129), misclassified records reclassified
- Abilities extracted: [Double]/[Triple]/[Quad]/[Reaction] actions parsed for ability records
- Every record has `searchable_text` for better ChatGPT context and filtering
- Final count: 3,828 records (down from 3,847 raw)

## Use Cases

### Create faction lists
```powershell
.\.venv\Scripts\python.exe scripts/search.py "stormcast" --chat-ready faction_summary.md
# Copy `faction_summary.md` into ChatGPT
```

### Find battle strategies
```powershell
.\.venv\Scripts\python.exe scripts/search.py "deployment" --max-results 100
```

### Extract specific rules
```powershell
.\.venv\Scripts\python.exe scripts/search.py "re-roll" -o reroll_rules.json
```

## Project Structure

```
warcry_scraper/
  spiders/
    warcry_spider.py      # Main crawler (WarcrierSpider)
  settings.py
  pipelines.py
  middleware.py
scripts/
  export.py              # Classify, parse, clean JSON records and export to MD/TXT formats
  search.py              # Search and filter the enhanced data
requirements.txt
README.md
```

## Updating Data

To pull fresh data from warcrier.net:

```powershell
# Delete old crawl
Remove-Item warcry_scrapy_full.json

# Recrawl
.\.venv\Scripts\python.exe -m scrapy crawl warcrier_full -o warcry_scrapy_full.json

# Re-export to Markdown for ChatGPT
.\.venv\Scripts\python.exe scripts/export.py
```

Done! `warcry_chat_ready.md` and `warcry_chat_ready.txt` are now ready with enhanced formatting and structured fighter stats.

