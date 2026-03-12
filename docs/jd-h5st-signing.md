# 京东 h5st SignatureOracle 签名方案

## 概述

京东前端 API（`api.m.jd.com`）使用 h5st 签名参数进行反爬保护。h5st 是一个多段分号分隔的加密字符串，版本已迭代至 5.3，纯算还原难度极高。

本项目采用 **SignatureOracle 模式**：在 Playwright 浏览器中加载京东页面，复用页面内置的 JS 签名 SDK（`window.ParamsSign`）生成 h5st，再用 httpx 发起实际 API 请求。这种方式无需逆向算法，且不惧版本更新。

## h5st 参数格式

```
时间戳;随机字符串;appId;token;sign_hash;5.3;毫秒时间戳;加密payload;hash2;hash3
```

示例：
```
20260311120000;abc123def;fb5df;tk_xxx;a1b2c3...;5.3;1741680000000;encrypted...;hash2;hash3
```

## SignatureOracle 实现

### 核心原理

1. 启动 Playwright 浏览器，注入 cookies，访问任意京东商品页
2. 页面加载后，JS 签名 SDK 自动初始化，`window.ParamsSign` 可用
3. 通过 `page.evaluate()` 调用 `new ParamsSign({appId}).sign(params)` 生成签名
4. 将签名后的参数（含 h5st）用于 httpx 直接请求 API

### 关键发现

#### 1. ParamsSign 入口

京东商品页加载完成后，以下全局对象可用：

| 对象 | 说明 |
|------|------|
| `window.ParamsSign` | 签名构造函数，`new ParamsSign({appId}).sign(params)` |
| `window.PSign` | 预初始化的签名实例 |
| `window.PSignCom` | 同上，不同组件使用 |
| `window.PSignComElevator` | 同上 |

所有预初始化实例的 `__appId` 均为 `fb5df`。

#### 2. appId 陷阱

API 请求的 `appid` 参数（如 `pc-rate-qa`）与签名 SDK 的 `appId`（`fb5df`）是**不同的概念**：

- `appid=pc-rate-qa`：放在请求参数中，标识调用方
- `appId=fb5df`：传给 `ParamsSign` 构造函数，用于签名计算

**错误做法**：`new ParamsSign({appId: 'pc-rate-qa'}).sign(params)` → 签名无效，403
**正确做法**：`new ParamsSign({appId: 'fb5df'}).sign(params)` → 签名有效

#### 3. uuid 参数

API 请求必须携带 `uuid` 参数，来源于 `__jda` cookie：

```javascript
// __jda 格式: 122270672.1741680000000.1741680000000.1741680000000.1741680000000.1
// uuid = 第二段（按 . 分割）
const jda = document.cookie.split(';').find(c => c.trim().startsWith('__jda='));
const uuid = jda.split('=')[1].split('.')[1];  // "1741680000000"
```

#### 4. sign() 返回值

`ParamsSign.sign()` 返回 Promise，resolve 后得到包含所有原始参数 + 签名字段的对象：

```javascript
{
  functionId: "getCommentListPage",
  appid: "pc-rate-qa",
  body: "{...}",
  t: "1741680000000",
  // ... 其他原始参数
  h5st: "20260311...;abc123;fb5df;tk_xxx;...",  // 签名结果
  _stk: "appid,body,client,...",                 // 签名字段列表
  _ste: "1"                                       // 签名类型
}
```

### 代码位置

- `web_scraper/sources/jd/h5st.py` — SignatureOracle 类
- `web_scraper/sources/jd/scrapers/comment.py` — CommentScraper API 模式调用示例

### 使用示例

```python
from web_scraper.sources.jd.h5st import SignatureOracle

with SignatureOracle(cookies_path) as oracle:
    params = {
        "functionId": "getCommentListPage",
        "appid": "pc-rate-qa",
        "client": "pc",
        "clientVersion": "1.0.0",
        "t": str(int(time.time() * 1000)),
        "loginType": "3",
        "uuid": oracle.uuid,
        "body": json.dumps({"sku": "10212262468526", "pageNum": 1, ...}),
    }
    signed = oracle.sign(params)  # 自动使用 fb5df 作为 appId

    # 用 httpx 发请求
    resp = httpx.post(
        "https://api.m.jd.com/client.action",
        params=signed,
        headers={"referer": "https://item.jd.com/"},
    )
```

## getCommentListPage API

### 端点

```
POST https://api.m.jd.com/client.action
```

### 请求参数（query string）

| 参数 | 值 | 说明 |
|------|-----|------|
| functionId | getCommentListPage | 接口标识 |
| appid | pc-rate-qa | 调用方标识 |
| client | pc | 客户端类型 |
| clientVersion | 1.0.0 | 版本 |
| t | 毫秒时间戳 | 请求时间 |
| loginType | 3 | 登录类型 |
| uuid | __jda cookie 第二段 | 设备标识 |
| body | JSON 字符串 | 请求体 |
| h5st | 签名值 | SignatureOracle 生成 |
| _stk | 字段列表 | 签名覆盖字段 |
| _ste | 1 | 签名类型 |

### body 参数

```json
{
  "sku": "10212262468526",
  "score": "0",
  "sortType": "5",
  "pageNum": 1,
  "pageSize": 10,
  "category": "",
  "isShadow": "0",
  "extInfo": {
    "spuId": "",
    "commentRate": "",
    "needTopAlbum": "",
    "userGroupComment": ""
  }
}
```

| 参数 | 说明 |
|------|------|
| score | 0=全部, 1=差评, 2=中评, 3=好评, 4=有图, 5=追评 |
| sortType | 5=默认(推荐), 6=按时间 |
| pageNum | 页码，从 1 开始 |
| pageSize | 每页数量，默认 10 |

### 响应结构

响应采用 floor（楼层）嵌套结构，通过 `mId` 标识不同数据块：

```
floors[]
├── mId: "commentlist-list"      → data.commentInfoList[] (评论列表)
├── mId: "commentlist-ratestar"  → subFloors[]
│   └── mId: "commentlist-label" → subFloors[]
│       └── mId: "commentlist-commonlabel" → data.generalTagList[] (标签)
└── ...
```

评论字段：`userNickName`, `commentData`, `commentScore`, `commentDate`, `wareAttribute`, `pictureCnt`, `publishArea`

标签字段：`generalTagList[].name`, `.count`（其中 name="ALL" 的 count 为总评论数）

## 双策略架构

CommentScraper 支持两种策略：

| 策略 | 命令参数 | 原理 | 优势 | 劣势 |
|------|----------|------|------|------|
| API (默认) | `--strategy api` | SignatureOracle 签名 + httpx 请求 | 支持筛选/排序/完整分页，风控暴露低 | 需启动浏览器初始化签名 |
| Playwright | `--strategy playwright` | 浏览器打开评论弹窗，拦截 API 响应 | 无需理解签名机制 | 仅获取默认排序，风控暴露高 |

```bash
# API 模式（推荐）
scraper jd comments 10212262468526 -n 100 --score good --sort time

# Playwright 模式（备用）
scraper jd comments 10212262468526 -n 50 --strategy playwright
```

## 反检测与风控处理

### 反检测措施

1. **隐藏 webdriver 属性**：`navigator.webdriver` 返回 `undefined`
2. **禁用自动化特征**：`--disable-blink-features=AutomationControlled`
3. **真实 viewport**：`1440x900`（过小的 viewport 会导致页面元素不渲染）
4. **Chrome UA**：模拟 Chrome 131

### 风控触发与恢复

当 JD 检测到异常时，会重定向至滑动验证码页面：

```
https://cfe.m.jd.com/privatedomain/risk_handler/?evtype=2&...
```

**恢复方法**：在本地浏览器中访问 `https://item.jd.com`，手动完成滑动验证码，然后重试。

代码中已实现风控检测：

```python
if "risk_handler" in page.url or "passport.jd.com" in page.url:
    raise Exception("JD risk control triggered...")
```

## 踩坑记录

### 1. viewport 影响页面渲染

**问题**：Playwright 默认 viewport 较小，京东评论弹窗不渲染，导致无法拦截 `getCommentListPage` 请求。

**解决**：设置 `viewport={"width": 1440, "height": 900}`。

### 2. POST body 中的 functionId

**问题**：`getCommentListPage` 的 `functionId` 不在 URL query string 中，而是在 POST form body 里，导致拦截 handler 无法匹配。

**解决**：同时检查 URL 参数和 POST body：

```python
def _extract_function_id(response):
    # 先查 URL query
    params = parse_qs(urlparse(response.url).query)
    fid = params.get("functionId", [None])[0]
    if fid:
        return fid
    # 再查 POST body
    post_data = response.request.post_data
    if post_data:
        body_params = parse_qs(post_data)
        return body_params.get("functionId", [None])[0]
```

### 3. 签名 appId ≠ 请求 appid

**问题**：将请求参数中的 `appid=pc-rate-qa` 传给 `ParamsSign({appId: 'pc-rate-qa'})`，签名无效返回 403。

**解决**：签名时使用 `PSign.__appId`（即 `fb5df`），请求参数中保留 `appid=pc-rate-qa`。

### 4. uuid 参数缺失

**问题**：缺少 `uuid` 参数导致 API 返回错误。

**解决**：从 `__jda` cookie 提取（第二段，按 `.` 分割），或在浏览器中通过 `document.cookie` 读取。

### 5. 嵌套 floor 结构

**问题**：标签数据（`commentlist-commonlabel`）不在顶层 floor 中，而是嵌套在 `commentlist-ratestar` → `commentlist-label` → `commentlist-commonlabel` 的 subFloor 链中。

**解决**：实现递归搜索函数 `_find_in_floors(floors, target_mid)`。

## h5st 方案对比（供参考）

| 方案 | 复杂度 | 稳定性 | 性能 | 本项目选择 |
|------|--------|--------|------|-----------|
| 纯 Python 算法还原 | 极高（5.x 有 VMP 保护） | 版本更新即失效 | 最快 | ✗ |
| Node.js 补环境 | 中等 | 较好 | 中等 | ✗ |
| Playwright SignatureOracle | 低 | 最稳定 | 较慢（需浏览器） | ✓ |

选择 Playwright SignatureOracle 的原因：
1. 项目已有 Playwright 基础设施
2. 与知乎 SignatureOracle 模式一致
3. 无需逆向 h5st 算法，自动适应版本更新
4. 实际 API 调用使用 httpx，风控暴露低于纯浏览器方案

## Node.js 无浏览器方案尝试（2026-03-11，已放弃）

### 目标

完全去除 Playwright 依赖，用 Node.js + jsdom 替代浏览器生成 h5st 签名。

### 实现

- `js/h5st_sign.js`：jsdom 环境加载 JD SDK（loader + main），mock canvas/crypto/localStorage/XMLHttpRequest
- `h5st_node.py`：Python 封装，subprocess 启动 Node.js 进程，JSON lines 协议通信（serve 模式）
- `js/package.json`：依赖 jsdom + xmlhttprequest-ssl

### 关键突破

1. **SDK 加载成功**：jsdom 中 `ParamsSign` / `ParamsSignMain` 均可用
2. **tk03 服务端令牌获取**：warm-up sign 触发 XHR → `cactus.jd.com/request_algo` → 返回 tk03 令牌（非 tk06 fallback）
3. **签名格式正确**：生成的 h5st 为标准 10 段分号分隔格式，含 tk03 token

### 失败原因

**h5st 内嵌设备指纹被服务端拒绝。**

h5st 签名不仅是加密校验，还包含 SDK 采集的设备指纹（canvas hash、WebGL 数据、屏幕参数等）。jsdom 无法提供真实的 canvas 渲染和 WebGL context，SDK 采集到的指纹与真实浏览器差异过大，JD 服务端验签时识别为非浏览器环境，返回 403。

验证方式：

| 签名来源 | HTTP 客户端 | 结果 |
|----------|------------|------|
| Playwright | httpx | 200 |
| Playwright | Node.js https | 200（推测） |
| Node.js jsdom | httpx | **403** |
| Node.js jsdom | Node.js https | **403** |
| Node.js jsdom | Node.js http2 | **403** |

关键对比：同一 httpx 客户端，Playwright 签名 200 而 Node.js 签名 403，证明问题在 h5st 内容而非 TLS 指纹。

### 尝试过的 HTTP 层优化（均无效）

- Node.js `https` 模块 + Chrome cipher suites
- Node.js `http2` 模块（Chrome 默认 H2）
- Chrome TLS sigalgs 配置

### 结论

纯 Node.js 方案不可行。h5st v5.3 的安全设计将设备指纹深度绑定到签名中，无法通过 mock DOM 环境绕过。保持 Playwright SignatureOracle + httpx 的混合架构。

### 保留代码

`h5st_node.py` 和 `js/h5st_sign.js` 保留在代码库中，虽然未被主流程使用，但可用于：
- 调试 h5st 签名机制
- 未来若 JD 放松指纹校验可快速启用

## 搜索 API 端点差异（2026-03-12）

### 发现

JD 不同 API 端点对 TLS 指纹的校验策略不同：

| 端点 | 方法 | Playwright h5st + httpx | 浏览器拦截 |
|------|------|------------------------|-----------|
| `api.m.jd.com/client.action` | POST | **200** | 200 |
| `api.m.jd.com/api` | GET | **403** | 200 |

- **评论 API** (`getCommentListPage`) 走 `/client.action`（POST），SignatureOracle + httpx 可行
- **搜索 API** (`pc_search_searchWare`) 走 `/api`（GET），httpx 被 TLS 指纹拦截，**必须用浏览器请求**

### 搜索 API 签名 appId

搜索页的 h5st 签名使用 `appId=f06cc`（非商品页的 `fb5df`）：

```
# 从浏览器拦截的实际请求
fid=pc_search_searchWare    h5st_appId=f06cc
fid=pctradesoa_equityInfo   h5st_appId=fb5df
fid=pcCart_jc_getCartNum     h5st_appId=f06cc 或 fb5df
```

部分辅助接口（`pc_search_relwords`、`pc_search_hotwords` 等）不携带 h5st。

### 搜索方案选择

由于 `/api` 端点的 TLS 校验，搜索功能采用 **Playwright 全程拦截模式**（非 SignatureOracle + httpx 混合模式）：

1. Playwright 导航到 `search.jd.com/Search?keyword=...`
2. 拦截 `pc_search_searchWare` 的 API 响应
3. 翻页通过导航到 `page=N` URL 实现
4. 解析 `wareList` 提取商品数据

### wareList 字段映射

API 文档中的字段名与实际响应不完全一致：

| 文档字段 | 实际字段 | 说明 |
|----------|----------|------|
| `name` | `wareName` | 商品名，含 HTML 高亮标签需 strip |
| `price` | `jdPrice` | 当前售价 |
| `imageurl` | `imageurl` | 相对路径，需拼接 CDN 前缀 |

`wareName` 中包含 `<font class="skcolor_ljg">关键词</font>` 格式的搜索高亮，需要 `re.sub(r'<[^>]+>', '', text)` 清除。
