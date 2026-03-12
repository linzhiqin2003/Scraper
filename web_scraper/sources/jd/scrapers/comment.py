"""JD product comment scraper.

Two strategies:
1. API mode (default): Use SignatureOracle to generate h5st signatures,
   then call getCommentListPage API directly with httpx. Fast, supports
   full pagination, and minimizes browser exposure.

2. Playwright mode (fallback): Open the product page, click "全部评价",
   scroll the popup to trigger infinite-scroll pagination, and intercept
   responses. More resource-heavy but works even if API mode fails.
"""
import json
import logging
import time
from math import ceil
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import httpx

from ..config import BASE_URL, Timeouts
from ..cookies import get_cookies_path, load_cookies, netscape_to_playwright
from ..models import CommentInfo, CommentSummary, SemanticTag

logger = logging.getLogger(__name__)

# Comment type filters
COMMENT_TYPE = {
    "all": "0",
    "bad": "1",
    "medium": "2",
    "good": "3",
    "pic": "4",
    "append": "5",
}

SORT_TYPE = {
    "default": "5",
    "time": "6",
}


def _extract_function_id(response) -> str | None:
    """Extract functionId from response's request URL or POST body."""
    url = response.url
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    for key in ("functionId", "fid"):
        fid = params.get(key, [None])
        if fid and fid[0]:
            return fid[0]
    if response.request.method == "POST":
        post_data = response.request.post_data or ""
        if post_data:
            body_params = parse_qs(post_data)
            fid = body_params.get("functionId", [None])
            if fid and fid[0]:
                return fid[0]
    return None


def _find_in_floors(floors: List[Dict], target_mid: str) -> Dict | None:
    """Recursively search floors and subFloors for a specific mId."""
    for floor in floors:
        if floor.get("mId") == target_mid:
            return floor
        sub = floor.get("subFloors", [])
        if sub:
            result = _find_in_floors(sub, target_mid)
            if result:
                return result
    return None


def _parse_comment_floor(floors: List[Dict]) -> tuple[List[CommentInfo], List[SemanticTag], str | None]:
    """Parse comment data from getCommentListPage floor structure."""
    comments = []
    tags = []
    total_count = None

    list_floor = _find_in_floors(floors, "commentlist-list")
    if list_floor:
        for item in list_floor.get("data", []):
            ci = item.get("commentInfo", item)
            specs = [a for a in ci.get("wareAttribute", []) if isinstance(a, dict)]
            pic_count = len(ci.get("pictureInfoList", []))
            comments.append(CommentInfo(
                user_name=ci.get("userNickName"),
                content=ci.get("tagCommentContent") or ci.get("content", ""),
                score=str(ci.get("commentScore", "")),
                date=ci.get("commentDate"),
                specs=specs,
                pic_count=pic_count,
                area=None,
            ))

    common_floor = _find_in_floors(floors, "commentlist-commonlabel")
    if common_floor:
        for tag in common_floor.get("data", {}).get("generalTagList", []):
            ident = tag.get("identification", "")
            if ident == "ALL":
                total_count = tag.get("count")
            elif ident not in ("SHAITU", "YOUTU"):
                name = tag.get("name", "")
                count = tag.get("count", "0")
                if name and count != "0":
                    tags.append(SemanticTag(name=name, count=str(count)))

    if total_count is None:
        mix_floor = _find_in_floors(floors, "commentlist-mixlabel")
        if mix_floor:
            for tag in mix_floor.get("data", {}).get("mixTagList", []):
                if tag.get("identification") == "ALL":
                    total_count = tag.get("count")
                    break

    return comments, tags, total_count


class CommentScraper:
    """JD comment scraper with API mode (h5st oracle) and Playwright fallback."""

    def __init__(self, cookies_path: Path | None = None):
        if cookies_path is None:
            cookies_path = get_cookies_path()
        if not cookies_path.exists():
            raise FileNotFoundError(
                f"Cookies file not found: {cookies_path}\n"
                f"Run 'scraper jd import-cookies <path>' first."
            )
        self.cookies_path = cookies_path

    def scrape(
        self,
        sku_id: str,
        max_pages: int | None = None,
        max_comments: int | None = None,
        score: str = "all",
        sort: str = "default",
        has_picture: bool = False,
        delay: float = 1.0,
        on_progress=None,
        strategy: str = "api",
        oracle=None,
    ) -> CommentSummary:
        """Scrape comments.

        Args:
            sku_id: Product SKU ID.
            max_pages: Max pages to fetch (10 comments per page).
            max_comments: Max comments to collect.
            score: Filter: all, good, medium, bad, pic, append.
            sort: Sort: default, time.
            has_picture: Only comments with pictures (same as score='pic').
            delay: Delay between requests (seconds).
            on_progress: Optional callback(page, total, count).
            strategy: 'api' (h5st oracle + httpx) or 'playwright' (browser interception).
            oracle: Optional pre-initialized SignatureOracle to reuse (api strategy only).
        """
        if has_picture:
            score = "pic"

        if strategy == "api":
            return self._scrape_api(
                sku_id, max_pages, max_comments, score, sort, delay, on_progress,
                oracle=oracle,
            )
        else:
            return self._scrape_playwright(
                sku_id, max_pages, max_comments, delay, on_progress
            )

    def _scrape_api(
        self,
        sku_id: str,
        max_pages: int | None,
        max_comments: int | None,
        score: str,
        sort: str,
        delay: float,
        on_progress,
        oracle=None,
    ) -> CommentSummary:
        """Scrape using Playwright SignatureOracle + httpx.

        Args:
            oracle: Optional pre-initialized SignatureOracle to reuse.
                    If None, a new one is created and managed internally.
        """
        from ..h5st import SignatureOracle

        http_cookies = load_cookies(self.cookies_path)

        if oracle is not None:
            return self._scrape_api_with_oracle(
                oracle, http_cookies, sku_id, max_pages, max_comments,
                score, sort, delay, on_progress,
            )

        with SignatureOracle(self.cookies_path) as new_oracle:
            return self._scrape_api_with_oracle(
                new_oracle, http_cookies, sku_id, max_pages, max_comments,
                score, sort, delay, on_progress,
            )

    def _scrape_api_with_oracle(
        self,
        oracle,
        http_cookies,
        sku_id: str,
        max_pages: int | None,
        max_comments: int | None,
        score: str,
        sort: str,
        delay: float,
        on_progress,
    ) -> CommentSummary:
        """Core API scraping logic using a pre-initialized SignatureOracle."""
        uuid = oracle.uuid or ""
        all_comments: List[CommentInfo] = []
        all_tags: List[SemanticTag] = []
        total_count: str | None = None
        first_guid: str | None = None

        score_type = COMMENT_TYPE.get(score, "0")
        sort_type = SORT_TYPE.get(sort, "5")

        page_num = 1
        effective_max = max_pages

        while True:
            body_obj = {
                "requestSource": "pc",
                "shopComment": 0,
                "sameComment": 0,
                "channel": None,
                "extInfo": {
                    "isQzc": "0",
                    "spuId": sku_id,
                    "commentRate": "1",
                    "needTopAlbum": "1",
                    "bbtf": "",
                    "userGroupComment": "1",
                },
                "num": "10",
                "pictureCommentType": "A",
                "scval": None,
                "shadowMainSku": "0",
                "shopType": "0",
                "sku": sku_id,
                "category": "",
                "shieldCurrentComment": "1",
                "pageSize": "10",
                "isFirstRequest": page_num == 1,
                "isCurrentSku": False,
                "sortType": sort_type,
                "tagId": "",
                "tagType": "",
                "type": score_type,
                "pageNum": str(page_num),
            }
            if page_num > 1:
                body_obj["style"] = "1"
            if first_guid:
                body_obj["firstCommentGuid"] = first_guid

            body_json = json.dumps(body_obj)

            params_to_sign = {
                "functionId": "getCommentListPage",
                "appid": "pc-rate-qa",
                "client": "pc",
                "clientVersion": "1.0.0",
                "body": body_json,
                "t": str(int(time.time() * 1000)),
                "loginType": "3",
                "uuid": uuid,
            }

            signed = oracle.sign(params_to_sign)

            form_data = {
                k: str(v) if not isinstance(v, str) else v
                for k, v in signed.items()
                if v is not None
            }

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Referer": "https://item.jd.com/",
                "Origin": "https://item.jd.com",
                "Content-Type": "application/x-www-form-urlencoded",
                "x-referer-page": f"https://item.jd.com/{sku_id}.html",
                "x-rp-client": "h5_1.0.0",
                "Accept": "application/json, text/plain, */*",
            }

            with httpx.Client(
                cookies=http_cookies, follow_redirects=True, timeout=15.0
            ) as client:
                resp = client.post(
                    "https://api.m.jd.com/client.action",
                    data=form_data,
                    headers=headers,
                )

            if resp.status_code != 200:
                raise Exception(f"API returned {resp.status_code}")

            data = resp.json()
            if data.get("code") not in (0, "0"):
                raise Exception(f"API error: {data.get('code')} - {data.get('msg', '')}")

            floors = data.get("result", {}).get("floors", [])
            comments, tags, count = _parse_comment_floor(floors)

            if not comments:
                logger.info(f"No comments on page {page_num}, stopping")
                break

            all_comments.extend(comments)
            logger.info(f"Page {page_num}: {len(comments)} comments (total: {len(all_comments)})")

            if page_num == 1 and not first_guid:
                list_floor = _find_in_floors(floors, "commentlist-list")
                if list_floor and list_floor.get("data"):
                    first_item = list_floor["data"][0]
                    ci = first_item.get("commentInfo", first_item)
                    first_guid = ci.get("guid")

            if tags and not all_tags:
                all_tags.extend(tags)
            if count and total_count is None:
                total_count = count
                try:
                    total_int = int(count.replace("+", ""))
                    calc_max = ceil(total_int / 10)
                    if effective_max is None:
                        effective_max = calc_max
                    else:
                        effective_max = min(effective_max, calc_max)
                except ValueError:
                    pass

            if on_progress:
                on_progress(page_num, effective_max, len(all_comments))

            if max_comments and len(all_comments) >= max_comments:
                break
            if effective_max and page_num >= effective_max:
                break

            page_num += 1
            time.sleep(delay)

        if max_comments:
            all_comments = all_comments[:max_comments]

        good_count = None
        for tag in all_tags:
            if "好评" in tag.name:
                good_count = tag.count
                break
        good_rate = None
        if total_count and good_count:
            try:
                t = int(total_count.replace("+", ""))
                g = int(good_count.replace("+", ""))
                if t > 0:
                    good_rate = f"{g * 100 // t}%"
            except ValueError:
                pass

        return CommentSummary(
            sku_id=sku_id,
            total_count=total_count,
            good_count=good_count,
            good_rate=good_rate,
            semantic_tags=all_tags,
            comments=all_comments,
        )

    def _scrape_playwright(
        self,
        sku_id: str,
        max_pages: int | None,
        max_comments: int | None,
        delay: float,
        on_progress,
    ) -> CommentSummary:
        """Fallback: scrape using Playwright popup interception."""
        from playwright.sync_api import sync_playwright

        product_url = f"{BASE_URL}/{sku_id}.html"
        all_comments: List[CommentInfo] = []
        all_tags: List[SemanticTag] = []
        total_count_holder: List[str | None] = [None]
        pages_loaded_holder: List[int] = [0]

        def handle_response(response):
            url = response.url
            if "api.m.jd.com" not in url:
                return
            fid = _extract_function_id(response)
            if fid != "getCommentListPage":
                return
            try:
                if response.status == 200:
                    data = response.json()
                    floors = data.get("result", {}).get("floors", [])
                    comments, tags, count = _parse_comment_floor(floors)
                    if comments:
                        all_comments.extend(comments)
                        pages_loaded_holder[0] += 1
                    if tags and not all_tags:
                        all_tags.extend(tags)
                    if count and total_count_holder[0] is None:
                        total_count_holder[0] = count
            except Exception as e:
                logger.warning(f"Failed to parse comment response: {e}")

        pw_cookies = netscape_to_playwright(self.cookies_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            context.add_cookies(pw_cookies)
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.on("response", handle_response)

            page.goto(product_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(4000)

            if "risk_handler" in page.url or "passport.jd.com" in page.url:
                browser.close()
                raise Exception(
                    "JD risk control triggered. Visit https://item.jd.com in your browser "
                    "to pass CAPTCHA, then retry."
                )

            # Click comment popup
            for selector in ["text=全部评价", ".all-btn", "text=商品评价"]:
                try:
                    el = page.locator(selector).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        break
                except Exception:
                    continue
            else:
                browser.close()
                raise Exception("Could not find comment button.")

            # Wait for first page
            deadline = time.time() + 15
            while pages_loaded_holder[0] == 0 and time.time() < deadline:
                page.wait_for_timeout(500)

            if pages_loaded_holder[0] == 0:
                browser.close()
                raise Exception("No comment data intercepted.")

            page.wait_for_timeout(3000)

            # Calculate target
            effective_max = None
            tc = total_count_holder[0]
            if tc:
                try:
                    effective_max = ceil(int(tc.replace("+", "")) / 10)
                except ValueError:
                    pass
            if max_pages:
                effective_max = min(max_pages, effective_max) if effective_max else max_pages

            # Scroll to load more
            scroll_fails = 0
            while True:
                if max_comments and len(all_comments) >= max_comments:
                    break
                if effective_max and pages_loaded_holder[0] >= effective_max:
                    break

                prev = len(all_comments)
                page.evaluate("""() => {
                    const sels = ['[class*="rateListContainer"]', '[class*="rate-list"]',
                                  '.jdc-page-overlay [class*="container"]', '.jdc-page-overlay'];
                    for (const s of sels) {
                        const el = document.querySelector(s);
                        if (el && el.scrollHeight > el.clientHeight) {
                            el.scrollTo(0, el.scrollHeight); return;
                        }
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                }""")
                time.sleep(delay)
                page.wait_for_timeout(1000)

                if len(all_comments) == prev:
                    scroll_fails += 1
                    if scroll_fails >= 3:
                        break
                else:
                    scroll_fails = 0
                    if on_progress:
                        on_progress(pages_loaded_holder[0], effective_max, len(all_comments))

            browser.close()

        if max_comments:
            all_comments = all_comments[:max_comments]

        good_count = None
        for tag in all_tags:
            if "好评" in tag.name:
                good_count = tag.count
                break
        good_rate = None
        tc = total_count_holder[0]
        if tc and good_count:
            try:
                t = int(tc.replace("+", ""))
                g = int(good_count.replace("+", ""))
                if t > 0:
                    good_rate = f"{g * 100 // t}%"
            except ValueError:
                pass

        return CommentSummary(
            sku_id=sku_id,
            total_count=tc,
            good_count=good_count,
            good_rate=good_rate,
            semantic_tags=all_tags,
            comments=all_comments,
        )
