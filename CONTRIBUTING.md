# Contributing to DQIII8

Thanks for your interest in contributing.

## Reporting Bugs

Open a [GitHub issue](https://github.com/senda-labs/DQIII8/issues) with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your OS and Python version

## Proposing Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run `bash install.sh` to set up the development environment
4. Make your changes
5. Open a pull request against `main`

## Code Style

- **Formatter**: Black (runs automatically via post-commit hook)
- **Paths**: Always use `pathlib.Path()`, never string concatenation
- **Encoding**: Always specify `encoding="utf-8"` in `open()` calls
- **Files**: Keep under 800 lines. Extract utilities when files grow.
- **Security**: Never commit secrets, API keys, or credentials. Use `config/.env`.

## Commit Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add confidence gate for selective RAG
fix: entity extraction ignores domain-context prefix
refactor: extract working_memory to separate module
docs: update install instructions
test: add smoke test for task relevance reranking
chore: nightly maintenance — 2026-03-23
```

## Pull Request Requirements

1. All tests must pass before submitting:
   ```bash
   python3 -m pytest tests/ -q
   # Expected: 0 failures
   ```
2. One PR per feature or fix
3. Include a clear description of what changed and why
4. Ensure no secrets appear in the diff (`git ls-files | grep -i '\.env'` must be empty)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
