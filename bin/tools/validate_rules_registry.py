#!/usr/bin/env python3
"""Validate the rules/routing governance surface: registry, token budget, agent
names and model slugs.

Manual doc-governance remediation kept finding the same shape of bug: a *silent*
drift between a declaration in code and a statement in a rule file, discoverable
only by a human reading both sides at once. This script turns the highest-
frequency drifts into mechanical pre-commit checks so they cannot come back:

  1. check_registry_reachability()  — no orphan/dangling `_REGISTRY` alias.
     (`routing`, `performance`, `git-workflow`, `workflow`, `testing` were all
     registered-but-unreachable; two of them also redefined canonical taxonomy.)
  2. check_token_budget()           — the dispatcher docstring, DYNAMIC.md and
     02_hooks_and_permissions.md (x2) must quote ONE range. It went stale twice
     on 2026-08-17 alone, which is exactly what a mechanical check is for.
  3. check_agent_names_exist()      — an agent cited in a routing table must
     exist in `AGENT_ROUTING` or as a `.claude/agents/*.md` file.
  4. check_model_slugs_match_code() — a model slug a rule file presents as
     configured must actually appear in the wrapper's routing tables. A doc
     fix can be written while the matching code fix never lands, and nothing
     else notices.
  5. check_command_skill_parity()   — `.claude/commands/<name>.md` and
     `.claude/skills/<name>/SKILL.md` must not be two forked copies of the same
     slash command. `handover` had drifted into two *different* procedures, one
     of which pushed to `master` unattended.
  6. check_constant_lists_match_prose() — a rule file's inline restatement of a
     code constant (e.g. `BLOCKED_PATHS`) must match the constant exactly; the
     alternative is a doc that lies about what the code actually blocks.

Contract, cloned from bin/tools/validate_hooks_config.py:
  * `--staged` (used by .git/hooks/pre-commit) reads content from the git index
    via `git show :path`, so it validates what is about to be committed rather
    than whatever is sitting in the worktree.
  * Default (direct CLI run, humans, CI) reads the worktree — the live files are
    what the hook runtime actually loads.
  * Every check returns a `(problems, warnings)` tuple; exit 1 on `problems`
    only. Warnings are printed and ignored, so a heuristic false positive can
    never block a commit.

Usage:
    python3 bin/tools/validate_rules_registry.py [--staged] [--root PATH]
Exit: 0 = clean, 1 = problems found, 2 = bad invocation.
"""

from __future__ import annotations

import ast
import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))

import rules_registry_introspect as intro  # noqa: E402

DISPATCHER = ".claude/hooks/rules_dispatcher.py"
WRAPPER = "bin/core/openrouter_wrapper.py"
DYNAMIC_MD = ".claude/rules/DYNAMIC.md"
HOOKS_PERMS_MD = ".claude/rules/02_hooks_and_permissions.md"
CORE_BEHAVIOR_MD = ".claude/rules/00_core_behavior.md"
TIERING_MD = ".claude/rules/03_tiering_and_routing.md"
_ARCHIVE_MD = ".claude/rules_db/archive/multi-tier-dormant-2026-08.md"
_BARE_ANTHROPIC_SLUG = re.compile(r"`(claude-[A-Za-z0-9_.\-]+)`")
AGENTS_DIR = ".claude/agents"

# `.claude/architecture/` is a vendored third-party book about Claude Code's own
# internals (ch01..ch10+). Its tables describe Anthropic's built-in agents
# ("General-Purpose", "Explore", "Plan"), not DQIII8's roster, so scanning it for
# DQIII8 agent names would be pure noise. Governance scope is DQIII8's own
# surface: rules/, rules_db/, skills/, commands/, agents/.
MD_SCAN_EXCLUDE = (".claude/architecture/",)


class Source:
    """Reads repo files either from the git index (staged) or the worktree."""

    def __init__(self, root: Path = ROOT, staged: bool = False) -> None:
        self.root = Path(root).resolve()
        self.staged = staged

    def read(self, rel: str) -> str | None:
        """Return file content, or None if the path does not exist.

        In staged mode, a path absent from the index (new untracked file, or a
        deletion staged for commit) falls back to the worktree, then to None —
        same fallback ladder as validate_hooks_config.py.
        """
        if self.staged:
            result = subprocess.run(
                ["git", "show", f":{rel}"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout
        path = self.root / rel
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None

    def list_md(self, subdir: str) -> list[str]:
        """Repo-relative markdown paths under `subdir`, excluding vendored docs.

        Staged mode enumerates the index (`git ls-files`) rather than only the
        files in this commit: a validator that inspects only changed files
        cannot catch drift that a *different* commit introduced elsewhere, which
        is precisely the class of bug Phase 1 spent a day cleaning up.
        """
        if self.staged:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--", f"{subdir}/**/*.md", f"{subdir}/*.md"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=15,
            )
            names = result.stdout.split() if result.returncode == 0 else []
        else:
            base = self.root / subdir
            names = [
                str(p.relative_to(self.root)) for p in base.rglob("*.md") if p.is_file()
            ]
        return sorted(
            n for n in names if not any(n.startswith(x) for x in MD_SCAN_EXCLUDE)
        )

    def list_governance_md(self) -> list[str]:
        """Every markdown file in governance scope: `.claude/**` plus the
        repo-root `CLAUDE.md` — `list_md(".claude")` alone always missed the
        apex always-loaded file, so its own stale counts and any model slug or
        agent name it cites went unchecked."""
        paths = self.list_md(".claude")
        root_claude = self.root / "CLAUDE.md"
        has_root_claude = (
            self._staged_file_exists("CLAUDE.md") if self.staged else root_claude.is_file()
        )
        if has_root_claude:
            paths = sorted(paths + ["CLAUDE.md"])
        return paths

    def _staged_file_exists(self, rel: str) -> bool:
        result = subprocess.run(
            ["git", "cat-file", "-e", f":{rel}"],
            cwd=self.root,
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0

    def list_agent_stems(self) -> set[str]:
        if self.staged:
            result = subprocess.run(
                ["git", "ls-files", "--cached", "--", f"{AGENTS_DIR}/*.md"],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=15,
            )
            names = result.stdout.split() if result.returncode == 0 else []
        else:
            base = self.root / AGENTS_DIR
            names = (
                [str(p.relative_to(self.root)) for p in base.glob("*.md")]
                if base.is_dir()
                else []
            )
        return {Path(n).stem for n in names}


# ── shared parsing helpers ───────────────────────────────────────────────────


def _literal_assignments(source: str, names: set[str]) -> dict[str, object]:
    """Statically evaluate module-level literal assignments by name.

    AST + literal_eval rather than importing: openrouter_wrapper.py reads .env,
    configures logging and inserts into sys.path at import time. A pre-commit
    gate must not do any of that, least of all against *staged* source.
    """
    out: dict[str, object] = {}
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    pass
    return out


def _num(raw: str) -> int | None:
    """'1.432' / '1,432' / '1432' -> 1432. Thousands separators only."""
    cleaned = raw.replace(".", "").replace(",", "").replace("\u202f", "").strip()
    return int(cleaned) if cleaned.isdigit() else None


_FENCE = re.compile(r"^\s*(```|~~~)")


def _md_tables(text: str):
    """Yield (header_cells, [body_row_cells...]) for every GFM table.

    A table is a `|---|---|` separator line, its preceding line as header, and
    every following pipe-line until the block ends.

    Lines inside fenced code blocks (``` or ~~~) are skipped — a pipe-table
    shown as a literal example inside a fence (illustrative output format,
    vendored snippet) is not a declarative citation, and scanning it produces
    false positives no author intended as a real agent-name citation.
    """
    lines = text.splitlines()
    sep = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")
    in_fence = [False] * len(lines)
    fenced = False
    for idx, line in enumerate(lines):
        if _FENCE.match(line):
            fenced = not fenced
            in_fence[idx] = True  # the fence marker line itself is never a table line
            continue
        in_fence[idx] = fenced

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    i = 1
    while i < len(lines):
        line = lines[i]
        if (
            not in_fence[i]
            and not in_fence[i - 1]
            and "|" in line
            and "-" in line
            and sep.match(line)
            and "|" in lines[i - 1]
        ):
            header = cells(lines[i - 1])
            body: list[list[str]] = []
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                body.append(cells(lines[j]))
                j += 1
            yield header, body
            i = j
        else:
            i += 1


def _clean_cell(cell: str) -> str:
    return cell.strip().strip("*").strip("`").strip("*").strip()


# ── check 1: registry reachability ───────────────────────────────────────────


def check_registry_reachability(src: Source) -> tuple[list[str], list[str]]:
    """Every `_REGISTRY` alias must be reachable, and every mapping must point
    at a registered alias.

    Reachability logic is imported from .claude/hooks/rules_registry_introspect.py
    — the SAME module tests/test_rules_dispatcher.py uses. It must not be
    reimplemented here as a four-table union: the fifth source (hardcoded path
    substrings inside get_rules()) would false-positive `hooks-perms`, `tiering`
    and `db-mutations` as orphans.
    """
    problems: list[str] = []
    warnings: list[str] = []

    source = src.read(DISPATCHER)
    if source is None:
        return [f"cannot read {DISPATCHER}"], warnings

    try:
        module = intro.load_dispatcher(source, name="rules_dispatcher_validated")
    except Exception as exc:  # syntax error, bad table literal, import failure
        return [f"{DISPATCHER} is not loadable: {exc.__class__.__name__}: {exc}"], warnings

    orphans = intro.orphan_aliases(module, source)
    if orphans:
        problems.append(
            f"{DISPATCHER}: orphaned _REGISTRY alias(es) {sorted(orphans)} — "
            "registered but unreachable from _ALWAYS/_TOOL_RULES/"
            "_BASH_KEYWORD_RULES/_EXT_RULES or any get_rules() path branch. "
            "Wire it to a trigger or delete the alias + its file."
        )

    dangling = intro.dangling_aliases(module, source)
    if dangling:
        problems.append(
            f"{DISPATCHER}: mapping tables reference unregistered alias(es) "
            f"{sorted(dangling)} — get_rules() drops these silently at runtime."
        )

    # Each alias must also resolve to a file that exists. Worktree-only: the
    # index has no directory semantics for a relative "../rules/x.md" walk, and
    # a rule file deleted-but-still-registered shows up as an orphan anyway.
    rules_db = src.root / ".claude" / "rules_db"
    missing = {
        alias: str((rules_db / rel).resolve())
        for alias, rel in module._REGISTRY.items()
        if not (rules_db / rel).is_file()
    }
    if missing:
        problems.append(f"{DISPATCHER}: _REGISTRY aliases with missing files: {missing}")

    return problems, warnings


# ── check 2: token budget ────────────────────────────────────────────────────

# "suelo de sesión N" is matched FIRST and its span removed, so the generic
# `suelo` pattern below can never mistake the session number for the dispatcher
# floor (the two are deliberately different quantities).
_SESSION_FLOOR = re.compile(r"suelo\s+de\s+sesi[oó]n\s+\*{0,2}([\d.,]+)", re.IGNORECASE)
_CANON_FLOOR = re.compile(r"suelo\s+(?:de\s+)?\*{0,2}([\d.,]+)", re.IGNORECASE)
_CANON_CEIL = re.compile(r"techo\s+(?:de\s+)?\*{0,2}([\d.,]+)", re.IGNORECASE)
_RANGE = re.compile(r"([\d][\d.,]*)\s*[-–—]\s*([\d][\d.,]*)\s*tokens")


def _canonical_range(dispatcher_src: str) -> tuple[int, int] | None:
    """The ONE canonical range, taken from the rules_dispatcher docstring."""
    doc = ast.get_docstring(ast.parse(dispatcher_src)) or ""
    floors = [_num(m) for m in _CANON_FLOOR.findall(_SESSION_FLOOR.sub(" ", doc))]
    ceils = [_num(m) for m in _CANON_CEIL.findall(doc)]
    floors = [f for f in floors if f]
    ceils = [c for c in ceils if c]
    if not floors or not ceils:
        return None
    return floors[0], ceils[0]


def _canonical_session_floor(dispatcher_src: str) -> int | None:
    """The published per-session floor (dispatcher floor + the two auto-injected
    files), or None if the docstring does not publish one."""
    doc = ast.get_docstring(ast.parse(dispatcher_src)) or ""
    values = [v for v in (_num(m) for m in _SESSION_FLOOR.findall(doc)) if v]
    return values[0] if values else None


def check_token_budget(src: Source) -> tuple[list[str], list[str]]:
    """The dispatcher docstring is the single source for the measured token
    range; DYNAMIC.md must quote it verbatim, and
    02_hooks_and_permissions.md must not quote it at all.

    Places stating this number drifted twice on 2026-08-17 alone, and again on
    2026-08-18 — that last time in BOTH directions while this check still
    printed "consistent", because it only cross-checked prose against prose.
    It now also MEASURES, holding BOTH bounds to exact equality: the real floor,
    the maximum reachable injection (derived from the dispatcher's own tables,
    not from a hand-written probe), and the per-session floor that includes the
    two files Claude Code auto-injects. Measurement reads the worktree even under
    --staged: token_estimate() needs real files on disk.
    """
    problems: list[str] = []
    warnings: list[str] = []

    dispatcher_src = src.read(DISPATCHER)
    if dispatcher_src is None:
        return [f"cannot read {DISPATCHER}"], warnings

    canon = _canonical_range(dispatcher_src)
    if canon is None:
        return (
            [
                f"{DISPATCHER}: cannot locate the canonical token range in the "
                "module docstring (expected 'suelo N' and 'techo N')."
            ],
            warnings,
        )
    floor, ceiling = canon
    session_floor = _canonical_session_floor(dispatcher_src)
    if session_floor is None:
        problems.append(
            f"{DISPATCHER}: the docstring publishes 'suelo {floor}' (dispatcher-only) "
            "but no 'suelo de sesión N'. CLAUDE.md and DYNAMIC.md are auto-injected "
            "into every session and nothing else measures them, so the dispatcher "
            "floor alone reads as a ~2.6x understatement of the real context tax "
            "(C8, 2026-08-18). Publish both."
        )

    # The docstring also restates the range in rounded prose ("~1.430-4.470
    # tokens"). Rounding to the nearest 10 is legitimate; anything further off
    # is drift, but only a warning — the suelo/techo markers are authoritative.
    for raw_lo, raw_hi in _RANGE.findall(dispatcher_src):
        lo, hi = _num(raw_lo), _num(raw_hi)
        if lo is None or hi is None:
            continue
        if abs(lo - floor) > 10 or abs(hi - ceiling) > 10:
            warnings.append(
                f"{DISPATCHER}: prose range {raw_lo}-{raw_hi} is not a rounding "
                f"of the canonical {floor}-{ceiling}."
            )

    # DYNAMIC.md: >=1 occurrence, and it must match the canonical range.
    for rel, expected_min in ((DYNAMIC_MD, 1),):
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        found = _RANGE.findall(text)
        if len(found) < expected_min:
            problems.append(
                f"{rel}: expected at least {expected_min} citation(s) of the "
                f"token range '{floor}-{ceiling}', found {len(found)}. The two "
                "sites that quote this number must be updated together."
            )
        for raw_lo, raw_hi in found:
            lo, hi = _num(raw_lo), _num(raw_hi)
            if (lo, hi) != (floor, ceiling):
                problems.append(
                    f"{rel}: token range '{raw_lo}-{raw_hi}' disagrees with the "
                    f"canonical '{floor}-{ceiling}' in {DISPATCHER}'s docstring."
                )
        # Prose restatements of any published bound ("el suelo de 1.432 es ...").
        # The session floor is stripped before the generic `suelo` sweep so the
        # two numbers cannot be confused for each other.
        for pattern, expected, label, scan in (
            (_SESSION_FLOOR, session_floor, "suelo de sesión", text),
            (_CANON_FLOOR, floor, "suelo", _SESSION_FLOOR.sub(" ", text)),
            (_CANON_CEIL, ceiling, "techo", text),
        ):
            if expected is None:
                continue
            for raw in pattern.findall(scan):
                value = _num(raw)
                if value is not None and value != expected:
                    problems.append(
                        f"{rel}: {label} stated as {raw} but the canonical "
                        f"{label} is {expected}."
                    )

    # 02_hooks_and_permissions.md is itself injected and itself counts toward
    # the ceiling it used to describe. It must point at the docstring, never
    # restate the numbers — a third citation site is a third thing to drift.
    hp_text = src.read(HOOKS_PERMS_MD)
    if hp_text is None:
        problems.append(f"cannot read {HOOKS_PERMS_MD}")
    else:
        stray = _RANGE.findall(hp_text) + _CANON_FLOOR.findall(hp_text) + _CANON_CEIL.findall(hp_text)
        if stray:
            problems.append(
                f"{HOOKS_PERMS_MD}: must NOT restate the token range "
                f"(found {stray!r}) — point at {DISPATCHER}'s docstring instead."
            )

    problems.extend(_measured_range_problems(src, floor, ceiling, session_floor))
    return problems, warnings


# Concrete probes kept as an *achievability* cross-check on the analytic maximum
# below: a hand-written probe proves the alias set the tables allow is actually
# producible by a real tool call. They are no longer the source of the ceiling —
# a hand-written probe can only ever under-measure once a new trigger is added
# (which is exactly how 7751 stayed published while reality was 7681).
_CEILING_PROBES = (
    (
        "Bash",
        {
            "command": "git python3 sqlite3 schema_v2 systemctl claude agent "
            "orchestrator tmux intl-reports firecrawl"
        },
        "bash-all-keywords",
    ),
    (
        "Edit",
        {
            "file_path": "/root/dqiii8/database/.claude/hooks/"
            "openrouter_wrapper_domain_agent.py"
        },
        "edit-hooks-tiering-db-py",
    ),
)

# Path substrings inside get_rules()'s Edit/Write branch. Not a table in the
# dispatcher, so it is mirrored here; check_registry_reachability() already
# fails if any of these stops being a real alias.
_EDIT_PATH_BRANCH_ALIASES = ("hooks-perms", "tiering", "db-mutations")


def _render_injection(rd, aliases) -> str:
    """Rebuild get_rules()'s output block for an arbitrary alias list.

    Mirrors get_rules()'s dedupe-then-join, so the token cost of a *derived*
    alias set is measured exactly the way the runtime would emit it.
    """
    seen: set[str] = set()
    parts = ["[DQIII8 Rules — context-specific]"]
    for alias in aliases:
        if alias in seen or alias not in rd._REGISTRY:
            continue
        seen.add(alias)
        content = rd._read(alias)
        if content:
            parts.append(content)
    return "\n\n".join(parts) if len(parts) > 1 else ""


def _reachable_alias_sets(rd) -> list[tuple[str, list[str]]]:
    """Every alias set get_rules() can emit, DERIVED FROM THE DISPATCHER TABLES.

    Exhaustive by construction for the three declarative tables: a new
    `_BASH_KEYWORD_RULES` row, `_EXT_RULES` extension or `_TOOL_RULES` entry
    enters the ceiling automatically. The prior hand-written probe string could
    not do this — it hit every alias group only by coincidence, so any added
    trigger would have silently under-measured the ceiling forever.

    One exception, NOT exhaustive by construction: get_rules()'s Edit/Write
    path-substring branches (`.claude/hooks`, `openrouter_wrapper`/`director.py`/
    `domain_agent`, `database/`) live as inline `if` statements in the AST, not
    a table — this function mirrors them by hand in `_EDIT_PATH_BRANCH_ALIASES`.
    A new path-substring branch added to get_rules() needs a matching manual
    update here too, or the ceiling silently under-measures again.
    """
    always = list(rd._ALWAYS)
    sets: list[tuple[str, list[str]]] = [("floor:_ALWAYS-only", always)]

    # Bash: every keyword row can fire in a single command (they are OR-ed, not
    # exclusive), so their union is genuinely reachable.
    bash = always + list(rd._TOOL_RULES.get("Bash", []))
    for _pattern, rule_list in rd._BASH_KEYWORD_RULES:
        bash.extend(rule_list)
    sets.append(("Bash:all-keywords", bash))

    # Edit/Write: exactly one extension per call, but every path-substring
    # branch can co-fire with it (".claude/hooks" + "domain_agent" + "database/"
    # in one path).
    for ext, rule_list in rd._EXT_RULES.items():
        sets.append(
            (f"Edit:{ext}+path-branches", always + rule_list + list(_EDIT_PATH_BRANCH_ALIASES))
        )
    sets.append(("Edit:no-ext+path-branches", always + list(_EDIT_PATH_BRANCH_ALIASES)))

    for tool, rule_list in rd._TOOL_RULES.items():
        if tool in ("Bash", "Edit", "Write"):
            continue
        sets.append((f"{tool}", always + rule_list))
    return sets


def _measured_ceiling(rd) -> tuple[int, str]:
    """(max reachable injection tokens, label of the path that reaches it)."""
    best = (0, "none")
    for label, aliases in _reachable_alias_sets(rd):
        tokens = rd.token_estimate(_render_injection(rd, aliases))
        if tokens > best[0]:
            best = (tokens, label)
    return best


def _session_floor(rd, root: Path) -> int | None:
    """Dispatcher floor + the two files Claude Code auto-injects every session.

    `CLAUDE.md` and `.claude/rules/DYNAMIC.md` are outside rules_dispatcher's
    control and nothing measured them before (C8, 2026-08-18), so the published
    946 read as "minimum context tax per session" while the real figure was
    ~2.6x that. Measuring them here means they cannot grow unobserved either.
    """
    total = rd.token_estimate(rd.get_rules("Glob", {}))
    for rel in ("CLAUDE.md", DYNAMIC_MD):
        try:
            total += rd.token_estimate((root / rel).read_text(encoding="utf-8").strip())
        except OSError:
            return None
    return total


def _measured_range_problems(
    src: Source, floor: int, ceiling: int, session_floor: int | None
) -> list[str]:
    """Measure the live corpus and hold the published numbers to it.

    Both bounds are held to EXACT equality. The ceiling check used to be
    one-sided (`measured > ceiling`), which let a stale-*high* ceiling — an
    inflated budget claim that is simply false — pass silently forever; that is
    exactly what happened on the commit that published 7751 against a real 7681
    (C1, 2026-08-18). An over-published ceiling is as much a lie about the system
    as an under-published one, so drift in either direction now fails.

    rules_dispatcher resolves its rule files from DQIII8_ROOT on disk, so this
    can only measure the real repo. Synthetic fixture repos (unit tests) get
    skipped rather than silently measured against the wrong tree.
    """
    problems: list[str] = []
    if src.root.resolve() != ROOT.resolve():
        return problems
    try:
        import rules_dispatcher as rd  # noqa: PLC0415 — optional, fail-open below
    except Exception as exc:
        return [f"cannot import rules_dispatcher to measure the token range: {exc}"]

    measured_floor = rd.token_estimate(rd.get_rules("Glob", {}))
    if measured_floor != floor:
        problems.append(
            f"{DISPATCHER}: docstring floor is {floor} but the measured "
            f"_ALWAYS-only injection is {measured_floor}. Re-measure and update "
            f"the docstring and {DYNAMIC_MD} together."
        )

    measured_ceiling, label = _measured_ceiling(rd)
    if measured_ceiling != ceiling:
        direction = "stale-high (an inflated budget claim)" if measured_ceiling < ceiling else "exceeded"
        problems.append(
            f"{DISPATCHER}: docstring ceiling is {ceiling} but the maximum "
            f"reachable injection ('{label}') measures {measured_ceiling} — "
            f"{direction}. Re-publish the ceiling in the docstring and "
            f"{DYNAMIC_MD} together, AFTER the last edit to any injected file."
        )

    # Achievability: the analytic maximum must be producible by a real tool call.
    for tool, tool_input, probe_label in _CEILING_PROBES:
        measured = rd.token_estimate(rd.get_rules(tool, tool_input))
        if measured > measured_ceiling:
            problems.append(
                f"{DISPATCHER}: concrete probe '{probe_label}' measures {measured}, "
                f"above the analytic maximum {measured_ceiling} — _reachable_alias_sets() "
                "is missing a branch that get_rules() can actually take."
            )

    if session_floor is not None:
        measured_session = _session_floor(rd, src.root)
        if measured_session is None:
            problems.append(
                f"{DISPATCHER}: cannot measure the session floor (CLAUDE.md or "
                f"{DYNAMIC_MD} unreadable)."
            )
        elif measured_session != session_floor:
            problems.append(
                f"{DISPATCHER}: published session floor is {session_floor} but "
                f"dispatcher floor + CLAUDE.md + {DYNAMIC_MD} measures "
                f"{measured_session}. Re-measure and update the docstring and "
                f"{DYNAMIC_MD} together."
            )
    return problems


# ── check 3: agent names ─────────────────────────────────────────────────────

_AGENT_COL = {"agent", "agente", "agent name", "nombre de agente"}
_NAME_SHAPE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def _agent_ssot(src: Source) -> set[str]:
    """SSOT = AGENT_ROUTING keys UNION `.claude/agents/*.md` stems.

    Two distinct runtimes, two distinct registries (see
    .claude/rules_db/common/agents.md): the wrapper dispatch table and Claude
    Code's own agent files. A name valid in either one is a valid citation.
    """
    names = set(src.list_agent_stems())
    wrapper = src.read(WRAPPER)
    if wrapper:
        routing = _literal_assignments(wrapper, {"AGENT_ROUTING"}).get("AGENT_ROUTING")
        if isinstance(routing, dict):
            names.update(routing)
    return names


_BACKTICKED_SLUG = re.compile(r"`[^`\s]*/[^`]*`")
_FILENAME = re.compile(r"[\w./\-]+\.(?:md|py|json|sh|sql|toml|ya?ml|txt|db)\b")


def _prose_text(text: str) -> str:
    """Strip the two constructs that dominate agent-name false positives.

    Model slugs in code spans (`nvidia/llama-3.1-nemoguard-8b-content-safety`)
    and filenames (`git-safety.md`) both end in tokens shaped exactly like an
    agent name. Neither is ever a citation of an agent, so remove them before
    the free-prose sweep rather than emitting a warning nobody can act on.
    """
    return _FILENAME.sub(" ", _BACKTICKED_SLUG.sub(" ", text))


def check_agent_names_exist(src: Source) -> tuple[list[str], list[str]]:
    """Agent names cited in a table column headed "Agent"/"Agente" must exist.

    Table rows are the hard gate because they are the *declarative* citations —
    a routing table row claims "this agent exists and is dispatchable". Free
    prose is far noisier (hypotheticals, deleted-agent post-mortems, examples in
    other people's vendored docs), so a prose mention of an unknown name is a
    warning only.
    """
    problems: list[str] = []
    warnings: list[str] = []

    ssot = _agent_ssot(src)
    if not ssot:
        return ["cannot build the agent-name SSOT (no AGENT_ROUTING, no agents/*.md)"], warnings

    # Prose detection is restricted to the compound shape `<something>-<suffix>`
    # where <suffix> is a suffix that real DQIII8 agents use. Scanning for every
    # hyphenated token would flag `pre-commit`, `rules-db`, `spec-kit`, ... .
    suffixes = {n.rsplit("-", 1)[-1] for n in ssot if "-" in n}
    prose_shape = (
        re.compile(r"\b([a-z][a-z0-9]*(?:-[a-z0-9]+)*-(?:" + "|".join(sorted(suffixes)) + r"))\b")
        if suffixes
        else None
    )

    for rel in src.list_governance_md():
        text = src.read(rel)
        if text is None:
            continue

        table_cited: set[str] = set()
        for header, body in _md_tables(text):
            cols = [i for i, h in enumerate(header) if _clean_cell(h).lower() in _AGENT_COL]
            if not cols:
                continue
            for row in body:
                for i in cols:
                    if i >= len(row):
                        continue
                    name = _clean_cell(row[i])
                    # Placeholders (`[name]`, `{agent}`, `—`, `...`) are template
                    # slots in output-format examples, not citations.
                    if not name or not _NAME_SHAPE.match(name):
                        continue
                    table_cited.add(name)

        for name in sorted(table_cited - ssot):
            problems.append(
                f"{rel}: table row cites agent '{name}', which is in neither "
                f"AGENT_ROUTING ({WRAPPER}) nor {AGENTS_DIR}/{name}.md."
            )

        if prose_shape is not None:
            prose_only = {
                m
                for m in prose_shape.findall(_prose_text(text))
                if m not in ssot and m not in table_cited
            }
            for name in sorted(prose_only):
                warnings.append(
                    f"{rel}: free-text mention of agent-shaped name '{name}' not "
                    "in the SSOT (prose is warn-only; a table row would fail)."
                )

    return problems, warnings


# ── check 4: model slugs ─────────────────────────────────────────────────────

# Only backticked code spans: a slug is a configuration value, and every rule
# file in this repo already writes them as `provider/model`. Bare prose is not
# scanned — the false-positive rate on "and/or", dates and paths is far too high.
_SLUG = re.compile(r"`([A-Za-z0-9][A-Za-z0-9_.\-]*/[A-Za-z0-9][A-Za-z0-9_.\-]*(?::[A-Za-z0-9_.\-]+)?)`")
_PATHISH_SUFFIX = (
    ".py", ".md", ".json", ".sh", ".sql", ".toml", ".yaml", ".yml", ".txt", ".db",
    ".flag", ".conf",
)
# Lines that explicitly document a slug as dead/wrong are citing it in order to
# warn about it. Requiring such a slug to exist in code would be backwards.
_NEGATION = re.compile(
    r"retirad|deprecad|\bEOL\b|\b40[0-9]\b|\b410\b|no intentar|incorrect|obsolet|"
    r"ya no\b|fuera de la cadena|Insufficient",
    re.IGNORECASE,
)
# A table listing what a *provider* offers is an availability inventory, not a
# claim about DQIII8's own routing. Detected by its header, not by line number.
_INVENTORY_HEADER = {"categoría", "categoria", "modelos confirmados", "category"}


def _code_slugs(src: Source) -> tuple[set[str], set[str], list[str]]:
    """(model slugs, provider names, problems) from openrouter_wrapper.py."""
    wrapper = src.read(WRAPPER)
    if wrapper is None:
        return set(), set(), [f"cannot read {WRAPPER}"]
    tables = _literal_assignments(
        wrapper, {"AGENT_ROUTING", "_PROVIDER_DEFAULT_MODEL", "FALLBACK_CHAIN", "PROVIDERS"}
    )
    models: set[str] = set()
    routing = tables.get("AGENT_ROUTING")
    if isinstance(routing, dict):
        for value in routing.values():
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                # AGENT_ROUTING stores (provider, model) tuples, but docs cite
                # the slash-joined form ("groq/llama-3.3-70b-versatile") — only
                # indexing the bare model id made every such doc citation a
                # false-positive "not in code" problem once the scan widened
                # to rules_db/skills and actually hit one (2026-08-18).
                models.add(value[1])
                models.add(f"{value[0]}/{value[1]}")
    defaults = tables.get("_PROVIDER_DEFAULT_MODEL")
    if isinstance(defaults, dict):
        models.update(str(v) for v in defaults.values())

    providers: set[str] = set()
    chain = tables.get("FALLBACK_CHAIN")
    if isinstance(chain, dict):
        providers.update(chain)
        for dests in chain.values():
            providers.update(dests)
    if isinstance(tables.get("PROVIDERS"), dict):
        providers.update(tables["PROVIDERS"])

    problems = []
    if not models:
        problems.append(f"{WRAPPER}: could not extract any model slug (parse failure?)")
    return models, providers, problems


def _inventory_line_numbers(text: str) -> set[int]:
    """1-based line numbers belonging to provider-inventory tables."""
    out: set[int] = set()
    lines = text.splitlines()
    for header, body in _md_tables(text):
        if not any(_clean_cell(h).lower() in _INVENTORY_HEADER for h in header):
            continue
        # Re-locate the rows: _md_tables is content-based, so match on the row text.
        wanted = {"|".join(r) for r in body}
        for n, line in enumerate(lines, 1):
            if "|" not in line:
                continue
            key = "|".join(c.strip() for c in line.strip().strip("|").split("|"))
            if key in wanted:
                out.add(n)
    return out


def check_model_slugs_match_code(src: Source) -> tuple[list[str], list[str]]:
    """A rule file must not present a model slug that the wrapper never uses.

    A doc can be updated to name a replacement model while the matching code
    change never lands, and nothing notices. Direction matters — doc-cites-
    but-code-lacks is a lie about the running system (problem); code-has-but-
    doc-omits is merely undocumented (warning).
    """
    models, providers, problems = _code_slugs(src)
    warnings: list[str] = []
    if problems:
        return problems, warnings

    scan_targets = {CORE_BEHAVIOR_MD, TIERING_MD, "CLAUDE.md"}
    for rel in src.list_governance_md():
        # .claude/rules_db/archive/ is explicitly historical/dormant content,
        # never re-synced with live code by design — scanning it here would
        # force either perpetual false positives or someone "fixing" a doc
        # that's supposed to preserve a past state.
        if rel.startswith(".claude/rules_db/archive/"):
            continue
        if rel.startswith(".claude/rules_db/") or (
            rel.startswith(".claude/skills/") and rel.endswith("/SKILL.md")
        ):
            scan_targets.add(rel)

    cited: set[str] = set()
    for rel in sorted(scan_targets):
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        # Anthropic models are conventionally cited bare (`claude-opus-5`),
        # never slash-prefixed (`anthropic/claude-opus-5`) — the wrapper's
        # AGENT_ROUTING stores both forms (see _code_slugs), but only the
        # slash form was ever credited as "cited", so any bare-only-cited
        # Anthropic model false-positived as undocumented (2026-08-18, first
        # hit: claude-haiku-4-5-20251001 in 03_tiering_and_routing.md).
        for bare in _BARE_ANTHROPIC_SLUG.findall(text):
            slash = f"anthropic/{bare}"
            if slash in models:
                cited.add(slash)
        inventory = _inventory_line_numbers(text)
        for n, line in enumerate(text.splitlines(), 1):
            for slug in _SLUG.findall(line):
                head, _, tail = slug.partition("/")
                # Strip a trailing `:N` file:line citation (the same shape the
                # slug regex itself accepts) before path-checking — expanding
                # the scan to skills/rules_db surfaced `src/db.py:15`-style
                # citations that the exists()/suffix checks below didn't catch
                # because the line number defeated both (2026-08-18).
                path_part = re.sub(r":\d+$", "", slug)
                # Not a model slug at all: repo paths (`bin/director.py`,
                # `var/circuit_breaker.json`) and hostnames (`models.github.ai/
                # inference` — a provider namespace never contains a dot).
                if "." in head or path_part.endswith(_PATHISH_SUFFIX):
                    continue
                if (src.root / path_part).exists():
                    continue
                cited.add(slug)
                if slug in models:
                    continue
                if head in providers and tail in ("", slug):
                    continue
                if n in inventory:
                    warnings.append(
                        f"{rel}:{n}: `{slug}` appears in a provider-inventory "
                        "table (availability listing, not a routing claim) and "
                        f"is absent from {WRAPPER}."
                    )
                elif _NEGATION.search(line):
                    warnings.append(
                        f"{rel}:{n}: `{slug}` is absent from {WRAPPER}, but the "
                        "line documents it as retired/incorrect — cited as a "
                        "warning, not as configuration."
                    )
                else:
                    problems.append(
                        f"{rel}:{n}: cites model slug `{slug}`, which appears in "
                        f"no AGENT_ROUTING / _PROVIDER_DEFAULT_MODEL entry in "
                        f"{WRAPPER}. Either the code fix was never applied, or "
                        "the doc names a model nothing routes to."
                    )

    # Dormant multi-tier slugs live on in the archive under their bare form
    # (no `nim/`/`openrouter/` provider prefix) — that's "documented, just
    # not in the hot path", not silence. Only warn for
    # slugs the archive doesn't mention either.
    archive_text = src.read(_ARCHIVE_MD) or ""
    for slug in sorted(models - cited):
        if "/" not in slug:
            continue  # bare model ids (`claude-opus-5`) are matched elsewhere
        bare = slug.rsplit("/", 1)[-1] if slug.split("/", 1)[0] in providers else slug
        if bare in archive_text or slug in archive_text:
            continue
        warnings.append(
            f"{WRAPPER}: model slug `{slug}` is configured but cited in neither "
            f"{CORE_BEHAVIOR_MD} nor {TIERING_MD} (undocumented, not wrong)."
        )

    return problems, warnings


# ── check 5: CLAUDE.md counts ────────────────────────────────────────────────

_COUNT_LINE_RE = {
    "Hooks": re.compile(r"Hooks \((\d+)\)"),
    "Skills": re.compile(r"Skills \((\d+)\)"),
    "Agents": re.compile(r"Agents \((\d+)\)"),
    "Contextual rules": re.compile(r"Contextual rules \((\d+)\)"),
}


def _glob_paths(src: Source, pattern: str) -> list[str]:
    """Repo-relative paths matching `pattern`, staged- or worktree-aware.

    Mirrors `Source.list_md`'s two-mode split but for an arbitrary glob (`.py`
    files, `SKILL.md` files one level down) rather than a recursive `.md` walk.
    """
    if src.staged:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--", pattern],
            cwd=src.root,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.split() if result.returncode == 0 else []
    return sorted(str(p.relative_to(src.root)) for p in src.root.glob(pattern))


def _dir_has_any_file(src: Source, dirpath: str) -> bool:
    """True if `dirpath` contains at least one tracked/worktree file.

    Distinguishes "this source never copied/tracks this subtree at all" (e.g. a
    test fixture that only mirrors `.claude/hooks`/`rules`/`rules_db`/`agents`)
    from "the directory is real but genuinely empty" — only the former should
    make `check_claude_md_counts()` skip that count instead of reporting a
    false 0-vs-declared mismatch.
    """
    # Staged mode: git pathspec `*` crosses directory separators (unlike a
    # worktree glob), so `dirpath/*` alone already matches recursively.
    return len(_glob_paths(src, f"{dirpath}/*")) > 0 if src.staged else (
        (src.root / dirpath).is_dir() and any((src.root / dirpath).iterdir())
    )


def check_claude_md_counts(src: Source) -> tuple[list[str], list[str]]:
    """`CLAUDE.md`'s Hooks/Skills/Agents/Contextual-rules counts must match the
    live filesystem exactly — this was the most frequently rediscovered stale-
    count defect across manual audits. User decision: keep exact counts, but
    validator-enforce them so they cannot silently drift again.

    Definitions, chosen to match what each count is actually claiming:
      * Hooks: `.py` files directly under `.claude/hooks/` (flat, not recursive).
      * Skills: directories under `.claude/skills/` that contain a `SKILL.md`.
      * Agents: `.claude/agents/*.md` files (reuses `list_agent_stems()`, the
        same source `check_agent_names_exist()` treats as the SSOT).
      * Contextual rules: `_REGISTRY` aliases in `rules_dispatcher.py` that
        resolve into `.claude/rules_db/` — the deterministic `.claude/rules/*.md`
        modules are a separate, already-counted-elsewhere surface, and archived
        aliases are dormant by design, not part of the live count.

    A count whose source directory is entirely absent from `src` (e.g. a test
    fixture that only mirrors a subset of `.claude/`) is skipped rather than
    compared against a live 0 — this validator's job is catching real drift in
    the real repo, not demanding every fixture mirror the full tree.
    """
    problems: list[str] = []
    warnings: list[str] = []

    text = src.read("CLAUDE.md")
    if text is None:
        return ["cannot read CLAUDE.md"], warnings

    declared: dict[str, int] = {}
    for label, pat in _COUNT_LINE_RE.items():
        m = pat.search(text)
        if m:
            declared[label] = int(m.group(1))
    if not declared:
        return problems, warnings  # counts not present — nothing to check

    live = _live_component_counts(src)
    for label, declared_n in declared.items():
        live_n = live.get(label)
        if live_n is None:
            continue
        if declared_n != live_n:
            problems.append(
                f"CLAUDE.md: declares '{label} ({declared_n})' but the live "
                f"count is {live_n} — update CLAUDE.md or the live count drifted."
            )

    return problems, warnings


def _live_component_counts(src: Source) -> dict[str, int | None]:
    """Live Hooks/Skills/Agents/Contextual-rules counts, or None per entry when
    this `src` does not carry that subtree at all (test fixtures mirror only a
    subset of `.claude/`). Shared by `check_claude_md_counts()` and
    `check_readme_counts()` so the two never disagree about what "live" means.
    """
    hooks_live = len(_glob_paths(src, ".claude/hooks/*.py"))
    skill_files_live = len(_glob_paths(src, ".claude/skills/*/SKILL.md"))
    # Not src.list_agent_stems(): its staged-mode `git ls-files -- "*.md"`
    # pathspec matches `*` across directory separators, so it over-counts
    # nested knowledge files (e.g. finance-specialist/knowledge/*.md). Filter
    # to exactly one path segment under AGENTS_DIR, flat like the worktree glob.
    _agents_depth = AGENTS_DIR.count("/") + 1
    agents_live = len(
        [p for p in _glob_paths(src, f"{AGENTS_DIR}/*.md") if p.count("/") == _agents_depth]
    )

    dispatcher_src = src.read(DISPATCHER)
    rules_db_aliases_live = None
    if dispatcher_src is not None:
        try:
            module = intro.load_dispatcher(dispatcher_src, name="rules_dispatcher_counts")
            rules_db_aliases_live = sum(
                1 for rel in module._REGISTRY.values() if not rel.startswith("../rules/")
            )
        except Exception:
            pass  # check_registry_reachability() already reports load failures

    return {
        "Hooks": hooks_live if _dir_has_any_file(src, ".claude/hooks") else None,
        "Skills": skill_files_live if _dir_has_any_file(src, ".claude/skills") else None,
        "Agents": agents_live if _dir_has_any_file(src, AGENTS_DIR) else None,
        "Contextual rules": rules_db_aliases_live,
    }


# ── check 5b: README.md counts ───────────────────────────────────────────────

README_MD = "README.md"
SCHEMA_SQL = "database/schema_v2.sql"

# Every "<N> <thing>" shape README uses for a count this repo can introspect.
# Deliberately phrase-driven rather than line-anchored: README restates the same
# counts in the intro, the design-principles list, the ASCII architecture
# diagram, a section heading, the directory tree and the installer steps, and new
# restatements keep appearing — one sweep found the hook count wrong in 4
# places at once.
_README_COUNT_RE = re.compile(
    r"(\d+)\s+(?:live\s+)?"
    r"(lifecycle hooks|hooks|slash-command skills|skills|specialist agents"
    r"|specialist agent definitions|agents|tables|views)\b"
)
_README_LABEL = {
    "lifecycle hooks": "Hooks",
    "hooks": "Hooks",
    "slash-command skills": "Skills",
    "skills": "Skills",
    "specialist agents": "Agents",
    "specialist agent definitions": "Agents",
    "agents": "Agents",
    "tables": "Tables",
    "views": "Views",
}
_CREATE_TABLE_RE = re.compile(r"^\s*CREATE\s+TABLE\b", re.IGNORECASE | re.MULTILINE)
_CREATE_VIEW_RE = re.compile(r"^\s*CREATE\s+VIEW\b", re.IGNORECASE | re.MULTILINE)


def check_readme_counts(src: Source) -> tuple[list[str], list[str]]:
    """`README.md`'s hook / skill / agent / table / view counts must match the
    live tree, exactly as `check_claude_md_counts()` pins `CLAUDE.md:16`.

    README is the repo's most public document, restates the same governance
    counts six times, and every check in this file used to stop at `.claude/`
    + `CLAUDE.md` — so "14 hooks" survived in four places while the live count
    was 15, alongside `46 tables + 20 views` against a 60/29 schema.
    `list_governance_md()` was widened once, for
    `CLAUDE.md`; the same reasoning applies here.

    Counts come from `_live_component_counts()` (shared with the CLAUDE.md
    check, so the two can never disagree about what "live" means) plus
    `CREATE TABLE`/`CREATE VIEW` statements in `schema_v2.sql` — the schema file
    rather than `dqiii8.db`, because the DB is gitignored, absent on a fresh
    clone, and carries runtime-created tables (`learning_metrics`,
    `harvest_log`) that a README describing the *installer* must not count.

    Hard problems, not warnings: every number here is mechanically derivable, so
    a mismatch is always a real defect and never a judgement call.
    """
    problems: list[str] = []
    warnings: list[str] = []

    text = src.read(README_MD)
    if text is None:
        return problems, warnings  # no README in this source (test fixtures)

    live: dict[str, int | None] = dict(_live_component_counts(src))
    schema = src.read(SCHEMA_SQL)
    live["Tables"] = len(_CREATE_TABLE_RE.findall(schema)) if schema else None
    live["Views"] = len(_CREATE_VIEW_RE.findall(schema)) if schema else None

    for n, line in enumerate(text.splitlines(), 1):
        for m in _README_COUNT_RE.finditer(line):
            label = _README_LABEL[m.group(2).lower()]
            live_n = live.get(label)
            if live_n is None:
                continue
            declared_n = int(m.group(1))
            if declared_n != live_n:
                problems.append(
                    f"{README_MD}:{n}: claims '{m.group(0)}' but the live count "
                    f"is {live_n} — update README.md (or the count drifted)."
                )

    return problems, warnings


# ── check 6: file-path citations ─────────────────────────────────────────────

_BACKTICK_PATH = re.compile(
    r"`((?:[\w.\-]+/)+[\w.\-]+\.(?:md|py|json|sh|sql|toml|ya?ml|txt|db))`"
)


def _path_citation_exists(src: Source, path_str: str) -> bool:
    """Mirrors panel_review.py's `_citation_exists()` security invariants
    (reject absolute paths, reject `~`, reject traversal outside the repo
    root) adapted for `Source`'s staged/worktree/test-fixture root instead of
    panel_review.py's hardcoded REPO_ROOT constant — that module always runs
    against the real repo; this validator also runs against staged content
    and pytest fixtures rooted elsewhere.
    """
    if path_str.startswith("/") or path_str.startswith("~"):
        return False
    candidate = (src.root / path_str).resolve()
    if not candidate.is_relative_to(src.root):
        return False
    rel = str(candidate.relative_to(src.root))
    return src._staged_file_exists(rel) if src.staged else candidate.is_file()


def check_file_citations_exist(src: Source) -> tuple[list[str], list[str]]:
    """Every backtick-fenced path shaped like a real file, cited from
    `.claude/rules*/` or `.claude/skills/`, is checked against this repo.

    Warn-only, same rationale as `check_agent_names_exist()`'s prose sweep:
    measured live against the real corpus (2026-08-18), a plain existence
    scan is dominated by false positives that are not stale citations —
    inline BLOCKED_PATHS glob-pattern examples (`.claude/rules/secrets.md`,
    `context/proposito.md`), deliberate "this was deleted" historical notes
    (`common/git-workflow.md`, `bin/tools/gemini_review.py`), and templated
    or runtime-created paths (`sessions/YYYY-MM-DD_session_N.md`,
    `tasks/todo.md`). None of that is reliably distinguishable by regex from
    a real stale citation, so this is a human-reviewed signal, not a hard
    gate — the one real hit found this way (`svsi/SKILL.md:16` ->
    `docs/SVSI_PLAN.md`, which never existed) was fixed directly in the doc.
    """
    problems: list[str] = []
    warnings: list[str] = []

    scan_paths = [
        rel
        for rel in src.list_governance_md()
        if rel.startswith(".claude/rules") or rel.startswith(".claude/skills")
    ]
    for rel in scan_paths:
        text = src.read(rel)
        if text is None:
            continue
        for m in _BACKTICK_PATH.finditer(text):
            path_str = m.group(1)
            if not _path_citation_exists(src, path_str):
                warnings.append(
                    f"{rel}: cites `{path_str}`, which does not exist in this repo."
                )

    return problems, warnings


# ── check 7: command/skill parity ────────────────────────────────────────────

COMMANDS_DIR = ".claude/commands"
SKILLS_DIR = ".claude/skills"

# A pointer file is short and names its SKILL.md. Measured on the live corpus
# (2026-08-18): the one real pointer, commands/handover.md, has a 1-line body
# once its `>` SSOT annotation is stripped; the smallest *duplicating* command
# body is 31 lines (`audit`). 15 sits in the middle of that gap.
_POINTER_MAX_LINES = 15
# Below this ratio the two copies have genuinely forked rather than drifted by a
# few edits. Measured across the 10 duplicated pairs the distribution is
# strongly bimodal: skill-create 0.06, weekly-review 0.51, mode 0.56, then a gap
# to audit 0.82 ... mobilize 1.00. 0.60 lands in that gap, so it separates real
# content forks from near-identical copies without hand-tuning per pair.
_PARITY_MIN_RATIO = 0.60


def _split_frontmatter(text: str) -> tuple[list[str], list[str]]:
    """(frontmatter lines, remaining lines). Empty frontmatter when absent."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, ln in enumerate(lines[1:], 1) if ln.strip() == "---"), None)
        if end is not None:
            return lines[1:end], lines[end + 1 :]
    return [], lines


def _frontmatter_fields(text: str) -> dict[str, str]:
    """Top-level `key: value` pairs of a file's YAML frontmatter, values
    normalised to a single-spaced string. Nested/list continuation lines are
    folded into the key they belong to, so `auto-invoke:` blocks compare as a
    unit — this is a drift detector, not a YAML parser.
    """
    fields: dict[str, str] = {}
    key: str | None = None
    for raw in _split_frontmatter(text)[0]:
        if not raw.strip():
            continue
        if raw[:1].strip() and ":" in raw and not raw.lstrip().startswith("-"):
            key, _, value = raw.partition(":")
            key = key.strip()
            fields[key] = " ".join(value.split())
        elif key is not None:
            fields[key] = (fields[key] + " " + " ".join(raw.split())).strip()
    return fields


# Frontmatter keys that decide *who may run this and when* — a mismatch here is
# a behavioral fork even when the prose is byte-identical (a real instance:
# a command file declared `allowed_tools`, a key no runtime reads, while its
# skill declared `allowed-tools` + `user-invocable: false`).
_PARITY_FRONTMATTER_KEYS = ("allowed-tools", "user-invocable", "auto-invoke", "model")


def _parity_body(text: str) -> list[str]:
    """Substantive lines only: no YAML frontmatter, no blank lines, no
    blockquote annotations (the `> **SSOT: ...**` cross-reference convention is
    metadata about the duplication, not part of the procedure)."""
    return [
        s for ln in _split_frontmatter(text)[1] if (s := ln.strip()) and not s.startswith(">")
    ]


def _pointer_body(text: str) -> list[str]:
    """Like `_parity_body()` but **keeps** blockquote lines. The pointer test
    must not strip them: a command file whose entire substance sits inside a
    blockquote otherwise measures ~1 line and is waved through as a "pointer"
    no matter what the blockquote instructs — verified with a blockquote
    reading `run git push --force origin master`.
    """
    return [s for ln in _split_frontmatter(text)[1] if (s := ln.strip())]


_SHELL_FENCE = re.compile(r"^\s*(?:```|~~~)\s*[A-Za-z0-9_+.\-]*\s*$")


def _fenced_lines(text: str) -> set[str]:
    """Every non-comment line inside a fenced code block, as a set.

    The cheap semantic proxy the audit asked for: prose similarity cannot see
    that one copy runs `ruff check --select E,F,W` and the other
    `--select E,F,W,PLE2510,…`, because a flag list is a tiny fraction of a
    large document — but as a *line set* the two differ outright. Same for a
    missing `[ -f … ] || touch …` guard.
    """
    out: set[str] = set()
    inside = False
    for ln in _split_frontmatter(text)[1]:
        if _SHELL_FENCE.match(ln):
            inside = not inside
            continue
        s = ln.strip()
        if inside and s and not s.startswith("#"):
            out.add(s)
    return out


def check_command_skill_parity(src: Source) -> tuple[list[str], list[str]]:
    """`.claude/commands/<name>.md` and `.claude/skills/<name>/SKILL.md` are
    11 pairs of the same slash-command definition with no parity check anywhere.
    The confirmed worst case was `handover`, whose two copies described
    genuinely *different* procedures —
    one pushed to `master` unattended, the other stopped to ask first — so an
    agent that read the wrong copy would auto-push when it should have asked.

    A pair is clean when the command file is a pure pointer at the skill (the
    SSOT pattern) — measured over the body *including* blockquotes, so a file
    cannot hide a full procedure inside a `>` block and still read as a pointer.

    Otherwise three independent signals are compared, because prose similarity
    alone has a measured ~67% false-negative rate on this corpus: an
    adversarial fork that inverts only the behaviour of a SKILL.md scores 0.95
    and passes. The two it misses are added here:

      1. **Prose similarity** — catches wholesale rewrites (`skill-create` 0.06).
      2. **Fenced code lines** — the commands actually executed, compared as
         sets. This is what would have caught `quality-gate`'s
         `--select E,F,W` vs `--select E,F,W,PLE2510-2515` (a dropped
         trojan-source defense that still reported PASS) and `checkpoint`'s
         missing `touch` guard.
      3. **Invocation frontmatter** (`_PARITY_FRONTMATTER_KEYS`) — who may run
         this and when. `_parity_body()` strips frontmatter, so before this
         these fields were compared by nothing.

    Hard-fail: all 11 pairs were reduced to pure pointers or reconciled, so a
    fresh divergence — not pre-existing debt — is what this now blocks.
    """
    problems: list[str] = []
    warnings: list[str] = []

    for rel in src.list_md(COMMANDS_DIR):
        name = Path(rel).stem
        skill_rel = f"{SKILLS_DIR}/{name}/SKILL.md"
        cmd_text = src.read(rel)
        skill_text = src.read(skill_rel)
        if cmd_text is None or skill_text is None:
            continue  # unpaired command or skill — nothing to compare

        if len(_pointer_body(cmd_text)) <= _POINTER_MAX_LINES and skill_rel in cmd_text:
            continue  # pure pointer at the SSOT — the intended end state

        ratio = difflib.SequenceMatcher(
            None, _parity_body(cmd_text), _parity_body(skill_text)
        ).ratio()
        diverged = ratio < _PARITY_MIN_RATIO
        if diverged:
            problems.append(
                f"{rel} duplicates {skill_rel} and has diverged "
                f"(similarity {ratio:.2f} < {_PARITY_MIN_RATIO:.2f}) — reconcile "
                f"them, or reduce the command file to a pointer at the skill."
            )

        # Only for pairs the ratio waves through: a wholesale rewrite is already
        # reported above, and re-reporting its code blocks adds noise without
        # information. The point of this signal is the *near-identical* pair
        # whose one divergent command line the ratio cannot see.
        cmd_cmds, skill_cmds = _fenced_lines(cmd_text), _fenced_lines(skill_text)
        if not diverged and cmd_cmds != skill_cmds:
            sample = sorted(cmd_cmds ^ skill_cmds)[:2]
            problems.append(
                f"{rel} duplicates {skill_rel} but their fenced code blocks "
                f"differ in {len(cmd_cmds ^ skill_cmds)} line(s) — one copy runs "
                f"commands the other does not, e.g. {sample}. Reconcile the "
                f"behaviour, or reduce the command file to a pointer."
            )

        cmd_fm, skill_fm = _frontmatter_fields(cmd_text), _frontmatter_fields(skill_text)
        if not cmd_fm:
            # No frontmatter at all: every governance field lives on one side
            # only. One line, not one per key — the warning channel has to stay
            # small enough that a new entry is actually read.
            absent = [k for k in _PARITY_FRONTMATTER_KEYS if k in skill_fm]
            if absent:
                problems.append(
                    f"{rel} duplicates {skill_rel} but declares no frontmatter, so "
                    f"{', '.join(f'`{k}`' for k in absent)} exist only in the skill "
                    f"— nothing states who may invoke the command form."
                )
        else:
            for key in _PARITY_FRONTMATTER_KEYS:
                if cmd_fm.get(key) != skill_fm.get(key):
                    problems.append(
                        f"{rel} duplicates {skill_rel} but their `{key}:` "
                        f"frontmatter differs ({cmd_fm.get(key)!r} vs "
                        f"{skill_fm.get(key)!r}) — this field governs who may "
                        f"invoke the command and when."
                    )

    return problems, warnings


# ── check 8: constant lists match prose ──────────────────────────────────────

PERMISSION_ANALYZER = ".claude/hooks/permission_analyzer.py"


def _code_blocked_paths(src: Source) -> list[str] | None:
    """The live `BLOCKED_PATHS` list from permission_analyzer.py, as string
    literals in source order. `None` if the file can't be read or the list
    can't be found (caller reports that as a problem, not a silent skip)."""
    text = src.read(PERMISSION_ANALYZER)
    if text is None:
        return None
    m = re.search(r"^BLOCKED_PATHS = \[(.*?)^\]", text, re.S | re.M)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def check_constant_lists_match_prose(src: Source) -> tuple[list[str], list[str]]:
    """`02_hooks_and_permissions.md`'s "Blocked paths" line restates
    `BLOCKED_PATHS` inline (backtick-comma list) instead of linking to code:
    the list has grown from 11 to 23 entries across several edits and the doc line had to be
    hand-edited to keep up, with nothing that would fail if a future edit
    forgot one side. Hard-fail: an out-of-sync prose restatement of a security
    allow/deny list is a doc that lies about what the code actually blocks.
    """
    problems: list[str] = []
    warnings: list[str] = []

    code_paths = _code_blocked_paths(src)
    if code_paths is None:
        problems.append(f"cannot find BLOCKED_PATHS in {PERMISSION_ANALYZER}")
        return problems, warnings

    doc_text = src.read(HOOKS_PERMS_MD)
    if doc_text is None:
        problems.append(f"cannot read {HOOKS_PERMS_MD}")
        return problems, warnings

    for path in code_paths:
        if f"`{path}`" not in doc_text:
            problems.append(
                f"{HOOKS_PERMS_MD}: BLOCKED_PATHS entry `{path}` (in {PERMISSION_ANALYZER}) "
                "is not cited in the doc's Blocked paths restatement."
            )

    # Reverse direction: a backtick-quoted entry in the Blocked paths
    # paragraph that isn't in BLOCKED_PATHS is stale or invented. Narrowed to
    # that one paragraph (not the whole doc) and to bare-token backticks —
    # `_BACKTICK_PATH` requires a directory component + known extension, which
    # excludes exactly the bare filenames (`CLAUDE.md` has no `/`, `secrets`
    # has no extension) that make up most of this list, so it can't be reused
    # here.
    code_set = set(code_paths)
    m = re.search(r"\*\*Blocked paths.*?\n(?=No exception)", doc_text, re.S)
    if m:
        for cited in re.findall(r"`([^`]+)`", m.group(0)):
            if cited in ("BLOCKED_PATHS", "permission_analyzer.py"):
                continue
            if cited not in code_set:
                problems.append(
                    f"{HOOKS_PERMS_MD}: cites `{cited}` in the Blocked paths list, "
                    f"which is not in BLOCKED_PATHS in {PERMISSION_ANALYZER} "
                    "(stale or invented entry)."
                )

    return problems, warnings


# ── check 9: no unresolved audit-ID comments ─────────────────────────────────

THIS_FILE = "bin/tools/validate_rules_registry.py"
GITLEAKS_HOOK_SETUP = "bin/tools/setup_gitleaks_hook.sh"

# Short audit-report shorthand (a letter-prefixed number, or "Gap"/"Phase"
# plus a number) reads fine to whoever wrote it, next to the gitignored audit
# report it points at — but that report never survives to `git log`, so six
# months later the shorthand is a dead end and the comment has to be
# re-derived from scratch. Every instance found this way was rewritten to
# state its reason directly instead. A ruff lint-suppression code is excluded
# below so this doesn't misfire on ordinary `noqa` comments — see `_NOQA_CODE`.
_AUDIT_ID = re.compile(
    r"\b(?:RC\d[\d.]*|INV\d+|SEC\d+|Gap \d+|Phase \d+ of|F\d+)\b"
)
_NOQA_CODE = re.compile(r"noqa:\s*F\d+")


def check_no_audit_id_comments(src: Source) -> tuple[list[str], list[str]]:
    """No dangling audit-report shorthand (see `_AUDIT_ID`) in the files this
    validator and its installer are made of. A citation like this is a
    pointer into a gitignored, ephemeral audit report — durable in the room
    where it was written, a dead end for anyone reading the comment later.
    State the reason inline instead.
    """
    problems: list[str] = []
    warnings: list[str] = []

    for rel in (THIS_FILE, GITLEAKS_HOOK_SETUP):
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        for n, line in enumerate(text.splitlines(), 1):
            stripped = _NOQA_CODE.sub("", line)
            m = _AUDIT_ID.search(stripped)
            if m:
                problems.append(
                    f"{rel}:{n}: dangling audit-ID citation `{m.group(0)}` — "
                    "state the reason directly instead of citing an ID."
                )

    return problems, warnings


# ── check: alias-reach counts ("2 / 13 / 4") ─────────────────────────────────
# The floor (2 _ALWAYS aliases), reachable ceiling (13, one Bash command hitting
# every _BASH_KEYWORD_RULES pattern) and `git status`'s own injection count (4)
# are hardcoded, unenforced prose in CLAUDE.md and 02_hooks_and_permissions.md.
# Derived analytically from the dispatcher's own tables (same primitives as
# _measured_range_problems above) rather than a hand re-count, so a new
# _BASH_KEYWORD_RULES row or registry alias updates the live numbers
# automatically. DYNAMIC.md deliberately does NOT restate these numbers (it
# points at rules_dispatcher.py's docstring instead, to keep its own token
# footprint down) — do not add a DYNAMIC_MD entry here unless DYNAMIC.md's
# prose is made to cite a number again; an entry whose regex can never match
# passes silently and gives no real coverage (this happened once already,
# 2026-08-19, when the prose it matched was trimmed in the same commit that
# added the pattern — see test_every_alias_count_pattern_matches below).

_ALIAS_COUNT_PATTERNS = {
    "CLAUDE.md": {
        "floor": re.compile(r"(\d+) files minimum"),
        "ceiling": re.compile(r"(\d+) in the reachable ceiling case"),
    },
    HOOKS_PERMS_MD: {
        "floor": re.compile(r"floor is the (\d+) `_ALWAYS`"),
        "ceiling": re.compile(r"reachable ceiling is (\d+)"),
        "git_status": re.compile(r"git status.? already injects (\d+)"),
    },
}


def _alias_count_for_set(rd, aliases: list[str]) -> int:
    """Unique, registry-resolvable alias count for one reachable set — same
    dedup rule get_rules() applies before rendering, but counting instead of
    reading file content."""
    seen: set[str] = set()
    for alias in aliases:
        if alias in rd._REGISTRY:
            seen.add(alias)
    return len(seen)


def _alias_count_via_get_rules(rd, tool: str, tool_input: dict) -> int:
    """Live unique-alias count get_rules() would inject for one call, measured
    by making `_read` return the bare alias name (no internal "\\n\\n") so the
    "\\n\\n"-joined block's separator count equals the alias count exactly."""
    orig_read = rd._read
    try:
        rd._read = lambda alias: alias
        text = rd.get_rules(tool, tool_input)
    finally:
        rd._read = orig_read
    return text.count("\n\n") if text else 0


def check_alias_reach_counts(src: Source) -> tuple[list[str], list[str]]:
    """CLAUDE.md / 02_hooks_and_permissions.md must each state the live
    "2 / 13 / 4" alias-reach facts, not a stale hand-written guess."""
    problems: list[str] = []
    warnings: list[str] = []

    if src.root.resolve() != ROOT.resolve():
        return problems, warnings  # only the real repo can be measured

    try:
        import rules_dispatcher as rd  # noqa: PLC0415
    except Exception as exc:
        return [f"cannot import rules_dispatcher to measure alias-reach counts: {exc}"], warnings

    live = {
        "floor": len(rd._ALWAYS),
        "ceiling": max(
            (_alias_count_for_set(rd, aliases) for _label, aliases in _reachable_alias_sets(rd)),
            default=0,
        ),
        "git_status": _alias_count_via_get_rules(rd, "Bash", {"command": "git status"}),
    }

    for rel, patterns in _ALIAS_COUNT_PATTERNS.items():
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        for label, pat in patterns.items():
            m = pat.search(text)
            if not m:
                continue  # this file doesn't cite that particular number
            declared = int(m.group(1))
            if declared != live[label]:
                problems.append(
                    f"{rel}: states {label}={declared} but the live measured "
                    f"{label} is {live[label]} — re-measure and update."
                )

    return problems, warnings


# ── check: no newly-committed audit docs ─────────────────────────────────────
# CLAUDE.md's "never committed — full stop" rule was prose only, with no
# mechanical enforcement — every neighboring invariant in this governance
# corpus is validator- or DB-trigger-backed, this one wasn't.
# --staged-only: a newly-*added* (git status "A") file under either gitignored
# audit-doc prefix means it was force-added (`git add -f`), bypassing
# .gitignore. The grandfathered `af869db` corpus is untouched — those 35
# files, if ever edited, show as "M" (modified), never "A".
_AUDIT_DOC_PREFIXES = ("docs/audits/", "database/audit_reports/")


def check_no_new_audit_docs(src: Source) -> tuple[list[str], list[str]]:
    """No newly-added file under docs/audits/ or database/audit_reports/ in the
    staged changeset. Both directories are gitignored with no negation
    (CLAUDE.md's exception is a one-time, already-closed archival decision, not
    a standing carve-out)."""
    problems: list[str] = []
    warnings: list[str] = []

    if not src.staged:
        return problems, warnings  # only meaningful at commit time

    # -z (NUL-separated, no quoting/octal-escaping of non-ASCII or space-bearing
    # paths) with rename detection left on: a rename/copy record is STATUS\0OLD\0NEW\0,
    # a plain record is STATUS\0PATH\0. Renames land the new path under the audit
    # prefix without ever going through "A" (git's default rename detection emits
    # R<score>, not A+D) — treat R/C's *new* path the same as a fresh add.
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-status", "-z"],
        cwd=src.root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        return [f"git diff --cached --name-status failed: {result.stderr.strip()}"], warnings

    fields = result.stdout.split("\0")[:-1]  # trailing NUL leaves one empty field
    i = 0
    while i < len(fields):
        status = fields[i]
        code = status[0] if status else ""
        if code in ("R", "C"):
            path = fields[i + 2] if i + 2 < len(fields) else ""
            i += 3
        else:
            path = fields[i + 1] if i + 1 < len(fields) else ""
            i += 2
        if code not in ("A", "R", "C") or not path:
            continue
        if path.startswith(_AUDIT_DOC_PREFIXES):
            problems.append(
                f"{path}: newly staged (status {status}) under a gitignored "
                "audit-doc prefix — these paths are never committed (CLAUDE.md "
                "§ New audit reports and audit docs). If this really is an "
                "intentional, one-time archival exception like af869db, get the "
                "same explicit human call and update CLAUDE.md's exception "
                "note, don't just add -f (or git mv) around this check."
            )

    return problems, warnings


# ── entrypoint ───────────────────────────────────────────────────────────────

CHECKS = (
    ("registry-reachability", check_registry_reachability),
    ("token-budget", check_token_budget),
    ("agent-names", check_agent_names_exist),
    ("model-slugs", check_model_slugs_match_code),
    ("claude-md-counts", check_claude_md_counts),
    ("readme-counts", check_readme_counts),
    ("file-citations", check_file_citations_exist),
    ("command-skill-parity", check_command_skill_parity),
    ("constant-lists-match-prose", check_constant_lists_match_prose),
    ("no-audit-id-comments", check_no_audit_id_comments),
    ("alias-reach-counts", check_alias_reach_counts),
    ("no-new-audit-docs", check_no_new_audit_docs),
)


def run_all(src: Source) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    for name, check in CHECKS:
        p, w = check(src)
        problems.extend(f"[{name}] {x}" for x in p)
        warnings.extend(f"[{name}] {x}" for x in w)
    return problems, warnings


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    staged = "--staged" in argv
    if staged:
        argv.remove("--staged")
    root = ROOT
    if "--root" in argv:
        idx = argv.index("--root") + 1
        if idx >= len(argv):
            print("[validate-rules] --root requires a PATH argument", file=sys.stderr)
            return 2
        root = Path(argv[idx])

    src = Source(root=root, staged=staged)
    problems, warnings = run_all(src)

    for w in warnings:
        print(f"[validate-rules] WARNING: {w}")
    if problems:
        print(f"[validate-rules] {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    mode = "staged" if staged else "worktree"
    print(
        f"[validate-rules] OK ({mode}) — registry reachable, token range "
        f"consistent, agent names and model slugs match code, CLAUDE.md counts "
        f"match live ({len(warnings)} warning(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
