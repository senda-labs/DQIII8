#!/usr/bin/env python3
"""
DQIII8 — PermissionAnalyzer v3
Centralized permission evaluation for pre_tool_use hooks.

v2: SQLite timeout + ALLOWED_DELETIONS + ESCALATE loop
v3: Dual-channel rejections (DB + JSON inbox) + budget check +
    autonomous auto-approve + FIX ESCALATE count (DENY+ESCALATE)
v3.1: BLOCKED_PATHS Bash enforcement, CLAUDE_MD_PLUGIN_EDIT bypass removal,
      in-process fallback counter, defensive pattern check wrapping
v3.4: Web egress gate for WebFetch/WebSearch (exfiltration control)
v3.5: BLOCKED_PATHS enforced for MCP tools via _candidate_paths() +
      GOVERNANCE_PATHS/ESCALATE for the .claude/ rule-hook-agent-skill corpus
"""

import ipaddress
import json
import logging
import os
import re
import sqlite3
import threading as _threading
import urllib.parse
from datetime import datetime
from pathlib import Path

log = logging.getLogger("dqiii8." + __name__)

# ── Configuration ───────────────────────────────────────────────────────────
DQIII8_ROOT = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))
DB_PATH = DQIII8_ROOT / "database" / "dqiii8.db"
SESSION_ID = os.environ.get("CLAUDE_SESSION_ID", "unknown")
DQIII8_MODE = os.environ.get("DQIII8_MODE", "supervised")

# ── Risk constants ──────────────────────────────────────────────────────────
BLOCKED_PATHS = [
    "CLAUDE.md",
    ".env",
    "secrets",
    "dqiii8.db",
    ".claude/settings.json",
    "schema_v2.sql",
    ".git/",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    "context/proposito.md",
    # The file that allow-lists mcp__filesystem__write_file / mcp__dqiii8-db__execute
    # with no matching deny. Editing it is how an agent would grant itself the
    # capability to bypass every other entry in this list. Governance-escalated
    # rather than hard-denied (see GOVERNANCE_PATHS below).
    ".claude/settings.local.json",
]

# ── Governance paths (v3.5) ─────────────────────────────────────────────────
# The rule/hook/agent/skill corpus that *defines* this system's behaviour. A
# write here is not automatically an attack — legitimate maintenance of the
# governance corpus is a real, recurring task — but it is never routine either:
# it rewrites the policy that every other check enforces.
#
# So these produce ESCALATE (human confirms, same wire effect as DENY but
# routed to the operator by record_rejection) instead of DENY. A hard DENY
# would make the governance system unmaintainable by any agent, including the
# remediation work that introduced this constant.
#
# ESCALATE here is deliberately NOT reachable by the autonomous-mode
# auto-approve fast path (step 5) nor by learned_approvals (step 4a): the
# candidate-path check runs at step 3, ahead of both.
GOVERNANCE_PATHS = [
    ".claude/hooks/",
    ".claude/rules/",
    ".claude/rules_db/",
    ".claude/agents/",
    ".claude/skills/",
    ".claude/settings.local.json",
]

# Paths where even READ is dangerous (credential exfiltration risk).
# Literal fast-path tokens only; the authoritative matcher is _credential_hit()
# below, which also covers suffix classes (.pem/.key/.p12/.pfx) and non-dotfile
# env files (prod.env, config/app.env) that a literal substring cannot express.
BASH_CREDENTIAL_PATHS = [
    ".credentials.json",
    ".env",
    "id_rsa",
    "id_ed25519",
    ".ssh/",
    ".gnupg/",
]

# ── Credential-path gate (v3.3) ─────────────────────────────────────────────
# Single source of truth shared by the read family (Read/Grep/Glob, step 3d)
# and by Bash (step 3c), so the three read-family tools and the shell can never
# drift apart: a path blocked for one is blocked for all.
#
# Deliberately NOT BLOCKED_PATHS: that list is a *write* denylist and also
# contains files that must stay readable (CLAUDE.md, dqiii8.db, schema_v2.sql,
# .claude/settings.json, context/proposito.md). This gate covers genuine
# credential material only.
#
# Directory components — any path segment equal to one of these is credential
# territory (covers the ".ssh/" / ".gnupg/" entries of BASH_CREDENTIAL_PATHS).
CREDENTIAL_DIRS = {".ssh", ".secrets", ".gnupg"}

# Template files carry placeholders, never real values (13 committed
# *.env.example files in this repo). Allowlisted so widening the env rule to
# non-dotfile forms does not make routine setup work impossible.
_CREDENTIAL_TEMPLATE_RE = re.compile(r"\.(?:example|sample|template|dist)$", re.IGNORECASE)

# Basenames — matched against the file name, not the whole path, so that
# source files that merely mention secrets (bin/core/human_pending/secrets.py,
# alembic/022_wallet_pass_secrets.py, SECRETPOWER.yaml) stay readable.
_CREDENTIAL_BASENAME_RE = re.compile(
    r"^(?:"
    r".*\.env(?:\..+)?"          # .env, .env.local, prod.env, config/app.env
    r"|\.credentials\.json"      # OAuth credential store
    r"|id_rsa.*|id_ed25519.*"    # private keys (and their .pub siblings)
    r"|\.secrets"                # dotfile secret store
    r"|.*secrets?\.json"         # client_secret.json, youtube_client_secret.json
    r"|.+\.(?:pem|key|p12|pfx)"  # X.509 / PKCS#12 key material
    r")$",
    re.IGNORECASE,
)
# The leading ".*\." on the env branch is mandatory, not optional: a bare
# basename "env" (virtualenv dirs, /usr/bin/env) must stay accessible.
# The ".+\." on the suffix branch likewise requires a non-empty stem.

_GLOB_WILDCARD_RE = re.compile(r"[*?]+")

# ── Candidate-path extraction (v3.5) ────────────────────────────────────────
# Every filesystem path a tool call could touch, whatever the tool. Before
# v3.5 the BLOCKED_PATHS write check ran only for Edit/Write/MultiEdit plus a
# Bash heuristic, so the MCP tools that settings.local.json allow-lists
# (mcp__filesystem__write_file, mcp__dqiii8-db__execute) reached the same files
# with no check at all.

# The @modelcontextprotocol/server-filesystem tools that only READ. Everything
# else under mcp__filesystem__ is treated as write-capable — settings.json
# allows the whole `mcp__*` glob, so an unlisted/new write tool must fail
# closed into the check rather than out of it.
_MCP_FS_READONLY_SUFFIXES = {
    "read_file",
    "read_text_file",
    "read_media_file",
    "read_multiple_files",
    "list_directory",
    "list_directory_with_sizes",
    "directory_tree",
    "search_files",
    "get_file_info",
    "list_allowed_directories",
}

# Argument names carrying a path across the filesystem MCP tools
# (write_file/edit_file/create_directory use `path`; move_file uses
# `source`/`destination`).
_MCP_PATH_KEYS = ("file_path", "path", "source", "destination", "target", "dest")

# SQLite statements that name a filesystem path directly.
_SQL_ATTACH_RE = re.compile(
    r"""\bATTACH\s+(?:DATABASE\s+)?['"]([^'"]+)['"]""", re.IGNORECASE
)
_SQL_VACUUM_INTO_RE = re.compile(
    r"""\bVACUUM\s+INTO\s+['"]([^'"]+)['"]""", re.IGNORECASE
)
# Best-effort catch-all for a path-shaped string literal anywhere in the query
# (readfile()/writefile() extensions, .import targets, or an ATTACH spelled in
# a form the two patterns above miss). Deliberately a heuristic, not a parser:
# a literal counts as path-shaped if it contains a directory separator or ends
# in a file extension this system actually protects.
_SQL_PATHISH_RE = re.compile(
    r"""['"]\s*((?:[^'"\s]*/[^'"]*)|(?:[^'"\s/]+\.(?:db|sqlite|sqlite3|sql|env|json|md|py|sh|key|pem)))\s*['"]""",
    re.IGNORECASE,
)


def _sql_candidate_paths(sql: str) -> list[str]:
    """Filesystem paths a SQL string could write to or read from."""
    if not sql:
        return []
    out: list[str] = []
    for pattern in (_SQL_ATTACH_RE, _SQL_VACUUM_INTO_RE, _SQL_PATHISH_RE):
        out.extend(m.group(1) for m in pattern.finditer(sql))
    seen: set[str] = set()
    return [p for p in out if p and not (p in seen or seen.add(p))]


def _candidate_paths(tool: str, tool_input: dict) -> list[str]:
    """Every filesystem path this tool call could touch.

    Edit/Write/MultiEdit — file_path (the pre-v3.5 behaviour, preserved).
    mcp__filesystem__*   — its path argument(s), unless the tool only reads.
    mcp__*__execute /
    mcp__*db*__query     — paths named by the SQL string (ATTACH DATABASE,
                           VACUUM INTO, path-shaped literals).
    Bash                 — deliberately empty: Bash keeps its own token/write-
                           operator heuristic in _bash_touches_blocked(), which
                           reasons over the whole command line rather than a
                           discrete path argument.
    """
    inp = tool_input or {}
    paths: list[str] = []

    if tool in ("Edit", "Write", "MultiEdit"):
        p = inp.get("file_path", inp.get("path", ""))
        if p:
            paths.append(str(p))
        return paths

    if tool.startswith("mcp__"):
        suffix = tool.rsplit("__", 1)[-1]
        is_fs = tool.startswith("mcp__filesystem__")
        if is_fs and suffix in _MCP_FS_READONLY_SUFFIXES:
            return []
        if is_fs:
            for key in _MCP_PATH_KEYS:
                val = inp.get(key)
                if isinstance(val, str) and val:
                    paths.append(val)
                elif isinstance(val, (list, tuple)):
                    paths.extend(str(v) for v in val if v)
        # Any MCP tool that takes SQL is a filesystem actor via ATTACH/VACUUM,
        # regardless of which server exposes it.
        for key in ("sql", "query", "statement"):
            val = inp.get(key)
            if isinstance(val, str) and val:
                paths.extend(_sql_candidate_paths(val))

    seen: set[str] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _blocked_path_hit(path: str) -> str | None:
    """The BLOCKED_PATHS token a path matches, ignoring governance-only tokens.

    A token that is in both lists (`.claude/settings.local.json`) is resolved by
    GOVERNANCE_PATHS (ESCALATE), so it is excluded here. A governance file that
    *also* matches a genuine deny token (e.g. `.claude/rules/secrets.md` hitting
    "secrets") still denies — DENY wins whenever the two lists disagree.
    """
    if not path:
        return None
    for blocked in BLOCKED_PATHS:
        if blocked in GOVERNANCE_PATHS:
            continue
        if blocked in path:
            return blocked
    return None


def _governance_path_hit(path: str) -> str | None:
    """The GOVERNANCE_PATHS token a path matches, or None."""
    if not path:
        return None
    normalized = path.replace("\\", "/")
    for gov in GOVERNANCE_PATHS:
        if gov in normalized:
            return gov
    return None

# Shell metacharacters used to split a Bash command into path-like tokens.
_BASH_TOKEN_SPLIT_RE = re.compile(r"""[\s'"();|&<>=`,]+""")


def _credential_hit(path: str) -> str | None:
    """Return the credential token a path touches, or None.

    Both the literal path and its realpath are checked: the read-family tools
    follow symlinks, so a link planted in an allowed directory
    (ln -s /root/dqiii8/.env notes.txt) must not launder credential content.
    The literal path is still checked as a fallback for broken/dangling links,
    where realpath() cannot resolve the target.
    """
    if not path:
        return None
    candidates = {os.path.normpath(path)}
    try:
        candidates.add(os.path.realpath(path))
    except OSError as _re:  # pragma: no cover — realpath rarely raises
        log.warning("permission_analyzer: realpath failed for %r: %s", path, _re)

    for cand in sorted(candidates):
        parts = [p for p in cand.split(os.sep) if p]
        if not parts:
            continue
        # Whole path, not just ancestors: a Grep/Glob target may itself be the
        # credential directory (path="/root/.ssh").
        seg_hit = CREDENTIAL_DIRS.intersection(parts)
        if seg_hit:
            return sorted(seg_hit)[0]
        base = parts[-1]
        if _CREDENTIAL_TEMPLATE_RE.search(base):
            continue
        if _CREDENTIAL_BASENAME_RE.match(base):
            return base
    return None


def _glob_filter_hit(spec: str) -> str | None:
    """Return the credential token a Grep --glob filter targets, or None.

    The filter is a name pattern rather than a path, so wildcards are collapsed
    before matching: '**/.env*' -> '.env', '*.pem' -> '.pem'. A non-targeting
    filter collapses to something harmless ('*' -> '', '**/*.py' -> '.py'), so
    ordinary filtered greps are unaffected. Without this, a Grep rooted at an
    allowed directory could still funnel credential content back via the filter.
    """
    if not spec:
        return None
    base = spec.replace("\\", "/").rsplit("/", 1)[-1]
    collapsed = _GLOB_WILDCARD_RE.sub("", base)
    if not collapsed or collapsed == ".":
        return None
    if _CREDENTIAL_TEMPLATE_RE.search(collapsed):
        return None
    # "x" + collapsed supplies the stem that a suffix-only filter ('*.pem')
    # loses when its wildcard is removed.
    for probe in (collapsed, "x" + collapsed):
        if _CREDENTIAL_BASENAME_RE.match(probe):
            return collapsed
    return None


def _url_secret_hit(text: str) -> str | None:
    """Return the name of the secret shape found in `text`, or None.

    Checked against both the raw string and its percent-decoded form: a URL
    carrying '?d=sk-ant-...' and one carrying '?d=sk%2Dant%2D...' are the same
    egress event.
    """
    if not text:
        return None
    forms = {text}
    try:
        forms.add(urllib.parse.unquote(text))
        forms.add(urllib.parse.unquote_plus(text))
    except Exception as _ue:  # pragma: no cover — unquote is total in practice
        log.warning("permission_analyzer: unquote failed for URL text: %s", _ue)
    for form in forms:
        for pattern, name in _URL_SECRET_PATTERNS:
            if pattern.search(form):
                return name
    return None


def _url_units(url: str) -> list[str]:
    """Split a URL into the atomic strings an exfiltrated payload could occupy.

    Host labels, path segments, query keys AND values, and the fragment. The
    query is harvested twice: once via parse_qsl (which decodes '+' to a space,
    the correct reading for a form-encoded value) and once by raw '&'/'=' split
    (which preserves '+' as a base64 character). A payload is opaque under at
    least one of those readings; a real sentence is opaque under neither.
    """
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return [url]
    units: list[str] = []
    host = p.hostname or ""
    units.extend(lbl for lbl in host.split(".") if lbl)
    units.extend(urllib.parse.unquote(seg) for seg in p.path.split("/") if seg)
    try:
        for key, val in urllib.parse.parse_qsl(p.query, keep_blank_values=True):
            units.extend((key, val))
    except Exception as _qe:  # pragma: no cover
        log.warning("permission_analyzer: parse_qsl failed: %s", _qe)
    for chunk in re.split(r"[&;]", p.query):
        for part in chunk.split("=", 1):
            if part:
                units.append(urllib.parse.unquote(part))
    if p.fragment:
        units.append(urllib.parse.unquote(p.fragment))
    return units


def _opaque_blob_hit(url: str) -> str | None:
    """Return an opaque high-volume token carried by the URL, or None.

    Structure, not entropy, is the discriminator. Shannon entropy fails here:
    hex digests score *below* Dutch agricultural URL slugs. What separates a
    payload from a slug is that a slug is punctuated into words and a payload is
    one unbroken token.
    """
    for unit in _url_units(url):
        unit = unit.strip()
        if len(unit) >= _BLOB_RAW_MIN and _BLOB_ALNUM_RE.match(unit):
            return unit[:60]
        # base64 alphabet: '+' and '/' are payload characters, not separators.
        core = unit.replace("+", "").replace("/", "").rstrip("=")
        if (
            len(core) >= _BLOB_B64_MIN
            and _BLOB_ALNUM_RE.match(core)
            and any(c.islower() for c in core)
            and any(c.isupper() for c in core)
            and any(c.isdigit() for c in core)
        ):
            return unit[:60]
    return None


def _host_egress_risk(host: str) -> tuple[str, str] | None:
    """Classify a URL host. Returns (severity_kind, token) or None.

    severity_kind ∈ {"sink", "metadata", "private"}.
    """
    if not host:
        return ("private", "<empty-host>")
    host = host.lower().strip(".")
    for sink in _EXFIL_SINK_HOSTS:
        if host == sink or host.endswith("." + sink):
            return ("sink", sink)
    # Integer / hex / octal-encoded IPv4 (http://2130706433/ == http://127.0.0.1/).
    # Decode and classify like any other IP instead of short-circuiting to
    # "private" — the short-circuit let http://2852039166/ (169.254.169.254,
    # cloud metadata) downgrade from DENY to ESCALATE (found by stress test,
    # 2026-08-11).
    _int_base = 16 if host.startswith("0x") else (8 if re.fullmatch(r"0[0-7]+", host) else (10 if host.isdigit() else None))
    if _int_base is not None:
        try:
            host = str(ipaddress.ip_address(int(host, _int_base)))
        except (ValueError, OverflowError):
            return ("private", host)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or host.endswith(
            (".localhost", ".local", ".internal", ".localdomain")
        ):
            return ("private", host)
        return None
    if ip.is_link_local:
        # 169.254.169.254 and friends: cloud instance metadata. Never a
        # legitimate research target, always an SSRF credential grab.
        return ("metadata", host)
    if ip.is_loopback or ip.is_private or ip.is_reserved or ip.is_unspecified:
        return ("private", host)
    return None


# ── Web egress gate (v3.4) ──────────────────────────────────────────────────
# The credential gates above stop secrets *entering* context. This one is the
# other half: WebFetch is the only tool that sends attacker-chosen bytes *out*
# of the VPS, and it was auto-approved with zero inspection.
#
# Verified tool contract (not assumed):
#   WebFetch(url, prompt) — GET only, http upgraded to https, cross-host
#     redirects returned rather than followed, response cached 15 min. There is
#     no request body and no header control, so the ONLY outbound channel an
#     attacker controls is the URL itself (host + path + query + fragment).
#     `prompt` is evaluated against the *fetched* content by an internal model;
#     it never reaches the remote host, so it is deliberately not gated.
#   WebSearch(query, allowed_domains, blocked_domains) — the query goes to the
#     search backend, never to an attacker-chosen host, so there is no
#     exfiltration channel; only the "secret pasted into a third-party search
#     log" case is gated (see _web_egress_block).
#
# Design decision — NO host allowlist. Derived empirically from 444 real
# WebFetch calls in this VPS's session history: 211 distinct hosts, 125 of them
# fetched exactly once. This system's WebFetch usage *is* open-ended market
# research (intl-reports, nl-onion study, job search). Any allowlist would deny
# the majority of legitimate calls, and an ESCALATE-on-unknown-host policy would
# fire on >50% of them — which trains the operator to rubber-stamp, i.e. makes
# the control worse than useless. So the gate targets exfiltration *shape*
# (where the data is) instead of host reputation (who the host is).
#
# Every threshold below was calibrated against that 444-URL corpus at 0 false
# positives; see tests/test_permission_analyzer.py::TestWebEgressGate.

_WEB_ALLOWED_SCHEMES = {"http", "https"}

# Hosts whose entire product is "receive an arbitrary inbound request and show
# it to whoever set me up". Zero research value, so a hit is unambiguous
# exfiltration rather than an ambiguous lookup → DENY, not ESCALATE.
_EXFIL_SINK_HOSTS = (
    "webhook.site",
    "requestbin.com",
    "requestbin.net",
    "requestcatcher.com",
    "pipedream.net",
    "beeceptor.com",
    "mockbin.org",
    "hookb.in",
    "ngrok.io",
    "ngrok.app",
    "ngrok-free.app",
    "loca.lt",
    "trycloudflare.com",
    "serveo.net",
    "burpcollaborator.net",
    "oast.fun",
    "oast.pro",
    "oast.live",
    "oast.site",
    "oast.online",
    "oast.me",
    "interact.sh",
    "canarytokens.com",
    "dnslog.cn",
)

# Secret shapes that must never appear in an outbound URL or a search query.
# Prefix-anchored on the issuer's own format, so these cannot match prose.
_URL_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "anthropic_api_key"),
    (re.compile(r"\bsk-(?:proj-|or-v1-)?[A-Za-z0-9]{20,}"), "openai_style_api_key"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"), "github_token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "github_pat"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}"), "aws_access_key_id"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "slack_token"),
    (re.compile(r"\bAIza[A-Za-z0-9_\-]{35}"), "google_api_key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{30,}"), "huggingface_token"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"), "gitlab_token"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{40,}"), "groq_api_key"),
    (re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}"), "nvidia_nim_key"),
    # The exact shape of the token leaked to a public repo on 2026-08-06.
    # {30,} not {35}: the canonical secret is 35 chars, but the length is not
    # contractual and an off-by-a-few variant is the same disclosure.
    (re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}"), "telegram_bot_token"),
    (re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY"), "private_key_block"),
]

# Opaque-blob heuristic. Longest contiguous alphanumeric run in the 444-URL
# legitimate corpus is 32 chars (an IMF dataset UUID); the next is 24. 48 for a
# raw run and 40 for a base64 run with its '+'/'/' padding characters stripped
# both clear that ceiling with margin, and catch 0 of 444 real URLs while
# catching ~83% of randomly generated base64/hex payloads.
_BLOB_RAW_MIN = 48
_BLOB_B64_MIN = 40
_BLOB_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")

# Bash operators that indicate a WRITE to a file
_BASH_WRITE_SIGNS = [">", ">>", "tee ", "sed -i", "truncate "]

# Always CRITICAL regardless of mode
CRITICAL_PATTERNS = [
    r"rm\s+-rf\s+/\s*$",  # rm -rf / (exact root filesystem wipe)
    r"rm\s+-rf\s+/\s+",  # rm -rf / followed by space (flags or paths after /)
    r">\s+/dev/sda",  # write directly to disk device
    r"\bmkfs\b",  # format a filesystem
    r"\bdd\b.*\bif=",  # disk dump (potential disk wipe)
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

HIGH_RISK_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf /anything (non-root paths)
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\$HOME",
    r"DROP\s+TABLE",
    r"DELETE\s+FROM\s+agent_actions\b(?!\s+WHERE)",  # mass-delete without WHERE
    r"DROP\s+DATABASE",
    r"chmod\s+777\s+/",
]

ALLOWED_DELETIONS = [
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "tmp",
    "/tmp/",
    ".mypy_cache",
    "*.pyc",
    ".ruff_cache",
    "plugins/cache/",
]

# Project directories always safe for writing
SAFE_PROJECT_DIRS = [
    str(DQIII8_ROOT) + "/",
    "/root/math-image-generator",
    "/tmp/",
]

# Tools auto-approved in autonomous mode (after passing checks)
AUTO_APPROVE_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "Write",
    "Edit",
    "MultiEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
}

MAX_SESSION_COST_USD = 5.0
MAX_SAME_REJECTION = 2  # After 2 identical rejections → ESCALATE

# Informational hints per denial type (help Claude self-correct)
DENIAL_HINTS: dict[str, str] = {
    "blocked_path:.env": (
        "Use os.environ['KEY'] to read temporary variables. "
        "Or use export KEY=value in bash without touching the file."
    ),
    "blocked_path:schema_v2.sql": (
        "Add the SQL migration in a new file: "
        "database/migrations/YYYYMMDD_description.sql"
    ),
    "blocked_path:CLAUDE.md": (
        "System instructions cannot be modified from code. "
        "Use the revise-claude-md skill to generate a diff, "
        "then apply it manually from the terminal."
    ),
    "blocked_path:dqiii8.db": (
        "Use INSERT/UPDATE via sqlite3 with the existing wrapper. "
        "Do not modify the DB file directly."
    ),
    "blocked_path:context/proposito.md": (
        "The system purpose can only be modified by the user directly. "
        "No agent can edit this file."
    ),
    "high_risk_pattern": (
        "Use specific relative paths instead of wildcards. "
        "Or add the pattern to ALLOWED_DELETIONS if it is cache cleanup."
    ),
    "budget_exceeded": (
        "Split the objective into smaller subtasks. "
        "Start a new session with j --autonomous"
    ),
    "repeat_rejection": (
        "This action was rejected multiple times. "
        "Change strategy: use a different tool or "
        "ask the user before retrying."
    ),
}


# In-process fallback counter for DENY/ESCALATE when DB is unavailable
_proc_rejection_counts: dict[str, int] = {}
_proc_rejection_lock = _threading.Lock()


class PermissionAnalyzer:
    """Centralized permission evaluator for Claude Code tools."""

    def _rm_target_is_allowed(self, cmd: str) -> bool:
        """
        True only if EVERY rm argument is an allowed-deletion target.
        The allowed token must be the final path component — not a substring
        anywhere in the command string.
        """
        allowed = set()
        for tok in ALLOWED_DELETIONS:
            t = tok.strip().strip("/").lstrip("./").replace("*", "")
            t = t.rsplit("/", 1)[-1]
            if t:
                allowed.add(t)

        targets: list[str] = []
        for m in re.finditer(r'\brm\b((?:\s+-{1,2}[a-zA-Z]+)*)((?:\s+[^\s;&|]+)+)', cmd):
            arg_blob = m.group(2)
            for arg in arg_blob.split():
                if arg.startswith("-"):
                    continue
                if arg in ("{}", "+", "\\;", ";"):
                    continue
                targets.append(arg)

        if not targets:
            return False

        for tgt in targets:
            # Absolute paths are only safe if they resolve inside a project dir
            if tgt.startswith("/"):
                real_tgt = os.path.realpath(os.path.normpath(tgt))
                if not any(real_tgt.startswith(os.path.realpath(safe)) for safe in SAFE_PROJECT_DIRS):
                    return False
            last = tgt.rstrip("/").rsplit("/", 1)[-1].replace("*", "")
            if last not in allowed:
                return False
        return True

    def _bash_touches_blocked(self, cmd: str) -> dict | None:
        """Block Bash commands that read credential paths or write to any blocked path."""
        # 1. Credential paths — block any access (read or write) using path-component matching
        for cred in BASH_CREDENTIAL_PATHS:
            # Match as path component: must be preceded/followed by space, quote, slash, or string boundary
            pattern = r'(?:^|[\s\'">/=@:(`$])' + re.escape(cred) + r'(?:[\s\'"/=@:;|)(&<>`$]|$)'
            if re.search(pattern, cmd):
                return self._deny(
                    "Bash", cmd,
                    f"Credential path '{cred}' referenced in Bash — access blocked.",
                    "CRITICAL",
                    f"bash_credential_path:{cred}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
        # 1b. Widened credential match (v3.3). The literal loop above needs a
        # boundary character immediately before the token, so 'cat prod.env',
        # 'cat config/app.env' and 'base64 certs/server.pem' slipped through.
        # Tokenize and reuse the same matcher the read family uses, so Bash and
        # Read/Grep/Glob cannot disagree about what counts as a credential.
        for tok in _BASH_TOKEN_SPLIT_RE.split(cmd):
            tok = tok.strip().strip("'\"")
            if not tok or tok.startswith("-"):
                continue
            hit = _credential_hit(tok)
            if hit:
                return self._deny(
                    "Bash", cmd,
                    f"Credential path '{tok}' referenced in Bash — access blocked ('{hit}').",
                    "CRITICAL",
                    f"bash_credential_path:{hit}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
        # 2. All BLOCKED_PATHS — block write operations
        is_write = any(sign in cmd for sign in _BASH_WRITE_SIGNS)
        if not is_write:
            # Detect sqlite3/psql/mysql with DML (writes to DB without shell write operators)
            if re.search(r'\b(?:sqlite3|psql|mysql|mariadb)\b', cmd):
                if re.search(r'\b(?:INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE)\b', cmd, re.IGNORECASE):
                    is_write = True
        if not is_write:
            # Detect python/perl writing inline
            cmd_lower = cmd.lower()
            if ("python" in cmd_lower or "perl" in cmd_lower) and "open(" in cmd:
                is_write = any(q in cmd for q in ("'w'", '"w"', "'a'", '"a"', "'x'", '"x"'))
        if not is_write:
            # Detect cp/mv/rsync/install/ln/dd (incl. sudo/absolute-path prefixes,
            # newline-separated commands) and shutil.copy*/shutil.move,
            # os.replace/os.rename, Path.write_text/write_bytes — these overwrite
            # a destination without any of the shell write operators above, so a
            # blocked path was reachable via e.g. `cp x .claude/settings.json`,
            # `sudo cp`, `/bin/cp`, a second line after `\n`, or `dd of=...`
            # (found by stress test, 2026-08-11 — first pass covered only the
            # bare unprefixed, single-line case).
            if re.search(r'(?:^|[;&|\n]\s*)(?:sudo\s+)?(?:[\w./-]*/)?(?:cp|mv|rsync|install|ln)\b', cmd, re.MULTILINE) or \
               re.search(r'\bdd\s+(?:\S+\s+)*of=', cmd) or \
               re.search(r'\bshutil\.(?:copy\w*|move)\s*\(', cmd) or \
               re.search(r'\bos\.(?:replace|rename)\s*\(', cmd) or \
               re.search(r'\.write_(?:text|bytes)\s*\(', cmd):
                is_write = True
        if is_write:
            blocked = _blocked_path_hit(cmd)
            if blocked:
                return self._deny(
                    "Bash", cmd,
                    f"Blocked path '{blocked}' targeted by Bash write operation.",
                    "CRITICAL",
                    f"bash_write_blocked_path:{blocked}",
                    "Use Write/Edit tool for file modifications. Bash cannot bypass path restrictions.",
                )
            # Governance corpus via shell (v3.5): same policy as the Edit/Write
            # and MCP routes — escalate, never silently allow.
            gov = _governance_path_hit(cmd)
            if gov:
                return self._escalate(
                    "Bash", cmd[:80],
                    f"Bash write targets the DQIII8 governance corpus ('{gov}') — "
                    "human confirmation required.",
                    f"bash_write_governance_path:{gov}",
                    "Confirm the governance change with the user before writing.",
                )
        return None

    def _read_touches_credential(self, tool: str, path: str) -> dict | None:
        """Block a read-family tool from touching genuine credential material."""
        hit = _credential_hit(path)
        if not hit:
            return None
        return self._deny(
            tool,
            path,
            f"{tool} blocked at '{path}': credential material ('{hit}').",
            "CRITICAL",
            f"read_credential_path:{hit}",
            "Use os.environ.get() for secrets. Credential files are never read into context.",
        )

    def _read_family_credential_block(self, tool: str, inp: dict) -> dict | None:
        """Credential gate for Read / Grep / Glob (v3.3).

        Read — file_path.
        Grep — path (a file, a directory, or omitted meaning cwd) *and* the
               --glob filter. Grep returns file content, and even in
               files_with_matches mode it is a per-regex oracle over that
               content, so both routes to a credential file must be closed.
        Glob — path only. Glob returns file names, never content; gating the
               search root stops enumeration inside .ssh/.secrets/.gnupg, which
               is the part with recon value, while leaving a codebase-wide
               '**/*.pem' sweep (itself a legitimate audit action) alone.
        """
        path = inp.get("file_path") or inp.get("path") or ""
        blocked = self._read_touches_credential(tool, path)
        if blocked:
            return blocked
        if tool == "Grep":
            hit = _glob_filter_hit(inp.get("glob") or "")
            if hit:
                return self._deny(
                    tool,
                    str(inp.get("glob", "")),
                    f"Grep blocked: --glob filter targets credential files ('{hit}').",
                    "CRITICAL",
                    f"read_credential_path:{hit}",
                    "Narrow the glob to non-credential files. Secrets come from os.environ.get().",
                )
        return None

    def _web_egress_block(self, tool: str, inp: dict) -> dict | None:
        """Egress gate for WebFetch / WebSearch (v3.4).

        WebFetch — the URL is the payload channel. Denied when it names a
            request-capture sink, a cloud metadata endpoint, a non-http scheme,
            embedded userinfo credentials, or carries a recognised secret shape.
            Escalated when it targets a private/loopback host or carries an
            opaque high-volume token — both are heuristics, so a human decides.
        WebSearch — no attacker-chosen destination exists, so only the secret
            shape is checked: a key pasted into a third-party search backend's
            logs is a disclosure even though nobody chose the recipient.
        """
        if tool == "WebSearch":
            query = str(inp.get("query", "") or "")
            secret = _url_secret_hit(query)
            if secret:
                return self._deny(
                    tool,
                    query[:80],
                    f"WebSearch blocked: query carries credential material ('{secret}').",
                    "CRITICAL",
                    f"web_egress_secret:{secret}",
                    "Never put keys or tokens in a search query — they land in "
                    "third-party logs. Search for the error text instead.",
                )
            return None

        url = str(inp.get("url", "") or "")
        if not url:
            return None

        # A schemeless URL ("example.com/page") parses with an empty hostname
        # and the whole thing in .path, which would misread a legitimate fetch
        # as an empty-host one. The tool itself resolves these as https, so
        # normalise the same way before any host reasoning. An explicit scheme
        # (including file:) is left untouched so the scheme check still sees it.
        raw = url.strip()
        if raw.startswith("//"):
            raw = "https:" + raw
        elif not re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", raw):
            raw = "https://" + raw

        try:
            parsed = urllib.parse.urlparse(raw)
        except Exception:
            return self._deny(
                tool, url[:80],
                "WebFetch blocked: URL could not be parsed for egress review.",
                "HIGH", "web_egress_unparseable",
                "Supply a plain https:// URL.",
            )

        scheme = (parsed.scheme or "").lower()
        if scheme and scheme not in _WEB_ALLOWED_SCHEMES:
            return self._deny(
                tool, url[:80],
                f"WebFetch blocked: scheme '{scheme}' is not http/https.",
                "CRITICAL", f"web_egress_scheme:{scheme}",
                "Use Read for local files. WebFetch is for http(s) pages only.",
            )

        if parsed.username or parsed.password:
            return self._deny(
                tool, url[:80],
                "WebFetch blocked: URL embeds userinfo credentials (user:pass@host).",
                "CRITICAL", "web_egress_userinfo",
                "Fetch the public URL. Authenticated URLs are not supported here.",
            )

        secret = _url_secret_hit(raw)
        if secret:
            return self._deny(
                tool, url[:80],
                f"WebFetch blocked: URL carries credential material ('{secret}') — "
                "this is exfiltration, not a lookup.",
                "CRITICAL", f"web_egress_secret:{secret}",
                "Never place a key, token or private key in an outbound URL.",
            )

        risk = _host_egress_risk(parsed.hostname or "")
        if risk:
            kind, token = risk
            if kind == "sink":
                return self._deny(
                    tool, url[:80],
                    f"WebFetch blocked: '{token}' is a request-capture endpoint "
                    "whose only purpose is receiving exfiltrated data.",
                    "CRITICAL", f"web_egress_sink_host:{token}",
                    "Fetch the real documentation or API host instead.",
                )
            if kind == "metadata":
                return self._deny(
                    tool, url[:80],
                    f"WebFetch blocked: '{token}' is a link-local/cloud-metadata "
                    "address (SSRF credential grab).",
                    "CRITICAL", f"web_egress_metadata_host:{token}",
                    "Instance metadata is never a legitimate research target.",
                )
            return self._escalate(
                tool, url[:80],
                f"WebFetch to private/loopback host '{token}' — needs human review.",
                f"web_egress_private_host:{token}",
                "Local services are reached with Bash curl, not WebFetch, so the "
                "request is visible in the transcript.",
            )

        blob = _opaque_blob_hit(raw)
        if blob:
            return self._escalate(
                tool, url[:80],
                f"WebFetch carries an opaque {len(blob)}+ char token "
                f"('{blob[:32]}…') — possible encoded payload. Human review required.",
                "web_egress_opaque_blob",
                "If this is a legitimate document/dataset id, fetch it via a "
                "human-readable URL or ask the user to approve this one.",
            )
        return None

    def evaluate(self, tool: str, inp: dict, session_id: str | None = None) -> dict:
        """
        Evaluates whether a tool can execute.
        decision ∈ {APPROVE, DENY, ESCALATE}

        session_id: Hook event session ID (takes priority over environment variable).
        """
        _session = session_id or SESSION_ID
        # Grep/Glob carry their target in "path", not "file_path"/"command";
        # without it every Grep in a session would share the empty detail string
        # and trip _check_repeat_rejections against each other. WebFetch/
        # WebSearch carry theirs in "url"/"query", for the same reason.
        detail = str(
            inp.get("file_path")
            or inp.get("command")
            or inp.get("path")
            or inp.get("url")
            or inp.get("query")
            or ""
        )

        # 0a. Safe project directories — fast-path (respects BLOCKED_PATHS)
        # Path is canonicalized (realpath + normpath) BEFORE the prefix check so
        # traversal payloads like /root/dqiii8/../../etc/sudoers cannot pass.
        if tool in ("Write", "Edit", "MultiEdit"):
            file_path = inp.get("file_path", inp.get("path", ""))
            real_path = os.path.realpath(os.path.normpath(file_path))
            in_safe_dir = any(
                real_path.startswith(os.path.realpath(safe))
                for safe in SAFE_PROJECT_DIRS
            )
            if in_safe_dir:
                # GOVERNANCE_PATHS excluded too: the whole governance corpus
                # lives *inside* DQIII8_ROOT, so without this the safe-dir
                # fast path would approve every rule/hook rewrite before the
                # step-3 escalation could ever run.
                if not any(
                    blocked in real_path for blocked in BLOCKED_PATHS
                ) and not _governance_path_hit(real_path):
                    return self._approve(
                        "Safe project directory", "LOW", "safe_project_dir"
                    )

        # 0b block removed — learned_approvals moved after CRITICAL_PATTERNS (see 4a)

        # 1. ESCALATE — closes infinite loops
        escalate = self._check_repeat_rejections(tool, detail, _session)
        if escalate:
            return escalate

        # 2. Budget — block if session budget is exceeded
        budget_deny = self._check_budget(_session)
        if budget_deny:
            return budget_deny

        # 3. Blocked / governance paths — EVERY tool that names a path (v3.5).
        # Runs ahead of learned_approvals (4a) and the autonomous auto-approve
        # (5), so neither can whitelist a blocked or governance write.
        try:
            _candidates = _candidate_paths(tool, inp)
        except Exception as _cpe:
            log.warning("permission_analyzer: _candidate_paths failed: %s", _cpe)
            return self._deny(
                tool, str(detail)[:80],
                "Internal analyzer error during path extraction — denying as precaution.",
                "HIGH", "analyzer_internal_error",
                "Retry, or ask the user to perform this write manually.",
            )
        for path in _candidates:
            blocked = _blocked_path_hit(path)
            if blocked:
                return self._deny(
                    tool,
                    path,
                    f"Write blocked at '{path}'. "
                    "Edit this file manually if needed.",
                    "CRITICAL",
                    f"blocked_path:{blocked}",
                    "Edit directly from terminal or ask the user.",
                )
            gov = _governance_path_hit(path)
            if gov:
                return self._escalate(
                    tool,
                    path,
                    f"'{path}' is part of the DQIII8 governance corpus ('{gov}') — "
                    "it defines the rules every other permission check enforces. "
                    "Human confirmation required before this write proceeds.",
                    f"governance_path:{gov}",
                    "Confirm with the user that this governance change is intended, "
                    "then have them apply it or re-run with explicit approval. "
                    "Autonomous mode does not waive this.",
                )

        # 3b. Resource claims — block if another agent holds the file
        if tool in ("Edit", "Write", "MultiEdit"):
            path = inp.get("file_path", inp.get("path", ""))
            claim_deny = self._check_resource_claim(tool, path, _session)
            if claim_deny:
                return claim_deny

        # Extract Bash command once for all Bash checks (3c, 4, 4b)
        _bash_cmd = inp.get("command", "") or "" if tool == "Bash" else ""

        # 3c. BLOCKED_PATHS enforcement for Bash
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                _bash_block = self._bash_touches_blocked(cmd)
                if _bash_block:
                    return _bash_block
            except Exception as _bte:
                # A security check that was reached and threw must fail closed,
                # not degrade to APPROVE — the "hooks degrade to APPROVE" doc
                # convention covers hook-level/startup failure, not a check
                # that ran and errored (mirrors block 4's handling, which
                # already denies; 3c/3d/3e previously didn't — found by
                # stress test, 2026-08-11).
                log.warning("permission_analyzer: _bash_touches_blocked failed: %s", _bte)
                return self._deny(
                    tool, str(cmd)[:80],
                    "Internal analyzer error during blocked-path check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry, or ask the user to run this command manually.",
                )

        # 3d. Credential enforcement for the read family (mirror of 3c for Bash).
        # Must run before 4a (learned_approvals) so a historically-seen path
        # can never whitelist a credential read.
        if tool in ("Read", "Grep", "Glob"):
            try:
                _read_block = self._read_family_credential_block(tool, inp)
                if _read_block:
                    return _read_block
            except Exception as _rte:
                log.warning("permission_analyzer: _read_family_credential_block failed: %s", _rte)
                return self._deny(
                    tool, str(inp.get("file_path", inp.get("path", "")))[:80],
                    "Internal analyzer error during credential check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry, or ask the user to check this file manually.",
                )

        # 3e. Egress enforcement for the web family (v3.4). Same placement rule
        # as 3c/3d: BEFORE 4a (learned_approvals), so a repeatedly-attempted
        # exfiltration URL can never be auto-whitelisted past the gate.
        # Any MCP tool carrying a `url` is the same egress channel: `mcp__fetch`
        # is settings.json-allowed via the `mcp__*` glob AND is this system's
        # *documented default* fetcher (web-research-tools.md), so gating only
        # the built-in WebFetch would leave the primary path wide open.
        if tool in ("WebFetch", "WebSearch") or (
            tool.startswith("mcp__") and inp.get("url")
        ):
            try:
                _web_block = self._web_egress_block(tool, inp)
                if _web_block:
                    return _web_block
            except Exception as _wee:
                log.warning("permission_analyzer: _web_egress_block failed: %s", _wee)
                return self._deny(
                    tool, str(inp.get("url", ""))[:80],
                    "Internal analyzer error during web egress check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry, or ask the user to fetch this URL manually.",
                )

        # 4. Always-CRITICAL commands (no mode exception, no ALLOWED_DELETIONS)
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                for pattern in CRITICAL_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE):
                        return self._deny(
                            tool, cmd,
                            f"Catastrophic command blocked: '{cmd[:80]}'",
                            "CRITICAL", f"critical_pattern:{pattern}",
                            "This command is irreversible and catastrophic.",
                        )
            except Exception as _ce:
                log.warning("permission_analyzer: CRITICAL pattern check failed: %s", _ce)
                return self._deny(
                    tool, str(inp.get("command", ""))[:80],
                    "Internal analyzer error during critical check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry with a valid command string.",
                )

        # 4a. learned_approvals — only AFTER blocked-path + CRITICAL checks.
        # A historically-safe pattern can never override a CRITICAL deny.
        if self._is_learned_safe(tool, detail):
            return self._approve(
                "Pattern approved by history", "LOW", "learned_approval"
            )

        # 4b. High-risk commands with ALLOWED_DELETIONS exception
        if tool == "Bash":
            try:
                cmd = _bash_cmd
                for pattern in HIGH_RISK_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE):
                        is_safe_deletion = self._rm_target_is_allowed(cmd)
                        if is_safe_deletion:
                            break
                        if DQIII8_MODE == "autonomous":
                            return self._deny(
                                tool, cmd,
                                f"High-risk command in autonomous mode: {cmd[:80]}",
                                "HIGH", f"high_risk_pattern:{pattern}",
                                "Use ALLOWED_DELETIONS or run in supervised mode.",
                            )
                        else:
                            return self._deny(
                                tool, cmd,
                                f"Blocked command: '{cmd[:80]}'",
                                "CRITICAL", f"high_risk_pattern:{pattern}",
                                "This command is destructive and irreversible.",
                            )
            except Exception as _he:
                log.warning("permission_analyzer: HIGH_RISK pattern check failed: %s", _he)

        # 5. Autonomous mode — auto-approve standard tools (after checks)
        if DQIII8_MODE == "autonomous" and tool in AUTO_APPROVE_TOOLS:
            return self._approve("autonomous_mode")

        return self._approve()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _approve(
        self,
        reason: str = "OK",
        risk_level: str = "LOW",
        rule_triggered: str | None = None,
    ) -> dict:
        return {
            "decision": "APPROVE",
            "reason": reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": None,
        }

    def _deny(
        self,
        tool: str,
        detail: str,
        reason: str,
        risk_level: str,
        rule_triggered: str,
        suggested_fix: str,
    ) -> dict:
        # Enrich reason with self-correction hint
        enriched_reason = reason
        if rule_triggered:
            for key, hint in DENIAL_HINTS.items():
                if key in rule_triggered:
                    enriched_reason = f"{reason} | Alternative: {hint}"
                    break
        return {
            "decision": "DENY",
            "reason": enriched_reason,
            "risk_level": risk_level,
            "rule_triggered": rule_triggered,
            "suggested_fix": suggested_fix,
        }

    def _escalate(
        self,
        tool: str,
        detail: str,
        reason: str,
        rule_triggered: str,
        suggested_fix: str,
    ) -> dict:
        """Blocked pending a human decision.

        Same wire effect as DENY (pre_tool_use.py maps both to a deny), but
        recorded as ESCALATE so record_rejection routes it to the operator
        instead of reading as a settled policy violation. Used for heuristics
        that a legitimate action could plausibly trip.
        """
        return {
            "decision": "ESCALATE",
            "reason": reason,
            "risk_level": "HIGH",
            "rule_triggered": rule_triggered,
            "suggested_fix": suggested_fix,
        }

    def _check_repeat_rejections(
        self, tool: str, detail: str, session_id: str | None = None
    ) -> dict | None:
        """
        If the same tool+action_detail has been rejected MAX_SAME_REJECTION
        times (DENY or ESCALATE) in this session → return ESCALATE.
        FIX C: counts both DENY and ESCALATE.
        """
        _session = session_id or SESSION_ID
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT COUNT(*) FROM permission_decisions
                WHERE session_id = ?
                  AND tool_name = ?
                  AND action_detail LIKE ?
                  AND decision IN ('DENY', 'ESCALATE')
                  AND timestamp > datetime('now', '-2 hours')
                """,
                (_session, tool, f"%{detail[:50]}%"),
            ).fetchone()

            count = row[0] if row else 0
            if count >= MAX_SAME_REJECTION:
                conn.close()
                return {
                    "decision": "ESCALATE",
                    "reason": (
                        f"Action '{tool}: {detail[:60]}' rejected "
                        f"{count} times in this session. "
                        "Requires human decision."
                    ),
                    "risk_level": "HIGH",
                    "rule_triggered": f"repeat_rejection:{count}",
                    "suggested_fix": (
                        "OrchestratorLoop must pause and notify the user. "
                        "The agent needs a different strategy that does not "
                        "require this blocked action. "
                        f"Previous attempts: {count}."
                    ),
                }
            conn.close()
            # Reset in-process fallback if DB is healthy
            _key = f"{tool}|{detail[:50]}"
            with _proc_rejection_lock:
                _proc_rejection_counts.pop(_key, None)
        except Exception as e:
            log.warning(
                "permission_analyzer: _check_repeat_rejections query failed "
                "— using in-process counter: %s", e
            )
            _key = f"{tool}|{detail[:50]}"
            with _proc_rejection_lock:
                _proc_rejection_counts[_key] = _proc_rejection_counts.get(_key, 0) + 1
                _count = _proc_rejection_counts[_key]
            if _count >= MAX_SAME_REJECTION:
                return {
                    "decision": "ESCALATE",
                    "reason": (
                        f"Action '{tool}: {detail[:60]}' rejected "
                        f"{_count} times (in-process counter — DB unavailable). "
                        "Requires human decision."
                    ),
                    "risk_level": "HIGH",
                    "rule_triggered": f"repeat_rejection_inproc:{_count}",
                    "suggested_fix": "DB unavailable. Human confirmation required.",
                }
        return None

    def _is_learned_safe(self, tool: str, detail: str) -> bool:
        """
        Checks if this tool+pattern has already been approved >= 3 times (active=1).
        Fast-path before all security checks.
        """
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT id FROM learned_approvals
                WHERE tool_name = ?
                  AND ? LIKE '%' || pattern || '%'
                  AND active = 1
                LIMIT 1
                """,
                (tool, detail),
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _check_resource_claim(
        self, tool: str, path: str, session_id: str
    ) -> dict | None:
        """
        Blocks if another agent/session holds an active claim on this resource.
        Claims expire automatically by TTL (expires_at).
        """
        if not path:
            return None
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                """
                SELECT agent, session_id FROM resource_claims
                WHERE resource = ?
                  AND session_id != ?
                  AND expires_at > datetime('now')
                LIMIT 1
                """,
                (path, session_id),
            ).fetchone()
            conn.close()
            if row:
                holder_agent, holder_session = row
                return self._deny(
                    tool,
                    path,
                    f"Resource '{path}' locked by agent '{holder_agent}' "
                    f"(session {holder_session[:8]}…). Wait for the claim to expire.",
                    "MEDIUM",
                    "resource_claim",
                    "Wait 30 min or ask the owning agent to release the resource.",
                )
        except Exception as e:
            log.warning("permission_analyzer: _check_resource_claim query failed: %s", e, exc_info=True)
        return None

    def _check_budget(self, session_id: str) -> dict | None:
        """Blocks if estimated session cost exceeds MAX_SESSION_COST_USD."""
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_used),0) FROM agent_actions "
                "WHERE session_id=? AND timestamp > datetime('now','-1 hour')",
                (session_id,),
            ).fetchone()
            conn.close()
            session_tokens = row[0] if row else 0
            estimated_cost = (session_tokens / 1_000_000) * 15.0
            if estimated_cost > MAX_SESSION_COST_USD:
                return self._deny(
                    "budget",
                    f"${estimated_cost:.2f}",
                    f"Session budget exceeded: "
                    f"${estimated_cost:.2f} > ${MAX_SESSION_COST_USD}",
                    "HIGH",
                    "budget_exceeded",
                    "Split the objective into smaller subtasks. "
                    "Start a new session with j --autonomous",
                )
        except Exception as e:
            log.warning("permission_analyzer: _check_budget query failed: %s", e, exc_info=True)
        return None


# ── Standalone functions (used by pre_tool_use.py) ──────────────────────────


def _notify_telegram_activation(tool_name: str, pattern: str) -> None:
    """Fire-and-forget Telegram alert when a pattern auto-activates at times_seen=3."""
    try:
        import requests
        from dotenv import load_dotenv

        load_dotenv(str(DQIII8_ROOT / ".env"))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        msg = (
            "🔓 *Auto-approval activated*\n"
            f"`{tool_name}` → `{pattern[:80]}`\n"
            "Seen: 3 times. Active for future uses."
        )
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        log.warning("permission_analyzer: _notify_telegram_activation send failed: %s", e, exc_info=True)  # never block the pipeline


def record_decision(tool: str, inp: dict, result: dict) -> None:
    """
    Records APPROVE decisions in the DB.
    For LOW risk approvals: auto-learns the pattern in learned_approvals
    when seen >= 3 times (activates the record).
    """
    if result["decision"] != "APPROVE":
        return
    action_detail = str(inp.get("file_path", inp.get("command", "")))[:200]
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                action_detail,
                "APPROVE",
                result.get("reason", "OK"),
                result.get("risk_level", "LOW"),
            ),
        )
        # Auto-learning for low-risk patterns
        if (
            result.get("risk_level") == "LOW"
            and result.get("reason") != "learned_approval"
        ):
            pattern = action_detail[:50].strip()
            if pattern:
                conn.execute(
                    """
                    INSERT INTO learned_approvals
                        (tool_name, pattern, times_seen, last_seen, active)
                    VALUES (?, ?, 1, datetime('now'), 0)
                    ON CONFLICT(tool_name, pattern) DO UPDATE SET
                        times_seen = times_seen + 1,
                        last_seen  = datetime('now'),
                        active     = CASE WHEN times_seen + 1 >= 3 THEN 1 ELSE 0 END
                    """,
                    (tool, pattern),
                )
                # Notify if this upsert just auto-activated the pattern (times_seen=3)
                row = conn.execute(
                    "SELECT times_seen, active FROM learned_approvals "
                    "WHERE tool_name=? AND pattern=?",
                    (tool, pattern),
                ).fetchone()
                if row and row[0] == 3 and row[1] == 1:
                    _notify_telegram_activation(tool, pattern)
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("permission_analyzer: record_decision DB write failed: %s", e, exc_info=True)


def record_rejection(tool: str, inp: dict, result: dict) -> None:
    """
    Records DENY and ESCALATE in two channels:
    Channel 1 — DB: permission_decisions table
    Channel 2 — JSON mailbox: tasks/permission_rejection.json (read by OrchestratorLoop)
    FIX A: added JSON channel.
    """
    if result["decision"] not in ("DENY", "ESCALATE"):
        return

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": SESSION_ID,
        "tool_name": tool,
        # url/query included so a blocked egress attempt reaches the operator
        # with the actual destination instead of an empty string. Deliberately
        # NOT mirrored into record_decision(): that path feeds learned_approvals,
        # and approved research URLs must not accumulate as auto-approve rules.
        # `path`/`sql` added in v3.5: MCP filesystem and DB tools carry their
        # target there, so without them a blocked/escalated MCP write reached
        # the operator as an empty action_detail.
        "action_detail": str(
            inp.get("file_path")
            or inp.get("command")
            or inp.get("path")
            or inp.get("url")
            or inp.get("query")
            or inp.get("sql")
            or ""
        )[:200],
        "decision": result["decision"],
        "reason": result.get("reason", ""),
        "risk_level": result.get("risk_level", ""),
        "rule_triggered": result.get("rule_triggered", ""),
        "suggested_fix": result.get("suggested_fix", ""),
    }

    # Channel 1: DB
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute(
            """
            INSERT INTO permission_decisions
                (session_id, tool_name, action_detail, decision, reason,
                 risk_level, rule_triggered, suggested_fix)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SESSION_ID,
                tool,
                entry["action_detail"],
                entry["decision"],
                entry["reason"],
                entry["risk_level"],
                entry["rule_triggered"],
                entry["suggested_fix"],
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning("permission_analyzer: record_rejection DB channel write failed: %s", e, exc_info=True)

    # Channel 2: JSON mailbox (append to array)
    try:
        reject_path = DQIII8_ROOT / "tasks" / "permission_rejection.json"
        existing: list = []
        if reject_path.exists():
            try:
                existing = json.loads(reject_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = []
            except Exception:
                existing = []
        existing.append(entry)
        reject_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning("permission_analyzer: record_rejection JSON mailbox write failed: %s", e, exc_info=True)
