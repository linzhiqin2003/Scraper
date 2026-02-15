"""Generic article content extractor for publisher pages.

Three-tier fetch strategy:
1. curl-cffi (Chrome TLS fingerprint impersonation) — fast, handles most sites
2. httpx (plain HTTP) — fallback for simple sites
3. Playwright (headless Chrome) — handles Cloudflare JS challenges, last resort
"""
import time
from pathlib import Path
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests

from ....converters.markdown import html_to_markdown
from ....core.rate_limiter import RateLimiter
from ..config import DEFAULT_HEADERS, RATE_LIMIT, Selectors
from ..models import ScholarArticle
from ..cookies import load_cookies


def _extract_meta(soup: BeautifulSoup, selector: str) -> Optional[str]:
    """Extract content from a meta tag."""
    el = soup.select_one(selector)
    if el:
        return el.get("content")
    return None


def _extract_meta_list(soup: BeautifulSoup, name: str) -> List[str]:
    """Extract all values from repeated meta tags (e.g. citation_author)."""
    results = []
    for tag in soup.find_all("meta", attrs={"name": name}):
        content = tag.get("content")
        if content:
            results.append(content)
    return results


def parse_article_html(html: str, url: str) -> ScholarArticle:
    """Parse publisher article HTML and extract content.

    Uses a multi-strategy approach:
    1. <article> tag
    2. <main> tag
    3. Known content class patterns
    4. Fallback: meta description / og:description

    Args:
        html: Raw HTML string.
        url: Source URL.

    Returns:
        ScholarArticle with extracted content.
    """
    soup = BeautifulSoup(html, "lxml")
    selectors = Selectors.article

    # Extract metadata from meta tags
    title = _extract_meta(soup, selectors.meta_title)
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else None

    authors = _extract_meta_list(soup, "citation_author")
    doi = _extract_meta(soup, selectors.meta_doi)
    journal = _extract_meta(soup, selectors.meta_journal)
    published_date = _extract_meta(soup, selectors.meta_date)

    # Extract abstract from meta tag
    abstract = _extract_meta(soup, selectors.meta_abstract)

    # Extract main content using multi-strategy approach
    content_html = None
    is_accessible = True

    # Strategy 1: <article> tag
    article_el = soup.find("article")
    if article_el:
        content_html = str(article_el)

    # Strategy 2: <main> tag
    if not content_html:
        main_el = soup.find("main")
        if main_el:
            content_html = str(main_el)

    # Strategy 3: known content classes
    if not content_html:
        for class_selector in selectors.content_classes:
            el = soup.select_one(class_selector)
            if el:
                content_html = str(el)
                break

    # Convert HTML to markdown
    content = None
    if content_html:
        content = html_to_markdown(content_html)
        if content and len(content.strip()) < 50:
            content = None

    # Fallback: use abstract or meta description
    if not content:
        if abstract:
            content = abstract
        else:
            desc = _extract_meta(soup, selectors.meta_description)
            if not desc:
                desc = _extract_meta(soup, selectors.og_description)
            if desc:
                content = desc
                is_accessible = False

    return ScholarArticle(
        url=url,
        title=title,
        authors=authors,
        abstract=abstract,
        content=content,
        doi=doi,
        journal=journal,
        published_date=published_date,
        is_accessible=is_accessible,
    )


def _is_blocked_page(html: str) -> bool:
    """Detect Cloudflare challenge, hard block, or other access-denied pages."""
    # Large pages with real content are not blocked
    if len(html) > 30000:
        return False
    markers = [
        # Cloudflare JS challenge
        "Just a moment...",
        "cf-browser-verification",
        "challenge-platform",
        # Cloudflare hard block
        "is blocked",
        "blocked by",
        "Access denied",
        "Access Denied",
        # Generic anti-bot
        "unusual traffic",
        "captcha",
        "Attention Required",
        "Enable JavaScript and cookies to continue",
    ]
    html_lower = html.lower()
    return any(m.lower() in html_lower for m in markers)


def _is_cloudflare_challenge(html: str) -> bool:
    """Detect Cloudflare JS challenge specifically (the auto-resolving kind)."""
    if len(html) > 20000:
        return False
    markers = ["Just a moment...", "cf-browser-verification", "challenge-platform"]
    return any(m in html for m in markers)


def _fetch_with_curl_cffi(url: str, cookies: httpx.Cookies) -> Tuple[str, str]:
    """Fetch URL using curl-cffi with Chrome TLS fingerprint impersonation.

    Returns:
        Tuple of (html, content_type).

    Raises:
        Exception on HTTP errors or Cloudflare challenge.
    """
    cookie_dict = {}
    for cookie in cookies.jar:
        cookie_dict[cookie.name] = cookie.value

    resp = curl_requests.get(
        url,
        headers=DEFAULT_HEADERS,
        cookies=cookie_dict or None,
        impersonate="chrome",
        allow_redirects=True,
        timeout=30,
    )

    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}")

    html = resp.text
    if _is_blocked_page(html):
        raise Exception("Blocked page detected")

    content_type = resp.headers.get("content-type", "")
    return html, content_type


def _fetch_with_httpx(url: str, cookies: httpx.Cookies) -> Tuple[str, str]:
    """Fetch URL using httpx (fallback).

    Returns:
        Tuple of (html, content_type).

    Raises:
        Exception on HTTP errors or blocked page.
    """
    with httpx.Client(
        cookies=cookies,
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        response = client.get(url)

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        html = response.text
        if _is_blocked_page(html):
            raise Exception("Blocked page detected")

        content_type = response.headers.get("content-type", "")
        return html, content_type


def _fetch_with_playwright(url: str) -> Tuple[str, str]:
    """Fetch URL using Playwright headless Chrome (last resort).

    Handles Cloudflare JS challenges by running a real browser with
    enhanced stealth settings.

    Returns:
        Tuple of (html, content_type).

    Raises:
        Exception on navigation errors.
    """
    from playwright.sync_api import sync_playwright
    from ....core.browser import STEALTH_SCRIPT, get_random_user_agent

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--headless=new",
            ],
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=get_random_user_agent(),
            locale="en-US",
            timezone_id="America/New_York",
            # Extra headers to look like a real Scholar click-through
            extra_http_headers={
                "Referer": "https://scholar.google.com/",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
        )

        page = context.new_page()
        page.add_init_script(STEALTH_SCRIPT)

        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)

            content = page.content()

            if _is_cloudflare_challenge(content):
                # Wait for Cloudflare to resolve — poll up to 30s
                for _ in range(60):
                    time.sleep(0.5)
                    content = page.content()
                    if not _is_cloudflare_challenge(content):
                        break
                else:
                    # Cloudflare didn't resolve — try to return whatever we have
                    # (might still have useful meta tags in the challenge page)
                    pass

            # Check if still blocked after waiting
            if _is_blocked_page(content):
                raise Exception(
                    "Site blocked headless browser (Cloudflare/anti-bot). "
                    "This site requires manual browser access."
                )

            # Give SPA/dynamic pages a moment to render
            try:
                page.wait_for_selector(
                    "h1, article, main, meta[name='citation_title']",
                    timeout=8000,
                )
            except Exception:
                # Some pages may not have these selectors, that's OK
                time.sleep(2)

            content = page.content()
            content_type = ""
            if response:
                val = response.header_value("content-type")
                if val:
                    content_type = val

            return content, content_type

        finally:
            browser.close()


class ArticleScraper:
    """Generic article scraper for publisher pages.

    Three-tier fetch strategy:
    1. curl-cffi (Chrome TLS impersonation) — fast, handles most anti-bot
    2. httpx — fallback for simple sites
    3. Playwright (headless Chrome) — handles Cloudflare JS challenges
    """

    def __init__(
        self,
        cookies_path: Optional[Path] = None,
        use_playwright: bool = True,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """Initialize scraper.

        Args:
            cookies_path: Optional path to cookies.txt file.
            use_playwright: Whether to use Playwright as last-resort fallback.
            rate_limiter: Optional rate limiter for request throttling.
        """
        self.cookies = load_cookies(cookies_path)
        self.use_playwright = use_playwright
        self.rate_limiter = rate_limiter

    def _fetch(self, url: str) -> Tuple[str, str]:
        """Fetch URL with three-tier fallback strategy.

        1. curl-cffi (Chrome TLS impersonation)
        2. httpx (plain HTTP)
        3. Playwright (headless Chrome, if enabled)

        Returns:
            Tuple of (html, content_type).
        """
        # Tier 1: curl-cffi
        try:
            return _fetch_with_curl_cffi(url, self.cookies)
        except Exception:
            pass

        # Tier 2: httpx
        try:
            return _fetch_with_httpx(url, self.cookies)
        except Exception:
            pass

        # Tier 3: Playwright
        if self.use_playwright:
            return _fetch_with_playwright(url)

        raise Exception(f"All fetch methods failed for: {url}")

    def scrape(self, url: str) -> ScholarArticle:
        """Scrape an article from a publisher page.

        Skips PDF URLs (returns a marker result).
        Uses three-tier fallback: curl-cffi → httpx → Playwright.

        Args:
            url: Article URL.

        Returns:
            ScholarArticle with extracted content.
        """
        # Check if URL points to a PDF
        if url.lower().endswith(".pdf"):
            return ScholarArticle(
                url=url,
                title=None,
                is_pdf=True,
                is_accessible=False,
                content="[PDF file - content extraction not supported]",
            )

        html, content_type = self._fetch(url)

        # Check if response is PDF by content-type
        if "pdf" in content_type.lower():
            return ScholarArticle(
                url=url,
                title=None,
                is_pdf=True,
                is_accessible=False,
                content="[PDF file - content extraction not supported]",
            )

        return parse_article_html(html, url)

    def scrape_batch(
        self,
        urls: List[str],
        delay: Optional[float] = None,
    ) -> List[dict]:
        """Scrape multiple articles with delay.

        Args:
            urls: List of article URLs.
            delay: Delay between requests (uses rate limit config if None).

        Returns:
            List of result dicts with status, url, title/error.
        """
        results = []

        for i, url in enumerate(urls, 1):
            try:
                article = self.scrape(url)
                results.append({
                    "status": "success",
                    "url": url,
                    "title": article.title,
                    "article": article,
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "url": url,
                    "error": str(e),
                })

            if i < len(urls):
                if self.rate_limiter and delay is None:
                    self.rate_limiter.wait()
                else:
                    wait = delay if delay is not None else RATE_LIMIT.random_delay()
                    time.sleep(wait)

        return results
