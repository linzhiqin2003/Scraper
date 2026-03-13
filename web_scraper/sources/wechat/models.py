"""Data models for WeChat Official Accounts."""
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WechatAccount(BaseModel):
    """微信公众号账号信息。"""
    fakeid: str = Field(description="公众号 fakeid (Base64 编码的 bizuin)")
    nickname: str = Field(description="公众号名称")
    alias: str = Field(default="", description="微信号 (英文 ID)")
    round_head_img: str = Field(default="", description="头像 URL")
    service_type: int = Field(default=0, description="账号类型: 1=订阅号, 2=服务号")
    signature: str = Field(default="", description="简介")
    verify_status: int = Field(default=0, description="认证状态: 2=已认证")


class WechatArticleBrief(BaseModel):
    """微信公众号文章摘要 (来自 MP 平台 API)。"""
    aid: str = Field(default="", description="文章唯一 ID")
    title: str = Field(description="文章标题")
    link: str = Field(default="", description="文章 URL")
    digest: str = Field(default="", description="文章摘要")
    cover: str = Field(default="", description="封面图 URL")
    update_time: int = Field(default=0, description="更新时间戳")
    appmsgid: int = Field(default=0, description="图文消息 ID")
    itemidx: int = Field(default=0, description="文章在群发中的位置索引")
    author_name: str = Field(default="", description="作者名")
    copyright_type: int = Field(default=0, description="版权类型: 0=无, 1=原创")

    @property
    def clean_title(self) -> str:
        """去除搜索高亮标签的标题。"""
        return re.sub(r'</?em[^>]*>', '', self.title)

    @property
    def update_datetime(self) -> Optional[datetime]:
        if self.update_time:
            return datetime.fromtimestamp(self.update_time)
        return None


class WechatSearchResponse(BaseModel):
    """公众号文章列表搜索响应。"""
    articles: List[WechatArticleBrief] = Field(default_factory=list)
    total_count: int = Field(default=0, description="总文章数")
    publish_count: int = Field(default=0, description="可翻页的发表数")


class WechatArticle(BaseModel):
    """微信公众号文章 (完整内容, 来自 URL 抓取)。"""
    title: str = Field(description="文章标题")
    author: Optional[str] = Field(default=None, description="作者")
    account_name: str = Field(description="公众号名称")
    account_id: Optional[str] = Field(default=None, description="公众号原始 ID (gh_xxx)")
    description: Optional[str] = Field(default=None, description="文章摘要")
    content: str = Field(description="文章正文 (Markdown)")
    url: str = Field(description="文章链接")
    cover_image: Optional[str] = Field(default=None, description="封面图 URL")
    images: List[str] = Field(default_factory=list, description="文章内图片 URL 列表")
    publish_time: Optional[datetime] = Field(default=None, description="发布时间")
    create_timestamp: Optional[int] = Field(default=None, description="创建时间戳")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None
        }
    }
