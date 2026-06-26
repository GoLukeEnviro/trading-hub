# Dirty Worktree Owner Check — 2026-06-15T09:00:02+00:00Z

Status: **YELLOW** | Operation Level: L1_READ_ONLY_DIRTY_WORKTREE_OWNER_CHECK
Repo: `/home/hermes/projects/trading` — read-only classification of 4 dirty/untracked entries.

## 1. Executive Verdict
**YELLOW** — Worktree state is classifiable. No mutations performed.
- 4 entries: 2 tracked-modified, 2 untracked.
- No secrets found in redacted fingerprints.
- One file needs content review before action: `orchestrator/reports/canonical_trading_status_latest.json` (tracked JSON).
- Recommended hygiene: commit 3 files, gitignore 1 file.
- No branch/PR merge until worktree is clean.

## 2. Current Worktree State
HEAD: `{'exit': 0, 'stdout': '# Ledger Integrity Watchdog Run — 2026-06-15 2026-06-15T08-29-45\n\n## Ergebnis\n\n| Check | Status | Detail |\n|---|---|---|\n| Sources Check | WARNING (Missing: freqai-rebel) | 4 active bots, 3 ledger keys |\n| Drawdown Check | WARNING (3.49% > 3%) | LEDGER current_drawdown = 3.4935% |\n| Live Gap | INFO | Δ = 1062.6403563622998 USDT (LIVE 3498.27 vs LEDGER 2435.6296436377) |\n\n## Aktionen ausgeführt\n\n- Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)\n- Canonical Status aktualisiert (JSON + MD + current-op-state)\n- Report aktualisiert: docs/context/ledger-watchdog-2026-06-15.md\n\n## Daten-Snapshot\n\n```\nLEDGER sources : [\'baseline_v1_freqforge\', \'freqforge_canary_v1\', \'regime_hybrid_dryrun\']\nActive bots    : [\'freqai-rebel\', \'freqforge\', \'freqforge-canary\', \'regime-hybrid\']\nMissing        : [\'freqai-rebel\']\nDrawdown       : 3.4935% (threshold 3%)\nLIVE-LEDGER Δ  : 1062.6403563622998 USDT\n```\n\n## Empfohlener nächster Schritt\n\nTier-2: ledger-collector needs source_key for missing bot(s): freqai-rebel; Tier-2: drawdown approaching R2 threshold; review fleet_risk_auto_params\n\n## Tier-Eskalation\n\n- **Tier 2 erforderlich** für Source-Vervollständigung\n- Begründung: fehlende ledger-Key(s) verzerren aggregierte Equity Drawdown überschreitet R2-Threshold\n\n## Meta\n- Run timestamp: 2026-06-15T08:29:45.587352+00:00\n- Fingerprint: {"dd_exceeds": true, "dd_value": 0.034935, "live_ledger_delta": 1062.64, "missing": ["freqai-rebel"]}\n- Log: /opt/data/profiles/orchestrator/logs/ledger_integrity_watchdog.log\n- State: /opt/data/profiles/orchestrator/state/ledger_integrity_watchdog_state.json\n', 'stderr': ''}`
`git status --short --branch`:
  `## main...remotes/origin/main`
  ` M docs/state/canonical-trading-status.md`
  ` M orchestrator/reports/canonical_trading_status_latest.json`
  `?? HERMES_METRICS.json`
  `?? docs/context/ledger-watchdog-2026-06-15.md`
  `?? docs/reports/git-tree-pr-integration-audit-20260615T084500Z.json`
  `?? docs/reports/git-tree-pr-integration-audit-20260615T084500Z.md`

## 3. Dirty Entry Matrix
| # | Path | Git Status | Type | Lines | Risk | Secrets? | Recommended Action |
|---|---|---|---|---|---|---|---|
| 1 | `docs/state/canonical-trading-status.md` | tracked_modified | markdown | 116 | MEDIUM | false | **COMMIT_LATER** |
| 2 | `orchestrator/reports/canonical_trading_status_latest.json` | tracked_modified | json | 518 | MEDIUM | unknown | **REVIEW_CONTENT_FIRST** |
| 3 | `HERMES_METRICS.json` | untracked | json | 110 | LOW | false | **IGNORE_LATER** |
| 4 | `docs/context/ledger-watchdog-2026-06-15.md` | untracked | markdown | 40 | LOW | false | **COMMIT_LATER** |

## 4. Ownership Evidence
| Path | Likely Owner | Grep Refs | Reason |
|---|---|---|---|
| `docs/state/canonical-trading-status.md` | Hermes orchestrator trading-status pipeline | 35 | Tracked file committed in main. Modified content is a scheduled trading-status report. No secrets detected in first 60 lines. Should be committed as hygiene artifact. |
| `orchestrator/reports/canonical_trading_status_latest.json` | Hermes orchestrator trading-status pipeline | 21 | Tracked JSON report — may embed ephemeral runtime/exchange status fields. Read first 60 lines: structured JSON. Review contents before committing. If purely status metadata, COMMIT_LATER; if dynamic runtime/exchange data, IGNORE_LATER or MOVE_OUTSIDE_REPO_LATER. |
| `HERMES_METRICS.json` | Hermes metrics collector / runtime | 9 | Untracked, not in .gitignore. Auto-generated metrics JSON with timestamps and counters. No secrets visible. Add to .gitignore or move generator path outside repo. |
| `docs/context/ledger-watchdog-2026-06-15.md` | Hermes watchdog cron / ledger cron job | 6 | Untracked context document. Markdown with operational memory content. Consistent with docs/context/ conventions. Should be committed or archived. |

## 5. Tracked vs Untracked vs Ignored
- `docs/state/canonical-trading-status.md`: **tracked_modified**
- `orchestrator/reports/canonical_trading_status_latest.json`: **tracked_modified**
- `HERMES_METRICS.json`: **untracked**
- `docs/context/ledger-watchdog-2026-06-15.md`: **untracked**

## 6. Redacted Fingerprints

### docs/state/canonical-trading-status.md
- SHA256: `a165768fd3f72dacee3c1408f6021bdba02f61cf94e6668192e66e5ece09eee4  docs/stat` | Lines: 116
  `# Canonical Trading Status`
  ``
  `Generated at: 2026-06-15T08:29:45.588167+00:00`
  ``
  `Verdict: WARNING`
  ``

### orchestrator/reports/canonical_trading_status_latest.json
- SHA256: `985dd0006d9a6df0399d4efb1e7e0183df1bb1e7f245e4e288f54878b8e7d8ac  orchestra` | Lines: 518
  `{`
  `  "schema_version": "1.0",`
  `  "generated_at": "2026-06-15T08:29:45.588167+00:00",`
  `  "overall_status": "WARNING",`
  `  "scores": {`
  `    "runtime_health_score": 92,`

### HERMES_METRICS.json
- SHA256: `550713060d327e0630585051805ae1e692cba95a2660728c8d2da4451cc7e9ad  HERMES_ME` | Lines: 110
  `[`
  `  {`
  `    "session_id": "auto_20260615_081652",`
  `    "timestamp": "2026-06-15T08:16:52.035664+00:00",`
  `    "duration_seconds": 0,`
  `    "tool_calls_total": 44,`

### docs/context/ledger-watchdog-2026-06-15.md
- SHA256: `046bf1bd49410ac52a38d8eec8f56227cb6ec847315bf89c3c5b08aa7e9623e5  docs/cont` | Lines: 40
  `# Ledger Integrity Watchdog Run — 2026-06-15 2026-06-15T08-29-45`
  ``
  `## Ergebnis`
  ``
  `\| Check \| Status \| Detail \|`
  `\|---\|---\|---\|`

## 7. Risk Assessment
- `docs/state/canonical-trading-status.md` → **MEDIUM**: Tracked file committed in main. Modified content is a scheduled trading-status report. No secrets detected in first 60 lines. Should be committed as hygiene artifact.
- `orchestrator/reports/canonical_trading_status_latest.json` → **MEDIUM**: Tracked JSON report — may embed ephemeral runtime/exchange status fields. Read first 60 lines: structured JSON. Review contents before committing. If purely status metadata, COMMIT_LATER; if dynamic runtime/exchange data, IGNORE_LATER or MOVE_OUTSIDE_REPO_LATER.
- `HERMES_METRICS.json` → **LOW**: Untracked, not in .gitignore. Auto-generated metrics JSON with timestamps and counters. No secrets visible. Add to .gitignore or move generator path outside repo.
- `docs/context/ledger-watchdog-2026-06-15.md` → **LOW**: Untracked context document. Markdown with operational memory content. Consistent with docs/context/ conventions. Should be committed or archived.

## 8. Recommended Later Actions Per File
### `docs/state/canonical-trading-status.md` → **COMMIT_LATER**
Tracked file committed in main. Modified content is a scheduled trading-status report. No secrets detected in first 60 lines. Should be committed as hygiene artifact.
### `orchestrator/reports/canonical_trading_status_latest.json` → **REVIEW_CONTENT_FIRST**
Tracked JSON report — may embed ephemeral runtime/exchange status fields. Read first 60 lines: structured JSON. Review contents before committing. If purely status metadata, COMMIT_LATER; if dynamic runtime/exchange data, IGNORE_LATER or MOVE_OUTSIDE_REPO_LATER.
### `HERMES_METRICS.json` → **IGNORE_LATER**
Untracked, not in .gitignore. Auto-generated metrics JSON with timestamps and counters. No secrets visible. Add to .gitignore or move generator path outside repo.
### `docs/context/ledger-watchdog-2026-06-15.md` → **COMMIT_LATER**
Untracked context document. Markdown with operational memory content. Consistent with docs/context/ conventions. Should be committed or archived.

## 9. Explicit Non-Actions
- No git add, commit, restore, reset, clean, stash, merge, rebase, push, pull executed.
- No package install, docker/compose, systemctl, crontab, scheduler, service mutation executed.
- No secrets printed or exposed. All outputs redacted through regex patterns.
- HERMES_METRICS.json was only read via head and sha256sum; not modified, moved, staged, or committed.
- No files were moved, renamed, deleted, or changed in any way.

## 10. Exact Next Step
**Run a gated hygiene step: (a) REVIEW_CONTENT_FIRST for orchestrator/reports/canonical_trading_status_latest.json — visually inspect the JSON contents to confirm it contains only status metadata and no runtime/exchange secrets; (b) if approved, commit all 4 files in a dedicated hygiene commit; (c) if HERMES_METRICS.json is ephemeral, add to .gitignore instead of committing. THEN proceed to branch/PR work.**