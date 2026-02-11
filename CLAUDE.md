# CLAUDE.md — Keyword Report Tool

## What This Is

Standalone, salesperson-facing tool that generates a keyword opportunity PDF for potential leads. Pre-sale lead gen — cheap, fast, deployed independently from the main design brief system.

**Flow**: URL → scrape site (5 pages) → Haiku extracts business info + service area → DataForSEO returns 10 keywords → check old site for keyword presence → generate PDF

**Cost**: ~$0.01-0.02 per report (one Haiku call + one DataForSEO call)

## Architecture

```
keyword_report/
├── cli.py          # CLI entry point: keyword-report --url <url>
├── web.py          # FastAPI web app with SSE progress (deployed on Railway)
├── main.py         # Orchestration: generate_keyword_report()
├── scraper.py      # Playwright Firefox scraper (5 pages max, simplified)
├── analyzer.py     # Haiku business extraction + keyword presence checking
├── keywords.py     # DataForSEO client + keyword strategy
└── report.py       # HTML template → WeasyPrint PDF generation
```

## Deployment

- **Hosted on Railway** — auto-deploys from GitHub on push to main
- **Dockerfile** — Python 3.12-slim + Playwright Firefox + WeasyPrint deps
- **Repo**: github.com/seanzing/keyword-report

## Environment Variables (set in Railway dashboard)

- `ANTHROPIC_API_KEY` — for Haiku business extraction
- `DATAFORSEO_LOGIN` — DataForSEO API login (email)
- `DATAFORSEO_PASSWORD` — DataForSEO API password

## How the Keyword Strategy Works

This is the most-iterated part. The goal is to produce a report matching `IdealReport.jpeg` in the parent design-brief-system repo — 10 diverse keywords across different cities and service types with compelling search volumes.

### Pipeline:

1. **Haiku extraction** (`analyzer.py`): Reads ALL scraped pages, extracts business_name, industry, location, services, and **service_area_cities** (the key ingredient). If the site doesn't list service areas, Haiku infers 5-8 nearby cities.

2. **Seed generation** (`keywords.py`): Seeds are spread across service area cities in round-robin. "painter Denver", "house painter Littleton", "interior painting Parker" — NOT "painter Castle Rock" x20.

3. **DataForSEO call**: Requests 200 results with state-level targeting (e.g., "Colorado,United States").

4. **Filtering & ranking** (`_parse_and_rank`):
   - Brand blocklist (Benjamin Moore, Sherwin Williams, Home Depot, etc.)
   - Service relevance filter (must contain industry-related terms)
   - Must contain a known city name (no generic "near me" keywords)
   - Semantic dedup (word-order variants collapsed: "castle rock house painting" = "house painting castle rock")
   - City diversity cap (max 3 per city)
   - Top 10 by volume

### Known Issues & Past Fixes:

- **"Mona Lisa" problem**: Generic seeds like "painting Denver" return art keywords. Fixed by making all industry templates service-oriented ("house painter", "painting contractor").
- **"near me" domination**: Generic national keywords drown out local results. Fixed by removing all "near me" from seeds — every seed includes a city name.
- **Repetitive keywords**: Word-order variants ("house painter castle rock" / "castle rock house painter") counted as different. Fixed with semantic intent normalization.
- **Low volumes**: Single small city keywords = tiny volumes. Fixed by spreading across metro service area.

## PDF Design

Matches `IdealReport.jpeg` — white card on gray background, teal pill badges for monthly impressions, check/X circles for old/new site, dark navy banner with business-specific message, ZING footer.

## Relationship to Design Brief System

Standalone package — no imports from `src/design_brief/`. Scraper and DataForSEO logic were copied and simplified from the main codebase. If the main system's scraper or DataForSEO client changes significantly, this tool's versions may need updating too.

## Common Tasks

### Test locally
```bash
pip install -e .
keyword-report --url https://some-plumber-site.com
```

### Run web app locally
```bash
uvicorn keyword_report.web:app --reload --port 8080
```

### Deploy
```bash
git push origin main  # Railway auto-deploys
```
