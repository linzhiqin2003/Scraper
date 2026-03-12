"""Configuration for the Sina news search scraper."""

from pathlib import Path

from ...core.user_agent import build_browser_headers

SOURCE_NAME = "sina"

DATA_DIR = Path.home() / ".web_scraper" / SOURCE_NAME
EXPORT_DIR = DATA_DIR / "exports"

BASE_URL = "https://search.sina.com.cn"
SEARCH_URL = f"{BASE_URL}/news"
DEFAULT_PAGE_SIZE = 10
DEFAULT_HEADERS = build_browser_headers(
    accept_language="zh-CN,zh;q=0.9,en;q=0.8",
    extra={"Referer": BASE_URL},
)

