"""Orchestration: URL -> scrape -> extract -> keywords -> check -> PDF."""

import asyncio
import re
from pathlib import Path

from .scraper import scrape_site, ScrapedSite
from .analyzer import extract_business_info, check_keyword_presence
from .keywords import get_keywords
from .report import generate_report_pdf


async def generate_keyword_report(
    url: str,
    output_path: Path | None = None,
    on_progress: callable = None,
) -> Path:
    """
    Generate a keyword opportunity PDF for a given URL.

    Steps:
        1. Scrape site (5 pages max)
        2. Extract business info via Haiku
        3. Get 10 keywords from DataForSEO
        4. Check each keyword against scraped content
        5. Generate PDF

    Args:
        url: Website URL to analyze
        output_path: Where to save the PDF (default: keyword_report_{slug}.pdf)
        on_progress: Optional callback(step: str) for progress updates

    Returns:
        Path to the generated PDF
    """
    def _progress(msg: str):
        if on_progress:
            on_progress(msg)

    # Step 1: Scrape
    _progress("Scraping website...")
    site = await scrape_site(url, max_pages=5)

    if not site.pages:
        raise RuntimeError(f"Could not scrape any pages from {url}")

    # Step 2: Extract business info
    _progress("Analyzing business...")
    business_info = extract_business_info(site.pages)

    business_name = business_info["business_name"]
    industry = business_info["industry"]
    location = business_info["location"]

    # Step 3: Get keywords from DataForSEO
    _progress("Fetching keywords...")
    keyword_data = await get_keywords(industry, location)

    if not keyword_data:
        raise RuntimeError(
            f"No keywords returned from DataForSEO for industry={industry}, location={location}"
        )

    # Step 4: Check keyword presence on old site
    _progress("Checking keyword presence...")
    keyword_results = check_keyword_presence(keyword_data, site.pages)

    # Step 5: Generate PDF
    _progress("Generating PDF...")
    if output_path is None:
        slug = re.sub(r"[^a-z0-9]+", "_", business_name.lower()).strip("_")
        output_path = Path(f"keyword_report_{slug}.pdf")

    pdf_path = generate_report_pdf(
        business_name=business_name,
        industry=industry,
        keywords=keyword_results,
        output_path=output_path,
    )

    return pdf_path


def generate_keyword_report_sync(
    url: str,
    output_path: Path | None = None,
    on_progress: callable = None,
) -> Path:
    """Synchronous wrapper for generate_keyword_report."""
    return asyncio.run(generate_keyword_report(url, output_path, on_progress))
