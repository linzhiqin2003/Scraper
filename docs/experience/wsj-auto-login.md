# WSJ 自动登录经验总结

## 背景

WSJ (华尔街日报) cookies 有效期较短，需要频繁重新登录。目标是实现自动化登录并持久化 cookies。

## 技术方案

使用 **Patchright**（Playwright 的反检测分支）自动登录，自动过 DataDome 滑块验证码。

### 为什么用 Patchright 而不是普通 Playwright

- Playwright 会被 DataDome 检测到 `navigator.webdriver=true` 和 Chrome automation flags
- Patchright 隐藏了这些自动化标志，DataDome 无法区分自动化浏览器和真实用户
- 安装：`poetry add patchright`

## 关键经验

### 1. 登录入口必须从 wsj.com 首页进入

**错误做法**：直接硬编码 SSO URL

```
https://sso.accounts.dowjones.com/login-page?...&redirect_uri=https://accounts.wsj.com/auth/sso/login
```

这个回调地址 `accounts.wsj.com/auth/sso/login` **已经返回 404**（CloudFront 报错）。

**正确做法**：从 wsj.com 首页点击 Sign In

```
www.wsj.com → 点击 "Sign In"
  → www.wsj.com/client/login
  → 302 → sso.accounts.dowjones.com/authorize?redirect_uri=https://www.wsj.com/client/auth
  → SSO login-page
```

关键区别：
- 旧回调：`accounts.wsj.com/auth/sso/login` → **404 Not Found**
- 新回调：`www.wsj.com/client/auth` → **302 → www.wsj.com** (正常工作)

**教训**：不要硬编码 OAuth 回调地址，应该走网站的正常登录流程，让前端 JS 动态生成正确的参数。

### 2. Cookie 域名和回调的关系

回调 URL 的域名决定了哪些 cookies 会被发送：

- 回调到 `accounts.wsj.com` → 浏览器发送 `accounts.wsj.com` 的 cookies
- 回调到 `www.wsj.com` → 浏览器发送 `www.wsj.com` 和 `.wsj.com` 的 cookies

从 wsj.com 首页进入会先在 `.wsj.com` 域设置 DataDome cookie，后续回调到 `www.wsj.com/client/auth` 时会携带这些 cookies，避免被 WAF 拦截。

### 3. JS 异步设置 Cookies 需要等待

到达 wsj.com 后，不能立即提取 cookies。关键认证 cookie（如 `DJSESSION`、`wsjregion`）是由页面 JS **异步** 设置的：

```python
# 等待页面完全加载
page.wait_for_load_state("networkidle", timeout=15000)
# 额外等 5 秒让 JS 设置所有 cookies
time.sleep(5)
```

不等待：~21 个 cookies（缺少认证 cookie）
等待 5s+：~73-193 个 cookies（包含 DJSESSION、wsjregion 等）

### 4. `connect.sid` 是新的认证 Cookie

WSJ 后端从旧架构迁移到了 Express.js（Node.js），认证 cookie 从 `DJSESSION` 变成了 `connect.sid`：

- `connect.sid`：Express.js session cookie，是主要的认证凭证
- `DJSESSION`、`wsjregion`：可能不再出现，取决于页面加载时间

Cookie 验证逻辑需要同时接受新旧两种 cookie。

### 5. SP Consent Message 弹窗会阻挡点击

wsj.com 首页有一个隐私同意弹窗（`<iframe title="SP Consent Message">`），它会拦截所有 pointer events，导致 Sign In 按钮无法点击：

```python
def _dismiss_consent_dialog(page):
    try:
        consent = page.frame_locator('iframe[title="SP Consent Message"]')
        btn = consent.locator('button:has-text("Yes, I Agree")')
        if btn.count() > 0:
            btn.first.click()
    except Exception:
        pass
```

必须在点击 Sign In 之前先关闭这个弹窗。

### 6. DataDome 滑块验证码自动解决

DataDome 使用 `.slider` 和 `.sliderTarget` 两个元素实现滑块验证码：

```python
# 在 captcha iframe 中获取滑块信息
slider_info = captcha_frame.evaluate("""() => {
    const slider = document.querySelector('.slider');
    const target = document.querySelector('.sliderTarget');
    const sr = slider.getBoundingClientRect();
    const tr = target.getBoundingClientRect();
    return {
        sx: sr.x + sr.width / 2,
        sy: sr.y + sr.height / 2,
        distance: tr.x - sr.x
    };
}""")
```

拟人化拖动要点：
- 使用 cubic ease-out 曲线：`ease = 1 - (1 - t)**3`
- Y 轴添加随机抖动：`random.uniform(-2, 2)`
- 步数随机：`random.randint(20, 30)`
- 每步之间随机延迟：`random.uniform(0.01, 0.04)`

### 7. Patchright evaluate() 必须用箭头函数

Patchright 的 `frame.evaluate()` 不支持裸 `return` 语句（与原生 CDP 不同）：

```python
# 错误 - SyntaxError: Illegal return statement
frame.evaluate("return document.title")

# 正确
frame.evaluate("() => document.title")
frame.evaluate("() => { return document.title; }")
```

### 8. CAPTCHA 解决后的判定

CAPTCHA 解决后，不能只检查 iframe 是否消失（可能短暂存在），还要检查页面标题变化：

```python
captcha_gone = not _find_captcha_frame(page)
title_changed = page.title() != "dowjones.com"
if captcha_gone or title_changed:
    # CAPTCHA 已解决
```

## 完整登录流程

```
1. 打开 www.wsj.com           → 可能触发 CAPTCHA → 自动解决
2. 关闭 SP Consent 弹窗
3. 点击 "Sign In"              → 跳转到 SSO
4. SSO 页面可能触发 CAPTCHA    → 自动解决
5. 输入邮箱（逐字输入模拟人类）→ 点击 Continue
6. 输入密码                    → 点击 Sign In
7. "Verify Email" 页面         → 点击 "Continue to WSJ"
8. SSO /continue → 302 → www.wsj.com/client/auth?code=... → 302 → www.wsj.com
9. 等待页面 JS 完全执行（5s+）
10. 提取所有 cookies 保存到 ~/.web_scraper/wsj/cookies.txt
```

## 调试技巧

### 诊断回调 404

```bash
# 直接 curl 测试回调 URL 是否存在
curl -sI "https://accounts.wsj.com/auth/sso/login"
# 如果返回 404，说明回调地址已失效
```

### 监控 Patchright 的网络请求

```python
def on_response(resp):
    if resp.status in [301, 302, 303, 307, 308]:
        loc = resp.headers.get('location', '')
        print(f"REDIRECT {resp.status} -> {loc[:120]}")
page.on("response", on_response)
```

### 检查 AUTH_CONFIG

SSO 登录页通过内联 `<script>` 注入 `AUTH_CONFIG`（Base64 编码 JSON），包含 `callbackURL`、`clientID`、`_csrf` 等：

```python
config = page.evaluate("""() => {
    if (typeof AUTH_CONFIG !== 'undefined') {
        return JSON.parse(atob(AUTH_CONFIG));
    }
    return null;
}""")
print(config.get('callbackURL'))  # 查看实际的回调 URL
```
