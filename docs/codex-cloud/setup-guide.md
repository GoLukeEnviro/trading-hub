# Codex Cloud — Reproducible Environment Setup Guide

> **Issue:** #606
> **Status:** ✅ Active
> **Execution class:** A1 — Repository-only (docs, no runtime mutation)

## Purpose

This guide documents how to configure a reproducible Codex Cloud environment
for `GoLukeEnviro/trading-hub` so A1 tasks can install the repository toolchain
and run the required validation without runtime or secret access.

## Prerequisites

- Codex Cloud agent with **Python 3.11** pinned
- Repository checkout at the selected branch or commit
- **Internet off by default** — enable only issue-specific limited access
- No exchange, VPS, Docker, or live secrets available during the agent phase

## Setup commands

Run these in the repository root after checkout:

```bash
# 1. Install root tooling with dev dependencies
python3 -m pip install --upgrade pip
python3 -m pip install -e ".[dev]"

# 2. Install SI-v2 dependencies
python3 -m pip install -e "./self_improvement_v2"
```

> **Note:** If `uv` is available and `uv.lock` is present, the locked
> environment can be reproduced with:
> ```bash
> uv sync --frozen
> ```
> This installs both root and SI-v2 requirements from the lock file.
> Use `uv` only when the lock file is compatible with the cloud environment.

## Validation baseline

After setup, run the following commands to verify the environment:

```bash
# 1. Secret scan (no secrets in tracked files)
python3 scripts/secret_scan.py --tracked

# 2. Compile check (all modules parse correctly)
python3 -m compileall bridge primo shadowlock intelligence orchestrator tests scripts

# 3. Root tests
python3 -m pytest tests -q

# 4. SI-v2 tests (checkout-relative PYTHONPATH)
PYTHONPATH=self_improvement_v2/src:self_improvement_v2 python3 -m pytest self_improvement_v2/tests -q
```

> **Important:** The historical command `PYTHONPATH=/home/hermes/projects/trading`
> must NOT be copied into Codex Cloud. Use the checkout-relative `PYTHONPATH`
> shown above. The `/home/hermes/projects/trading` path is specific to the
> HermesTrader host and does not exist in Codex Cloud.

## Cloud settings

| Setting | Value |
|---------|-------|
| Base branch/commit | Selected per-issue (pinned SHA, not moving branch) |
| Python version | 3.11 pinned |
| Internet access | Off by default; enable only issue-specific limited access |
| Secrets | Not available during agent phase |
| Runtime access | None (no VPS, Docker, exchange, or live secrets) |

## Acceptance criteria

- [ ] Fresh cloud environment installs successfully from pinned repository metadata
- [ ] All baseline commands pass (or each unsupported command has a documented reason)
- [ ] Codex reports the loaded root/scoped `AGENTS.md` instruction chain
- [ ] No runtime file, database, log, secret, or nested private repository is required
- [ ] Setup and validation commands match this guide without divergence

## Maintenance

If cached environments need deterministic dependency refresh, add a maintenance
script under `scripts/` that re-runs the setup commands. Do not introduce a new
dependency-management path without evidence.
