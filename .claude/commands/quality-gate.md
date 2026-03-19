# /quality-gate — On-Demand Quality Pipeline

Run the DQIII8 quality pipeline for a file or directory scope.

## Usage

```
/quality-gate [path|.] [--fix] [--strict]
```

- Default target: current directory (`.`)
- `--fix`: allow auto-format/fix where supported (Black, isort)
- `--strict`: treat warnings as errors

## Pipeline

Run these phases in order. Stop on first failure unless `--strict` is passed.

### Phase 1 — Format (Black)

```bash
black --check [path] 2>&1 | tail -15
# With --fix:
black [path]
```

### Phase 2 — Imports (isort, if installed)

```bash
isort --check-only [path] 2>&1 | head -10
# With --fix:
isort [path]
```

### Phase 3 — Lint (ruff)

```bash
ruff check [path] --select E,F,W 2>&1 | head -30
```

Fail on E and F codes. W codes: report only.

### Phase 4 — Tests (pytest)

```bash
python3 -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
```

With `--strict`: fail on warnings too (`-W error`).

### Phase 5 — Security Quick-Scan

```bash
grep -rn "shell=True" [path] --include="*.py" | grep -v "#\|test_"
grep -rn "f['\"].*SELECT\|f['\"].*INSERT\|f['\"].*DELETE" [path] --include="*.py"
```

Both must return empty.

## Output Format

```
QUALITY GATE — [path]
=====================
Phase 1 Format:   PASS
Phase 2 Imports:  PASS / SKIP (isort not installed)
Phase 3 Lint:     PASS / FAIL — 3 errors
Phase 4 Tests:    PASS — 12 passed in 0.8s
Phase 5 Security: PASS

RESULT: PASS / BLOCKED
```

## Arguments

- `path`: file or directory (default `.`)
- `--fix`: auto-apply Black + isort fixes
- `--strict`: fail on warnings

## When to Run

- Before every commit
- After `python-specialist` hands off code
- After refactoring (in place of running phases manually)
- As part of `/checkpoint create` flow

## Related

- `verification-loop` skill — more detailed phase-by-phase protocol
- `tdd-workflow` skill — write tests before running this
- `security-review` skill — deeper checklist for auth/secrets code
