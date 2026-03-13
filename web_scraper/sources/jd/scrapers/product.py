"""JD product detail scraper using Playwright response interception.

Strategy: Load the product page in a real browser with cookies,
intercept all API responses from api.m.jd.com, and parse the JSON data.
This bypasses the h5st signing mechanism entirely.
"""
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from ..config import (
    BASE_URL,
    CDN_IMAGE_BASE,
    INTERCEPT_FUNCTION_IDS,
    SOURCE_NAME,
    STOCK_STATE,
    Timeouts,
)
from ..cookies import get_cookies_path, netscape_to_playwright
from ..models import (
    CommentInfo,
    CommentSummary,
    PriceInfo,
    ProductAttribute,
    ProductDetail,
    Promotion,
    RecommendedProduct,
    RecommendationResponse,
    SemanticTag,
    ShopInfo,
    SKUDimension,
    SKUVariant,
)

logger = logging.getLogger(__name__)


def extract_sku_id(url_or_id: str) -> str:
    """Extract SKU ID from a JD product URL or raw ID string."""
    # Already a numeric ID
    if url_or_id.isdigit():
        return url_or_id

    # URL pattern: item.jd.com/{skuId}.html
    match = re.search(r"item\.jd\.com/(\d+)", url_or_id)
    if match:
        return match.group(1)

    # Fallback: find any long digit sequence
    match = re.search(r"(\d{8,})", url_or_id)
    if match:
        return match.group(1)

    raise ValueError(f"Cannot extract SKU ID from: {url_or_id}")


def _get_function_id(url: str) -> str | None:
    """Extract functionId from API URL query string."""
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    fid = params.get("functionId", [None])
    return fid[0] if fid else None


def _parse_product_data(data: Dict[str, Any], sku_id: str) -> ProductDetail:
    """Parse pc_detailpage_wareBusiness response into ProductDetail."""
    # Price
    price_data = data.get("price", {})
    final_price_data = price_data.get("finalPrice", {})
    price = PriceInfo(
        current=price_data.get("p"),
        original=price_data.get("op"),
        final=final_price_data.get("price"),
        final_label=final_price_data.get("priceContent"),
    )

    # SKU dimensions
    sku_dims: List[SKUDimension] = []
    color_size = data.get("colorSizeVO", {})
    for dim in color_size.get("colorSizeList", []):
        variants = []
        for btn in dim.get("buttons", []):
            variants.append(SKUVariant(
                sku_id=str(btn.get("skuId", "")),
                text=btn.get("text", ""),
                stock=str(btn.get("stock", "0")),
            ))
        sku_dims.append(SKUDimension(
            title=dim.get("title", ""),
            variants=variants,
        ))

    # Stock state
    stock_info = color_size.get("stockInfo", {})
    sku_stock = stock_info.get(sku_id, {})
    stock_state = sku_stock.get("stockState")
    stock_label = STOCK_STATE.get(str(stock_state)) if stock_state else None

    # Attributes
    attrs: List[ProductAttribute] = []
    attr_vo = data.get("productAttributeVO", {})
    # Try nested attrList format first, then flat labelName/labelValue format
    for attr in attr_vo.get("attributes", []):
        if isinstance(attr, dict):
            # Flat format: {labelName, labelValue}
            name = attr.get("labelName") or attr.get("attrName") or ""
            value = attr.get("labelValue") or attr.get("attrValue") or ""
            if name and value:
                attrs.append(ProductAttribute(name=name, value=value))
            # Nested format: {attrList: [{attrName, attrValue}]}
            for item in attr.get("attrList", []):
                n = item.get("attrName") or item.get("labelName") or ""
                v = item.get("attrValue") or item.get("labelValue") or ""
                if n and v:
                    attrs.append(ProductAttribute(name=n, value=v))

    # Promotions
    promos: List[Promotion] = []
    pref_vo = data.get("preferenceVO", {})
    for label_item in pref_vo.get("sharedLabel", []):
        label = label_item.get("text") or label_item.get("title") or ""
        content = label_item.get("shortText") or label_item.get("value") or label_item.get("content") or ""
        if label or content:
            promos.append(Promotion(label=label, content=content))
    for label_item in pref_vo.get("againSharedLabel", []):
        label = label_item.get("text") or label_item.get("title") or ""
        content = label_item.get("shortText") or label_item.get("value") or label_item.get("content") or ""
        if label or content:
            promos.append(Promotion(label=label, content=content))

    # Shop info
    ware_info = data.get("wareInfoReadMap", {})
    page_config = data.get("pageConfigVO", {})
    shop = ShopInfo(
        shop_id=str(page_config.get("shopId", "")),
        shop_name=ware_info.get("shop_name"),
        vender_id=str(ware_info.get("vender_id", "")),
        is_self=page_config.get("isSelf", False),
    )

    # Images from wareInfoReadMap
    images: List[str] = []
    image_list = ware_info.get("imageList", [])
    if isinstance(image_list, list):
        for img_url in image_list:
            if isinstance(img_url, str) and img_url:
                if img_url.startswith("//"):
                    img_url = "https:" + img_url
                images.append(img_url)

    return ProductDetail(
        sku_id=sku_id,
        url=f"{BASE_URL}/{sku_id}.html",
        name=ware_info.get("sku_name"),
        price=price,
        sku_dimensions=sku_dims,
        stock_state=str(stock_state) if stock_state else None,
        stock_label=stock_label,
        attributes=attrs,
        promotions=promos,
        shop=shop,
        category_ids=ware_info.get("category_ids"),
        images=images,
        raw_data=data,
    )


def _parse_comments_data(data: Dict[str, Any], sku_id: str) -> CommentSummary:
    """Parse getLegoWareDetailComment response into CommentSummary."""
    tags = []
    for tag in data.get("semanticTagList", []):
        tags.append(SemanticTag(
            name=tag.get("name", ""),
            count=str(tag.get("count", "0")),
        ))

    comments = []
    for c in data.get("commentInfoList", []):
        specs = []
        for attr in c.get("wareAttribute", []):
            if isinstance(attr, dict):
                specs.append(attr)
        comments.append(CommentInfo(
            user_name=c.get("userNickName"),
            content=c.get("commentData", ""),
            score=str(c.get("commentScore", "")),
            date=c.get("commentDate"),
            specs=specs,
            pic_count=c.get("pictureCnt", 0),
            area=c.get("publishArea"),
        ))

    return CommentSummary(
        sku_id=sku_id,
        total_count=data.get("allCnt"),
        good_count=data.get("goodCnt"),
        good_rate=data.get("goodRate"),
        pic_count=data.get("showPicCnt"),
        semantic_tags=tags,
        comments=comments,
    )


def _parse_recommendations(data: Any, sku_id: str) -> RecommendationResponse:
    """Parse pctradesoa_diviner response into RecommendationResponse."""
    products = []
    items = data if isinstance(data, list) else data.get("data", []) if isinstance(data, dict) else []

    for item in items:
        if not isinstance(item, dict):
            continue
        img = item.get("img", "")
        if img and not img.startswith("http"):
            img = f"{CDN_IMAGE_BASE}/{img}" if not img.startswith("//") else f"https:{img}"

        price_info = item.get("price", {})
        final_p = price_info.get("finalPrice", {})

        products.append(RecommendedProduct(
            sku_id=str(item.get("sku", "")),
            title=item.get("t", ""),
            image=img,
            price=str(price_info.get("p", "")),
            market_price=str(price_info.get("mp", "")) if price_info.get("mp") else None,
            final_price=str(final_p.get("estimatedPrice", "")) if final_p.get("estimatedPrice") else None,
            brand=item.get("bn"),
            is_self=item.get("isSelfSku", False),
            shop_id=str(item.get("shId", "")) if item.get("shId") else None,
        ))

    return RecommendationResponse(
        sku_id=sku_id,
        products=products,
    )


def _parse_graphic_detail(data: Dict[str, Any]) -> tuple[str | None, List[str]]:
    """Parse pc_item_getWareGraphic response.

    Returns (html_content, image_urls).
    """
    inner = data.get("data", data)
    html = inner.get("graphicContent")
    images: List[str] = []

    if html:
        # Extract image URLs from data-lazyload attributes and src
        for pattern in [r'data-lazyload="([^"]+)"', r'src="(https?://img\d+\.360buyimg\.com[^"]+)"']:
            for match in re.finditer(pattern, html):
                url = match.group(1)
                if url.startswith("//"):
                    url = "https:" + url
                if url not in images:
                    images.append(url)

    return html, images


class ProductScraper:
    """JD product scraper using Playwright response interception.

    Loads the product page in a browser and intercepts API responses
    to extract structured data, bypassing the h5st signing mechanism.
    """

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
        url_or_id: str,
        include_comments: bool = True,
        include_recommendations: bool = False,
        include_graphic: bool = False,
    ) -> ProductDetail:
        """Scrape product detail by URL or SKU ID.

        Args:
            url_or_id: Product URL or SKU ID.
            include_comments: Whether to wait for comment data.
            include_recommendations: Whether to scroll to load recommendations.
            include_graphic: Whether to scroll to load graphic detail.

        Returns:
            ProductDetail with all intercepted data.
        """
        from patchright.sync_api import sync_playwright

        sku_id = extract_sku_id(url_or_id)
        product_url = f"{BASE_URL}/{sku_id}.html"

        # Intercepted API responses
        api_responses: Dict[str, Any] = {}

        def handle_response(response):
            """Intercept API responses from api.m.jd.com."""
            url = response.url
            if "api.m.jd.com" not in url:
                return

            fid = _get_function_id(url)
            if not fid or fid not in INTERCEPT_FUNCTION_IDS:
                return

            try:
                if response.status == 200:
                    body = response.json()
                    api_responses[fid] = body
                    logger.debug(f"Intercepted {fid}: {len(json.dumps(body))} bytes")
            except Exception as e:
                logger.warning(f"Failed to parse response for {fid}: {e}")

        # Load cookies for Playwright
        pw_cookies = netscape_to_playwright(self.cookies_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
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

            # Hide webdriver property
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)

            page.on("response", handle_response)

            # Navigate to product page
            logger.info(f"Loading product page: {product_url}")
            page.goto(product_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)

            # Wait for core API response
            deadline = time.time() + Timeouts.API_WAIT / 1000
            while "pc_detailpage_wareBusiness" not in api_responses and time.time() < deadline:
                page.wait_for_timeout(500)

            # Check for risk redirect
            if "risk_handler" in page.url or "passport.jd.com" in page.url:
                browser.close()
                raise Exception(
                    "JD risk control triggered (CAPTCHA verification required).\n"
                    "Please visit https://item.jd.com in your browser first to pass "
                    "the CAPTCHA, then retry.\n"
                    "If this persists, wait a few minutes or re-import fresh cookies."
                )

            # Wait a bit more for comment data
            if include_comments:
                extra_deadline = time.time() + 3
                while "getLegoWareDetailComment" not in api_responses and time.time() < extra_deadline:
                    page.wait_for_timeout(300)

            # Scroll down to trigger lazy-loaded APIs
            if include_graphic or include_recommendations:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(1500)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(2000)

            browser.close()

        # Parse intercepted data
        if "pc_detailpage_wareBusiness" not in api_responses:
            raise Exception(
                "Failed to intercept product data API. "
                "Page may have loaded incorrectly or cookies are invalid."
            )

        product = _parse_product_data(api_responses["pc_detailpage_wareBusiness"], sku_id)

        # Attach comment data
        if "getLegoWareDetailComment" in api_responses:
            comment_summary = _parse_comments_data(
                api_responses["getLegoWareDetailComment"], sku_id
            )
            # Store as part of raw_data for now
            if product.raw_data is None:
                product.raw_data = {}
            product.raw_data["comment_summary"] = comment_summary.model_dump(mode="json")

        # Attach graphic detail
        if "pc_item_getWareGraphic" in api_responses:
            html, images = _parse_graphic_detail(api_responses["pc_item_getWareGraphic"])
            product.graphic_detail_html = html
            product.graphic_detail_images = images

        # Attach recommendations
        if "pctradesoa_diviner" in api_responses:
            recs = _parse_recommendations(
                api_responses["pctradesoa_diviner"], sku_id
            )
            if product.raw_data is None:
                product.raw_data = {}
            product.raw_data["recommendations"] = recs.model_dump(mode="json")

        logger.info(
            f"Scraped product {sku_id}: {product.name}, "
            f"price={product.price.current}, "
            f"intercepted {len(api_responses)} APIs"
        )

        return product

    def scrape_comments(self, url_or_id: str) -> CommentSummary:
        """Scrape only the comment summary for a product."""
        product = self.scrape(url_or_id, include_comments=True, include_recommendations=False)
        comment_data = (product.raw_data or {}).get("comment_summary")
        if comment_data:
            return CommentSummary(**comment_data)
        return CommentSummary(sku_id=extract_sku_id(url_or_id))

    def scrape_recommendations(self, url_or_id: str) -> RecommendationResponse:
        """Scrape product recommendations ('看了又看')."""
        product = self.scrape(
            url_or_id,
            include_comments=False,
            include_recommendations=True,
        )
        rec_data = (product.raw_data or {}).get("recommendations")
        if rec_data:
            return RecommendationResponse(**rec_data)
        return RecommendationResponse(sku_id=extract_sku_id(url_or_id))
