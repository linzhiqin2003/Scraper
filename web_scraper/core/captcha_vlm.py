"""VLM-based CAPTCHA solver for slider puzzles and icon selection.

Uses Vision Language Models (e.g. Gemini, Qwen-VL) to analyze CAPTCHA images
and compute drag offsets / click coordinates. Works with Patchright pages.

Supports:
- Slide puzzles: detects dark piece + light gap, computes drag distance
- Icon selection: identifies and orders icons to click

Usage:
    from web_scraper.core.captcha_vlm import VLMCaptchaSolver
    solver = VLMCaptchaSolver()
    solved = solver.solve_on_page(page)  # returns True/False

Environment variables:
    CAPTCHA_VLM_MODEL    — model name (default: google/gemini-3-flash-preview)
    CAPTCHA_VLM_PROVIDER — "openrouter" or "dashscope" (default: openrouter)
    OPENROUTER_API_KEY   — API key for OpenRouter
    DASHSCOPE_API_KEY    — API key for DashScope
"""

import base64
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Optional

from .captcha import (
    CaptchaChallenge,
    CaptchaSolution,
    CaptchaSolver,
    CaptchaType,
)

logger = logging.getLogger(__name__)

# ── VLM Prompt ──

CAPTCHA_PROMPT = """Look at this CAPTCHA image and determine its type, then solve it.

TYPE A — SLIDE PUZZLE:
The image shows a photo with TWO overlay shapes:
- A DARK shape on the left (the draggable piece)
- A LIGHT/WHITE semi-transparent shape on the right (the target)
→ Return the BOUNDING BOX of the LIGHT/WHITE target shape,
  AND "piece_cx": the horizontal center X of the DARK piece (normalized 0-999).

TYPE B — ICON SELECTION:
The image shows a photo with several GRAY ICONS scattered on it,
and a bottom bar saying "Select icons in the correct order" with 3 small reference icons.
→ Return the CENTER coordinates of the 3 matching LARGE icons in the photo,
in the ORDER shown by the bottom bar reference icons (left to right = 1st, 2nd, 3rd).
IMPORTANT: Click the LARGE icons in the PHOTO, not the tiny ones in the bottom bar.

Coordinates: normalized 0-999 scale (0,0 = top-left, 999,999 = bottom-right).

Return ONLY valid JSON, no markdown, no explanation. Strictly follow these exact formats:

Type A: {"type": "slide", "bbox": [x1, y1, x2, y2], "piece_cx": 80}
Type B: {"type": "icons", "clicks": [{"x": 123, "y": 456, "icon": "name1"}, \
{"x": 234, "y": 567, "icon": "name2"}, {"x": 345, "y": 678, "icon": "name3"}]}

Each click MUST have separate "x" and "y" integer fields. Do NOT nest coordinates in arrays."""

VLM_PROVIDERS = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
}


@dataclass
class VLMResult:
    """Parsed VLM response."""
    ctype: str  # "slide" or "icons"
    bbox: Optional[list] = None      # [x1, y1, x2, y2] for slide
    piece_cx: Optional[int] = None   # piece center X for slide
    clicks: Optional[list] = None    # [{x, y, icon}] for icons


# ── VLM API ──

def _call_vlm(
    image_bytes: bytes,
    model: str = "",
    provider: str = "",
) -> Optional[VLMResult]:
    """Call VLM to analyze CAPTCHA image. Returns VLMResult or None."""
    model = model or os.getenv("CAPTCHA_VLM_MODEL", "google/gemini-3-flash-preview")
    provider = provider or os.getenv("CAPTCHA_VLM_PROVIDER", "openrouter")

    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed — pip install openai")
        return None

    cfg = VLM_PROVIDERS.get(provider)
    if not cfg:
        logger.error("Unknown VLM provider: %s", provider)
        return None

    api_key = os.getenv(cfg["env_key"])
    if not api_key:
        logger.error("Missing env var %s for VLM provider %s", cfg["env_key"], provider)
        return None

    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    b64 = base64.b64encode(image_bytes).decode()

    t0 = time.time()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": CAPTCHA_PROMPT},
            ]}],
        )
    except Exception as e:
        logger.error("VLM API error: %s", e)
        return None

    raw = completion.choices[0].message.content
    elapsed = time.time() - t0
    logger.info("[captcha-vlm] %s in %.1fs: %s", model, elapsed, raw[:200])

    return _parse_vlm_response(raw)


def _parse_vlm_response(raw: str) -> Optional[VLMResult]:
    """Parse VLM JSON response into VLMResult."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?```\s*$', '', text)

    for attempt_text in [text, re.sub(r'"x":\s*(\d+),\s*(\d+)', r'"x": \1, "y": \2', text)]:
        match = re.search(r'\{.*\}', attempt_text, re.DOTALL)
        if not match:
            continue
        try:
            d = json.loads(match.group())
            ctype = d.get("type", "")
            if ctype == "slide" and "bbox" in d:
                return VLMResult(ctype="slide", bbox=d["bbox"], piece_cx=d.get("piece_cx"))
            elif ctype == "icons" and "clicks" in d:
                clicks = []
                for c in d["clicks"]:
                    x, y = c.get("x"), c.get("y")
                    if isinstance(x, list) and len(x) == 2:
                        x, y = x[0], x[1]
                    if x is not None and y is not None:
                        clicks.append({"x": int(x), "y": int(y), "icon": c.get("icon", "?")})
                return VLMResult(ctype="icons", clicks=clicks)
        except json.JSONDecodeError:
            continue
    return None


# ── Page interaction helpers ──

def _find_captcha_modal_rect(page):
    """Find the CAPTCHA modal bounding rect by walking up from the image."""
    return page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        let captchaImg = null;
        for (const img of imgs) {
            const r = img.getBoundingClientRect();
            if (r.width > 200 && r.height > 80 && r.top > 100) {
                if (!captchaImg || r.width > captchaImg.getBoundingClientRect().width)
                    captchaImg = img;
            }
        }
        if (!captchaImg) return null;
        const imgR = captchaImg.getBoundingClientRect();
        let el = captchaImg.parentElement;
        for (let i = 0; i < 8 && el; i++) {
            const r = el.getBoundingClientRect();
            if (r.height > imgR.height + 20 && r.width >= imgR.width * 0.9)
                return {x: r.x, y: r.y, w: r.width, h: r.height};
            el = el.parentElement;
        }
        return null;
    }""")


def _find_captcha_image_rect(page):
    """Find the CAPTCHA background image rect."""
    return page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        let best = null;
        for (const img of imgs) {
            const r = img.getBoundingClientRect();
            if (r.width > 200 && r.height > 80 && r.top > 100) {
                if (!best || r.width > best.w)
                    best = {x: r.x, y: r.y, w: r.width, h: r.height};
            }
        }
        return best;
    }""")


def _find_slider(page):
    """Find the slider handle element."""
    return page.evaluate("""() => {
        const handle = document.querySelector('.cpt-drop-bg');
        if (handle) {
            const r = handle.getBoundingClientRect();
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }
        const el = document.querySelector(
            '[class*=cpt-drop], [class*=slider-btn], [class*=drag-btn]');
        if (el) {
            const r = el.getBoundingClientRect();
            return {x: r.x + r.width/2, y: r.y + r.height/2};
        }
        return null;
    }""")


def _human_drag(page, start_x: float, start_y: float, target_x: float):
    """Simulate human-like drag with acceleration and slight wobble."""
    offset = target_x - start_x
    if offset <= 0:
        return
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    steps = random.randint(20, 35)
    for i in range(steps + 1):
        t = i / steps
        ease = t * t * (3 - 2 * t)
        x = start_x + offset * ease
        y = start_y + random.uniform(-2, 2)
        page.mouse.move(x, y)
        time.sleep(random.uniform(0.008, 0.025))
    page.mouse.move(start_x + offset + random.randint(2, 6), start_y)
    time.sleep(0.05)
    page.mouse.move(start_x + offset, start_y)
    time.sleep(random.uniform(0.05, 0.15))
    page.mouse.up()


def _screenshot_captcha(page):
    """Screenshot the CAPTCHA modal. Returns (bytes, modal_rect, img_rect) or (None, None, None)."""
    captcha_rect = _find_captcha_modal_rect(page)
    if not captcha_rect:
        captcha_rect = _find_captcha_image_rect(page)
    if not captcha_rect:
        return None, None, None
    img_rect = _find_captcha_image_rect(page) or captcha_rect
    clip = {"x": captcha_rect["x"], "y": captcha_rect["y"],
            "width": captcha_rect["w"], "height": captcha_rect["h"]}
    captcha_bytes = page.screenshot(clip=clip)
    return captcha_bytes, captcha_rect, img_rect


def _check_captcha_present(page) -> bool:
    """Check if CAPTCHA modal is still visible on page."""
    try:
        visible = page.evaluate("""() => {
            const imgs = document.querySelectorAll('img');
            for (const img of imgs) {
                const r = img.getBoundingClientRect();
                if (r.width > 200 && r.height > 80 && r.top > 100) {
                    const style = window.getComputedStyle(img);
                    if (style.display !== 'none' && style.visibility !== 'hidden'
                        && style.opacity !== '0') {
                        let el = img.parentElement;
                        for (let i = 0; i < 5 && el; i++) {
                            if (/slide|captcha|verif|select icons|too many/i.test(
                                el.textContent || '')) return true;
                            el = el.parentElement;
                        }
                    }
                }
            }
            return false;
        }""")
        if visible:
            return True
        text = page.evaluate("""() => {
            const sel = document.querySelector(
                '[class*=captcha], [class*=verify], [class*=cpt-]');
            if (!sel) return '';
            const style = window.getComputedStyle(sel);
            if (style.display === 'none' || style.visibility === 'hidden') return '';
            return sel.innerText || '';
        }""")
        return any(s in text.lower() for s in [
            "too many attempts", "slide to complete", "select icons",
            "complete the verification",
        ])
    except Exception:
        return False


def detect_captcha(page) -> bool:
    """Quick check: is a CAPTCHA showing on this page?"""
    try:
        text = page.evaluate("document.body ? document.body.innerText : ''")
        return any(s in text.lower() for s in [
            "too many attempts", "slide to complete",
            "complete the verification", "select icons",
        ])
    except Exception:
        return False


# ── Main solver ──

def solve_captcha_on_page(
    page,
    max_attempts: int = 5,
    model: str = "",
    provider: str = "",
) -> bool:
    """Detect and solve CAPTCHA on a Patchright page.

    Handles both slide puzzles and icon selection CAPTCHAs.
    Returns True if solved, False if failed after max_attempts.
    """
    from PIL import Image as PILImage
    from io import BytesIO

    page.wait_for_timeout(2000)

    for attempt in range(max_attempts):
        logger.info("[captcha] attempt %d/%d", attempt + 1, max_attempts)

        # Wait for CAPTCHA image to load
        for _ in range(15):
            loaded = page.evaluate("""() => {
                const imgs = document.querySelectorAll('img');
                for (const img of imgs) {
                    const r = img.getBoundingClientRect();
                    if (r.width > 200 && r.height > 80 && r.top > 100) return true;
                }
                return false;
            }""")
            if loaded:
                break
            page.wait_for_timeout(500)

        captcha_bytes, captcha_rect, img_rect = _screenshot_captcha(page)
        if not captcha_bytes:
            logger.warning("[captcha] modal not found, waiting...")
            page.wait_for_timeout(2000)
            continue

        result = _call_vlm(captcha_bytes, model=model, provider=provider)
        if not result:
            logger.warning("[captcha] VLM failed to parse")
            continue

        # Get scale factor (screenshot pixels vs CSS pixels)
        pil_img = PILImage.open(BytesIO(captcha_bytes))
        crop_px_w, crop_px_h = pil_img.size
        scale = crop_px_w / captcha_rect["w"]

        # ── Execute action ──
        if result.ctype == "slide" and result.bbox:
            gap_cx_norm = (result.bbox[0] + result.bbox[2]) / 2
            gap_cx_css = (gap_cx_norm * crop_px_w / 999) / scale

            if result.piece_cx is not None:
                piece_cx_css = (result.piece_cx * crop_px_w / 999) / scale
                drag_dist = gap_cx_css - piece_cx_css
                logger.info("[captcha] slide: piece=%.0f gap=%.0f drag=%.0fpx",
                            piece_cx_css, gap_cx_css, drag_dist)
            else:
                page_gap_x = img_rect["x"] + gap_cx_css
                slider_tmp = _find_slider(page)
                drag_dist = page_gap_x - slider_tmp["x"] if slider_tmp else gap_cx_css

            slider = _find_slider(page)
            if not slider:
                logger.warning("[captcha] slider not found")
                continue
            _human_drag(page, slider["x"], slider["y"], slider["x"] + drag_dist)

        elif result.ctype == "icons" and result.clicks:
            for i, click in enumerate(result.clicks):
                px = captcha_rect["x"] + (click["x"] * crop_px_w / 999) / scale
                py = captcha_rect["y"] + (click["y"] * crop_px_h / 999) / scale
                logger.info("[captcha] click %d/3: (%.0f, %.0f)", i + 1, px, py)
                page.mouse.click(px, py)
                page.wait_for_timeout(600)
        else:
            logger.warning("[captcha] unknown type: %s", result.ctype)
            continue

        # Check result
        page.wait_for_timeout(2000)

        after_text = page.evaluate("document.body ? document.body.innerText : ''")
        if "internet connection" in after_text.lower():
            logger.info("[captcha] rejected")
            page.wait_for_timeout(2000)
            try:
                refresh = page.query_selector('[class*=refresh], [class*=reload]')
                if refresh:
                    refresh.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass
            continue

        if not _check_captcha_present(page):
            logger.info("[captcha] SOLVED!")
            return True
        else:
            logger.info("[captcha] failed, retrying...")
            try:
                refresh = page.query_selector('[class*=refresh], [class*=reload]')
                if refresh:
                    refresh.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass

    logger.warning("[captcha] failed after %d attempts", max_attempts)
    return False


# ── CaptchaSolver interface implementation ──

class VLMCaptchaSolver(CaptchaSolver):
    """VLM-based CAPTCHA solver using Vision Language Models.

    Solves slider puzzles and icon selection CAPTCHAs by:
    1. Screenshotting the CAPTCHA modal
    2. Sending to VLM for analysis (gap/piece detection or icon ordering)
    3. Executing the drag or click actions on the page

    Requires a Patchright Page object in challenge.extra["page"].

    Usage:
        solver = VLMCaptchaSolver()
        challenge = CaptchaChallenge(
            captcha_type=CaptchaType.SLIDER,
            site_url="https://example.com",
            extra={"page": patchright_page},
        )
        solution = solver.solve(challenge)
    """

    def __init__(
        self,
        model: str = "",
        provider: str = "",
        max_attempts: int = 5,
    ):
        self._model = model
        self._provider = provider
        self._max_attempts = max_attempts

    @property
    def name(self) -> str:
        model = self._model or os.getenv("CAPTCHA_VLM_MODEL", "google/gemini-3-flash-preview")
        return f"VLMCaptchaSolver ({model})"

    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        page = challenge.extra.get("page") if challenge.extra else None
        if not page:
            return CaptchaSolution(
                success=False,
                error="VLMCaptchaSolver requires a Patchright Page in challenge.extra['page']",
            )

        solved = solve_captcha_on_page(
            page,
            max_attempts=self._max_attempts,
            model=self._model,
            provider=self._provider,
        )
        return CaptchaSolution(success=solved, error=None if solved else "Failed to solve CAPTCHA")

    def get_balance(self) -> Optional[float]:
        return None
