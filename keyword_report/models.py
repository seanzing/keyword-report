"""BusinessProfile dataclass — the core data structure for any business type."""

from dataclasses import dataclass, field


BUSINESS_MODELS = (
    "local_service",
    "local_storefront",
    "ecommerce",
    "saas",
    "professional_service",
    "national_brand",
)

LOCAL_MODELS = ("local_service", "local_storefront", "professional_service")


@dataclass
class BusinessProfile:
    business_name: str
    industry: str  # free text, e.g. "plumbing", "Italian restaurant", "personal injury law"
    industry_plural: str  # e.g. "plumbers", "Italian restaurants", "personal injury lawyers"
    business_model: str  # one of BUSINESS_MODELS
    location: str  # "City, ST" or empty for non-local
    services: list[str] = field(default_factory=list)
    service_area_cities: list[str] = field(default_factory=list)
    seed_keywords: list[str] = field(default_factory=list)
    relevance_terms: list[str] = field(default_factory=list)
    brand_blocklist: list[str] = field(default_factory=list)
    report_headline: str = "SEO Opportunity Report"
    report_value_prop: str = ""
    report_cta_text: str = ""

    @property
    def is_local(self) -> bool:
        return self.business_model in LOCAL_MODELS
