"""JD h5st signature oracle using Node.js + jsdom.

Replaces Playwright-based SignatureOracle with a pure Node.js subprocess
that runs JD's signing SDK in a jsdom environment. No browser needed.

The Node.js process runs in "serve" mode: it reads JSON lines from stdin
and writes JSON line responses to stdout. This keeps the SDK initialized
(with cached server token) across multiple sign() calls.
"""
import json
import logging
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict

from .cookies import get_cookies_path, load_cookies_raw

logger = logging.getLogger(__name__)

_JS_DIR = Path(__file__).parent / "js"
_H5ST_SCRIPT = _JS_DIR / "h5st_sign.js"

# Timeout for Node.js process initialization (seconds)
_INIT_TIMEOUT = 20
# Timeout for individual sign requests (seconds)
_SIGN_TIMEOUT = 10


class NodeSignatureOracle:
    """Generate h5st signatures via Node.js subprocess.

    Usage:
        oracle = NodeSignatureOracle(cookies_path)
        oracle.start()

        signed_params = oracle.sign({
            'functionId': 'getCommentListPage',
            'appid': 'pc-rate-qa',
            ...
        })

        oracle.stop()
    """

    def __init__(self, cookies_path: Path | None = None):
        if cookies_path is None:
            cookies_path = get_cookies_path()
        if not cookies_path.exists():
            raise FileNotFoundError(
                f"Cookies file not found: {cookies_path}\n"
                f"Run 'scraper jd import-cookies <path>' first."
            )
        self.cookies_path = cookies_path
        self._process: subprocess.Popen | None = None
        self._ready = False
        self._uuid: str | None = None
        self._stdout_queue: queue.Queue = queue.Queue()

    @property
    def uuid(self) -> str | None:
        return self._uuid

    def start(self) -> None:
        """Start the Node.js signing subprocess."""
        if self._process and self._process.poll() is None:
            return

        cookie_str = load_cookies_raw(self.cookies_path)

        # Extract UUID from __jda cookie
        for part in cookie_str.split("; "):
            if part.startswith("__jda="):
                jda_parts = part.split("=", 1)[1].split(".")
                if len(jda_parts) > 1:
                    self._uuid = jda_parts[1]
                break

        self._check_node_deps()

        logger.info("Starting Node.js h5st signing service...")
        self._process = subprocess.Popen(
            ["node", str(_H5ST_SCRIPT), "--cookies", cookie_str, "--serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_JS_DIR),
        )

        stderr_lines: queue.Queue = queue.Queue()
        self._stdout_queue = queue.Queue()

        def read_stderr():
            assert self._process and self._process.stderr
            for line in iter(self._process.stderr.readline, ''):
                line = line.rstrip()
                if line:
                    logger.debug(f"[h5st-node] {line}")
                    stderr_lines.put(line)

        def read_stdout():
            assert self._process and self._process.stdout
            for line in iter(self._process.stdout.readline, ''):
                line = line.rstrip()
                if line:
                    self._stdout_queue.put(line)

        threading.Thread(target=read_stderr, daemon=True).start()
        threading.Thread(target=read_stdout, daemon=True).start()

        # Wait for SDK initialization
        deadline = time.time() + _INIT_TIMEOUT
        while time.time() < deadline:
            if self._process.poll() is not None:
                remaining = []
                while not stderr_lines.empty():
                    remaining.append(stderr_lines.get_nowait())
                raise RuntimeError(
                    "Node.js h5st process died during init.\n"
                    + "\n".join(remaining)
                )
            try:
                line = stderr_lines.get(timeout=0.5)
                if "Serve mode ready" in line:
                    self._ready = True
                    logger.info("Node.js h5st signing service ready")
                    break
            except queue.Empty:
                continue

        if not self._ready:
            self.stop()
            raise RuntimeError("Node.js h5st service failed to initialize within timeout")

        # Verify with a ping
        try:
            resp = self._send_request({"action": "ping"})
            if not resp.get("ok"):
                raise RuntimeError("Ping returned not ok")
            logger.info(f"Node.js h5st oracle ready. UUID: {self._uuid}")
        except Exception as e:
            self.stop()
            raise RuntimeError(f"Ping failed: {e}")

    def stop(self) -> None:
        """Stop the Node.js subprocess."""
        self._ready = False
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    def sign(self, params: Dict[str, str], app_id: str | None = None) -> Dict[str, Any]:
        """Generate h5st signature for the given request parameters."""
        if not self._ready or not self._process:
            raise RuntimeError("NodeSignatureOracle not started. Call start() first.")

        if "t" not in params:
            params["t"] = str(int(time.time() * 1000))

        request: dict = {"action": "sign", "params": params}
        if app_id:
            request["appId"] = app_id

        response = self._send_request(request)

        if not response.get("ok"):
            raise RuntimeError(f"h5st signing failed: {response.get('error', 'unknown')}")

        result = response.get("result", {})
        if not result.get("h5st"):
            raise RuntimeError("h5st signing returned empty result")

        return result

    def _send_request(self, request: dict) -> dict:
        """Send a JSON line request and read the JSON line response."""
        if not self._process or self._process.poll() is not None:
            raise RuntimeError("Node.js process is not running")

        line = json.dumps(request) + "\n"
        try:
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"Failed to write to Node.js process: {e}")

        deadline = time.time() + _SIGN_TIMEOUT
        while time.time() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError("Node.js process died during request")
            try:
                resp_line = self._stdout_queue.get(timeout=0.5)
                return json.loads(resp_line)
            except queue.Empty:
                continue
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid JSON from Node.js: {e}")

        raise RuntimeError("Timeout waiting for h5st sign response")

    def _check_node_deps(self):
        """Check that Node.js and required npm packages are available."""
        try:
            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("node --version failed")
        except FileNotFoundError:
            raise RuntimeError(
                "Node.js is not installed. Install it with: brew install node"
            )

        node_modules = _JS_DIR / "node_modules"
        if not node_modules.exists():
            logger.info("Installing Node.js dependencies...")
            result = subprocess.run(
                ["npm", "install"], cwd=str(_JS_DIR),
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                raise RuntimeError(f"npm install failed:\n{result.stderr}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
