# Code Quality & Security

## Coding style
- Immutability: ALWAYS create new objects, NEVER mutate in-place
- Files: 200-400 lines typical, 800 max; organize by feature/domain
- Error handling: explicit at every level; never silently swallow; user-friendly messages in UI, detailed logs server-side
- Validate at system boundaries only (user input, external APIs); trust internal code

## Code quality checklist
Before marking work complete:
- [ ] Readable, well-named, functions < 50 lines
- [ ] No deep nesting (>4 levels), no hardcoded values
- [ ] Proper error handling, no mutation

## Security — mandatory before ANY commit
- [ ] No hardcoded secrets (API keys, passwords, tokens)
- [ ] User inputs validated; SQL parameterized; HTML sanitized
- [ ] Error messages don't leak sensitive data

## Secret management
- NEVER hardcode secrets — always env vars or secret manager
- Rotate any secrets that may have been exposed
- On security issue: STOP → `code-reviewer` agent (Opus adversarial pass) → fix CRITICAL before continuing
