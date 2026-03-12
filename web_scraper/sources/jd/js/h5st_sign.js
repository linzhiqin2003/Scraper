/**
 * JD h5st signing service via Node.js + jsdom environment.
 *
 * Usage:
 *   One-shot:  echo '{"params":{...}}' | node h5st_sign.js --cookies '...'
 *   Serve:     node h5st_sign.js --cookies '...' --serve   (reads JSON lines)
 *
 * Strategy:
 *   Use jsdom to provide a full browser-like DOM environment,
 *   then load JD's js_security_v3 SDK (loader + main) which defines
 *   ParamsSign/ParamsSignMain. A warm-up sign triggers the async XHR to
 *   cactus.jd.com/request_algo which provisions the server token (tk03).
 *   Subsequent sign() calls use the cached tk03 token.
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { JSDOM } = require('jsdom');

const SDK_DIR = __dirname;

// ---------------------------------------------------------------------------
// Parse args
// ---------------------------------------------------------------------------
const args = process.argv.slice(2);
let cookiesStr = '';
let serveMode = false;

for (let i = 0; i < args.length; i++) {
  if (args[i] === '--cookies' && i + 1 < args.length) {
    cookiesStr = args[++i];
  } else if (args[i] === '--serve') {
    serveMode = true;
  }
}

// ---------------------------------------------------------------------------
// Create jsdom environment
// ---------------------------------------------------------------------------
async function createEnvironment() {
  const html = `<!DOCTYPE html><html><head></head><body></body></html>`;

  // Track XHR completion for init
  let algoResponseReceived = false;

  const dom = new JSDOM(html, {
    url: 'https://item.jd.com/100041256706.html',
    referrer: 'https://item.jd.com/',
    contentType: 'text/html',
    pretendToBeVisual: true,
    runScripts: 'dangerously',
    beforeParse(window) {
      // Set cookies
      Object.defineProperty(window.document, 'cookie', {
        get: () => cookiesStr,
        set: () => {},
        configurable: true,
      });

      // document.domain
      Object.defineProperty(window.document, 'domain', {
        get: () => 'item.jd.com',
        set: () => {},
        configurable: true,
      });

      // Navigator patches
      Object.defineProperty(window.navigator, 'userAgent', {
        get: () => 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'platform', {
        get: () => 'MacIntel',
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'language', {
        get: () => 'zh-CN',
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'languages', {
        get: () => ['zh-CN', 'zh', 'en'],
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'hardwareConcurrency', {
        get: () => 8,
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'webdriver', {
        get: () => false,
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'plugins', {
        get: () => ({ length: 3, 0: { name: 'Chrome PDF Plugin' }, 1: { name: 'Chrome PDF Viewer' }, 2: { name: 'Native Client' } }),
        configurable: true,
      });
      Object.defineProperty(window.navigator, 'mimeTypes', {
        get: () => ({ length: 2, 0: { type: 'application/pdf' }, 1: { type: 'application/x-nacl' } }),
        configurable: true,
      });

      // Screen
      window.screen = {
        width: 1440, height: 900,
        availWidth: 1440, availHeight: 900,
        colorDepth: 24, pixelDepth: 24,
      };
      window.outerWidth = 1440;
      window.outerHeight = 900;
      window.innerWidth = 1440;
      window.innerHeight = 900;
      window.devicePixelRatio = 2;

      // Chrome object
      window.chrome = { runtime: {} };

      // Canvas mock (jsdom doesn't implement canvas)
      const origCreateElement = window.document.createElement.bind(window.document);
      window.document.createElement = function(tag) {
        const el = origCreateElement(tag);
        if (tag === 'canvas') {
          el.getContext = function(type) {
            if (type === '2d') {
              return {
                fillStyle: '#000',
                font: '10px sans-serif',
                textBaseline: 'alphabetic',
                fillRect: () => {},
                fillText: () => {},
                beginPath: () => {},
                arc: () => {},
                fill: () => {},
                stroke: () => {},
                closePath: () => {},
                measureText: (t) => ({ width: t.length * 6 }),
                isPointInPath: () => false,
                getImageData: () => ({ data: new Uint8Array(4) }),
                putImageData: () => {},
                createLinearGradient: () => ({ addColorStop: () => {} }),
                drawImage: () => {},
              };
            }
            return null;
          };
          el.toDataURL = () => 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB';
        }
        return el;
      };

      // Performance
      const startTime = Date.now();
      window.performance.now = () => Date.now() - startTime;

      // crypto.getRandomValues (jsdom may not have it)
      if (!window.crypto) window.crypto = {};
      window.crypto.getRandomValues = (arr) => {
        const bytes = crypto.randomBytes(arr.length);
        arr.set(bytes);
        return arr;
      };
      if (!window.crypto.subtle) {
        window.crypto.subtle = {
          digest: async (algorithm, data) => {
            const algName = (typeof algorithm === 'string' ? algorithm : algorithm.name)
              .replace('-', '').toLowerCase();
            const hash = crypto.createHash(algName === 'sha256' ? 'sha256' : algName);
            hash.update(Buffer.from(data));
            return hash.digest().buffer;
          },
        };
      }
      window.msCrypto = window.crypto;

      // localStorage mock (SDK caches token/algo here)
      const store = {};
      window.localStorage = {
        getItem: (key) => store[key] || null,
        setItem: (key, val) => { store[key] = String(val); },
        removeItem: (key) => { delete store[key]; },
        clear: () => { Object.keys(store).forEach(k => delete store[k]); },
        get length() { return Object.keys(store).length; },
        key: (i) => Object.keys(store)[i] || null,
      };

      // Real XMLHttpRequest for SDK's algo/token API calls
      const { XMLHttpRequest: NodeXHR } = require('xmlhttprequest-ssl');
      window.XMLHttpRequest = function() {
        const xhr = new NodeXHR({ disableHeaderCheck: true });
        const origOpen = xhr.open.bind(xhr);
        xhr.open = function(method, url, async_, user, pass) {
          if (url && url.startsWith('//')) url = 'https:' + url;
          process.stderr.write('[h5st-xhr] ' + method + ' ' + url + '\n');
          origOpen(method, url, async_ !== false, user, pass);
        };
        const origSend = xhr.send.bind(xhr);
        xhr.send = function(body) {
          try { xhr.setRequestHeader('Cookie', cookiesStr); } catch(e) {}
          try { xhr.setRequestHeader('User-Agent', window.navigator.userAgent); } catch(e) {}
          try { xhr.setRequestHeader('Referer', 'https://item.jd.com/'); } catch(e) {}
          try { xhr.setRequestHeader('Origin', 'https://item.jd.com'); } catch(e) {}
          const origOnReady = xhr.onreadystatechange;
          xhr.onreadystatechange = function() {
            if (xhr.readyState === 4) {
              const resp = xhr.responseText || '';
              if (resp.includes('request_algo') || resp.includes('"tk"')) {
                algoResponseReceived = true;
                process.stderr.write('[h5st-xhr] Algo/token response received\n');
              }
            }
            if (origOnReady) origOnReady.call(xhr);
          };
          origSend(body);
        };
        return xhr;
      };

      // Expose algoResponseReceived checker
      window.__h5stAlgoReceived = () => algoResponseReceived;

      // Suppress console noise from SDK
      console.log = () => {};
    },
  });

  const window = dom.window;

  // Load the main SDK first (since the loader will try to load it via <script>
  // which won't work with jsdom's resource loading from CDN)
  const mainCode = fs.readFileSync(path.join(SDK_DIR, 'js_security_v3_main_0.1.8.js'), 'utf8');
  window.eval(mainCode);

  // Then load the loader (which wraps ParamsSignMain into ParamsSign)
  const loaderCode = fs.readFileSync(path.join(SDK_DIR, 'js_security_v3_0.1.8.js'), 'utf8');
  window.eval(loaderCode);

  return window;
}

// ---------------------------------------------------------------------------
// Initialize SDK: warm-up sign triggers async XHR, then wait for response
// ---------------------------------------------------------------------------
async function initSDK(window, appId) {
  const ParamsSign = window.ParamsSign;
  if (!ParamsSign) {
    throw new Error('ParamsSign not loaded');
  }

  const signAppId = appId || 'fb5df';

  // Warm-up sign triggers the XHR to cactus.jd.com/request_algo
  process.stderr.write('[h5st] Performing warm-up sign to fetch token...\n');
  const warmup = new ParamsSign({ appId: signAppId });
  try {
    await warmup.sign({
      functionId: '_warmup',
      appid: signAppId,
      body: '{}',
      t: String(Date.now()),
    });
  } catch (e) {
    // Warm-up sign may fail — that's OK, we just need the XHR to fire
  }

  // Wait for the algo/token XHR to complete (up to 10 seconds)
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500));
    if (window.__h5stAlgoReceived()) {
      process.stderr.write('[h5st] Token received from server\n');
      // Give SDK a moment to process the response
      await new Promise(r => setTimeout(r, 500));
      return;
    }
  }

  process.stderr.write('[h5st] Warning: algo/token XHR did not complete within 10s\n');
}

// ---------------------------------------------------------------------------
// Sign
// ---------------------------------------------------------------------------
async function signParams(window, params, appId) {
  const ParamsSign = window.ParamsSign;
  if (!ParamsSign) {
    throw new Error('ParamsSign not loaded');
  }

  if (!params.t) {
    params.t = String(Date.now());
  }

  const signAppId = appId || 'fb5df';
  const ps = new ParamsSign({ appId: signAppId });
  const result = await ps.sign(params);

  if (!result) {
    throw new Error('sign() returned null');
  }
  if (result.h5st === 'null' || !result.h5st) {
    if (!window.ParamsSignMain) {
      throw new Error('ParamsSignMain not loaded (main SDK failed to initialize)');
    }
    throw new Error('h5st is null — signing failed silently');
  }

  // Validate token type
  const parts = (result.h5st || '').split(';');
  if (parts.length >= 4) {
    const token = parts[3];
    if (token.startsWith('tk06')) {
      process.stderr.write('[h5st] Warning: using fallback token (tk06). Server token may not have been cached.\n');
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
async function main() {
  let window;
  try {
    window = await createEnvironment();
  } catch (e) {
    process.stderr.write('[h5st] Environment creation failed: ' + e.message + '\n');
    process.exit(1);
  }

  const hasPS = typeof window.ParamsSign === 'function';
  const hasPSM = typeof window.ParamsSignMain === 'function';
  process.stderr.write(`[h5st] SDK loaded: ParamsSign=${hasPS}, ParamsSignMain=${hasPSM}\n`);

  if (!hasPS) {
    process.stderr.write('[h5st] FATAL: ParamsSign not found\n');
    process.exit(1);
  }

  // Initialize: warm-up sign + wait for server token
  await initSDK(window);

  if (serveMode) {
    // Long-running: read JSON lines from stdin
    process.stderr.write('[h5st] Serve mode ready. Send JSON lines to stdin.\n');
    const readline = require('readline');
    const rl = readline.createInterface({ input: process.stdin });

    rl.on('line', async (line) => {
      try {
        const req = JSON.parse(line.trim());
        if (req.action === 'sign') {
          const result = await signParams(window, req.params, req.appId);
          process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
        } else if (req.action === 'ping') {
          process.stdout.write(JSON.stringify({ ok: true, pong: true }) + '\n');
        } else {
          process.stdout.write(JSON.stringify({ ok: false, error: 'unknown action' }) + '\n');
        }
      } catch (e) {
        process.stdout.write(JSON.stringify({ ok: false, error: e.message }) + '\n');
      }
    });

    rl.on('close', () => process.exit(0));
  } else {
    // One-shot
    let input = '';
    process.stdin.setEncoding('utf8');
    for await (const chunk of process.stdin) {
      input += chunk;
    }

    try {
      const req = JSON.parse(input.trim());
      const result = await signParams(window, req.params, req.appId);
      process.stdout.write(JSON.stringify({ ok: true, result }) + '\n');
    } catch (e) {
      process.stdout.write(JSON.stringify({ ok: false, error: e.message }) + '\n');
      process.exit(1);
    }
  }
}

main().catch(e => {
  process.stderr.write('[h5st] Fatal: ' + e.message + '\n');
  process.exit(1);
});
