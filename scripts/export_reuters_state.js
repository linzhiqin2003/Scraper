/**
 * Reuters Browser State Export Script
 *
 * 使用方法：
 * 1. 在 Chrome 中打开 https://www.reuters.com 并确保已登录
 * 2. 按 F12 或 Cmd+Option+I 打开开发者工具
 * 3. 切换到 Console 标签
 * 4. 复制下面的代码并粘贴到控制台，按回车执行
 * 5. 浏览器会自动下载 reuters_state.json 文件
 * 6. 运行: scraper reuters import-state ~/Downloads/reuters_state.json
 */

(function(){
  const state = {
    cookies: [],
    origins: [{
      origin: "https://www.reuters.com",
      localStorage: []
    }]
  };

  // Get all cookies
  document.cookie.split(';').forEach(c => {
    const [name, ...rest] = c.trim().split('=');
    if (name) {
      state.cookies.push({
        name: name,
        value: rest.join('='),
        domain: ".reuters.com",
        path: "/"
      });
    }
  });

  // Get localStorage
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    state.origins[0].localStorage.push({
      name: key,
      value: localStorage.getItem(key)
    });
  }

  // Download as file
  const blob = new Blob([JSON.stringify(state, null, 2)], {type: 'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'reuters_state.json';
  a.click();

  console.log('Exported:', state.cookies.length, 'cookies,', state.origins[0].localStorage.length, 'localStorage items');
})();
