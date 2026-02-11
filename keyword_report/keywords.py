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

# Industry-specific keyword templates (copied from main codebase)
INDUSTRY_KEYWORDS = {
    "plumbing": [
        "plumber", "plumbing", "drain cleaning", "water heater",
        "leak repair", "pipe repair", "sewer", "toilet repair",
        "faucet repair", "garbage disposal", "emergency plumber",
    ],
    "hvac": [
        "hvac", "air conditioning", "ac repair", "heating",
        "furnace repair", "ac installation", "heat pump",
        "duct cleaning", "thermostat", "emergency hvac",
    ],
    "roofing": [
        "roofing", "roof repair", "roof replacement", "roofer",
        "roof inspection", "shingle repair", "roof leak",
        "metal roofing", "flat roof", "emergency roof repair",
    ],
    "electrical": [
        "electrician", "electrical", "electrical repair",
        "outlet installation", "circuit breaker", "wiring",
        "lighting installation", "panel upgrade", "emergency electrician",
    ],
    "painting": [
        "painter", "painting", "house painting", "interior painting",
        "exterior painting", "commercial painting", "cabinet painting",
        "deck staining", "pressure washing",
    ],
    "landscaping": [
        "landscaping", "landscaper", "lawn care", "lawn service",
        "tree service", "tree trimming", "landscape design",
        "irrigation", "sod installation", "mulching",
    ],
    "cleaning": [
        "cleaning service", "house cleaning", "maid service",
        "deep cleaning", "move out cleaning", "office cleaning",
        "commercial cleaning", "carpet cleaning", "window cleaning",
    ],
    "pest_control": [
        "pest control", "exterminator", "termite", "bed bugs",
        "rodent control", "ant control", "mosquito control",
        "wildlife removal", "bee removal",
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

    # Base keywords: industry + location variations
    keywords.extend([
        f"{industry_lower} {location}",
        f"{industry_lower} near me",
        f"{industry_lower}",
        f"best {industry_lower} {location}",
        f"{industry_lower} services {location}",
        f"local {industry_lower} {location}",
        f"{industry_lower} company {location}",
        f"{industry_lower} business {location}",
    ])

    # Add industry-specific terms
    industry_key = industry_lower.replace(" ", "_")
    if industry_key in INDUSTRY_KEYWORDS:
        for term in INDUSTRY_KEYWORDS[industry_key][:8]:
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

    endpoint = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"
    payload = [
        {
            "keywords": seed_keywords[:20],
            "location_name": country,
            "language_name": "English",
            "sort_by": "search_volume",
            "limit": 10,
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

    return _parse_response(data)


def _parse_response(response: dict[str, Any]) -> list[KeywordData]:
    """Parse DataForSEO response into KeywordData list."""
    keywords: list[KeywordData] = []

    for task in response.get("tasks", []):
        for item in task.get("result", []) or []:
            keyword = item.get("keyword", "")
            search_volume = item.get("search_volume", 0)
            if keyword and search_volume and search_volume > 0:
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
