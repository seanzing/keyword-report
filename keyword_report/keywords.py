"""DataForSEO client for keyword research — tuned for local service businesses.

Strategy (matching IdealReport.jpeg):
- Seeds spread across service area cities, not just the home city
- Each result keyword should ideally be a different {service} + {city} combo
- Semantic dedup prevents "house painting castle rock" / "castle rock house painting"
- Brand blocklist, service relevance filter
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

# Service terms per industry — diverse set for varied results
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


@dataclass
class RankedKeywordData:
    keyword: str
    search_volume: int
    rank_position: int
    serp_type: str  # "organic", "paid", etc.


def _extract_domain(url: str) -> str:
    """Strip protocol, www., and path from a URL to get bare domain.

    >>> _extract_domain("https://www.example.com/about")
    'example.com'
    """
    domain = re.sub(r"^https?://", "", url)
    domain = re.sub(r"^www\.", "", domain)
    domain = domain.split("/")[0].split("?")[0]
    return domain.lower()


def build_city_list(location: str, service_area_cities: list[str] | None) -> list[str]:
    """Build a combined city list from primary location and service area cities."""
    primary_city = _extract_city(location)
    all_cities = [primary_city]
    if service_area_cities:
        all_cities.extend(c for c in service_area_cities if c not in all_cities)
    return all_cities


def _extract_city(location: str) -> str:
    """Extract just the city name from 'City, ST' format."""
    return location.split(",")[0].strip()


def generate_seed_keywords(
    industry: str,
    location: str,
    services: list[str] | None = None,
    service_area_cities: list[str] | None = None,
) -> list[str]:
    """
    Generate seed keywords spread across service area cities.

    Strategy: pair different service terms with different cities so
    DataForSEO returns a diverse set of {service} {city} keywords.
    """
    primary_city = _extract_city(location)
    industry_lower = industry.lower()
    industry_key = industry_lower.replace(" ", "_")

    # Build the list of cities to target
    cities = [primary_city]
    if service_area_cities:
        for c in service_area_cities:
            if c.lower() != primary_city.lower() and c not in cities:
                cities.append(c)

    # Build service terms list
    service_terms = [industry_lower]
    if industry_key in INDUSTRY_SEEDS:
        service_terms.extend(INDUSTRY_SEEDS[industry_key])
    if services:
        for svc in services:
            if svc.lower() not in [s.lower() for s in service_terms]:
                service_terms.append(svc)

    # Pair service terms with cities in round-robin
    # This ensures we get keywords for multiple cities, not just the primary
    keywords = []
    for i, term in enumerate(service_terms):
        city = cities[i % len(cities)]
        keywords.append(f"{term} {city}")

    # Also ensure the primary city gets the core industry term
    primary_seed = f"{industry_lower} {primary_city}"
    if primary_seed.lower() not in [k.lower() for k in keywords]:
        keywords.insert(0, primary_seed)

    # Deduplicate
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
    Detect the best DataForSEO location_name.

    Uses state-level for US (e.g., "Colorado,United States").
    """
    location_lower = location.lower()

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

    match = re.search(r",\s*([A-Z]{2})\b", location)
    if match:
        abbrev = match.group(1)
        if abbrev in us_states:
            return f"{us_states[abbrev]},United States"

    return "United States"


def _is_blocked_brand(keyword: str) -> bool:
    kw_lower = keyword.lower()
    return any(brand in kw_lower for brand in BRAND_BLOCKLIST)


def _normalize_service_intent(keyword: str, known_cities: list[str]) -> str:
    """
    Extract the service intent from a keyword by removing location parts.

    "house painter castle rock" → "house painter"
    "interior painting castle rock co" → "interior painting"
    "castle rock house painters" → "house painters"

    This lets us detect that these are all semantically the same.
    """
    kw = keyword.lower()

    # Remove city names
    for city in known_cities:
        kw = kw.replace(city.lower(), "")

    # Remove state abbreviations and common suffixes
    kw = re.sub(r"\b[a-z]{2}\b$", "", kw)  # trailing 2-letter state
    kw = re.sub(r"\bco\b", "", kw)
    kw = re.sub(r"\bin\b", "", kw)

    # Normalize whitespace and sort words for order-independent comparison
    words = sorted(kw.split())
    return " ".join(words)


def _is_service_relevant(keyword: str, industry: str, services: list[str] | None) -> bool:
    """Check if keyword is relevant to the service industry."""
    kw_lower = keyword.lower()
    industry_key = industry.lower().replace(" ", "_")

    service_signals = {
        "service", "services", "contractor", "company", "repair",
        "install", "installation", "removal", "maintenance",
        "cost", "price", "quote", "estimate", "emergency",
        "residential", "commercial", "licensed", "professional",
        "near me", "in my area",
    }

    if industry_key in INDUSTRY_SEEDS:
        for seed in INDUSTRY_SEEDS[industry_key]:
            for word in seed.lower().split():
                if len(word) > 2 and word not in {"the", "and", "for", "near"}:
                    service_signals.add(word)

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
    service_area_cities: list[str] | None = None,
) -> list[KeywordData]:
    """
    Fetch keywords from DataForSEO with service area diversity.

    Seeds are spread across service area cities. Results are filtered for
    relevance, deduplicated by intent, and diversified by city.
    """
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise ValueError(
            "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
        )

    primary_city = _extract_city(location)

    # Build full city list for intent normalization
    all_cities = [primary_city]
    if service_area_cities:
        all_cities.extend(c for c in service_area_cities if c not in all_cities)

    seed_keywords = generate_seed_keywords(industry, location, services, service_area_cities)
    target_location = _detect_location(location)

    credentials = f"{login}:{password}"
    auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"

    endpoint = "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"
    payload = [
        {
            "keywords": seed_keywords[:20],
            "location_name": target_location,
            "language_name": "English",
            "sort_by": "search_volume",
            "limit": 200,
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

    return _parse_and_rank(data, industry, services, all_cities)


def _parse_and_rank(
    response: dict[str, Any],
    industry: str,
    services: list[str] | None,
    all_cities: list[str],
) -> list[KeywordData]:
    """
    Parse, filter, deduplicate by intent, and diversify results.

    Goal: 10 keywords that each represent a DIFFERENT {service} + {city} combo,
    matching the style of IdealReport.jpeg.
    """
    # Step 1: Parse all results
    raw: list[tuple[str, int]] = []
    for task in response.get("tasks", []):
        for item in task.get("result", []) or []:
            keyword = item.get("keyword", "")
            volume = item.get("search_volume", 0)
            if keyword and volume and volume > 0:
                raw.append((keyword.lower(), volume))

    # Step 2: Case dedup
    seen_exact: set[str] = set()
    deduped = []
    for kw, vol in raw:
        if kw in seen_exact:
            continue
        seen_exact.add(kw)
        deduped.append((kw, vol))

    # Step 3: Filter brands and irrelevant
    filtered = []
    for kw, vol in deduped:
        if _is_blocked_brand(kw):
            continue
        if not _is_service_relevant(kw, industry, services):
            continue
        # Must contain at least one known city name to be a local keyword
        has_city = any(city.lower() in kw for city in all_cities)
        if not has_city:
            continue
        filtered.append((kw, vol))

    # Step 4: Semantic dedup — keep highest volume for each intent
    intent_best: dict[str, tuple[str, int]] = {}
    for kw, vol in filtered:
        intent = _normalize_service_intent(kw, all_cities)
        if intent not in intent_best or vol > intent_best[intent][1]:
            intent_best[intent] = (kw, vol)

    unique_keywords = list(intent_best.values())
    unique_keywords.sort(key=lambda x: x[1], reverse=True)

    # Step 5: Diversify by city — don't let one city dominate
    final: list[tuple[str, int]] = []
    city_count: dict[str, int] = {}
    max_per_city = 3  # No more than 3 keywords per city

    for kw, vol in unique_keywords:
        if len(final) >= 10:
            break

        # Which city is this keyword for?
        kw_city = None
        for city in all_cities:
            if city.lower() in kw:
                kw_city = city.lower()
                break

        if kw_city:
            count = city_count.get(kw_city, 0)
            if count >= max_per_city:
                continue
            city_count[kw_city] = count + 1

        final.append((kw, vol))

    # If we still need more (rare), add back skipped ones
    if len(final) < 10:
        used = {kw for kw, _ in final}
        for kw, vol in unique_keywords:
            if len(final) >= 10:
                break
            if kw not in used:
                final.append((kw, vol))

    return [KeywordData(keyword=kw, monthly_searches=vol) for kw, vol in final]


def get_keywords_sync(
    industry: str,
    location: str,
    services: list[str] | None = None,
    service_area_cities: list[str] | None = None,
) -> list[KeywordData]:
    """Synchronous wrapper for get_keywords."""
    return asyncio.run(get_keywords(industry, location, services, service_area_cities))


# ---------------------------------------------------------------------------
# Ranked Keywords — actual SERP ranking data for a domain
# ---------------------------------------------------------------------------

async def get_ranked_keywords(
    domain: str,
    location: str,
) -> list[RankedKeywordData]:
    """
    Fetch keywords that a domain actually ranks for in Google.

    Uses DataForSEO's Ranked Keywords endpoint. Non-fatal: returns [] on any
    failure so the report pipeline can continue (all Old Site marks become X).
    """
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        return []

    target_location = _detect_location(location)
    bare_domain = _extract_domain(domain) if "://" in domain else domain

    credentials = f"{login}:{password}"
    auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"

    endpoint = "https://api.dataforseo.com/v3/dataforseo_labs/google/ranked_keywords/live"
    payload = [
        {
            "target": bare_domain,
            "location_name": target_location,
            "language_name": "English",
            "order_by": ["keyword_data.keyword_info.search_volume,desc"],
            "limit": 1000,
        }
    ]
    headers = {
        "Authorization": auth,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return _parse_ranked_keywords(data)
    except Exception:
        return []


def _parse_ranked_keywords(response: dict[str, Any]) -> list[RankedKeywordData]:
    """Parse the Ranked Keywords API response."""
    results: list[RankedKeywordData] = []
    for task in response.get("tasks", []):
        for result in task.get("result", []) or []:
            for item in result.get("items", []) or []:
                keyword_data = item.get("keyword_data", {})
                keyword = keyword_data.get("keyword", "")
                keyword_info = keyword_data.get("keyword_info", {})
                volume = keyword_info.get("search_volume", 0)

                serp_elem = item.get("ranked_serp_element", {})
                serp_item = serp_elem.get("serp_item", {})
                rank = serp_item.get("rank_group", 0)
                serp_type = serp_item.get("type", "organic")

                if keyword:
                    results.append(RankedKeywordData(
                        keyword=keyword,
                        search_volume=volume or 0,
                        rank_position=rank or 0,
                        serp_type=serp_type,
                    ))
    return results


def check_ranking_for_keywords(
    opportunity_keywords: list[KeywordData],
    ranked_keywords: list[RankedKeywordData],
    all_cities: list[str],
) -> list[dict]:
    """
    Determine Old Site check/X marks by cross-referencing opportunity keywords
    against the domain's actual Google rankings.

    Uses intent normalization (strips city names, sorts words) for fuzzy
    matching, plus an exact-string fallback.

    Returns:
        [{"keyword": str, "monthly_searches": int, "on_old_site": bool}, ...]
    """
    # Build sets for fast lookup
    ranked_raw = {rk.keyword.lower() for rk in ranked_keywords}
    ranked_intents = {
        _normalize_service_intent(rk.keyword, all_cities) for rk in ranked_keywords
    }

    results = []
    for kw in opportunity_keywords:
        kw_lower = kw.keyword.lower()
        kw_intent = _normalize_service_intent(kw.keyword, all_cities)

        on_old_site = kw_intent in ranked_intents or kw_lower in ranked_raw

        results.append({
            "keyword": kw.keyword,
            "monthly_searches": kw.monthly_searches,
            "on_old_site": on_old_site,
        })

    return results
