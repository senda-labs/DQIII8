"""Tests for bin/tools/validate_rules_registry.py (Phase 2 governance gate).

Every check gets a synthetic fixture in both directions — the drift it exists to
catch must fail, and the corresponding *legitimate* pattern must not.

The load-bearing test is `test_clean_repo_state_has_no_problems`: Phase 1 just
brought the real repo to a known-good state on all four axes, so a problem there
means either this validator has a false positive or Phase 1 missed something.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin" / "tools"))

import validate_rules_registry as vrr  # noqa: E402


# ── fixtures ────────────────────────────────────────────────────────────────

# Only the surface the validator actually reads; keeps each fixture repo cheap.
_COPY_TREES = (".claude/hooks", ".claude/rules", ".claude/rules_db", ".claude/agents")
_COPY_FILES = ("bin/core/openrouter_wrapper.py", "CLAUDE.md")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway copy of the real governance surface, safe to mutate."""
    for rel in _COPY_TREES:
        shutil.copytree(ROOT / rel, tmp_path / rel, dirs_exist_ok=True)
    for rel in _COPY_FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    return tmp_path


def src(repo: Path, staged: bool = False) -> vrr.Source:
    return vrr.Source(root=repo, staged=staged)


def edit(repo: Path, rel: str, old: str, new: str) -> None:
    path = repo / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture precondition failed: {old!r} not in {rel}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# ── the sanity check that matters most ──────────────────────────────────────


def test_clean_repo_state_has_no_problems():
    """Zero problems against the REAL current (post Phase-1) worktree."""
    problems, _warnings = vrr.run_all(vrr.Source(root=ROOT, staged=False))
    assert not problems, "validator reports problems on the clean repo:\n" + "\n".join(
        problems
    )


def test_clean_repo_fixture_copy_is_also_clean(repo: Path):
    """The fixture repo itself starts clean, so each mutation test is isolated."""
    problems, _ = vrr.run_all(src(repo))
    assert not problems, problems


# ── check 1: registry reachability ──────────────────────────────────────────


def test_orphan_alias_is_a_problem(repo: Path):
    """An alias registered but wired to no trigger must fail."""
    (repo / ".claude/rules_db/orphan-fixture.md").write_text("# orphan\n")
    edit(
        repo,
        ".claude/hooks/rules_dispatcher.py",
        '"quality":        "common/quality.md",',
        '"quality":        "common/quality.md",\n    "orphan-fixture": "orphan-fixture.md",',
    )
    problems, _ = vrr.check_registry_reachability(src(repo))
    assert any("orphan-fixture" in p and "orphaned" in p for p in problems), problems


def test_inline_path_wired_aliases_are_not_orphans(repo: Path):
    """Regression guard for the naive four-table union.

    `hooks-perms`, `tiering` and `db-mutations` are injected by hardcoded path
    substrings inside get_rules(). `hooks-perms` is reachable ONLY that way, so
    a validator that unioned the four declarative tables would report it as an
    orphan and invite deleting a live, correctly-wired rule.
    """
    problems, _ = vrr.check_registry_reachability(src(repo))
    assert not problems, problems
    source = (repo / ".claude/hooks/rules_dispatcher.py").read_text(encoding="utf-8")
    module = vrr.intro.load_dispatcher(source)
    inline = vrr.intro.inline_aliases(source, module._REGISTRY)
    declarative = vrr.intro.declarative_aliases(module)

    assert {"hooks-perms", "tiering", "db-mutations"} <= inline
    # The trap: hooks-perms is in NO mapping table.
    assert "hooks-perms" not in declarative
    assert "hooks-perms" in vrr.intro.reachable_aliases(module, source)
    assert "hooks-perms" not in vrr.intro.orphan_aliases(module, source)


def test_dangling_mapping_alias_is_a_problem(repo: Path):
    """A mapping table naming an unregistered alias fails too (other direction)."""
    edit(
        repo,
        ".claude/hooks/rules_dispatcher.py",
        '"Read":       ["prevention"],',
        '"Read":       ["prevention", "typo-alias"],',
    )
    problems, _ = vrr.check_registry_reachability(src(repo))
    assert any("typo-alias" in p and "unregistered" in p for p in problems), problems


def test_registered_alias_with_missing_file_is_a_problem(repo: Path):
    (repo / ".claude/rules_db/common/quality.md").unlink()
    problems, _ = vrr.check_registry_reachability(src(repo))
    assert any("missing files" in p for p in problems), problems


# ── check 2: token budget ───────────────────────────────────────────────────


def test_token_range_mismatch_in_dynamic_md_is_a_problem(repo: Path):
    edit(repo, ".claude/rules/DYNAMIC.md", "1144–6853", "1999–6853")
    problems, _ = vrr.check_token_budget(src(repo))
    assert any("DYNAMIC.md" in p and "disagrees" in p for p in problems), problems


def test_token_range_mismatch_in_hooks_perms_is_a_problem(repo: Path):
    edit(repo, ".claude/rules/02_hooks_and_permissions.md", "~1144–6853", "~1144–9999")
    problems, _ = vrr.check_token_budget(src(repo))
    assert any("02_hooks_and_permissions.md" in p and "disagrees" in p for p in problems), problems


def test_prose_floor_restatement_mismatch_is_a_problem(repo: Path):
    """'el suelo de 1144 es ops + core-behavior' must track the canonical floor."""
    edit(repo, ".claude/rules/02_hooks_and_permissions.md", "suelo de 1144", "suelo de 1111")
    problems, _ = vrr.check_token_budget(src(repo))
    assert any("suelo stated as 1111" in p for p in problems), problems


def test_dropping_a_required_citation_is_a_problem(repo: Path):
    """02_hooks_and_permissions.md must keep BOTH of its range citations."""
    edit(repo, ".claude/rules/02_hooks_and_permissions.md", "~1144–6853 tokens", "some tokens")
    problems, _ = vrr.check_token_budget(src(repo))
    assert any("expected at least 2 citation" in p for p in problems), problems


def test_canonical_range_change_alone_breaks_the_docs(repo: Path):
    """Re-measuring the dispatcher without updating the 3 doc sites fails."""
    edit(repo, ".claude/hooks/rules_dispatcher.py", "**suelo 1144**", "**suelo 2000**")
    problems, _ = vrr.check_token_budget(src(repo))
    assert len([p for p in problems if "disagrees" in p or "suelo" in p]) >= 2, problems


def test_missing_canonical_markers_is_a_problem(repo: Path):
    edit(repo, ".claude/hooks/rules_dispatcher.py", "**suelo 1144**", "**floor 1144**")
    edit(repo, ".claude/hooks/rules_dispatcher.py", "**techo 6853**", "**ceiling 6853**")
    problems, _ = vrr.check_token_budget(src(repo))
    assert any("cannot locate the canonical token range" in p for p in problems), problems


def test_rounded_prose_range_in_docstring_is_accepted(repo: Path):
    """'~1144–6853' is a legitimate (exact) rounding of the canonical 1144-6853 — no warning."""
    _, warnings = vrr.check_token_budget(src(repo))
    assert not [w for w in warnings if "not a rounding" in w], warnings


def test_badly_rounded_prose_range_in_docstring_is_a_warning(repo: Path):
    edit(repo, ".claude/hooks/rules_dispatcher.py", "~1144–6853 tokens", "~1200–6853 tokens")
    problems, warnings = vrr.check_token_budget(src(repo))
    assert any("not a rounding" in w for w in warnings), warnings
    assert not problems, problems


# ── check 3: agent names ────────────────────────────────────────────────────

_TABLE = """# Fixture

| Agente | Proveedor/Modelo | Usar para |
|--------|------------------|-----------|
| `{name}` | Groq / llama-3.3-70b | fixture row |
"""


def test_unknown_agent_in_table_row_is_a_problem(repo: Path):
    (repo / ".claude/rules_db/fixture-table.md").write_text(
        _TABLE.format(name="ghost-specialist"), encoding="utf-8"
    )
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert any("ghost-specialist" in p and "table row cites agent" in p for p in problems), problems


def test_unknown_agent_in_a_fenced_code_block_table_is_not_a_problem(repo: Path):
    """RC11.2: a pipe-table shown as a literal example inside a ``` fence
    (illustrative output format, vendored snippet) is not a declarative
    citation — _md_tables() must not scan it."""
    fenced = "# Fixture\n\n```\n" + _TABLE.split("\n", 1)[1] + "```\n"
    (repo / ".claude/rules_db/fixture-fenced-table.md").write_text(
        fenced.format(name="ghost-specialist"), encoding="utf-8"
    )
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert not [p for p in problems if "ghost-specialist" in p], problems


def test_same_unknown_name_in_free_prose_is_only_a_warning(repo: Path):
    """Identical name, prose instead of a table row: warning, never a problem."""
    (repo / ".claude/rules_db/fixture-prose.md").write_text(
        "# Fixture\n\nAntes delegábamos esto a ghost-specialist, ya retirado.\n",
        encoding="utf-8",
    )
    problems, warnings = vrr.check_agent_names_exist(src(repo))
    assert not [p for p in problems if "ghost-specialist" in p], problems
    assert any("ghost-specialist" in w and "free-text" in w for w in warnings), warnings


def test_known_agent_in_table_row_is_clean(repo: Path):
    """A name present in AGENT_ROUTING passes even with no agents/*.md file."""
    (repo / ".claude/rules_db/fixture-ok.md").write_text(
        _TABLE.format(name="algo-specialist"), encoding="utf-8"
    )
    assert not (repo / ".claude/agents/algo-specialist.md").exists()
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert not [p for p in problems if "algo-specialist" in p], problems


def test_agent_file_without_routing_entry_is_clean(repo: Path):
    """The other half of the SSOT union: a `.claude/agents/*.md` stem is valid."""
    (repo / ".claude/agents/explorer-lite.md").write_text("# explorer-lite\n", encoding="utf-8")
    (repo / ".claude/rules_db/fixture-file-agent.md").write_text(
        _TABLE.format(name="explorer-lite"), encoding="utf-8"
    )
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert not [p for p in problems if "explorer-lite" in p], problems


def test_table_placeholders_are_not_treated_as_agent_names(repo: Path):
    (repo / ".claude/rules_db/fixture-placeholder.md").write_text(
        "| Agent | Status |\n|---|---|\n| [name] | — |\n| {agent_id} | ok |\n",
        encoding="utf-8",
    )
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert not problems, problems


def test_non_agent_column_tables_are_ignored(repo: Path):
    """Only a column literally headed Agent/Agente is a citation site."""
    (repo / ".claude/rules_db/fixture-other-col.md").write_text(
        "| Tool | Owner |\n|---|---|\n| ghost-specialist | nobody |\n", encoding="utf-8"
    )
    problems, _ = vrr.check_agent_names_exist(src(repo))
    assert not problems, problems


# ── check 4: model slugs ────────────────────────────────────────────────────


def test_doc_slug_absent_from_code_is_a_problem(repo: Path):
    """Gap 2's failure mode: the doc names a model nothing routes to."""
    path = repo / ".claude/rules/00_core_behavior.md"
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\nRazonamiento: `nvidia/llama-9.9-imaginary-999b`.\n",
        encoding="utf-8",
    )
    problems, _ = vrr.check_model_slugs_match_code(src(repo))
    assert any("nvidia/llama-9.9-imaginary-999b" in p for p in problems), problems


def test_code_slug_absent_from_docs_is_only_a_warning(repo: Path):
    """Reverse direction: undocumented, not wrong."""
    edit(
        repo,
        "bin/core/openrouter_wrapper.py",
        '"git-specialist":    ("ollama", "qwen2.5-coder:7b"),',
        '"git-specialist":    ("ollama", "vendor/undocumented-model-1b"),',
    )
    problems, warnings = vrr.check_model_slugs_match_code(src(repo))
    assert not [p for p in problems if "undocumented-model-1b" in p], problems
    assert any("undocumented-model-1b" in w for w in warnings), warnings


def test_slug_in_provider_inventory_table_is_only_a_warning(repo: Path):
    """A provider availability listing is not a claim about DQIII8's routing."""
    (repo / ".claude/rules_db/fixture-inventory.md").write_text(
        "# Fixture\n\n"
        "| Categoría | Modelo |\n"
        "|---|---|\n"
        "| LLM | `openai/gpt-oss-120b` |\n",
        encoding="utf-8",
    )
    problems, warnings = vrr.check_model_slugs_match_code(src(repo))
    assert not problems, problems
    assert any("openai/gpt-oss-120b" in w and "inventory" in w for w in warnings), warnings


def test_slug_documented_as_retired_is_only_a_warning(repo: Path):
    (repo / ".claude/rules_db/fixture-retired.md").write_text(
        "# Fixture\n\n"
        "El modelo `qwen/qwen3-coder:free` quedó retirado del proveedor, no usar.\n",
        encoding="utf-8",
    )
    _problems, warnings = vrr.check_model_slugs_match_code(src(repo))
    assert any("qwen/qwen3-coder:free" in w and "retired" in w for w in warnings), warnings


def test_repo_paths_and_hostnames_are_not_mistaken_for_slugs(repo: Path):
    """`bin/director.py`, `var/circuit_breaker.json`, `models.github.ai/inference`
    are all `x/y`-shaped and must never be reported."""
    problems, warnings = vrr.check_model_slugs_match_code(src(repo))
    noise = [
        m
        for m in problems + warnings
        if "director.py" in m or "circuit_breaker" in m or "models.github.ai" in m
    ]
    assert not noise, noise


# ── check 5: CLAUDE.md counts (RC3) ─────────────────────────────────────────


def test_hooks_count_drift_is_a_problem(repo: Path):
    edit(repo, "CLAUDE.md", "Hooks (15)", "Hooks (99)")
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert any("Hooks (99)" in p and "live count is 15" in p for p in problems), problems


def test_agents_count_drift_is_a_problem(repo: Path):
    edit(repo, "CLAUDE.md", "Agents (17)", "Agents (1)")
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert any("Agents (1)" in p for p in problems), problems


def test_agents_count_ignores_nested_knowledge_files(repo: Path):
    """Regression: a fixture with a nested `<agent>/knowledge/*.md` file must not
    over-count agents — only one path segment under `.claude/agents/` counts."""
    nested = repo / ".claude/agents/finance-specialist/knowledge/extra.md"
    nested.parent.mkdir(parents=True, exist_ok=True)
    nested.write_text("# extra\n", encoding="utf-8")
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert not any("Agents" in p for p in problems), problems


def test_skills_count_is_skipped_when_the_directory_is_absent(repo: Path):
    """The `repo` fixture never copies `.claude/skills/` — a directory the
    validator's own check wants to count but this fixture doesn't mirror should
    be skipped, not reported as a false 'live count is 0' drift."""
    assert not (repo / ".claude/skills").exists()
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert not any("Skills" in p for p in problems), problems


def test_skills_count_drift_is_detected_when_the_directory_is_present(repo: Path):
    skills_dir = repo / ".claude/skills/example"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "SKILL.md").write_text("# example\n", encoding="utf-8")
    assert "Skills (22)" in (repo / "CLAUDE.md").read_text(encoding="utf-8")
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert any("Skills (22)" in p and "live count is 1" in p for p in problems), problems


def test_contextual_rules_count_drift_is_a_problem(repo: Path):
    edit(repo, "CLAUDE.md", "Contextual rules (11)", "Contextual rules (0)")
    problems, _ = vrr.check_claude_md_counts(src(repo))
    assert any("Contextual rules (0)" in p for p in problems), problems


def test_staged_mode_reads_counts_from_the_index(tmp_path: Path):
    for rel in _COPY_TREES:
        shutil.copytree(ROOT / rel, tmp_path / rel, dirs_exist_ok=True)
    for rel in _COPY_FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    run = lambda *a: subprocess.run(  # noqa: E731
        a, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "init")
    edit(tmp_path, "CLAUDE.md", "Hooks (15)", "Hooks (99)")

    worktree_problems, _ = vrr.check_claude_md_counts(vrr.Source(root=tmp_path))
    staged_problems, _ = vrr.check_claude_md_counts(vrr.Source(root=tmp_path, staged=True))
    assert any("Hooks (99)" in p for p in worktree_problems), worktree_problems
    assert not any("Hooks" in p for p in staged_problems), staged_problems


# ── staged-content reads ────────────────────────────────────────────────────


def test_staged_read_uses_the_index_not_the_worktree(tmp_path: Path):
    """`git show :path` semantics: the validator gates what is being committed."""
    run = lambda *a: subprocess.run(  # noqa: E731
        a, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")
    target = tmp_path / "sample.md"
    target.write_text("STAGED\n", encoding="utf-8")
    run("git", "add", "sample.md")
    target.write_text("WORKTREE\n", encoding="utf-8")

    assert vrr.Source(root=tmp_path, staged=True).read("sample.md") == "STAGED\n"
    assert vrr.Source(root=tmp_path, staged=False).read("sample.md") == "WORKTREE\n"
    # Untracked path: staged mode falls back to the worktree rather than crashing.
    (tmp_path / "untracked.md").write_text("NEW\n", encoding="utf-8")
    assert vrr.Source(root=tmp_path, staged=True).read("untracked.md") == "NEW\n"
    assert vrr.Source(root=tmp_path, staged=True).read("nope.md") is None


def test_staged_mode_detects_a_problem_only_present_in_the_index(tmp_path: Path):
    """End-to-end: stage a broken dispatcher, leave the worktree clean, still fail."""
    for rel in _COPY_TREES:
        shutil.copytree(ROOT / rel, tmp_path / rel, dirs_exist_ok=True)
    for rel in _COPY_FILES:
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst)
    run = lambda *a: subprocess.run(  # noqa: E731
        a, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    run("git", "init", "-q")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")

    good = (tmp_path / ".claude/hooks/rules_dispatcher.py").read_text(encoding="utf-8")
    bad = good.replace(
        '"quality":        "common/quality.md",',
        '"quality":        "common/quality.md",\n    "orphan-fixture": "orphan-fixture.md",',
    )
    assert bad != good
    (tmp_path / ".claude/rules_db/orphan-fixture.md").write_text("# orphan\n")
    (tmp_path / ".claude/hooks/rules_dispatcher.py").write_text(bad, encoding="utf-8")
    run("git", "add", "-A")
    (tmp_path / ".claude/hooks/rules_dispatcher.py").write_text(good, encoding="utf-8")

    worktree_problems, _ = vrr.check_registry_reachability(vrr.Source(root=tmp_path))
    staged_problems, _ = vrr.check_registry_reachability(
        vrr.Source(root=tmp_path, staged=True)
    )
    assert not worktree_problems, worktree_problems
    assert any("orphan-fixture" in p for p in staged_problems), staged_problems


# ── check 6: file-path citations (RC11.3) ───────────────────────────────────


def test_nonexistent_backtick_path_is_a_warning_not_a_problem(repo: Path):
    skill_dir = repo / ".claude/skills/fixture-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "# Fixture skill\n\nPlan: `docs/DOES_NOT_EXIST.md`\n", encoding="utf-8"
    )
    problems, warnings = vrr.check_file_citations_exist(src(repo))
    assert not [p for p in problems if "DOES_NOT_EXIST" in p], problems
    assert any("DOES_NOT_EXIST" in w and "does not exist in this repo" in w for w in warnings), warnings


def test_real_backtick_path_is_clean(repo: Path):
    (repo / ".claude/rules_db/fixture-real-path.md").write_text(
        "# Fixture\n\nSee `.claude/rules_db/git-safety.md` for details.\n", encoding="utf-8"
    )
    _, warnings = vrr.check_file_citations_exist(src(repo))
    assert not [w for w in warnings if "fixture-real-path.md" in w], warnings


def test_absolute_path_citation_does_not_escape_repo_root(repo: Path):
    """Mirrors panel_review.py's _citation_exists() regression: an absolute
    path or a `..`-traversal must never resolve outside the source root."""
    assert not vrr._path_citation_exists(src(repo), "/etc/passwd")
    assert not vrr._path_citation_exists(src(repo), "../../../etc/passwd")


# ── CLI contract ────────────────────────────────────────────────────────────


def test_cli_exits_zero_on_the_real_repo(capsys):
    assert vrr.main([]) == 0
    assert "[validate-rules] OK" in capsys.readouterr().out


def test_cli_exits_one_on_problems(repo: Path, capsys):
    edit(repo, ".claude/rules/DYNAMIC.md", "1144–6853", "1999–6853")
    assert vrr.main(["--root", str(repo)]) == 1
    assert "problem(s)" in capsys.readouterr().out


def test_cli_rejects_root_without_argument(capsys):
    assert vrr.main(["--root"]) == 2


def test_warnings_never_cause_a_nonzero_exit(repo: Path, capsys):
    edit(
        repo,
        "bin/core/openrouter_wrapper.py",
        '"git-specialist":    ("ollama", "qwen2.5-coder:7b"),',
        '"git-specialist":    ("ollama", "vendor/undocumented-model-1b"),',
    )
    assert vrr.main(["--root", str(repo)]) == 0
    assert "WARNING" in capsys.readouterr().out
