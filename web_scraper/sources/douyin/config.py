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

# Data storage
DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME


class Timeouts:
    """Timeout configurations in milliseconds."""

    DEFAULT = 30_000
    NAVIGATION = 60_000
    LOGIN_MANUAL = 300_000
    COMMENT_LOAD = 3_000
    SCROLL_WAIT = 2_000
