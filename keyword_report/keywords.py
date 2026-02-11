"""DataForSEO client for keyword research — tuned for local service businesses.

All seeds are location-specific ({service} {city}), never generic "near me".
Results are filtered for service relevance and brand names are excluded.
Keywords containing the actual city name are prioritized.
"""

import asyncio
import base64
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

# Industry-specific seed terms — just the service, no "near me"
# Location gets appended to every one of these
INDUSTRY_SEEDS = {
    "plumbing": [
        "plumber", "plumbing services", "drain cleaning",
        "water heater repair", "leak repair", "emergency plumber",
        "pipe repair", "sewer repair", "toilet repair",
    ],
    "hvac": [
        "hvac repair", "air conditioning repair", "ac repair",
        "furnace repair", "heating repair", "ac installation",
        "hvac company", "heat pump installation", "duct cleaning",
    ],
    "roofing": [
        "roofing contractor", "roof repair", "roofer",
        "roof replacement", "roof inspection", "roof leak repair",
        "shingle repair", "metal roofing", "emergency roof repair",
    ],
    "electrical": [
        "electrician", "electrical contractor", "electrical repair",
        "outlet installation", "lighting installation",
        "panel upgrade", "emergency electrician", "wiring repair",
    ],
    "painting": [
        "painter", "house painter", "painting contractor",
        "interior painting", "exterior painting", "house painting",
        "residential painter", "commercial painter",
        "cabinet painting", "deck staining",
    ],
    "landscaping": [
        "landscaping company", "landscaper", "lawn care service",
        "tree trimming", "tree removal", "landscape design",
        "lawn mowing service", "irrigation installation",
    ],
    "cleaning": [
        "house cleaning service", "cleaning service", "maid service",
        "deep cleaning", "office cleaning", "commercial cleaning",
        "carpet cleaning", "move out cleaning",
    ],
    "pest_control": [
        "pest control", "exterminator", "termite treatment",
        "bed bug treatment", "rodent control", "ant exterminator",
        "mosquito control", "wildlife removal",
    ],
}

# Brand names that should never appear in results
BRAND_BLOCKLIST = [
    "benjamin moore", "sherwin williams", "sherwin-williams", "behr",
    "valspar", "ppg", "dulux", "farrow", "rust-oleum", "rustoleum",
    "home depot", "lowes", "lowe's", "menards", "ace hardware",
    "angi", "angie", "thumbtack", "yelp", "houzz", "nextdoor",
    "trane", "carrier", "lennox", "goodman", "rheem", "daikin",
    "kohler", "moen", "delta faucet",
    "scotts", "trugreen", "john deere",
    "orkin", "terminix", "rentokil",
]


@dataclass
class KeywordData:
    keyword: str
    monthly_searches: int


def _extract_city(location: str) -> str:
    """Extract just the city name from 'City, ST' or 'City, State' format."""
    return location.split(",")[0].strip()


def generate_seed_keywords(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[str]:
    """
    Generate seed keywords — every seed includes the city name.

    No generic "near me" terms. All seeds are "{service term} {city}".
    """
    city = _extract_city(location)
    keywords = []
    industry_lower = industry.lower()
    industry_key = industry_lower.replace(" ", "_")

    # Industry + city base patterns
    keywords.extend([
        f"{industry_lower} {city}",
        f"{industry_lower} services {city}",
        f"{industry_lower} contractor {city}",
        f"{industry_lower} company {city}",
        f"best {industry_lower} {city}",
    ])

    # Industry-specific seeds + city
    if industry_key in INDUSTRY_SEEDS:
        for term in INDUSTRY_SEEDS[industry_key]:
            keywords.append(f"{term} {city}")

    # Extracted services + city
    if services:
        for service in services[:5]:
            keywords.append(f"{service} {city}")

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        lower = kw.lower()
        if lower not in seen:
            seen.add(lower)
            unique.append(kw)

    return unique[:20]


def _detect_location(location: str) -> str:
    """
    Detect the best DataForSEO location_name for targeting.

    Uses state-level targeting for US locations (e.g., "Colorado,United States")
    to get more relevant local search volumes.
    """
    location_lower = location.lower()

    # International countries
    intl_mappings = {
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

    for keyword, country in intl_mappings.items():
        if keyword in location_lower:
            return country

    # US state abbreviation mapping for state-level targeting
    us_states = {
        "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
        "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
        "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
        "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
        "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
        "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
        "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
        "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
        "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
        "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
        "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
        "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
        "WI": "Wisconsin", "WY": "Wyoming",
    }

    # Try to match "City, ST" pattern
    match = re.search(r",\s*([A-Z]{2})\b", location)
    if match:
        abbrev = match.group(1)
        if abbrev in us_states:
            return f"{us_states[abbrev]},United States"

    return "United States"


def _is_blocked_brand(keyword: str) -> bool:
    """Check if keyword contains a brand name."""
    kw_lower = keyword.lower()
    return any(brand in kw_lower for brand in BRAND_BLOCKLIST)


def _is_service_relevant(keyword: str, industry: str, services: list[str] | None) -> bool:
    """Check if keyword is relevant to the service industry (not just any random result)."""
    kw_lower = keyword.lower()
    industry_key = industry.lower().replace(" ", "_")

    # Must contain at least one service-related term
    service_signals = {
        "service", "services", "contractor", "company", "repair",
        "install", "installation", "removal", "maintenance",
        "cost", "price", "quote", "estimate", "emergency",
        "residential", "commercial", "licensed", "professional",
        "near me", "in my area",
    }

    # Add industry-specific terms
    if industry_key in INDUSTRY_SEEDS:
        for seed in INDUSTRY_SEEDS[industry_key]:
            for word in seed.lower().split():
                if len(word) > 2 and word not in {"the", "and", "for", "near"}:
                    service_signals.add(word)

    # Add extracted services
    if services:
        for svc in services:
            for word in svc.lower().split():
                if len(word) > 2:
                    service_signals.add(word)

    return any(term in kw_lower for term in service_signals)


async def get_keywords(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[KeywordData]:
    """
    Generate location-specific seed keywords, fetch from DataForSEO,
    filter for relevance, and prioritize keywords containing the city name.
    """
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise ValueError(
            "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
        )

    seed_keywords = generate_seed_keywords(industry, location, services)
    target_location = _detect_location(location)
    city = _extract_city(location).lower()

    # Build auth header
    credentials = f"{login}:{password}"
    auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"

    endpoint = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"
    payload = [
        {
            "keywords": seed_keywords[:20],
            "location_name": target_location,
            "language_name": "English",
            "sort_by": "search_volume",
            "limit": 100,
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

    return _parse_and_rank(data, industry, city, services)


def _parse_and_rank(
    response: dict[str, Any],
    industry: str,
    city: str,
    services: list[str] | None,
) -> list[KeywordData]:
    """
    Parse DataForSEO response, filter, and rank.

    Ranking priority:
    1. Keywords containing the city name (local-specific)
    2. Keywords with service terms (general service intent)
    Filtered out: brand names, irrelevant results
    """
    all_keywords: list[tuple[str, int]] = []

    for task in response.get("tasks", []):
        for item in task.get("result", []) or []:
            keyword = item.get("keyword", "")
            volume = item.get("search_volume", 0)
            if not keyword or not volume or volume <= 0:
                continue
            all_keywords.append((keyword, volume))

    # Filter: remove brands, irrelevant keywords, and case duplicates
    seen_lower: set[str] = set()
    filtered = []
    for kw, vol in all_keywords:
        kw_lower = kw.lower()
        if kw_lower in seen_lower:
            continue
        seen_lower.add(kw_lower)
        if _is_blocked_brand(kw):
            continue
        if not _is_service_relevant(kw, industry, services):
            continue
        filtered.append((kw_lower, vol))

    # Separate into location-specific and generic
    local_keywords = [(kw, vol) for kw, vol in filtered if city in kw.lower()]
    generic_keywords = [(kw, vol) for kw, vol in filtered if city not in kw.lower()]

    # Sort each group by volume
    local_keywords.sort(key=lambda x: x[1], reverse=True)
    generic_keywords.sort(key=lambda x: x[1], reverse=True)

    # Prefer local: fill with local first, then generic to reach 10
    final = local_keywords[:10]
    if len(final) < 10:
        final.extend(generic_keywords[:10 - len(final)])

    return [KeywordData(keyword=kw, monthly_searches=vol) for kw, vol in final]


def get_keywords_sync(
    industry: str,
    location: str,
    services: list[str] | None = None,
) -> list[KeywordData]:
    """Synchronous wrapper for get_keywords."""
    return asyncio.run(get_keywords(industry, location, services))
