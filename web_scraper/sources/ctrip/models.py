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

class HotelRoom(BaseModel):
    room_name: str = Field(description="房型名称")
    bed_type: Optional[str] = Field(default=None, description="床型，如 大床/双床")
    area: Optional[str] = Field(default=None, description="面积，如 25㎡")
    floor: Optional[str] = Field(default=None, description="楼层")
    max_guests: Optional[int] = Field(default=None, description="最大入住人数")
    breakfast: Optional[str] = Field(default=None, description="早餐信息")
    price: Optional[str] = Field(default=None, description="价格")
    cancel_policy: Optional[str] = Field(default=None, description="取消政策")
    tags: List[str] = Field(default_factory=list, description="标签，如 含双早、免费取消")


class HotelDetail(BaseModel):
    hotel_id: str = Field(description="酒店 ID")
    name: str = Field(description="酒店名称")
    name_en: Optional[str] = Field(default=None, description="英文名称")
    star: Optional[int] = Field(default=None, description="星级")
    score: Optional[str] = Field(default=None, description="评分")
    score_desc: Optional[str] = Field(default=None, description="评分描述")
    comment_count: Optional[str] = Field(default=None, description="点评数")
    address: Optional[str] = Field(default=None, description="详细地址")
    phone: Optional[str] = Field(default=None, description="联系电话")
    opening_year: Optional[str] = Field(default=None, description="开业年份")
    renovation_year: Optional[str] = Field(default=None, description="装修年份")
    room_count: Optional[int] = Field(default=None, description="客房数量")
    tags: List[str] = Field(default_factory=list, description="酒店标签")
    facilities: List[str] = Field(default_factory=list, description="设施服务列表")
    description: Optional[str] = Field(default=None, description="酒店介绍")
    images: List[str] = Field(default_factory=list, description="图片 URL 列表（前几张）")
    rooms: List[HotelRoom] = Field(default_factory=list, description="房型列表")
    detail_url: str = Field(description="详情页 URL")


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


class FlightCalendarPrice(BaseModel):
    date: str = Field(description="出发日期 YYYY-MM-DD")
    price: Optional[float] = Field(default=None, description="票面价")
    total_price: Optional[float] = Field(default=None, description="税费后总价")
    transport_price: Optional[float] = Field(default=None, description="机票价格")
    discount_label: Optional[str] = Field(default=None, description="价格标签，如 低价")
    direct_label: Optional[str] = Field(default=None, description="直飞标签")


class FlightCard(BaseModel):
    sequence: int = Field(description="当前列表中的顺序")
    airlines: List[str] = Field(default_factory=list, description="航司列表")
    flight_numbers: List[str] = Field(default_factory=list, description="航班号列表")
    aircraft_summary: Optional[str] = Field(default=None, description="机型摘要")
    departure_time: str = Field(description="起飞时间")
    arrival_time: str = Field(description="到达时间")
    departure_airport: str = Field(description="出发机场")
    arrival_airport: str = Field(description="到达机场")
    departure_terminal: Optional[str] = Field(default=None, description="出发航站楼")
    arrival_terminal: Optional[str] = Field(default=None, description="到达航站楼")
    price: Optional[str] = Field(default=None, description="显示价格，如 ¥330")
    price_value: Optional[float] = Field(default=None, description="价格数值")
    cabin_classes: List[str] = Field(default_factory=list, description="舱位/折扣信息")
    tags: List[str] = Field(default_factory=list, description="标签，如 当日低价、免费退改")
    is_direct: bool = Field(default=True, description="是否直飞")
    transfer_count: int = Field(default=0, description="中转次数")
    transfer_duration: Optional[str] = Field(default=None, description="中转总耗时")
    transfer_description: Optional[str] = Field(default=None, description="中转说明")


class FlightSearchResult(BaseModel):
    departure_city: str = Field(description="出发城市")
    departure_code: str = Field(description="出发城市三字码")
    arrival_city: str = Field(description="到达城市")
    arrival_code: str = Field(description="到达城市三字码")
    departure_date: str = Field(description="出发日期")
    direct_only: bool = Field(default=False, description="是否只看直飞")
    search_url: str = Field(description="携程搜索结果页 URL")
    flights: List[FlightCard] = Field(default_factory=list, description="航班列表")
    calendar_prices: List[FlightCalendarPrice] = Field(default_factory=list, description="低价日历")
    no_result_message: Optional[str] = Field(default=None, description="无结果提示")
