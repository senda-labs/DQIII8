# Code Quality & Security

Generic craft rules (function length, nesting depth, immutability, PEP 8) are model-prior
knowledge and are not restated here — every line in this file is injected on **every `.py`
edit**, so it only earns its place if it is DQIII8-specific. Python conventions that *are*
project-specific: `python.md` (co-injected on the same trigger), including the secrets rule.

## Before marking work complete
- Errors: explicit at every level, never silently swallowed. A hook is the one exception —
  it must degrade to APPROVE rather than block (`02_hooks_and_permissions.md`).
- Validate at system boundaries only (user input, external APIs); trust internal code.
- Error messages must not leak secrets, absolute VPS paths or DB contents.

## On a security issue
STOP → `code-reviewer` agent (Opus adversarial pass) → fix CRITICAL before continuing.
Any secret that may have been exposed is rotated, not just removed from the file —
git history keeps it otherwise (see the 2026-08 Telegram/Netcup leaks).
