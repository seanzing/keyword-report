"""FastAPI web app for keyword report generation."""

import asyncio
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from .scraper import scrape_site
from .analyzer import extract_business_info
from .keywords import (
    get_keywords,
    get_ranked_keywords,
    check_ranking_for_keywords,
    build_city_list,
    _extract_domain,
)
from .report import generate_report_pdf

load_dotenv()

app = FastAPI(title="Keyword Report Generator")

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


@app.get("/api/generate")
async def generate(url: str):
    """Generate a keyword report via Server-Sent Events."""

    async def event_stream():
        try:
            yield _sse("progress", "Scraping website...")
            site = await scrape_site(url, max_pages=5)

            if not site.pages:
                yield _sse("error", "Could not scrape any pages from this URL.")
                return

            yield _sse("progress", "Analyzing business...")
            business_info = await asyncio.to_thread(
                extract_business_info, site.pages
            )
            business_name = business_info["business_name"]
            industry = business_info["industry"]
            location = business_info["location"]
            services = business_info.get("services", [])
            service_area_cities = business_info.get("service_area_cities", [])

            yield _sse(
                "progress",
                f"Found: {business_name} ({industry} in {location})",
            )

            yield _sse("progress", "Fetching keywords and ranking data...")
            domain = _extract_domain(url)
            all_cities = build_city_list(location, service_area_cities)

            keyword_data, ranked_keywords = await asyncio.gather(
                get_keywords(industry, location, services, service_area_cities),
                get_ranked_keywords(domain, location),
            )

            if not keyword_data:
                yield _sse("error", "No keyword data returned. Check DataForSEO credentials.")
                return

            yield _sse(
                "progress",
                f"Got {len(keyword_data)} keywords. Cross-referencing against {len(ranked_keywords)} ranked keywords...",
            )
            keyword_results = check_ranking_for_keywords(
                keyword_data, ranked_keywords, all_cities
            )

            yield _sse("progress", "Generating PDF...")
            slug = re.sub(r"[^a-z0-9]+", "", business_name.lower())
            filename = f"{slug}_keyword_report.pdf"
            output_path = REPORTS_DIR / filename

            await asyncio.to_thread(
                generate_report_pdf,
                business_name,
                industry,
                keyword_results,
                output_path,
            )

            total = sum(kw["monthly_searches"] for kw in keyword_results)
            old_count = sum(1 for kw in keyword_results if kw["on_old_site"])

            yield _sse(
                "complete",
                f'{{"filename":"{filename}","business_name":"{business_name}",'
                f'"total_impressions":{total},"old_site_keywords":{old_count},'
                f'"new_site_keywords":{len(keyword_results)}}}',
            )

        except Exception as e:
            yield _sse("error", str(e))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/reports/{filename}")
async def download_report(filename: str):
    path = REPORTS_DIR / filename
    if not path.exists():
        return HTMLResponse("Report not found.", status_code=404)
    return FileResponse(path, filename=filename, media_type="application/pdf")


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


# ---------------------------------------------------------------------------
# Inline HTML — single page app
# ---------------------------------------------------------------------------

INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Keyword Report Generator</title>
<style>
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    background: #f0f2f5;
    color: #1a1a2e;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }

  .card {
    background: white;
    border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 8px 24px rgba(0,0,0,0.06);
    padding: 48px;
    width: 100%;
    max-width: 520px;
  }

  .logo {
    font-size: 14px;
    font-weight: 600;
    color: #8b95a5;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  h1 {
    font-size: 24px;
    font-weight: 700;
    margin-bottom: 6px;
  }

  .subtitle {
    font-size: 14px;
    color: #6b7280;
    margin-bottom: 32px;
  }

  label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #4a5568;
    margin-bottom: 6px;
  }

  .input-row {
    display: flex;
    gap: 10px;
  }

  input[type="text"] {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid #d1d5db;
    border-radius: 10px;
    font-size: 15px;
    outline: none;
    transition: border-color 0.15s;
  }

  input[type="text"]:focus {
    border-color: #4ecdc4;
    box-shadow: 0 0 0 3px rgba(78,205,196,0.15);
  }

  button {
    padding: 12px 24px;
    background: #1a1a2e;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
  }

  button:hover { background: #2a2a4e; }
  button:disabled { background: #9ca3af; cursor: not-allowed; }

  /* Progress area */
  #progress {
    margin-top: 28px;
    display: none;
  }

  .step {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    font-size: 14px;
    color: #6b7280;
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; } }

  .step .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ecdc4;
    flex-shrink: 0;
  }

  .step.active .dot {
    animation: pulse 1s ease infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  /* Result */
  #result {
    margin-top: 24px;
    display: none;
  }

  .result-card {
    background: linear-gradient(135deg, #1a1a2e, #2a2a4e);
    border-radius: 12px;
    padding: 28px;
    text-align: center;
    color: white;
  }

  .result-card h2 {
    font-size: 18px;
    margin-bottom: 8px;
  }

  .result-stats {
    font-size: 13px;
    color: rgba(255,255,255,0.7);
    margin-bottom: 18px;
  }

  .download-btn {
    display: inline-block;
    padding: 12px 32px;
    background: #4ecdc4;
    color: #1a1a2e;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 700;
    text-decoration: none;
    transition: background 0.15s;
  }

  .download-btn:hover { background: #3dbdb5; }

  /* Error */
  .error-msg {
    margin-top: 16px;
    padding: 12px 16px;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 10px;
    color: #991b1b;
    font-size: 14px;
    display: none;
  }

  .footer {
    margin-top: 24px;
    font-size: 12px;
    color: #9ca3af;
  }
</style>
</head>
<body>
<div class="card">
  <div class="logo">ZING Website Design</div>
  <h1>Keyword Report</h1>
  <p class="subtitle">Enter a website URL to generate a keyword opportunity report.</p>

  <form id="form">
    <label for="url">Website URL</label>
    <div class="input-row">
      <input type="text" id="url" name="url" placeholder="https://example.com" required>
      <button type="submit" id="btn">Generate</button>
    </div>
  </form>

  <div class="error-msg" id="error"></div>

  <div id="progress"></div>

  <div id="result">
    <div class="result-card">
      <h2 id="result-title"></h2>
      <div class="result-stats" id="result-stats"></div>
      <a class="download-btn" id="download-link" href="#">Download PDF</a>
    </div>
  </div>
</div>

<div class="footer">Prepared by ZING Website Design &middot; zing.work</div>

<script>
const form = document.getElementById('form');
const btn = document.getElementById('btn');
const urlInput = document.getElementById('url');
const progressEl = document.getElementById('progress');
const resultEl = document.getElementById('result');
const errorEl = document.getElementById('error');

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  // Reset UI
  progressEl.innerHTML = '';
  progressEl.style.display = 'block';
  resultEl.style.display = 'none';
  errorEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = 'Working...';

  const evtSource = new EventSource('/api/generate?url=' + encodeURIComponent(url));
  let lastStep = null;

  evtSource.addEventListener('progress', (e) => {
    // Deactivate previous step's pulse
    if (lastStep) lastStep.classList.remove('active');

    const step = document.createElement('div');
    step.className = 'step active';
    step.innerHTML = '<span class="dot"></span>' + e.data;
    progressEl.appendChild(step);
    lastStep = step;
  });

  evtSource.addEventListener('complete', (e) => {
    evtSource.close();
    if (lastStep) lastStep.classList.remove('active');

    const data = JSON.parse(e.data);

    document.getElementById('result-title').textContent = data.business_name;
    document.getElementById('result-stats').textContent =
      data.total_impressions.toLocaleString() + '/mo potential impressions \u00b7 ' +
      data.old_site_keywords + ' keywords on old site \u00b7 ' +
      data.new_site_keywords + ' on new site';
    document.getElementById('download-link').href = '/reports/' + data.filename;

    resultEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Generate';
  });

  evtSource.addEventListener('error', (e) => {
    evtSource.close();
    if (lastStep) lastStep.classList.remove('active');

    if (e.data) {
      errorEl.textContent = e.data;
    } else {
      errorEl.textContent = 'Connection lost. Please try again.';
    }
    errorEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = 'Generate';
  });
});
</script>
</body>
</html>
"""
