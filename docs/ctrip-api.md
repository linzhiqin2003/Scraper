# 携程 API / 请求说明

## 概述

- **CLI Source**: `ctrip`
- **当前实现**:
  - 用户中心：SOA2 + `httpx`
  - 酒店：SOA2 API + Playwright XHR 拦截
  - 机票：低价日历走 SOA2，航班列表走 Playwright 结果页 DOM 解析
- **主域名**:
  - `www.ctrip.com`
  - `passport.ctrip.com`
  - `m.ctrip.com`
  - `flights.ctrip.com`
- **认证**:
  - 登录后导出的 cookies.txt
  - 关键 cookie: `cticket`、`login_uid`、`_udl`
  - 部分 SOA2 请求还依赖 `GUID` 生成 `_fxpcqlniredt`

## 当前代码实际使用的请求

### 1. 登录页 GET

```text
GET https://passport.ctrip.com/user/login
```

**代码入口**:

- `web_scraper/sources/ctrip/auth.py` -> `interactive_login()`

**说明**:

- 该流程不直接调登录 API，而是打开真实浏览器等待用户扫码 / 验证码 / 账密登录
- 一旦检测到 `cticket`，就把全量 cookies 导出为 Netscape 格式

### 2. 用户信息接口 POST

```text
POST https://m.ctrip.com/restapi/soa2/15201/getMemberSummaryInfo
```

**代码入口**:

- `web_scraper/sources/ctrip/scrapers/user_center.py` -> `UserCenterScraper.get_profile()`
- `web_scraper/sources/ctrip/cookies.py` -> `check_cookies_valid()`

**当前代码使用的请求参数**:

- Query: `_fxpcqlniredt={GUID}`
- Body:

```json
{
  "channel": "Online",
  "clientVersion": "99.99",
  "head": {
    "cid": "GUID or fallback",
    "ctok": "",
    "cver": "1.0",
    "lang": "01",
    "sid": "8888",
    "syscode": "09",
    "auth": "",
    "xsid": "",
    "extension": []
  }
}
```

### 3. 积分接口 POST

```text
POST https://m.ctrip.com/restapi/soa2/10182/GetAvailablePoints
```

**代码入口**:

- `web_scraper/sources/ctrip/scrapers/user_center.py` -> `UserCenterScraper.get_points()`

**当前代码使用的请求体**:

```json
{
  "head": {
    "cid": "GUID or fallback",
    "ctok": "",
    "cver": "1.0",
    "lang": "01",
    "sid": "8888",
    "syscode": "09",
    "auth": "",
    "xsid": "",
    "extension": []
  }
}
```

### 4. 未读消息接口 POST

```text
POST https://m.ctrip.com/restapi/soa2/10612/GetMessageCount
```

**代码入口**:

- `web_scraper/sources/ctrip/scrapers/user_center.py` -> `UserCenterScraper.get_messages()`

**当前代码使用的请求体**:

```json
{
  "StartTime": 0,
  "head": {
    "cid": "GUID or fallback",
    "ctok": "",
    "cver": "1.0",
    "lang": "01",
    "sid": "8888",
    "syscode": "09",
    "auth": "",
    "xsid": "",
    "extension": []
  }
}
```

### 5. 机票低价日历接口 POST

```text
POST https://m.ctrip.com/restapi/soa2/15380/bjjson/FlightIntlAndInlandLowestPriceSearch
```

**代码入口**:

- `web_scraper/sources/ctrip/scrapers/flight.py` -> `FlightLowPriceScraper.search()`

**当前代码使用的请求体**:

```json
{
  "departNewCityCode": "SHA",
  "arriveNewCityCode": "BJS",
  "startDate": "2026-03-10",
  "grade": 15,
  "flag": 0,
  "channelName": "FlightOnline",
  "searchType": 1,
  "passengerList": [
    {"passengercount": 1, "passengertype": "Adult"}
  ],
  "calendarSelections": [
    {"selectionType": 8, "selectionContent": ["15"]}
  ]
}
```

### 6. 机票结果页 GET

```text
GET https://flights.ctrip.com/online/list/oneway-sha-bjs?_=1&depdate=2026-03-10&cabin=Y_S_C_F
```

**代码入口**:

- `web_scraper/sources/ctrip/scrapers/flight.py` -> `FlightSearchScraper.search()`

**说明**:

- 机票搜索主接口带动态签名，直接 `httpx` 调用容易只拿到 `showAuthCode`
- 当前实现改为打开 PC 结果页，等待 `.flight-item.domestic` 渲染完成后直接解析 DOM
- 关键字段包括航司、航班号、起降时间、机场、价格、舱位标签、中转信息

## 代码里已定义或实际消费的业务 URL

- `https://m.ctrip.com/restapi/soa2/34951/getAdHotels`
- `https://m.ctrip.com/restapi/soa2/34951/fetchBrowseRecords`
- `https://m.ctrip.com/restapi/soa2/34951/getCityList`
- `https://hotels.ctrip.com/hotels/list`
- `https://hotels.ctrip.com/hotels/detail/`
- `https://m.ctrip.com/restapi/soa2/15380/bjjson/FlightIntlAndInlandLowestPriceSearch`
- `https://flights.ctrip.com/online/list/...`

**说明**:

- 酒店和机票相关常量已在 `ctrip/config.py` 中维护
- 机票结果页的底层 `batchSearch` 请求仍依赖前端签名，不建议脱离浏览器直接复用

## 公共请求头

```http
content-type: application/json
cookieorigin: https://www.ctrip.com
origin: https://www.ctrip.com
referer: https://www.ctrip.com/
user-agent: Chrome desktop UA
```

## 当前命令与请求映射

- `scraper ctrip login` -> 浏览器登录页，成功后导出 cookies
- `scraper ctrip status` -> `getMemberSummaryInfo`
- `scraper ctrip profile` -> `getMemberSummaryInfo`
- `scraper ctrip points` -> `GetAvailablePoints`
- `scraper ctrip messages` -> `GetMessageCount`
- `scraper ctrip search` -> 酒店搜索页 / `fetchHotelList`
- `scraper ctrip recommend` -> `getAdHotels`
- `scraper ctrip history` -> `fetchBrowseRecords`
- `scraper ctrip flight-calendar` -> `FlightIntlAndInlandLowestPriceSearch`
- `scraper ctrip flight-search` -> `flights.ctrip.com/online/list/...` 页面 DOM 解析
