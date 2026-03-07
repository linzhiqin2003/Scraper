"""Configuration for Serper search source."""
import os

SOURCE_NAME = "serper"
SERPER_BASE_URL = "https://google.serper.dev"

# Search type endpoints
SEARCH_TYPES = {
    "search": "/search",
    "news": "/news",
    "images": "/images",
}

# Time range options (Serper tbs parameter)
TIME_RANGES = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
    "year": "qdr:y",
    "hour": "qdr:h",
}

# Common country codes (gl parameter)
COUNTRIES = {
    "us": "us",
    "cn": "cn",
    "gb": "gb",
    "au": "au",
    "ca": "ca",
    "de": "de",
    "fr": "fr",
    "jp": "jp",
    "kr": "kr",
    "in": "in",
}

# Common language codes (hl parameter)
LANGUAGES = {
    "en": "en",
    "zh-cn": "zh-cn",
    "zh-tw": "zh-tw",
    "ja": "ja",
    "ko": "ko",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "pt": "pt",
    "ru": "ru",
}


def get_api_key() -> str:
    """Get Serper API key from environment."""
    return os.environ.get("SERPER_API_KEY", "")
