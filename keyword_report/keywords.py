"""DataForSEO client for keyword research — works for any business type.

Strategy:
- Seeds come from BusinessProfile (AI-generated per-business)
- For local businesses: city diversity, service relevance, semantic dedup
- For non-local businesses: relevance filter, dedup, top 10 by volume
"""

import asyncio
import base64
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

from .models import BusinessProfile

load_dotenv()

# Universal aggregator/platform blocklist — merged with profile.brand_blocklist
UNIVERSAL_BLOCKLIST = [
    "yelp", "angi", "angie", "thumbtack", "nextdoor", "houzz",
    "home depot", "lowes", "lowe's", "menards", "ace hardware",
    "amazon", "walmart", "target", "ebay", "etsy",
    "wikipedia", "reddit", "quora",
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


def build_city_list(profile: BusinessProfile) -> list[str]:
    """Build a combined city list from primary location and service area cities."""
    if not profile.is_local or not profile.location:
        return []
    primary_city = _extract_city(profile.location)
    all_cities = [primary_city]
    if profile.service_area_cities:
        all_cities.extend(c for c in profile.service_area_cities if c not in all_cities)
    return all_cities


def _extract_city(location: str) -> str:
    """Extract just the city name from 'City, ST' format."""
    return location.split(",")[0].strip()


def generate_seed_keywords(profile: BusinessProfile) -> list[str]:
    """
    Return seed keywords from the profile (AI-generated).

    Claude already handles city-pairing for local businesses in the prompt.
    """
    return profile.seed_keywords[:20]


_INTL_MAPPINGS = {
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

_US_STATES = {
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


def _detect_location(location: str) -> str:
    """
    Detect the best DataForSEO location_name.

    Uses state-level for US (e.g., "Colorado,United States").
    Used by the Keywords for Keywords endpoint which supports state-level.
    """
    if not location:
        return "United States"

    location_lower = location.lower()

    for keyword, country in _INTL_MAPPINGS.items():
        if keyword in location_lower:
            return country

    match = re.search(r",\s*([A-Z]{2})\b", location)
    if match:
        abbrev = match.group(1)
        if abbrev in _US_STATES:
            return f"{_US_STATES[abbrev]},United States"

    return "United States"


def _detect_country(location: str) -> str:
    """
    Detect the country-level DataForSEO location_name.

    The Ranked Keywords endpoint only accepts country-level locations
    (e.g., "United States"), not state-level (e.g., "Colorado,United States").
    """
    if not location:
        return "United States"

    location_lower = location.lower()

    for keyword, country in _INTL_MAPPINGS.items():
        if keyword in location_lower:
            return country

    return "United States"


def _is_blocked_brand(keyword: str, profile: BusinessProfile) -> bool:
    kw_lower = keyword.lower()
    combined_blocklist = UNIVERSAL_BLOCKLIST + [b.lower() for b in profile.brand_blocklist]
    return any(brand in kw_lower for brand in combined_blocklist)


# Stop words stripped from non-local keywords before intent normalization
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be",
    "near", "me", "my", "best", "top", "good", "how", "what",
    "food", "vs",
}


def _normalize_service_intent(keyword: str, known_cities: list[str]) -> str:
    """
    Normalize a keyword to its core intent for semantic dedup.

    Local path (cities provided): strips city names and state abbreviations,
    sorts remaining words. Intentionally does NOT stem — "house painter" and
    "painting contractor" are different service intents worth keeping.

    Non-local path (no cities): strips stop words, stems, deduplicates words.
    Much more aggressive because without city variation we need to collapse
    "project management software" / "project management tools" / etc.
    """
    kw = keyword.lower()

    if known_cities:
        # Local: strip city names and state abbreviations
        for city in known_cities:
            kw = kw.replace(city.lower(), "")
        kw = re.sub(r"\b[a-z]{2}\b$", "", kw)  # trailing 2-letter state
        kw = re.sub(r"\bco\b", "", kw)
        kw = re.sub(r"\bin\b", "", kw)
        words = sorted(kw.split())
    else:
        # Non-local: aggressive normalization
        words = kw.split()
        words = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
        words = [_stem_service_word(w) for w in words]
        words = sorted(set(words))  # dedup words within the keyword

    return " ".join(words)


def _core_intent(normalized: str) -> str:
    """
    Extract the 2 most significant words as a cluster key for diversity capping.

    Picks the 2 longest words (most specific) from the normalized intent.
    "management project software" -> "management software"
    "cuisin ital restaurant"     -> "cuisin restaurant"
    """
    words = normalized.split()
    if len(words) <= 2:
        return normalized
    top2 = sorted(sorted(words, key=len, reverse=True)[:2])
    return " ".join(top2)


def _is_relevant(keyword: str, profile: BusinessProfile) -> bool:
    """Check if keyword is relevant to the business using profile.relevance_terms."""
    kw_lower = keyword.lower()
    return any(term.lower() in kw_lower for term in profile.relevance_terms)


async def get_keywords(profile: BusinessProfile) -> list[KeywordData]:
    """
    Fetch keywords from DataForSEO using profile-driven seeds.

    Seeds come from the BusinessProfile. Results are filtered for
    relevance, deduplicated, and (for local businesses) diversified by city.
    """
    login = os.getenv("DATAFORSEO_LOGIN")
    password = os.getenv("DATAFORSEO_PASSWORD")
    if not login or not password:
        raise ValueError(
            "DataForSEO not configured. Set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD."
        )

    all_cities = build_city_list(profile)
    seed_keywords = generate_seed_keywords(profile)
    target_location = _detect_location(profile.location)

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

    return _parse_and_rank(data, profile, all_cities)


def _parse_and_rank(
    response: dict[str, Any],
    profile: BusinessProfile,
    all_cities: list[str],
) -> list[KeywordData]:
    """
    Parse, filter, deduplicate, and rank results.

    For local businesses: requires city names, applies city diversity cap.
    For non-local businesses: just dedup and take top 10 by volume.
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
        if _is_blocked_brand(kw, profile):
            continue
        if not _is_relevant(kw, profile):
            continue
        if profile.is_local:
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

    if profile.is_local:
        # Step 5 (local only): Diversify by city — don't let one city dominate
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
    else:
        # Non-local: diversity cap by core intent — don't let one topic dominate
        final: list[tuple[str, int]] = []
        core_count: dict[str, int] = {}
        max_per_core = 2  # No more than 2 keywords per core bigram

        for kw, vol in unique_keywords:
            if len(final) >= 10:
                break
            intent = _normalize_service_intent(kw, [])
            core = _core_intent(intent)
            count = core_count.get(core, 0)
            if count >= max_per_core:
                continue
            core_count[core] = count + 1
            final.append((kw, vol))

        # Backfill if we still need more
        if len(final) < 10:
            used = {kw for kw, _ in final}
            for kw, vol in unique_keywords:
                if len(final) >= 10:
                    break
                if kw not in used:
                    final.append((kw, vol))

    return [KeywordData(keyword=kw, monthly_searches=vol) for kw, vol in final]


def get_keywords_sync(profile: BusinessProfile) -> list[KeywordData]:
    """Synchronous wrapper for get_keywords."""
    return asyncio.run(get_keywords(profile))


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

    target_country = _detect_country(location)
    bare_domain = _extract_domain(domain) if "://" in domain else domain

    credentials = f"{login}:{password}"
    auth = f"Basic {base64.b64encode(credentials.encode()).decode()}"

    endpoint = "https://api.dataforseo.com/v3/dataforseo_labs/google/ranked_keywords/live"
    payload = [
        {
            "target": bare_domain,
            "location_name": target_country,
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


def _stem_service_word(word: str) -> str:
    """Reduce a word to its root for fuzzy cross-referencing.

    Handles the common service-industry suffixes so that word-form variants
    match: painter/painting/painters -> paint, electrician/electrical -> electric.

    Only used for ranking cross-reference — NOT for the keyword dedup pipeline,
    where we want "house painter" and "house painting" to stay distinct.

    >>> _stem_service_word("painters")
    'paint'
    >>> _stem_service_word("plumbing")
    'plumb'
    >>> _stem_service_word("electricians")
    'electric'
    >>> _stem_service_word("water")
    'water'
    """
    if len(word) <= 4:
        return word
    for suffix in ("ians", "ers", "ing", "ors", "ian", "er", "or", "al", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def _normalize_for_ranking_match(keyword: str, known_cities: list[str]) -> str:
    """Aggressively normalize a keyword for ranking cross-reference.

    Like _normalize_service_intent but also stems each word so that
    "house painting castle rock" and "house painters castle rock" both
    reduce to the same root form.
    """
    kw = keyword.lower()

    for city in known_cities:
        kw = kw.replace(city.lower(), "")

    if known_cities:
        kw = re.sub(r"\b[a-z]{2}\b$", "", kw)
        kw = re.sub(r"\bco\b", "", kw)
        kw = re.sub(r"\bin\b", "", kw)

    words = sorted(_stem_service_word(w) for w in kw.split() if w)
    return " ".join(words)


def check_ranking_for_keywords(
    opportunity_keywords: list[KeywordData],
    ranked_keywords: list[RankedKeywordData],
    all_cities: list[str],
) -> list[dict]:
    """
    Determine Old Site check/X marks by cross-referencing opportunity keywords
    against the domain's actual Google rankings.

    Uses stemmed intent normalization (strips city names, stems words, sorts)
    for fuzzy matching, plus an exact-string fallback.

    Returns:
        [{"keyword": str, "monthly_searches": int, "on_old_site": bool}, ...]
    """
    # Build sets for fast lookup
    ranked_raw = {rk.keyword.lower() for rk in ranked_keywords}
    ranked_stemmed = {
        _normalize_for_ranking_match(rk.keyword, all_cities) for rk in ranked_keywords
    }

    results = []
    for kw in opportunity_keywords:
        kw_lower = kw.keyword.lower()
        kw_stemmed = _normalize_for_ranking_match(kw.keyword, all_cities)

        on_old_site = kw_stemmed in ranked_stemmed or kw_lower in ranked_raw

        results.append({
            "keyword": kw.keyword,
            "monthly_searches": kw.monthly_searches,
            "on_old_site": on_old_site,
        })

    return results
