#!/usr/bin/env python3
"""
DQIII8 — PermissionAnalyzer
Centralized permission evaluation for pre_tool_use hooks.

Every tool call resolves to APPROVE, DENY or ESCALATE. What is gated:

- Destructive commands and SQL (CRITICAL_PATTERNS / HIGH_RISK_PATTERNS),
  with ALLOWED_DELETIONS as the only carve-out.
- Path writes: BLOCKED_PATHS denies, GOVERNANCE_PATHS escalates. Paths are
  extracted by _candidate_paths() from Edit/Write, MCP filesystem and github
  write tools, and Bash (cwd- and glob-aware); mcp__context-mode__ctx_execute*
  is treated as Bash-equivalent.
- Credential reads, including glob- and quote-spliced forms.
- Network egress: WebFetch/WebSearch, MCP tools carrying url/urls/query, the
  MCP payload catch-all, and egress primitives inside Bash.
- Per-session budget.

Rejections go to two channels (SQLite + JSON inbox) so an operator sees them
even when the DB is unavailable.
"""

import fnmatch
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
    # Host persistence paths (2026-08-18). This list was repo-shaped except for
    # the SSH/key entries, so `Write /etc/cron.d/pwn`, `Write /root/.bashrc`
    # and `echo … >> /etc/passwd` were all approved — each of which executes
    # code on the next cron tick, shell start or login, i.e. *outside* the hook
    # system, which makes every other control here bypassable in one approved
    # step. The agent runs as root; nothing it legitimately does writes any of
    # these. Read stays unaffected — this is a write denylist.
    "/etc/cron",
    "/etc/systemd/",
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/profile",
    "/etc/rc.local",
    "/etc/ld.so.preload",
    "/root/.bashrc",
    "/root/.bash_profile",
    "/root/.profile",
]

# ── Governance paths ────────────────────────────────────────────────────────
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

# ── Credential-path gate ────────────────────────────────────────────────────
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

# Bracket classes are globs too (2026-08-18, RT17): bash expands
# '.claude/setting[s].json' onto the blocked literal exactly like the '?' form
# already denied, but a '*?'-only detector never flagged the token, so it
# never reached the fnmatch probes below.
_GLOB_WILDCARD_RE = re.compile(r"[*?]+|\[[^\]]+\]")

# ── Candidate-path extraction ───────────────────────────────────────────────
# Every filesystem path a tool call could touch, whatever the tool. The
# BLOCKED_PATHS check runs against all of them, not just Edit/Write file_path:
# the MCP tools settings.local.json allow-lists (mcp__filesystem__write_file,
# mcp__dqiii8-db__execute) reach the same files by other argument names.

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
# `source`/`destination`). `paths`/`file_paths` added 2026-08-18:
# read_multiple_files carries its targets as a *list* under a
# plural key that this tuple never matched, so a multi-file credential read
# via that one tool was invisible to every path-based check below.
_MCP_PATH_KEYS = (
    "file_path", "path", "source", "destination", "target", "dest",
    "paths", "file_paths",
)

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

    Edit/Write/MultiEdit — file_path.
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

    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Artifact"):
        # NotebookEdit carries its target as notebook_path, not file_path;
        # Artifact carries file_path but publishes content to a hosted page
        # rather than the local filesystem — surfaced here so the credential
        # gate at step 3d can still cover it, even though a
        # BLOCKED_PATHS/GOVERNANCE_PATHS hit is not really meaningful for it.
        p = inp.get("file_path") or inp.get("notebook_path") or inp.get("path", "")
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
        # mcp__github__* (2026-08-18): create_or_update_file/delete_file/
        # push_files etc. write repo content and were entirely unchecked —
        # _MCP_PATH_KEYS didn't apply because the branch above is gated to
        # mcp__filesystem__ only. Read-shaped suffixes (get_*/list_*/search_*)
        # are exempt; anything else fails closed, same policy as the
        # filesystem server above (settings.json allows the whole mcp__* glob).
        if tool.startswith("mcp__github__") and not suffix.startswith(
            ("get_", "list_", "search_")
        ):
            for key in _MCP_PATH_KEYS:
                val = inp.get(key)
                if isinstance(val, str) and val:
                    paths.append(val)
                elif isinstance(val, (list, tuple)):
                    paths.extend(str(v) for v in val if v)
            # push_files carries its targets as files: [{path, content}, ...],
            # not a top-level path key.
            files = inp.get("files")
            if isinstance(files, (list, tuple)):
                for f in files:
                    if isinstance(f, dict):
                        p = f.get("path")
                        if isinstance(p, str) and p:
                            paths.append(p)
        # Any MCP tool that takes SQL is a filesystem actor via ATTACH/VACUUM,
        # regardless of which server exposes it.
        for key in ("sql", "query", "statement"):
            val = inp.get(key)
            if isinstance(val, str) and val:
                paths.extend(_sql_candidate_paths(val))

    seen: set[str] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _mcp_read_candidate_paths(tool: str, tool_input: dict) -> list[str]:
    """Every path-like argument an MCP call carries, INCLUDING read-only
    filesystem tools (2026-08-18).

    `_candidate_paths()` deliberately exempts `_MCP_FS_READONLY_SUFFIXES`
    (read_text_file, read_multiple_files, ...) from the BLOCKED_PATHS/
    GOVERNANCE_PATHS *write* check — you must be able to read CLAUDE.md. But
    that exemption also meant those exact tools never surfaced their paths
    for the *credential* gate, so `mcp__filesystem__read_text_file
    {"path": ".env"}` reached zero checks and exfiltrated the file into
    context. This function is used ONLY at step 3d (credential gate), never
    for the write-path check — a read-only tool's paths must be credential-
    checked regardless of whether they're also write-checked.
    """
    if not tool.startswith("mcp__"):
        return []
    inp = tool_input or {}
    paths: list[str] = []
    for key in _MCP_PATH_KEYS:
        val = inp.get(key)
        if isinstance(val, str) and val:
            paths.append(val)
        elif isinstance(val, (list, tuple)):
            paths.extend(str(v) for v in val if v)
    seen: set[str] = set()
    return [p for p in paths if not (p in seen or seen.add(p))]


def _path_match_candidates(path: str) -> list[str]:
    """Normalized forms of `path` to test BLOCKED_PATHS/GOVERNANCE_PATHS against.

    Mirrors `_credential_hit`'s candidate set (2026-08-18): the plain normpath
    closes the `/./`/`//` bypass (`.claude/./settings.json` collapsed a
    substring match that raw string containment never caught), and the
    realpath closes symlink laundering (`ln -s CLAUDE.md notes.md` then
    `Write notes.md` must resolve to the real protected file, same as the
    credential gate already requires).
    """
    if not path:
        return []
    # normpath/realpath both strip a trailing slash, but BLOCKED_PATHS/
    # GOVERNANCE_PATHS tokens for directories carry one ('.claude/hooks/') to
    # avoid matching a same-prefixed file — restore it unconditionally (not
    # only when the input itself had one) so a bare directory name like
    # `Write {"file_path": ".../.git"}` still matches the `.git/` token
    # instead of silently falling through to APPROVE (F10, 2026-08-19).
    candidates = {os.path.normpath(path)}
    try:
        candidates.add(os.path.realpath(path))
    except OSError as _re:  # pragma: no cover — realpath rarely raises
        log.warning("permission_analyzer: realpath failed for %r: %s", path, _re)
    candidates |= {c + "/" for c in candidates}
    return sorted(candidates)


def _blocked_path_hit(path: str) -> str | None:
    """The BLOCKED_PATHS token a path matches, ignoring governance-only tokens.

    A token that is in both lists (`.claude/settings.local.json`) is resolved by
    GOVERNANCE_PATHS (ESCALATE), so it is excluded here. A governance file that
    *also* matches a genuine deny token (e.g. `.claude/rules/secrets.md` hitting
    "secrets") still denies — DENY wins whenever the two lists disagree.
    """
    for cand in _path_match_candidates(path):
        for blocked in BLOCKED_PATHS:
            if blocked in GOVERNANCE_PATHS:
                continue
            if blocked in cand:
                return blocked
    return None


def _governance_path_hit(path: str) -> str | None:
    """The GOVERNANCE_PATHS token a path matches, or None."""
    for cand in _path_match_candidates(path):
        normalized = cand.replace("\\", "/")
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


# Known-sensitive basenames a Bash glob token is probed against
# (2026-08-18). _CREDENTIAL_BASENAME_RE needs an exact basename ('cat .env'
# denies, 'cat .e*' doesn't — the token isn't a real basename, it's a glob
# pattern), so credential detection for a glob-shaped token instead asks the
# reverse question: does this pattern match a name we know is sensitive?
_CREDENTIAL_GLOB_PROBES = (
    ".env", ".env.local", ".env.production", ".credentials.json",
    "id_rsa", "id_ed25519", ".secrets", "secrets.json",
    "client_secret.json", "server.pem", "server.key", "cert.p12", "cert.pfx",
)

def _credential_glob_hit(token: str) -> str | None:
    """Return the sensitive basename a Bash glob TOKEN would expand to, or None.

    Only checked when `token` actually contains a glob metacharacter — a
    literal token is already covered by `_credential_hit`.
    """
    if not token or not _GLOB_WILDCARD_RE.search(token):
        return None
    base = token.replace("\\", "/").rsplit("/", 1)[-1]
    for probe in _CREDENTIAL_GLOB_PROBES:
        if fnmatch.fnmatchcase(probe, base):
            return probe
    return None


def _collapse_adjacent_quotes(cmd: str) -> str:
    """Collapse Bash's directly-adjacent-quote string concatenation.

    Bash joins quoted literals with no separating whitespace into one word:
    '.en''v' -> .env, ".e"'nv' -> .env. The tokenizer splits on quote
    characters, so it never reconstructs this; without collapsing first,
    `cat '.en''v'` reads as two harmless tokens ('.en', 'v') instead of one
    credential basename. Applied repeatedly to a working copy used only for
    credential detection — a 3+-way concatenation needs more than one
    pass, and this must never affect any other check's view of `cmd`.
    """
    prev = None
    out = cmd
    while prev != out:
        prev = out
        out = out.replace("''", "").replace('""', "").replace("'\"", "").replace("\"'", "")
        # Backslash-escaped characters ('.en\v' -> '.env') collapse the same
        # way Bash itself does — without this,
        # 'cat .en\vironment.env'-style splicing evaded credential detection
        # exactly like the adjacent-quote case above.
        out = re.sub(r"\\(.)", r"\1", out)
    return out


# [S5] base64/openssl/xxd/uudecode piped straight into a shell/interpreter —
# the decoded payload never touches disk as a visible file, so no
# blocked-path or CRITICAL/HIGH_RISK matcher ever sees its content.
_OBFUSCATED_DECODE_PIPE_RE = re.compile(
    r"\bbase64\b[^|;\n]*\s(?:-d\b|--decode\b|-di\b)[^|;\n]*\|\s*(?:sudo\s+)?"
    r"(?:sh|bash|zsh|python[0-9.]*|perl|ruby)\b"
    r"|\bopenssl\b[^|;\n]*\benc\b[^|;\n]*\s-d\b[^|;\n]*\s-a\b[^|;\n]*\|\s*(?:sudo\s+)?"
    r"(?:sh|bash|zsh|python[0-9.]*|perl|ruby)\b"
    r"|\bxxd\b[^|;\n]*\s-r\b[^|;\n]*\s-p\b[^|;\n]*\|\s*(?:sudo\s+)?"
    r"(?:sh|bash|zsh|python[0-9.]*|perl|ruby)\b"
    r"|\buudecode\b[^|;\n]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python[0-9.]*|perl|ruby)\b"
)

# [S5] Bash ANSI-C quoted strings ($'...') are decoded by the shell itself
# before the command it names ever runs — 'rm -rf /' hidden as
# $'\x72\x6d\x20\x2d\x72\x66\x20\x2f' reaches the real rm binary untouched
# by any pattern matcher that only sees the literal escape sequences.
# Deliberately matched against the RAW cmd, never the _collapse_adjacent_quotes
# copy: that helper's `\(.)-> \1` pass runs re.sub repeatedly and would mangle
# `\xNN` into a single stray character before this ever sees it.
_ANSI_C_QUOTE_RE = re.compile(r"\$'((?:[^'\\]|\\.)*)'")
_ANSI_C_ESCAPE_RE = re.compile(
    r"\\x([0-9A-Fa-f]{1,2})|\\u([0-9A-Fa-f]{4})|\\([0-7]{1,3})|\\e|\\n"
)


def _decode_ansi_c_escapes(payload: str) -> str:
    """Best-effort decode of the escape forms Bash's $'...' honors that a
    hex/octal/obfuscated-command payload would actually use: \\xNN, \\NNN
    (octal), \\uNNNN, \\e, \\n. [S5]"""
    def _sub(m: re.Match) -> str:
        if m.group(1) is not None:
            return chr(int(m.group(1), 16))
        if m.group(2) is not None:
            return chr(int(m.group(2), 16))
        if m.group(3) is not None:
            return chr(int(m.group(3), 8) & 0xFF)
        if m.group(0) == r"\e":
            return "\x1b"
        if m.group(0) == r"\n":
            return "\n"
        return m.group(0)

    return _ANSI_C_ESCAPE_RE.sub(_sub, payload)


def _ansi_c_decoded_cmd(raw_cmd: str) -> str | None:
    """`raw_cmd` with every $'...' ANSI-C-quoted span replaced by its
    decoded content, or None if no such span is present. [S5]"""
    if "$'" not in raw_cmd:
        return None
    return _ANSI_C_QUOTE_RE.sub(lambda m: _decode_ansi_c_escapes(m.group(1)), raw_cmd)


# Every directory change in the command, not just a leading `cd <dir> &&`
# prefix (2026-08-18): the anchored form missed `pushd`, a second chained
# `cd`, a subshell `(cd … && …)`, a newline separator, and the `cd` inside
# `bash -c '…'`. The lookbehind keeps 'abcd foo' / '/usr/bin/cd' from
# matching while allowing '(', quote, ';', '&&' and newline to precede it.
_CD_CHDIR_RE = re.compile(
    r"""(?<![\w./-])(?:cd|pushd)\s+("[^"]*"|'[^']*'|[^\s;&|)]+)"""
)


def _bash_effective_cwd(cmd: str) -> str:
    """The directory the command's `cd`/`pushd` chain ends up in, or
    DQIII8_ROOT if there is none.

    `_blocked_path_hit`/`_governance_path_hit` did plain substring matching
    against the raw command text, so `cd /root/dqiii8/.claude && echo pwned >
    settings.json` never contained the literal blocked-path token in any
    form — the write target only becomes '.claude/settings.json' once you
    resolve it against the directory the `cd` changed into. Every chdir in
    the command is applied in order, so `cd /root/dqiii8 && cd .claude && …`
    and `(cd /root/dqiii8/.claude && …)` resolve the same as the canonical
    single-prefix form.
    """
    cwd = str(DQIII8_ROOT)
    for m in _CD_CHDIR_RE.finditer(cmd):
        target = m.group(1).strip("'\"")
        if not target or target.startswith("-"):
            continue
        if target in ("~", "$HOME", "${HOME}"):
            cwd = str(DQIII8_ROOT)
        elif target.startswith("/"):
            cwd = os.path.normpath(target)
        else:
            cwd = os.path.normpath(os.path.join(cwd, target))
    return cwd


# Archive extraction destination directories (2026-08-18, round-3 audit).
# `tar -C <dir> -xf a.tar` and `unzip -d <dir> a.zip` write every member of the
# archive into <dir>, but the destination only ever appeared as a bare
# directory token — and the BLOCKED/GOVERNANCE matchers need a trailing slash
# ('.claude/hooks/') or an exact file match, so a directory token never hit.
# Both tools' short and long destination flags are covered, with or without
# '='.
_TAR_DEST_RE = re.compile(
    r"""\btar\b[^|;&\n]*?\s(?:-C|--directory)(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|]+)"""
)
_UNZIP_DEST_RE = re.compile(
    r"""\bunzip\b[^|;&\n]*?\s(?:-d|--directory)(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|]+)"""
)
# Same surface, other tools (2026-08-18). tar/unzip were never the only way to
# unpack attacker-chosen filenames into a directory:
#   7z/7za/7zr  -o<dir>          — 7zip's own syntax, no space after the flag
#   bsdtar      -C/--directory   — NOT matched by _TAR_DEST_RE ('bsdtar' has no
#                                  word boundary before 'tar')
#   cpio        -D/--directory   — extract mode, e.g. `cpio -idmv -D <dir>`
#   pip install --target/-t      — writes arbitrary package files (including
#                                  .py that later gets imported) into <dir>
_SEVENZIP_DEST_RE = re.compile(
    r"""\b7z[ar]?\b[^|;&\n]*?\s-o("[^"]*"|'[^']*'|[^\s;&|]+)"""
)
_BSDTAR_DEST_RE = re.compile(
    r"""\bbsdtar\b[^|;&\n]*?\s(?:-C|--directory)(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|]+)"""
)
_CPIO_DEST_RE = re.compile(
    r"""\bcpio\b[^|;&\n]*?\s(?:-D|--directory)(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|]+)"""
)
_PIP_TARGET_RE = re.compile(
    r"""\bpip[23]?\b[^|;&\n]*?\binstall\b[^|;&\n]*?\s(?:--target|-t)(?:=|\s+)("[^"]*"|'[^']*'|[^\s;&|]+)"""
)

_ARCHIVE_DEST_RES = (
    _TAR_DEST_RE,
    _UNZIP_DEST_RE,
    _SEVENZIP_DEST_RE,
    _BSDTAR_DEST_RE,
    _CPIO_DEST_RE,
    _PIP_TARGET_RE,
)


def _archive_dest_dirs(cmd: str) -> list[str]:
    """Destination directories an archive/installer tool would write into.

    Returned with a trailing separator so the directory tokens in
    BLOCKED_PATHS/GOVERNANCE_PATHS ('.git/', '.claude/hooks/') can match; the
    slash-less form is returned too for the file-shaped tokens. Relative
    destinations are resolved against the command's effective cwd, same as
    every other Bash write target.
    """
    cwd = _bash_effective_cwd(cmd)
    out: list[str] = []
    for pattern in _ARCHIVE_DEST_RES:
        for m in pattern.finditer(cmd):
            tgt = m.group(1).strip().strip("'\"")
            if not tgt or tgt.startswith("-"):
                continue
            resolved = os.path.normpath(
                tgt if tgt.startswith("/") else os.path.join(cwd, tgt)
            )
            out.append(resolved)
            out.append(resolved.rstrip("/") + "/")
    return out


# Same-command shell variables (2026-08-18, RT16). `Y=settings; echo x >
# .claude/$Y.json` writes the blocked literal, but every '$'-carrying token was
# either dropped outright or resolved with the reference left intact, so no
# BLOCKED/GOVERNANCE token ever appeared. Static text substitution of
# assignments found earlier in the same command string — nothing is executed,
# no eval, no environment lookup.
_SHELL_ASSIGN_RE = re.compile(
    r"""(?:^|[\s;&|(])([A-Za-z_]\w*)=("[^"]*"|'[^']*'|[^\s;&|)<>]*)"""
)
_SHELL_VAR_REF_RE = re.compile(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)")


def _shell_assignments(cmd: str) -> dict[str, str]:
    return {
        m.group(1): m.group(2).strip("'\"")
        for m in _SHELL_ASSIGN_RE.finditer(cmd)
    }


def _expand_shell_vars(token: str, assigns: dict[str, str]) -> str:
    return _SHELL_VAR_REF_RE.sub(
        lambda m: assigns.get(m.group(1) or m.group(2), m.group(0)), token
    )


def _protected_paths_matching(pattern: str) -> list[str]:
    """Protected paths a still-unresolved write target could expand onto.

    The leftover '$VAR' is treated as one wildcard segment, so a token whose
    value only the runtime knows (an environment variable, a command
    substitution) is never silently approved: if some expansion of it lands on
    a BLOCKED/GOVERNANCE path, that concrete path is handed back to the normal
    matchers, which decide DENY vs ESCALATE with the usual precedence.
    Equal segment count keeps fnmatch's '/'-crossing '*' from making every
    variable write match every protected path under the root.
    """
    depth = pattern.count("/")
    hits = []
    for token in (*BLOCKED_PATHS, *GOVERNANCE_PATHS):
        cand = token if token.startswith("/") else os.path.join(str(DQIII8_ROOT), token)
        cand = cand.rstrip("/")
        if cand.count("/") == depth and fnmatch.fnmatchcase(cand, pattern):
            hits.append(cand + "/" if token.endswith("/") else cand)
    return hits


def _bash_resolved_write_targets(cmd: str) -> list[str]:
    """Strings to test against BLOCKED_PATHS/GOVERNANCE_PATHS for a Bash
    write: the raw command (cheap, catches the common case), the quote/
    backslash-collapsed command ('CLA''UDE.md' / 'CLA\\UDE.md'
    evaded the raw-string match), and every relative path-shaped token
    resolved against the command's effective cwd (a `cd`
    prefix changes what a bare relative token actually targets).
    """
    collapsed = _collapse_adjacent_quotes(cmd)
    cwd = _bash_effective_cwd(collapsed)
    assigns = _shell_assignments(collapsed)
    out = [cmd, collapsed]
    out.extend(_archive_dest_dirs(collapsed))
    for raw_tok in _BASH_TOKEN_SPLIT_RE.split(collapsed):
        tok = raw_tok.strip().strip("'\"")
        if not tok or tok.startswith("-"):
            continue
        if "$" in tok:
            tok = _expand_shell_vars(tok, assigns)
        # `~/.bashrc` and `$HOME/.bashrc` name the same file as
        # `/root/.bashrc`, but the first resolved against cwd into a
        # nonexistent `<cwd>/~/…` and the second was skipped outright with
        # every other `$`-prefixed token. Only these two home spellings are
        # expanded (2026-08-18): a general expandvars would rewrite unset
        # variables to the empty string and manufacture paths the command
        # never names.
        if tok.startswith("~"):
            tok = os.path.expanduser(tok)
        elif tok.startswith(("$HOME", "${HOME}")):
            tok = os.path.expanduser("~" + tok.split("}", 1)[-1].removeprefix("$HOME"))
        elif "$" in tok and "/" in tok:
            # RT16: a var not assigned earlier in this same command (an
            # inherited env var, a value from a prior command) survives
            # _expand_shell_vars unresolved. Silently skipping the token, as
            # before, let `Y=settings; echo x > .claude/$Y.json` (a known
            # assignment) work while `echo x > .claude/$UNKNOWN.json` sailed
            # past every check with no candidate path at all. Each remaining
            # '$VAR'/'${VAR}' becomes one wildcard path segment instead, so
            # any concrete expansion landing on a BLOCKED/GOVERNANCE path is
            # still caught (see _protected_paths_matching). Gated on '/' in
            # tok: a bare '$VAR' with no path structure at all (a value being
            # echoed/passed, not a path — `echo "$ANTHROPIC_API_KEY" > /dev/
            # null`) would otherwise become a lone '*' that fnmatches ANY
            # single-segment protected file at cwd's depth, denying commands
            # that touch no protected path whatsoever.
            wildcard_tok = _SHELL_VAR_REF_RE.sub("*", tok)
            wildcard_path = os.path.normpath(
                wildcard_tok if wildcard_tok.startswith("/") else os.path.join(cwd, wildcard_tok)
            )
            out.extend(_protected_paths_matching(wildcard_path))
            continue
        elif tok.startswith("$"):
            continue
        resolved = os.path.normpath(
            tok if tok.startswith("/") else os.path.join(cwd, tok)
        )
        out.append(resolved)
        # Directory entries in BLOCKED_PATHS/GOVERNANCE_PATHS carry a trailing
        # separator ('.git/', '.claude/hooks/') so they cannot match a
        # same-prefixed file, but a token naming the directory itself
        # (`rm -r .claude/hooks`) never carries one — so the directory form is
        # offered too, exactly as _archive_dest_dirs already does for
        # extraction destinations.
        out.append(resolved.rstrip("/") + "/")
    return out


# Reverse-glob probes for BLOCKED_PATHS/GOVERNANCE_PATHS basenames
# (mirrors _credential_glob_hit for the write-path gate):
# does a glob-shaped Bash token ('CLAUD?.md', '*.local.json') expand onto a
# protected basename? Split into two probe sets, same DENY-wins-except-
# settings.local.json precedence as _blocked_path_hit/_governance_path_hit.
_BLOCKED_GLOB_PROBES = tuple(sorted({
    p.rstrip("/").rsplit("/", 1)[-1]
    for p in BLOCKED_PATHS if p.rstrip("/") and p not in GOVERNANCE_PATHS
}))
_GOVERNANCE_GLOB_PROBES = tuple(sorted({
    p.rstrip("/").rsplit("/", 1)[-1] for p in GOVERNANCE_PATHS if p.rstrip("/")
}))


def _blocked_glob_hit(token: str) -> str | None:
    """The BLOCKED_PATHS basename a glob-shaped Bash TOKEN would expand to
    match, or None (excludes the settings.local.json overlap — governance
    wins there, same as _blocked_path_hit)."""
    if not token or not _GLOB_WILDCARD_RE.search(token):
        return None
    base = token.replace("\\", "/").rsplit("/", 1)[-1]
    for probe in _BLOCKED_GLOB_PROBES:
        if probe and fnmatch.fnmatchcase(probe, base):
            return probe
    return None


def _governance_glob_hit(token: str) -> str | None:
    """The GOVERNANCE_PATHS basename a glob-shaped Bash TOKEN would expand to
    match, or None."""
    if not token or not _GLOB_WILDCARD_RE.search(token):
        return None
    base = token.replace("\\", "/").rsplit("/", 1)[-1]
    for probe in _GOVERNANCE_GLOB_PROBES:
        if probe and fnmatch.fnmatchcase(probe, base):
            return probe
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


# ── Web egress gate ─────────────────────────────────────────────────────────
# The credential gates above stop secrets *entering* context. Egress is the
# other half, and it is gated on four surfaces: this WebFetch/WebSearch gate,
# the Bash network-egress checks in step 3, and the MCP url/urls and payload
# catch-all gates in steps 3e/3f. Each one is load-bearing — none is a subset
# of another. This surface covers the tools whose only outbound channel is a
# URL, with no request body and no header control.
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

# Bash operators that indicate a WRITE to a file. Expanded 2026-08-18 —
# the original list missed sed's long-form flag, perl -i,
# interactive editors, and curl/wget's own output-to-file flags, all of
# which write without any of ">"/"tee"/"truncate" appearing.
_BASH_WRITE_SIGNS = [">", ">>", "tee ", "sed -i", "truncate "]
_BASH_WRITE_SIGN_PATTERNS = [
    re.compile(r"\bsed\b[^|;&\n]*\s(?:-i|--in-place)\b"),
    re.compile(r"\bperl\b[^|;&\n]*\s-\w*i\w*\b"),
    re.compile(r"(?:^|[\s;&|])(?:ex|vi|vim|nvim|nano|emacs)\s+\S"),
    re.compile(r"\b(?:curl|wget)\b[^|;&\n]*\s(?:-o|-O|--output|--output-document)\b"),
    re.compile(r"\b(?:touch|mkdir|chmod|chown|ln)\b"),
    # Deletion is a write (2026-08-18). `_rm_destructive_targets` below only
    # reasons about recursive+force rm against '/'-rooted or $HOME targets and
    # only against ALLOWED_DELETIONS — it never consults BLOCKED_PATHS or
    # GOVERNANCE_PATHS. So plain `rm <file>`, `rm -r <dir>` (no -f),
    # `find … -delete`, `xargs rm` and `shred -u` deleted CLAUDE.md,
    # .claude/settings.json or this analyzer itself with no matcher at all,
    # while `mv` away and `truncate -s 0` were both caught. A removed file is
    # as gone as an overwritten one, and removing the analyzer disarms every
    # other check in this module. ALLOWED_DELETIONS is unaffected: build/cache
    # names are not blocked or governance paths.
    re.compile(r"\b(?:rm|unlink|shred)\b"),
    re.compile(r"\bfind\b[^|;&\n]*\s-delete\b"),
    # The stream compressors replace their input file in place and delete the
    # original unless '-c'/'--stdout' is given, so `gzip -f CLAUDE.md`
    # destroys the file without naming any write operator.
    re.compile(r"\b(?:gzip|bzip2|xz|zstd)\b(?![^|;&\n]*\s-{1,2}(?:c\b|stdout\b))"),
]

# rm invocation matcher: `rm`, its flags (short-combined/-separate/long-form,
# any order), then its non-flag arguments. Style-agnostic on purpose
# (2026-08-18) — the prior literal `rm -rf ...` regexes missed
# `rm -fr`, `rm -r -f`, `rm --recursive --force`, and `--no-preserve-root`.
_RM_INVOCATION_RE = re.compile(r"\brm\b((?:\s+-{1,2}[A-Za-z-]+)*)((?:\s+[^\s;&|]+)+)")


def _rm_flags_recursive_and_force(flags_blob: str) -> bool:
    """True if the captured rm flags include both recursive and force,
    regardless of style: -rf, -fr, -Rf, -r -f, --recursive --force, or any
    mix of short/long forms."""
    has_r = has_f = False
    for tok in flags_blob.split():
        if tok.startswith("--"):
            has_r = has_r or tok == "--recursive"
            has_f = has_f or tok == "--force"
        elif tok.startswith("-"):
            letters = tok[1:]
            has_r = has_r or ("r" in letters or "R" in letters)
            has_f = has_f or ("f" in letters)
    return has_r and has_f


def _rm_destructive_targets(cmd: str) -> list[str]:
    """Every rm target reached by a recursive+force invocation — '/', an
    absolute path, '~', or '$HOME' — flag-order/style agnostic. Non-dangerous
    targets (relative paths, ALLOWED_DELETIONS-shaped names) are left for the
    caller, which applies `_rm_target_is_allowed`."""
    hits: list[str] = []
    for m in _RM_INVOCATION_RE.finditer(cmd):
        if not _rm_flags_recursive_and_force(m.group(1)):
            continue
        for raw_tgt in m.group(2).split():
            # Strip surrounding quotes before comparing: `rm -rf "/"` and
            # `rm -rf '/'` are the exact same catastrophic call as `rm -rf /`
            # and previously slipped through because the raw token ('"/"')
            # matched neither '/' nor startswith('/').
            tgt = raw_tgt.strip("'\"")
            if not tgt or tgt.startswith("-") or tgt in ("{}", "+", "\\;", ";"):
                continue
            if tgt == "/" or tgt.startswith("/") or tgt in ("~", "$HOME", "${HOME}"):
                hits.append(tgt)
    return hits

# context-mode MCP server (2026-08-18): allow-listed in
# settings.local.json, arbitrary sandboxed code/subprocess execution, and its
# own tool descriptions actively steer callers here instead of Bash ("PREFER
# THIS OVER BASH for: API calls..., test runners..."). None of it was routed
# through any Bash-equivalent check. ctx_fetch_and_index/ctx_search are read/
# query-shaped by name and are deliberately left out — only the three
# confirmed exec-capable tools are covered.
_CTX_MODE_EXEC_TOOLS = frozenset({
    "mcp__context-mode__ctx_execute",
    "mcp__context-mode__ctx_execute_file",
    "mcp__context-mode__ctx_batch_execute",
})


def _ctx_mode_command_text(tool: str, inp: dict) -> str:
    """The command-line-equivalent text a context-mode exec tool carries.

    ctx_execute/ctx_execute_file: a `code` string (plus `path` for the file
    variant, which is fed into `code` as FILE_CONTENT — the path itself is
    still worth scanning directly). ctx_batch_execute: an array of literal
    shell command strings under `commands[].command`.
    """
    parts: list[str] = []
    code = inp.get("code")
    if isinstance(code, str) and code:
        parts.append(code)
    path = inp.get("path")
    if isinstance(path, str) and path:
        parts.append(path)
    commands = inp.get("commands")
    if isinstance(commands, (list, tuple)):
        for c in commands:
            if isinstance(c, dict):
                cmd_str = c.get("command")
                if isinstance(cmd_str, str) and cmd_str:
                    parts.append(cmd_str)
    return "\n".join(parts)


# Entry gate for the Bash egress checks below: the WebFetch/WebSearch gate
# (_web_egress_block) never runs for Bash, so anything that can open a socket
# from a shell command needs its own trigger here. Matches any shape that can
# reach the network: egress binaries, Python HTTP and socket clients, and bare
# bash `/dev/tcp/` redirection, which opens a connection while naming no binary
# at all. The alternation below is the list — do not restate it elsewhere.
# Deliberately shape-based, not binary-name-based: a name-only list left the
# socat/nc sinks in _ENV_DUMP_TO_NET_RE unreachable, and a matched command is
# only inspected further (secret/env-dump/pipe-to-shell), never denied on the
# match alone — so over-matching here is cheap and under-matching is not.
# This is not the full WebFetch gate: host-risk and opaque-blob reasoning over
# arbitrary shell text is too noisy to be worth running here.
_NETWORK_EGRESS_BASH_RE = re.compile(
    r"\b(?:curl|wget|nc|ncat|netcat|socat|scp|sftp|rsync|ssh|ftp|telnet)\b"
    r"|urllib\.request|requests\.(?:post|get|put|patch)\b|httpx\."
    r"|socket\.(?:socket|connect|create_connection)"
    r"|http\.client|aiohttp|/dev/tcp/"
)
_SENSITIVE_ENV_VAR_RE = re.compile(
    r"\$\{?[A-Z][A-Z0-9_]*(?:_KEY|_TOKEN|_SECRET|_PASSWORD|_PASSWD)\}?\b"
)
_ENV_DUMP_TO_NET_RE = re.compile(
    r"\b(?:printenv|env)\b[^|;\n]*\|\s*(?:curl|wget|nc|ncat|netcat|socat)\b"
    # `exec 3<>/dev/tcp/host/port; env >&3` dumps the environment to a socket
    # with no pipe and no external binary at all.
    r"|\b(?:printenv|env)\b[^|;\n]*>&\s*\d"
)
# The environment object handed wholesale to a network call in Python
# (`requests.post(url, data=os.environ)`, `http.client ... os.environ[...]`).
# `_ENV_DUMP_TO_NET_RE` is shell-pipeline-shaped and never saw these. Only
# consulted for commands that already look like egress, so a plain
# `python3 -c "print(os.environ['HOME'])"` is unaffected.
_PY_ENV_TO_NET_RE = re.compile(r"os\.environ\b")
# Bare hostname literals ('webhook.site' inside HTTPSConnection('…')) never
# appear as an http(s):// URL, so the URL sweep below cannot see them.
_BASH_BARE_HOST_RE = re.compile(r"""['"]([A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,})['"]""")
_PIPE_TO_SHELL_RE = re.compile(
    r"\b(?:curl|wget)\b[^|;\n]*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|python[0-9.]*|perl|ruby)\b"
)
# [S6] Upload forms beyond the `curl -T-` shape already implied by
# _NETWORK_EGRESS_BASH_RE: -T/--upload-file, and -F/--form with an @-file
# attachment (curl reads the file named after '@' and sends its bytes).
_UPLOAD_FORM_RE = re.compile(
    r"\bcurl\b[^|;\n]*\s(?:-T\b|--upload-file\b)"
    r"|\bcurl\b[^|;\n]*\s(?:-F\b|--form\b)[^|;\n]*=@"
)
# [S6] A local archive/compress/encode tool piped straight into a network
# command — the compressed/encoded bytes never touch disk as a named file,
# so no blocked-path check ever sees what's being sent. Extends the
# existing tar|zip|7z coverage (_ARCHIVE_DEST_RES et al., a different
# check for a different purpose — those gate the archive's *destination*
# path, this gates archived *content* leaving via the network).
_ARCHIVE_PIPE_TO_NET_RE = re.compile(
    r"\b(?:zstd|gzip|bzip2|xz|base64|gpg)\b[^|;\n]*\|\s*(?:sudo\s+)?"
    r"(?:curl|wget|nc|ncat|netcat|socat|scp|rsync)\b"
)
# [S6] Reverse-shell shapes: the direct `nc -e`/`ncat -c`/`socat ... exec:`
# exec-flag form (this was only claimed as "existing coverage" by a stale
# comment — no regex ever matched it; found live-unfixed 2026-08-19), a named
# pipe piped through nc without -e (the classic `mkfifo`-based workaround for
# netcat builds lacking -e), and Python/Perl socket-plus-shell one-liners.
# [guardrails-security panel, 2026-08-19] four more standard-issue shapes
# that walked straight through as APPROVE, live-confirmed: (1) bash's
# `/dev/tcp/HOST/PORT` pseudo-device attached to an interactive shell or fd
# dup'd back into one — no external binary at all, so none of the token
# checks above ever fire; (2) socat's `system:` address type, functionally
# identical to `exec:`/`EXEC:` but a different literal string; (3) Perl's
# `-MSocket` command-line module flag, functionally identical to a
# `use Socket;` source line but not matched by that literal text; (4) a
# Python socket + os.dup2 fd-redirect one-liner that hands off to
# subprocess/os.exec* instead of pty.spawn.
_REVERSE_SHELL_RE = re.compile(
    r"\b(?:nc|ncat|netcat)\b[^|;\n]*\s-[A-Za-z]*[ec]\S*\s"
    r"|\bsocat\b[^|;\n]*\b(?:exec|EXEC|system|SYSTEM):"
    r"|\bmkfifo\b[^|;\n]*(?:[;&\n]|&&)[^|;\n]*\bnc\b[^|;\n]*<"
    r"|\bpython[0-9.]*\b[^\n]*\bimport\s+socket\b[^\n]*\bpty\.spawn\b"
    r"|\bperl\b[^\n]*(?:\buse\s+Socket\b|-MSocket\b)"
    r"|/dev/tcp/[A-Za-z0-9.\-]+/\d+[^\n]*(?:<&|>&|&>)"
    r"|(?:<&|>&|&>)[^\n]*/dev/tcp/[A-Za-z0-9.\-]+/\d+"
    r"|(?=[^\n]*\bimport\s+socket\b)(?=[^\n]*\bos\.dup2\b)"
    r"(?=[^\n]*\b(?:subprocess\.(?:call|run|Popen)\b|os\.exec[lv][ep]?\b|os\.system\b))"
    r"\bpython[0-9.]*\b"
)
# [RT12] os.system/os.popen hand a full shell command to the OS; pty.spawn
# starts an interactive shell; eval/exec/compile run arbitrary Python source.
# All four are execution primitives, not just write primitives — folded
# into the same is_write trigger as os.remove/shutil.move/etc above, plus a
# narrower unresolvable-argument ESCALATE (see the call site).
_INLINE_EXEC_RE = re.compile(
    r"\bos\.(?:system|popen)\s*\(|\bpty\.spawn\s*\(|\b(?:eval|exec|compile)\s*\("
)


def _py_inline_call_first_arg(cmd: str, paren_open_idx: int) -> str | None:
    """The text of a Python call's first argument, given the index right
    after its opening '(' (as returned by re.Match.end() on a call regex
    ending in '\\('). Returns None if the parens don't balance within the
    command (truncated/malformed source — fail open on the extraction,
    the caller's regex-based checks elsewhere still see the raw text)."""
    depth = 1
    i = paren_open_idx
    start = paren_open_idx
    while i < len(cmd) and depth:
        ch = cmd[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    if depth:
        return None
    arg_blob = cmd[start:i - 1]
    # First top-level comma splits off the first argument.
    depth = 0
    for j, ch in enumerate(arg_blob):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return arg_blob[:j].strip()
    return arg_blob.strip()


_PY_STRING_LITERAL_RE = re.compile(
    r"""^(?:r|b|rb|br)?(['"]).*\1$""", re.IGNORECASE | re.DOTALL
)


def _py_arg_is_resolvable(arg: str) -> bool:
    """[RT12] True only for a plain quoted string literal with no
    interpolation — the one shape whose runtime value is already fully
    known from the source text, so the existing literal-content checks
    (blocked/governance path, Bash-pattern matchers) cover it. An f-string
    (`f"..."`), a bare identifier, `sys.argv[...]`, string concatenation,
    or anything else is treated as unresolvable — its actual value can only
    be known at runtime."""
    arg = arg.strip()
    if not arg:
        return True
    if re.match(r"^(?:f|fr|rf)['\"]", arg, re.IGNORECASE):
        return False
    return bool(_PY_STRING_LITERAL_RE.match(arg))

# Always CRITICAL regardless of mode.
# The literal 'rm -rf /' entries are handled separately by
# _rm_destructive_targets() (flag-order/style agnostic — see _RM_INVOCATION_RE)
# rather than as regexes here; evaluate() checks that first.
CRITICAL_PATTERNS = [
    r">\s*/dev/(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+|hd[a-z]+|md\d+|mapper/\S+)",
    r"\bmkfs\b",  # format a filesystem
    r"\bdd\b[^|;&\n]*\b(?:if|of)=/dev/(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+|hd[a-z]+|md\d+|mapper/\S+)",  # `of=` is the destructive half; `if=` is matched too because reading a raw device is how a disk gets copied off the box
    # Device writes that never go through '>' or dd: `cat /dev/zero | tee
    # /dev/sda` destroys the disk exactly like '> /dev/sda' did, and
    # wipefs/parted/sfdisk/fdisk/blkdiscard/shred rewrite the partition
    # table or scrub the device with no redirection at all.
    r"\btee\b[^|;&\n]*\s/dev/(?:sd[a-z]+|nvme\d+n\d+|vd[a-z]+|hd[a-z]+|md\d+|mapper/\S+|disk/\S+)",
    r"\b(?:wipefs|parted|sfdisk|fdisk|blkdiscard|shred)\b[^|;&\n]*\s/dev/\S+",
    r">\s*/dev/disk/by-(?:uuid|id|label|partuuid|path)/\S+",  # device aliases resolve to the same raw disks
    r":\(\)\s*\{.*:\|:.*\}",  # fork bomb
]

# ── Protected-table matching (2026-08-18, round-3 audit) ────────────────────
# Two shape fixes, both found live by the round-3 re-audit:
#
#  * schema qualifier — `UPDATE main.learned_approvals` / `DELETE FROM
#    sqlite_main.agent_actions` reached the table under a `<schema>.` prefix
#    the old regexes never allowed for, so the table name simply didn't match.
#  * tautological predicate — `DELETE FROM agent_actions WHERE 1=1` satisfied
#    the old `(?!\s+WHERE)` guard (the word WHERE *was* present) while still
#    deleting every row.
#
# Best-effort regex, not a SQL parser — same stance as _SQL_PATHISH_RE above:
# the well-known no-op predicate shapes are pattern-matched, nothing more.
_SQL_TABLE_PREFIX = r"(?:[\"'`\[]?\w+[\"'`\]]?\s*\.\s*)?[\"'`\[]?"
_PROTECTED_AUDIT_TABLES = r"(?:agent_actions|permission_decisions|session_memory|instincts|sqlite_master|sqlite_schema)"
_PROTECTED_MUTATION_TABLES = r"(?:learned_approvals|permission_decisions|agent_actions|instincts|sqlite_master|sqlite_schema)"
# Predicates that bound nothing. Ordered most-specific-first so `WHERE 1=1`
# never falls through to the bare-`WHERE 1` branch.
# End of a WHERE predicate: statement terminator, comment, closing paren, or
# the closing shell quote of `sqlite3 db "DELETE ... WHERE ..."`.
_SQL_PREDICATE_END = r"(?:\s*(?:;|--|/\*|\)|[\"'`]|$))"

_SQL_TAUTOLOGY = (
    r"(?:"
    r"[\"'`]?\s*1\s*[\"'`]?\s*(?:==|=)\s*[\"'`]?\s*1\s*[\"'`]?"   # 1=1, '1'='1', "1"="1"
    r"|1\s*(?:<>|!=)\s*0"                                          # 1<>0, 1!=0
    r"|TRUE\b"                                                     # WHERE TRUE
    r"|(['\"])([^'\"]*)\1\s*=\s*\1\2\1"                            # 'a'='a' — same literal both sides
    r"|\b(\w+)\s*=\s*\3\b"                                         # col = col
    r"|1\s*(?:;|--|/\*|\)|$)"                                      # WHERE 1  (no column at all)
    # Semantic no-ops (2026-08-18, round-4 gap). Each is anchored to the end of
    # the predicate (_SQL_PREDICATE_END) so it only fires when the shape *is*
    # the whole WHERE clause — `WHERE id > -1 AND agent='x'` is genuinely
    # bounded and must stay APPROVE.
    r"|\w+\s+IS\s+NOT\s+NULL" + _SQL_PREDICATE_END                 # id IS NOT NULL — true for every PK row
    + r"|\w+\s*(?:>=|>)\s*-\s*\d+" + _SQL_PREDICATE_END            # id > -1, id >= -999 — true for any non-negative id
    + r"|\w+\s*(?:<>|!=)\s*-\s*\d+" + _SQL_PREDICATE_END           # id <> -1 — ditto
    + r")"
)
# NOTE: the two branches above use backreferences, so _SQL_TAUTOLOGY may only
# be concatenated onto patterns that contain no capture groups of their own
# (_SQL_TABLE_PREFIX / _PROTECTED_*_TABLES are all non-capturing). Adding a
# capturing group ahead of it would silently renumber \1..\3. The semantic
# branches appended at the end add no groups, so \1..\3 keep their positions.
#
# CEILING — read before adding "one more shape". This is a shape-matcher, not a
# SQL parser, and building one is explicitly out of scope. It recognises the
# handful of no-op predicates seen in practice; it does NOT understand SQL, so
# these still get through and are known-missed, by design:
#   * `WHERE NOT (1=0)` / any negation of a false predicate
#   * `WHERE id BETWEEN -999 AND 999999999` (range covering the whole table)
#   * `WHERE id IN (SELECT id FROM agent_actions)` or any subquery
#   * `WHERE id > -1 OR agent='x'` — OR'ing a tautology onto a real predicate
#     (the anchors below deliberately require the no-op to be the *whole*
#     clause, which trades this miss for zero false positives on bounded ANDs)
#   * anything computed at runtime (`WHERE id > (SELECT MIN(id)-1 ...)`)
# The unbounded-DELETE guard above (no WHERE at all) and the blanket
# UPDATE/ALTER/TRUNCATE/REPLACE/INSERT guard remain the real backstops.

# Literal-vs-literal integer comparison as the entire predicate. Both operands
# are integer literals from the matched text, so the result can be computed
# exactly — no parser and no injection risk, just arithmetic. Handled as a
# function rather than a HIGH_RISK_PATTERNS entry because a regex cannot decide
# whether `5>=5` is true.
_SQL_LITERAL_COMPARE_RE = re.compile(
    r"DELETE\s+FROM\s+" + _SQL_TABLE_PREFIX + _PROTECTED_AUDIT_TABLES
    + r"\b[\"'`\]]?\s+WHERE\s+(\d+)\s*(>=|<=|<>|!=|==|=|>|<)\s*(\d+)"
    + _SQL_PREDICATE_END,
    re.IGNORECASE,
)


def _sql_literal_tautology(cmd: str) -> str | None:
    """The always-true literal comparison bounding a DELETE on a protected
    table, or None.

    `DELETE FROM agent_actions WHERE 2>1` deletes exactly what no WHERE at all
    deletes. An always-*false* one (`WHERE 1>2`) deletes nothing and is not a
    finding, so the comparison is evaluated rather than merely matched.
    """
    for m in _SQL_LITERAL_COMPARE_RE.finditer(cmd):
        left, op, right = int(m.group(1)), m.group(2), int(m.group(3))
        truth = {
            ">": left > right,
            "<": left < right,
            ">=": left >= right,
            "<=": left <= right,
            "=": left == right,
            "==": left == right,
            "<>": left != right,
            "!=": left != right,
        }[op]
        if truth:
            return f"{left}{op}{right}"
    return None


def _strip_sql_comments(sql: str) -> str:
    """Strip SQL '--' line comments and '/* */' block comments.

    [S9a] An additional pass, never a replacement: called only on
    _mcp_sql_text and on the quoted SQL argument of a recognised DB-client
    Bash invocation (see _bash_db_client_sql_text) — never on the full Bash
    command. Blind-stripping '--' from arbitrary Bash blinds the analyzer to
    real commands: 'ls --color=auto && rm -rf /' -> 'ls ' and
    'git checkout -- x && DROP TABLE agent_actions' -> 'git checkout '.
    """
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return sql


_DB_CLIENT_SQL_ARG_RE = re.compile(
    r'\b(?:sqlite3|psql|mysql|mariadb)\b(?:\s+(?!["\'])\S+)*\s+(["\'])(.*?)\1', re.DOTALL
)


def _bash_db_client_sql_text(cmd: str) -> str:
    """The quoted SQL argument of a sqlite3/psql/mysql/mariadb invocation in
    a Bash command, or "" if none is present. Matches by the outer quote
    character reappearing (not the first quote of any kind), since the SQL
    payload itself routinely contains the other quote style as a string
    literal (`'.claude/settings.json'` inside a "..."-quoted argument)."""
    m = _DB_CLIENT_SQL_ARG_RE.search(cmd)
    return m.group(2) if m else ""


HIGH_RISK_PATTERNS = [
    # rm -rf /anything, ~, $HOME are handled by _rm_destructive_targets(),
    # not as regexes here: a literal regex list cannot stay flag-order agnostic.
    (r"DROP\s+TABLE", "drop_table"),
    (r"DROP\s+DATABASE", "drop_database"),
    # DROP TRIGGER (2026-08-18): agent_actions/instincts are append-only
    # *because* of DB triggers (01_database_mutations.md). Dropping the
    # trigger achieves what DROP TABLE achieves — a silently mutable audit
    # trail — and was not covered by either DROP pattern above.
    (r"DROP\s+TRIGGER", "drop_trigger"),
    # Mass-delete without WHERE against the audit trail. Widened beyond
    # agent_actions (2026-08-18): erasing `permission_decisions` erases the
    # forensic record of this very analyzer's denials *and* starves the
    # repeat-rejection loop-breaker that reads it.
    (r"DELETE\s+FROM\s+" + _SQL_TABLE_PREFIX + _PROTECTED_AUDIT_TABLES + r"\b[\"'`\]]?(?!\s+WHERE)",
     "delete_unbounded_audit_table"),
    # ...and the same delete *with* a WHERE whose predicate is a tautology:
    # `WHERE 1=1` / `WHERE TRUE` / `WHERE 1` delete exactly the same rows as
    # no WHERE at all, and previously APPROVED.
    (r"DELETE\s+FROM\s+" + _SQL_TABLE_PREFIX + _PROTECTED_AUDIT_TABLES + r"\b[\"'`\]]?\s+WHERE\s+" + _SQL_TAUTOLOGY,
     "delete_tautology_audit_table"),
    # Any mutating verb against a governance/audit table. `01_database_mutations.md`
    # makes agent_actions/instincts append-only (DB triggers), and
    # learned_approvals/permission_decisions drive the permission decision
    # itself — rewriting either from a shell or through mcp__dqiii8-db__execute
    # is self-escalation, never routine maintenance. Legitimate writes go
    # through bin/core/action_log.py, not raw SQL. sqlite_master/sqlite_schema
    # added 2026-08-18: writing the catalog directly rewrites the schema
    # (and drops triggers) without naming any protected table at all.
    (r"\b(?:UPDATE|ALTER\s+TABLE|TRUNCATE\s+TABLE|REPLACE\s+INTO|INSERT\s+(?:OR\s+\w+\s+)?INTO)\s+"
     + _SQL_TABLE_PREFIX + _PROTECTED_MUTATION_TABLES + r"\b", "mutate_protected_table"),
    # [S9c] CREATE TABLE ... AS SELECT ... FROM <protected table> copies a
    # protected table's rows into a brand-new, unprotected table — the
    # mutation verbs above only ever look at what comes right after
    # CREATE/UPDATE/etc, never at the SELECT's FROM clause, so this exfil
    # shape had no explicit matcher (only the incidental `*`-wildcard
    # heuristic below, which false-positives on unrelated globs and misses
    # an explicit column list).
    (r"CREATE\s+TABLE\b[\s\S]*?\bAS\s+SELECT\b[\s\S]*?\bFROM\s+"
     + _SQL_TABLE_PREFIX + _PROTECTED_MUTATION_TABLES + r"\b", "sql_create_table_as_select_protected"),
    (r"CREATE\s+TABLE\b[\s\S]*?\bAS\s+SELECT\b[\s\S]*?\bFROM\s+"
     + _SQL_TABLE_PREFIX + _PROTECTED_AUDIT_TABLES + r"\b", "sql_create_table_as_select_protected"),
    (r"PRAGMA\s+writable_schema", "pragma_writable_schema"),  # flips SQLite's schema table writable — arbitrary catalog rewrite
    (r"chmod\s+(?:-[\w-]+\s+)*(?:777|a\+rwx)\s+/\S*", "chmod_777_root"),
    # git push --force / -f / --force-with-lease (2026-08-18). This module had
    # ZERO matchers for it: `permission_request.py` names it in its own
    # unrelated CRITICAL_PATTERNS, but that hook only fires for tools *absent*
    # from settings.json's permissions.allow, and `Bash(*)` is pre-approved —
    # so nothing enforced it. 00_core_behavior.md files force-push alongside
    # `rm -rf` and `DROP` as destructive/irreversible, so it gets the same
    # verdict those get here: DENY, not ESCALATE (ESCALATE is for ambiguous
    # risk and governance writes; overwriting published history is neither
    # ambiguous nor recoverable from this side).
    # Flag-order/style agnostic, like the chmod entry above: the flag may sit
    # before or after the remote/branch. `-[a-zA-Z]*f` catches bundled short
    # flags (`-qf`); the trailing lookahead keeps `--follow-tags` and
    # `-f`-prefixed longer flags from matching.
    #
    # Four evasions closed 2026-08-18, all live-reproduced:
    #  * git global options — `git -c protocol.version=2 push --force` broke
    #    the old `git\s+push` adjacency. The leading group accepts any number
    #    of option-shaped tokens, each with an optional non-option value
    #    (`-c x=y`), and nothing else: a bare token run would make
    #    `git commit -m "push --force"` deny.
    #  * quoted invocation — `bash -c 'git push -f'` failed the trailing
    #    lookahead on the closing quote; quotes and parens are accepted
    #    terminators now.
    #  * backslash line continuation before the flag. A *bare* newline stays
    #    excluded from the gap on purpose: it terminates the command, so
    #    admitting it would deny `git push origin main` followed on the next
    #    line by an unrelated `rm -f`.
    #  * `git push origin +main` (plus-refspec force) and `--mirror` — both
    #    overwrite published history with no force flag in the command.
    # `--delete`/`-d` is deliberately NOT here: removing a stale remote branch
    # is routine and rewrites no history, and `test_r5_benign_push_still_
    # approved` pins it as APPROVE.
    (r"\bgit\b(?:\s+-{1,2}[A-Za-z][^\s;&|]*(?:\s+[^\s;&|-][^\s;&|]*)?)*\s+push\b"
     r"(?:(?:[^|;&\n]|\\\n)*?\s)?"
     r"(?:--force-with-lease(?:=[^\s;&|]*)?|--force|--mirror"
     r"|-[a-zA-Z]*f|\+[^\s;&|]+)"
     r"(?=[\s;&|'\"()]|$)", "git_push_force"),
]

# [S4] Branches whose deletion via `git push --delete`/`-d`/a `:<ref>` empty-
# source refspec must DENY even though it carries no --force flag (the
# force-push matcher above deliberately treats `--delete` as routine — it
# is, for a throwaway feature branch, but not for one of these).
PROTECTED_BRANCHES = frozenset({
    "main", "master", "production", "release", "develop", "trunk",
    "staging", "prod", "premium-main", "premium-full",
})
_PROTECTED_BRANCH_PREFIXES = ("release/", "hotfix/")


def _is_protected_branch(ref: str) -> bool:
    ref = ref.strip("'\" ").split(":", 1)[-1]
    ref = ref.rsplit("/", 1)[-1] if not ref.startswith(_PROTECTED_BRANCH_PREFIXES) else ref
    if ref in PROTECTED_BRANCHES:
        return True
    return ref.startswith(_PROTECTED_BRANCH_PREFIXES)


def _git_push_deleted_ref(cmd: str) -> str | None:
    """The branch name a `git push` deletes (`--delete`/`-d <ref>`, or the
    empty-source `:<ref>` refspec form), or None if this isn't a deleting
    push at all. [S4]

    `--delete`/`-d` take the REF as a trailing positional, with the remote
    (if given) positional before it — `git push --delete origin main` and
    `git push origin --delete main` are both valid and both delete `main`,
    not `origin`. Matching "the token right after --delete" (the original
    approach) silently captured the remote name instead whenever a remote
    was present, which is the common case — a real bypass, not a corner
    case. Token-split and take the LAST non-flag positional instead.
    """
    m = re.search(r"\bgit\b(?:\s+\S+)*?\s+push\b(.*)$", cmd)
    if not m:
        return None
    tail = re.split(r"[;&|\n]", m.group(1), maxsplit=1)[0]
    tokens = tail.split()
    has_delete_flag = any(t in ("--delete", "-d") for t in tokens)
    if has_delete_flag:
        positionals = [t.strip("'\"") for t in tokens if not t.startswith("-")]
        return positionals[-1] if positionals else None
    m = re.search(r"(?:^|[\s])(?:[\w.\-]+/)?:([^\s;&|'\"]+)", cmd)
    if m:
        return m.group(1)
    return None
# Rule ids [panel-review, P1]: each entry above carries its own stable id as
# a (regex, rule_id) tuple, not a parallel dict keyed by position
# (HIGH_RISK_PATTERNS[-1]). A positional key silently re-points itself every
# time a new pattern is appended or inserted — the id and the id-holder can
# never drift apart once they're one tuple. Add the id in the same edit that
# adds the pattern.

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
        "Narrow the action: name explicit paths instead of wildcards, bound the "
        "SQL with a WHERE clause, or push without --force. If a deletion is "
        "genuine cache cleanup, ask the user to add the name to "
        "ALLOWED_DELETIONS in permission_analyzer.py — that file is "
        "governance-escalated, so you cannot add it yourself."
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
        # ALLOWED_DELETIONS tokens come in three shapes and each needs its own
        # comparison. The previous single-bucket normalisation used
        # `lstrip("./")`, which strips every leading '.'/'/' CHARACTER rather
        # than the literal prefix: `.pytest_cache` became `pytest_cache` (so the
        # documented dotfile carve-outs never matched a real target and were
        # DENIED), `*.pyc` became `.pyc` (never equal to `foo.pyc`), and
        # `plugins/cache/` collapsed to a bare `cache` (approving
        # `<anything>/cache` — wider than documented).
        allowed_names: set[str] = set()      # exact final path component
        allowed_suffixes: set[str] = set()   # from `*.ext` globs
        allowed_tails: set[str] = set()      # multi-component relative tails
        for tok in ALLOWED_DELETIONS:
            t = tok.strip().strip("/")
            if not t:
                continue
            if t.startswith("*"):
                suffix = t[1:]
                if suffix:
                    allowed_suffixes.add(suffix)
            elif "/" in t:
                allowed_tails.add(t)
            else:
                allowed_names.add(t)

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
            norm = tgt.rstrip("/")
            last = norm.rsplit("/", 1)[-1]
            if last in allowed_names:
                continue
            if any(
                last.endswith(suffix) and len(last) > len(suffix)
                for suffix in allowed_suffixes
            ):
                continue
            if any(
                norm == tail or norm.endswith("/" + tail)
                for tail in allowed_tails
            ):
                continue
            return False
        return True

    def _bash_touches_blocked(self, cmd: str, tool: str = "Bash") -> dict | None:
        """Block Bash (or a context-mode exec-equivalent) commands that
        read credential paths or write to any blocked path.

        `tool` is only used as the label on the returned decision — every
        heuristic below still reasons over `cmd`, the flattened command text
        (see _ctx_mode_command_text for the non-Bash callers).
        """
        # 1. Credential paths — block any access (read or write) using path-component matching
        for cred in BASH_CREDENTIAL_PATHS:
            # Match as path component: must be preceded/followed by space, quote, slash, or string boundary
            pattern = r'(?:^|[\s\'">/=@:(`$])' + re.escape(cred) + r'(?:[\s\'"/=@:;|)(&<>`$]|$)'
            if re.search(pattern, cmd):
                return self._deny(
                    tool, cmd,
                    f"Credential path '{cred}' referenced in Bash — access blocked.",
                    "CRITICAL",
                    f"bash_credential_path:{cred}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
        # 1b. Widened credential match. The literal loop above needs a
        # boundary character immediately before the token, so 'cat prod.env',
        # 'cat config/app.env' and 'base64 certs/server.pem' slipped through.
        # Tokenize and reuse the same matcher the read family uses, so Bash and
        # Read/Grep/Glob cannot disagree about what counts as a credential.
        # Tokenized on a quote-collapsed working copy (2026-08-18) —
        # Bash concatenates directly-adjacent quoted literals ('.en''v' ->
        # .env), which the split-on-quote-chars tokenizer never reconstructs
        # from the raw command. `cmd` itself is untouched; every other check
        # in this function still sees the original string.
        _cred_cmd = _collapse_adjacent_quotes(cmd)
        for tok in _BASH_TOKEN_SPLIT_RE.split(_cred_cmd):
            tok = tok.strip().strip("'\"")
            if not tok or tok.startswith("-"):
                continue
            hit = _credential_hit(tok)
            if hit:
                return self._deny(
                    tool, cmd,
                    f"Credential path '{tok}' referenced in Bash — access blocked ('{hit}').",
                    "CRITICAL",
                    f"bash_credential_path:{hit}",
                    "Use os.environ.get() for secrets. Never reference credential files in Bash.",
                )
            # A glob token ('.e*', '?env') has no exact basename to
            # match, but it can still be crafted to expand onto a known
            # credential file. Ask the reverse question via fnmatch.
            glob_hit = _credential_glob_hit(tok)
            if glob_hit:
                return self._deny(
                    tool, cmd,
                    f"Glob '{tok}' in Bash would match credential file "
                    f"'{glob_hit}' — access blocked.",
                    "CRITICAL",
                    f"bash_credential_glob:{glob_hit}",
                    "Reference the file explicitly, or use os.environ.get() for secrets.",
                )
        # 2. All BLOCKED_PATHS — block write operations
        is_write = any(sign in cmd for sign in _BASH_WRITE_SIGNS)
        if not is_write:
            # Detect sqlite3/psql/mysql with DML (writes to DB without shell write operators)
            if re.search(r'\b(?:sqlite3|psql|mysql|mariadb)\b', cmd):
                if re.search(r'\b(?:INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE)\b', cmd, re.IGNORECASE):
                    is_write = True
        if not is_write:
            # Detect python/perl writing inline (2026-08-18):
            # context-mode's ctx_execute/ctx_execute_file carry raw Python
            # source with no literal "python"/"perl" token anywhere in the
            # text, so the substring gate never fired for that tool family —
            # treat it as Python context unconditionally instead of requiring
            # the token.
            cmd_lower = cmd.lower()
            _py_context = tool in _CTX_MODE_EXEC_TOOLS or "python" in cmd_lower or "perl" in cmd_lower
            if _py_context and "open(" in cmd:
                is_write = any(q in cmd for q in ("'w'", '"w"', "'a'", '"a"', "'x'", '"x"'))
            if not is_write and _py_context and (
                "write_text(" in cmd or "write_bytes(" in cmd
                or re.search(r'\bshutil\.(?:copy\w*|move|rmtree)\s*\(', cmd)
                or re.search(r'\bos\.(?:remove|unlink|rmdir|rename|replace|truncate)\s*\(', cmd)
                or re.search(r'\bsubprocess\.(?:run|Popen|call|check_call|check_output)\s*\(', cmd)
                # [RT12] os.system/os.popen/pty.spawn hand a full shell
                # command to the OS; eval/exec/compile run arbitrary Python.
                # Both are strictly more powerful than a single file write,
                # so they're folded into the same is_write path rather than
                # a parallel blocklist — see the unresolvable-target
                # ESCALATE immediately below for the part a target-path
                # check alone can't cover.
                or _INLINE_EXEC_RE.search(cmd)
            ):
                is_write = True
            # [RT12] A literal inline-exec argument ("os.system('ls')") is
            # just a Bash-equivalent command and already runs through the
            # blocked/governance/network checks elsewhere in this function
            # (see _ctx_mode_command_text and the checks above). What those
            # checks cannot see is a *non-literal* argument — a bare
            # variable, `sys.argv[...]`, or an f-string — since its actual
            # content is only known at runtime. Scoped to exactly that gap
            # (not "ESCALATE every inline interpreter call") so that
            # `python3 -c "import subprocess; subprocess.run(['ls'])"`
            # keeps approving.
            if _py_context:
                for _m in _INLINE_EXEC_RE.finditer(cmd):
                    _arg = _py_inline_call_first_arg(cmd, _m.end())
                    if _arg is not None and not _py_arg_is_resolvable(_arg):
                        return self._escalate(
                            tool, cmd[:80],
                            f"Inline Python call ('{_m.group(0)}...') passes a "
                            "non-literal argument (variable/sys.argv/f-string) "
                            "whose runtime value cannot be statically checked "
                            "— human review required.",
                            "bash_inline_exec_unresolvable_target",
                            "Use a literal argument, or confirm the runtime "
                            "value with the user before approving.",
                        )
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
        if not is_write:
            # 2026-08-18: write primitives that reach a target path
            # without any shell write operator or a name matched above —
            # found live against governance-path escalation: 'patch -p1',
            # 'git apply', 'git checkout <ref> -- <path>' (the -- form only;
            # a bare 'git checkout <branch>' just switches branches, not a
            # write), 'tar x... -C <dir>', 'unzip ... -d <dir>', and 'ed
            # <file>' (writes on its own 'w' command, but the file argument
            # alone is enough to treat it as write-capable — a read-only ed
            # session against a governance path should still be escalated
            # for human visibility, matching the conservative bias already
            # used above for sqlite3 DML detection).
            _tar_mode = re.search(r'\btar\s+(-?[a-zA-Z]{1,8})\b', cmd)
            if re.search(r'\bpatch\b', cmd) or \
               re.search(r'\bgit\s+apply\b', cmd) or \
               re.search(r'\bgit\s+checkout\b[^|;&\n]*--', cmd) or \
               (_tar_mode and "x" in _tar_mode.group(1).lower()) or \
               _archive_dest_dirs(cmd) or \
               re.search(r'\btar\b[^|;&\n]*--extract\b', cmd) or \
               re.search(r'\bunzip\b', cmd) or \
               re.search(r'(?:^|[\s;&|])ed\s+\S', cmd):
                is_write = True
        if not is_write:
            # 2026-08-18: sed --in-place, perl -i, interactive
            # editors, curl/wget -o/-O, and touch/mkdir/chmod/chown/ln all
            # write or create a target with none of the signs above present.
            if any(p.search(cmd) for p in _BASH_WRITE_SIGN_PATTERNS):
                is_write = True
        if is_write:
            # 2026-08-18: match against the raw command,
            # the quote/backslash-collapsed command, and every relative
            # token resolved against the command's effective `cd` cwd — a
            # plain substring check against `cmd` alone missed
            # `cd /root/dqiii8/.claude && echo x > settings.json` (the
            # blocked token never appears literally) and quote/backslash
            # splicing (`CLA''UDE.md`, `CLA\UDE.md`).
            _targets = _bash_resolved_write_targets(cmd)
            blocked = next((h for h in (_blocked_path_hit(t) for t in _targets) if h), None)
            if blocked:
                return self._deny(
                    tool, cmd,
                    f"Blocked path '{blocked}' targeted by Bash write operation.",
                    "CRITICAL",
                    f"bash_write_blocked_path:{blocked}",
                    "Use Write/Edit tool for file modifications. Bash cannot bypass path restrictions.",
                )
            # Governance corpus via shell: same policy as the Edit/Write
            # and MCP routes — escalate, never silently allow.
            gov = next((h for h in (_governance_path_hit(t) for t in _targets) if h), None)
            if gov:
                return self._escalate(
                    tool, cmd[:80],
                    f"Bash write targets the DQIII8 governance corpus ('{gov}') — "
                    "human confirmation required.",
                    f"bash_write_governance_path:{gov}",
                    "Confirm the governance change with the user before writing.",
                )
            # Glob-shaped tokens ('CLAUD?.md', '*.local.json') never appear
            # as a resolved literal path — probe them separately.
            for raw_tok in _BASH_TOKEN_SPLIT_RE.split(_collapse_adjacent_quotes(cmd)):
                tok = raw_tok.strip().strip("'\"")
                bg_hit = _blocked_glob_hit(tok)
                if bg_hit:
                    return self._deny(
                        tool, cmd,
                        f"Glob token in Bash write would match blocked path '{bg_hit}'.",
                        "CRITICAL", f"bash_write_blocked_glob:{bg_hit}",
                        "Reference the file explicitly. Bash cannot bypass path restrictions via globbing.",
                    )
                gg_hit = _governance_glob_hit(tok)
                if gg_hit:
                    return self._escalate(
                        tool, cmd[:80],
                        f"Glob token in Bash write would match governance path '{gg_hit}' — human confirmation required.",
                        f"bash_write_governance_glob:{gg_hit}",
                        "Confirm the governance change with the user before writing.",
                    )
        # [S9d] sqlite3/psql/mysql/mariadb invocations reach the filesystem via
        # ATTACH DATABASE / VACUUM INTO / path-shaped literals the same way an
        # MCP sql/query/statement argument does (_candidate_paths already
        # routes those through _sql_candidate_paths) — this was previously
        # wired only for MCP, so the identical SQL text run through a Bash DB
        # client bypassed the blocked/governance path check entirely.
        _db_sql = _bash_db_client_sql_text(cmd)
        if _db_sql:
            _sql_cwd = _bash_effective_cwd(cmd)
            for _p in _sql_candidate_paths(_db_sql):
                _norm = os.path.normpath(_p if _p.startswith("/") else os.path.join(_sql_cwd, _p))
                _bh = _blocked_path_hit(_norm)
                if _bh:
                    return self._deny(
                        tool, cmd,
                        f"Blocked path '{_bh}' targeted by a DB-client SQL statement.",
                        "CRITICAL", f"bash_sql_blocked_path:{_bh}",
                        "Do not ATTACH/VACUUM INTO a protected path from a DB client.",
                    )
                _gh = _governance_path_hit(_norm)
                if _gh:
                    return self._escalate(
                        tool, cmd[:80],
                        f"DB-client SQL statement targets the DQIII8 governance "
                        f"corpus ('{_gh}') — human confirmation required.",
                        f"bash_sql_governance_path:{_gh}",
                        "Confirm the governance change with the user before writing.",
                    )

        # [S6] Reverse-shell shapes — checked ahead of, and independent of,
        # the _NETWORK_EGRESS_BASH_RE gate below: a `python3 -c 'import
        # socket,pty,os; pty.spawn(...)'` or `perl -e 'use Socket;...'`
        # reverse-shell one-liner names no curl/wget/nc/socat token at all,
        # so gating this on that list would miss exactly the obfuscated
        # shapes it exists to catch.
        if _REVERSE_SHELL_RE.search(cmd):
            return self._deny(
                tool, cmd,
                "Command matches a reverse-shell shape "
                "(mkfifo+nc, socat exec:, or a socket+pty/Socket one-liner).",
                "CRITICAL", "bash_web_egress_reverse_shell",
                "Reverse shells are never approved from an agent session.",
            )

        # 3. Web-egress bypass via Bash — every socket-opening shape, not just
        # curl/wget; _NETWORK_EGRESS_BASH_RE above is the list.
        if _NETWORK_EGRESS_BASH_RE.search(cmd):
            # [S6] Upload forms beyond -T-: --upload-file, -F/--form with an
            # @-file attachment.
            if _UPLOAD_FORM_RE.search(cmd):
                return self._deny(
                    tool, cmd,
                    "Command uploads a local file via curl "
                    "(--upload-file/-T or -F/--form with an @-attachment).",
                    "CRITICAL", "bash_web_egress_upload_form",
                    "Confirm the file and destination with the user before uploading.",
                )
            # [S6] Archive/compress/encode tool piped straight into a
            # network command — same risk as tar|zip|7z piped to curl/nc,
            # extended to zstd/gzip/bzip2/xz/base64/gpg. Documented residual
            # risk (accepted, not a gap to re-file): the two-call form —
            # `tar czf /tmp/a.tgz ...` in one Bash call, `curl -F
            # f=@/tmp/a.tgz ...` in a separate one, or `find | xargs curl`
            # — is outside a single-command regex's reach; only the direct
            # pipe form is covered.
            if _ARCHIVE_PIPE_TO_NET_RE.search(cmd):
                return self._deny(
                    tool, cmd,
                    "Command pipes a compressed/encoded payload directly "
                    "into a network command.",
                    "CRITICAL", "bash_web_egress_archive_pipe",
                    "Write to a file, inspect it, then send it explicitly.",
                )
            secret = _url_secret_hit(cmd)
            if secret:
                return self._deny(
                    tool, cmd,
                    f"Command reaches a network tool while also carrying what looks like "
                    f"credential material ('{secret}') — that co-occurrence isn't worth the risk.",
                    "CRITICAL", f"bash_web_egress_secret:{secret}",
                    "Never pass a key/token to a network command on the command line.",
                )
            var_match = _SENSITIVE_ENV_VAR_RE.search(cmd)
            if var_match:
                # [F-05] This is co-occurrence, not a proven dataflow: the regex
                # only checks that a *_KEY/*_TOKEN/*_SECRET/*_PASSWORD-shaped
                # variable reference appears somewhere in a command already
                # judged egress-shaped — it never confirms the variable's value
                # actually reaches the network call's arguments (it could be an
                # unrelated var mentioned in a comment or a later, unrelated
                # command in the same line). The reason below states what was
                # actually detected instead of asserting a send that wasn't verified.
                return self._deny(
                    tool, cmd,
                    f"Command reaches a network tool while also referencing "
                    f"what looks like a sensitive env var ('{var_match.group(0)}') "
                    "— even if unused here, that ambiguity isn't worth the risk.",
                    "CRITICAL", "bash_web_egress_secret_envvar",
                    "Never interpolate a *_KEY/*_TOKEN/*_SECRET/*_PASSWORD env "
                    "var into a network command.",
                )
            if _ENV_DUMP_TO_NET_RE.search(cmd):
                return self._deny(
                    tool, cmd,
                    "Command sends the full process environment over the "
                    "network, either piped into a network tool or "
                    "redirected straight to a socket file descriptor.",
                    "CRITICAL", "bash_web_egress_env_dump",
                    "Never pipe printenv/env output to curl/wget/nc/ncat/netcat/socat, "
                    "and never redirect it (>&N) to a socket fd — send only the "
                    "specific values needed.",
                )
            # Payload-shape check, independent of the destination host: a
            # request carrying os.environ is an environment dump whether it
            # goes to a known sink or to an attacker-controlled host that
            # looks perfectly ordinary.
            if _PY_ENV_TO_NET_RE.search(cmd):
                return self._deny(
                    tool, cmd,
                    "Command hands the process environment to a network call "
                    "(os.environ inside an egress call).",
                    "CRITICAL", "bash_web_egress_env_dump",
                    "Send only the specific values needed, never os.environ itself.",
                )
            if _PIPE_TO_SHELL_RE.search(cmd):
                return self._escalate(
                    tool, cmd[:80],
                    "Command downloads remote content and pipes it directly into "
                    "a shell/interpreter — human review required.",
                    "bash_web_egress_pipe_to_shell",
                    "Download to a file, inspect it, then run it explicitly.",
                )
            # 2026-08-18: sink-host/opaque-blob reasoning
            # existed only inside the WebFetch gate — `curl https://webhook.site/x`
            # bypassed it entirely while `WebFetch https://webhook.site/x`
            # correctly denied. Extract every URL in the command and run it
            # through the same host-risk/opaque-blob checks.
            for _url in re.findall(r"https?://[^\s'\"]+", cmd):
                try:
                    _host = urllib.parse.urlparse(_url).hostname or ""
                except Exception:
                    _host = ""
                _risk = _host_egress_risk(_host)
                if _risk:
                    _kind, _token = _risk
                    if _kind in ("sink", "metadata"):
                        return self._deny(
                            tool, cmd,
                            f"Command sends data to '{_token}' — a known "
                            "exfiltration/metadata endpoint.",
                            "CRITICAL", f"bash_web_egress_sink_host:{_token}",
                            "Use the documented API host instead.",
                        )
                    return self._escalate(
                        tool, cmd[:80],
                        f"Command reaches private/loopback host '{_token}' — human review required.",
                        f"bash_web_egress_private_host:{_token}",
                        "Confirm this local/private-network target is intended.",
                    )
                _blob = _opaque_blob_hit(_url)
                if _blob:
                    return self._escalate(
                        tool, cmd[:80],
                        f"Command carries an opaque token ('{_blob[:32]}…') in "
                        "an outbound URL — possible encoded payload.",
                        "bash_web_egress_opaque_blob",
                        "Confirm this is not exfiltrated data before approving.",
                    )
            # Sink/metadata hosts named as a bare quoted string rather than a
            # URL — http.client.HTTPSConnection('webhook.site') and friends.
            # Only sink/metadata verdicts act here; private-host ESCALATE is
            # left to the URL sweep to avoid firing on ordinary quoted names.
            for _bare in _BASH_BARE_HOST_RE.findall(cmd):
                _risk = _host_egress_risk(_bare)
                if _risk and _risk[0] in ("sink", "metadata"):
                    return self._deny(
                        tool, cmd,
                        f"Command sends data to '{_risk[1]}' — a known "
                        "exfiltration/metadata endpoint.",
                        "CRITICAL", f"bash_web_egress_sink_host:{_risk[1]}",
                        "Use the documented API host instead.",
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
        """Credential gate for Read / Grep / Glob.

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
        """Egress gate for the URL- and query-carrying tools.

        WebFetch — the URL is the payload channel. Denied when it names a
            request-capture sink, a cloud metadata endpoint, a non-http scheme,
            embedded userinfo credentials, or carries a recognised secret shape.
            Escalated when it targets a private/loopback host or carries an
            opaque high-volume token — both are heuristics, so a human decides.
        WebSearch — no attacker-chosen destination exists, so only the secret
            shape is checked: a key pasted into a third-party search backend's
            logs is a disclosure even though nobody chose the recipient.
        Any other MCP search-shaped tool (a `query` key, no `url` key, no
            `sql`/`statement` key — e.g. mcp__exa__web_search_exa) is the
            same case as WebSearch: a third-party backend, no
            attacker-chosen destination. A `query` key accompanied by
            `sql`/`statement` is a DB call that happens to reuse the name
            "query" for its statement text, not a search — routing it
            through the secret-only check here would skip the
            CRITICAL/HIGH_RISK SQL pattern checks below. Excluding it here
            loses no coverage: the payload-wide MCP credential scan and the
            `_mcp_sql_text` extraction that feeds the CRITICAL/HIGH_RISK SQL
            pattern checks (both further down `evaluate()`) already read the
            same `sql`/`query`/`statement` keys regardless of which branch
            here runs.
        """
        if tool == "WebSearch" or (
            tool.startswith("mcp__")
            and inp.get("query")
            and not inp.get("url")
            and not (inp.get("sql") or inp.get("statement"))
        ):
            query = str(inp.get("query", "") or "")
            secret = _url_secret_hit(query)
            if secret:
                return self._deny(
                    tool,
                    query[:80],
                    f"Search blocked: query carries credential material ('{secret}').",
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
                f"{tool} blocked: URL could not be parsed for egress review.",
                "HIGH", "web_egress_unparseable",
                "Supply a plain https:// URL.",
            )

        scheme = (parsed.scheme or "").lower()
        if scheme and scheme not in _WEB_ALLOWED_SCHEMES:
            return self._deny(
                tool, url[:80],
                f"{tool} blocked: scheme '{scheme}' is not http/https.",
                "CRITICAL", f"web_egress_scheme:{scheme}",
                "Use Read for local files. This tool accepts http(s) URLs only.",
            )

        if parsed.username or parsed.password:
            return self._deny(
                tool, url[:80],
                f"{tool} blocked: URL embeds userinfo credentials (user:pass@host).",
                "CRITICAL", "web_egress_userinfo",
                "Fetch the public URL. Authenticated URLs are not supported here.",
            )

        secret = _url_secret_hit(raw)
        if secret:
            return self._deny(
                tool, url[:80],
                f"{tool} blocked: URL carries credential material ('{secret}') — "
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
                    f"{tool} blocked: '{token}' is a request-capture endpoint "
                    "whose only purpose is receiving exfiltrated data.",
                    "CRITICAL", f"web_egress_sink_host:{token}",
                    "Fetch the real documentation or API host instead.",
                )
            if kind == "metadata":
                return self._deny(
                    tool, url[:80],
                    f"{tool} blocked: '{token}' is a link-local/cloud-metadata "
                    "address (SSRF credential grab).",
                    "CRITICAL", f"web_egress_metadata_host:{token}",
                    "Instance metadata is never a legitimate research target.",
                )
            return self._escalate(
                tool, url[:80],
                f"{tool} to private/loopback host '{token}' — needs human review.",
                f"web_egress_private_host:{token}",
                "Local services are reached with Bash curl, not a fetch tool, so "
                "the request is visible in the transcript. Bash runs the full "
                "egress gate on that command — this does not bypass anything.",
            )

        blob = _opaque_blob_hit(raw)
        if blob:
            return self._escalate(
                tool, url[:80],
                f"{tool} carries an opaque {len(blob)}+ char token "
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
                # [F9/F10] Uses the same _blocked_path_hit/_governance_path_hit
                # matcher as every other path check below, instead of a second,
                # separate substring loop over BLOCKED_PATHS — one matcher
                # implementation, not two. This path was already realpath+
                # normpath'd above, which is what _path_match_candidates adds
                # over a plain substring check, so the change is SSOT/
                # maintainability only, not a security fix (no bypass here was
                # ever open that the old and new matcher disagree on).
                if not _blocked_path_hit(real_path) and not _governance_path_hit(real_path):
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

        # 3. Blocked / governance paths — EVERY tool that names a path.
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

        # Extract Bash command once for all Bash checks (3c, 4, 4b).
        # 2026-08-18: mcp__context-mode__ctx_execute* is an arbitrary
        # sandboxed-exec surface, allow-listed and actively steered to over
        # Bash by its own tool descriptions, that reached none of the Bash
        # checks below — treated as a Bash-equivalent here rather than left
        # ungated.
        if tool == "Bash":
            _bash_cmd = inp.get("command", "") or ""
        elif tool in _CTX_MODE_EXEC_TOOLS:
            _bash_cmd = _ctx_mode_command_text(tool, inp)
        else:
            _bash_cmd = ""

        # 3c. BLOCKED_PATHS enforcement for Bash
        if tool == "Bash" or tool in _CTX_MODE_EXEC_TOOLS:
            try:
                cmd = _bash_cmd
                _bash_block = self._bash_touches_blocked(cmd, tool)
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
        if tool in ("Read", "Grep", "Glob", "mcp__context-mode__ctx_execute_file", "Artifact"):
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

        # 3d'. Credential enforcement for MCP read-only tools (2026-08-18) — mcp__filesystem__read_text_file / read_multiple_files
        # etc. are exempt from the step-3 write check (you must be able to
        # read CLAUDE.md) but that exemption also skipped the credential
        # check entirely; _mcp_read_candidate_paths() covers every mcp__*
        # path-like argument regardless of read/write shape.
        if tool.startswith("mcp__"):
            try:
                for _mp in _mcp_read_candidate_paths(tool, inp):
                    _cred_block = self._read_touches_credential(tool, _mp)
                    if _cred_block:
                        return _cred_block
            except Exception as _mce:
                log.warning("permission_analyzer: MCP credential check failed: %s", _mce)
                return self._deny(
                    tool, str(detail)[:80],
                    "Internal analyzer error during MCP credential check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry, or ask the user to perform this call manually.",
                )

        # 3e. Egress enforcement for the web family. Same placement rule
        # as 3c/3d: BEFORE 4a (learned_approvals), so a repeatedly-attempted
        # exfiltration URL can never be auto-whitelisted past the gate.
        # Any MCP tool carrying a `url` is the same egress channel: `mcp__fetch`
        # is settings.json-allowed via the `mcp__*` glob AND is this system's
        # *documented default* fetcher (web-research-tools.md), so gating only
        # the built-in WebFetch would leave the primary path wide open.
        # `urls` (plural, e.g. firecrawl_batch_scrape) is checked
        # the same way — one item at a time — since the trigger condition
        # only ever looked at the singular `url`/`query` keys before.
        if tool in ("WebFetch", "WebSearch") or (
            tool.startswith("mcp__") and (inp.get("url") or inp.get("query") or inp.get("urls"))
        ):
            try:
                # Every URL the call carries, never one key in place of the
                # other (2026-08-18): `urls` as a bare string used to iterate
                # nothing useful, and a benign `url` alongside a malicious
                # `urls` list disabled the list scan entirely.
                _url_targets: list = []
                if inp.get("url"):
                    _url_targets.append(inp.get("url"))
                _urls_list = inp.get("urls")
                if isinstance(_urls_list, (list, tuple)):
                    _url_targets.extend(_urls_list)
                elif isinstance(_urls_list, str) and _urls_list:
                    _url_targets.append(_urls_list)
                _web_block = None
                if _url_targets:
                    for _u in _url_targets:
                        _web_block = self._web_egress_block(tool, {**inp, "url": str(_u or "")})
                        if _web_block:
                            break
                else:
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

        # 3f. Generic secret-in-payload catch-all for MCP tools (2026-08-18). mcp__claude_ai_Google_Drive__create_file/share_file
        # and any other MCP tool carrying free-form content have no url/
        # query/path key at all, so none of 3-3e ever inspect them. Last,
        # tool-agnostic line of defense: no recognised secret shape may
        # appear anywhere in a mcp__* call's arguments.
        if tool.startswith("mcp__"):
            try:
                _payload_text = json.dumps(inp, ensure_ascii=False, default=str)
            except Exception:
                _payload_text = str(inp)
            _secret = _url_secret_hit(_payload_text)
            if _secret:
                return self._deny(
                    tool, _payload_text[:80],
                    f"MCP call carries credential material ('{_secret}') in its arguments.",
                    "CRITICAL", f"mcp_payload_secret:{_secret}",
                    "Never pass a key/token as an MCP tool argument — read it via "
                    "os.environ.get() only where the code that needs it runs.",
                )

        # SQL text carried by any MCP tool (mcp__dqiii8-db__execute and
        # friends) is a Bash-equivalent surface for the CRITICAL/HIGH_RISK
        # pattern checks below (2026-08-18) — DROP TABLE/DROP
        # DATABASE/mass-DELETE previously reached the DB unchecked because
        # steps 4/4b only ever looked at Bash/ctx_execute text.
        if tool.startswith("mcp__"):
            _mcp_sql_text = " ".join(
                str(inp.get(k, "")) for k in ("sql", "query", "statement") if inp.get(k)
            )
        else:
            _mcp_sql_text = ""
        _pattern_scope = tool == "Bash" or tool in _CTX_MODE_EXEC_TOOLS or bool(_mcp_sql_text)

        # [S9a] Comment-stripped SQL text, checked in ADDITION to the raw cmd
        # below (never a replacement) — scoped to _mcp_sql_text or a
        # recognised DB-client Bash invocation's quoted arg only, so a
        # DROP/DELETE hidden behind a '--' or '/* */' comment still matches.
        _sql_comment_src = _mcp_sql_text or (
            _bash_db_client_sql_text(_bash_cmd) if tool == "Bash" and _bash_cmd else ""
        )
        _sql_decommented = _strip_sql_comments(_sql_comment_src) if _sql_comment_src else ""

        # [S5] ANSI-C-quoted ($'...') command text, decoded on the RAW Bash
        # command (before any quote-collapsing) — checked in ADDITION to cmd
        # below, same additive pattern as _sql_decommented, so a
        # $'\x72\x6d...'-hidden destructive command still matches.
        _ansi_c_decoded = (
            _ansi_c_decoded_cmd(_bash_cmd) if tool == "Bash" and _bash_cmd else None
        ) or ""

        # [S5] ANSI-C obfuscation — ESCALATE, not DENY: this is a heuristic
        # decode, not a direct match on visible command text, so it gets
        # human review rather than the CRITICAL/HIGH_RISK loops' automatic
        # DENY. Checked ahead of section 4 so an obfuscated destructive
        # command never reaches the ordinary approve path.
        if _ansi_c_decoded and _ansi_c_decoded != _bash_cmd:
            _ansi_hit = None
            if any(_t == "/" for _t in _rm_destructive_targets(_ansi_c_decoded)):
                _ansi_hit = "rm_rf_root"
            else:
                for _pattern in CRITICAL_PATTERNS:
                    if re.search(_pattern, _ansi_c_decoded, re.IGNORECASE):
                        _ansi_hit = _pattern
                        break
                if not _ansi_hit:
                    for _pattern, _rule in HIGH_RISK_PATTERNS:
                        if re.search(_pattern, _ansi_c_decoded, re.IGNORECASE):
                            _ansi_hit = _rule
                            break
            if _ansi_hit:
                return self._escalate(
                    tool, _bash_cmd[:80],
                    f"Command contains an ANSI-C quoted ($'...') span that "
                    f"decodes to a high-risk pattern ('{_ansi_hit}') — human "
                    "review required.",
                    f"bash_ansi_c_obfuscated:{_ansi_hit}",
                    "Confirm the decoded command's intent with the user "
                    "before approving.",
                )

        # [S5] Decoded-payload-piped-to-shell — base64/openssl/xxd/uudecode
        # decoding straight into sh/bash/python/perl/ruby with no
        # intermediate file, same risk shape as _PIPE_TO_SHELL_RE's
        # curl|wget case but for a locally-encoded payload. Independent of
        # the network-egress gate below: this never has to touch the
        # network. Documented residual risk (accepted, not a gap to
        # re-file): a two-step form — `base64 -d file.b64 > /tmp/x && sh
        # /tmp/x` — is architecturally outside a single-command regex's
        # reach; only the direct pipe form is covered.
        if tool == "Bash" and _bash_cmd and _OBFUSCATED_DECODE_PIPE_RE.search(_bash_cmd):
            return self._escalate(
                tool, _bash_cmd[:80],
                "Command decodes a base64/openssl/xxd/uudecode payload "
                "directly into a shell/interpreter — human review required.",
                "bash_obfuscated_decode_pipe_to_shell",
                "Decode to a file, inspect it, then run it explicitly.",
            )

        # 4. Always-CRITICAL commands (no mode exception, no ALLOWED_DELETIONS)
        if _pattern_scope:
            try:
                cmd = _bash_cmd or _mcp_sql_text
                # rm -rf / (and flag-order variants) targeting the exact root
                # filesystem — checked ahead of the regex list.
                for _tgt in _rm_destructive_targets(cmd):
                    if _tgt == "/":
                        return self._deny(
                            tool, cmd,
                            f"Catastrophic command blocked: recursive-force rm "
                            f"targeting root filesystem: '{cmd[:80]}'",
                            "CRITICAL", "critical_pattern:rm_rf_root",
                            "This command is irreversible and catastrophic.",
                        )
                for pattern in CRITICAL_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE) or (
                        _sql_decommented and re.search(pattern, _sql_decommented, re.IGNORECASE)
                    ):
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

        # 4b. High-risk commands with ALLOWED_DELETIONS exception
        if _pattern_scope:
            try:
                cmd = _bash_cmd or _mcp_sql_text
                # rm -rf /anything, ~, $HOME — flag-order/style agnostic
                # replacing the old literal HIGH_RISK_PATTERNS
                # entries.
                _rm_hits = _rm_destructive_targets(cmd)
                if _rm_hits and not self._rm_target_is_allowed(cmd):
                    if DQIII8_MODE == "autonomous":
                        return self._deny(
                            tool, cmd,
                            f"High-risk command in autonomous mode: {cmd[:80]}",
                            "HIGH", "high_risk_pattern:rm_rf",
                            "Use ALLOWED_DELETIONS or run in supervised mode.",
                        )
                    else:
                        return self._deny(
                            tool, cmd,
                            f"Blocked command: '{cmd[:80]}'",
                            "CRITICAL", "high_risk_pattern:rm_rf",
                            "This command is destructive and irreversible.",
                        )
                # [S4] git push --delete / :<ref> targeting a protected
                # branch — DENY even without --force, since the ordinary
                # git_push_force pattern deliberately treats --delete as
                # routine (it is, for a disposable feature branch).
                if tool == "Bash":
                    _del_ref = _git_push_deleted_ref(cmd)
                    if _del_ref and _is_protected_branch(_del_ref):
                        return self._deny(
                            tool, cmd,
                            f"git push deletes protected branch '{_del_ref}': '{cmd[:80]}'",
                            "CRITICAL", "high_risk_pattern:git_push_delete_protected_branch",
                            "Protected branches (main/master/production/release/"
                            "develop/trunk/staging/prod/premium-main/premium-full, "
                            "release/*, hotfix/*) cannot be deleted from a session.",
                        )
                # [S9b] VACUUM INTO copies the whole live DB to an arbitrary
                # destination — unconditional ESCALATE regardless of where it
                # lands (a copy outside the project is a data-exfil path even
                # to a destination that isn't itself BLOCKED/GOVERNANCE); a
                # blocked/governance destination still DENYs/ESCALATEs first
                # via the S9d check above (for Bash) or the MCP path check —
                # this is the residual case neither of those covers.
                for _vac_sql in (cmd, _sql_decommented):
                    if _vac_sql and _SQL_VACUUM_INTO_RE.search(_vac_sql):
                        return self._escalate(
                            tool, cmd[:80],
                            "VACUUM INTO copies the entire database to an "
                            "arbitrary destination — human confirmation required.",
                            "sql_vacuum_into_arbitrary_copy",
                            "Confirm the destination and purpose with the user "
                            "before running VACUUM INTO.",
                        )
                # Literal-vs-literal always-true DELETE predicate (`WHERE 2>1`).
                # Not expressible as a HIGH_RISK_PATTERNS regex — the truth of
                # the comparison has to be computed, see _sql_literal_tautology.
                _lit = _sql_literal_tautology(cmd) or (
                    _sql_decommented and _sql_literal_tautology(_sql_decommented)
                )
                if _lit:
                    return self._deny(
                        tool, cmd,
                        f"Unbounded DELETE on an audit table: predicate "
                        f"'{_lit}' is always true — '{cmd[:80]}'",
                        "CRITICAL", "high_risk_pattern:sql_literal_tautology",
                        "Bound the DELETE with a real predicate, or use "
                        "bin/core/action_log.py for legitimate writes.",
                    )
                for pattern, _rule in HIGH_RISK_PATTERNS:
                    if re.search(pattern, cmd, re.IGNORECASE) or (
                        _sql_decommented and re.search(pattern, _sql_decommented, re.IGNORECASE)
                    ):
                        if DQIII8_MODE == "autonomous":
                            return self._deny(
                                tool, cmd,
                                f"High-risk command in autonomous mode: {cmd[:80]}",
                                "HIGH", f"high_risk_pattern:{_rule}",
                                "Use ALLOWED_DELETIONS or run in supervised mode.",
                            )
                        else:
                            return self._deny(
                                tool, cmd,
                                f"Blocked command: '{cmd[:80]}'",
                                "CRITICAL", f"high_risk_pattern:{_rule}",
                                "This command is destructive and irreversible.",
                            )
            except Exception as _he:
                log.warning("permission_analyzer: HIGH_RISK pattern check failed: %s", _he)
                return self._deny(
                    tool, str(inp.get("command", ""))[:80],
                    "Internal analyzer error during high-risk check — denying as precaution.",
                    "HIGH", "analyzer_internal_error",
                    "Retry with a valid command string.",
                )

        # 4a. learned_approvals — only AFTER blocked-path + CRITICAL + HIGH_RISK
        # checks. A historically-safe pattern can never override
        # any of those denies, even latently.
        if self._is_learned_safe(tool, detail):
            return self._approve(
                "Pattern approved by history", "LOW", "learned_approval"
            )

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
            # Fail CLOSED, same contract as block 4b: a check that ran and
            # errored is not a check that passed. Returning None here made the
            # multi-agent write lock silently cease to exist whenever the DB was
            # locked/missing/corrupt.
            log.warning("permission_analyzer: _check_resource_claim query failed: %s", e, exc_info=True)
            return self._deny(
                tool, path,
                "Internal analyzer error during resource-claim check — denying as precaution.",
                "HIGH", "analyzer_internal_error",
                "Retry once the permissions DB is reachable.",
            )
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
            # Fail CLOSED. The budget gate is a DENY row in the decision table of
            # 02_hooks_and_permissions.md with its own DENIAL_HINTS key; returning
            # None on error deleted that gate whenever SQLite was locked/missing/
            # corrupt, which is not a theoretical state under a concurrent writer.
            log.warning("permission_analyzer: _check_budget query failed: %s", e, exc_info=True)
            return self._deny(
                "budget", session_id,
                "Internal analyzer error during budget check — denying as precaution.",
                "HIGH", "analyzer_internal_error",
                "Retry once the permissions DB is reachable.",
            )
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


def record_rejection(tool: str, inp: dict, result: dict, session_id: str | None = None) -> None:
    """
    Records DENY and ESCALATE in two channels:
    Channel 1 — DB: permission_decisions table
    Channel 2 — JSON mailbox: tasks/permission_rejection.json (read by OrchestratorLoop)

    session_id: defaults to the module-level SESSION_ID constant, which is
    only ever set from CLAUDE_SESSION_ID — a variable never populated
    anywhere in settings.json's env, so every row this function writes
    without an explicit session_id lands under session_id='unknown'. That
    silently breaks _check_repeat_rejections()'s loop-breaker, which filters
    `WHERE session_id = ?` using the REAL per-invocation session id passed
    into evaluate(). Callers (pre_tool_use.py) already have that real id —
    pass it through instead of relying on the broken env-var fallback.
    """
    if result["decision"] not in ("DENY", "ESCALATE"):
        return

    _session = session_id or SESSION_ID
    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": _session,
        "tool_name": tool,
        # url/query included so a blocked egress attempt reaches the operator
        # with the actual destination instead of an empty string. Deliberately
        # NOT mirrored into record_decision(): that path feeds learned_approvals,
        # and approved research URLs must not accumulate as auto-approve rules.
        # `path`/`sql` are included because MCP filesystem and DB tools carry their
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
                _session,
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
