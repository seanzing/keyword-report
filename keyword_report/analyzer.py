"""Business extraction via Haiku and keyword presence matching."""

import json
import os
import re

import anthropic
from dotenv import load_dotenv

from .scraper import ScrapedPage
from .keywords import KeywordData

load_dotenv()

HAIKU_MODEL = "claude-3-5-haiku-20241022"


def extract_business_info(pages: list[ScrapedPage]) -> dict:
    """
    Extract business name, industry, location, services, and service area
    from scraped pages using Haiku.

    Sends content from ALL pages (not just homepage) so we catch service area
    info that's often on about/contact/locations pages.

    Returns:
        {
            "business_name": str,
            "industry": str,
            "location": str,
            "services": list[str],
            "service_area_cities": list[str],
        }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    if not pages:
        raise ValueError("No pages scraped — cannot extract business info.")

    # Build content from ALL pages, not just homepage
    content_parts = []
    for i, page in enumerate(pages[:5]):
        label = "HOMEPAGE" if i == 0 else f"PAGE {i + 1} ({page.url})"
        parts = [f"\n--- {label} ---"]
        if page.title:
            parts.append(f"Title: {page.title}")
        if page.h1:
            parts.append(f"H1: {page.h1}")
        if page.meta_description:
            parts.append(f"Meta Description: {page.meta_description}")
        if page.text_content:
            parts.append(f"Content:\n{page.text_content[:1500]}")
        content_parts.append("\n".join(parts))

    page_content = "\n".join(content_parts)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=512,
        system=(
            "You are analyzing a LOCAL SERVICE BUSINESS website. These are businesses "
            "like plumbers, painters, roofers, electricians, etc. that serve customers "
            "in a specific geographic area.\n\n"
            "Extract the following. Respond with JSON only, no other text.\n\n"
            "Format:\n"
            "{\n"
            '  "business_name": "...",\n'
            '  "industry": "...",\n'
            '  "location": "City, ST",\n'
            '  "services": ["service1", "service2", ...],\n'
            '  "service_area_cities": ["City1", "City2", ...]\n'
            "}\n\n"
            "INDUSTRY must be one of: plumbing, hvac, roofing, electrical, painting, "
            "landscaping, cleaning, pest_control. If none fit, use a short descriptor.\n"
            "IMPORTANT: These are SERVICE businesses. Painting = house painting, NOT art.\n\n"
            "SERVICES: List 3-5 specific services (e.g., interior painting, deck staining).\n\n"
            "LOCATION: Primary city in City, ST format (e.g., Castle Rock, CO).\n\n"
            "SERVICE_AREA_CITIES: List ALL cities/towns mentioned on the site that this "
            "business serves. Look for 'Areas We Serve', 'Service Areas', city names in "
            "page URLs, location pages, etc. Include nearby major cities and suburbs. "
            "If the site doesn't list specific cities, infer 5-8 nearby cities/suburbs "
            "based on the primary location. These should be real cities within reasonable "
            "driving distance. Return at least 5 cities."
        ),
        messages=[{"role": "user", "content": page_content}],
    )

    text = response.content[0].text.strip()

    # Extract JSON — handle nested arrays/objects
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        text = json_match.group()

    result = json.loads(text)

    return {
        "business_name": result.get("business_name", "Unknown Business"),
        "industry": result.get("industry", "service"),
        "location": result.get("location", "Unknown"),
        "services": result.get("services", []),
        "service_area_cities": result.get("service_area_cities", []),
    }


def check_keyword_presence(
    keywords: list[KeywordData],
    pages: list[ScrapedPage],
) -> list[dict]:
    """
    DEPRECATED: Use keywords.check_ranking_for_keywords() instead.

    This function checks for keyword text presence on scraped pages, which
    doesn't reflect actual Google rankings. A keyword can appear on a page
    without the site ranking for it, or the site can rank for keywords not
    literally on the page.

    Kept for backward compatibility only.

    Returns:
        [{"keyword": str, "monthly_searches": int, "on_old_site": bool}, ...]
    """
    parts: list[str] = []
    for page in pages:
        if page.title:
            parts.append(page.title)
        if page.meta_description:
            parts.append(page.meta_description)
        if page.h1:
            parts.append(page.h1)
        if page.text_content:
            parts.append(page.text_content)

    combined = " ".join(parts).lower()

    results = []
    for kw in keywords:
        results.append({
            "keyword": kw.keyword,
            "monthly_searches": kw.monthly_searches,
            "on_old_site": kw.keyword.lower() in combined,
        })

    return results
