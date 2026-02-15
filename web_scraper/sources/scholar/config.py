"""Configuration for Google Scholar scraper."""
import random
from dataclasses import dataclass, field
from typing import Dict, List

from ...core.user_agent import build_browser_headers

SOURCE_NAME = "scholar"
BASE_URL = "https://scholar.google.com"
SCHOLAR_SEARCH_URL = f"{BASE_URL}/scholar"

# HTTP Headers - mimic real Chrome browser (critical for anti-bot)
DEFAULT_HEADERS = build_browser_headers()

# Search sort options
SEARCH_SORT: Dict[str, str] = {
    "relevance": "",       # Default - by relevance
    "date": "scisbd=1",    # Sort by date
}

# Search language options
SEARCH_LANGUAGES: Dict[str, str] = {
    "any": "",
    "en": "lang_en",
    "zh": "lang_zh-CN",
    "ja": "lang_ja",
    "de": "lang_de",
    "fr": "lang_fr",
    "es": "lang_es",
    "pt": "lang_pt",
    "ko": "lang_ko",
    "ru": "lang_ru",
}


@dataclass(frozen=True)
class ScholarSelectors:
    """CSS selectors for Google Scholar search results page."""

    result_item: str = "div.gs_r.gs_or.gs_scl"
    title_link: str = "h3.gs_rt a"
    title_text: str = "h3.gs_rt"
    authors_info: str = "div.gs_a"
    snippet: str = "div.gs_rs"
    bottom_links: str = "div.gs_fl"
    cited_by_link: str = 'a[href*="cites="]'
    pdf_link: str = "div.gs_or_ggsm a"
    next_page: str = 'button[aria-label="Next"]'
    captcha_form: str = "form#captcha-form"
    no_results: str = "div.gs_r div.gs_nma"


@dataclass(frozen=True)
class ArticleSelectors:
    """CSS selectors for generic publisher article pages."""

    article_tag: str = "article"
    main_tag: str = "main"
    content_classes: List[str] = field(default_factory=lambda: [
        ".article-content",
        ".fulltext",
        ".article-body",
        ".paper-content",
        ".content-body",
        "#article-body",
        ".abstract",
    ])
    meta_doi: str = 'meta[name="citation_doi"]'
    meta_author: str = 'meta[name="citation_author"]'
    meta_title: str = 'meta[name="citation_title"]'
    meta_date: str = 'meta[name="citation_publication_date"]'
    meta_journal: str = 'meta[name="citation_journal_title"]'
    meta_abstract: str = 'meta[name="citation_abstract"]'
    meta_description: str = 'meta[name="description"]'
    og_description: str = 'meta[property="og:description"]'


class Selectors:
    """Central selector registry."""

    scholar = ScholarSelectors()
    article = ArticleSelectors()


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for Scholar requests."""

    min_delay: float = 2.0
    max_delay: float = 5.0
    captcha_backoff: float = 30.0

    def random_delay(self) -> float:
        """Return a random delay between min and max."""
        return random.uniform(self.min_delay, self.max_delay)


RATE_LIMIT = RateLimitConfig()
