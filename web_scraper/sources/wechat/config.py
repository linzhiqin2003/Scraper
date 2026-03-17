"""Configuration for WeChat Official Accounts scraper."""
from dataclasses import dataclass
from pathlib import Path

from ...core.cookies import get_cookies_path, load_cookies

SOURCE_NAME = "wechat"
BASE_URL = "https://mp.weixin.qq.com"
COOKIES_FILE = get_cookies_path(SOURCE_NAME)

# Data directory
DATA_DIR = Path.home() / ".web_scraper" / SOURCE_NAME

# Login QR code
LOGIN_QR_SELECTOR = "img.login__type__container__scan__qrcode"
LOGIN_SUCCESS_INDICATOR = ".weui-desktop-account__nickname"  # Dashboard element after login
QR_IMAGE_PATH = DATA_DIR / "login_qrcode.png"

# MP platform API base
MP_API_BASE = "https://mp.weixin.qq.com/cgi-bin"

# Rate limiting: WeChat will block if too many requests
RATE_LIMIT_DELAY = 3.0  # seconds between requests
MAX_BATCH_SIZE = 20  # max articles per batch

# Required cookies for MP platform API
AUTH_COOKIE_NAMES = {"slave_sid", "bizuin", "data_ticket"}

# Default headers for MP platform API
MP_HEADERS = {
    "x-requested-with": "XMLHttpRequest",
    "referer": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1&type=10",
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class Selectors:
    """CSS selectors for WeChat MP articles."""

    # Article metadata
    TITLE = "#activity-name"
    ACCOUNT_NAME = "#js_name"
    PUBLISH_TIME = "#publish_time"
    CONTENT = "#js_content"
    META_CONTENT = "#meta_content"

    # OG meta tags (reliable fallback)
    OG_TITLE = 'meta[property="og:title"]'
    OG_DESCRIPTION = 'meta[property="og:description"]'
    OG_IMAGE = 'meta[property="og:image"]'
    OG_URL = 'meta[property="og:url"]'

    # Content elements
    IMAGES = "#js_content img"
    LINKS = "#js_content a"
    SECTIONS = "#js_content section"

    # Profile
    PROFILE_BT = "#profileBt"


@dataclass
class Timeouts:
    """Timeout configurations in seconds/milliseconds."""
    DEFAULT = 30
    NAVIGATION = 60_000  # ms
    LOGIN_MANUAL = 120_000  # ms — 2 minutes for QR scan


def get_cookies_from_file() -> dict[str, str]:
    """Load cookies as a plain dict via core.cookies."""
    return load_cookies(SOURCE_NAME)
