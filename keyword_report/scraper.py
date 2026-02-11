"""Simplified Playwright scraper for keyword report tool.

Stripped-down version of src/design_brief/scraper.py:
- 5 pages max
- No WHOIS lookup, no social link extraction, no ScraperAPI fallback
- Returns simple dataclasses
"""

import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from playwright.async_api import (
    async_playwright,
    Page,
    TimeoutError as PlaywrightTimeout,
)
from bs4 import BeautifulSoup


@dataclass
class ScrapedPage:
    url: str
    title: str | None = None
    meta_description: str | None = None
    h1: str | None = None
    text_content: str = ""


@dataclass
class ScrapedSite:
    base_url: str
    pages: list[ScrapedPage] = field(default_factory=list)


# Priority patterns for local service business pages
PRIORITY_PATTERNS = [
    r"/services?",
    r"/about",
    r"/contact",
    r"/locations?",
    r"/areas?",
    r"/team",
    r"/testimonials?",
    r"/reviews?",
]


async def scrape_site(url: str, max_pages: int = 5) -> ScrapedSite:
    """
    Scrape a website, returning up to max_pages pages.

    Args:
        url: Homepage URL to start from
        max_pages: Maximum pages to scrape (default 5)

    Returns:
        ScrapedSite with scraped pages
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    scraped_pages: list[ScrapedPage] = []
    visited: set[str] = set()
    to_visit: list[str] = [url]

    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        try:
            page = await context.new_page()

            while to_visit and len(scraped_pages) < max_pages:
                current_url = _normalize_url(to_visit.pop(0))

                if current_url in visited:
                    continue
                if not current_url.startswith(base_url):
                    continue

                visited.add(current_url)
                scraped_page, links = await _scrape_page(page, current_url, base_url)

                if scraped_page:
                    scraped_pages.append(scraped_page)

                for link in links:
                    norm = _normalize_url(link)
                    if norm not in visited and norm not in to_visit and norm.startswith(base_url):
                        to_visit.append(norm)
        finally:
            await browser.close()

    return ScrapedSite(base_url=base_url, pages=scraped_pages)


async def _scrape_page(
    page: Page, url: str, base_url: str
) -> tuple[ScrapedPage | None, list[str]]:
    """Scrape a single page, returning the page data and discovered links."""
    try:
        await page.goto(url, timeout=30000, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        html = await page.content()
    except (PlaywrightTimeout, Exception):
        return None, []

    soup = BeautifulSoup(html, "html.parser")

    # Extract metadata
    title = None
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)

    meta_description = None
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_description = meta_tag.get("content", "")

    h1 = None
    h1_tag = soup.find("h1")
    if h1_tag:
        h1 = h1_tag.get_text(strip=True)

    # Discover internal links before stripping nav
    links = _discover_links(soup, base_url)

    # Extract text content (strips nav/header/footer/scripts)
    text_content = _extract_text(soup)

    scraped = ScrapedPage(
        url=url,
        title=title,
        meta_description=meta_description,
        h1=h1,
        text_content=text_content,
    )
    return scraped, links


def _extract_text(soup: BeautifulSoup) -> str:
    """Extract clean text content from HTML."""
    for el in soup.find_all(["script", "style", "noscript", "header", "footer", "nav"]):
        el.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = "\n".join(lines)

    if len(text) > 15000:
        text = text[:15000]

    return text


def _discover_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Discover internal links, prioritizing service/about/contact pages."""
    links: list[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|mp4|mp3|zip|doc|docx)$", href, re.I):
            continue

        full_url = urljoin(base_url, href)
        if full_url.startswith(base_url):
            links.append(full_url)

    def priority_sort(url: str) -> int:
        for i, pattern in enumerate(PRIORITY_PATTERNS):
            if re.search(pattern, url, re.I):
                return i
        return len(PRIORITY_PATTERNS)

    return sorted(set(links), key=priority_sort)


def _normalize_url(url: str) -> str:
    """Normalize URL by removing trailing slashes and fragments."""
    parsed = urlparse(url)
    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    return normalized


def scrape_site_sync(url: str, max_pages: int = 5) -> ScrapedSite:
    """Synchronous wrapper for scrape_site."""
    return asyncio.run(scrape_site(url, max_pages))
