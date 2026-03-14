"""WSJ automated login via Patchright (undetected Playwright).

Uses Patchright to bypass DataDome bot detection, auto-solves slider CAPTCHA,
and saves session cookies to ~/.web_scraper/wsj/cookies.txt in Netscape format.
"""
import json
import logging
import random
import time
from pathlib import Path
from typing import Optional

from ...core.browser import get_state_path
from ...core.cookies import get_cookies_path
from .config import SOURCE_NAME
from .headers import save_browser_profile

logger = logging.getLogger(__name__)

# Use WSJ's native login entry point — this redirects to the correct SSO URL
# with redirect_uri=https://www.wsj.com/client/auth (the working callback).
# Do NOT use a hardcoded SSO URL with accounts.wsj.com/auth/sso/login
# (that endpoint returns 404 from CloudFront).
WSJ_LOGIN_URL = "https://www.wsj.com/client/login"


def _find_captcha_frame(page):
    """Find the DataDome captcha frame if present."""
    for f in page.frames:
        if (
            "captcha" in f.url
            or "geo.captcha" in f.url
            or "interstitial" in f.url
            or "captcha-delivery.com" in f.url
        ):
            return f
    return None


def _solve_slider_captcha(page, *, timeout: float = 25.0, max_attempts: int = 4) -> bool:
    """Detect and solve DataDome slider CAPTCHA if present.

    Returns True if captcha was solved or not present, False on failure.
    """
    for attempt in range(max_attempts):
        captcha_frame = _find_captcha_frame(page)
        if not captcha_frame:
            return True  # No captcha

        if attempt > 0:
            logger.info("CAPTCHA retry attempt %d/%d", attempt + 1, max_attempts)

        logger.info("DataDome slider CAPTCHA detected, solving...")

        # Wait for slider elements to appear
        deadline = time.monotonic() + timeout
        slider_info = None
        while time.monotonic() < deadline:
            try:
                slider_info = captcha_frame.evaluate("""() => {
                    const slider = document.querySelector('.slider');
                    const target = document.querySelector('.sliderTarget');
                    if (!slider || !target) return null;
                    const sr = slider.getBoundingClientRect();
                    const tr = target.getBoundingClientRect();
                    if (sr.width === 0 || tr.width === 0) return null;
                    return {
                        sx: sr.x + sr.width / 2,
                        sy: sr.y + sr.height / 2,
                        sw: sr.width,
                        distance: tr.x - sr.x
                    };
                }""")
                if slider_info and slider_info["distance"] > 10:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not slider_info:
            logger.warning("Slider elements not found within timeout")
            captcha_frame = _find_captcha_frame(page)
            if captcha_frame:
                try:
                    captcha_frame.click("#captcha__reload__button", timeout=3000)
                    time.sleep(3)
                    continue
                except Exception:
                    pass
            return False

        # Get iframe position in main page coordinates
        iframe_offset = page.evaluate("""() => {
            const selectors = [
                'iframe[src*="captcha"]',
                'iframe[src*="geo.captcha"]',
                'iframe[src*="captcha-delivery"]',
                'iframe[src*="interstitial"]',
            ];
            for (const sel of selectors) {
                const iframe = document.querySelector(sel);
                if (iframe) {
                    const r = iframe.getBoundingClientRect();
                    return {x: r.x, y: r.y, w: r.width, h: r.height};
                }
            }
            // Fallback: find any iframe with captcha in src
            const all = document.querySelectorAll('iframe');
            for (const iframe of all) {
                if (iframe.src && (iframe.src.includes('captcha') || iframe.src.includes('interstitial'))) {
                    const r = iframe.getBoundingClientRect();
                    return {x: r.x, y: r.y, w: r.width, h: r.height};
                }
            }
            return {x: 0, y: 0, w: 0, h: 0};
        }""")

        start_x = iframe_offset["x"] + slider_info["sx"]
        start_y = iframe_offset["y"] + slider_info["sy"]
        end_x = start_x + slider_info["distance"]

        logger.debug(
            "Slider drag: (%d,%d) -> (%d,%d), iframe offset (%d,%d)",
            start_x, start_y, end_x, start_y,
            iframe_offset["x"], iframe_offset["y"],
        )

        # Human-like drag: move to slider, press, ease-out with jitter
        page.mouse.move(start_x, start_y)
        time.sleep(0.2 + random.random() * 0.3)
        page.mouse.down()
        time.sleep(0.05 + random.random() * 0.1)

        steps = random.randint(20, 30)
        for i in range(steps + 1):
            t = i / steps
            ease = 1 - (1 - t) ** 3  # cubic ease-out
            cx = start_x + (end_x - start_x) * ease
            cy = start_y + random.uniform(-2, 2)
            page.mouse.move(cx, cy)
            time.sleep(random.uniform(0.01, 0.04))

        time.sleep(0.1 + random.random() * 0.15)
        page.mouse.up()

        # Wait for captcha to clear — check both frame presence and page title
        for _ in range(20):
            time.sleep(0.5)
            captcha_gone = not _find_captcha_frame(page)
            title_changed = page.title() != "dowjones.com"
            if captcha_gone or title_changed:
                logger.info("CAPTCHA solved successfully")
                time.sleep(1)
                return True

        logger.warning("CAPTCHA attempt %d failed, may retry", attempt + 1)
        # Click reload button to get a new captcha
        captcha_frame = _find_captcha_frame(page)
        if captcha_frame:
            try:
                captcha_frame.click("#captcha__reload__button", timeout=3000)
                time.sleep(2)
            except Exception:
                pass

    logger.warning("All CAPTCHA attempts exhausted")
    return False


def _save_cookies_netscape(cookies: list[dict], source: str) -> Path:
    """Save Patchright cookies to Netscape format file."""
    path = get_cookies_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Netscape HTTP Cookie File", f"# Saved by WSJ auto-login"]
    for c in cookies:
        domain = c.get("domain", "")
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path_val = c.get("path", "/")
        secure = "TRUE" if c.get("secure") else "FALSE"
        expires = str(int(c.get("expires", 0)))
        name = c["name"]
        value = c["value"]
        lines.append(f"{domain}\t{flag}\t{path_val}\t{secure}\t{expires}\t{name}\t{value}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _dismiss_cookie_banner(page):
    """Click 'YES, I AGREE' cookie consent banner if present."""
    try:
        agree_btn = page.locator('button:has-text("YES, I AGREE")')
        if agree_btn.count() > 0:
            agree_btn.click()
            time.sleep(1)
    except Exception:
        pass


def _dismiss_consent_dialog(page):
    """Dismiss the SP Consent Message dialog if present."""
    try:
        # The consent iframe blocks other clicks
        consent_frame = page.frame_locator('iframe[title="SP Consent Message"]')
        accept_btn = consent_frame.locator(
            'button[title="Yes, I Agree"], button:has-text("Accept"), '
            'button:has-text("Agree"), button:has-text("OK")'
        )
        if accept_btn.count() > 0:
            accept_btn.first.click()
            time.sleep(1)
    except Exception:
        pass


def _wait_for_login_form(page, *, attempts: int = 3) -> bool:
    """Ensure the SSO email form is visible, retrying via the native login URL."""
    for attempt in range(attempts):
        try:
            page.wait_for_selector("#emailOrUsername-form-item", timeout=15000)
            return True
        except Exception:
            logger.warning("Login form not visible (attempt %d/%d), retrying...", attempt + 1, attempts)
            try:
                page.goto(WSJ_LOGIN_URL, timeout=30000)
                time.sleep(4)
                _solve_slider_captcha(page, timeout=10.0, max_attempts=2)
                _dismiss_consent_dialog(page)
            except Exception:
                pass
    return False


def _extract_and_save_cookies(ctx, page=None) -> Optional[Path]:
    """Extract cookies from browser context and save to Netscape file.

    If page is provided, waits for wsj.com to fully load so JS-set cookies
    (DJSESSION, wsjregion etc.) have time to appear.
    """
    if page:
        try:
            current = page.url
            if "wsj.com" not in current or "sso.accounts" in current:
                page.goto("https://www.wsj.com", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # Wait for JS to set all cookies (DJSESSION etc. are set asynchronously)
        time.sleep(5)
        try:
            profile = page.evaluate("""() => ({
                userAgent: navigator.userAgent,
                language: navigator.language,
                platform: navigator.userAgentData?.platform || navigator.platform || "",
                brands: navigator.userAgentData?.brands || []
            })""")
            if profile:
                save_browser_profile(json.loads(json.dumps(profile)))
        except Exception:
            pass

    all_cookies = ctx.cookies()

    # Keep all cookies from relevant domains
    relevant_domains = [".wsj.com", ".dowjones.com", "wsj.com",
                        "accounts.wsj.com", "sso.accounts.dowjones.com"]
    wsj_cookies = [
        c for c in all_cookies
        if any(d in c.get("domain", "") for d in relevant_domains)
    ]

    if not wsj_cookies:
        return None

    try:
        state_path = get_state_path(SOURCE_NAME)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=str(state_path))
    except Exception:
        pass

    return _save_cookies_netscape(wsj_cookies, SOURCE_NAME)


def ensure_cookies(
    email: str,
    password: str,
    *,
    headless: bool = False,
) -> tuple[bool, str]:
    """Check if current cookies are valid; if not, auto-login to refresh.

    Call this before any WSJ scraping operation that requires authentication.

    Returns:
        (success, message) tuple.
    """
    from .cookies import load_cookies, check_cookies_valid_sync

    cookies = load_cookies()
    if cookies.jar:
        is_valid, msg = check_cookies_valid_sync(cookies)
        if is_valid:
            return True, msg

    logger.info("Cookies expired or missing, auto-logging in...")
    return login(email, password, headless=headless)


def _login_once(
    email: str,
    password: str,
    *,
    headless: bool = False,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Run a single WSJ login attempt."""
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return False, "patchright not installed. Run: poetry add patchright"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context()
        page = ctx.new_page()

        try:
            # Step 1: Visit wsj.com first — establishes cookies for the domain
            # then click Sign In to enter the SSO flow with correct redirect_uri
            logger.info("Navigating to wsj.com...")
            page.goto("https://www.wsj.com", timeout=30000)
            time.sleep(4)

            if not _solve_slider_captcha(page, timeout=20.0, max_attempts=4):
                return False, "Failed to solve CAPTCHA on wsj.com. Try: scraper wsj login -i"

            time.sleep(2)
            _dismiss_consent_dialog(page)

            # Click Sign In link (falls back to direct URL)
            logger.info("Clicking Sign In...")
            sign_in = page.locator('a:has-text("Sign In")')
            if sign_in.count() > 0:
                sign_in.first.click(timeout=10000)
            else:
                page.goto(WSJ_LOGIN_URL, timeout=30000)
            time.sleep(5)

            # Step 2: Handle CAPTCHA on SSO page (DataDome may block)
            if not _solve_slider_captcha(page, timeout=20.0, max_attempts=4):
                return False, "Failed to solve CAPTCHA on SSO. Try: scraper wsj login -i"

            time.sleep(2)
            if "captcha" in page.url or page.title() == "dowjones.com":
                time.sleep(3)
                _solve_slider_captcha(page, timeout=8.0)

            # Wait for login form (should now be on sso.accounts.dowjones.com)
            if not _wait_for_login_form(page):
                body = page.evaluate("document.body.innerText.substring(0, 200)")
                return False, f"Login form not found. Page: {body[:150]}"

            # Step 3: Enter email with retry on "Service unavailable"
            logger.info("Entering email...")
            for email_attempt in range(3):
                email_input = page.locator("#emailOrUsername-form-item")
                email_input.click()
                time.sleep(0.2)
                email_input.fill("")
                time.sleep(0.1)
                # Type character by character for more human-like behavior
                for ch in email:
                    email_input.press(ch)
                    time.sleep(random.uniform(0.03, 0.08))
                time.sleep(0.5 + random.random() * 0.3)

                # Click Continue
                page.locator("#signin-continue-btn").click()
                time.sleep(3)

                # Check for CAPTCHA after email submission
                _solve_slider_captcha(page, timeout=5.0)

                # Check if we got "Service unavailable" error
                body_text = page.evaluate("document.body.innerText.substring(0, 500)")
                if "Service is currently unavailable" in body_text:
                    logger.warning("Service unavailable (attempt %d), retrying...", email_attempt + 1)
                    page.goto(WSJ_LOGIN_URL, timeout=30000)
                    time.sleep(3)
                    _solve_slider_captcha(page)
                    time.sleep(2)
                try:
                    _wait_for_login_form(page, attempts=1)
                except Exception:
                    pass
                    continue
                break

            # Step 4: Wait for password field
            try:
                page.wait_for_selector(
                    'input[name="password"], input[type="password"]',
                    timeout=10000,
                )
            except Exception:
                body = page.evaluate("document.body.innerText.substring(0, 300)")
                return False, f"Password field not found. Page says: {body[:150]}"

            logger.info("Entering password...")
            pwd_input = page.locator('input[name="password"], input[type="password"]')
            pwd_input.click()
            time.sleep(0.3)
            pwd_input.fill(password)
            time.sleep(0.5 + random.random() * 0.3)

            # Click Sign In
            sign_in_btn = page.locator('button[type="submit"], button:has-text("Sign In")')
            sign_in_btn.first.click()

            # Step 5: Wait for post-login pages, click through to wsj.com
            # Flow: Sign In → "Verify Email" page → "Continue to WSJ" click
            #   → SSO /continue → www.wsj.com/client/auth?code=... → www.wsj.com
            logger.info("Waiting for login to complete...")
            deadline = time.monotonic() + timeout
            login_done = False
            while time.monotonic() < deadline:
                url = page.url

                # Already on wsj.com (not the SSO or callback) — done
                if "www.wsj.com" in url and "/client/auth" not in url:
                    login_done = True
                    break

                # Click any "Continue to WSJ" button on interstitial pages
                try:
                    continue_btn = page.locator(
                        'button:has-text("Continue to WSJ"), '
                        'a:has-text("Continue to WSJ")'
                    )
                    if continue_btn.count() > 0:
                        logger.info("Clicking 'Continue to WSJ'")
                        continue_btn.first.click()
                        # Wait for redirect chain to complete
                        for _ in range(15):
                            time.sleep(1)
                            cur = page.url
                            if "www.wsj.com" in cur and "/client/auth" not in cur:
                                login_done = True
                                break
                            if _find_captcha_frame(page):
                                _solve_slider_captcha(page)
                        if login_done:
                            break
                        continue
                except Exception:
                    pass

                # Handle CAPTCHA
                _solve_slider_captcha(page, timeout=3.0)
                time.sleep(1)

            if not login_done:
                current_url = page.url
                body = page.evaluate("document.body.innerText.substring(0, 200)")
                return False, f"Login timeout. URL: {current_url}, Page: {body[:100]}"

            # Dismiss consent/cookie banners
            _dismiss_cookie_banner(page)
            _dismiss_consent_dialog(page)

            # Step 6: Wait for page to fully load and JS to set all cookies
            logger.info("Waiting for cookies to be set...")
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(5)
            path = _extract_and_save_cookies(ctx, page)
            if not path:
                return False, "Login appeared successful but no WSJ cookies found"

            return True, f"Login successful! Cookies saved to {path}"

        except Exception as e:
            logger.exception("Login failed")
            return False, f"Login error: {e}"
        finally:
            browser.close()


def login(
    email: str,
    password: str,
    *,
    headless: bool = False,
    timeout: float = 60.0,
    attempts: int = 3,
) -> tuple[bool, str]:
    """Automated WSJ login via Patchright.

    Args:
        email: WSJ account email.
        password: WSJ account password.
        headless: Run browser headlessly (default False for CAPTCHA visibility).
        timeout: Max seconds to wait for login completion.
        attempts: Number of full login attempts before giving up.

    Returns:
        (success, message) tuple.
    """
    last_message = "WSJ login failed"
    for attempt in range(1, attempts + 1):
        ok, message = _login_once(email, password, headless=headless, timeout=timeout)
        if ok:
            return ok, message
        last_message = message
        if attempt < attempts:
            logger.warning("WSJ login attempt %d/%d failed: %s", attempt, attempts, message)
            time.sleep(3)

    return False, last_message


def login_interactive(
    email: Optional[str] = None,
    password: Optional[str] = None,
    *,
    headless: bool = False,
) -> tuple[bool, str]:
    """Interactive login — opens browser, waits for user to complete login manually.

    Use this when automated login fails (e.g., new CAPTCHA type, 2FA).
    If email/password are provided, they are pre-filled.

    Returns:
        (success, message) tuple.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        return False, "patchright not installed. Run: poetry add patchright"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # Always visible
        ctx = browser.new_context()
        page = ctx.new_page()

        try:
            # Start from wsj.com for proper cookie domain setup
            page.goto("https://www.wsj.com", timeout=30000)
            time.sleep(3)
            _solve_slider_captcha(page)
            _dismiss_consent_dialog(page)

            # Navigate to login
            sign_in = page.locator('a:has-text("Sign In")')
            if sign_in.count() > 0:
                sign_in.first.click(timeout=10000)
            else:
                page.goto(WSJ_LOGIN_URL, timeout=30000)
            time.sleep(4)
            _solve_slider_captcha(page)

            # Pre-fill email if provided
            if email:
                try:
                    if not _wait_for_login_form(page, attempts=2):
                        raise RuntimeError("login form unavailable")
                    page.locator("#emailOrUsername-form-item").fill(email)
                except Exception:
                    pass

            # Wait for user to complete login (up to 5 minutes)
            logger.info("Waiting for user to complete login...")
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                url = page.url
                if "www.wsj.com" in url and "sso.accounts" not in url:
                    break
                time.sleep(2)
            else:
                return False, "Timeout waiting for login (5 minutes)"

            _dismiss_cookie_banner(page)
            _dismiss_consent_dialog(page)

            path = _extract_and_save_cookies(ctx, page)
            if not path:
                return False, "No WSJ cookies captured"

            return True, f"Login successful! Cookies saved to {path}"

        except Exception as e:
            return False, f"Interactive login error: {e}"
        finally:
            browser.close()
