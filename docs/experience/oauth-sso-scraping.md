# OAuth SSO 登录自动化经验

## 核心原则

**永远走网站的正常登录流程，不要硬编码 OAuth URL。**

OAuth 的 `redirect_uri`、`client_id`、`scope`、`state`、`nonce` 等参数都可能随时变化。硬编码会在网站更新时失效。

## 正确做法

```
1. 访问网站首页
2. 找到 "登录" / "Sign In" 按钮并点击
3. 让浏览器自然跟随重定向链到达 SSO 页面
4. 在 SSO 页面填写凭证
5. 让浏览器自然完成回调和 cookie 设置
```

## WSJ SSO 流程实例

### 发现过程

1. **初始方案**：硬编码 SSO URL `sso.accounts.dowjones.com/login-page?...&redirect_uri=accounts.wsj.com/auth/sso/login`
2. **问题**：回调地址 `accounts.wsj.com/auth/sso/login` 返回 CloudFront 404
3. **调试**：抓取真实登录流程的重定向链
4. **发现**：WSJ 已将回调从 `accounts.wsj.com/auth/sso/login` 迁移到 `www.wsj.com/client/auth`

### 真实重定向链

```
www.wsj.com
  → 点击 "Sign In"
  → www.wsj.com/client/login?target=...
  → 302 → sso.accounts.dowjones.com/authorize?
          client_id=5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO
          &redirect_uri=https://www.wsj.com/client/auth  ← 新的回调地址
          &scope=openid idp_id roles ...
          &nonce=xxx
          &state=https://www.wsj.com
  → 302 → sso.accounts.dowjones.com/login-page?...
  → (用户填写邮箱/密码)
  → sso.accounts.dowjones.com/continue?state=...
  → 302 → www.wsj.com/client/auth?code=xxx&state=yyy
  → 302 → www.wsj.com
```

### AUTH_CONFIG

SSO 登录页通过 Base64 编码的 JSON 注入配置：

```javascript
const config = JSON.parse(atob(AUTH_CONFIG));
// config.callbackURL = "https://www.wsj.com/client/auth"
// config.clientID = "5hssEAdMy0mJTICnJNvC9TXEw3Va7jfO"
// config.extraParams._csrf = "..."
```

可以用这个检查当前实际的回调地址。

## 通用 OAuth 登录自动化模式

```python
# 1. 访问首页，建立 cookie 上下文
page.goto("https://www.example.com")
solve_captcha_if_needed(page)
dismiss_consent_dialogs(page)

# 2. 点击登录按钮（不要直接 goto SSO URL）
page.locator('a:has-text("Sign In")').click()
time.sleep(5)
solve_captcha_if_needed(page)

# 3. 填写凭证
page.fill("#email", email)
page.fill("#password", password)
page.click("#submit")

# 4. 处理中间页面（邮箱验证、同意条款等）
while not on_target_site(page):
    handle_interstitial_pages(page)
    solve_captcha_if_needed(page)

# 5. 等待 JS 设置 cookies
page.wait_for_load_state("networkidle")
time.sleep(5)

# 6. 提取并保存 cookies
cookies = ctx.cookies()
save_cookies(cookies)
```

## 常见陷阱

### 1. Cookie 域名不匹配

OAuth 回调 URL 的域名很重要。如果回调到 `accounts.example.com`，浏览器只会发送 `accounts.example.com` 域的 cookies。如果该域没有必要的 cookie（如 DataDome），请求可能被 WAF 拦截。

**解决**：先访问目标域的首页，让 WAF/CDN 设置必要的 cookies。

### 2. 隐私弹窗阻挡点击

很多网站有 GDPR/CCPA 同意弹窗，作为 `<iframe>` 覆盖在页面上，拦截所有 pointer events：

```
<iframe title="SP Consent Message">  ← 阻挡了下面的按钮
<a>Sign In</a>                       ← 无法点击
```

**解决**：先进入 iframe 关闭弹窗，再操作页面。

### 3. 回调页面返回 404/403

可能原因：
- 回调地址已过时（网站更新）
- 缺少必要的 cookies（DataDome 等 WAF）
- CloudFront/CDN 配置变更

**调试**：`curl -sI "https://callback-url"` 检查路由是否存在。

### 4. Cookies 异步设置

认证 cookies 可能不是由 HTTP Set-Cookie 头直接设置，而是由页面 JS 异步设置：

```javascript
// 页面 JS 可能在 DOMContentLoaded 后异步调用 API 设置 cookies
fetch('/api/session').then(r => r.json()).then(data => {
    document.cookie = `DJSESSION=${data.session}; ...`;
});
```

**解决**：到达目标页面后至少等 5 秒 + `networkidle`。
