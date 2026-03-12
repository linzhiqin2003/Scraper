# 京东搜索页 API 接口文档

## 概述

- **网站地址**: https://search.jd.com/Search
- **API 域名**:
  - `api.m.jd.com` — 主要业务 API 网关（搜索结果、用户信息、广告等）
  - `sso.jd.com` — 单点登录 / Cookie 刷新
  - `cactus.jd.com` — h5st 签名算法服务 + 行为上报
  - `h5speed.m.jd.com` — 性能监控上报
  - `gia.jd.com` — 广告曝光追踪
  - `storage.360buyimg.com` — 静态配置 JSON（lowcode 平台）
- **认证方式**: Cookie 认证 + h5st 动态签名（双重验证）
- **关键 Cookie**:

| Cookie | 说明 |
|--------|------|
| `thor` | 主登录态 token，HttpOnly+Secure |
| `_pst` | 登录用户 pin（明文，如 `jd_5c4618143bcd7`） |
| `npin` | 同 `_pst`，另一份 pin |
| `token` | 业务 token，格式 `hash,version,uid` |
| `3AB9D23F7A4B3CSS` | 设备 EID token，即 `x-api-eid-token` 请求头的值 |
| `flash` | 反爬 session token，每次请求可能更新 |
| `sdtoken` | 安全 token，由服务端通过 `X-Rp-Sdtoken` 响应头下发并更新 |
| `shshshfpa/fpb/fpx` | 设备指纹 |
| `areaId` / `ipLoc-djd` | 地区 ID，影响库存和价格展示 |
| `__jdu` / `__jda` / `__jdb` | 用户唯一标识（uuid）及访问链路追踪 |
| `logintype` | 登录方式（如 `wx` 微信） |

### 公共请求头（搜索 API）

| Header | 值 | 说明 |
|--------|-----|------|
| `x-referer-page` | `https://search.jd.com/Search` | 来源页面 |
| `x-rp-client` | `h5_1.0.0` | 客户端标识 |
| `accept` | `application/json, text/plain, */*` | |
| `origin` | `https://search.jd.com` | |
| `referer` | `https://search.jd.com/Search?keyword=...` | |

### 通用 URL 参数（api.m.jd.com/api）

| 参数 | 说明 |
|------|------|
| `appid` | 应用 ID，搜索页固定为 `search-pc-java` |
| `functionId` | 接口功能 ID，区分具体业务 |
| `client` | 固定 `pc` |
| `clientVersion` | 固定 `1.0.0` |
| `uuid` | 用户设备唯一标识，对应 Cookie `__jdu` |
| `loginType` | 登录类型，已登录为 `3` |
| `t` | 毫秒时间戳 |
| `x-api-eid-token` | 设备 EID token，对应 Cookie `3AB9D23F7A4B3CSS` |
| `h5st` | 动态签名（见下方说明） |

### 响应格式（api.m.jd.com/api）

```json
{
  "code": 0,
  "data": { ... },
  "msg": "Success",
  "abBuriedTagMap": { ... }
}
```

`code=0` 表示成功。部分接口返回 `text/html` Content-Type 但内容仍是 JSON。

---

## 一、h5st 签名机制

### 1.1 签名获取 — cactus.jd.com POST [重要度: ⭐⭐⭐]

```
POST https://cactus.jd.com/request_algo
Content-Type: application/json
```

**用途**: 获取当前请求所需的 tk（临时签名 token）以及 SHA256 算法函数，用于构造 h5st 参数。

**Request Body 关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `version` | string | 固定 `"5.3"` |
| `fp` | string | 设备指纹 ID，格式类似 `2ezbjeb1pzbe2zb7` |
| `appId` | string | 应用 ID，如 `"73806"` |
| `timestamp` | number | 毫秒时间戳 |
| `platform` | string | 固定 `"web"` |
| `expandParams` | string | 加密的环境检测数据（混淆 JS 生成） |
| `fv` | string | 算法版本，如 `"h5_file_v5.3.0"` |
| `localTk` | string | 本地临时 token |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.result.tk` | string | 签名用的临时 token（以 `tk03w` 开头） |
| `data.result.fp` | string | 设备指纹确认值 |
| `data.result.algo` | string | JavaScript 函数字符串，用于计算最终 hash |
| `data.ts` | number | 服务端时间戳 |

**响应示例**:
```json
{
  "status": 200,
  "data": {
    "version": "5.3",
    "result": {
      "tk": "tk03w99851bef18nZkCLAaz19e5...",
      "fp": "2ezbjeb1pzbe2zb7",
      "algo": "function test(tk,fp,ts,ai,algo){var rd='2FrmxhwwVR4v';var str=\"\".concat(tk).concat(fp).concat(ts).concat(ai).concat(rd);return algo.SHA256(str);}"
    },
    "ts": 1773269762287
  }
}
```

### 1.2 h5st 参数结构

h5st 是分号分隔的多段字符串：

```
{时间戳yyyyMMddHHmmssSSS};{fp设备指纹};{appId十六进制};{tk};{SHA256hash};{version};{请求时间戳ms};{expandParams加密串}
```

示例：
```
20260311225606769;z5zbijbe2pbpzze7;f06cc;tk06w1d7b7cfb41lf...;ee2d0ce6c0987...;5.3;1773269761769;of7ruCLj...
```

**签名流程**：
1. 调用 `cactus.jd.com/request_algo` 获取 `tk` 和 `algo` 函数
2. 使用 `algo` 函数：`SHA256(tk + fp + ts + ai + rd)` 得到 hash
3. 拼接各字段组成 h5st
4. 将 h5st 作为 URL 参数附加到 `api.m.jd.com/api` 请求中

---

## 二、搜索结果页接口

### 2.1 搜索商品列表 GET [重要度: ⭐⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_searchWare&appid=search-pc-java&client=pc&clientVersion=1.0.0&cthr=1&uuid={uuid}&loginType=3&keyword={keyword}&body={body_json}&x-api-eid-token={eid}&h5st={h5st}&t={timestamp}
```

**用途**: 核心搜索接口，返回商品列表、筛选项、价格区间、分页信息。

**body 参数**（JSON 编码后放入 `body` 查询参数）:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `enc` | string | 是 | 固定 `"utf-8"` |
| `area` | string | 是 | 地区 ID，格式 `省_市_区_街道`，如 `53283_53480_59926_389086` |
| `page` | number | 是 | 页码，从 1 开始 |
| `mode` | null/string | 否 | 展示模式，默认 null |
| `concise` | boolean | 否 | 简洁模式，默认 false |
| `new_interval` | boolean | 否 | 新价格区间，默认 true |
| `s` | number | 是 | 当前页第一个商品的序号，第1页为 1，第2页为 31（每页30个） |
| `sort` | string | 否 | 排序方式：`sort_default`（综合）、`sort_totalsales15_desc`（销量）、`sort_price_asc`（价格升）、`sort_price_desc`（价格降）、`sort_commentcount_desc`（评价数） |
| `ev` | string | 否 | 筛选参数，格式 `attr_{属性id}:{属性值}%5E`，多个用 `%5E` 分隔 |
| `pinlei` | string | 否 | 品类筛选，品类 cid3 |
| `brands` | string | 否 | 品牌筛选，品牌 ID |
| `price` | string | 否 | 价格区间筛选，格式 `{min}-{max}` |
| `delivery` | string | 否 | 配送方式，如 `1`（京东物流）|
| `shop_id` | string | 否 | 旗舰店筛选 |
| `go_to_page` | boolean | 否 | 是否跳页，配合 `page` 使用 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.resultCount` | number | 总结果数，如 `117` |
| `data.listKeyWord` | string | 服务端规范化关键词，如 `"水果奇异果"` |
| `data.wareList` | array | 商品列表 |
| `data.wareList[].skuId` | string | 商品 SKU ID |
| `data.wareList[].name` | string | 商品名称 |
| `data.wareList[].price` | string | 当前价格 |
| `data.wareList[].imageurl` | string | 主图 URL（相对路径，需拼接 `https://img14.360buyimg.com/n1/`) |
| `data.wareList[].shopId` | string | 店铺 ID |
| `data.wareList[].shopName` | string | 店铺名称 |
| `data.wareList[].catid` | string | 三级类目 ID（cid3） |
| `data.wareList[].cid1` | string | 一级类目 ID |
| `data.wareList[].cid2` | string | 二级类目 ID |
| `data.wareList[].comment` | string | 评论数 |
| `data.wareList[].averageScore` | string | 平均评分（1-5） |
| `data.wareList[].brandId` | string | 品牌 ID |
| `data.wareList[].brand` | string | 品牌名称 |
| `data.wareList[].isPlusShop` | number | 是否 PLUS 店铺 |
| `data.wareList[].benefitList` | array | 权益标签（满减、免运费等） |
| `data.wareList[].deliveryDays` | number | 预计送达天数 |
| `data.wareList[].color` | string | 商品副标题/规格描述 |
| `data.intervalPrice` | array | 价格区间选项，每项含 `{value: {min, max}}` |
| `data.price` | array | 同 intervalPrice |
| `data.advCount` | number | 广告商品数量 |
| `data.isPlusPin` | number | 是否 PLUS 会员，0=否 |
| `data.dataBuried` | object | 埋点数据（pvid、排序类型、AB 实验等） |
| `data.dataBuried.pvid` | string | 页面访问唯一 ID |
| `data.dataBuried.sort_type` | string | 当前排序类型 |
| `abBuriedTagMap` | object | AB 实验分组信息（base64 编码的实验 ID） |

**分页规则**:
- 每页 30 个商品
- 第 N 页的 `s` 参数 = `(N-1)*30 + 1`
- 无明确 `pageCount` 字段，通过 `resultCount / 30` 估算页数

**响应示例（精简）**:
```json
{
  "code": 0,
  "data": {
    "resultCount": 117,
    "listKeyWord": "水果奇异果",
    "isPlusPin": 0,
    "intervalPrice": [
      {"value": {"min": "0", "max": "10"}},
      {"value": {"min": "10", "max": "30"}},
      {"value": {"min": "30", "max": "300"}}
    ],
    "wareList": [
      {
        "skuId": "10211819069352",
        "name": "猕猴桃纸质装箱子手水果5斤",
        "price": "19.9",
        "imageurl": "jfs/t1/.../s200x200_jfs.jpg",
        "shopId": "12345678",
        "catid": "35083",
        "cid1": "35025",
        "comment": "1234",
        "averageScore": "5",
        "color": "手5斤红心猕猴桃",
        "benefitList": [{"type": 6, "title": ["6个及以上", "免打孔"]}]
      }
    ],
    "dataBuried": {
      "pvid": "91aab0039f96437690060359cde00f40",
      "sort_type": "sort_default"
    }
  }
}
```

---

### 2.2 搜索广告位 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_adv_Search&appid=search-pc-java&keyword={keyword}&body={body_json}&x-api-eid-token={eid}&h5st={h5st}&t={timestamp}
```

**用途**: 获取搜索结果页广告位商品（展示在结果列表顶部或插入其中）。

**body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `ad_ids` | string | 广告位 ID，如 `"292:6"` |
| `xtest` | string | AB 测试标识，如 `"new_search"` |
| `ec` | string | 编码，`"utf-8"` |
| `area` | string | 省级地区 ID，如 `"53283"` |
| `page` | string | 页码 |
| `simpleSearch` | string | `"0"` 或 `"1"` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `isSimpleSearch` | number | 是否简单搜索 |
| `priceUpTypeMap` | object | 价格类型映射表 |
| `abBuriedTag` | array | AB 实验标签 |

---

### 2.3 推荐混排商品 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_mixer&appid=search-pc-java&body={body_json}&x-api-eid-token={eid}&h5st={h5st}
```

**用途**: 获取插入搜索结果中的推荐/混排商品（个性化推荐）。

**body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `lim` | number | 条数限制，如 `12` |
| `p` | number | 推荐场景 ID，如 `202002` |
| `ec` | string | 编码 |
| `uuid` | string | 用户设备 ID |
| `lid` | string | 省级地区 ID |
| `ck` | string | 推荐所需 Cookie 字段列表，如 `"pinId,lighting,pin,ipLocation,atw,aview"` |
| `page` | string | 页码 |
| `c1/c2/c3` | string | 类目 ID（可为空） |
| `brand` | string | 品牌（可为空） |

**响应**:
```json
{
  "encode": "utf-8",
  "bucket": 45,
  "data": [],
  "success": true,
  "flow": "10",
  "timestamp": 1773269791022
}
```

---

## 三、搜索辅助接口

### 3.1 AB 实验标签 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_getAbExpLabel&appid=search-pc-java&client=pc&clientVersion=1.0.0&uuid={uuid}&body={}&t={timestamp}
```

**用途**: 获取当前用户在各功能模块的 AB 实验分组，控制页面功能开关。

**响应关键字段**（`data` 下）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `conciseMode` | boolean | 是否启用简洁模式 |
| `filterNew` | boolean | 是否启用新版筛选器 |
| `newSearchShow` | boolean | 是否展示新版搜索 |
| `shopSearchShow` | boolean | 是否展示店铺搜索入口 |
| `noAdShow` | boolean | 是否隐藏广告 |
| `showSales` | boolean | 是否显示销量 |
| `aiSearch` | boolean | 是否启用 AI 搜索 |
| `newImageSearchShow` | boolean | 是否展示图片搜索 |
| `searchTagShow` | boolean | 是否展示搜索标签 |
| `abExpLabelMap` | object | 各功能模块实验标签详情，含 `keyParamMap`（开关参数）和 `label`（实验组） |

---

### 3.2 相关搜索词 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_relwords&appid=search-pc-java&client=pc&clientVersion=1.0.0&uuid={uuid}&keyword={keyword}&num=10&rettype=json&type_name=relsearch&body={"keyword":"{keyword}"}&t={timestamp}
```

**用途**: 获取关键词的相关推荐搜索词（显示在搜索框下方的热搜标签）。

**参数**:

| 参数 | 说明 |
|------|------|
| `keyword` | 搜索关键词（URL 编码），空字符串时返回通用推荐词 |
| `num` | 返回数量，如 `10` |
| `type_name` | 固定 `relsearch` |

**响应**（`data` 为数组）:
```json
[
  {"keywordType": 1, "searchKey": "水果猕猴桃", "keyword": "水果猕猴桃"},
  {"keywordType": 1, "searchKey": "佳沛阳光金奇异果", "keyword": "佳沛阳光金奇异果"}
]
```

---

### 3.3 热搜词 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_hotwords&appid=search-pc-java&client=pc&clientVersion=1.0.0&uuid={uuid}&t={timestamp}
```

**用途**: 获取全站热搜词列表（搜索框点击时展示）。

**响应**: `data` 为二维数组，每项含 `c`（类型）、`gid`（分组 ID）、`n`（显示文字）、`u`（跳转链接）、`ext_columns`（附加信息）。

---

### 3.4 搜索发现词 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_searchDiscovery&appid=search-pc-java&client=pc&clientVersion=1.0.0&uuid={uuid}&pvid={pvid}&aiSearch={aiSearch}&t={timestamp}
```

**用途**: 获取搜索发现词列表（搜索框聚焦时的热门发现，大量关键词）。

**参数**:

| 参数 | 说明 |
|------|------|
| `pvid` | 页面访问 ID（UUID 格式） |
| `aiSearch` | AI 搜索状态，`"undefined"` 或 `true/false` |

**响应**: `data.items` 为数组，每项含 `text`（关键词）和 `icon`（图标 URL，可为空）。

---

### 3.5 AI 图片分类标签 GET [重要度: ⭐⭐]

```
GET https://api.m.jd.com/api?functionId=pc_search_aiPicTagInfo&appid=search-pc-java&client=pc&clientVersion=1.0.0&uuid={uuid}&body={body_json}&t={timestamp}
```

**用途**: 根据搜索词及当前 SKU 列表，AI 识别并返回商品品类细分标签（如"黄金奇异果"、"红心奇异果"），展示为可点击的筛选 chip。

**body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `keyword` | string | 搜索关键词 |
| `sku_list` | string | 逗号分隔的 SKU ID 列表（当前页商品 ID） |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.aiPicTagInfo` | array | 标签列表，每项含 `ai_pictag_name`（标签名）和 `ai_pictag_image_url`（标签图） |
| `data.headInfo` | object | 标签区域头部配置（标题、加载文案、图标等） |
| `data.config` | object | UI 样式配置（颜色、动画等） |
| `data.buriedTag` | object | 埋点信息，含 `conversation_id`、`message_id` |

**响应示例**:
```json
{
  "code": 0,
  "data": {
    "aiPicTagInfo": [
      {"ai_pictag_name": "黄金奇异果", "ai_pictag_image_url": null},
      {"ai_pictag_name": "红心奇异果", "ai_pictag_image_url": null},
      {"ai_pictag_name": "绿心奇异果", "ai_pictag_image_url": null},
      {"ai_pictag_name": "双色奇异果", "ai_pictag_image_url": null},
      {"ai_pictag_name": "单颗尝鲜", "ai_pictag_image_url": null}
    ],
    "headInfo": {
      "head_text": "购物灵感",
      "loading_complete_text": "结合全网消费趋势，为你总结出以下热卖的水果奇异果类型"
    }
  }
}
```

---

## 四、用户与地址接口

### 4.1 地址名称查询 POST [重要度: ⭐⭐]

```
POST https://api.m.jd.com/client.action?fid=pc_address_cmpnt_getAreaNameById
Content-Type: application/x-www-form-urlencoded
```

**用途**: 根据地区 ID（省市区街道）查询完整地址名称，用于展示"配送至 XX"。

**表单参数**:

| 参数 | 说明 |
|------|------|
| `functionId` | `pc_address_cmpnt_getAreaNameById` |
| `appid` | `search-pc-java` |
| `client` | `pc` |
| `clientVersion` | `1.0.14` |
| `loginType` | `3` |
| `uuid` | 用户设备 ID |
| `x-api-eid-token` | EID token |
| `h5st` | 动态签名 |
| `body` | JSON：`{"provinceId":53283,"cityId":53480,"countyId":59926,"townId":389086,...}` |

**body 字段**:

| 参数 | 说明 |
|------|------|
| `provinceId` | 省级 ID |
| `cityId` | 市级 ID |
| `countyId` | 区县 ID |
| `townId` | 街道 ID |
| `deviceUUID` | 设备 UUID |
| `appId` | 小程序 ID |
| `bizModelCode` | 业务模型代码，如 `"3"` |
| `token` | 请求 token |
| `externalLoginType` | 外部登录类型 |

**响应**:
```json
{
  "code": "0",
  "message": "success",
  "body": {
    "provinceId": 53283, "provinceName": "海外",
    "cityId": 53480, "cityName": "英国",
    "countyId": 59926, "countyName": "England",
    "townId": 389086, "townName": "Bedfordshire",
    "complete": true,
    "hideLevel": "4"
  }
}
```

---

### 4.2 会员权益信息 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_equityInfo&appid=search-pc-java&loginType=3&x-api-eid-token={eid}&h5st={h5st}&body={}&client=pc&clientVersion=1.0.0
```

**用途**: 查询当前用户的会员权益信息（如 PLUS 会员优惠标识）。需要有效登录态，否则返回 `{"code":"1","echo":"no access"}`。

---

### 4.3 PLUS 会员信息 GET [重要度: ⭐]

```
GET https://api.m.jd.com/api?functionId=pctradesoa_queryPlusInfo&appid=search-pc-java&loginType=3&x-api-eid-token={eid}&h5st={h5st}&body={"pageId":"Search_ProductList"}&client=pc&clientVersion=1.0.0
```

**用途**: 查询当前用户 PLUS 会员状态，影响搜索结果中 PLUS 价格展示。`pageId` 固定为 `"Search_ProductList"`。

---

## 五、登录验证接口

### 5.1 SSO Cookie 验证 GET [重要度: ⭐⭐]

```
GET https://sso.jd.com/sso/rac?t={timestamp}&r={random}&s={h5st_signature}&ua={userAgent}
```

**用途**: 搜索页加载时验证登录态，同时刷新 `flash` Cookie。每次导航到搜索页时自动触发。

**参数**:

| 参数 | 说明 |
|------|------|
| `t` | 毫秒时间戳 |
| `r` | 随机字符串（9字符） |
| `s` | h5st 签名串（分号分隔多段） |
| `ua` | URL 编码的 User-Agent |

**响应**: `{"nfd": 10}` — `nfd` 含义为 "next fetch delay"（下次检查间隔，秒）。

**副作用**: 响应头中通过 `Set-Cookie` 刷新 `flash` token。

---

## 六、风控与安全接口

### 6.1 风控自定义控制 POST [重要度: ⭐]

```
POST https://api.m.jd.com/
Content-Type: application/x-www-form-urlencoded
Body: appid=risk_h5_info&functionId=getCustomCtrl&t={timestamp}&body={"scenes":["disposalGray"]}
```

**用途**: 查询当前用户是否命中灰度处置规则（风控拦截）。`hit=false` 表示正常。

---

### 6.2 SDK 调用日志上报 POST [重要度: ⭐]

```
POST https://api.m.jd.com/api
Content-Type: application/x-www-form-urlencoded
Body: appid=risk_h5_info&functionId=reportInvokeLog&body={"sdkClient":"handler","sdkVersion":"1.1.0","url":"{base64_url}","timestamp":{ts}}
```

**用途**: 上报风控 SDK 初始化日志，`url` 字段为 base64 编码的当前页面 URL。

---

## 七、底层基础设施接口

### 7.1 性能监控规则获取 GET [重要度: ⭐]

```
GET https://h5speed.m.jd.com/event/getRule?version=1.2.3&aid={aid}
```

**用途**: 获取前端性能监控的采样规则和插件配置（PV、API 错误、JS 错误等的采集开关和采样率）。

**参数**:

| 参数 | 说明 |
|------|------|
| `version` | SDK 版本，如 `1.2.3` |
| `aid` | 应用 ID（32位十六进制字符串） |

---

### 7.2 性能数据上报 POST [重要度: ⭐]

```
POST https://h5speed.m.jd.com/event/log
```

**用途**: 上报前端性能数据（首屏时间、API 耗时、JS 错误等）。

---

### 7.3 行为数据上报 POST [重要度: ⭐]

```
POST https://cactus.jd.com/behavior_report
```

**用途**: 上报用户行为事件（页面滚动、商品曝光、点击等），用于推荐系统。每次用户交互后触发多次。

---

## 八、接口调用链路

```
用户打开搜索页
│
├── [并行] sso.jd.com/sso/rac          → 验证登录态，刷新 flash Cookie
├── [并行] cactus.jd.com/request_algo  → 获取 h5st 签名算法 (tk + algo函数)
│
├── [并行，使用 h5st] api.m.jd.com/api
│   ├── pc_search_getAbExpLabel        → 获取 AB 实验分组（功能开关）
│   ├── pc_search_relwords             → 获取热搜词（keyword 为空）
│   ├── pc_search_hotwords             → 获取全站热词
│   └── pc_search_searchDiscovery      → 获取发现词列表
│
├── [主请求] pc_search_searchWare      → 获取第1页商品列表（含筛选项、价格区间）
│
├── [商品列表返回后，并行]
│   ├── pc_search_relwords             → 用实际 keyword 获取相关词（第二次，带keyword）
│   ├── pc_search_aiPicTagInfo         → 根据 sku_list 获取 AI 分类标签
│   ├── pctradesoa_equityInfo          → 获取会员权益
│   ├── pctradesoa_queryPlusInfo       → 获取 PLUS 状态
│   ├── client.action?fid=pc_address_cmpnt_getAreaNameById → 解析地区名称
│   └── cactus.jd.com/behavior_report → 上报页面 PV
│
用户滚动至底部
│
├── cactus.jd.com/request_algo         → 重新获取签名（tk 有时效性）
├── pc_search_searchWare (page=2,s=31) → 加载第2页商品
├── pc_search_adv_Search               → 加载广告位商品
└── pctradesoa_mixer                   → 加载推荐混排商品
```

---

## 九、关键发现

### h5st 签名机制（核心反爬手段）

1. **两阶段签名**：必须先调用 `cactus.jd.com/request_algo` 获取 `tk`，再用返回的 JavaScript `algo` 函数计算 SHA256 hash。
2. **tk 有时效性**：tk 以 `tk03w`（临时）或 `tk06w`（本地初始）开头，页面滚动或翻页时会重新请求并更新。
3. **expandParams 环境检测**：`request_algo` 请求体中的 `expandParams` 是混淆 JS 运行后生成的环境指纹（含浏览器特征、Canvas 指纹等），是反爬的关键。
4. **h5st 与 x-api-eid-token 联动**：两个参数必须同时正确，缺一不可。`x-api-eid-token` 对应 Cookie `3AB9D23F7A4B3CSS`。

### 分页机制

- **懒加载触发**：第2页在用户滚动到底部时自动请求，**不**需要点击翻页按钮。
- **s 参数**：每页30条，`s = (page-1)*30 + 1`。
- **同时触发广告请求**：`pc_search_adv_Search` 和 `pctradesoa_mixer` 在页面滚动后与第2页请求并发触发。

### 搜索结果为纯 AJAX

- 搜索页 HTML 骨架通过 SSR 渲染，但**商品列表本身是客户端通过 `pc_search_searchWare` 接口渲染的**，HTML 中无商品数据。
- 搜索结果的 Content-Type 为 `text/html;charset=UTF-8`（非 `application/json`），但响应体是 JSON，需注意解析。

### 地区参数影响价格和库存

- `area` 参数（省_市_区_街道）影响商品价格、配送时效、库存展示。
- `areaId` Cookie 只存省级 ID，完整四级地址存在 `ipLoc-djd` Cookie 中（格式 `省-市-区-街道`）。

### AI 标签功能

- 搜索结果返回后，页面会将第一页的所有 SKU ID 传给 `pc_search_aiPicTagInfo`，由 AI 聚类生成细分品类标签（如"黄金奇异果"、"红心奇异果"）供用户二次筛选。
- 标签点击后作为 AB 实验参数重新请求 `pc_search_searchWare`。

### sdtoken 动态更新

- 每次调用 `api.m.jd.com/api` 成功后，响应头 `X-Rp-Sdtoken` 会下发新的 `sdtoken`（格式：`set;{ttl};{token_value}`），客户端需更新对应 Cookie。
- sdtoken 有效期约 1800 秒（30分钟）。

### 筛选参数构造方式

通过在 `pc_search_searchWare` 的 `body.ev` 参数追加筛选条件：
- 品牌筛选：`body.brands = "品牌ID"`
- 价格区间：`body.price = "min-max"`
- 属性筛选：`body.ev = "attr_品类ID:属性值%5E"`（如颜色、规格等）
- 京东物流：`body.delivery = "1"`
- 旗舰店：URL 参数追加 `&shop=1`
- 仅显示有货：URL 参数 `&stock=1`
