# 知乎 API / 请求说明

## 概述

- **CLI Source**: `zhihu`
- **当前实现**: 纯 API 优先，其次浏览器签名 API，再其次响应拦截 / DOM 回退
- **主域名**:
  - `www.zhihu.com`
- **认证**: 依赖导入或登录后保存的 cookies，尤其是 `d_c0`

## 当前代码实际使用的接口

### 1. 搜索接口 GET

```text
GET https://www.zhihu.com/api/v4/search_v3
```

**代码入口**:

- `web_scraper/sources/zhihu/api_client.py` -> `PureAPIClient.search()`
- `web_scraper/sources/zhihu/api_client.py` -> `ZhihuAPIClient.search()`

**当前代码使用的关键参数**:

```json
{
  "t": "general",
  "q": "transformer",
  "correction": 1,
  "offset": 0,
  "limit": 20
}
```

**说明**:

- 分页通过 `offset` 推进
- `t` 可切换不同搜索类型，如 `general` / `topic` / `people`
- 当前实现最多保守拉取 5 页

### 2. 回答详情接口 GET

```text
GET https://www.zhihu.com/api/v4/answers/{answer_id}?include=content,voteup_count,comment_count,created_time,updated_time
```

**代码入口**:

- `web_scraper/sources/zhihu/api_client.py` -> `PureAPIClient.fetch_answer()`
- `web_scraper/sources/zhihu/api_client.py` -> `ZhihuAPIClient.fetch_answer()`

### 3. 文章详情接口 GET

```text
GET https://www.zhihu.com/api/v4/articles/{article_id}?include=content,voteup_count,comment_count,created,updated
```

**代码入口**:

- `web_scraper/sources/zhihu/api_client.py` -> `PureAPIClient.fetch_article()`
- `web_scraper/sources/zhihu/api_client.py` -> `ZhihuAPIClient.fetch_article()`

### 4. 问题详情接口 GET

```text
GET https://www.zhihu.com/api/v4/questions/{question_id}
```

**说明**:

- 当前代码在响应拦截器里识别该模式，但核心 CLI 主要用搜索 / 回答 / 文章接口

## 鉴权与签名

### 必要请求头

- `Referer: https://www.zhihu.com/`
- `Origin: https://www.zhihu.com`
- `x-requested-with: fetch`
- `x-zse-93: 101_3_3.0`
- `x-zse-96: ...` 由本地签名逻辑或浏览器 JS 生成

### 依赖 Cookie

- `d_c0` 是纯 API 模式初始化的关键 Cookie
- 其他知乎 cookies 也会一并从 `browser_state.json` 注入到 `httpx.Client`

## 当前命令与请求映射

- `scraper zhihu search ... --strategy pure_api` -> 直接调用 `/api/v4/search_v3`
- `scraper zhihu fetch ... --strategy pure_api` -> `/api/v4/answers/*` 或 `/api/v4/articles/*`
- `--strategy api` -> 仍是 API，但签名由浏览器提供
- `--strategy intercept` -> 页面加载时拦截内部 API 响应

## 风控与回退

- API 返回异常状态码时会经过 `BlockDetector` 判断是否被限流或鉴权失败
- `pure_api` 失败后，自动策略会继续尝试浏览器签名 API 和拦截方案
