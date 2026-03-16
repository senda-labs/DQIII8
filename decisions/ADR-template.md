# ADR-XXX — [Title]

**Date:** YYYY-MM-DD
**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-YYY
**Project:** jarvis-core | content-automation | all
**Deciders:** Iker, JARVIS

---

## Context

[What is the problem or situation that requires a decision?
What constraints, trade-offs, or forces are at play?]

## Decision

[What was decided? Be specific — name models, tools, file paths, patterns.]

## Consequences

**Positive:**
- [benefit]

**Negative / Trade-offs:**
- [cost or limitation]

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| [option A] | [reason] |

---

## Invariants

Invariants are machine-checked by `bin/adr-check.py` against the codebase.
Only ADRs with `Status: Accepted` are checked.

```yaml
invariants:
  - id: "ADR-XXX-I1"
    description: "[what this check enforces]"
    paths:
      - "path/to/file.py"
    must_contain:
      - "expected_string"
    must_not_contain:
      - "forbidden_string"
    message: "Violation: [explanation of what went wrong and how to fix it]"
```

---

*Template — replace all bracketed placeholders before marking Accepted.*
