"""Douyin video downloader using browser-backed page extraction."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import requests
from playwright.sync_api import sync_playwright

from ....core.browser import STEALTH_SCRIPT, get_data_dir, get_state_path
from ..config import BASE_URL, SOURCE_NAME, Timeouts
from ..models import DouyinVideoDownloadResponse, DouyinVideoInfo
from ..utils import normalize_video_target


class VideoDownloadError(Exception):
    """Raised when a Douyin video cannot be resolved or downloaded."""

def choose_best_video_url(info: DouyinVideoInfo) -> Optional[str]:
    """Pick the preferred downloadable video URL."""
    for candidates in (info.play_urls, info.download_urls):
        for candidate in candidates:
            if candidate:
                return candidate
    return None


def extract_video_info_from_html(html: str, aweme_id: str) -> Optional[DouyinVideoInfo]:
    """Extract embedded video metadata from page HTML."""
    normalized_html = html.replace('\\"', '"')
    marker = f'"awemeId":"{aweme_id}"'
    start = normalized_html.find(marker)
    if start != -1:
        segment = normalized_html[start: start + 200_000]
    else:
        fallback_start = normalized_html.find('"video":{"width"')
        if fallback_start == -1:
            return None
        segment = normalized_html[fallback_start: fallback_start + 200_000]

    def _decode(value: str) -> str:
        try:
            return json.loads(f'"{value}"')
        except Exception:
            return value.replace("\\u0026", "&").replace("\\u002F", "/").replace('\\"', '"')

    def _extract_string(pattern: str) -> Optional[str]:
        match = re.search(pattern, segment, re.S)
        return _decode(match.group(1)) if match else None

    def _extract_int(pattern: str) -> Optional[int]:
        match = re.search(pattern, segment)
        return int(match.group(1)) if match else None

    def _extract_urls(key: str) -> list[str]:
        patterns = [
            rf'"{key}":\[(.*?)\],"{key}Size"',
            rf'"{key}":\[(.*?)\](?=,"[A-Za-z])',
        ]
        for pattern in patterns:
            match = re.search(pattern, segment, re.S)
            if not match:
                continue
            urls = [
                _decode(item)
                for item in re.findall(r'"src":"((?:\\.|[^"])*)"', match.group(1))
            ]
            if urls:
                return urls
        return []

    def _extract_meta_content(name: str) -> Optional[str]:
        match = re.search(
            rf'<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]+)"',
            normalized_html,
            re.I,
        )
        return _decode(match.group(1)) if match else None

    desc = _extract_meta_content("lark:url:video_title") or _extract_string(r'"desc":"((?:\\.|[^"])*)"')
    author_name = _extract_string(r'"nickname":"((?:\\.|[^"])*)"')
    if not author_name:
        description = _extract_meta_content("description") or ""
        meta_author = re.search(r"-\s*([^-\s][^于]+)于\d+", description)
        author_name = meta_author.group(1).strip() if meta_author else None
    cover_url = _extract_string(r'"coverUrl":"((?:\\.|[^"])*)"') or _extract_meta_content(
        "lark:url:video_cover_image_url"
    )

    info = DouyinVideoInfo(
        aweme_id=aweme_id,
        desc=desc,
        author_name=author_name,
        duration_ms=_extract_int(r'"duration":(\d+)'),
        width=_extract_int(r'"width":(\d+)'),
        height=_extract_int(r'"height":(\d+)'),
        play_urls=_extract_urls("playAddr"),
        download_urls=_extract_urls("downloadAddr"),
        cover_url=cover_url,
    )
    return info if info.play_urls or info.download_urls else None


def _sanitize_filename(text: str, fallback: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", (text or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:80] if cleaned else fallback


class VideoDownloader:
    """Resolve and download a Douyin video to local disk."""

    def __init__(self, headless: bool = True, max_retries: int = 3, retry_delay: float = 2.0):
        self.headless = headless
        self.max_retries = max(1, max_retries)
        self.retry_delay = max(0.0, retry_delay)

    def download(
        self,
        url: str,
        output: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ) -> DouyinVideoDownloadResponse:
        aweme_id, canonical_url = normalize_video_target(url)
        if not aweme_id or not canonical_url:
            raise VideoDownloadError(f"Cannot extract video ID from URL or ID: {url}")

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                video_info = self._resolve_video_info(canonical_url, aweme_id)
                video_url = choose_best_video_url(video_info)
                if not video_url:
                    raise VideoDownloadError(
                        f"Could not resolve a playable video URL for aweme {aweme_id}"
                    )

                output_path = output.expanduser() if output else self._existing_or_default_output_path(
                    video_info,
                    output_dir,
                )
                output_path.parent.mkdir(parents=True, exist_ok=True)
                metadata_path = self._metadata_path_for(output_path)
                skipped = output_path.exists() and output_path.stat().st_size > 0
                file_size = output_path.stat().st_size if skipped else self._download_file(video_url, output_path)

                result = DouyinVideoDownloadResponse(
                    url=canonical_url,
                    aweme_id=aweme_id,
                    desc=video_info.desc,
                    author_name=video_info.author_name,
                    video_url=video_url,
                    output_path=str(output_path),
                    metadata_path=str(metadata_path),
                    file_size=file_size,
                    duration_ms=video_info.duration_ms,
                    method=video_info.source,
                    skipped=skipped,
                    attempts=attempt,
                )
                if not metadata_path.exists() or not skipped:
                    self._write_metadata(result, metadata_path)
                return result
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay * (2 ** (attempt - 1)))

        raise VideoDownloadError(str(last_error) if last_error else f"Failed to download video: {url}")

    def _resolve_video_info(self, url: str, aweme_id: str) -> DouyinVideoInfo:
        state_file = get_state_path(SOURCE_NAME)
        storage_state = str(state_file) if state_file.exists() else None

        with sync_playwright() as playwright:
            context = None
            browser = playwright.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context_kwargs: dict = {
                    "viewport": {"width": 1440, "height": 1024},
                    "locale": "zh-CN",
                }
                if storage_state:
                    context_kwargs["storage_state"] = storage_state

                context = browser.new_context(**context_kwargs)
                context.add_init_script(STEALTH_SCRIPT)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                page.wait_for_timeout(Timeouts.VIDEO_LOAD)

                html = page.content()
                info = extract_video_info_from_html(html, aweme_id)
                if info:
                    return info

                fallback_url = self._extract_video_src(page)
                if fallback_url:
                    return DouyinVideoInfo(
                        aweme_id=aweme_id,
                        desc=page.title() or None,
                        play_urls=[fallback_url],
                        source="video_element",
                    )
            finally:
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass
                browser.close()

        raise VideoDownloadError(
            "Failed to locate embedded video metadata. Try re-running with --no-headless."
        )

    def _extract_video_src(self, page) -> Optional[str]:
        try:
            src = page.evaluate(
                """
                () => {
                    const videos = Array.from(document.querySelectorAll("video"));
                    for (const video of videos) {
                        const src = video.currentSrc || video.src || "";
                        if (src && !src.startsWith("blob:") && !src.includes("uuu_265.mp4")) {
                            return src;
                        }
                    }
                    return null;
                }
                """
            )
            return src or None
        except Exception:
            return None

    def _default_output_path(self, info: DouyinVideoInfo, output_dir: Optional[Path] = None) -> Path:
        downloads_dir = output_dir.expanduser() if output_dir else (get_data_dir(SOURCE_NAME) / "downloads")
        filename = _sanitize_filename(
            info.desc or f"douyin_{info.aweme_id}",
            fallback=f"douyin_{info.aweme_id}",
        )
        return downloads_dir / f"{filename}_{info.aweme_id}.mp4"

    def _existing_or_default_output_path(
        self,
        info: DouyinVideoInfo,
        output_dir: Optional[Path] = None,
    ) -> Path:
        downloads_dir = output_dir.expanduser() if output_dir else (get_data_dir(SOURCE_NAME) / "downloads")
        if downloads_dir.exists():
            matches = sorted(downloads_dir.glob(f"*_{info.aweme_id}.mp4"))
            if matches:
                return matches[0]
        return self._default_output_path(info, output_dir)

    def _metadata_path_for(self, output_path: Path) -> Path:
        if output_path.suffix:
            return output_path.with_suffix(".json")
        return output_path.parent / f"{output_path.name}.json"

    def _write_metadata(self, result: DouyinVideoDownloadResponse, metadata_path: Path) -> None:
        metadata_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _download_file(self, video_url: str, output_path: Path) -> int:
        headers = {
            "Referer": f"{BASE_URL}/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/145.0.0.0 Safari/537.36"
            ),
        }
        with requests.get(video_url, headers=headers, stream=True, timeout=120) as response:
            response.raise_for_status()
            with output_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 128):
                    if chunk:
                        handle.write(chunk)
        return output_path.stat().st_size
