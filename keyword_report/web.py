"""FastAPI web app for keyword report generation."""

import asyncio
import hmac
import logging
import os
import re
import uuid
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

logger = logging.getLogger("keyword_report.web")

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

REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "/app/reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

API_TOKEN = os.getenv("KEYWORD_REPORT_API_TOKEN", "").strip()
DATA_ENDPOINT_TIMEOUT = float(os.getenv("KEYWORD_REPORT_DATA_TIMEOUT", "180"))


def require_api_token(authorization: str | None = Header(default=None)) -> None:
    """Constant-time bearer token check. Returns 503 if server has no token configured."""
    if not API_TOKEN:
        logger.error("KEYWORD_REPORT_API_TOKEN is not set; refusing request to protected endpoint")
        raise HTTPException(status_code=503, detail="Server not configured for API access.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    presented = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(presented, API_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid bearer token.")


def _validate_url(url: str) -> str:
    """Reject obviously bad / SSRF-prone URLs. Returns the normalized URL."""
    if not url or len(url) > 2048:
        raise HTTPException(status_code=400, detail="URL is required and must be < 2048 chars.")
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must use http or https.")
    host = (parsed.hostname or "").lower()
    if not host or "." not in host:
        raise HTTPException(status_code=400, detail="URL must include a valid hostname.")
    # Block local / internal targets to mitigate SSRF.
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "metadata.google.internal"}
    if host in blocked_hosts or host.endswith(".local") or host.endswith(".internal"):
        raise HTTPException(status_code=400, detail="URL host is not allowed.")
    if host.startswith("169.254.") or host.startswith("10.") or host.startswith("192.168."):
        raise HTTPException(status_code=400, detail="URL host is not allowed.")
    return parsed.geturl()


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
            profile = await asyncio.to_thread(
                extract_business_info, site.pages
            )

            yield _sse(
                "progress",
                f"Found: {profile.business_name} ({profile.industry} — {profile.business_model})",
            )
            yield _sse(
                "progress",
                f"Location: {profile.location or '(none)'} | Cities: {len(profile.service_area_cities)} | Seeds: {len(profile.seed_keywords)} | Relevance terms: {len(profile.relevance_terms)}",
            )

            yield _sse("progress", "Fetching keywords and ranking data...")
            domain = _extract_domain(url)
            all_cities = build_city_list(profile)

            keyword_data, ranked_keywords = await asyncio.gather(
                get_keywords(profile),
                get_ranked_keywords(domain, profile.location),
            )

            if not keyword_data:
                yield _sse(
                    "error",
                    f"No keyword data returned. Seeds: {len(profile.seed_keywords)}, "
                    f"Location: {profile.location}, Cities: {len(all_cities)}",
                )
                return

            yield _sse(
                "progress",
                f"Got {len(keyword_data)} keywords. Cross-referencing against {len(ranked_keywords)} ranked keywords...",
            )
            keyword_results = check_ranking_for_keywords(
                keyword_data, ranked_keywords, all_cities
            )

            yield _sse("progress", "Generating PDF...")
            slug = re.sub(r"[^a-z0-9]+", "", profile.business_name.lower())
            filename = f"{slug}_keyword_report.pdf"
            output_path = REPORTS_DIR / filename

            await asyncio.to_thread(
                generate_report_pdf,
                profile,
                keyword_results,
                output_path,
            )

            total = sum(kw["monthly_searches"] for kw in keyword_results)
            old_count = sum(1 for kw in keyword_results if kw["on_old_site"])

            yield _sse(
                "complete",
                f'{{"filename":"{filename}","business_name":"{profile.business_name}",'
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


@app.get("/api/data", dependencies=[Depends(require_api_token)])
async def generate_data(url: str):
    """Run the keyword research pipeline and return raw JSON (no PDF).

    Requires `Authorization: Bearer <KEYWORD_REPORT_API_TOKEN>` header.
    """
    request_id = uuid.uuid4().hex[:12]
    safe_url = _validate_url(url)

    async def _pipeline() -> dict:
        site = await scrape_site(safe_url, max_pages=5)
        if not site.pages:
            raise HTTPException(status_code=422, detail="Could not scrape any pages from this URL.")

        profile = await asyncio.to_thread(extract_business_info, site.pages)
        domain = _extract_domain(safe_url)
        all_cities = build_city_list(profile)

        keyword_data, ranked_keywords = await asyncio.gather(
            get_keywords(profile),
            get_ranked_keywords(domain, profile.location),
        )

        if not keyword_data:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"No keyword data returned. Seeds: {len(profile.seed_keywords)}, "
                    f"Location: {profile.location}, Cities: {len(all_cities)}"
                ),
            )

        keyword_results = check_ranking_for_keywords(
            keyword_data, ranked_keywords, all_cities
        )
        total = sum(kw["monthly_searches"] for kw in keyword_results)
        old_count = sum(1 for kw in keyword_results if kw["on_old_site"])

        return {
            "request_id": request_id,
            "url": safe_url,
            "domain": domain,
            "profile": asdict(profile),
            "keywords": keyword_results,
            "totals": {
                "total_impressions": total,
                "old_site_keywords": old_count,
                "new_site_keywords": len(keyword_results),
                "ranked_keywords_checked": len(ranked_keywords),
            },
        }

    try:
        payload = await asyncio.wait_for(_pipeline(), timeout=DATA_ENDPOINT_TIMEOUT)
        return JSONResponse({"ok": True, **payload})
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("[%s] /api/data timed out for url=%s", request_id, safe_url)
        raise HTTPException(
            status_code=504,
            detail=f"Pipeline exceeded {DATA_ENDPOINT_TIMEOUT:.0f}s (request_id={request_id}).",
        )
    except Exception as e:
        logger.exception("[%s] /api/data failed for url=%s", request_id, safe_url)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error (request_id={request_id}): {type(e).__name__}",
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

  .share-input-row {
    display: flex;
    gap: 8px;
    margin-top: 6px;
  }

  .share-url-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 8px;
    background: rgba(255,255,255,0.1);
    color: white;
    font-size: 13px;
  }

  .copy-btn {
    padding: 8px 16px;
    background: rgba(255,255,255,0.15);
    color: white;
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }

  .copy-btn:hover { background: rgba(255,255,255,0.25); }

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
      <div class="share-row" id="share-row" style="display:none;">
        <label style="color:rgba(255,255,255,0.6);font-size:12px;margin-top:16px;display:block;">Shareable Link</label>
        <div class="share-input-row">
          <input type="text" id="share-url" readonly class="share-url-input">
          <button type="button" id="copy-btn" class="copy-btn">Copy</button>
        </div>
      </div>
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
    const reportPath = '/reports/' + data.filename;
    document.getElementById('download-link').href = reportPath;

    const shareUrl = window.location.origin + reportPath;
    document.getElementById('share-url').value = shareUrl;
    document.getElementById('share-row').style.display = 'block';

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

document.getElementById('copy-btn').addEventListener('click', () => {
  const input = document.getElementById('share-url');
  navigator.clipboard.writeText(input.value).then(() => {
    const btn = document.getElementById('copy-btn');
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 2000);
  });
});
</script>
</body>
</html>
"""
