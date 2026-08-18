#!/usr/bin/env python3
"""Validate the rules/routing governance surface: registry, token budget, agent
names and model slugs.

Phase 2 of the 2026-08-17 doc-governance remediation. Phase 1 fixed 18 concrete
gaps by hand; every one of them was a *silent* drift between a declaration in
code and a statement in a rule file, discoverable only by a human reading both
sides at once. This script turns the four highest-frequency drifts into
mechanical pre-commit checks so they cannot come back:

  1. check_registry_reachability()  — no orphan/dangling `_REGISTRY` alias.
     (`routing`, `performance`, `git-workflow`, `workflow`, `testing` were all
     registered-but-unreachable; two of them also redefined canonical taxonomy.)
  2. check_token_budget()           — the dispatcher docstring, DYNAMIC.md and
     02_hooks_and_permissions.md (x2) must quote ONE range. It went stale twice
     on 2026-08-17 alone, which is exactly what a mechanical check is for.
  3. check_agent_names_exist()      — an agent cited in a routing table must
     exist in `AGENT_ROUTING` or as a `.claude/agents/*.md` file.
  4. check_model_slugs_match_code() — a model slug a rule file presents as
     configured must actually appear in the wrapper's routing tables. This is
     Gap 2's exact failure mode: the doc fix was written, the code fix never was.

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
        apex always-loaded file, so its own stale counts (RC3) and any model
        slug or agent name it cites went unchecked (RC11.6, 2026-08-18)."""
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

_CANON_FLOOR = re.compile(r"suelo\s+(?:de\s+)?\*{0,2}([\d.,]+)", re.IGNORECASE)
_CANON_CEIL = re.compile(r"techo\s+(?:de\s+)?\*{0,2}([\d.,]+)", re.IGNORECASE)
_RANGE = re.compile(r"([\d][\d.,]*)\s*[-–—]\s*([\d][\d.,]*)\s*tokens")


def _canonical_range(dispatcher_src: str) -> tuple[int, int] | None:
    """The ONE canonical range, taken from the rules_dispatcher docstring."""
    doc = ast.get_docstring(ast.parse(dispatcher_src)) or ""
    floors = [_num(m) for m in _CANON_FLOOR.findall(doc)]
    ceils = [_num(m) for m in _CANON_CEIL.findall(doc)]
    floors = [f for f in floors if f]
    ceils = [c for c in ceils if c]
    if not floors or not ceils:
        return None
    return floors[0], ceils[0]


def check_token_budget(src: Source) -> tuple[list[str], list[str]]:
    """The dispatcher docstring is the single source for the measured token
    range; DYNAMIC.md and 02_hooks_and_permissions.md must quote it verbatim.

    Four places state this number and there is no mechanical link between them,
    so it drifted twice on 2026-08-17 alone. Now a mismatch fails the commit.
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

    # DYNAMIC.md: >=1 occurrence. 02_hooks_and_permissions.md: >=2 (the hook
    # order line and the § Rules dispatcher paragraph).
    for rel, expected_min in ((DYNAMIC_MD, 1), (HOOKS_PERMS_MD, 2)):
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        found = _RANGE.findall(text)
        if len(found) < expected_min:
            problems.append(
                f"{rel}: expected at least {expected_min} citation(s) of the "
                f"token range '{floor}-{ceiling}', found {len(found)}. The four "
                "sites that quote this number must be updated together."
            )
        for raw_lo, raw_hi in found:
            lo, hi = _num(raw_lo), _num(raw_hi)
            if (lo, hi) != (floor, ceiling):
                problems.append(
                    f"{rel}: token range '{raw_lo}-{raw_hi}' disagrees with the "
                    f"canonical '{floor}-{ceiling}' in {DISPATCHER}'s docstring."
                )
        # Prose restatements of either bound ("el suelo de 1.432 es ...").
        for pattern, expected, label in (
            (_CANON_FLOOR, floor, "suelo"),
            (_CANON_CEIL, ceiling, "techo"),
        ):
            for raw in pattern.findall(text):
                value = _num(raw)
                if value is not None and value != expected:
                    problems.append(
                        f"{rel}: {label} stated as {raw} but the canonical "
                        f"{label} is {expected}."
                    )

    return problems, warnings


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

    Gap 2's exact failure mode: 03_tiering_and_routing.md was updated to name
    the replacement model, the wrapper never was, and nothing noticed. Direction
    matters — doc-cites-but-code-lacks is a lie about the running system
    (problem); code-has-but-doc-omits is merely undocumented (warning).
    """
    models, providers, problems = _code_slugs(src)
    warnings: list[str] = []
    if problems:
        return problems, warnings

    scan_targets = {CORE_BEHAVIOR_MD, TIERING_MD, "CLAUDE.md"}
    for rel in src.list_governance_md():
        # .claude/rules_db/archive/ is explicitly historical/dormant content
        # (RC9, 2026-08-18) — it is never re-synced with live code by design,
        # so scanning it here would force either perpetual false positives or
        # someone "fixing" a doc that's supposed to preserve a past state.
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

    for slug in sorted(models - cited):
        if "/" not in slug:
            continue  # bare model ids (`claude-opus-4-8`) are matched elsewhere
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
    live filesystem exactly (RC3, cited 5x across the 2026-08-17 audit reports
    — the highest-cited single defect). User decision: keep exact counts, but
    validator-enforce them so they cannot silently drift a 6th time.

    Definitions, chosen to match what each count is actually claiming:
      * Hooks: `.py` files directly under `.claude/hooks/` (flat, not recursive).
      * Skills: directories under `.claude/skills/` that contain a `SKILL.md`.
      * Agents: `.claude/agents/*.md` files (reuses `list_agent_stems()`, the
        same source `check_agent_names_exist()` treats as the SSOT).
      * Contextual rules: `_REGISTRY` aliases in `rules_dispatcher.py` that
        resolve into `.claude/rules_db/` — the deterministic `.claude/rules/*.md`
        modules are a separate, already-counted-elsewhere surface, and archived
        aliases are dormant by design (RC9), not part of the live count.

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

    live = {
        "Hooks": hooks_live if _dir_has_any_file(src, ".claude/hooks") else None,
        "Skills": skill_files_live if _dir_has_any_file(src, ".claude/skills") else None,
        "Agents": agents_live if _dir_has_any_file(src, AGENTS_DIR) else None,
        "Contextual rules": rules_db_aliases_live,
    }
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


# ── entrypoint ───────────────────────────────────────────────────────────────

CHECKS = (
    ("registry-reachability", check_registry_reachability),
    ("token-budget", check_token_budget),
    ("agent-names", check_agent_names_exist),
    ("model-slugs", check_model_slugs_match_code),
    ("claude-md-counts", check_claude_md_counts),
    ("file-citations", check_file_citations_exist),
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
