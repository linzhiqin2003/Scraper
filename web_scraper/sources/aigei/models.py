"""Data models for Aigei GIF source."""
from typing import List, Optional

from pydantic import BaseModel, Field


class GifItem(BaseModel):
    """A single GIF resource from Aigei."""

    itemid: str = Field(description="资源 ID")
    item_code: str = Field(default="", description="资源编码")
    title: str = Field(default="", description="资源标题")
    detail_url: str = Field(default="", description="详情页 URL")
    img_url: str = Field(default="", description="图片 URL")
    is_vip: bool = Field(default=False, description="是否 VIP 资源")


class GifSearchResult(BaseModel):
    """Search result containing multiple GIF items."""

    keyword: str = Field(description="搜索关键词")
    total_pages: int = Field(default=1, description="总页数")
    items: List[GifItem] = Field(default_factory=list, description="资源列表")

    @property
    def free_count(self) -> int:
        return sum(1 for it in self.items if not it.is_vip)

    @property
    def vip_count(self) -> int:
        return sum(1 for it in self.items if it.is_vip)
