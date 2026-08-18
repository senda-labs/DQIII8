#!/usr/bin/env python3
"""Second off-VPS backup channel for the audit corpus: upload new audit files to Telegram.

WHY
    `docs/audits/` is gitignored and therefore has no durability from git (see
    `.gitignore`, F-26). `bin/tools/backup_audit_docs.sh` is the primary
    off-VPS copy (Netcup <-> Hostinger rsync). This is the *second* channel, so a
    simultaneous loss of both VPS still leaves the findings ledger recoverable
    from the operator's own Telegram history.

WHAT IT DOES
    Walks `docs/audits/`, compares against a local manifest of already-uploaded
    files, and sends each new/changed file to a single allowlisted chat as a
    Telegram document. Nothing else.

SECURITY POSTURE (deliberately narrow)
    * Token and chat id come from the environment ONLY:
      `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BACKUP_CHAT_ID`. Never hardcoded, never
      logged, never written to the manifest.
    * Hard allowlist: the one and only permitted destination is the exact value
      of `TELEGRAM_BACKUP_CHAT_ID`. Every outbound send re-checks it.
    * Fail closed: if either env var is missing the script exits non-zero with a
      loud message. It never exits 0 having sent nothing, because a silent no-op
      in a cron log is indistinguishable from a working backup.
    * Passive monitoring only. If `--check-updates` sees traffic addressed to the
      bot from an unexpected chat, it LOGS it. There is deliberately NO
      counter-measure, no block, no retaliation, no "auto-response" of any kind.
      Hacking back is out of scope by explicit design decision; incident response
      is a human action.
    * Rotating a compromised bot token is a human action too (BotFather + update
      the env var). This script only ever reads whatever token it is given.

USAGE
    TELEGRAM_BOT_TOKEN=... TELEGRAM_BACKUP_CHAT_ID=... \
        python3 bin/tools/telegram_audit_backup.py [--dry-run] [--check-updates]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
WATCH_DIRS = [ROOT / "docs" / "audits"]
MANIFEST = ROOT / "var" / "telegram_audit_backup_manifest.json"

# Telegram rejects documents above 50 MB via the Bot API.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
API_BASE = "https://api.telegram.org"

log = logging.getLogger("telegram_audit_backup")


class ConfigError(RuntimeError):
    """Missing or invalid configuration. Always fatal — never degrade to a no-op."""


# ── configuration ────────────────────────────────────────────────────────────


def load_config() -> tuple[str, str]:
    """Return (token, allowed_chat_id) or raise. Fails closed on purpose."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_BACKUP_CHAT_ID", "").strip()

    missing = [
        name
        for name, value in (
            ("TELEGRAM_BOT_TOKEN", token),
            ("TELEGRAM_BACKUP_CHAT_ID", chat_id),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            f"{', '.join(missing)} not set — refusing to run. "
            "No audit file was backed up to Telegram. "
            "(Fail-closed by design: a silent success here would hide a dead backup channel.)"
        )
    return token, chat_id


# ── manifest ─────────────────────────────────────────────────────────────────


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if not MANIFEST.exists():
        return {"uploaded": {}}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # A corrupt manifest must not silently re-upload the whole corpus or,
        # worse, skip everything. Refuse and let a human look.
        raise ConfigError(f"manifest unreadable ({MANIFEST}): {exc}") from exc
    data.setdefault("uploaded", {})
    return data


def save_manifest(manifest: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_suffix(f".{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(MANIFEST)


def find_new_files(manifest: dict) -> list[Path]:
    """Files present on disk whose (relative path, sha256) is not in the manifest."""
    uploaded = manifest["uploaded"]
    pending: list[Path] = []
    for base in WATCH_DIRS:
        if not base.is_dir():
            log.warning("watch dir missing, skipping: %s", base)
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            key = str(path.relative_to(ROOT))
            record = uploaded.get(key)
            if record and record.get("sha256") == file_digest(path):
                continue
            pending.append(path)
    return pending


# ── telegram ─────────────────────────────────────────────────────────────────


def _multipart(fields: dict[str, str], filename: str, payload: bytes) -> tuple[bytes, str]:
    boundary = f"----dqiii8{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        )
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="document"; '
        f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
    )
    parts.append(payload)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _api_url(token: str, method: str) -> str:
    return f"{API_BASE}/bot{token}/{method}"


def _redact(text: str, token: str) -> str:
    """Never let the bot token reach a log line."""
    return text.replace(token, "<TELEGRAM_BOT_TOKEN>") if token else text


def send_document(token: str, allowed_chat_id: str, chat_id: str, path: Path, caption: str) -> bool:
    # Allowlist re-check at the point of egress, not just at config time. Any
    # future caller that tries to pass a different destination is refused here.
    if chat_id != allowed_chat_id:
        log.error(
            "REFUSED: destination chat id does not match TELEGRAM_BACKUP_CHAT_ID allowlist"
        )
        return False

    size = path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        log.error("skip %s: %d bytes exceeds Telegram's %d byte limit", path, size, MAX_UPLOAD_BYTES)
        return False

    body, content_type = _multipart(
        {"chat_id": chat_id, "caption": caption[:1024], "disable_notification": "true"},
        path.name,
        path.read_bytes(),
    )
    req = urllib.request.Request(
        _api_url(token, "sendDocument"),
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _redact(exc.read().decode("utf-8", "replace")[:300], token)
        log.error("sendDocument HTTP %s for %s: %s", exc.code, path.name, detail)
        return False
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        log.error("sendDocument failed for %s: %s", path.name, _redact(str(exc), token))
        return False

    if not payload.get("ok"):
        log.error("sendDocument rejected %s: %s", path.name, payload.get("description"))
        return False
    return True


def check_updates(token: str, allowed_chat_id: str) -> None:
    """Passive anomaly logging. Observes, records, and does nothing else.

    Any incoming message from a chat other than the allowlisted one is a signal
    that the bot token may be known to someone else (cf. the 2026-08-06 breach).
    We log it so a human can decide to rotate the token. No blocking, no reply,
    no counter-measure — retaliation is explicitly out of scope.
    """
    url = _api_url(token, "getUpdates") + "?" + urllib.parse.urlencode({"timeout": 0, "limit": 50})
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError) as exc:
        log.warning("getUpdates failed (non-fatal): %s", _redact(str(exc), token))
        return

    if not payload.get("ok"):
        log.warning("getUpdates rejected: %s", payload.get("description"))
        return

    unexpected = 0
    for update in payload.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        seen_id = str(chat.get("id", ""))
        if seen_id and seen_id != allowed_chat_id:
            unexpected += 1
            log.warning(
                "ANOMALY: incoming update from non-allowlisted chat id=%s type=%s. "
                "Logged only — no action taken. If unexplained, rotate the bot token "
                "manually via BotFather.",
                seen_id,
                chat.get("type"),
            )
    total = len(payload.get("result", []))
    if total:
        log.info("getUpdates: %d update(s), %d from unexpected chats", total, unexpected)


# ── main ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list what would be uploaded, send nothing")
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="also poll getUpdates and log (only log) unexpected incoming chats",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        manifest = load_manifest()
        # Config is validated even for --dry-run: a dry run that "passes" with no
        # credentials configured would be a misleading green light.
        token, allowed_chat_id = load_config()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    pending = find_new_files(manifest)
    if not pending:
        log.info("nothing new to back up (%d file(s) already in manifest)", len(manifest["uploaded"]))
        if args.check_updates and not args.dry_run:
            check_updates(token, allowed_chat_id)
        return 0

    log.info("%d new/changed file(s) to upload", len(pending))
    if args.dry_run:
        for path in pending:
            log.info("DRY RUN would upload: %s", path.relative_to(ROOT))
        return 0

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    failures = 0
    for path in pending:
        rel = str(path.relative_to(ROOT))
        caption = f"DQIII8 audit backup\n{rel}\n{now}"
        if send_document(token, allowed_chat_id, allowed_chat_id, path, caption):
            manifest["uploaded"][rel] = {"sha256": file_digest(path), "uploaded_at": now}
            log.info("uploaded %s", rel)
            # Persist after each success: an interrupted run must not re-send
            # everything it already delivered.
            save_manifest(manifest)
        else:
            failures += 1

    if args.check_updates:
        check_updates(token, allowed_chat_id)

    if failures:
        log.error("%d file(s) failed to upload", failures)
        return 1
    log.info("backup complete — %d file(s) uploaded", len(pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())
