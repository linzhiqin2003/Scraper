"""User-Agent pool and HTTP header generation.

Provides consistent UA profiles (UA string + matching Sec-Ch-Ua headers)
and unified header builders to replace per-source hardcoded DEFAULT_HEADERS.
"""

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class UAProfile:
    """A consistent browser identity: UA string + matching client hints."""

    user_agent: str
    sec_ch_ua: str  # Chrome-only; empty for Safari/Firefox
    sec_ch_ua_platform: str  # "macOS" / "Windows"
    sec_ch_ua_mobile: str  # "?0"
    platform: str  # navigator.platform for stealth scripts


_PROFILES: list[UAProfile] = [
    # Chrome 131 — macOS
    UAProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
        platform="MacIntel",
    ),
    # Chrome 131 — Windows
    UAProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        platform="Win32",
    ),
    # Safari 17 — macOS (no Sec-Ch-Ua headers)
    UAProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Safari/605.1.15"
        ),
        sec_ch_ua="",
        sec_ch_ua_platform='"macOS"',
        sec_ch_ua_mobile="?0",
        platform="MacIntel",
    ),
    # Firefox 121 — Windows (no Sec-Ch-Ua headers)
    UAProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        ),
        sec_ch_ua="",
        sec_ch_ua_platform='"Windows"',
        sec_ch_ua_mobile="?0",
        platform="Win32",
    ),
]


def get_random_profile() -> UAProfile:
    """Return a random UA profile."""
    return random.choice(_PROFILES)


def get_random_user_agent() -> str:
    """Return a random user-agent string. Backward-compatible with browser.py."""
    return get_random_profile().user_agent


def build_browser_headers(
    profile: UAProfile | None = None,
    accept_language: str = "en-US,en;q=0.9",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build headers that mimic a real browser navigating to a page.

    Replaces per-source DEFAULT_HEADERS dictionaries.

    Args:
        profile: Specific UA profile to use; None picks one at random.
        accept_language: Accept-Language header value.
        extra: Source-specific headers (Referer, Origin, Cache-Control, etc.).
    """
    if profile is None:
        profile = get_random_profile()

    headers: dict[str, str] = {
        "User-Agent": profile.user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    # Chrome profiles get Sec-Ch-Ua headers; Safari/Firefox do not
    if profile.sec_ch_ua:
        headers["Sec-Ch-Ua"] = profile.sec_ch_ua
        headers["Sec-Ch-Ua-Mobile"] = profile.sec_ch_ua_mobile
        headers["Sec-Ch-Ua-Platform"] = profile.sec_ch_ua_platform

    if extra:
        headers.update(extra)

    return headers


def build_api_headers(
    profile: UAProfile | None = None,
    accept_language: str = "en-US,en;q=0.9",
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build headers for XHR / fetch-style API requests (Accept: application/json).

    Args:
        profile: Specific UA profile to use; None picks one at random.
        accept_language: Accept-Language header value.
        extra: Source-specific headers (Referer, Origin, x-requested-with, etc.).
    """
    if profile is None:
        profile = get_random_profile()

    headers: dict[str, str] = {
        "User-Agent": profile.user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": accept_language,
        "Accept-Encoding": "gzip, deflate, br",
    }

    if profile.sec_ch_ua:
        headers["Sec-Ch-Ua"] = profile.sec_ch_ua
        headers["Sec-Ch-Ua-Mobile"] = profile.sec_ch_ua_mobile
        headers["Sec-Ch-Ua-Platform"] = profile.sec_ch_ua_platform

    if extra:
        headers.update(extra)

    return headers
