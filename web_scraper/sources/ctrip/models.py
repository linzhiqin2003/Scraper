"""Data models for Ctrip."""
from typing import List, Optional
from pydantic import BaseModel, Field


class AssetSummary(BaseModel):
    asset_type: str = Field(description="资产类型，如 GroupTicketCount、CreditScore")
    balance: float = Field(description="资产余额")


class MemberProfile(BaseModel):
    user_name: str = Field(description="用户昵称")
    grade: str = Field(description="会员等级编号")
    grade_name: str = Field(description="会员等级名称")
    svip: bool = Field(default=False, description="是否超级会员")
    is_corp: bool = Field(default=False, description="是否企业账户")
    avatar_url: Optional[str] = Field(default=None, description="头像 URL")
    assets: List[AssetSummary] = Field(default_factory=list, description="资产摘要列表")


class PointsInfo(BaseModel):
    total_available: int = Field(description="可用积分")
    total_balance: int = Field(description="积分余额（含冻结）")
    total_pending: int = Field(default=0, description="待入账积分")
    is_freeze: bool = Field(default=False, description="账户是否被冻结")


class MessageStat(BaseModel):
    msg_type: str = Field(description="消息类型，如 SERVICE")
    status: str = Field(description="消息状态，NEW=未读")
    count: int = Field(description="消息数量")
    need_prompt: bool = Field(default=False, description="是否需要提醒")


class MessageCount(BaseModel):
    stats: List[MessageStat] = Field(default_factory=list, description="各类型消息统计")

    @property
    def total_unread(self) -> int:
        return sum(s.count for s in self.stats if s.status == "NEW")


# ─────────────────────────────────────────
# Hotel models
# ─────────────────────────────────────────

class HotelCard(BaseModel):
    hotel_id: str = Field(description="酒店 ID")
    name: str = Field(description="酒店名称")
    star: Optional[int] = Field(default=None, description="星级，2-5")
    score: Optional[str] = Field(default=None, description="评分，如 4.8")
    score_desc: Optional[str] = Field(default=None, description="评分描述，如 超棒")
    comment_num: Optional[str] = Field(default=None, description="点评数，如 3128条点评")
    address: Optional[str] = Field(default=None, description="位置描述")
    room_name: Optional[str] = Field(default=None, description="推荐房型名称")
    price: Optional[str] = Field(default=None, description="价格，如 ¥2471")
    promotion: Optional[str] = Field(default=None, description="促销标签，如 特惠一口价")
    free_cancel: bool = Field(default=False, description="是否支持免费取消")
    is_ad: bool = Field(default=False, description="是否为广告")
    detail_url: Optional[str] = Field(default=None, description="详情页 URL")


class HotelSearchResult(BaseModel):
    city_id: int = Field(description="城市 ID")
    city_name: str = Field(description="城市名称")
    checkin: str = Field(description="入住日期")
    checkout: str = Field(description="退房日期")
    hotels: List[HotelCard] = Field(default_factory=list, description="酒店列表")


class HotelCity(BaseModel):
    city_id: int = Field(description="携程城市 ID")
    city_name: str = Field(description="城市中文名")
    country_id: int = Field(description="国家 ID")
    group_name: Optional[str] = Field(default=None, description="分组名，如 国内热门城市")
