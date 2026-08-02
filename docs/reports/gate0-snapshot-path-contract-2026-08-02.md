# Gate-0 Snapshot Path Contract — Native Default

**Date:** 2026-08-02
**Author:** Hermes (trading-hub-orchestrator)
**Issue:** #684
**Branch:** `fix/gate0-snapshot-path-contract-2026-08-02`
**Base:** `72421de2fecf9399732bdce1754124332bcee171` (origin/main)

## Observation

`gate0_evaluation_integration.py` hardcoded `SNAPSHOT_DIR = Path("/opt/data/gate0-snapshot")`.
On the native host this path **does not exist** (verified: no directory, no symlink,
no bind mount — `ls`, `stat`, `findmnt` all negative). The real, hash-verified
Bitget Gate-0 snapshot (156,489 candles, BTC/ETH/SOL 15m USDT-FUTURES) lives at
`/opt/data/hermes/gate0-snapshot/`.

## Root Cause

The snapshot was planned under `/opt/data/gate0-snapshot` in the A2 contract
(issue #651, container-era layout) but materialized under the profile path
`/opt/data/hermes/gate0-snapshot`. The hardcoded constant was never reconciled
with the native filesystem.

## Fix

Replaced the hardcoded constant with a validated `snapshot_dir` contract:

- `DEFAULT_SNAPSHOT_DIR = Path("/opt/data/hermes/gate0-snapshot")` — native canonical default
- `resolve_snapshot_dir(snapshot_dir: Path | None = None) -> Path` — fail-closed
  (`SNAPSHOT_DIR_NOT_FOUND` RuntimeError when the directory is missing); explicit
  override supported
- `_snapshot_file(snapshot_dir: Path, filename: str) -> Path` — path confinement
  (`SNAPSHOT_PATH_ESCAPE` on traversal/absolute escape)
- `load_snapshot_manifest`, `load_snapshot_candles`, `compute_total_snapshot_hash`,
  `compute_benchmark_hash` and `build_manifest_v3` accept `snapshot_dir` and thread it
  through

No snapshot data was written, moved, or modified. Historical reports (c1/c4) were
not rewritten.

## Validation

- New tests `TestSnapshotDirContract` (8): native default, valid resolve, missing
  dir fail-closed, traversal/absolute rejection, manifest load without candle
  reads (no implicit holdout/candle access), minimal gz candle load, hash
  computation with explicit dir
- `test_gate0_evaluation_integration.py`: 17/17 passed (9 existing + 8 new)
- Combined Gate-0 suite from repo root: 154/154 passed (C5.1 19, C5.3 46,
  C5.4 47, eval_bundle 25, gate0_integration 17)
- Ruff clean on changed files; `git diff --check` clean
- CI: main-gate ✅, offline-smoke ✅, governance-consistency ✅

## Safety

```
holdout_inspected=NO
backtest_executed=NO
runtime_mutation=NO
live_trading=NO
snapshot_data_mutated=NO
```

## Changed Files

- `self_improvement_v2/src/si_v2/research/gate0_evaluation_integration.py` — snapshot dir contract
- `self_improvement_v2/tests/test_gate0_evaluation_integration.py` — 8 new contract tests
- `docs/state/current-operational-state.md` — snapshot path row corrected
