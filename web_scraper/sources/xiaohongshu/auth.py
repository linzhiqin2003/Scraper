"""Authentication module for Xiaohongshu."""

from typing import Optional

from playwright.async_api import Page
from rich.console import Console
from rich.prompt import Prompt

from ...core.browser import BrowserManager, random_delay
from .config import SOURCE_NAME, EXPLORE_URL, COOKIE_PATH, Selectors

console = Console()


class AuthManager:
    """Manages authentication for Xiaohongshu."""

    def __init__(self, browser: BrowserManager):
        """Initialize auth manager.

        Args:
            browser: BrowserManager instance.
        """
        self.browser = browser

    async def check_login_status(self, page: Optional[Page] = None) -> bool:
        """Check if user is currently logged in.

        Args:
            page: Optional existing page to check.

        Returns:
            True if logged in.
        """
        close_page = False
        if page is None:
            page = await self.browser.new_page()
            close_page = True

        try:
            await page.goto(EXPLORE_URL, wait_until="domcontentloaded")
            await random_delay(1.0, 2.0)

            login_btn = await page.query_selector(Selectors.LOGIN_BUTTON)
            is_logged_in = login_btn is None

            if is_logged_in:
                console.print("[green]Already logged in[/green]")
            else:
                console.print("[yellow]Not logged in[/yellow]")

            return is_logged_in

        finally:
            if close_page:
                await page.close()

    async def login_with_phone(self, phone: str) -> bool:
        """Login with phone number and SMS verification code.

        Args:
            phone: Phone number (without country code).

        Returns:
            True if login successful.
        """
        page = await self.browser.new_page()

        try:
            console.print("[blue]Starting phone login...[/blue]")

            await page.goto(EXPLORE_URL, wait_until="domcontentloaded")
            await random_delay(2.0, 3.0)

            login_modal = await page.query_selector(Selectors.PHONE_LOGIN_TEXT)

            if not login_modal:
                login_btn = await page.query_selector(Selectors.LOGIN_BUTTON)
                if login_btn:
                    await login_btn.click()
                    await random_delay(1.0, 2.0)

            await page.wait_for_selector(Selectors.PHONE_LOGIN_TEXT, timeout=15000)

            phone_input = await page.query_selector(Selectors.PHONE_INPUT)
            if phone_input:
                await phone_input.click()
                await random_delay(0.3, 0.5)
                await phone_input.fill(phone)
                await random_delay(0.5, 1.0)

            get_code_btn = await page.query_selector(Selectors.GET_CODE_BUTTON)
            if get_code_btn:
                await get_code_btn.click()
                console.print("[yellow]Verification code sent to your phone[/yellow]")
                await random_delay(1.0, 2.0)

            code = Prompt.ask("[bold cyan]Please enter the verification code[/bold cyan]")

            code_input = await page.query_selector(Selectors.CODE_INPUT)
            if not code_input:
                code_input = await page.query_selector('[aria-label*="验证码"]')
            if code_input:
                await code_input.click()
                await random_delay(0.3, 0.5)
                await code_input.fill(code)
                await random_delay(0.5, 1.0)

            submit_btn = await page.query_selector('.login-container button:has-text("登录")')
            if not submit_btn:
                submit_btn = await page.query_selector('button:has-text("登录"):visible')
            if submit_btn:
                await submit_btn.click()

            try:
                await page.wait_for_selector(
                    Selectors.LOGIN_MODAL, state="hidden", timeout=15000
                )
                await random_delay(2.0, 3.0)

                console.print("[green]Login successful![/green]")
                await self.browser.save_cookies()
                return True

            except Exception:
                console.print("[red]Login failed or timed out[/red]")
                return False

        except Exception as e:
            console.print(f"[red]Login error: {e}[/red]")
            return False

        finally:
            await page.close()

    async def login_with_qrcode(self) -> bool:
        """Login by scanning QR code.

        Returns:
            True if login successful.
        """
        console.print("[blue]Starting QR code login...[/blue]")
        console.print("[yellow]Please scan the QR code with Xiaohongshu app or WeChat[/yellow]")

        page = await self.browser.new_page()

        try:
            await page.goto(EXPLORE_URL, wait_until="domcontentloaded")
            await random_delay(2.0, 3.0)

            login_modal = await page.query_selector(Selectors.LOGIN_MODAL)

            if not login_modal:
                login_btn = await page.query_selector(Selectors.LOGIN_BUTTON)
                if login_btn:
                    await login_btn.click()
                    await random_delay(1.0, 2.0)

            await page.wait_for_selector(Selectors.QR_CODE_TEXT, timeout=15000)

            console.print("[bold cyan]QR code displayed. Please scan with Xiaohongshu app or WeChat.[/bold cyan]")
            console.print("[yellow]Waiting for you to scan... (timeout: 120 seconds)[/yellow]")

            try:
                await page.wait_for_selector(
                    Selectors.LOGIN_MODAL, state="hidden", timeout=120000
                )
                await random_delay(2.0, 3.0)

                console.print("[green]Login successful![/green]")
                await self.browser.save_cookies()
                return True

            except Exception:
                console.print("[red]QR code login timed out or failed[/red]")
                return False

        except Exception as e:
            console.print(f"[red]QR code login error: {e}[/red]")
            return False

        finally:
            await page.close()

    async def logout(self) -> bool:
        """Logout and clear saved cookies.

        Returns:
            True if logout successful.
        """
        try:
            if COOKIE_PATH.exists():
                COOKIE_PATH.unlink()
                console.print("[green]Cookies cleared[/green]")
            return True
        except Exception as e:
            console.print(f"[red]Logout error: {e}[/red]")
            return False
