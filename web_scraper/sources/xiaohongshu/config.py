"""Configuration and constants for Xiaohongshu scraper."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from ...core.browser import DEFAULT_DATA_DIR

# Source identifier
SOURCE_NAME = "xiaohongshu"

# URLs
BASE_URL = "https://www.xiaohongshu.com"
EXPLORE_URL = f"{BASE_URL}/explore"
SEARCH_URL = f"{BASE_URL}/search_result"
USER_URL = f"{BASE_URL}/user/profile"

# Data directories
DATA_DIR = DEFAULT_DATA_DIR / SOURCE_NAME
COOKIE_PATH = DATA_DIR / "cookies.json"
EXPORT_DIR = DATA_DIR / "exports"

# Category to channel_id mapping
CATEGORY_CHANNELS: Dict[str, str] = {
    "推荐": "homefeed_recommend",
    "穿搭": "homefeed.fashion_v3",
    "美食": "homefeed.food_v3",
    "彩妆": "homefeed.cosmetics_v3",
    "影视": "homefeed.movie_and_tv_v3",
    "职场": "homefeed.career_v3",
    "情感": "homefeed.love_v3",
    "家居": "homefeed.household_product_v3",
    "游戏": "homefeed.gaming_v3",
    "旅行": "homefeed.travel_v3",
    "健身": "homefeed.fitness_v3",
}

# Search type to URL parameter mapping
SEARCH_TYPES: Dict[str, str] = {
    "all": "51",
    "notes": "51",
    "video": "52",
    "image": "54",
    "user": "55",
}


@dataclass
class ScraperConfig:
    """Configuration for scraper behavior."""

    # Timeouts (milliseconds)
    default_timeout: int = 30000
    navigation_timeout: int = 60000

    # Scrolling
    max_scroll_attempts: int = 50
    scroll_delay: float = 1.5

    # Rate limiting
    min_delay: float = 1.0
    max_delay: float = 3.0

    # Retry
    max_retries: int = 3
    retry_delay: float = 5.0


# Default config instance
Config = ScraperConfig()


class Selectors:
    """CSS selectors for Xiaohongshu website elements."""

    # Login
    LOGIN_BUTTON = 'button:has-text("登录")'
    LOGIN_MODAL = 'text=登录后推荐更懂你的笔记'
    QR_CODE_TEXT = 'text=小红书如何扫码'
    PHONE_LOGIN_TEXT = 'text=手机号登录'
    PHONE_INPUT = 'input[placeholder="输入手机号"]'
    CODE_INPUT = 'input[type="number"], spinbutton'
    GET_CODE_BUTTON = 'text=获取验证码'

    # Notes
    NOTE_ITEM = 'section.note-item'
    NOTE_LINK = 'a[href*="/explore/"][href*="xsec_token"]'
    NOTE_COVER = 'a.cover img, img'
    NOTE_TITLE = 'a.title, .title'
    NOTE_FOOTER = '.footer'

    # Author
    AUTHOR_WRAPPER = '.author-wrapper'
    AUTHOR_LINK = 'a[href*="/user/profile/"]'
    AUTHOR_AVATAR = 'img'
    AUTHOR_NAME = 'span.name'
    AUTHOR_CONTAINER = '.author-container, .author-wrapper'

    # Stats
    LIKE_WRAPPER = '.like-wrapper .count, span.count'

    # Note detail
    NOTE_TITLE_DETAIL = '#detail-title, .note-content .title'
    NOTE_CONTENT = '#detail-desc .note-text, .note-text, .desc'
    NOTE_IMAGES = '[class*="swiper"] img, [class*="carousel"] img, [class*="slide"] img'
    NOTE_VIDEO = 'video source, video'
    NOTE_TAGS = 'a.tag, a[id="hash-tag"], a[href*="/search_result?keyword"]'
    NOTE_TIME = '[class*="time"], [class*="date"]'
    NOTE_ERROR = 'text=当前笔记暂时无法浏览'

    # Comments
    COMMENTS_CONTAINER = '#comments'
    COMMENT_ITEM = '.comment-item, [class*="comment"]'

    # Captcha/Login detection
    CAPTCHA_SLIDER = '.slider, [class*="captcha"], [class*="verification"]'
    LOGIN_REQUIRED = 'text=登录后查看'
