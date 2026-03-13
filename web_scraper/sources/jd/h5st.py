"""JD h5st signature oracle using Playwright.

Strategy: Load a JD product page once to initialize the JS signing SDK,
then call ParamsSign.sign() in the browser context to generate h5st
signatures for any API request. The actual API calls are made with httpx,
avoiding repeated page navigations and reducing risk control exposure.

This is analogous to Zhihu's SignatureOracle pattern.
"""
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

from .config import BASE_URL
from .cookies import get_cookies_path, netscape_to_playwright

logger = logging.getLogger(__name__)

# A known product page to initialize the signing SDK
_INIT_URL = f"{BASE_URL}/100041256706.html"  # Popular product, unlikely to be removed

# Max retries for browser crashes
_MAX_RETRIES = 3


class SignatureOracle:
    """Generate h5st signatures by calling JD's JS signing SDK in a browser.

    Usage:
        oracle = SignatureOracle(cookies_path)
        oracle.start()

        signed_params = oracle.sign({
            'functionId': 'getCommentListPage',
            'appid': 'pc-rate-qa',
            'client': 'pc',
            'clientVersion': '1.0.0',
            'body': '{"sku":"123",...}',
            't': '1773266700145',
            'loginType': '3',
            'uuid': '...',
        })
        # signed_params now contains h5st, _stk, _ste fields

        oracle.stop()
    """

    def __init__(self, cookies_path: Path | None = None, init_url: str | None = None):
        if cookies_path is None:
            cookies_path = get_cookies_path()
        if not cookies_path.exists():
            raise FileNotFoundError(
                f"Cookies file not found: {cookies_path}\n"
                f"Run 'scraper jd import-cookies <path>' first."
            )
        self.cookies_path = cookies_path
        self.init_url = init_url or _INIT_URL
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._pw_cookies = None
        self._uuid: str | None = None
        self._ready = False

    @property
    def uuid(self) -> str | None:
        return self._uuid

    def _launch_browser(self):
        """Launch browser and create context. Separated for retry logic."""
        from patchright.sync_api import sync_playwright

        if self._pw_cookies is None:
            self._pw_cookies = netscape_to_playwright(self.cookies_path)

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--disable-software-rasterizer",
            ],
        )
        self._context = self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        self._context.add_cookies(self._pw_cookies)

        self._page = self._context.new_page()
        self._page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )

    def _close_browser(self):
        """Close browser without stopping playwright."""
        self._page = None
        self._context = None
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

    def start(self) -> None:
        """Launch browser and initialize the signing SDK.

        Retries up to _MAX_RETRIES times on browser crashes.
        """
        last_error = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._close_browser()
                self._launch_browser()

                logger.info(f"Loading init page (attempt {attempt}): {self.init_url}")
                self._page.goto(self.init_url, wait_until="domcontentloaded", timeout=60000)
                self._page.wait_for_timeout(5000)

                # Check for risk redirect
                if "risk_handler" in self._page.url or "passport.jd.com" in self._page.url:
                    self.stop()
                    raise Exception(
                        "JD risk control triggered during SignatureOracle init.\n"
                        "Please visit https://item.jd.com in your browser to pass CAPTCHA, then retry."
                    )

                # Verify ParamsSign is available
                check = self._page.evaluate("""() => {
                    return {
                        hasParamsSign: typeof window.ParamsSign === 'function',
                        hasPSign: !!window.PSign,
                    };
                }""")

                if not check.get("hasParamsSign"):
                    self.stop()
                    raise Exception("ParamsSign not found on page. JD SDK may have changed.")

                # Extract uuid from __jda cookie
                self._uuid = self._page.evaluate("""() => {
                    const jda = document.cookie.split(';').find(c => c.trim().startsWith('__jda='));
                    if (jda) {
                        const parts = jda.split('=')[1].split('.');
                        return parts.length > 1 ? parts[1] : null;
                    }
                    return null;
                }""")

                self._ready = True
                logger.info(f"SignatureOracle ready. UUID: {self._uuid}")
                return

            except Exception as e:
                last_error = e
                err_msg = str(e)
                # Don't retry on risk control or missing SDK — those aren't transient
                if "risk control" in err_msg or "ParamsSign not found" in err_msg:
                    raise
                logger.warning(f"SignatureOracle start attempt {attempt} failed: {e}")
                self._close_browser()
                if attempt < _MAX_RETRIES:
                    time.sleep(2)

        self.stop()
        raise Exception(
            f"SignatureOracle failed after {_MAX_RETRIES} attempts. "
            f"Last error: {last_error}"
        )

    def stop(self) -> None:
        """Close the browser."""
        self._close_browser()
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._ready = False

    def sign(self, params: Dict[str, str], app_id: str | None = None) -> Dict[str, Any]:
        """Generate h5st signature for the given request parameters.

        Args:
            params: Request parameters dict. Must include at least:
                - functionId
                - appid
                - body (JSON string)
                - t (timestamp, will be auto-generated if missing)
            app_id: Override the signing appId (used internally by ParamsSign).
                   If None, uses the page's default PSign appId.

        Returns:
            Dict with all original params plus h5st, _stk, _ste fields.

        Raises:
            Exception: If signing fails or oracle is not started.
        """
        if not self._ready or not self._page:
            raise Exception("SignatureOracle not started. Call start() first.")

        # Ensure t is set
        if "t" not in params:
            params["t"] = str(int(time.time() * 1000))

        # Retry on Target crashed — restart browser and re-init
        last_error = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                result = self._page.evaluate("""({params, appId}) => {
                    return new Promise((resolve, reject) => {
                        try {
                            const signAppId = appId || (window.PSign && window.PSign.__appId) || 'fb5df';
                            const ps = new window.ParamsSign({appId: signAppId});
                            const result = ps.sign(params);
                            if (result && typeof result.then === 'function') {
                                result.then(r => resolve(r || {error: 'null result'}))
                                      .catch(e => resolve({error: e.message}));
                            } else {
                                resolve(result || {error: 'null result'});
                            }
                        } catch(e) {
                            resolve({error: e.message});
                        }
                    });
                }""", {"params": params, "appId": app_id})

                if isinstance(result, dict) and "error" in result:
                    raise Exception(f"h5st signing failed: {result['error']}")

                return result

            except Exception as e:
                last_error = e
                err_msg = str(e)
                if "Target crashed" in err_msg or "Target closed" in err_msg:
                    logger.warning(f"Browser crashed during sign (attempt {attempt}), restarting...")
                    if attempt < _MAX_RETRIES:
                        # Restart the whole browser
                        self._ready = False
                        self.start()
                        # Update t for the retry
                        params["t"] = str(int(time.time() * 1000))
                        continue
                raise

        raise Exception(
            f"Signing failed after {_MAX_RETRIES} attempts. Last error: {last_error}"
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
