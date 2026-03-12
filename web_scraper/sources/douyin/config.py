"""Configuration for Douyin scraper."""

from ...core.browser import DEFAULT_DATA_DIR

SOURCE_NAME = "douyin"

# URLs
BASE_URL = "https://www.douyin.com"
LOGIN_URL = f"{BASE_URL}/login"
HOME_URL = BASE_URL

# API path fragments used for response interception
COMMENT_API_PATH = "aweme/v1/web/comment/list/"
COMMENT_REPLY_API_PATH = "aweme/v1/web/comment/list/reply/"
FEED_API_PATH = "aweme/v2/web/module/feed/"
USER_PROFILE_API_PATH = "aweme/v1/web/user/profile/other/"
USER_POST_API_PATH = "aweme/v1/web/aweme/post/"
USER_FAVORITE_API_PATH = "aweme/v1/web/aweme/favorite/"

# Data storage
DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME


class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30_000
    NAVIGATION = 60_000
    LOGIN_MANUAL = 300_000
    COMMENT_LOAD = 3_000
    SCROLL_WAIT = 2_000
    VIDEO_LOAD = 8_000
    CAPTCHA_MANUAL = 120_000  # Max wait for manual CAPTCHA solve
    CAPTCHA_CHECK_INTERVAL = 1_000  # Polling interval during CAPTCHA wait


# CAPTCHA detection selectors and URL patterns (ByteDance verify service)
CAPTCHA_URL_PATTERNS = [
    "verify.zijieapi.com",
    "captcha.bytedance.com",
]

CAPTCHA_DOM_SELECTORS = [
    # ByteDance slider CAPTCHA overlay
    '[class*="captcha"]',
    '[class*="verify-bar"]',
    '[class*="secsdk-captcha"]',
    '#captcha_container',
    '#secsdk-captcha-drag-wrapper',
    'div[id*="captcha"]',
    # Iframe-based CAPTCHA
    'iframe[src*="verify"]',
    'iframe[src*="captcha"]',
]

# Text patterns that indicate a CAPTCHA challenge
CAPTCHA_TEXT_PATTERNS = [
    "验证码",
    "请完成验证",
    "滑动滑块",
    "按住左边按钮",
    "拖动滑块",
    "安全验证",
    "请通过安全验证",
]
