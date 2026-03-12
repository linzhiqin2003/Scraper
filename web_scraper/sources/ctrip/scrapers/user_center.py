"""Ctrip user center scraper — pure httpx, no browser needed."""
import logging
from pathlib import Path

import httpx

from ..config import (
    CTRIP_RATE_LIMIT,
    DEFAULT_HEADERS,
    MEMBER_SUMMARY_URL,
    AVAILABLE_POINTS_URL,
    MESSAGE_COUNT_URL,
    GRADE_MAP,
    soa2_head,
    retry_on_error,
)
from ..cookies import load_cookies, get_guid
from ..models import AssetSummary, MemberProfile, MessageCount, MessageStat, PointsInfo

logger = logging.getLogger(__name__)


class UserCenterScraper:
    """Scraper for Ctrip user center APIs."""

    def __init__(self, cookies_path: Path | None = None):
        self.cookies = load_cookies(cookies_path)
        self._guid = get_guid(self.cookies)

        from ....core.rate_limiter import RateLimiter, RateLimiterConfig
        self._rate_limiter = RateLimiter(RateLimiterConfig(**CTRIP_RATE_LIMIT))

    def _post(self, url: str, payload: dict) -> dict:
        self._rate_limiter.wait()
        params = {"_fxpcqlniredt": self._guid} if self._guid else {}
        try:
            with httpx.Client(cookies=self.cookies, follow_redirects=True, timeout=15) as client:
                resp = client.post(url, json=payload, headers=DEFAULT_HEADERS, params=params)
                resp.raise_for_status()
                result = resp.json()
                self._rate_limiter.record_success()
                return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_rate_limit()
            raise
        except Exception:
            raise

    def _check_response(self, data: dict, url: str) -> None:
        """Check API response for auth errors and raise appropriate exceptions."""
        # Check SOA2 style response
        ack = data.get("ResponseStatus", {}).get("Ack", "")
        if ack == "Failure":
            errors = data.get("ResponseStatus", {}).get("Errors", [])
            msg = errors[0].get("Message", "") if errors else ""
            if any(kw in msg for kw in ["未登录", "登录", "expired", "unauthorized"]):
                from ....core.exceptions import SessionExpiredError
                raise SessionExpiredError(f"Cookie 已过期：{msg}。请运行 scraper ctrip login 重新登录")
        # Check simple ResultCode style
        code = data.get("ResultCode")
        if code and code not in ("Success", 0):
            msg = data.get("ResultMsg") or data.get("ResultMessage") or "请求失败"
            if any(kw in str(msg) for kw in ["未登录", "登录"]):
                from ....core.exceptions import SessionExpiredError
                raise SessionExpiredError(f"Cookie 已过期：{msg}")

    def _base_payload(self, extra: dict | None = None) -> dict:
        payload = {"head": soa2_head(self._guid)}
        if extra:
            payload.update(extra)
        return payload

    @retry_on_error()
    def get_profile(self) -> MemberProfile:
        """Fetch member summary info."""
        payload = self._base_payload({"channel": "Online", "clientVersion": "99.99"})
        data = self._post(MEMBER_SUMMARY_URL, payload)

        self._check_response(data, MEMBER_SUMMARY_URL)

        ack = data.get("ResponseStatus", {}).get("Ack", "")
        if ack != "Success":
            errors = data.get("ResponseStatus", {}).get("Errors", [])
            msg = errors[0].get("Message", "请求失败") if errors else "请求失败"
            raise RuntimeError(f"获取用户信息失败：{msg}")

        grade = str(data.get("grade", ""))
        avatars = data.get("avatarNameEntities", [])
        avatar_url = avatars[0].get("url") if avatars else None
        assets = [
            AssetSummary(
                asset_type=a.get("assetType", ""),
                balance=a.get("balance", 0),
            )
            for a in data.get("memberAssetSummaries", [])
        ]

        return MemberProfile(
            user_name=data.get("userName", ""),
            grade=grade,
            grade_name=GRADE_MAP.get(grade, f"等级{grade}"),
            svip=data.get("svip", False),
            is_corp=data.get("isCorp", False),
            avatar_url=avatar_url,
            assets=assets,
        )

    @retry_on_error()
    def get_points(self) -> PointsInfo:
        """Fetch available points balance."""
        data = self._post(AVAILABLE_POINTS_URL, self._base_payload())

        self._check_response(data, AVAILABLE_POINTS_URL)

        if data.get("ResultCode") != "Success":
            raise RuntimeError(f"获取积分失败：{data.get('ResultMsg', '未知错误')}")

        return PointsInfo(
            total_available=data.get("TotalAvailable", 0),
            total_balance=data.get("TotalBalance", 0),
            total_pending=data.get("TotalPending", 0),
            is_freeze=data.get("IsFreeze", False),
        )

    @retry_on_error()
    def get_messages(self) -> MessageCount:
        """Fetch unread message counts."""
        payload = self._base_payload({"StartTime": 0})
        data = self._post(MESSAGE_COUNT_URL, payload)

        self._check_response(data, MESSAGE_COUNT_URL)

        if data.get("ResultCode") != 0:
            raise RuntimeError(f"获取消息失败：{data.get('ResultMessage', '未知错误')}")

        stats = [
            MessageStat(
                msg_type=s.get("MsgType", ""),
                status=s.get("Status", ""),
                count=s.get("Count", 0),
                need_prompt=s.get("IsPromptingMsgType", "N") == "Y",
            )
            for s in data.get("StatResults", [])
        ]
        return MessageCount(stats=stats)
