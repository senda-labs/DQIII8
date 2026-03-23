# my-projects/

This directory is the home for your personal projects built on top of DQIII8.

## Usage

Create a subdirectory per project:

```
my-projects/
├── my-content-pipeline/
├── my-finance-tracker/
└── my-research-agent/
```

Each project can have its own:
- `.claude/agents/` — project-specific agent MDs with custom knowledge
- `config/` — project-specific config (excluded from git)
- `README.md` — project documentation

## Connecting your workspace

If you use the private workspace pattern (`dqiii8-workspace`), run:

```bash
bash /path/to/dqiii8-workspace/overlay.sh
```

This replaces this directory with a symlink to your workspace's `my-projects/`.

## Note

`my-projects/*/` is excluded from the public repo via `.gitignore`.
Never commit personal project files to `senda-labs/DQIII8`.
