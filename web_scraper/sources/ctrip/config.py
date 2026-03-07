"""Configuration for Ctrip scraper."""

SOURCE_NAME = "ctrip"
BASE_URL = "https://www.ctrip.com"
API_BASE = "https://m.ctrip.com/restapi/soa2"
HOTEL_LIST_URL = "https://hotels.ctrip.com/hotels/list"
HOTEL_DETAIL_URL = "https://hotels.ctrip.com/hotels/detail/"

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
