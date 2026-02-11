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


def extract_business_info(pages: list[ScrapedPage]) -> dict[str, str]:
    """
    Extract business name, industry, and location from scraped pages using Haiku.

    Sends homepage content (title + h1 + first 2000 chars of text) to Haiku
    for minimal extraction.

    Returns:
        {"business_name": str, "industry": str, "location": str}
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set.")

    # Build homepage content from first page
    homepage = pages[0] if pages else None
    if not homepage:
        raise ValueError("No pages scraped — cannot extract business info.")

    content_parts = []
    if homepage.title:
        content_parts.append(f"Title: {homepage.title}")
    if homepage.h1:
        content_parts.append(f"H1: {homepage.h1}")
    if homepage.meta_description:
        content_parts.append(f"Meta Description: {homepage.meta_description}")
    if homepage.text_content:
        content_parts.append(f"Page Content:\n{homepage.text_content[:2000]}")

    page_content = "\n".join(content_parts)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=256,
        system=(
            "Extract the business name, industry, and primary city/state location "
            "from this website content. Respond with JSON only, no other text.\n\n"
            'Format: {"business_name": "...", "industry": "...", "location": "..."}\n\n'
            "For industry, use a single lowercase word like: plumbing, hvac, roofing, "
            "electrical, painting, landscaping, cleaning, pest_control. If it doesn't "
            "match a common trade, use your best short description.\n\n"
            "For location, use the format: City, ST (e.g., Denver, CO). If the business "
            "serves multiple areas, use the primary/headquarters city."
        ),
        messages=[{"role": "user", "content": page_content}],
    )

    # Parse response
    text = response.content[0].text.strip()

    # Try to extract JSON from response
    json_match = re.search(r"\{[^}]+\}", text)
    if json_match:
        text = json_match.group()

    result = json.loads(text)

    return {
        "business_name": result.get("business_name", "Unknown Business"),
        "industry": result.get("industry", "service"),
        "location": result.get("location", "Unknown"),
    }


def check_keyword_presence(
    keywords: list[KeywordData],
    pages: list[ScrapedPage],
) -> list[dict]:
    """
    Check whether each keyword appears on the scraped site.

    Combines all page text_content + title + meta_description + h1 into one
    lowercase string, then checks for case-insensitive exact phrase match.

    Returns:
        [{"keyword": str, "monthly_searches": int, "on_old_site": bool}, ...]
    """
    # Build combined site text
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
