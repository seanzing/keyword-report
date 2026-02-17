"""Business extraction via Haiku and keyword presence matching."""

import json
import os
import re

import anthropic
from dotenv import load_dotenv

from .scraper import ScrapedPage
from .keywords import KeywordData
from .models import BusinessProfile, BUSINESS_MODELS

load_dotenv()

HAIKU_MODEL = "claude-haiku-4-5-20251001"


def extract_business_info(pages: list[ScrapedPage]) -> BusinessProfile:
    """
    Extract a full BusinessProfile from scraped pages using Haiku.

    Sends content from ALL pages (not just homepage) so we catch service area
    info that's often on about/contact/locations pages.

    Returns:
        BusinessProfile with AI-generated fields for any business type.
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

    models_list = ", ".join(BUSINESS_MODELS)

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=1024,
        system=(
            "You are analyzing a business website. Your job is to classify the business "
            "and generate keyword research data. The business could be ANY type: a local "
            "service company (plumber, painter), a restaurant, a law firm, a medical practice, "
            "an e-commerce store, a SaaS product, a national brand, etc.\n\n"
            "Respond with JSON only, no other text.\n\n"
            "Format:\n"
            "{\n"
            '  "business_name": "...",\n'
            '  "industry": "free text industry description (e.g. plumbing, Italian restaurant, personal injury law, women\'s clothing)",\n'
            '  "industry_plural": "what you\'d call these businesses (e.g. plumbers, Italian restaurants, personal injury lawyers, women\'s clothing stores)",\n'
            f'  "business_model": "one of: {models_list}",\n'
            '  "location": "City, ST (or empty string if non-local/national)",\n'
            '  "services": ["service/product 1", "service/product 2", ...],\n'
            '  "service_area_cities": ["City1", "City2", ...],\n'
            '  "seed_keywords": ["keyword1", "keyword2", ...],\n'
            '  "relevance_terms": ["term1", "term2", ...],\n'
            '  "brand_blocklist": ["competitor1", "aggregator1", ...],\n'
            '  "report_headline": "...",\n'
            '  "report_value_prop": "...",\n'
            '  "report_cta_text": "..."\n'
            "}\n\n"
            "BUSINESS_MODEL classification:\n"
            "- local_service: serves customers in a geographic area (plumbers, painters, electricians, cleaners)\n"
            "- local_storefront: physical location customers visit (restaurants, salons, retail stores)\n"
            "- professional_service: local professional practices (law firms, dentists, accountants, therapists)\n"
            "- ecommerce: sells products online, ships nationally/globally\n"
            "- saas: software-as-a-service, online tool or platform\n"
            "- national_brand: national/global brand without strong local component\n\n"
            "LOCATION: Primary city in 'City, ST' format for local businesses. Empty string for non-local.\n\n"
            "SERVICE_AREA_CITIES: For local businesses (local_service, local_storefront, professional_service), "
            "list ALL cities/towns the business serves. Look for 'Areas We Serve', 'Service Areas', city names "
            "in page URLs, location pages, etc. If the site doesn't list specific cities, infer 5-8 nearby "
            "cities/suburbs. Return at least 5 cities. For non-local businesses, return empty list.\n\n"
            "SERVICES: List 3-8 specific services or products offered.\n\n"
            "SEED_KEYWORDS: Generate 15-20 seed keywords for keyword research.\n"
            "- For LOCAL businesses: pair service terms with city names (e.g. 'plumber Denver', 'roof repair Littleton'). "
            "Spread across different cities in the service area.\n"
            "- For ECOMMERCE: use product category + buying intent terms (e.g. 'buy women\\'s running shoes', 'best yoga pants').\n"
            "- For SAAS: use feature/solution + intent terms (e.g. 'project management software', 'best CRM for small business').\n"
            "- For all types: include a mix of head terms and long-tail.\n\n"
            "RELEVANCE_TERMS: 20-30 words/phrases that signal a keyword is relevant to this specific business. "
            "Include industry terms, service/product names, and related concepts. These are used to filter "
            "keyword results for relevance.\n\n"
            "BRAND_BLOCKLIST: List competitor brand names, aggregator sites (Yelp, Angi, etc.), and major "
            "retailers/platforms that should be filtered out of keyword results. 5-15 entries.\n\n"
            "REPORT_HEADLINE: A short headline for the PDF report (e.g. 'Local SEO Opportunity Report', "
            "'E-Commerce Keyword Opportunity Report', 'Search Visibility Report').\n\n"
            "REPORT_VALUE_PROP: 1-2 sentences explaining the value proposition for this business type. "
            "For local businesses: mention local landing pages and local search visibility. "
            "For e-commerce: mention product page optimization and shopping search visibility. "
            "For SaaS: mention search visibility for solution-related queries. "
            "Keep it specific to the business.\n\n"
            "REPORT_CTA_TEXT: 1-2 sentences for the call-to-action banner. Mention the specific benefit "
            "relevant to this business type (more local enquiries, more online sales, more demo requests, etc.)."
        ),
        messages=[{"role": "user", "content": page_content}],
    )

    text = response.content[0].text.strip()

    # Extract JSON — handle nested arrays/objects
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        text = json_match.group()

    result = json.loads(text)

    # Validate business_model
    business_model = result.get("business_model", "local_service")
    if business_model not in BUSINESS_MODELS:
        business_model = "local_service"

    # Build profile with sensible fallbacks
    profile = BusinessProfile(
        business_name=result.get("business_name", "Unknown Business"),
        industry=result.get("industry", "service"),
        industry_plural=result.get("industry_plural", f"{result.get('industry', 'service')} businesses"),
        business_model=business_model,
        location=result.get("location", ""),
        services=result.get("services", []),
        service_area_cities=result.get("service_area_cities", []),
        seed_keywords=result.get("seed_keywords", []),
        relevance_terms=result.get("relevance_terms", []),
        brand_blocklist=result.get("brand_blocklist", []),
        report_headline=result.get("report_headline", "SEO Opportunity Report"),
        report_value_prop=result.get("report_value_prop", ""),
        report_cta_text=result.get("report_cta_text", ""),
    )

    # Fallback: if no seed keywords generated, create basic ones from services
    if not profile.seed_keywords and profile.services:
        if profile.is_local and profile.location:
            city = profile.location.split(",")[0].strip()
            profile.seed_keywords = [f"{svc} {city}" for svc in profile.services[:10]]
        else:
            profile.seed_keywords = profile.services[:15]

    # Fallback: if no relevance terms, use services + industry
    if not profile.relevance_terms:
        profile.relevance_terms = list(profile.services) + [profile.industry]

    # Fallback: report copy
    if not profile.report_value_prop:
        if profile.is_local:
            profile.report_value_prop = (
                "At ZING, we build your new website along with local landing pages "
                "so you rank in more places and get more impressions. That means more people "
                "in your area see your business when they search — and more of them get in touch."
            )
        else:
            profile.report_value_prop = (
                "At ZING, we build your new website optimized for search so you rank for "
                "the keywords your customers are searching. That means more visibility, "
                "more traffic, and more conversions."
            )

    if not profile.report_cta_text:
        if profile.is_local:
            profile.report_cta_text = (
                "With your new website and landing pages, your business has the potential to appear "
                "in thousands more local searches every month. More visibility means more enquiries, "
                "and more enquiries means more jobs."
            )
        else:
            profile.report_cta_text = (
                "With your new website optimized for search, your business has the potential to capture "
                "thousands more searches every month. More visibility means more traffic, "
                "and more traffic means more customers."
            )

    if not profile.report_headline:
        profile.report_headline = "Local SEO Opportunity Report" if profile.is_local else "SEO Opportunity Report"

    return profile


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
