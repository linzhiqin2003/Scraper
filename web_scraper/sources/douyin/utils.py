"""Shared helpers for Douyin aweme IDs and canonical video URLs."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from .config import BASE_URL

_AWEME_ID_PATTERN = re.compile(r"\b(\d{15,20})\b")


def extract_aweme_id(value: str) -> Optional[str]:
    """Extract a Douyin aweme ID from a URL or a bare numeric ID."""
    parsed = urlparse(value)
    modal_id = parse_qs(parsed.query).get("modal_id")
    if modal_id and modal_id[0].isdigit():
        return modal_id[0]

    match = re.search(r"/video/(\d+)", value)
    if match:
        return match.group(1)

    match = _AWEME_ID_PATTERN.search(value)
    return match.group(1) if match else None


def build_video_url(aweme_id: str) -> str:
    """Build the canonical Douyin video page URL for an aweme."""
    return f"{BASE_URL}/video/{aweme_id}"


def normalize_video_target(value: str) -> tuple[Optional[str], Optional[str]]:
    """Return ``(aweme_id, canonical_url)`` for a URL or bare video ID."""
    aweme_id = extract_aweme_id(value)
    if not aweme_id:
        return None, None
    return aweme_id, build_video_url(aweme_id)
