"""Configuration and selectors for Zhihu scraper."""

from ...core.browser import DEFAULT_DATA_DIR

# Source identifier
SOURCE_NAME = "zhihu"

# URLs
BASE_URL = "https://www.zhihu.com"
SEARCH_URL = f"{BASE_URL}/search"
LOGIN_URL = (
    "https://www.zhihu.com/signin"
    "?next=%2Fsearch%3Ftype%3Dcontent%26q%3Dtransformer"
)

# Paths
DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME
STATE_FILE = DATA_DIR / "browser_state.json"

# Default CDP port for connecting to user's real Chrome
DEFAULT_CDP_PORT = 9222

# API endpoints for direct access
SEARCH_API_URL = f"{BASE_URL}/api/v4/search_v3"
ANSWER_API_URL = f"{BASE_URL}/api/v4/answers"
ARTICLE_API_URL = f"{BASE_URL}/api/v4/articles"
QUESTION_API_URL = f"{BASE_URL}/api/v4/questions"

# Extraction strategy options
STRATEGY_AUTO = "auto"
STRATEGY_PURE_API = "pure_api"  # Pure Python API (no browser)
STRATEGY_API = "api"            # Browser-based API (CDP + SignatureOracle)
STRATEGY_INTERCEPT = "intercept"
STRATEGY_DOM = "dom"

# Search type mapping: display name -> URL type param
SEARCH_TYPES = {
    "综合": "content",
    "用户": "people",
    "论文": "scholar",
    "专栏": "column",
    "话题": "topic",
    "视频": "zvideo",
}


class Selectors:
    """CSS selectors for Zhihu pages."""

    # Login state detection
    LOGIN_ENTRY = (
        'button:has-text("登录/注册"), '
        'a:has-text("登录"), '
        'a:has-text("登录/注册")'
    )
    LOGIN_MODAL_HINT = (
        'text="验证码登录", '
        'text="密码登录", '
        'input[placeholder*="手机号"], '
        'input[placeholder*="短信验证码"]'
    )
    USER_AVATAR = (
        'img[class*="Avatar"], '
        'a[href*="/people/"], '
        '[data-za-module*="User"], '
        '[class*="AppHeader-profile"]'
    )

    # Search page
    SEARCH_INPUT = 'input[type="search"], input[aria-label="搜索"], #Popover1-toggle'
    SEARCH_BUTTON = 'button:has-text("搜索")'
    SEARCH_TABS = '.SearchTabs .SearchTabs-item, [class*="Tabs"] a'
    NO_RESULT = ':text("未搜索到相关内容")'

    # Search result cards
    RESULT_CARD = '.List-item .ContentItem, .SearchResult-Card'
    RESULT_CARD_FALLBACK = '.List-item'

    # Within a result card
    CARD_TITLE = 'h2 a, h2 span, [class*="ContentItem-title"] a'
    CARD_EXCERPT = '.RichContent-inner, .CopyrightRichTextContainer, [class*="RichText"]'
    CARD_AUTHOR = '.AuthorInfo .UserLink-link, [class*="AuthorInfo"] a'
    CARD_META = '.ContentItem-meta, .ContentItem-time'
    CARD_STATS = '.ContentItem-actions button, [class*="VoteButton"]'

    # Article/Answer detail page
    ARTICLE_TITLE = 'h1.Post-Title, h1[class*="QuestionHeader-title"], article h1'
    ARTICLE_CONTENT = '.Post-RichTextContainer, .RichContent-inner'
    ARTICLE_AUTHOR = '.AuthorInfo .UserLink-link'
    ARTICLE_TIME = 'time, .ContentItem-time'
    ARTICLE_TAGS = '.Tag-content'
    ANSWER_CONTENT = '.RichContent-inner'


class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30_000
    NAVIGATION = 60_000
    LOGIN_MANUAL = 300_000
    RESULT_LOAD = 10_000
    SCROLL_WAIT = 2_000
