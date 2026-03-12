# 京东商品详情页 API 接口文档

## 概述

- **网站地址**: https://item.jd.com/10212262468526.html
- **测试商品**: COFNI卡芙尼男士冰丝内裤（SKU: 10212262468526）
- **API 域名**:
  - `api.m.jd.com` — 核心业务接口（商品、价格、评价、推荐）
  - `cactus.jd.com` — 风控/行为上报
  - `h5speed.m.jd.com` — 性能监控日志
  - `blackhole.m.jd.com` — 行为数据采集（bypass）
- **认证方式**: Cookie 认证。需要 `thor`（登录凭证）、`_pst`、`token`、`3AB9D23F7A4B3CSS`（EID Token）等 Cookie。部分接口还需要 `x-api-eid-token` 和 `h5st` 查询参数做签名校验。

---

### 公共请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `Cookie` | 见下方 Cookie 清单 | 身份认证，必须包含 `thor`、`_pst`、`token` |
| `x-rp-client` | `h5_1.0.0` 或 `h5_2.0.0` | 客户端标识 |
| `x-referer-page` | `https://item.jd.com/{skuId}.html` | 来源页面 |
| `Referer` | `https://item.jd.com/` | HTTP Referer |
| `Origin` | `https://item.jd.com` | CORS 来源 |

### 关键 Cookie

| Cookie 名 | 说明 |
|-----------|------|
| `thor` | 登录态主凭证（加密，Secure） |
| `_pst` | 用户 pin 的缓存（如 `jd_5c4618143bcd7`） |
| `token` | 业务 token（格式: `hex,3,数字`） |
| `3AB9D23F7A4B3CSS` | EID Token，用于 `x-api-eid-token` 参数 |
| `shshshfpa/b/x` | 设备指纹，用于风控 |
| `ipLoc-djd` | 地区编码（`省_市_区_镇`，如 `53283_53480_59926_389086`） |
| `areaId` | 省级区域 ID |
| `flash` | 安全 Token（Secure） |
| `sdtoken` | 反爬 Token，随请求自动更新（响应头 `x-rp-sdtoken` 滚动刷新） |

### 公共查询参数（GET 接口）

| 参数 | 说明 |
|------|------|
| `appid` | 应用 ID（常见值: `item-v3`, `pc-item-soa`） |
| `client` | 固定为 `pc` |
| `clientVersion` | 固定为 `1.0.0` |
| `uuid` | 设备唯一标识（从 `__jda` Cookie 中取第二段） |
| `loginType` | 登录类型，已登录时为 `3` |
| `t` | 时间戳（毫秒） |
| `h5st` | 请求签名（格式: `时间戳;设备ID;版本;token;hash;版本;时间戳;...`，防重放/防篡改） |
| `x-api-eid-token` | 等同于 `3AB9D23F7A4B3CSS` Cookie 值 |
| `body` | JSON 字符串（URL 编码），接口业务参数 |

### 响应格式

大多数接口返回 JSON，结构为：

```json
{
  "code": 0,
  "msg": "Success",
  "data": { ... }
}
```

部分旧接口使用 `errorCode`/`errorMsg`，个别接口（如 `pc_item_getFooter`）返回 HTML 片段。

响应头 `x-rp-sdtoken` 会携带新的 `sdtoken`，格式为 `set;1800;<新值>`，客户端需更新对应 Cookie。

---

## 一、商品详情页 (item.jd.com/{skuId}.html)

### 1.1 商品业务核心数据 GET [重要度: ⭐⭐⭐]

```
GET https://api.m.jd.com/?appid=pc-item-soa&functionId=pc_detailpage_wareBusiness
```

**用途**: 商品详情页最核心接口，一次返回价格、SKU 颜色尺码、促销优惠、库存、商品属性、规格参数、A/B 实验配置等所有主要数据。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `skuId` | int | 商品 SKU ID |
| `cat` | string | 三级类目，逗号分隔（如 `"1315,1345,9744"`） |
| `area` | string | 地区编码，下划线分隔（如 `"53283_53480_59926_389086"`） |
| `shopId` | string | 店铺 ID |
| `venderId` | int | 商家 ID |
| `num` | string | 购买数量，默认 `"1"` |
| `paramJson` | string | 附加参数 JSON 字符串，含 `platform2`、`colType`、`specialAttrStr`、`skuMarkStr` |
| `canvasType` | int | 固定为 `1` |
| `sfTime` | string | 时效参数，如 `"1,0,0"` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `price.p` | string | 当前售价 |
| `price.op` | string | 原价 |
| `price.finalPrice.price` | string | 到手价 |
| `colorSizeVO.colorSizeList` | array | 颜色/尺码 SKU 列表，含每个 SKU 的 `skuId`、`text`、`stock` |
| `colorSizeVO.stockInfo` | object | 各 SKU 库存状态（`stockState: "34"` 表示无货） |
| `colorSizeVO.limitInfo` | object | 各 SKU 限购数量 |
| `preferenceVO.sharedLabel` | array | 已享优惠（满减券等） |
| `preferenceVO.againSharedLabel` | array | 可叠加优惠（折扣/返豆） |
| `preferenceVO.preferencePopUp.expression` | object | 价格计算明细（原价、券额、折扣额、到手价） |
| `productAttributeVO.attributes` | array | 商品属性列表（品牌、货号、材质等） |
| `wareInfoReadMap` | object | 商品详细信息（SKU 名称、类目 ID、店铺名、图片等） |
| `pageConfigVO` | object | 页面配置（是否自营 `isSelf`、是否有货、店铺 ID 等） |
| `commonLimitInfo.resultExtMap.canBuy` | string | `"1"` 表示可购买 |
| `abData` | object | A/B 实验分组信息 |

**响应示例**:

```json
{
  "price": {"p": "368.00", "op": "368.00", "finalPrice": {"price": "358", "priceContent": "到手价"}},
  "colorSizeVO": {
    "colorSizeList": [
      {"title": "颜色", "buttons": [{"skuId": "10212262468526", "text": "海棠+沙白+黑灰+黄色：礼盒装*4条", "stock": "0"}]},
      {"title": "尺码", "buttons": [
        {"skuId": "10212262468524", "text": "L 100-120斤", "stock": "0"},
        {"skuId": "10212262468526", "text": "2XL 140-160斤", "stock": "0"}
      ]}
    ],
    "stockInfo": {"10212262468526": {"dc": "-1", "stockState": "34"}}
  },
  "pageConfigVO": {"shopId": "16249317", "isSelf": false, "isPop": true, "skuid": 10212262468526},
  "wareInfoReadMap": {"sku_name": "COFNI...", "shop_name": "COFNI内衣旗舰店", "vender_id": "17882615"}
}
```

---

### 1.2 相关搜索推荐关键词 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?appid=item-v3&functionId=relsearch
```

**用途**: 获取商品详情页搜索框下方的推荐搜索词。

**关键查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `skuid` | int | 商品 SKU ID |
| `num` | int | 返回关键词数量，默认 `6` |
| `rettype` | string | 固定为 `json` |
| `type_name` | string | 固定为 `relsearch` |
| `body` | string | `{}` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `errorCode` | int | `0` 为成功 |
| `resultKeywords` | array | 推荐关键词列表 |
| `resultKeywords[].keyword` | string | 显示文字 |
| `resultKeywords[].searchKey` | string | 搜索用关键词 |
| `resultKeywords[].keywordType` | int | 类型（`1` = 普通） |

**响应示例**:

```json
{
  "errorCode": 0,
  "resultKeywords": [
    {"keyword": "冰丝内裤大码", "keywordType": 1, "searchKey": "冰丝内裤大码"},
    {"keyword": "冰丝内裤男", "keywordType": 1, "searchKey": "冰丝内裤男"}
  ]
}
```

---

### 1.3 商品评价列表（详情页预览） GET [重要度: ⭐⭐⭐]

```
GET https://api.m.jd.com/api?appid=item-v3&functionId=getLegoWareDetailComment
```

**用途**: 获取商品详情页底部展示的评价预览（含评价统计、语义标签、前 N 条评论）。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `sku` | int | 商品 SKU ID |
| `commentNum` | int | 显示评价条数，默认 `5` |
| `shopType` | string | 店铺类型，`"0"` = 第三方 |
| `source` | string | 来源，固定 `"pc"` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `allCnt` | string | 总评价数（可能带 `+`，如 `"100+"`） |
| `goodCnt` | string | 好评数 |
| `goodRate` | string | 好评率（如 `"100%"`） |
| `showPicCnt` | string | 有图评价数 |
| `semanticTagList` | array | 语义标签（物流速度、材质等），含 `name`、`count` |
| `commentInfoList` | array | 评价列表 |
| `commentInfoList[].userNickName` | string | 用户昵称（可能脱敏） |
| `commentInfoList[].commentData` | string | 评价内容 |
| `commentInfoList[].commentScore` | string | 评分（1-5） |
| `commentInfoList[].commentDate` | string | 评价日期 |
| `commentInfoList[].wareAttribute` | array | 购买规格（颜色、尺码） |
| `commentInfoList[].pictureCnt` | int | 评价图片数 |
| `commentInfoList[].publishArea` | string | 发布省份 |

**响应示例**:

```json
{
  "allCnt": "100+", "goodRate": "100%",
  "semanticTagList": [{"name": "物流速度快", "count": "8"}, {"name": "包装严实", "count": "2"}],
  "commentInfoList": [{
    "userNickName": "在人间最清醒_",
    "commentData": "非常满意，材质做工非常好...",
    "commentScore": "5",
    "commentDate": "2026-03-10 21:54:36",
    "wareAttribute": [{"颜色": "海棠+沙白+黑灰+黄色：礼盒装*4条"}, {"型号": "2XL 140-160斤"}]
  }]
}
```

---

### 1.4 用户权益信息（Plus/企业权益） GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_equityInfo&appid=item-v3
```

**用途**: 获取当前登录用户的会员权益信息（是否 Plus 会员、可享权益列表）。

**关键查询参数**: `body={}` 无需额外参数。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `isPlus` | bool | 是否 Plus 会员 |
| `plusStatus` | string | Plus 状态码 |
| `userRights` | array | Plus 会员专属权益列表（无限免邮、只换不修等） |
| `potentialUserRights` | array | 潜在用户可享权益 |
| `userBenefit` | array | 企业用户权益（企业团购、自营免邮等） |
| `isLogin` | bool | 是否已登录 |

---

### 1.5 Plus 会员信息查询 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_queryPlusInfo&appid=item-v3
```

**用途**: 查询当前用户是否为 Plus 会员及积分等级。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `pageId` | string | 固定为 `"JD_SXmain"` |

**响应示例**:

```json
{
  "code": 0,
  "data": {
    "isLogin": true,
    "plusInfo": {"isPlus": false, "plusStatus": "103"},
    "user": {"score": 0, "level": "50"}
  }
}
```

---

### 1.6 客服接入检测 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/?functionId=checkChat
```

**用途**: 检查商品是否支持在线客服咨询，获取客服聊天链接。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `source` | string | 固定 `"jd_pc_item"` |
| `key` | string | 页面唯一 key（如 `"JDPC_baf0bd4ca77d4e09847b97504b8763cf"`） |
| `pid` | int | 商品 SKU ID |
| `returnCharset` | string | 固定 `"utf-8"` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | `1` 表示支持客服 |
| `seller` | string | 店铺名称 |
| `chatUrl` | string | 客服聊天页 URL |
| `chatDomain` | string | 聊天域名（如 `chat.jd.com`） |

**响应示例**:

```json
{
  "seller": "COFNI内衣旗舰店",
  "code": 1,
  "chatUrl": "https://chat.jd.com/index.action?_t=&pid=10212262468526",
  "chatDomain": "chat.jd.com"
}
```

---

### 1.7 店铺关注状态查询 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_vender_batchIsFollow&appid=item-v3
```

**用途**: 批量查询当前用户是否已关注指定店铺。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `venderIds` | string/int | 商家 ID，可多个逗号分隔 |
| `sysName` | string | 固定 `"item.jd.com"` |

**响应示例**:

```json
{"code": 1, "data": {"16249317": false}, "success": true}
```

---

### 1.8 商品图文详情 GET [重要度: ⭐⭐⭐]

```
GET https://api.m.jd.com/?functionId=pc_item_getWareGraphic&appid=item-v3
```

**用途**: 获取商品图文描述内容（商品详情页"商品详情"标签下的图片列表）。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `skuId` | int | 商品 SKU ID |
| `area` | string | 地区编码 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | int | `200` 成功 |
| `data.skuId` | string | SKU ID |
| `data.graphicContent` | string | HTML 格式图文内容（含 `<img>` 标签，使用懒加载 `data-lazyload`） |
| `data.afterSaleGather` | object | 售后保障说明（京东承诺、正品行货、版权声明等） |

---

### 1.9 用户资质查询 GET [重要度: ⭐]

```
GET https://api.m.jd.com/qualification/life_v2?functionId=pc_qualification_life_v2
```

**用途**: 查询用户在特定类目下的购买资质（如处方类商品资质）。

**关键查询参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `area` | string | 地区编码 |
| `catId1/2/3` | string | 三级类目 ID |
| `skuId` | int | 商品 SKU ID |
| `pid` | int | 商品 product ID |
| `venderId` | int | 商家 ID |
| `body` | string | `{}` |

**响应示例**:

```json
{"traceStatus": 200, "qualityStatus": 200, "quaSelf": []}
```

---

### 1.10 弹窗信息查询 GET [重要度: ⭐]

```
GET https://api.m.jd.com/?appid=pc-item-soa&functionId=pc_item_getPopUpInfo
```

**用途**: 查询商品页面弹窗配置（如服务说明、活动弹窗等）。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `area` | string | 地区编码 |

**响应**: `{}` (本次无弹窗)

---

### 1.11 地区名称反查 POST [重要度: ⭐⭐]

```
POST https://api.m.jd.com/client.action?fid=pc_address_cmpnt_getAreaNameById
```

**用途**: 根据地区 ID 反查地区名称（省/市/区/镇），用于送至地址展示。

**请求体 (form-urlencoded body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `provinceId` | int | 省级 ID |
| `cityId` | int | 市级 ID |
| `countyId` | int | 区县级 ID |
| `townId` | int | 镇级 ID |
| `bizModelCode` | string | 固定 `"3"` |
| `externalLoginType` | string | 固定 `"1"` |

**响应示例**:

```json
{
  "body": {
    "provinceId": 53283, "provinceName": "海外",
    "cityId": 53480, "cityName": "英国",
    "countyId": 59926, "countyName": "England",
    "townId": 389086, "townName": "Bedfordshire",
    "complete": true
  },
  "code": "0", "message": "success"
}
```

---

### 1.12 "看了又看"商品推荐 GET [重要度: ⭐⭐⭐]

```
GET https://api.m.jd.com/api?appid=item-v3&functionId=pctradesoa_diviner
```

**用途**: 获取"看了又看"商品推荐列表（基于当前 SKU + 用户行为个性化推荐），页面滚动到底部时触发。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `sku` | int | 当前商品 SKU ID |
| `lim` | int | 返回数量（默认 `12`） |
| `page` | int | 分页，从 `1` 开始 |
| `p` | int | 推荐位 ID（`100100288` = 商品详情页推荐位） |
| `ck` | string | 上下文字段，固定 `"pin,bview"` |
| `clientChannel` | string | 固定 `"3"` |
| `clientPageId` | string | 固定 `"item.jd.com"` |
| `lid` | int | 固定 `1` |
| `ec` | string | 固定 `"utf-8"` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data` | array | 推荐商品列表 |
| `data[].sku` | int | 推荐商品 SKU ID |
| `data[].t` | string | 商品标题 |
| `data[].img` | string | 商品图片路径（需拼接 CDN 域名） |
| `data[].price.p` | string | 价格 |
| `data[].price.mp` | string | 市场价 |
| `data[].price.finalPrice.estimatedPrice` | string | 到手价 |
| `data[].bn` | string | 品牌名 |
| `data[].c1/c2/c3` | int | 一/二/三级类目 ID |
| `data[].shId` | string | 店铺 ID |
| `data[].rankWeight` | float | 推荐权重分 |
| `data[].clk` | string | 点击埋点 URL（`//knicks.jd.com/log/server?...`） |
| `data[].isSelfSku` | bool | 是否京东自营 |

**分页说明**: `page` 参数控制分页，每页返回 `lim` 条。

**响应示例**:

```json
{
  "data": [
    {
      "sku": 100041256706, "t": "南极人6条含蚕丝抗菌档冰丝男士内裤...",
      "price": {"p": "79", "mp": "99", "finalPrice": {"estimatedPrice": "66.1"}},
      "bn": "南极人（Nanjiren）", "isSelfSku": true, "rankWeight": 0.617
    }
  ]
}
```

---

### 1.13 页脚内容 GET [重要度: ⭐ (低价值)]

```
GET https://api.m.jd.com/?functionId=pc_item_getFooter&appid=item-v3
```

**用途**: 获取页面底部公共页脚 HTML（购物指南、配送方式、版权等）。

**关键查询参数 (body JSON)**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定 `"gb_common"` |
| `area` | string | 地区编码 |

**响应**: `{"content": "<style>...</style><div id=\"footer-2024\">...</div>"}` — 完整 HTML 字符串。

---

## 二、风控与监控接口（低价值）

### 2.1 风控灰度控制 POST

```
POST https://api.m.jd.com/  (appid=risk_h5_info, functionId=getCustomCtrl)
```

**用途**: 查询风控灰度开关（如是否启用 disposal 模式）。请求体: `body={"scenes":["disposalGray"]}` 或 `body={"domain":".jd.com"}`。

### 2.2 风控设备信息上报 POST

```
POST https://api.m.jd.com/  (appid=risk_h5, functionId=wsgw_getinfo)
```

**用途**: 上报浏览器设备指纹（屏幕分辨率、浏览器版本、平台信息、`shshshfpb` 等），用于反爬风控识别。响应包含 `whwswswws`（更新的设备指纹 token）。

### 2.3 SDK 调用日志上报 POST

```
POST https://api.m.jd.com/api  (appid=risk_h5_info, functionId=reportInvokeLog)
```

**用途**: 上报 SDK 调用日志，无业务意义。

### 2.4 风控算法请求 POST

```
POST https://cactus.jd.com/request_algo
```

**用途**: 向风控引擎请求算法决策，返回验证配置。

### 2.5 行为上报 POST

```
POST https://cactus.jd.com/behavior_report
POST https://blackhole.m.jd.com/bypass
POST https://h5speed.m.jd.com/event/log
```

**用途**: 用户行为/性能数据埋点上报，无需关注。

---

## 接口调用链路

```
用户访问 https://item.jd.com/{skuId}.html
│
├── [初始化阶段] 并发请求：
│   ├── risk_h5_info/getCustomCtrl   → 检查风控灰度
│   ├── risk_h5_info/reportInvokeLog → 上报SDK调用
│   ├── pctradesoa_equityInfo        → 加载用户权益
│   ├── pctradesoa_queryPlusInfo     → 查询Plus状态
│   ├── checkChat                    → 检查客服接入
│   └── getLegoWareDetailComment     → 加载评价预览
│
├── [核心数据] pc_detailpage_wareBusiness
│   └── 返回: skuId → colorSizeList (其他尺码的 skuId 列表)
│           shopId → 店铺ID → 用于 mall.jd.com/index-{shopId}.html
│           venderId → 商家ID → 用于 pctradesoa_vender_batchIsFollow
│
├── [地址组件] pc_address_cmpnt_getAreaNameById
│   └── 使用 Cookie 中的 ipLoc-djd 解析地区名称
│
├── [辅助数据] 并发请求：
│   ├── relsearch                    → 推荐搜索词
│   ├── pc_qualification_life_v2     → 购买资质检查
│   └── pc_item_getPopUpInfo         → 弹窗配置
│
└── [滚动懒加载]
    ├── pc_item_getWareGraphic       → 图文详情
    ├── pc_item_getFooter            → 页脚HTML
    └── pctradesoa_diviner           → "看了又看"推荐（分页: page=1,2,...）
```

### ID 关联关系

| 来源接口 | 字段 | 目标接口/用途 |
|---------|------|-------------|
| URL 参数 | `skuId=10212262468526` | 所有商品相关接口的 `skuId`/`sku` 参数 |
| `pc_detailpage_wareBusiness` | `pageConfigVO.shopId` | 店铺页 URL: `mall.jd.com/index-{shopId}.html` |
| `pc_detailpage_wareBusiness` | `wareInfoReadMap.vender_id` | `pctradesoa_vender_batchIsFollow` 的 `venderIds` |
| `pc_detailpage_wareBusiness` | `colorSizeVO.colorSizeList[].buttons[].skuId` | 切换尺码时重新调用 `pc_detailpage_wareBusiness` |
| `pc_detailpage_wareBusiness` | `wareInfoReadMap.product_id` | `pc_qualification_life_v2` 的 `pid` 参数 |
| Cookie `ipLoc-djd` | `{province}_{city}_{county}_{town}` | `area` 参数（所有需要地区的接口） |

---

## 关键发现

1. **签名机制 `h5st`**: 所有业务接口均携带 `h5st` 参数，格式为多段分号分隔的字符串，包含时间戳、设备 ID、token 版本、HMAC 签名等。签名算法在前端 JS 中实现，防重放攻击，每次请求生成唯一值，难以直接伪造。

2. **滚动 sdtoken**: 响应头 `x-rp-sdtoken: set;1800;<新值>` 会在每次成功请求后刷新 `sdtoken` Cookie，形成滚动 token 机制，爬虫需要同步更新此值。

3. **EID Token 双重验证**: `3AB9D23F7A4B3CSS` Cookie 值同时作为 `x-api-eid-token` URL 参数传递，是设备身份凭证。

4. **多 SKU 结构**: 一个商品（product）可包含多个 SKU（颜色/尺码组合）。`pc_detailpage_wareBusiness` 一次性返回所有 SKU 信息，切换规格时以新 `skuId` 重新调用该接口。

5. **库存状态码**: `stockState: "34"` 表示无货（库存为 0），`stockState: "33"` 表示有货。

6. **地区影响价格**: `area` 参数（来自 Cookie `ipLoc-djd`）会影响价格展示和配送时效，本次测试地区为海外（英国 Bedfordshire）。

7. **风控跳转**: 无 Cookie 或 Cookie 失效时访问商品页，服务器会返回 302 跳转到 `cfe.m.jd.com/privatedomain/risk_handler/` 进行风控验证，要求用户登录。

8. **图文详情懒加载**: `pc_item_getWareGraphic` 返回的 HTML 中图片使用 `data-lazyload` 属性，实际图片 URL 在 `data-lazyload` 中，页面滚动到可见区才会加载。图片域名为 `img10.360buyimg.com`。

9. **推荐接口分页**: `pctradesoa_diviner` 支持 `page` 参数翻页，每页 `lim=12` 条，用于"看了又看"无限滚动加载。

10. **appid 差异**: 部分接口使用 `appid=item-v3`（新版），部分使用 `appid=pc-item-soa`（SOA 架构）。`pc-item-soa` 的接口走 `api.m.jd.com/` 路径（不带 `/api`），`item-v3` 走 `api.m.jd.com/api` 路径。
