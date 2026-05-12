# Git Hygiene — Trading Hub

This document describes what is tracked, what is ignored, and why.

## Tracked Files

### Strategy Source Code (highest priority)
All `.py` files matching these patterns are explicitly un-ignored:
- `**/strategies/**/*.py`
- `**/strategy/**/*.py`
- `**/*strategy*.py`
- `**/research/**/*.py`

These negation rules in `.gitignore` ensure strategy files are never
accidentally excluded, even if their parent directory is ignored.

### Configuration
- `docker-compose*.yml` — service definitions
- `Dockerfile` — container builds
- `config*.example.*` — sanitized config templates
- `pyproject.toml`, `requirements*.txt` — dependency manifests

### Documentation
- `docs/**/*.md` — all documentation
- Root-level identity files: `SOUL.md`, `AGENTS.md`, `ORCHESTRATOR_CHARTER.md`

### Tooling
- `tools/**/*.py` — shadow evaluator, utilities
- `scripts/**/*.sh`, `scripts/**/*.py` — automation
- `orchestrator/**/*.py`, `orchestrator/**/*.md` — orchestrator scripts and docs

## Ignored Files (never committed)

### Security
- `.env`, `.env.*` — credentials and secrets
- `*.pem`, `*.key` — TLS keys and certificates

### Runtime / Generated
- `var/` — shadow decisions, state files
- `logs/`, `*.log` — log output
- `output/`, `cache/` — signal history, LLM cache
- `*.sqlite`, `*.db` — Freqtrade trade databases

### Large Binaries
- `freqtrade/shared/images/` — Docker image tarballs (~912 MB)
- `backups/` — cold archives (~186 MB)
- `.venv/` — Python virtual environments (~1 GB)
- `*.fthypt` — Freqtrade hyperopt result binaries
- `*.feather`, `*.parquet`, `*.pkl` — data files

### Nested Repositories
- `ai-hedge-fund-crypto/` — upstream clone, managed separately
- `weatherhermes_persistent/`, `weatherhermes_backup/` — unrelated project

## Verification

Before each commit, verify:
```bash
# Check for accidentally staged secrets
git diff --cached --name-only | grep -iE '\.env|secret|token|\.pem|\.key'

# Check for large staged files (>1 MB)
git diff --cached --name-only | xargs -I{} sh -c 'test $(stat -c%s "{}" 2>/dev/null || echo 0) -gt 1048576 && echo "LARGE: {}"'

# Verify strategy files are tracked
git ls-files | grep -i strategy | wc -l
```

## Adding New Content

When adding new directories or file types:
1. Check `.gitignore` — is the pattern excluded?
2. Add a negation rule (`!pattern`) if the file type should be tracked
3. Run `git add -n <path>` to dry-run before staging
4. Never force-add ignored files with `git add -f`
