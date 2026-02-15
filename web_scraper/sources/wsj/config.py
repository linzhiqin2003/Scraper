"""Configuration for WSJ scraper."""
from dataclasses import dataclass
from typing import Dict

from ...core.user_agent import build_browser_headers

SOURCE_NAME = "wsj"
BASE_URL = "https://www.wsj.com"
LOGIN_URL = f"{BASE_URL}/client/login"
SEARCH_URL = f"{BASE_URL}/search"

# RSS Feeds
FEEDS: Dict[str, str] = {
    "world": "https://feeds.a.dj.com/rss/RSSWorldNews.xml",
    "markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "technology": "https://feeds.a.dj.com/rss/RSSWSJD.xml",
    "business": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml",
    "opinion": "https://feeds.a.dj.com/rss/RSSOpinion.xml",
    "lifestyle": "https://feeds.a.dj.com/rss/RSSLifestyle.xml",
}

# Search filter options
SEARCH_SORT: Dict[str, str] = {
    "newest": "desc",      # Newest to Oldest
    "oldest": "asc",       # Oldest to Newest
    "relevance": "relevance",  # Relevance
}

SEARCH_DATE_RANGE: Dict[str, str] = {
    "day": "1d",           # Past Day
    "week": "7d",          # Past Week
    "month": "30d",        # Past Month
    "year": "1yr",         # Past Year
    "all": "all",          # All Time (default)
}

SEARCH_SOURCES: Dict[str, str] = {
    "articles": "wsj",           # WSJ Articles
    "video": "video",            # Videos
    "audio": "audio",            # Podcasts
    "livecoverage": "livecoverage",  # Live Coverage
    "buyside": "buyside",        # Buy Side
}

# HTTP Headers for requests
DEFAULT_HEADERS = build_browser_headers()


@dataclass(frozen=True)
class SearchPageSelectors:
    """Selectors for WSJ search results page."""

    search_box: str = 'input[type="search"], [role="searchbox"]'
    results_heading: str = 'h2:has-text("Search Results")'
    article_link: str = 'a[data-testid="flexcard-headline"][href*="mod=Searchresults"]'
    article_link_fallback: str = 'a[href*="mod=Searchresults"]'
    next_page: str = 'a:has-text("NEXT")'
    cookie_accept: str = 'button:has-text("YES, I AGREE")'


@dataclass(frozen=True)
class ArticlePageSelectors:
    """Selectors for WSJ article detail page."""

    title: str = "h1"
    subtitle: str = "h2"
    breadcrumb: str = 'nav[aria-label*="breadcrumb"] a'
    author_link: str = 'a[href*="/news/author/"]'
    time_element: str = "time"
    article_body: str = "article"
    paragraphs: str = "article p"
    featured_image: str = "article figure img"
    paywall_subscribe_button: str = 'button:has-text("Subscribe Now")'


@dataclass(frozen=True)
class LoginSelectors:
    """Selectors for WSJ login page."""

    email_input: str = 'input[name="username"], input[type="email"]'
    password_input: str = 'input[name="password"], input[type="password"]'
    continue_button: str = 'button:has-text("Continue"), button:has-text("Next")'
    sign_in_button: str = 'button:has-text("Sign In"), button[type="submit"]'
    sign_in_header_link: str = 'header a:has-text("Sign In")'


class Selectors:
    """Central selector registry."""

    search = SearchPageSelectors()
    article = ArticlePageSelectors()
    login = LoginSelectors()


@dataclass
class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30000
    NAVIGATION = 60000
    ELEMENT = 10000
    LOGIN = 300000  # 5 minutes for interactive login
