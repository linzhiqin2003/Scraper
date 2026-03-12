"""Data models for JD (京东) scraper."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class PriceInfo(BaseModel):
    """Product price information."""

    current: Optional[str] = Field(default=None, description="Current price")
    original: Optional[str] = Field(default=None, description="Original price")
    final: Optional[str] = Field(default=None, description="Final price after coupons")
    final_label: Optional[str] = Field(default=None, description="Final price label (e.g. '到手价')")


class SKUVariant(BaseModel):
    """A single SKU variant (color/size combination)."""

    sku_id: str = Field(description="SKU ID")
    text: str = Field(description="Display text (e.g. '2XL 140-160斤')")
    stock: str = Field(default="0", description="Stock indicator")


class SKUDimension(BaseModel):
    """A SKU dimension (e.g. color, size)."""

    title: str = Field(description="Dimension name (e.g. '颜色', '尺码')")
    variants: List[SKUVariant] = Field(default_factory=list, description="Variants in this dimension")


class ProductAttribute(BaseModel):
    """Product attribute (e.g. brand, material)."""

    name: str = Field(description="Attribute name")
    value: str = Field(description="Attribute value")


class Promotion(BaseModel):
    """Promotion/discount information."""

    label: str = Field(description="Promotion label")
    content: str = Field(default="", description="Promotion detail")


class ShopInfo(BaseModel):
    """Shop/seller information."""

    shop_id: Optional[str] = Field(default=None, description="Shop ID")
    shop_name: Optional[str] = Field(default=None, description="Shop name")
    vender_id: Optional[str] = Field(default=None, description="Vendor ID")
    is_self: bool = Field(default=False, description="Whether JD self-operated")


class ProductDetail(BaseModel):
    """Full product detail."""

    sku_id: str = Field(description="Product SKU ID")
    url: str = Field(description="Product URL")
    name: Optional[str] = Field(default=None, description="Product name")
    price: PriceInfo = Field(default_factory=PriceInfo, description="Price info")
    sku_dimensions: List[SKUDimension] = Field(default_factory=list, description="SKU dimensions (color/size)")
    stock_state: Optional[str] = Field(default=None, description="Stock state code")
    stock_label: Optional[str] = Field(default=None, description="Stock state label")
    attributes: List[ProductAttribute] = Field(default_factory=list, description="Product attributes")
    promotions: List[Promotion] = Field(default_factory=list, description="Active promotions")
    shop: ShopInfo = Field(default_factory=ShopInfo, description="Shop info")
    category_ids: Optional[str] = Field(default=None, description="Category IDs (comma-separated)")
    images: List[str] = Field(default_factory=list, description="Product image URLs")
    graphic_detail_html: Optional[str] = Field(default=None, description="Graphic detail HTML content")
    graphic_detail_images: List[str] = Field(default_factory=list, description="Image URLs from graphic detail")
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Raw API response data")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")

    @computed_field
    @property
    def product_url(self) -> str:
        """Canonical product URL."""
        return f"https://item.jd.com/{self.sku_id}.html"

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class CommentInfo(BaseModel):
    """A single product comment/review."""

    user_name: Optional[str] = Field(default=None, description="User nickname")
    content: str = Field(default="", description="Comment text")
    score: Optional[str] = Field(default=None, description="Rating score (1-5)")
    date: Optional[str] = Field(default=None, description="Comment date")
    specs: List[Dict[str, str]] = Field(default_factory=list, description="Purchased specs (color/size)")
    pic_count: int = Field(default=0, description="Number of pictures")
    area: Optional[str] = Field(default=None, description="User province")


class SemanticTag(BaseModel):
    """Comment semantic tag."""

    name: str = Field(description="Tag name (e.g. '物流速度快')")
    count: str = Field(default="0", description="Tag count")


class CommentSummary(BaseModel):
    """Product comment summary with sample reviews."""

    sku_id: str = Field(description="Product SKU ID")
    total_count: Optional[str] = Field(default=None, description="Total comment count")
    good_count: Optional[str] = Field(default=None, description="Good review count")
    good_rate: Optional[str] = Field(default=None, description="Good review rate")
    pic_count: Optional[str] = Field(default=None, description="Comments with pictures")
    semantic_tags: List[SemanticTag] = Field(default_factory=list, description="Semantic tags")
    comments: List[CommentInfo] = Field(default_factory=list, description="Sample comments")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class SearchProduct(BaseModel):
    """A product from search results."""

    sku_id: str = Field(description="Product SKU ID")
    name: str = Field(default="", description="Product name")
    price: Optional[str] = Field(default=None, description="Current price")
    image_url: Optional[str] = Field(default=None, description="Product image URL")
    shop_id: Optional[str] = Field(default=None, description="Shop ID")
    shop_name: Optional[str] = Field(default=None, description="Shop name")
    brand: Optional[str] = Field(default=None, description="Brand name")
    brand_id: Optional[str] = Field(default=None, description="Brand ID")
    comment_count: Optional[str] = Field(default=None, description="Comment count")
    average_score: Optional[str] = Field(default=None, description="Average rating (1-5)")
    subtitle: Optional[str] = Field(default=None, description="Subtitle / spec description")
    is_plus_shop: bool = Field(default=False, description="Whether PLUS shop")
    category_ids: Optional[str] = Field(default=None, description="Category IDs (cid1/cid2/cid3)")

    @computed_field
    @property
    def url(self) -> str:
        return f"https://item.jd.com/{self.sku_id}.html"


class SearchResult(BaseModel):
    """Search result summary."""

    keyword: str = Field(description="Search keyword")
    normalized_keyword: Optional[str] = Field(default=None, description="Server-normalized keyword")
    total_count: Optional[int] = Field(default=None, description="Total result count")
    products: List[SearchProduct] = Field(default_factory=list, description="Product list")
    page: int = Field(default=1, description="Current page")
    pages_fetched: int = Field(default=0, description="Number of pages fetched")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class RecommendedProduct(BaseModel):
    """A recommended product from '看了又看'."""

    sku_id: str = Field(description="SKU ID")
    title: str = Field(default="", description="Product title")
    image: Optional[str] = Field(default=None, description="Product image URL")
    price: Optional[str] = Field(default=None, description="Current price")
    market_price: Optional[str] = Field(default=None, description="Market price")
    final_price: Optional[str] = Field(default=None, description="Estimated final price")
    brand: Optional[str] = Field(default=None, description="Brand name")
    is_self: bool = Field(default=False, description="Whether JD self-operated")
    shop_id: Optional[str] = Field(default=None, description="Shop ID")

    @computed_field
    @property
    def url(self) -> str:
        return f"https://item.jd.com/{self.sku_id}.html"


class RecommendationResponse(BaseModel):
    """Response for product recommendations."""

    sku_id: str = Field(description="Source SKU ID")
    products: List[RecommendedProduct] = Field(default_factory=list, description="Recommended products")
    page: int = Field(default=1, description="Current page")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }
