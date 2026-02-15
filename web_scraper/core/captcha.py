"""CAPTCHA solver interface and implementations.

Provides a pluggable abstraction for CAPTCHA solving services.
Sources inject a CaptchaSolver (or the default NullCaptchaSolver) and call
solver.solve(challenge) when a CAPTCHA is detected.
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CaptchaType(Enum):
    """Known CAPTCHA types."""

    RECAPTCHA_V2 = "recaptcha_v2"
    RECAPTCHA_V3 = "recaptcha_v3"
    HCAPTCHA = "hcaptcha"
    IMAGE_TEXT = "image_text"
    SLIDER = "slider"
    CLICK_SELECT = "click_select"
    TURNSTILE = "turnstile"
    CUSTOM = "custom"


@dataclass
class CaptchaChallenge:
    """Data describing a CAPTCHA that needs solving."""

    captcha_type: CaptchaType
    site_url: str
    site_key: Optional[str] = None  # reCAPTCHA / hCaptcha site key
    image_base64: Optional[str] = None  # OCR image data
    extra: Optional[dict] = field(default_factory=dict)  # platform-specific data


@dataclass
class CaptchaSolution:
    """Result returned by a solver."""

    success: bool
    token: Optional[str] = None  # reCAPTCHA / hCaptcha response token
    text: Optional[str] = None  # recognised text (image OCR)
    coordinates: Optional[list] = None  # click coords (click-select / slider)
    error: Optional[str] = None


class CaptchaSolver(ABC):
    """Abstract CAPTCHA solver interface."""

    @abstractmethod
    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        """Attempt to solve the given CAPTCHA challenge."""

    @abstractmethod
    def get_balance(self) -> Optional[float]:
        """Return account balance, or None if unsupported."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable solver name."""


class NullCaptchaSolver(CaptchaSolver):
    """Default no-op solver: logs a warning and returns failure."""

    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        logger.warning(
            "No CAPTCHA solver configured — cannot solve %s at %s",
            challenge.captcha_type.value,
            challenge.site_url,
        )
        return CaptchaSolution(
            success=False,
            error="No CAPTCHA solver configured",
        )

    def get_balance(self) -> Optional[float]:
        return None

    @property
    def name(self) -> str:
        return "NullCaptchaSolver"


class TwoCaptchaSolver(CaptchaSolver):
    """2Captcha / rucaptcha implementation.

    Supports reCAPTCHA v2/v3, hCaptcha, image OCR, and Turnstile.
    Flow: submit task → poll for result.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://2captcha.com",
        timeout: int = 120,
        polling_interval: float = 5.0,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url.rstrip("/")
        self._timeout = timeout
        self._polling_interval = polling_interval

    @property
    def name(self) -> str:
        return "TwoCaptchaSolver"

    def solve(self, challenge: CaptchaChallenge) -> CaptchaSolution:
        import httpx

        try:
            task_id = self._submit(challenge)
            if not task_id:
                return CaptchaSolution(success=False, error="Failed to submit task")
            return self._poll(task_id, challenge.captcha_type)
        except Exception as e:
            logger.error("TwoCaptcha solve error: %s", e)
            return CaptchaSolution(success=False, error=str(e))

    def get_balance(self) -> Optional[float]:
        import httpx

        try:
            resp = httpx.get(
                f"{self._api_url}/res.php",
                params={"key": self._api_key, "action": "getbalance", "json": 1},
                timeout=10.0,
            )
            data = resp.json()
            if data.get("status") == 1:
                return float(data["request"])
        except Exception as e:
            logger.warning("Failed to get 2Captcha balance: %s", e)
        return None

    # ------------------------------------------------------------------

    def _submit(self, challenge: CaptchaChallenge) -> Optional[str]:
        import httpx

        params: dict = {"key": self._api_key, "json": 1}

        if challenge.captcha_type in (
            CaptchaType.RECAPTCHA_V2,
            CaptchaType.RECAPTCHA_V3,
        ):
            params.update(
                {
                    "method": "userrecaptcha",
                    "googlekey": challenge.site_key,
                    "pageurl": challenge.site_url,
                }
            )
            if challenge.captcha_type == CaptchaType.RECAPTCHA_V3:
                params["version"] = "v3"
                params["action"] = challenge.extra.get("action", "verify") if challenge.extra else "verify"

        elif challenge.captcha_type == CaptchaType.HCAPTCHA:
            params.update(
                {
                    "method": "hcaptcha",
                    "sitekey": challenge.site_key,
                    "pageurl": challenge.site_url,
                }
            )

        elif challenge.captcha_type == CaptchaType.TURNSTILE:
            params.update(
                {
                    "method": "turnstile",
                    "sitekey": challenge.site_key,
                    "pageurl": challenge.site_url,
                }
            )

        elif challenge.captcha_type == CaptchaType.IMAGE_TEXT:
            params.update(
                {
                    "method": "base64",
                    "body": challenge.image_base64,
                }
            )

        else:
            return None

        resp = httpx.post(
            f"{self._api_url}/in.php", data=params, timeout=30.0
        )
        data = resp.json()
        if data.get("status") == 1:
            return data["request"]

        logger.warning("2Captcha submit failed: %s", data)
        return None

    def _poll(
        self, task_id: str, captcha_type: CaptchaType
    ) -> CaptchaSolution:
        import httpx

        deadline = time.monotonic() + self._timeout
        while time.monotonic() < deadline:
            time.sleep(self._polling_interval)
            resp = httpx.get(
                f"{self._api_url}/res.php",
                params={
                    "key": self._api_key,
                    "action": "get",
                    "id": task_id,
                    "json": 1,
                },
                timeout=10.0,
            )
            data = resp.json()

            if data.get("status") == 1:
                answer = data["request"]
                if captcha_type == CaptchaType.IMAGE_TEXT:
                    return CaptchaSolution(success=True, text=answer)
                return CaptchaSolution(success=True, token=answer)

            if data.get("request") != "CAPCHA_NOT_READY":
                return CaptchaSolution(
                    success=False, error=data.get("request", "unknown")
                )

        return CaptchaSolution(success=False, error="Timeout waiting for solution")
