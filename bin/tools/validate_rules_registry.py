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


def _md_tables(text: str):
    """Yield (header_cells, [body_row_cells...]) for every GFM table.

    A table is a `|---|---|` separator line, its preceding line as header, and
    every following pipe-line until the block ends.
    """
    lines = text.splitlines()
    sep = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")

    def cells(line: str) -> list[str]:
        return [c.strip() for c in line.strip().strip("|").split("|")]

    i = 1
    while i < len(lines):
        line = lines[i]
        if "|" in line and "-" in line and sep.match(line) and "|" in lines[i - 1]:
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

    for rel in src.list_md(".claude"):
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
_PATHISH_SUFFIX = (".py", ".md", ".json", ".sh", ".sql", ".toml", ".yaml", ".yml", ".txt", ".db")
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
                models.add(value[1])
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

    cited: set[str] = set()
    for rel in (CORE_BEHAVIOR_MD, TIERING_MD):
        text = src.read(rel)
        if text is None:
            problems.append(f"cannot read {rel}")
            continue
        inventory = _inventory_line_numbers(text)
        for n, line in enumerate(text.splitlines(), 1):
            for slug in _SLUG.findall(line):
                head, _, tail = slug.partition("/")
                # Not a model slug at all: repo paths (`bin/director.py`,
                # `var/circuit_breaker.json`) and hostnames (`models.github.ai/
                # inference` — a provider namespace never contains a dot).
                if "." in head or slug.endswith(_PATHISH_SUFFIX):
                    continue
                if (src.root / slug).exists():
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


# ── entrypoint ───────────────────────────────────────────────────────────────

CHECKS = (
    ("registry-reachability", check_registry_reachability),
    ("token-budget", check_token_budget),
    ("agent-names", check_agent_names_exist),
    ("model-slugs", check_model_slugs_match_code),
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
        f"consistent, agent names and model slugs match code "
        f"({len(warnings)} warning(s))"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
