# WSJ SSO 登录接口文档

## 概述

- **登录页地址**: `https://sso.accounts.dowjones.com/login-page`
- **API 域名**: `sso.accounts.dowjones.com`
- **认证方式**: OAuth2 Authorization Code Flow
- **框架**: React (Zustand state management)
- **反bot**: DataDome (`captcha-delivery.com`)
- **realm**: `DJldap`（WSJ 主站）/ `FNAuth`（Financial News）

## OAuth2 配置

| 参数 | 值 |
|------|-----|
| `client_id` | `5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO` |
| `response_type` | `code` |
| `redirect_uri` | `https://accounts.wsj.com/auth/sso/login` |
| `scope` | `openid idp_id roles email given_name family_name djid djUsername djStatus trackid tags prts updated_at created_at` |
| `tenant` | `b2c` |
| `issuer` | `https://sso.accounts.dowjones.com/` |

## 公共请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `Accept` | `application/json` | |
| `Content-Type` | `application/json` | |
| `X-REQUEST-SCHEME` | `https` | |
| `X-REMOTE-USER` | `{email}` | 当前登录邮箱 |
| `X-REQUEST-EDITIONID` | (动态) | 版本 ID，由 `ge()` 函数生成 |

## CSRF Token

页面加载时通过内联 `<script>` 注入 `AUTH_CONFIG`（Base64 编码 JSON），其中 `extraParams._csrf` 字段包含 CSRF token。每次页面加载都会生成新的 token。

```javascript
const config = JSON.parse(atob(AUTH_CONFIG));
const csrf = config.extraParams._csrf;
```

---

## 登录流程

### 两步登录（邮箱 + 密码）

```
用户输入邮箱 → POST /start → 显示密码框 → POST /authenticate → 302 redirect → callback → 设置 cookies
```

### 一键验证码登录（Passwordless OTP）

```
用户输入邮箱 → POST /passwordless/start → 发送验证码到邮箱 → POST /passwordless/verify → 302 redirect → callback → 设置 cookies
```

---

## 一、/start — 邮箱预检查

```
POST https://sso.accounts.dowjones.com/start
```

**用途**: 验证邮箱是否存在，返回下一步操作提示

**Request Body**:

```json
{
  "username": "user@example.com",
  "client_id": "5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO",
  "csrf": "{_csrf from AUTH_CONFIG}"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 邮箱或用户名 |
| `client_id` | string | 是 | OAuth2 client ID，从 URL 参数 `client` 获取 |
| `csrf` | string | 是 | CSRF token，从 `AUTH_CONFIG.extraParams._csrf` 获取 |

---

## 二、/authenticate — 密码登录

```
POST https://sso.accounts.dowjones.com/authenticate
```

**用途**: 提交邮箱和密码进行认证

**Request Body**:

```json
{
  "username": "user@example.com",
  "password": "user_password",
  "state": "brand%3Dmw",
  "client_id": "5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO",
  "csrf": "{_csrf}",
  "response_mode": null,
  "scope": "openid idp_id roles email given_name family_name djid djUsername djStatus trackid tags prts updated_at created_at",
  "code_challenge": null,
  "realm": "DJldap",
  "code_challenge_method": null,
  "nonce": "{nonce from URL}",
  "ui_locales": "en-us-x-wsj-83-2",
  "redirect_uri": "https://accounts.wsj.com/auth/sso/login",
  "response_type": "code"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 是 | 邮箱 |
| `password` | string | 是 | 密码 |
| `state` | string | 是 | 默认 `brand%3Dmw`，从 AUTH_CONFIG.extraParams.state 获取 |
| `client_id` | string | 是 | OAuth2 client ID |
| `csrf` | string | 是 | CSRF token |
| `scope` | string | 是 | OAuth2 scope |
| `realm` | string | 是 | `DJldap`（WSJ）或 `FNAuth`（FN） |
| `nonce` | string | 是 | 从 URL 参数或 AUTH_CONFIG 获取 |
| `redirect_uri` | string | 是 | 回调地址 |
| `response_type` | string | 是 | `code` |
| `ui_locales` | string | 否 | 语言设置 |
| `response_mode` | string | 否 | 通常为 null |
| `code_challenge` | string | 否 | PKCE（通常为 null） |
| `code_challenge_method` | string | 否 | PKCE 方法（通常为 null） |

**认证成功响应**:

- 返回 302 重定向到 `redirect_uri`，URL 中携带 `code` 参数
- `https://accounts.wsj.com/auth/sso/login?code={authorization_code}&state={state}`
- 回调页面交换 code 为 access_token 并设置 session cookies

---

## 三、/passwordless/start — 发送 OTP 验证码

```
POST https://sso.accounts.dowjones.com/passwordless/start
```

**用途**: 向用户邮箱发送一次性验证码

**Request Body**:

```json
{
  "username": "user@example.com",
  "connection": "email",
  "send": "code",
  "client_id": "5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO",
  "csrf": "{_csrf}",
  "scope": "openid idp_id roles ...",
  "nonce": "{nonce}",
  "ui_locales": "en-us-x-wsj-83-2",
  "redirect_uri": "https://accounts.wsj.com/auth/sso/login",
  "response_type": "code"
}
```

---

## 四、/passwordless/verify — 验证 OTP

```
POST https://sso.accounts.dowjones.com/passwordless/verify
```

**用途**: 提交 OTP 验证码完成认证

**Request Body**:

```json
{
  "username": "user@example.com",
  "otp": "123456",
  "state": "brand%3Dmw",
  "client_id": "5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO",
  "csrf": "{_csrf}",
  "scope": "openid idp_id roles ...",
  "realm": "DJldap",
  "nonce": "{nonce}",
  "ui_locales": "en-us-x-wsj-83-2",
  "redirect_uri": "https://accounts.wsj.com/auth/sso/login",
  "response_type": "code"
}
```

---

## 五、其他页面路由

| 路由 | 说明 |
|------|------|
| `#/signin` | 登录首页 |
| `#/signin-password` | 密码输入页 |
| `#/otp-request` | OTP 验证码输入页 |
| `#/email-verification` | 邮箱验证页 |
| `#/forgot-credential/username` | 忘记用户名 |
| `#/forgot-credential/password` | 忘记密码 |
| `#/reset-password` | 重置密码 |
| `#/reset-password/confirmation` | 重置确认 |
| `#/verify-registration` | 注册验证 |

---

## 六、关键发现

### 自动登录可行性分析

**密码登录方式** (`/start` → `/authenticate`):

1. ✅ API 端点和参数已完全解析
2. ⚠️ **CSRF token** 每次页面加载动态生成，需先 GET 登录页获取
3. ⚠️ **nonce** 每次生成新 UUID，需从登录页 URL 或 AUTH_CONFIG 提取
4. ❌ **DataDome 反bot** — 纯 HTTP 请求大概率被拦截，需要：
   - 通过 DataDome CAPTCHA 挑战
   - 或使用真实浏览器绕过（`--disable-blink-features=AutomationControlled`）
5. ⚠️ 可能触发 reCAPTCHA（未验证，需实际测试）

**推荐实现方案**:

使用 Playwright + 连接到用户真实 Chrome（CDP 模式）：

```python
# 1. 启动 Chrome 带 remote-debugging-port（无 --enable-automation 标志）
# 2. Playwright connect_over_cdp("http://localhost:9222")
# 3. 导航到 SSO 登录页
# 4. 填入邮箱和密码
# 5. 点击 Continue → 等待密码框 → 输入密码 → 点击 Sign In
# 6. 等待 redirect 完成
# 7. 提取 cookies 保存到 ~/.web_scraper/wsj/cookies.txt
```

**不推荐纯 HTTP 方案**：DataDome 会检测 TLS fingerprint、请求频率、行为模式等，纯 HTTP 几乎必然被拦截。

### DataDome 反bot 机制

- 服务商：DataDome (`captcha-delivery.com`, `ct.captcha-delivery.com`)
- 检测方式：IP 信誉、TLS fingerprint、`navigator.webdriver`、Chrome automation flags
- 一旦 IP 被标记，即使正常浏览器也需要通过 CAPTCHA 才能访问
- 使用 `--disable-blink-features=AutomationControlled` 可隐藏自动化标志

### Cookie 生命周期

WSJ cookies 时效性较短（用户反馈），失效后需重新登录。自动化重登录需要存储用户凭据（邮箱+密码）或使用 OTP 方式。
