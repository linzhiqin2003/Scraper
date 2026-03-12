"""Configuration and constants for Dianping scraper."""
from urllib.parse import quote

from ...core.browser import DEFAULT_DATA_DIR

SOURCE_NAME = "dianping"

WWW_BASE_URL = "https://www.dianping.com"
MOBILE_BASE_URL = "https://m.dianping.com"
MAPI_BASE_URL = "https://mapi.dianping.com"
VERIFY_BASE_URL = "https://verify.meituan.com"

DP_HOME_URL = f"{MOBILE_BASE_URL}/dphome"

GROWTH_QUERY_INDEX_URL = f"{MAPI_BASE_URL}/mapi/mgw/growthqueryindex"
GROWTH_USER_INFO_URL = f"{MAPI_BASE_URL}/mapi/mgw/growthuserinfo"
GROWTH_LIST_FEEDS_URL = f"{MAPI_BASE_URL}/mapi/mgw/growthlistfeeds"
NOTE_RECOMMEND_URL = f"{MAPI_BASE_URL}/mapi/friendship/recfeeds.bin"

DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME
COOKIE_PATH = DATA_DIR / "cookies.txt"
EXPORT_DIR = DATA_DIR / "exports"

DEFAULT_CITY_ID = 1
DEFAULT_SOURCE_ID = 1
DEFAULT_PAGE_SIZE = 10
DEFAULT_TIMEOUT = 20.0
LOGIN_TIMEOUT_SECONDS = 300

AUTH_COOKIE_NAMES = {
    "dper",
    "dplet",
    "ctu",
    "logan_session_token",
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

JSON_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
}


def build_home_feed_payload(
    page_start: int,
    page_size: int,
    city_id: int,
    lx_cuid: str,
    source_id: int = DEFAULT_SOURCE_ID,
) -> dict:
    """Build request body for the home feed API."""
    return {
        "cityId": city_id,
        "pageStart": page_start,
        "pageSize": page_size,
        "sourceId": source_id,
        "lxCuid": lx_cuid,
        "awakeAppHandler": "awakeAppHandler",
        "envParam": {
            "os": "ios",
            "locCityId": city_id,
            "latitude": 0,
            "longitude": 0,
        },
    }


def build_search_url(
    query: str,
    city_id: int = DEFAULT_CITY_ID,
    channel: int = 0,
    page: int = 1,
) -> str:
    """Build a Dianping search URL."""
    encoded_query = quote(query)
    url = f"{WWW_BASE_URL}/search/keyword/{city_id}/{channel}_{encoded_query}"
    if page > 1:
        url += f"/p{page}"
    return url
