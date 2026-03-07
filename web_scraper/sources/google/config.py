"""Configuration for Google Custom Search source."""
import os

SOURCE_NAME = "google"
GOOGLE_CSE_BASE_URL = "https://www.googleapis.com/customsearch/v1"

# Date restriction options (dateRestrict parameter)
DATE_RESTRICT = {
    "day": "d1",
    "week": "w1",
    "month": "m1",
    "year": "y1",
    "2days": "d2",
    "2weeks": "w2",
    "2months": "m2",
}

# Sort options
SORT_OPTIONS = {
    "relevance": "",      # Default
    "date": "date",       # Sort by date
}

# Search type options (searchType parameter)
SEARCH_TYPES = {
    "web": "",            # Default web search
    "image": "image",     # Image search
}

# Interface language options (hl parameter)
LANGUAGES = {
    "en": "en",
    "zh-cn": "zh-CN",
    "zh-tw": "zh-TW",
    "ja": "ja",
    "ko": "ko",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "pt": "pt",
    "ru": "ru",
}

# Safe search options
SAFE_SEARCH = {
    "off": "off",
    "medium": "medium",
    "high": "high",
}


def get_api_key() -> str:
    """Get Google CSE API key from environment."""
    return os.environ.get("GOOGLE_CSE_API_KEY", "")


def get_cx() -> str:
    """Get Google Custom Search Engine ID from environment."""
    return os.environ.get("GOOGLE_CSE_CX", "")


def is_configured() -> bool:
    """Check if both API key and CX are set."""
    return bool(get_api_key() and get_cx())
