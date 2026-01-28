"""Configuration and selectors for Reuters scraper."""

from typing import Dict

# Source identifier
SOURCE_NAME = "reuters"

# URLs
BASE_URL = "https://www.reuters.com"
SIGN_IN_URL = f"{BASE_URL}/account/sign-in/"
SEARCH_URL = f"{BASE_URL}/site-search/"

# Valid search filter values (from Reuters search page)
VALID_SECTIONS = {
    "world",
    "business",
    "legal",
    "markets",
    "breakingviews",
    "technology",
    "sustainability",
    "science",
    "sports",
    "lifestyle",
}

VALID_DATE_RANGES = {
    "past_24_hours",
    "past_week",
    "past_month",
    "past_year",
}

# Sections - Reuters main categories and subcategories (verified 2026-01-28)
SECTIONS: Dict[str, Dict[str, str]] = {
    # World
    "world": {"name": "World", "url": "/world/"},
    "world/africa": {"name": "Africa", "url": "/world/africa/"},
    "world/americas": {"name": "Americas", "url": "/world/americas/"},
    "world/asia-pacific": {"name": "Asia Pacific", "url": "/world/asia-pacific/"},
    "world/china": {"name": "China", "url": "/world/china/"},
    "world/europe": {"name": "Europe", "url": "/world/europe/"},
    "world/india": {"name": "India", "url": "/world/india/"},
    "world/israel-hamas": {"name": "Israel and Hamas at War", "url": "/world/israel-hamas/"},
    "world/japan": {"name": "Japan", "url": "/world/japan/"},
    "world/middle-east": {"name": "Middle East", "url": "/world/middle-east/"},
    "world/ukraine-russia-war": {"name": "Ukraine and Russia at War", "url": "/world/ukraine-russia-war/"},
    "world/uk": {"name": "United Kingdom", "url": "/world/uk/"},
    "world/us": {"name": "United States", "url": "/world/us/"},
    "world/reuters-next": {"name": "Reuters NEXT New York", "url": "/world/reuters-next/"},
    # Business
    "business": {"name": "Business", "url": "/business/"},
    "business/aerospace-defense": {"name": "Aerospace & Defense", "url": "/business/aerospace-defense/"},
    "business/autos-transportation": {"name": "Autos & Transportation", "url": "/business/autos-transportation/"},
    "business/davos": {"name": "Davos", "url": "/business/davos/"},
    "business/energy": {"name": "Energy", "url": "/business/energy/"},
    "business/environment": {"name": "Environment", "url": "/business/environment/"},
    "business/finance": {"name": "Finance", "url": "/business/finance/"},
    "business/healthcare-pharmaceuticals": {"name": "Healthcare & Pharmaceuticals", "url": "/business/healthcare-pharmaceuticals/"},
    "business/media-telecom": {"name": "Media & Telecom", "url": "/business/media-telecom/"},
    "business/retail-consumer": {"name": "Retail & Consumer", "url": "/business/retail-consumer/"},
    "business/future-of-health": {"name": "Future of Health", "url": "/business/future-of-health/"},
    "business/future-of-money": {"name": "Future of Money", "url": "/business/future-of-money/"},
    "business/take-five": {"name": "Take Five", "url": "/business/take-five/"},
    "business/world-at-work": {"name": "World at Work", "url": "/business/world-at-work/"},
    # Markets
    "markets": {"name": "Markets", "url": "/markets/"},
    "markets/on-the-money": {"name": "On the Money", "url": "/markets/on-the-money/"},
    "markets/asia": {"name": "Asian Markets", "url": "/markets/asia/"},
    "markets/carbon": {"name": "Carbon Markets", "url": "/markets/carbon/"},
    "markets/commodities": {"name": "Commodities", "url": "/markets/commodities/"},
    "markets/currencies": {"name": "Currencies", "url": "/markets/currencies/"},
    "markets/deals": {"name": "Deals", "url": "/markets/deals/"},
    "markets/emerging": {"name": "Emerging Markets", "url": "/markets/emerging/"},
    "markets/etf": {"name": "ETFs", "url": "/markets/etf/"},
    "markets/europe": {"name": "European Markets", "url": "/markets/europe/"},
    "markets/funds": {"name": "Funds", "url": "/markets/funds/"},
    "markets/global-market-data": {"name": "Global Market Data", "url": "/markets/global-market-data/"},
    "markets/rates-bonds": {"name": "Rates & Bonds", "url": "/markets/rates-bonds/"},
    "markets/stocks": {"name": "Stocks", "url": "/markets/stocks/"},
    "markets/us": {"name": "U.S. Markets", "url": "/markets/us/"},
    "markets/wealth": {"name": "Wealth", "url": "/markets/wealth/"},
    "markets/econ-world": {"name": "Econ World", "url": "/markets/econ-world/"},
    # Sustainability
    "sustainability": {"name": "Sustainability", "url": "/sustainability/"},
    "sustainability/boards-policy-regulation": {"name": "Boards, Policy & Regulation", "url": "/sustainability/boards-policy-regulation/"},
    "sustainability/climate-energy": {"name": "Climate & Energy", "url": "/sustainability/climate-energy/"},
    "sustainability/land-use-biodiversity": {"name": "Land Use & Biodiversity", "url": "/sustainability/land-use-biodiversity/"},
    "sustainability/society-equity": {"name": "Society & Equity", "url": "/sustainability/society-equity/"},
    "sustainability/sustainable-finance-reporting": {"name": "Sustainable Finance & Reporting", "url": "/sustainability/sustainable-finance-reporting/"},
    "sustainability/the-switch": {"name": "The Switch", "url": "/sustainability/the-switch/"},
    "sustainability/reuters-impact": {"name": "Reuters Impact", "url": "/sustainability/reuters-impact/"},
    "sustainability/cop": {"name": "COP30", "url": "/sustainability/cop/"},
    # Legal
    "legal": {"name": "Legal", "url": "/legal/"},
    "legal/government": {"name": "Government", "url": "/legal/government/"},
    "legal/legalindustry": {"name": "Legal Industry", "url": "/legal/legalindustry/"},
    "legal/litigation": {"name": "Litigation", "url": "/legal/litigation/"},
    "legal/transactional": {"name": "Transactional", "url": "/legal/transactional/"},
    "legal/us-supreme-court": {"name": "US Supreme Court", "url": "/legal/us-supreme-court/"},
    # Commentary
    "commentary": {"name": "Commentary", "url": "/commentary/"},
    "commentary/breakingviews": {"name": "Breakingviews", "url": "/breakingviews/"},
    # Technology
    "technology": {"name": "Technology", "url": "/technology/"},
    "technology/artificial-intelligence": {"name": "Artificial Intelligence", "url": "/technology/artificial-intelligence/"},
    "technology/cybersecurity": {"name": "Cybersecurity", "url": "/technology/cybersecurity/"},
    "technology/space": {"name": "Space", "url": "/technology/space/"},
    "technology/disrupted": {"name": "Disrupted", "url": "/technology/disrupted/"},
    # Investigations
    "investigations": {"name": "Investigations", "url": "/investigations/"},
    # Sports
    "sports": {"name": "Sports", "url": "/sports/"},
    "sports/athletics": {"name": "Athletics", "url": "/sports/athletics/"},
    "sports/baseball": {"name": "Baseball", "url": "/sports/baseball/"},
    "sports/basketball": {"name": "Basketball", "url": "/sports/basketball/"},
    "sports/cricket": {"name": "Cricket", "url": "/sports/cricket/"},
    "sports/cycling": {"name": "Cycling", "url": "/sports/cycling/"},
    "sports/formula1": {"name": "Formula 1", "url": "/sports/formula1/"},
    "sports/golf": {"name": "Golf", "url": "/sports/golf/"},
    "sports/nfl": {"name": "NFL", "url": "/sports/nfl/"},
    "sports/nhl": {"name": "NHL", "url": "/sports/nhl/"},
    "sports/soccer": {"name": "Soccer", "url": "/sports/soccer/"},
    "sports/tennis": {"name": "Tennis", "url": "/sports/tennis/"},
    "sports/olympics": {"name": "Winter Olympics", "url": "/sports/olympics/"},
    # Science
    "science": {"name": "Science", "url": "/science/"},
    # Lifestyle
    "lifestyle": {"name": "Lifestyle", "url": "/lifestyle/"},
}


class Selectors:
    """CSS selectors for Reuters website elements."""

    # Login page - Step 1 (Email)
    EMAIL_INPUT = "input#email"
    NEXT_BUTTON = 'button:has-text("Next")'

    # Login page - Step 2 (Password)
    PASSWORD_INPUT = "input#password"
    SIGN_IN_BUTTON = 'button:has-text("Sign in")'

    # Login status detection (on homepage)
    SIGN_IN_LINK = 'a[href*="sign-in"]'

    # Alternative selectors (fallback)
    EMAIL_INPUT_ALT = 'input[name="email"]'
    PASSWORD_INPUT_ALT = 'input[name="password"]'


class Timeouts:
    """Timeout configurations."""

    DEFAULT = 30000
    NAVIGATION = 60000
    LOGIN_MANUAL = 300000  # 5 minutes for manual login if needed


class ScraperSelectors:
    """CSS selectors for scraping content."""

    # Search page
    SEARCH_RESULTS_CONTAINER = '[class*="search-results-module__list"]'
    SEARCH_RESULT_ITEM = '[class*="search-results-module__story"]'
    SEARCH_RESULT_TITLE = '[data-testid="Heading"] a, h3 a'
    SEARCH_RESULT_SUMMARY = '[data-testid="Body"]'
    SEARCH_RESULT_TIME = 'time, [data-testid="Label"]'
    SEARCH_LOAD_MORE = 'button[class*="load-more"], button:has-text("Load more")'
    SEARCH_NO_RESULTS = ':has-text("No results found")'

    # Article page (verified via HTML analysis 2026-01-28)
    ARTICLE_TITLE = 'h1[data-testid="Heading"]'
    ARTICLE_AUTHOR = '[data-testid="AuthorNameLink"], a[rel="author"]'
    ARTICLE_TIME = 'time[data-testid="DateLine"]'
    ARTICLE_BODY = '[data-testid="ArticleBody"]'
    ARTICLE_PARAGRAPH = '[class*="article-body-module__paragraph"]'
    ARTICLE_IMAGE = '[data-testid="ArticleBody"] img, [data-testid="Image"] img'
    ARTICLE_IMAGE_CAPTION = 'figcaption, [data-testid="Caption"]'
    ARTICLE_TAGS = '[class*="tags-line"] a[data-testid="TextButton"]'

    # Section page (verified 2026-01-28 via Playwright exploration)
    # Article items - two layout types
    SECTION_ARTICLE_ITEM = 'main li[class*="story-card-module"], main li[class*="four-section-module__list-item"]'
    # Title link - URLs contain date pattern like -2026-01-28
    SECTION_ARTICLE_TITLE = 'a[href*="-202"]'
    SECTION_ARTICLE_SUMMARY = 'p'
    SECTION_ARTICLE_TIME = 'time'
    SECTION_ARTICLE_THUMBNAIL = 'img[src*="cloudfront"]'
    # Load more button
    SECTION_LOAD_MORE = 'button:has-text("Load more")'
    # Category link (optional)
    SECTION_ARTICLE_CATEGORY = 'a[href$="/"]'

    # Rate limit / error detection
    RATE_LIMIT_TEXT = "安全限制|访问频次异常|rate limit|too many requests"
    PAYWALL_INDICATOR = '[data-testid="paywall"], .paywall-container'
