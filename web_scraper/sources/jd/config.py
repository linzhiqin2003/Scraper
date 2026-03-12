"""Configuration for JD (京东) scraper."""
from dataclasses import dataclass

from ...core.user_agent import build_browser_headers

SOURCE_NAME = "jd"
BASE_URL = "https://item.jd.com"
API_BASE_URL = "https://api.m.jd.com"
CDN_IMAGE_BASE = "https://img10.360buyimg.com"

# API function IDs and appids
API_ENDPOINTS = {
    "product_detail": {
        "appid": "pc-item-soa",
        "functionId": "pc_detailpage_wareBusiness",
        "path": "/",
    },
    "comments": {
        "appid": "item-v3",
        "functionId": "getLegoWareDetailComment",
        "path": "/api",
    },
    "recommendations": {
        "appid": "item-v3",
        "functionId": "pctradesoa_diviner",
        "path": "/api",
    },
    "graphic_detail": {
        "appid": "item-v3",
        "functionId": "pc_item_getWareGraphic",
        "path": "/",
    },
    "rel_search": {
        "appid": "item-v3",
        "functionId": "relsearch",
        "path": "/api",
    },
}

# Required cookies for authentication
REQUIRED_COOKIES = ["thor", "_pst", "token"]

# Important cookies to track
AUTH_COOKIES = [
    "thor",           # Login credential (encrypted, Secure)
    "_pst",           # User pin cache
    "token",          # Business token
    "3AB9D23F7A4B3CSS",  # EID Token
    "flash",          # Security token
]

DEVICE_COOKIES = [
    "shshshfpa",      # Device fingerprint
    "shshshfpb",      # Device fingerprint
    "shshshfpx",      # Device fingerprint
    "ipLoc-djd",      # Region code (province_city_county_town)
    "areaId",         # Province-level area ID
    "sdtoken",        # Anti-bot rolling token
]

# Stock state codes
STOCK_STATE = {
    "33": "in_stock",
    "34": "out_of_stock",
    "40": "available",
    "36": "pre_sale",
}

# HTTP Headers
DEFAULT_HEADERS = {
    **build_browser_headers(),
    "Referer": "https://item.jd.com/",
    "Origin": "https://item.jd.com",
}

# Playwright intercept URL patterns
INTERCEPT_PATTERNS = [
    "**/api.m.jd.com/**",
]

# Function IDs to intercept during page load
INTERCEPT_FUNCTION_IDS = {
    "pc_detailpage_wareBusiness",
    "getLegoWareDetailComment",
    "getCommentListPage",
    "pctradesoa_diviner",
    "pc_item_getWareGraphic",
    "relsearch",
    "pctradesoa_equityInfo",
    "checkChat",
}


@dataclass
class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30000
    NAVIGATION = 60000
    ELEMENT = 10000
    API_WAIT = 15000  # Wait for API responses after page load
