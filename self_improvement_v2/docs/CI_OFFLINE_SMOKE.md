# CI Offline Smoke

> **SI v2 Offline Smoke Workflow** — GitHub Actions CI for deterministic offline validation.

---

## What It Does

The `si-v2-offline-smoke.yml` workflow runs on every push to `main` or `feat/si-v2-**` branches, and on pull requests targeting `main`.

It executes these checks in order:

| Step | What | Fails On |
|------|------|----------|
| 1. Python compile | `python -m compileall .` | Syntax errors, import errors |
| 2. JSON parse | `python -m json.tool` on all `.json` files | Invalid JSON |
| 3. SI v2 pipeline tests | `pytest -k "rainbow or evidence or regime or attribution or quality or manifest or readiness or episode"` | Test failures |
| 4. Ruff lint | `ruff check .` | Style violations (unused imports, ambiguous chars, etc.) |

## What It Does NOT Do

- ❌ No Docker containers
- ❌ No Freqtrade API calls
- ❌ No Telegram or exchange connections
- ❌ No secrets or credentials
- ❌ No runtime probing
- ❌ No production Shadowlock writes
- ❌ No live trading checks (out of scope for offline CI)

## How to Trigger

Push to any `feat/si-v2-**` branch, or open a PR against `main`. The workflow runs automatically.

## Expected Outcome

A green checkmark means:

- All Python code compiles
- All JSON files are valid
- The SI v2 offline pipeline tests pass (~370+ tests)
- Ruff lint passes

A red X means one or more steps failed. Inspect the step output in the GitHub Actions UI.

## Maintenance

The workflow lives at `.github/workflows/si-v2-offline-smoke.yml`.

To add new test categories, update the `pytest -k` filter string.
To add new checks, add a new step before or after the existing ones.

---

*Workflow added as part of #120 — Offline Pipeline Smoke Workflow*
*Last updated: 2026-06-10*
