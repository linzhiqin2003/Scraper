"""Configuration for Ctrip scraper."""

import functools
import logging
import re
import time

SOURCE_NAME = "ctrip"
BASE_URL = "https://www.ctrip.com"
API_BASE = "https://m.ctrip.com/restapi/soa2"
HOTEL_LIST_URL = "https://hotels.ctrip.com/hotels/list"
HOTEL_DETAIL_URL = "https://hotels.ctrip.com/hotels/detail/"
FLIGHT_LIST_URL = "https://flights.ctrip.com/online/list"
FLIGHT_LOWEST_PRICE_URL = f"{API_BASE}/15380/bjjson/FlightIntlAndInlandLowestPriceSearch"

# SOA2 service endpoints
MEMBER_SUMMARY_URL = f"{API_BASE}/15201/getMemberSummaryInfo"
AVAILABLE_POINTS_URL = f"{API_BASE}/10182/GetAvailablePoints"
MESSAGE_COUNT_URL = f"{API_BASE}/10612/GetMessageCount"

# Hotel API endpoints (soa2/34951)
HOTEL_SEARCH_URL = f"{API_BASE}/34951/fetchHotelList"
HOTEL_FILTER_URL = f"{API_BASE}/34951/getHotelCommonFilter"
HOTEL_AD_URL = f"{API_BASE}/34951/getAdHotels"
HOTEL_BROWSE_URL = f"{API_BASE}/34951/fetchBrowseRecords"
HOTEL_CITY_URL = f"{API_BASE}/34951/getCityList"

# Sort filter mapping (type 17)
SORT_FILTERS = {
    "popular":    {"filterId": "17|1",  "type": "17", "value": "1",  "subType": "2"},
    "smart":      {"filterId": "17|9",  "type": "17", "value": "9",  "subType": "2"},
    "score":      {"filterId": "17|6",  "type": "17", "value": "6",  "subType": "2"},
    "price_asc":  {"filterId": "17|3",  "type": "17", "value": "3",  "subType": "2"},
    "price_desc": {"filterId": "17|4",  "type": "17", "value": "4",  "subType": "2"},
    "distance":   {"filterId": "17|5",  "type": "17", "value": "5",  "subType": "2"},
    "star":       {"filterId": "17|14", "type": "17", "value": "14", "subType": "2"},
}

# Star filter mapping (type 16)
STAR_FILTERS = {
    2: {"filterId": "16|2", "type": "16", "value": "2", "subType": "2"},
    3: {"filterId": "16|3", "type": "16", "value": "3", "subType": "2"},
    4: {"filterId": "16|4", "type": "16", "value": "4", "subType": "2"},
    5: {"filterId": "16|5", "type": "16", "value": "5", "subType": "2"},
}

# Price range filter mapping (type 15)
PRICE_RANGE_FILTERS = {
    (0, 150):    {"filterId": "15|1", "type": "15", "value": "0|150",    "subType": "2"},
    (150, 300):  {"filterId": "15|2", "type": "15", "value": "150|300",  "subType": "2"},
    (300, 450):  {"filterId": "15|3", "type": "15", "value": "300|450",  "subType": "2"},
    (450, 600):  {"filterId": "15|4", "type": "15", "value": "450|600",  "subType": "2"},
    (600, 1000): {"filterId": "15|5", "type": "15", "value": "600|1000", "subType": "2"},
}

# Brand filter mapping (type 4) — common hotel chains
BRAND_FILTERS: dict[str, dict] = {
    "如家":     {"filterId": "4|2",   "type": "4", "value": "2",   "subType": "2"},
    "汉庭":     {"filterId": "4|3",   "type": "4", "value": "3",   "subType": "2"},
    "7天":      {"filterId": "4|4",   "type": "4", "value": "4",   "subType": "2"},
    "全季":     {"filterId": "4|5",   "type": "4", "value": "5",   "subType": "2"},
    "亚朵":     {"filterId": "4|11",  "type": "4", "value": "11",  "subType": "2"},
    "锦江之星": {"filterId": "4|6",   "type": "4", "value": "6",   "subType": "2"},
    "维也纳":   {"filterId": "4|8",   "type": "4", "value": "8",   "subType": "2"},
    "希尔顿":   {"filterId": "4|15",  "type": "4", "value": "15",  "subType": "2"},
    "万豪":     {"filterId": "4|16",  "type": "4", "value": "16",  "subType": "2"},
    "洲际":     {"filterId": "4|17",  "type": "4", "value": "17",  "subType": "2"},
    "香格里拉": {"filterId": "4|18",  "type": "4", "value": "18",  "subType": "2"},
    "喜来登":   {"filterId": "4|19",  "type": "4", "value": "19",  "subType": "2"},
    "凯悦":     {"filterId": "4|20",  "type": "4", "value": "20",  "subType": "2"},
    "华住":     {"filterId": "4|21",  "type": "4", "value": "21",  "subType": "2"},
    "首旅":     {"filterId": "4|22",  "type": "4", "value": "22",  "subType": "2"},
}

# Authentication cookies required for user center
AUTH_COOKIES = ["cticket", "login_uid", "_udl"]

# Common city name → (cityId, countryId, cityEnName)
CITY_MAP: dict[str, tuple[int, int, str]] = {
    "上海": (2, 1, "Shanghai"),
    "北京": (1, 1, "Beijing"),
    "广州": (7, 1, "Guangzhou"),
    "深圳": (6, 1, "Shenzhen"),
    "成都": (28, 1, "Chengdu"),
    "杭州": (14, 1, "Hangzhou"),
    "西安": (32, 1, "Xian"),
    "重庆": (71, 1, "Chongqing"),
    "南京": (9, 1, "Nanjing"),
    "武汉": (49, 1, "Wuhan"),
    "厦门": (36, 1, "Xiamen"),
    "青岛": (26, 1, "Qingdao"),
    "三亚": (43, 1, "Sanya"),
    "丽江": (266, 1, "Lijiang"),
    "大理": (1271, 1, "Dali"),
    "张家界": (590, 1, "Zhangjiajie"),
    "桂林": (133, 1, "Guilin"),
    "黄山": (193, 1, "Huangshan"),
    "乌鲁木齐": (104, 1, "Urumqi"),
    "哈尔滨": (57, 1, "Harbin"),
}

# Member grade mapping
GRADE_MAP = {
    "1": "普通会员",
    "2": "银卡会员",
    "3": "金卡会员",
    "4": "铂金会员",
    "5": "钻石会员",
    "10": "黄金贵宾",
    "11": "铂金贵宾",
    "12": "钻石贵宾",
}

DEFAULT_HEADERS = {
    "content-type": "application/json",
    "cookieorigin": "https://www.ctrip.com",
    "origin": "https://www.ctrip.com",
    "referer": "https://www.ctrip.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

# Common flight city name/code mapping used by the PC result page.
FLIGHT_CITY_CODE_MAP: dict[str, str] = {
    "上海": "SHA",
    "北京": "BJS",
    "广州": "CAN",
    "深圳": "SZX",
    "成都": "CTU",
    "杭州": "HGH",
    "西安": "SIA",
    "重庆": "CKG",
    "南京": "NKG",
    "武汉": "WUH",
    "厦门": "XMN",
    "青岛": "TAO",
    "三亚": "SYX",
    "丽江": "LJG",
    "大理": "DLI",
    "张家界": "DYG",
    "桂林": "KWL",
    "黄山": "TXN",
    "乌鲁木齐": "URC",
    "哈尔滨": "HRB",
    "天津": "TSN",
    "长沙": "CSX",
    "昆明": "KMG",
    "福州": "FOC",
    "沈阳": "SHE",
    "郑州": "CGO",
    "大连": "DLC",
    "长春": "CGQ",
    "贵阳": "KWE",
    "太原": "TYN",
    "合肥": "HFE",
    "呼和浩特": "HET",
    "济南": "TNA",
    "烟台": "YNT",
    "南昌": "KHN",
    "常州": "CZX",
}

FLIGHT_CODE_NAME_MAP: dict[str, str] = {code: name for name, code in FLIGHT_CITY_CODE_MAP.items()}

FLIGHT_DEFAULT_HEADERS = {
    "accept": "application/json",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://flights.ctrip.com",
    "referer": "https://flights.ctrip.com/",
    "user-agent": DEFAULT_HEADERS["user-agent"],
}


class HotelSelectors:
    """CSS selectors for hotel search page (client-side rendered React)."""
    CARD = "div.list-item .hotel-card"          # one hotel card
    NAME = ".hotelName"
    SCORE = ".comment-score .score"
    SCORE_DESC = ".comment-desc"
    COMMENT_NUM = ".comment-num"
    ADDRESS = ".position-desc"
    ROOM_NAME = ".room-name"
    PRICE = ".price-line .sale"
    PRICE_SUFFIX = ".price-suffix"
    PROMOTION = ".promotion-tag"
    FREE_CANCEL = ".room-advantageTag .hotel-tag-content"
    AD_MARK = ".ad-info"


class FlightSelectors:
    """DOM selectors for the PC flight result page."""

    CARD = ".flight-item.domestic"
    NO_RESULT_TEXT = "未找到符合条件的航班"
    CARD_CONTAINER = ".flight-list.root-flights"


def hotel_head(guid: str = "", checkin: str = "", checkout: str = "") -> dict:
    """Build hotel-specific HBU head structure."""
    return {
        "platform": "PC",
        "cver": "0",
        "cid": guid or "1772835467381.0cdacRLVlR3w",
        "bu": "HBU",
        "group": "ctrip",
        "aid": "4899",
        "sid": "135371",
        "locale": "zh-CN",
        "timezone": "0",
        "currency": "CNY",
        "pageId": "10650171192",
        "vid": guid or "1772835467381.0cdacRLVlR3w",
        "isSSR": False,
        "extension": [
            {"name": "checkIn", "value": checkin},
            {"name": "checkOut", "value": checkout},
            {"name": "region", "value": "CN"},
        ],
    }


def soa2_head(guid: str = "") -> dict:
    """Build standard SOA2 request head."""
    return {
        "cid": guid or "09031099415419114348",
        "ctok": "",
        "cver": "1.0",
        "lang": "01",
        "sid": "8888",
        "syscode": "09",
        "auth": "",
        "xsid": "",
        "extension": [],
    }


def normalize_flight_city(city: str) -> tuple[str, str]:
    """Normalize a flight city input to (code, display_name)."""
    value = city.strip()
    if not value:
        raise ValueError("城市不能为空")

    match = re.search(r"\(([A-Za-z]{3})\)", value)
    if match:
        code = match.group(1).upper()
        return code, FLIGHT_CODE_NAME_MAP.get(code, code)

    if re.fullmatch(r"[A-Za-z]{3}", value):
        code = value.upper()
        return code, FLIGHT_CODE_NAME_MAP.get(code, code)

    code = FLIGHT_CITY_CODE_MAP.get(value)
    if code:
        return code, value

    raise ValueError(
        f"暂不支持的机票城市：{city}。"
        f"支持示例：{', '.join(list(FLIGHT_CITY_CODE_MAP.keys())[:10])}，"
        "或直接传三字码如 SHA/BJS。"
    )


_logger = logging.getLogger(__name__)

# Ctrip-specific rate limiter config (conservative)
CTRIP_RATE_LIMIT = {
    "min_delay": 1.0,
    "max_delay": 3.0,
    "requests_per_minute": 20,
    "requests_per_hour": 300,
    "backoff_base": 3.0,
    "backoff_max": 30.0,
    "jitter_range": 1.0,
}


def retry_on_error(max_retries: int = 2, retry_delay: float = 2.0):
    """Decorator that retries on transient errors (network, timeout, rate limit).

    Does NOT retry on ValueError or other programming errors.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (ValueError, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        wait = retry_delay * (2 ** attempt)
                        _logger.warning(
                            "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                            attempt + 1, max_retries + 1, func.__name__, exc, wait,
                        )
                        time.sleep(wait)
                    else:
                        raise
            raise last_exc  # unreachable but makes type checker happy
        return wrapper
    return decorator
