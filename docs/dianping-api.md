# 大众点评站点接口文档

## 概述

- **网站地址**: `https://m.dianping.com/dphome`
- **探索页面**:
  - 首页: `https://m.dianping.com/dphome`
  - 搜索结果页样本: `https://www.dianping.com/search/keyword/1/0_%E7%91%9E%E5%B9%B8`
  - 商户详情样本: `https://www.dianping.com/shop/laht1FD7c2e0OXbk`
  - 笔记详情样本: `https://www.dianping.com/note/445060906_29`
- **API 域名**:
  - `mapi.dianping.com` - 业务数据接口
  - `m.dianping.com` - H5 配置接口
  - `www.dianping.com` - 城市 / SSR 页面
  - `apimeishi.meituan.com` - 美食业务接口
  - `apimobile.meituan.com` - AB 实验配置
  - `verify.meituan.com` - 人机验证 / 风控页
  - `lx1.meituan.net`, `lx2.meituan.net` - 埋点上报
- **认证方式**: Cookie。首页在带 `dper` / `dplet` / `ctu` / `logan_session_token` 等 cookie 的登录态下正常返回个性化用户信息

### 公共请求特征

首页业务接口基本都带以下特征：

| 项 | 值 |
|---|---|
| `Accept` | `application/json, text/plain, */*` |
| `Content-Type` | `application/json`（POST 接口） |
| Cookie | 依赖浏览器自动携带 |
| 凭证模式 | 前端使用 `credentials: include` / XHR withCredentials |

### 通用响应格式

多数业务接口为：

```json
{
  "code": 200,
  "msg": "成功",
  "result": {...},
  "success": true
}
```

配置接口 `mconfig/get` 略有不同：

```json
{
  "code": 200,
  "msg": "success",
  "data": [...],
  "spiderFilterData": {...}
}
```

AB 实验接口为：

```json
{
  "code": 0,
  "body": {...},
  "errorMsg": ""
}
```

---

## 一、首页 `dphome`

### 1.1 城市信息 GET

```text
GET https://www.dianping.com/dpindex/city?cityId=1
```

**用途**: 获取当前城市基础信息。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `cityId` | int | 城市 ID |
| `cityName` | string | 城市中文名 |
| `cityEnName` | string | 城市英文名 |

**样本响应**:

```json
{"cityId":1,"cityName":"上海","cityEnName":"shanghai"}
```

---

### 1.2 拉起 App / 反爬配置 GET

```text
GET https://m.dianping.com/usergrowth/mconfig/get?pageKey=home&mSource=default
```

**用途**: 获取首页 App 拉起策略、下载地址和 spider filter 配置。

**关键参数**:

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `pageKey` | string | 是 | 页面标识，首页为 `home` |
| `mSource` | string | 是 | 当前抓到值为 `default` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `data[].launchKey` | string | 拉起配置 key |
| `data[].launchAppUrl` | string | App schema，如 `dianping://home` |
| `data[].androidUrl` | string | Android 下载页 |
| `data[].iosUrl` | string | iOS 下载跳转 |
| `spiderFilterData.enableSpiderFilter` | bool | 是否启用 spider filter |
| `spiderFilterData.filterKey` | string[] | 当前过滤的爬虫 UA 关键字 |

---

### 1.3 首页导航图标 POST

```text
POST https://mapi.dianping.com/mapi/mgw/growthqueryindex
```

**用途**: 获取首页顶部入口导航，如美食、景点、酒店、休闲玩乐等。

**Request Body**:

```json
{
  "cityId": 1,
  "sourceId": 1
}
```

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `result[].configId` | int | 导航配置 ID |
| `result[].eleOrder` | int | 排序 |
| `result[].title` | string | 导航标题 |
| `result[].url` | string | 跳转链接 |
| `result[].iconUrl` | string | 图标地址 |

**已抓到的导航样本**:

- `78371` -> `美食` -> `/shanghai/ch10/d1`
- `78364` -> `景点/周边游` -> `/shanghai/ch35/d1`
- `78368` -> `酒店/民宿` -> `/shanghai/ch0/d1`
- `78358` -> `休闲/玩乐` -> `/shanghai/ch30`
- `78357` -> `猫眼电影` -> `/shanghai/ch25`
- `78359` -> `丽人/美发` -> `/shanghai/ch50`
- `78367` -> `美团外卖` -> `https://h5.waimai.meituan.com/waimai/mindex/home`

---

### 1.4 用户信息 POST

```text
POST https://mapi.dianping.com/mapi/mgw/growthuserinfo
```

**用途**: 获取当前登录用户的昵称、头像和等级。

**Request Body**:

```json
{}
```

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `result.userId` | string | 当前用户 ID |
| `result.userNickName` | string | 昵称 |
| `result.userFace` | string | 头像 |
| `result.reviewCount` | int | 点评数 |
| `result.fansCount` | int | 粉丝数 |
| `result.userLevel` | int | 用户等级 |

**样本响应**:

```json
{
  "code": 200,
  "msg": "成功",
  "result": {
    "userId": "1942885326",
    "userNickName": "流年",
    "reviewCount": 15,
    "fansCount": 0,
    "userLevel": 2
  },
  "success": true
}
```

---

### 1.5 首页内容流 POST

```text
POST https://mapi.dianping.com/mapi/mgw/growthlistfeeds
```

**用途**: 获取首页推荐内容流，滚动加载时继续翻页。

**Request Body**:

```json
{
  "cityId": 1,
  "pageStart": 0,
  "pageSize": 10,
  "sourceId": 1,
  "lxCuid": "19cc56b57561-0606649222f6c48-1a525631-1fa400-19cc56b5757c8",
  "awakeAppHandler": "awakeAppHandler",
  "envParam": {
    "os": "ios",
    "locCityId": 1,
    "latitude": 0,
    "longitude": 0
  }
}
```

**关键参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `cityId` | int | 是 | 当前城市 ID |
| `pageStart` | int | 是 | 偏移量，首屏为 `0`，继续加载时递增 `10` |
| `pageSize` | int | 是 | 每页数量，当前抓到为 `10` |
| `sourceId` | int | 是 | 当前抓到为 `1` |
| `lxCuid` | string | 是 | 设备 / 访客标识，来自 cookie `_lxsdk_cuid` |
| `awakeAppHandler` | string | 是 | 当前固定为 `awakeAppHandler` |
| `envParam.os` | string | 是 | 当前抓到为 `ios` |
| `envParam.locCityId` | int | 是 | 定位城市 ID |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `result.totalNum` | int | 总量，当前返回 `10000` |
| `result.feedsRecordDTOS[]` | array | 首页 feed 列表 |
| `feedsRecordDTOS[].bizType` | int | 业务类型，当前样本为 `300` |
| `feedsRecordDTOS[].bizId` | string | feed ID |
| `feedsRecordDTOS[].contentId` | int | 内容 ID |
| `feedsRecordDTOS[].title` | string | 标题 |
| `feedsRecordDTOS[].picKey` | string | 封面图 |
| `feedsRecordDTOS[].schema` | string | 详情页跳转链接 |
| `feedsRecordDTOS[].likeCount` | int | 点赞数 |
| `feedsRecordDTOS[].userId` | int | 作者 ID |
| `feedsRecordDTOS[].userNickName` | string | 作者昵称 |
| `feedsRecordDTOS[].poiCityId` | int | POI 城市 ID |

**分页机制**:

- 首屏: `pageStart=0`
- 第一次下拉: `pageStart=10`
- 第二次下拉: `pageStart=20`

当前页面滚动后，确认该接口按 `pageStart += pageSize` 线性分页。

---

### 1.6 AB 实验配置 GET

```text
GET https://apimobile.meituan.com/abtest/v2/getClientAbTestResult?layerIds=292584&userid=undefined&uuid={uuid}&ci=undefined&isAll=false&app=dianping_nova&version_name=undefined&platform=PC
```

**用途**: 获取当前页面 AB 实验分桶结果。

**说明**:

- 对首页业务数据不是主接口，但前端启动时会请求
- `uuid` 与 `_lxsdk_cuid` / 访客标识相关
- 当前抓到 `app=dianping_nova`、`platform=PC`

---

## 二、搜索结果页

样本页面:

```text
GET https://www.dianping.com/search/keyword/1/0_%E7%91%9E%E5%B9%B8
```

### 2.1 URL 结构

搜索结果页本身是 `www.dianping.com` 的 SSR 页面，筛选和翻页主要靠路径编码：

| 结构 | 说明 |
|---|---|
| `/search/keyword/{cityId}/{channel}_{keyword}` | 关键词搜索主路径 |
| `/search/keyword/1/0_瑞幸/p2` | 第 2 页 |
| `/search/keyword/1/0_瑞幸/o3` | 按好评排序 |
| `/search/keyword/1/0_瑞幸/r860` | 按商圈筛选 |
| `/search/keyword/1/10_瑞幸` | 切到频道 `美食` |

当前样本里：

- `cityId=1` -> 上海
- `channel=0` -> 不限
- `10` -> 美食
- `/pN` -> 页码
- `/o2` / `/o3` / `/o11` -> 排序
- `/r{regionId}` -> 商圈 / 区域

---

### 2.2 搜索结果页核心 Ajax

```text
POST https://www.dianping.com/ajax/json/shopremote/search
```

**用途**: 搜索结果页的补充数据接口。结合前端脚本 `app-main-search.js` 和实际抓包，至少承载两类能力：

1. `do=gettppromo` - 给列表中的团购卡片补充促销标签
2. `do=getcorr` - 获取右侧相关榜单

**前端源码中已确认的两种请求体**:

```json
{
  "do": "gettppromo",
  "cityid": 1,
  "dealgroupids": "1224954878,1237219864",
  "dealgroupprices": "11.9,11.9"
}
```

```json
{
  "do": "getcorr",
  "t": 10,
  "cityId": 1,
  "s": "laht1FD7c2e0OXbk,kaPmFuzGK3otXIWL",
  "limit": "3"
}
```

**说明**:

- 搜索结果主列表本身优先 SSR 在 HTML 里
- 页面加载后，再通过这个接口补榜单 / 团购促销等动态块

---

### 2.3 结果页其他补充接口

```text
POST https://www.dianping.com/mkt/ajax/getNewItems
POST https://www.dianping.com/searchads/ajax/suggestads
```

**用途**:

- `getNewItems`：营销位 / 活动补充内容
- `suggestads`：搜索广告 / 建议广告位

这两个接口不是结果主列表，但会在结果页首屏请求。

---

### 2.4 分页与筛选结论

- 翻页不是滚动接口，而是纯路径分页：`/p2`、`/p3` ...
- 排序和筛选也主要体现在 URL path，而不是首屏 XHR 参数
- 结果页点商户后，跳转到 `/shop/{shopUuid}` 详情页

---

### 2.5 分类页风控

首页顶部导航如 `美食 -> /shanghai/ch10/d1`、`景点/周边游 -> /shanghai/ch35/d1`。

本次实测里，直接从首页点击 `美食` 会被重定向到：

```text
https://verify.meituan.com/v2/app/general_page?...&succCallbackUrl=https://www.dianping.com/shanghai/ch10/d1
```

**结论**:

- 分类页链路存在独立风控
- 在当前 cookie 和设备环境下，分类列表进一步探索会先撞到 `verify.meituan.com`

---

## 三、商户详情页

样本页面:

```text
GET https://www.dianping.com/shop/laht1FD7c2e0OXbk
```

### 3.1 页面形态

商户详情页不是旧 PC 模板，而是：

- `www.dianping.com/shop/{shopUuid}` 的页面壳
- 加载移动端 bundle，如 `poi-bundle.es6`
- 首屏数据大量内嵌在 HTML 的 `window.__xhrCache__ = {...}` 脚本中

这意味着抓取时可以优先：

1. 拉取 HTML
2. 解析内联 `__xhrCache__`
3. 再按需补抓后续 XHR

---

### 3.2 首屏预埋接口集合

当前样本页内联缓存里确认有 10 个首屏接口，核心包括：

```text
GET //m.dianping.com/wxmapi/shop/shopservice
GET //m.dianping.com/meishi/poi/v1/shelf/0
GET //apimeishi.meituan.com/meishi/contentapi/dp-m-poi/coupon-zone
GET //m.dianping.com/api/dzviewscene/dealshelf/dealfilterlist
GET //m.dianping.com/wxmapi/shop/shopmenu
GET //m.dianping.com/wxmapi/shop/shopinfo
GET //mapi.dianping.com/mapi/base/unify/shop.bin
GET //m.dianping.com/wxmapi/shop/shopother
GET //m.dianping.com/wxmapi/shop/cooperation
GET //m.dianping.com/wxmapi/shop/rankinfo
```

---

### 3.3 商户基础信息聚合接口

```text
GET https://mapi.dianping.com/mapi/base/unify/shop.bin?...&shopUuid=laht1FD7c2e0OXbk
```

**用途**: 返回商户详情页的主聚合数据。

**已确认关键字段**:

| 字段 | 说明 |
|---|---|
| `id` | 商户 ID |
| `shopUuid` | 商户 UUID |
| `name` | 商户名 |
| `scoreText` | 评分文案 |
| `phoneNos` | 电话 |
| `deals` | 团购 / 优惠 |
| `shopType` | 商户类型 |
| `route` | 路线 / 到店相关 |
| `shopStatusDetail` | 营业状态 |
| `lat` / `lng` | 坐标 |

---

### 3.4 团购货架接口

```text
GET https://m.dianping.com/meishi/poi/v1/shelf/0?enterchannel=dph5&shopuuid=laht1FD7c2e0OXbk&device_system=MACINTOSH
```

**用途**: 返回团购套餐 / 单品券货架。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `data.dpPoiId` | string | 点评 POI ID |
| `data.meal.classificationList[]` | array | 团购分组 |
| `mealList[].id` | int | 团购 ID |
| `mealList[].title` | string | 标题 |
| `mealList[].dealTags[]` | array | 标签，如周一至周日 / 随时退 |
| `mealList[].price` | number | 售价 |
| `mealList[].value` | number | 门市价 |
| `mealList[].discount` | string | 折扣文案 |
| `mealList[].soldsDesc` | string | 销量文案 |
| `mealList[].imgUrl` | string | 图片 |

**样本团购**:

- `【瑞门闭眼入】10选1`
- `生椰拿铁`

---

### 3.5 详情页补充接口

首屏及后续还会请求：

```text
GET https://m.dianping.com/usergrowth/mconfig/get?pageKey=shopdetail&mSource=default
GET https://m.dianping.com/an/gear/dpmapp/api/poi/breadcrumb?shopId=laht1FD7c2e0OXbk
GET https://m.dianping.com/an/gear/dpmapp/api/readLionConfig/config?pageKey=detail
GET https://m.dianping.com/wxmapi/shop/friendslike?...&shopUuid=laht1FD7c2e0OXbk
GET https://m.dianping.com/wxmapi/shop/shopquestion?shopId=laht1FD7c2e0OXbk
GET https://mapi.dianping.com/mapi/review/outsideshopreviewlist.bin?...&shopuuid=laht1FD7c2e0OXbk
GET https://apimeishi.meituan.com/blackpearl/rank/getBlackPearlDealDTOs?platformId=2&shopUuid=laht1FD7c2e0OXbk
```

**用途**:

- `mconfig/get`：App 拉起 / 反爬配置
- `breadcrumb`：面包屑导航
- `readLionConfig/config`：详情页配置
- `friendslike`：相似 / 你可能喜欢
- `shopquestion`：问答模块
- `outsideshopreviewlist.bin`：外显评论列表
- `getBlackPearlDealDTOs`：黑珍珠相关权益

---

### 3.6 风控结论

本次实测中：

- 直接浏览商户详情页首屏可正常拿到数据
- 但主动程序化请求 `outsideshopreviewlist.bin` 后，会被重定向到 `verify.meituan.com`

说明商户详情页允许“首屏被动加载”，但对主动深抓评论链路有更严的风控。

---

## 四、笔记详情页

样本页面:

```text
GET https://www.dianping.com/note/445060906_29
```

### 4.1 详情页配置 GET

```text
GET https://m.dianping.com/usergrowth/mconfig/get?pageKey=notedetail&mSource=default
```

**用途**: 获取详情页的 App 拉起 / 反爬配置。

**说明**:

- 与首页同源同结构，只是 `pageKey` 变成 `notedetail`

---

### 4.2 相关推荐 GET

```text
GET https://mapi.dianping.com/mapi/friendship/recfeeds.bin?feedid=445060906&feedtype=29&cityid=-1&choosecityid=-1&longitude=0&latitude=0&start=0&limit=20
```

**用途**: 获取笔记详情页底部推荐 feed。

**关键参数**:

| 参数 | 类型 | 说明 |
|---|---|---|
| `feedid` | string | 当前内容 ID |
| `feedtype` | int | 当前样本为 `29` |
| `cityid` | int | 当前抓到 `-1` |
| `choosecityid` | int | 当前抓到 `-1` |
| `longitude` / `latitude` | number | 当前为 `0` |
| `start` | int | 偏移 |
| `limit` | int | 数量，当前为 `20` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|---|---|---|
| `recList[]` | array | 推荐列表 |
| `recList[].storyTitle` | string | 推荐标题 |
| `recList[].storyContent` | string | 文本内容 |
| `recList[].storyFeedPics[]` | array | 图片列表 |
| `recList[].commentCount` | int | 评论数 |
| `recList[].likeCount` | int | 点赞数 |
| `recList[].storyFeedUser.userId` | int | 作者 ID |
| `recList[].storyFeedUser.userNickName` | string | 作者昵称 |

---

### 4.3 正文数据来源：SSR `__NEXT_DATA__`

**关键发现**:

- 当前样本详情页加载时，没有单独抓到“正文详情 JSON 接口”
- 页面正文、标题、富文本内容直接嵌在 HTML 内的 `#__NEXT_DATA__`

**已验证字段**:

| 字段 | 说明 |
|---|---|
| `props.pageProps.feedInfo.mainId` | 内容主 ID |
| `props.pageProps.feedInfo.feedType` | feed 类型 |
| `props.pageProps.feedInfo.title` | 标题 |
| `props.pageProps.feedInfo.content` | 正文文本 |
| `props.pageProps.feedInfo.richContent` | 富文本结构 |

这意味着详情页爬取可以优先考虑：

1. 直接解析 SSR HTML 中的 `__NEXT_DATA__`
2. 再按需补抓 `recfeeds.bin` 等周边接口

---

## 五、接口调用链路

```text
首页 dphome
  ├─ GET /dpindex/city?cityId=1                      -> 当前城市
  ├─ GET /usergrowth/mconfig/get?pageKey=home        -> App 拉起 / spider filter
  ├─ POST /mapi/mgw/growthqueryindex                 -> 顶部导航入口
  ├─ POST /mapi/mgw/growthuserinfo                   -> 当前登录用户
  └─ POST /mapi/mgw/growthlistfeeds                  -> 首页推荐流
         ├─ 搜索框跳转到 /search/keyword/{city}/{channel}_{kw}
         ├─ 分类入口跳转到 /shanghai/ch10/d1 等频道页
         └─ schema 跳转到 /ugcdetail/{id} 或 /note/{id}_{type}

搜索结果页 /search/keyword/{city}/{channel}_{kw}
  ├─ HTML SSR                                        -> 商户列表主内容
  ├─ POST /ajax/json/shopremote/search               -> 榜单 / 团购补充数据
  ├─ POST /mkt/ajax/getNewItems                      -> 营销位
  └─ POST /searchads/ajax/suggestads                 -> 搜索广告位

商户详情页 /shop/{shopUuid}
  ├─ HTML 内联 window.__xhrCache__                  -> 首屏预埋接口缓存
  ├─ GET /mapi/base/unify/shop.bin                   -> 商户主聚合数据
  ├─ GET /meishi/poi/v1/shelf/0                      -> 团购货架
  ├─ GET /wxmapi/shop/shopmenu                       -> 菜单 / 推荐菜
  ├─ GET /wxmapi/shop/shopother                      -> 其他模块
  ├─ GET /mapi/review/outsideshopreviewlist.bin      -> 评论列表
  └─ 深抓时可能跳 verify.meituan.com                 -> 人机验证

详情页 /note/{feedid}_{feedtype}
  ├─ HTML SSR __NEXT_DATA__                     -> 正文主数据
  ├─ GET /usergrowth/mconfig/get?pageKey=notedetail
  └─ GET /mapi/friendship/recfeeds.bin          -> 相关推荐
```

---

## 六、关键发现

1. **首页是 Cookie 驱动的轻接口组合**: 首页不是一个“大而全”接口，而是导航、用户、推荐流三个接口拆开拉。
2. **内容流分页很直接**: `growthlistfeeds` 使用 `pageStart + pageSize` 做偏移分页，没有看到游标字段。
3. **设备标识参与请求**: `growthlistfeeds` 明确依赖 `lxCuid`，它与 `_lxsdk_cuid` cookie 对应。
4. **搜索结果主列表偏 SSR，动态块再用 Ajax 补**: `/search/keyword/...` 主体商户列表直接在 HTML 中，`shopremote/search` 更像团购标签、榜单等补充接口。
5. **搜索 / 分类 / 详情跨了 PC 壳和移动接口**: 页面 URL 在 `www.dianping.com`，但商户详情大量数据来自 `m.dianping.com` / `mapi.dianping.com` / `apimeishi.meituan.com`。
6. **商户详情首屏最值得抓的是内联 `__xhrCache__`**: 相比单独回放多个接口，先解析 HTML 里的缓存对象成本更低，也更稳定。
7. **分类页和评论深抓都有独立风控**: 点击 `美食` 分类入口会跳 `verify.meituan.com`；主动抓评论列表也会触发验证。
8. **笔记正文优先 SSR**: 笔记详情页正文直接放在 `__NEXT_DATA__`，并不依赖首屏 XHR 返回正文。
9. **配置接口承担反爬 / 拉起逻辑**: `mconfig/get` 返回 `spiderFilterData`，说明前端本身带基础 spider filter 配置。
10. **AB 与埋点来自美团公共能力**: `apimobile.meituan.com` 和 `lx*.meituan.net` 主要是实验、埋点，不是业务主数据。
