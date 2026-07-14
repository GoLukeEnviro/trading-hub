# Codex Cloud A1 Writer Governance — Issue #592

**Timestamp:** 2026-07-14T14:45:00Z
**Execution class:** A1 repository-only
**Branch:** `docs/codex-cloud-a1-writer-contract`
**Status:** READY_FOR_REVIEW

## Goal

Define the Codex Cloud PR-only A1 writer path in `AGENTS.md` so Codex Cloud
can create reviewable A1 branches and PRs without weakening the HermesTrader
host writer contract (`repo_writer.py`, host lock, isolated worktree).

## Evidence reviewed

- `AGENTS.md` and `SOUL.md` — operator identity, safety rules, writer contract
- `docs/state/current-operational-state.md` — confirms PR #591 merged, Codex
  Cloud backlog exists as non-authoritative track
- Issue #592 — full scope and acceptance criteria
- PR #608 (merged) — already added `codex/` branch prefix to repo writer code
  and roadmap-tick.md; governance section in AGENTS.md was the remaining gap
- `orchestrator/scripts/repo_writer.py` — host lock + isolated worktree contract
- `commands/trading-hub-roadmap-tick.md` — already updated with `codex/` prefix

## Change summary

Added a new **Codex Cloud A1 writer path** section to `AGENTS.md` under the
existing "Repository writer contract" section. The section:

1. States that Codex Cloud **cannot** acquire the HermesTrader host lock and
   therefore has a separate, PR-only A1 writer path.
2. Defines a comparison table showing the two non-overlapping writer domains
   (HermesTrader vs. Codex Cloud) with their respective lock, worktree, branch
   prefix, and direct-to-main rules.
3. Lists 8 explicit Codex Cloud A1 writer rules covering:
   - One atomic issue, one branch, one PR, one report
   - Open PR inspection before starting
   - Branch naming convention (`codex/{feature}{date}`)
   - PR-only, no direct-to-main, no force-push, no history rewrite
   - No runtime mutation (VPS, Docker, Cron, exchange, secrets, live capital)
   - Hard blockers (conflicting PR, ambiguous truth, missing toolchain,
     secret exposure, A2/A3 scope without approval)
   - Cleanup procedure for abandoned/superseded PRs
   - Regression check proving host writer contract is not weakened
4. The HermesTrader host writer contract (`repo_writer.py`, host lock,
   isolated worktree) is **unchanged** — `BLOCKED_BY_ACTIVE_REPO_WRITER`
   remains a hard stop for HermesTrader sessions.

## Safety assessment

- No Docker, VPS, container, scheduler, exchange, secret, or runtime mutation.
- No trading strategy/config behavior changed.
- No `dry_run=false`, live order, risk increase, RiskGuard weakening, or
  kill-switch bypass.
- The change is repository-only governance documentation.
- The HermesTrader host writer contract is explicitly preserved and
  cross-referenced.

## Validation

Commands executed from the isolated worktree:

1. `git status --porcelain` — clean (0 uncommitted changes after commit)
2. `git diff --check` — PASS (no whitespace errors)
3. `python3 scripts/secret_scan.py --tracked` — PASS
4. `python3 -m compileall orchestrator tests scripts` — PASS
5. `python3 -m pytest tests/test_repo_writer.py -q` — PASS (34 passed)

## Rollback

Revert this PR. That removes the Codex Cloud A1 governance section from
`AGENTS.md` and the matching report, restoring the previous governance
state. The `codex/` branch prefix in `repo_writer.py` and
`roadmap-tick.md` (from PR #608) would remain but would lack the
governance context.

## Next task after merge

After Issue #592 is merged, the next unblocked Codex Cloud backlog task is
Issue #606 (reproducible Codex Cloud environment), subject to the same
single-active-PR and writer-contract governance.
