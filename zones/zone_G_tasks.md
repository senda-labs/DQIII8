# Zone G — Tasks
> Updated: 2026-06-02

---

## What it covers
`tasks/` directory — audits, benchmarks, research, results, and the full system map.

---

## Structure (post-reorganization 2026-06-02)

```
tasks/
├── FULL_SYSTEM_MAP.md    ← linked from CLAUDE.md (path must not change)
├── lessons.md            ← accumulated learnings
├── audit/                ← security audit outputs (hardcoded in skills — DO NOT RENAME)
├── benchmarks/           ← benchmark runs + reports (absorbed benchmark_reports/)
├── research/             ← research queue (renamed from research_queue/)
└── results/              ← test/run results (absorbed test_results/)
```

**WARNING:** `tasks/audit/` is hardcoded in `.claude/skills/red-team/`, `blue-team/`, `security-cycle/`. Never rename it.

---

## Key Files

| File | Contents |
|---|---|
| `tasks/FULL_SYSTEM_MAP.md` | Annotated full system map (2026-03-23 snapshot) |
| `tasks/lessons.md` | Lessons learned, anti-patterns, recurring fixes |
| `tasks/audit/` | Red-team reports, blue-team reviews |
| `tasks/benchmarks/` | Benchmark JSON + logs + reports |
| `tasks/research/` | Research queue articles and papers |
| `tasks/results/` | Test runs, execution results, status snapshots |

---

## Usage

```bash
ls tasks/audit/           # latest security audits
ls tasks/benchmarks/      # benchmark results
ls -t tasks/results/      # most recent run results
```

---

## Cross-zone Links
- Audit skills → [[zone_B_extensions]]
- Session outputs → [[zone_I_ops]]
