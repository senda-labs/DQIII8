#!/usr/bin/env python3
"""On-demand, single-shot CDP investigation of a URL over a tunneled Chrome
debugger port (default 9333 — the user's authenticated Windows Chrome via
SSH tunnel). One dedicated tab, one CDPSession, closed guaranteed.

Closed extraction enum by design (text|html|screenshot|all) — no raw JS
passthrough, no free-form network filter. Any write capability (click, type,
submit, eval-with-effects) is explicitly out of scope for this tool; see
the "Próximos pasos" / red line section of the approved plan.

Usage:
  python3 bin/tools/cdp_investigate.py --url https://example.com --extract all
  python3 bin/tools/cdp_investigate.py --url https://x.test --extract screenshot --full-page

Outcomes printed as a single JSON line to stdout:
  {"ok": false, "error": "tunnel_down", ...}   # port not reachable, normal outcome
  {"ok": false, "error": "cdp_busy", ...}      # another investigation in flight, normal outcome
  {"ok": true, "text_path": ..., "html_path": ..., "screenshot_path": ..., "inline": {...}}
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bin.core import cdp_client
from bin.core.paths import CDP_INVESTIGATE_OUT_DIR, LOGS_DIR

EXTRACT_MODES = ("text", "html", "screenshot", "all")
INLINE_TRUNCATE = 4000
MAX_TEXT_BYTES = 2 * 1024 * 1024
AUDIT_LOG = LOGS_DIR / "cdp_investigate.log"


def _is_blocked_host(url: str) -> bool:
    """Reject loopback/private/link-local targets: the dedicated tab lives
    inside the same Chrome that exposes the DevTools HTTP control plane
    (e.g. GET /json/close/<id>), so an unrestricted --url is an SSRF
    pivot that can manipulate the browser's own tabs or reach the
    Windows-side intranet. DNS resolves on the VPS, not the Windows PC,
    so this only closes the direct localhost/private-IP vectors."""
    host = urlparse(url).hostname or ""
    if host.lower() in ("localhost",):
        return True
    # Bracketed IPv6 literals (urlparse strips the brackets) and plain IP
    # literals: classify directly without DNS.
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_private or ip.is_link_local
    except ValueError:
        pass
    # Hostname: resolve BOTH address families (gethostbyname is IPv4-only and
    # missed IPv6 loopback/ULA — Fable 5 audit 2026-07-05). Block if ANY
    # resolved address is loopback/private/link-local.
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        addrs = [ipaddress.ip_address(info[4][0]) for info in infos]
        if not addrs:
            return False
        return any(ip.is_loopback or ip.is_private or ip.is_link_local for ip in addrs)
    except (socket.gaierror, ValueError, OSError):
        return False


def _audit(url: str, extract_mode: str, outcome: str) -> None:
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with open(AUDIT_LOG, "a") as f:
            f.write(json.dumps({
                "ts": time.time(), "url": url, "extract_mode": extract_mode, "outcome": outcome,
            }) + "\n")
    except Exception:
        pass  # audit log must never break the investigation


def _emit(payload: dict) -> None:
    print(json.dumps(payload))


def _truncate_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


class Watchdog:
    """Real wall-clock watchdog: forces process exit if the whole
    navigate+extract+cleanup budget is exceeded. Not a per-call timeout."""

    def __init__(self, max_total_s: float, url: str, extract_mode: str):
        self._timer = threading.Timer(max_total_s, self._fire, args=(url, extract_mode))
        self._timer.daemon = True
        self._tab_id = None
        self._port = None

    def arm_tab(self, tab_id: str, port: int) -> None:
        """Called once the dedicated tab exists, so a fired watchdog can
        best-effort close it before force-exiting — without this the tab
        leaks in the user's real Chrome every time the watchdog fires."""
        self._tab_id, self._port = tab_id, port

    def _fire(self, url: str, extract_mode: str) -> None:
        if self._tab_id:
            try:
                import requests
                requests.get(f"http://localhost:{self._port}/json/close/{self._tab_id}", timeout=2)
            except Exception:
                pass
        _audit(url, extract_mode, "error")
        _emit({"ok": False, "error": "watchdog_timeout"})
        sys.stdout.flush()
        import os
        os._exit(1)

    def start(self) -> None:
        self._timer.start()

    def cancel(self) -> None:
        self._timer.cancel()


def run(args: argparse.Namespace) -> int:
    scheme = urlparse(args.url).scheme
    if scheme not in ("http", "https"):
        _emit({"ok": False, "error": "invalid_url_scheme"})
        return 2

    if _is_blocked_host(args.url):
        _audit(args.url, args.extract, "blocked_host")
        _emit({"ok": False, "error": "blocked_host"})
        return 2

    watchdog = Watchdog(args.max_total_s, args.url, args.extract)
    watchdog.start()

    if not cdp_client.check_liveness(port=args.port):
        watchdog.cancel()
        _audit(args.url, args.extract, "tunnel_down")
        _emit({"ok": False, "error": "tunnel_down"})
        return 1

    lock = cdp_client.acquire_port_lock(port=args.port)
    if lock is None:
        watchdog.cancel()
        _audit(args.url, args.extract, "cdp_busy")
        _emit({"ok": False, "error": "cdp_busy"})
        return 1

    session = None
    tab = None
    out_dir = Path(args.out_dir) / str(int(time.time()))
    try:
        tab = cdp_client.open_tab("about:blank", port=args.port)
        watchdog.arm_tab(tab["id"], args.port)
        session = cdp_client.CDPSession(tab["id"], port=args.port)
        session.navigate(args.url, wait_s=args.settle)

        out_dir.mkdir(parents=True, exist_ok=True)
        result: dict = {"ok": True}
        inline: dict = {}

        if args.extract in ("text", "all"):
            text = _truncate_bytes(session.extract_text(), MAX_TEXT_BYTES)
            text_path = out_dir / "text.txt"
            text_path.write_text(text)
            result["text_path"] = str(text_path)
            inline["text"] = text[:INLINE_TRUNCATE]

        if args.extract in ("html", "all"):
            html = _truncate_bytes(session.extract_html(), MAX_TEXT_BYTES)
            html_path = out_dir / "page.html"
            html_path.write_text(html)
            result["html_path"] = str(html_path)
            inline["html"] = html[:INLINE_TRUNCATE]

        if args.extract in ("screenshot", "all"):
            shot_path = out_dir / "screenshot.png"
            session.screenshot(str(shot_path), full_page=args.full_page)
            result["screenshot_path"] = str(shot_path)

        result["inline"] = inline
        watchdog.cancel()
        _audit(args.url, args.extract, "ok")
        _emit(result)
        return 0
    except Exception as e:
        watchdog.cancel()
        _audit(args.url, args.extract, "error")
        _emit({"ok": False, "error": "exception", "detail": str(e)})
        return 1
    finally:
        if session is not None:
            session.close()
        cdp_client.release_port_lock(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--extract", required=True, choices=EXTRACT_MODES)
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument("--settle", type=float, default=4.0, help="Seconds to wait for page load before extracting")
    parser.add_argument("--out-dir", default=str(CDP_INVESTIGATE_OUT_DIR))
    parser.add_argument("--max-total-s", type=float, default=60.0, dest="max_total_s")
    parser.add_argument("--full-page", action="store_true", dest="full_page")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
