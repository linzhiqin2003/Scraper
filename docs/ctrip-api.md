# 携程 API / 请求说明

## 概述

- **CLI Source**: `ctrip`
- **当前实现**: 以用户中心 SOA2 接口为主，登录流程通过浏览器拿 cookie，业务请求通过 `httpx` 直连
- **主域名**:
  - `www.ctrip.com`
  - `passport.ctrip.com`
  - `m.ctrip.com`
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

## 代码里已定义但当前 CLI 未直接消费的 URL

- `https://m.ctrip.com/restapi/soa2/34951/getAdHotels`
- `https://m.ctrip.com/restapi/soa2/34951/fetchBrowseRecords`
- `https://m.ctrip.com/restapi/soa2/34951/getCityList`
- `https://hotels.ctrip.com/hotels/list`
- `https://hotels.ctrip.com/hotels/detail/`

**说明**:

- 这些常量已经在 `ctrip/config.py` 里准备好，但当前命令集主要仍聚焦用户中心能力

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
