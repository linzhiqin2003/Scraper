"""WeChat MP platform API scraper.

Searches public accounts by name, fetches their article lists via
the mp.weixin.qq.com backend API (requires login cookies + token).
"""
import hashlib
import json
import logging
import random
import re
import time
from typing import Optional

from ....core.http_client import HttpClient
from ..config import (
    MP_API_BASE,
    MP_HEADERS,
    RATE_LIMIT_DELAY,
    get_cookies_from_file,
)
from ..models import WechatAccount, WechatArticleBrief, WechatSearchResponse

logger = logging.getLogger(__name__)


class MPPlatformScraper:
    """Scraper for WeChat MP platform backend APIs.

    Requires MP platform cookies (slave_sid, bizuin, etc.) and a session token.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        cookies: Optional[dict[str, str]] = None,
        fingerprint: Optional[str] = None,
    ):
        self._cookies = cookies or get_cookies_from_file()
        self._fingerprint = fingerprint or hashlib.md5(
            str(random.random()).encode()
        ).hexdigest()
        self._client = HttpClient(
            cookies=self._cookies,
            headers=dict(MP_HEADERS),
            timeout=30,
        )
        self._last_request_time = 0.0
        self._token = token or self._fetch_token()

    def _fetch_token(self) -> str:
        """Auto-extract session token by visiting MP homepage.

        The MP homepage redirects to a URL containing the token parameter:
        https://mp.weixin.qq.com/cgi-bin/home?...&token=1122555813
        """
        if not self._cookies.get("slave_sid"):
            return ""
        try:
            resp = self._client.get(
                "https://mp.weixin.qq.com/",
                headers={
                    "accept": "text/html,application/xhtml+xml",
                    "accept-language": "zh-CN,zh;q=0.9",
                },
            )
            m = re.search(r"token=(\d+)", str(resp.url))
            if m:
                token = m.group(1)
                logger.debug("Auto-extracted token: %s", token)
                return token
        except Exception as e:
            logger.warning("Failed to auto-extract token: %s", e)
        return ""

    def is_configured(self) -> bool:
        """Check if cookies and token are available."""
        return bool(self._token and self._cookies.get("slave_sid"))

    def search_account(
        self, query: str, count: int = 5, begin: int = 0
    ) -> list[WechatAccount]:
        """Search for public accounts by name or WeChat ID.

        Args:
            query: Account name or WeChat ID.
            count: Results per page (default 5).
            begin: Pagination offset.

        Returns:
            List of matching accounts.
        """
        self._rate_limit()
        resp = self._client.get(
            f"{MP_API_BASE}/searchbiz",
            params={
                "action": "search_biz",
                "query": query,
                "begin": begin,
                "count": count,
                "fingerprint": self._fingerprint,
                "token": self._token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
            },
        )
        self._client.raise_for_status(resp, context="searchbiz")
        data = resp.json()

        self._check_base_resp(data)

        accounts = []
        for item in data.get("list", []):
            accounts.append(WechatAccount(
                fakeid=item["fakeid"],
                nickname=item.get("nickname", ""),
                alias=item.get("alias", ""),
                round_head_img=item.get("round_head_img", ""),
                service_type=item.get("service_type", 0),
                signature=item.get("signature", ""),
                verify_status=item.get("verify_status", 0),
            ))
        return accounts

    def get_articles(
        self,
        fakeid: str,
        count: int = 5,
        begin: int = 0,
    ) -> WechatSearchResponse:
        """Get article list for a public account.

        Args:
            fakeid: Account fakeid (Base64-encoded bizuin).
            count: Articles per page (default 5).
            begin: Pagination offset.

        Returns:
            WechatSearchResponse with articles and pagination info.
        """
        self._rate_limit()
        resp = self._client.get(
            f"{MP_API_BASE}/appmsgpublish",
            params={
                "sub": "list",
                "search_field": "null",
                "begin": begin,
                "count": count,
                "query": "",
                "fakeid": fakeid,
                "type": "101_1",
                "free_publish_type": "1",
                "sub_action": "list_ex",
                "fingerprint": self._fingerprint,
                "token": self._token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
            },
        )
        self._client.raise_for_status(resp, context="appmsgpublish list")
        data = resp.json()

        self._check_base_resp(data)
        return self._parse_publish_response(data)

    def search_articles(
        self,
        fakeid: str,
        query: str,
        count: int = 5,
        begin: int = 0,
    ) -> WechatSearchResponse:
        """Search articles by title within a specific account.

        Args:
            fakeid: Account fakeid.
            query: Title search keyword.
            count: Results per page (default 5).
            begin: Pagination offset.

        Returns:
            WechatSearchResponse with matching articles.
        """
        self._rate_limit()
        resp = self._client.get(
            f"{MP_API_BASE}/appmsgpublish",
            params={
                "sub": "search",
                "search_field": "7",
                "begin": begin,
                "count": count,
                "query": query,
                "fakeid": fakeid,
                "type": "101_1",
                "free_publish_type": "1",
                "sub_action": "list_ex",
                "fingerprint": self._fingerprint,
                "token": self._token,
                "lang": "zh_CN",
                "f": "json",
                "ajax": "1",
            },
        )
        self._client.raise_for_status(resp, context="appmsgpublish search")
        data = resp.json()

        self._check_base_resp(data)
        return self._parse_publish_response(data)

    def _parse_publish_response(self, data: dict) -> WechatSearchResponse:
        """Parse the triple-nested JSON from appmsgpublish responses."""
        publish_page_str = data.get("publish_page", "{}")
        try:
            publish_page = json.loads(publish_page_str)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse publish_page JSON")
            return WechatSearchResponse()

        total_count = publish_page.get("total_count", 0)
        publish_count = publish_page.get("publish_count", 0)

        articles = []
        for item in publish_page.get("publish_list", []):
            publish_info_str = item.get("publish_info", "{}")
            try:
                publish_info = json.loads(publish_info_str)
            except (json.JSONDecodeError, TypeError):
                continue

            for article in publish_info.get("appmsgex", []):
                articles.append(WechatArticleBrief(
                    aid=article.get("aid", ""),
                    title=article.get("title", ""),
                    link=article.get("link", ""),
                    digest=article.get("digest", ""),
                    cover=article.get("cover", ""),
                    update_time=article.get("update_time", 0),
                    appmsgid=article.get("appmsgid", 0),
                    itemidx=article.get("itemidx", 0),
                    author_name=article.get("author_name", ""),
                    copyright_type=article.get("copyright_type", 0),
                ))

        return WechatSearchResponse(
            articles=articles,
            total_count=total_count,
            publish_count=publish_count,
        )

    @staticmethod
    def _check_base_resp(data: dict) -> None:
        """Check API response for errors."""
        base_resp = data.get("base_resp", {})
        ret = base_resp.get("ret", -1)
        if ret != 0:
            err_msg = base_resp.get("err_msg", "unknown error")
            if ret == 200003:
                raise RuntimeError(f"会话已过期 (ret={ret}), 请重新导入 cookies 和 token")
            if ret == 200002:
                raise RuntimeError(f"参数错误 (ret={ret}): {err_msg}")
            raise RuntimeError(f"API 错误 (ret={ret}): {err_msg}")

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.monotonic()
