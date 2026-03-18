# Contributing to DQIII8

Thanks for your interest in contributing.

## Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run `./install.sh` to set up the development environment
4. Make your changes

## Code Standards

- **Python**: Black formatter, pathlib for paths, `encoding="utf-8"` on all `open()` calls
- **Commits**: Conventional commits format — `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- **Files**: Keep under 800 lines. Extract utilities when files grow.
- **Security**: Never commit secrets, API keys, or credentials. Use `.env` for configuration.

## Pull Requests

1. One PR per feature or fix
2. Include a clear description of what changed and why
3. Ensure no secrets are included in the diff
4. Test your changes locally before submitting

## Reporting Issues

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your OS and Python version

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
