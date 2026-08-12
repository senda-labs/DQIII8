"""
Minimal Chrome DevTools Protocol client for driving an already-authenticated
browser tab over a local SSH-tunneled debugger port (e.g. 9333).

Starting point is a byte-identical copy of
my-projects/football-value/capture/navigator/cdp_client.py (left frozen,
untouched). This duplicates infrastructure against the "no duplicate infra"
principle in my-projects/jarvis-control3/architecture/06-cdp-access.md —
known debt, unifying into one shared module is future work, not this session.

Why this exists: injecting `fetch()` via Runtime.evaluate gets Cloudflare-
challenged on SofaScore even from a logged-in tab (the call doesn't carry the
same-site navigation context Cloudflare's bot management expects). Instead we
navigate the real tab to a target page and sniff the XHR/fetch responses the
page's own scripts make via the Network domain — those are indistinguishable
from normal browsing because they are normal browsing.
"""
from __future__ import annotations

import base64
import fcntl
import json
import time
from pathlib import Path
from typing import Any

import requests
import websocket

from bin.core.paths import CDP_INVESTIGATE_OUT_DIR


def list_tabs(port: int = 9333) -> list[dict]:
    resp = requests.get(f"http://localhost:{port}/json", timeout=5)
    resp.raise_for_status()
    return [t for t in resp.json() if t.get("type") == "page"]


def find_tab(url_substring: str, port: int = 9333) -> dict | None:
    for tab in list_tabs(port):
        if url_substring in tab.get("url", ""):
            return tab
    return None


def check_liveness(port: int = 9333, timeout: float = 3.0) -> bool:
    try:
        resp = requests.get(f"http://localhost:{port}/json/version", timeout=timeout)
        return resp.ok
    except Exception:
        return False


def open_tab(url: str, port: int = 9333) -> dict:
    resp = requests.put(f"http://localhost:{port}/json/new?{url}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def _lock_path(port: int) -> Path:
    CDP_INVESTIGATE_OUT_DIR.mkdir(parents=True, exist_ok=True)
    return CDP_INVESTIGATE_OUT_DIR / f"{port}.lock"


def acquire_port_lock(port: int = 9333):
    """Non-blocking, port-scoped exclusive lock. Returns a file handle to
    hold onto (pass to release_port_lock), or None if already held.

    Port-scoped, not process-scoped: any client — this pilot, football-value's
    CDP scripts, a future jarvis-control3 co-browsing resume flow — that
    respects this lockfile is excluded by construction from colliding on the
    same CDP port.
    """
    fh = open(_lock_path(port), "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def release_port_lock(handle) -> None:
    if handle is None:
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    try:
        handle.close()
    except Exception:
        pass


class CDPSession:
    """One WebSocket connection bound to a single Chrome tab."""

    def __init__(
        self,
        page_id: str,
        port: int = 9333,
        timeout: float = 30.0,
        owns_tab: bool = True,
    ):
        """`owns_tab` must be False when attaching to a tab this process did
        not create itself (e.g. a real, pre-existing user tab found via
        `find_tab`/`list_tabs`) — `close()` then only tears down the debug
        websocket, never the tab. Only pass True (the default, matching the
        existing pilot's own `open_tab()` + `CDPSession(...)` + `close()`
        lifecycle) when this session created the tab it's attaching to."""
        self.page_id = page_id
        self.port = port
        self.owns_tab = owns_tab
        self.ws = websocket.create_connection(
            f"ws://localhost:{port}/devtools/page/{page_id}", timeout=timeout
        )
        self._id = 0
        self._event_buffer: list[dict] = []
        self._send("Runtime.enable", {})

    def _send(self, method: str, params: dict) -> dict:
        self._id += 1
        msg_id = self._id
        self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params}))
        while True:
            raw = self.ws.recv()
            msg = json.loads(raw)
            if msg.get("id") == msg_id:
                return msg
            if "method" in msg:
                self._event_buffer.append(msg)

    def _next_event(self) -> dict | None:
        """Pop a buffered event first (stashed by _send while awaiting a
        command reply), else read straight from the socket."""
        if self._event_buffer:
            return self._event_buffer.pop(0)
        raw = self.ws.recv()
        return json.loads(raw)

    def evaluate(self, expression: str, await_promise: bool = True) -> Any:
        result = self._send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
                "timeout": 25000,
            },
        )
        res = result.get("result", {})
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("text", "JS exception"))
        return res.get("result", {}).get("value")

    def fetch_json(self, url: str) -> Any:
        """fetch() a same-origin URL from inside the page's own session.
        Only works when `url` shares origin with the currently loaded page —
        cross-origin calls (e.g. api.sofascore.com from www.sofascore.com)
        get Cloudflare-challenged even with valid cookies.
        """
        expr = (
            "fetch(" + json.dumps(url) + ", {credentials: 'include'})"
            ".then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))"
        )
        return self.evaluate(expr)

    def navigate(self, url: str, wait_s: float = 10.0) -> None:
        """Best-effort navigate: fires Page.navigate then waits up to wait_s
        for a Page.loadEventFired, but never blocks past that budget."""
        self._send("Page.enable", {})
        self._id += 1
        nav_id = self._id
        self.ws.send(json.dumps({
            "id": nav_id, "method": "Page.navigate", "params": {"url": url}
        }))
        prev_timeout = self.ws.gettimeout()
        self.ws.settimeout(1.0)
        try:
            deadline = time.time() + wait_s
            while time.time() < deadline:
                try:
                    msg = self._next_event()
                except Exception:
                    continue
                if msg and msg.get("method") == "Page.loadEventFired":
                    return
        finally:
            self.ws.settimeout(prev_timeout)

    def extract_text(self) -> str:
        return self.evaluate("document.body.innerText") or ""

    def extract_html(self) -> str:
        return self.evaluate("document.documentElement.outerHTML") or ""

    def screenshot(self, path: str, full_page: bool = False) -> str:
        params: dict[str, Any] = {"format": "png"}
        if full_page:
            metrics = self._send("Page.getLayoutMetrics", {})
            content_size = metrics.get("result", {}).get("cssContentSize", {})
            width = min(int(content_size.get("width", 1920)), 1920)
            height = min(int(content_size.get("height", 1080)), 8000)
            self._send("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
            })
            params["captureBeyondViewport"] = True
        result = self._send("Page.captureScreenshot", params)
        data = result.get("result", {}).get("data", "")
        Path(path).write_bytes(base64.b64decode(data))
        return path

    # -- Network sniffing: capture real page-driven API responses ----------

    def navigate_and_capture(
        self,
        url: str,
        url_filter: str,
        settle_s: float = 6.0,
    ) -> dict[str, Any]:
        """Navigate this tab to `url`, then collect bodies of every
        XHR/fetch response whose URL contains `url_filter`, for `settle_s`
        seconds after load. Returns {response_url: parsed_json_or_text}.
        """
        self._send("Network.enable", {})
        self._send("Page.enable", {})
        self._id += 1
        nav_id = self._id
        self.ws.send(json.dumps({
            "id": nav_id, "method": "Page.navigate", "params": {"url": url}
        }))

        pending_urls: dict[str, str] = {}  # requestId -> response url (post responseReceived)
        bodies: dict[str, Any] = {}
        self.ws.settimeout(1.0)
        deadline = time.time() + settle_s
        while time.time() < deadline:
            try:
                msg = self._next_event()
            except Exception:
                continue
            method = msg.get("method")
            if method == "Network.responseReceived":
                params = msg["params"]
                resp_url = params.get("response", {}).get("url", "")
                if url_filter in resp_url:
                    pending_urls[params["requestId"]] = resp_url
            elif method == "Network.loadingFinished":
                req_id = msg["params"]["requestId"]
                resp_url = pending_urls.pop(req_id, None)
                if resp_url is None:
                    continue
                try:
                    body_msg = self._send("Network.getResponseBody", {"requestId": req_id})
                    if "error" in body_msg:
                        bodies[resp_url] = {"_error": body_msg["error"]}
                        continue
                    body = body_msg.get("result", {}).get("body", "")
                    try:
                        bodies[resp_url] = json.loads(body)
                    except Exception:
                        bodies[resp_url] = body
                except Exception as e:
                    bodies[resp_url] = {"_error": str(e)}
        return bodies

    def close(self) -> None:
        """Closes the underlying target/tab first if (and only if) this
        session owns it (fixes a bug in the original football-value client,
        which only closed the websocket and leaked orphaned tabs in the
        user's real Chrome), then always closes the socket. When `owns_tab`
        is False (attached to a pre-existing, real user tab), only the
        websocket is closed — a near-miss during the Asana write session
        (2026-08-03) found that closing a live authenticated user tab via
        Target.closeTarget is silent and easy to trigger by habit. Both
        branches are best-effort — cleanup must never raise."""
        if self.owns_tab:
            try:
                self._send("Target.closeTarget", {"targetId": self.page_id})
            except Exception:
                try:
                    requests.get(
                        f"http://localhost:{self.port}/json/close/{self.page_id}", timeout=5
                    )
                except Exception:
                    pass
        try:
            self.ws.close()
        except Exception:
            pass


def wait_for_tab(url_substring: str, port: int = 9333, retries: int = 10, delay: float = 1.0) -> dict:
    for _ in range(retries):
        tab = find_tab(url_substring, port)
        if tab:
            return tab
        time.sleep(delay)
    raise RuntimeError(f"No tab found matching {url_substring!r} on port {port}")
