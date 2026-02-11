"""Simplified DataForSEO client for keyword research.

Stripped-down version of src/design_brief/integrations/dataforseo.py:
- Same industry keyword templates and seed generation
- Same API call but hardcoded limit=10
- Same country detection
- No competition assessment, no benchmarks
"""

import asyncio
import base64
import os
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# Industry-specific keyword templates — all terms are SERVICE-oriented
# to prevent DataForSEO from returning irrelevant results (e.g., art for "painting")
INDUSTRY_KEYWORDS = {
    "plumbing": [
        "plumber near me", "plumbing services", "drain cleaning", "water heater repair",
        "leak repair", "pipe repair", "sewer repair", "toilet repair",
        "faucet repair", "garbage disposal repair", "emergency plumber",
    ],
    "hvac": [
        "hvac repair", "air conditioning repair", "ac repair near me", "heating repair",
        "furnace repair", "ac installation", "heat pump installation",
        "duct cleaning", "hvac company", "emergency hvac",
    ],
    "roofing": [
        "roofing contractor", "roof repair near me", "roof replacement", "roofer near me",
        "roof inspection", "shingle repair", "roof leak repair",
        "metal roofing contractor", "flat roof repair", "emergency roof repair",
    ],
    "electrical": [
        "electrician near me", "electrical repair", "electrical contractor",
        "outlet installation", "circuit breaker repair", "electrical wiring",
        "lighting installation", "panel upgrade", "emergency electrician",
    ],
    "painting": [
        "house painter near me", "painting contractor", "house painting",
        "interior painting services", "exterior painting services",
        "commercial painter", "cabinet painting", "deck staining",
        "residential painter", "painting company",
    ],
    "landscaping": [
        "landscaping company", "landscaper near me", "lawn care service",
        "lawn mowing service", "tree trimming service", "tree removal",
        "landscape design", "irrigation installation", "sod installation",
    ],
    "cleaning": [
        "house cleaning service", "cleaning service near me", "maid service",
        "deep cleaning service", "move out cleaning", "office cleaning service",
        "commercial cleaning", "carpet cleaning service", "window cleaning service",
    ],
    "pest_control": [
        "pest control near me", "exterminator near me", "termite treatment",
        "bed bug treatment", "rodent control", "ant exterminator",
        "mosquito control service", "wildlife removal", "pest control company",
    ],
}

DEFAULT_KEYWORDS = [
    "service", "repair", "installation", "maintenance",
    "professional", "licensed", "near me",
]


@dataclass
class KeywordData:
    keyword: str
    monthly_searches: int


def generate_seed_keywords(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[str]:
    """
    Generate seed keywords by combining industry terms with location.

    Returns up to 20 seed keywords.
    """
    keywords = []
    industry_lower = industry.lower()

    # Base keywords: always service-oriented to avoid ambiguity
    keywords.extend([
        f"{industry_lower} services {location}",
        f"{industry_lower} contractor {location}",
        f"{industry_lower} company {location}",
        f"best {industry_lower} {location}",
        f"local {industry_lower} {location}",
        f"{industry_lower} near me",
    ])

    # Add industry-specific terms (already service-oriented)
    industry_key = industry_lower.replace(" ", "_")
    if industry_key in INDUSTRY_KEYWORDS:
        for term in INDUSTRY_KEYWORDS[industry_key][:10]:
            keywords.append(f"{term} {location}")

    # Add specific services if provided
    if services:
        for service in services[:5]:
            keywords.append(f"{service} {location}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique.append(kw)

    return unique[:20]


def _detect_country(location: str) -> str:
    """Detect the country from a location string for DataForSEO API."""
    location_lower = location.lower()

    country_mappings = {
        "australia": "Australia",
        "sydney": "Australia",
        "melbourne": "Australia",
        "brisbane": "Australia",
        "perth": "Australia",
        "adelaide": "Australia",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "london": "United Kingdom",
        "england": "United Kingdom",
        "canada": "Canada",
        "toronto": "Canada",
        "vancouver": "Canada",
        "new zealand": "New Zealand",
        "auckland": "New Zealand",
    }

    for keyword, country in country_mappings.items():
        if keyword in location_lower:
            return country

    return "United States"


async def get_keywords(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[KeywordData]:
    """
    Generate seed keywords and fetch top 10 from DataForSEO.

    Returns list of KeywordData sorted by monthly_searches descending.
    Filters results to only include service-relevant keywords.
    """
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise ValueError(
            "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
        )

    seed_keywords = generate_seed_keywords(industry, location, services)
    country = _detect_country(location)

    # Build auth header
    credentials = f"{login}:{password}"
    auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"

    # Request more than 10 so we can filter and still have enough
    endpoint = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"
    payload = [
        {
            "keywords": seed_keywords[:20],
            "location_name": country,
            "language_name": "English",
            "sort_by": "search_volume",
            "limit": 50,
        }
    ]
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    # Build relevance terms for filtering
    relevance_terms = _build_relevance_terms(industry, services)
    return _parse_response(data, relevance_terms)


def _build_relevance_terms(industry: str, services: list[str] | None = None) -> set[str]:
    """Build a set of terms that a keyword must contain at least one of to be relevant."""
    industry_key = industry.lower().replace(" ", "_")

    # Start with general service-intent terms
    terms = {
        "service", "services", "contractor", "company", "repair",
        "install", "installation", "removal", "cleaning", "maintenance",
        "near me", "cost", "price", "quote", "estimate", "emergency",
        "residential", "commercial", "licensed", "professional", "local",
    }

    # Add industry-specific relevance terms
    if industry_key in INDUSTRY_KEYWORDS:
        for template_term in INDUSTRY_KEYWORDS[industry_key]:
            # Extract the core words from each template
            for word in template_term.lower().split():
                if word not in {"near", "me", "in", "the", "a", "and", "or", "for"}:
                    terms.add(word)

    # Add extracted services
    if services:
        for svc in services:
            for word in svc.lower().split():
                if len(word) > 2:
                    terms.add(word)

    return terms


def _is_relevant_keyword(keyword: str, relevance_terms: set[str]) -> bool:
    """Check if a keyword is relevant to the service industry."""
    kw_lower = keyword.lower()
    return any(term in kw_lower for term in relevance_terms)


def _parse_response(
    response: dict[str, Any],
    relevance_terms: set[str] | None = None,
) -> list[KeywordData]:
    """Parse DataForSEO response into KeywordData list, filtering for relevance."""
    keywords: list[KeywordData] = []

    for task in response.get("tasks", []):
        for item in task.get("result", []) or []:
            keyword = item.get("keyword", "")
            search_volume = item.get("search_volume", 0)
            if not keyword or not search_volume or search_volume <= 0:
                continue

            # Filter out irrelevant keywords
            if relevance_terms and not _is_relevant_keyword(keyword, relevance_terms):
                continue

            keywords.append(KeywordData(keyword=keyword, monthly_searches=search_volume))

    keywords.sort(key=lambda k: k.monthly_searches, reverse=True)
    return keywords[:10]


def get_keywords_sync(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[KeywordData]:
    """Synchronous wrapper for get_keywords."""
    return asyncio.run(get_keywords(industry, location, services))
