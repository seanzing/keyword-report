"""Orchestration: URL -> scrape -> extract -> keywords -> check -> PDF."""

import asyncio
import re
from pathlib import Path

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


async def generate_keyword_report(
    url: str,
    output_path: Path | None = None,
    on_progress: callable = None,
) -> Path:
    """
    Generate a keyword opportunity PDF for a given URL.

    Steps:
        1. Scrape site (5 pages max)
        2. Extract business info via Haiku -> BusinessProfile
        3. Get 10 keywords from DataForSEO
        4. Check each keyword against actual rankings
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

    # Step 2: Extract business info -> BusinessProfile
    _progress("Analyzing business...")
    profile = extract_business_info(site.pages)

    # Step 3: Fetch opportunity keywords + ranked keywords in parallel
    _progress("Fetching keywords and ranking data...")
    domain = _extract_domain(url)
    all_cities = build_city_list(profile)

    keyword_data, ranked_keywords = await asyncio.gather(
        get_keywords(profile),
        get_ranked_keywords(domain, profile.location),
    )

    if not keyword_data:
        raise RuntimeError(
            f"No keywords returned from DataForSEO for industry={profile.industry}, location={profile.location}"
        )

    # Step 4: Cross-reference opportunity keywords against actual rankings
    _progress(f"Cross-referencing against {len(ranked_keywords)} ranked keywords...")
    keyword_results = check_ranking_for_keywords(keyword_data, ranked_keywords, all_cities)

    # Step 5: Generate PDF
    _progress("Generating PDF...")
    if output_path is None:
        slug = re.sub(r"[^a-z0-9]+", "_", profile.business_name.lower()).strip("_")
        output_path = Path(f"keyword_report_{slug}.pdf")

    pdf_path = generate_report_pdf(
        profile=profile,
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
