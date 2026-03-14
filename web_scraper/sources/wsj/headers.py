"""Persisted HTTP header profile for WSJ requests."""

from __future__ import annotations

import json
from pathlib import Path

from ...core.user_agent import build_browser_headers


def get_headers_path() -> Path:
    """Return the path storing WSJ browser header metadata."""
    return Path.home() / ".web_scraper" / "wsj" / "headers.json"


def save_browser_profile(profile: dict) -> Path:
    """Persist browser metadata gathered during login."""
    path = get_headers_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_browser_profile() -> dict | None:
    """Load the last saved browser metadata, if any."""
    path = get_headers_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _format_sec_ch_ua(brands: list[dict]) -> str:
    parts = []
    for item in brands:
        brand = item.get("brand")
        version = item.get("version")
        if not brand or not version:
            continue
        parts.append(f'"{brand}";v="{version}"')
    return ", ".join(parts)


def build_wsj_headers() -> dict[str, str]:
    """Build stable WSJ request headers, preferring the saved browser profile."""
    profile = load_browser_profile()
    if not profile:
        return build_browser_headers()

    language = profile.get("language") or "en-US"
    if "," not in language:
        language = f"{language},en;q=0.9"

    headers = {
        "User-Agent": profile.get("userAgent") or build_browser_headers()["User-Agent"],
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": language,
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    brands = profile.get("brands")
    if isinstance(brands, list):
        sec_ch_ua = _format_sec_ch_ua(brands)
        if sec_ch_ua:
            headers["Sec-Ch-Ua"] = sec_ch_ua
            headers["Sec-Ch-Ua-Mobile"] = "?0"

    platform = profile.get("platform")
    if platform:
        headers["Sec-Ch-Ua-Platform"] = f'"{platform}"'

    return headers
