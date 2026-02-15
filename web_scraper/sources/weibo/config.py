"""Configuration and selectors for Weibo scraper."""

from ...core.browser import DEFAULT_DATA_DIR
from ...core.user_agent import build_browser_headers

# Source identifier
SOURCE_NAME = "weibo"
DEFAULT_QUERY = "pony"

# URLs
BASE_URL = "https://weibo.com"
SEARCH_BASE_URL = "https://s.weibo.com/weibo"
SEARCH_URL = f"{SEARCH_BASE_URL}?q={DEFAULT_QUERY}"
HOT_SEARCH_URL = f"{BASE_URL}/hot/search"
HOT_SEARCH_API = f"{BASE_URL}/ajax/side/hotSearch"
DETAIL_FALLBACK_URL = f"{BASE_URL}/detail"
DETAIL_SHOW_API = f"{BASE_URL}/ajax/statuses/show"
DETAIL_COMMENTS_API = f"{BASE_URL}/ajax/statuses/buildComments"
LOGIN_URL = (
    "https://passport.weibo.com/sso/signin"
    "?entry=miniblog"
    "&source=miniblog"
    "&url=https%3A%2F%2Fs.weibo.com%2Fweibo%3Fq%3Dpony"
)

# Paths
DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME
STATE_FILE = DATA_DIR / "browser_state.json"

# HTTP headers for Weibo requests-first scraping.
DEFAULT_HEADERS = build_browser_headers(
    accept_language="zh-CN,zh;q=0.9,en;q=0.8",
    extra={
        "Referer": BASE_URL,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    },
)

RATE_LIMIT_KEYWORDS = (
    "访问频次过高",
    "访问过于频繁",
    "安全验证",
    "请输入验证码",
    "captcha",
    "verification required",
)

LOGGED_OUT_KEYWORDS = (
    "passport.weibo.com",
    "/visitor/visitor",
    "请先登录",
    "登录后查看更多",
    "open.weixin.qq.com/connect/qrconnect",
)


class Selectors:
    """CSS selectors for Weibo login flows."""

    # Tabs
    TAB_CODE_LOGIN = 'a:has-text("验证码登录")'
    TAB_ACCOUNT_LOGIN = 'a:has-text("账号登录")'

    # Code login
    COUNTRY_CODE_BUTTON = "#dropdownDefaultButton"
    PHONE_INPUT = 'input[placeholder="手机号"], input[aria-label="手机号"]'
    CODE_INPUT = 'input[placeholder="验证码"], input[aria-label="验证码"]'
    CODE_SUBMIT_BUTTON = 'button:has-text("登录/注册")'

    # Account login
    ACCOUNT_INPUT = 'input[placeholder="手机号或邮箱"], input[aria-label="手机号或邮箱"]'
    PASSWORD_INPUT = 'input[placeholder="密码"], input[aria-label="密码"]'
    ACCOUNT_SUBMIT_BUTTON = 'button:has-text("登录")'

    # Status checks
    LOGIN_FORM_INPUT = (
        'input[placeholder="手机号"], '
        'input[placeholder="验证码"], '
        'input[placeholder="手机号或邮箱"], '
        'input[placeholder="密码"]'
    )

    # Search page
    SEARCH_INPUT = 'input[placeholder="搜索微博"]'
    FEED_LIST_ROOT = "#pl_feedlist_index"
    FEED_CARD = "#pl_feedlist_index .card-wrap"
    FEED_CARD_FALLBACK = '.card-wrap[action-type="feed_list_item"]'
    FEED_USER = ".card-feed .name, .content .name"
    FEED_TIME = ".card-feed .from > a[href]"
    FEED_SOURCE = ".card-feed .from > a + a"
    FEED_TEXT = 'p[node-type="feed_list_content"]'
    FEED_TEXT_FULL = 'p[node-type="feed_list_content_full"]'
    FEED_ACTION = ".card-act ul li"
    NEXT_PAGE = 'a.next[href*="page="]'
    NO_RESULT = ".card-no-result"

    # Hot search page
    HOT_SEARCH_ROW = "main [data-index][data-active]"
    HOT_SEARCH_TOPIC_LINK = 'main [data-index][data-active] a[href*="/weibo?q="]'
    HOT_SEARCH_HEAT = 'main [data-index][data-active] div[class*="num"] span'
    HOT_SEARCH_BADGE = "main [data-index][data-active] .wbpro-icon-search-2"

    # Detail page
    DETAIL_ARTICLE = "main article"
    DETAIL_HEADER = "main article header"
    DETAIL_AUTHOR_NAME = 'main article header a[href*="/u/"] span[title]'
    DETAIL_AUTHOR_LINK = 'main article header a[href*="/u/"]'
    DETAIL_TIME = 'main article header a[href^="https://weibo.com/"]'
    DETAIL_REGION = 'main article header [title^="发布于 "]'
    DETAIL_SOURCE = 'main article header [title^="来自 "]'
    DETAIL_TEXT = 'main article .wbpro-feed-content div[class*="_wbtext_"]'
    DETAIL_IMAGES = "main article .wbpro-feed-content img"
    DETAIL_FOOTER = "main article footer[aria-label]"
    DETAIL_LIKE_COUNT = 'main article footer button[title="赞"] .woo-like-count'

    DETAIL_COMMENT_SCROLLER = "#scroller.vue-recycle-scroller"
    DETAIL_COMMENT_ITEM = "#scroller .wbpro-scroller-item .wbpro-list .item1"
    DETAIL_COMMENT_USER = '#scroller .wbpro-scroller-item .item1 .text > a[href*="/u/"]'
    DETAIL_COMMENT_TEXT = "#scroller .wbpro-scroller-item .item1 .text > span"
    DETAIL_COMMENT_META = "#scroller .wbpro-scroller-item .item1 .info > div:first-child"
    DETAIL_COMMENT_LIKE = '#scroller .wbpro-scroller-item .item1 button[title="赞"]'


class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30_000
    NAVIGATION = 60_000
    LOGIN_MANUAL = 300_000
