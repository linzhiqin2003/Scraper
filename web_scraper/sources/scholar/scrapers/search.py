"""Google Scholar search scraper using httpx + BeautifulSoup."""
import re
import time
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup, Tag

from ....core.exceptions import CaptchaError, RateLimitedError
from ....core.rate_limiter import RateLimiter, RateLimiterConfig
from ..config import (
    BASE_URL,
    SCHOLAR_SEARCH_URL,
    DEFAULT_HEADERS,
    SEARCH_SORT,
    SEARCH_LANGUAGES,
    RATE_LIMIT,
    Selectors,
)
from ..models import ScholarResult, ScholarSearchResponse
from ..cookies import load_cookies


def _parse_result_item(item: Tag) -> Optional[ScholarResult]:
    """Parse a single Scholar search result div.

    Args:
        item: BeautifulSoup Tag for a single result (div.gs_r.gs_or.gs_scl).

    Returns:
        ScholarResult or None if parsing fails.
    """
    selectors = Selectors.scholar

    # Title and URL
    title_link = item.select_one(selectors.title_link)
    title_text_el = item.select_one(selectors.title_text)

    if title_link:
        title = title_link.get_text(strip=True)
        url = title_link.get("href")
        is_citation = False
    elif title_text_el:
        # [CITATION] entries have no link
        title = title_text_el.get_text(strip=True)
        # Remove "[CITATION]" prefix
        title = re.sub(r"^\[CITATION\]\s*", "", title).strip()
        url = None
        is_citation = True
    else:
        return None

    if not title:
        return None

    # Authors / source info (div.gs_a)
    authors_el = item.select_one(selectors.authors_info)
    authors_text = authors_el.get_text(strip=True) if authors_el else None

    # Extract year from authors string (e.g. "J Smith, A Lee - Nature, 2023 - springer.com")
    year = None
    source = None
    if authors_text:
        year_match = re.search(r"\b(19|20)\d{2}\b", authors_text)
        if year_match:
            year = int(year_match.group())

        # Extract source: last segment after " - "
        parts = authors_text.split(" - ")
        if len(parts) >= 2:
            source = parts[-1].strip()

    # Snippet (div.gs_rs)
    snippet_el = item.select_one(selectors.snippet)
    snippet = snippet_el.get_text(strip=True) if snippet_el else None

    # Cited by count and URL
    cited_by_count = None
    cited_by_url = None
    cited_by_link = item.select_one(selectors.cited_by_link)
    if cited_by_link:
        cited_text = cited_by_link.get_text(strip=True)
        count_match = re.search(r"\d+", cited_text)
        if count_match:
            cited_by_count = int(count_match.group())
        href = cited_by_link.get("href", "")
        if href and not href.startswith("http"):
            cited_by_url = f"{BASE_URL}{href}"
        else:
            cited_by_url = href

    # PDF link
    pdf_url = None
    pdf_link = item.select_one(selectors.pdf_link)
    if pdf_link:
        pdf_href = pdf_link.get("href")
        if pdf_href:
            pdf_url = pdf_href

    return ScholarResult(
        title=title,
        url=url,
        authors=authors_text,
        snippet=snippet,
        cited_by_count=cited_by_count,
        cited_by_url=cited_by_url,
        year=year,
        pdf_url=pdf_url,
        source=source,
        is_citation=is_citation,
    )


def _detect_captcha(html: str, response: httpx.Response) -> None:
    """Check for CAPTCHA or rate limiting.

    Raises:
        CaptchaError: If CAPTCHA is detected.
        RateLimitedError: If rate limited (429).
    """
    if response.status_code == 429:
        raise RateLimitedError("Rate limited by Google Scholar (429)")

    # Check URL redirect to /sorry/
    if "/sorry/" in str(response.url):
        raise CaptchaError("Google Scholar CAPTCHA detected (redirected to /sorry/)")

    # Check for captcha form in HTML
    if "captcha" in html.lower() or "unusual traffic" in html.lower():
        raise CaptchaError("Google Scholar CAPTCHA detected in response")


def _extract_total_results(html: str) -> Optional[int]:
    """Extract approximate total results count from Scholar page.

    Scholar shows something like "About 1,234,000 results".
    """
    match = re.search(r"About\s+([\d,]+)\s+results", html)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


class SearchScraper:
    """Google Scholar search scraper using httpx."""

    def __init__(
        self,
        cookies_path: Optional[Path] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """Initialize scraper with optional cookies.

        Args:
            cookies_path: Optional path to cookies.txt file.
            rate_limiter: Optional rate limiter for request throttling.
        """
        self.cookies = load_cookies(cookies_path)
        self.rate_limiter = rate_limiter

    def search(
        self,
        query: str,
        page: int = 1,
        sort: Optional[str] = None,
        year_lo: Optional[int] = None,
        year_hi: Optional[int] = None,
        lang: Optional[str] = None,
    ) -> ScholarSearchResponse:
        """Search Google Scholar.

        Args:
            query: Search keywords.
            page: Page number (1-indexed).
            sort: Sort order - "relevance" or "date".
            year_lo: Filter papers from this year onwards.
            year_hi: Filter papers up to this year.
            lang: Language filter (e.g. "en", "zh").

        Returns:
            ScholarSearchResponse with results.

        Raises:
            CaptchaError: If CAPTCHA is detected.
            RateLimitedError: If rate limited.
        """
        # Build query parameters
        params = {"q": query, "hl": "en"}

        # Pagination: Scholar uses start=0,10,20...
        if page > 1:
            params["start"] = (page - 1) * 10

        # Sort by date
        if sort and sort in SEARCH_SORT and SEARCH_SORT[sort]:
            params["scisbd"] = "1"

        # Year range
        if year_lo:
            params["as_ylo"] = str(year_lo)
        if year_hi:
            params["as_yhi"] = str(year_hi)

        # Language filter
        if lang and lang in SEARCH_LANGUAGES and SEARCH_LANGUAGES[lang]:
            params["lr"] = SEARCH_LANGUAGES[lang]

        url = f"{SCHOLAR_SEARCH_URL}?{urlencode(params)}"

        with httpx.Client(
            cookies=self.cookies,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            response = client.get(url)

        # Check for CAPTCHA / rate limiting
        html = response.text
        _detect_captcha(html, response)

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}")

        # Parse HTML
        soup = BeautifulSoup(html, "lxml")

        # Extract results
        selectors = Selectors.scholar
        result_items = soup.select(selectors.result_item)

        results = []
        for item in result_items:
            parsed = _parse_result_item(item)
            if parsed:
                results.append(parsed)

        # Total results
        total_results = _extract_total_results(html)

        # Check for next page
        has_next_page = soup.select_one(selectors.next_page) is not None

        return ScholarSearchResponse(
            query=query,
            results=results,
            total_results=total_results,
            page=page,
            has_next_page=has_next_page,
        )

    def search_multi_pages(
        self,
        query: str,
        max_pages: int = 1,
        sort: Optional[str] = None,
        year_lo: Optional[int] = None,
        year_hi: Optional[int] = None,
        lang: Optional[str] = None,
    ) -> List[ScholarResult]:
        """Search multiple pages with rate-limiting delays.

        Args:
            query: Search keywords.
            max_pages: Maximum number of pages to fetch.
            sort: Sort order.
            year_lo: Filter papers from this year.
            year_hi: Filter papers up to this year.
            lang: Language filter.

        Returns:
            List of all ScholarResult items across pages.
        """
        all_results: List[ScholarResult] = []

        for page in range(1, max_pages + 1):
            try:
                response = self.search(
                    query,
                    page=page,
                    sort=sort,
                    year_lo=year_lo,
                    year_hi=year_hi,
                    lang=lang,
                )
                all_results.extend(response.results)

                if not response.results or not response.has_next_page:
                    break

                if page < max_pages:
                    if self.rate_limiter:
                        self.rate_limiter.wait()
                    else:
                        delay = RATE_LIMIT.random_delay()
                        time.sleep(delay)

            except (CaptchaError, RateLimitedError) as e:
                print(f"[Page {page}] Blocked: {e}")
                break
            except Exception as e:
                print(f"[Page {page}] Error: {e}")
                break

        return all_results
