"""Browser-based fallback fetchers for WSJ protected pages."""

from __future__ import annotations

import time
from pathlib import Path

from ...core.browser import ensure_display
from ...core.cookies import load_cookies_playwright
from .auth import (
    _dismiss_consent_dialog,
    _dismiss_cookie_banner,
    _find_captcha_frame,
    _solve_slider_captcha,
)
from .config import SOURCE_NAME
from .headers import load_browser_profile


def _page_looks_blocked(html: str) -> bool:
    lowered = html.lower()
    return (
        "captcha-delivery.com" in lowered
        or "geo.captcha-delivery.com" in lowered
        or "please enable " in lowered
        or "var dd={" in lowered
    )


def fetch_html(url: str, cookies_path: Path | None = None, *, headless: bool = False) -> str:
    """Fetch a WSJ page through Patchright using saved cookies."""
    if not headless and ensure_display(headless=False):
        headless = True

    try:
        from patchright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError("patchright not installed") from e

    profile = load_browser_profile() or {}
    user_agent = profile.get("userAgent")
    locale = profile.get("language") or "en-US"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            channel="chrome",
            args=[
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--disable-infobars",
                "--window-size=1920,1080",
                *([] if not headless else ["--headless=new"]),
            ],
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=user_agent,
            locale=locale,
            timezone_id="America/New_York",
        )

        cookies = load_cookies_playwright(SOURCE_NAME, cookies_path)
        if cookies:
            context.add_cookies(cookies)

        page = context.new_page()
        try:
            # Warm the WSJ origin first so DataDome/session cookies settle on the root domain.
            page.goto("https://www.wsj.com", timeout=60000, wait_until="domcontentloaded")
            time.sleep(2)
            if _find_captcha_frame(page):
                _solve_slider_captcha(page, timeout=15.0, max_attempts=3)
            _dismiss_consent_dialog(page)
            _dismiss_cookie_banner(page)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(2)

            for _ in range(2):
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(2)
                if _find_captcha_frame(page):
                    _solve_slider_captcha(page, timeout=15.0, max_attempts=3)
                _dismiss_consent_dialog(page)
                _dismiss_cookie_banner(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)
                html = page.content()
                if not _page_looks_blocked(html):
                    return html

            return page.content()
        finally:
            browser.close()
