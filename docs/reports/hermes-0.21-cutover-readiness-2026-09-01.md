# Hermes 0.21 CUTOVER_READY evidence — 2026-09-01

## Beobachtung

- Issue: parent #699, atomic child #718.
- Production stayed `/opt/hermes-native/current ->
  /opt/hermes-native/releases/0.19.0`; the live binary reports Hermes Agent
  v0.19.0. No production state migration, service restart, symlink switch or
  cutover was executed.
- The qualifying backup/restore proof remains verified and is bound to fresh
  Restic snapshot
  `781d93e19f7ee4467417e60098305c10a07651c7cd07b87b7939d32a4c2c36af`.
- The exact official stable target is Hermes Agent `0.21.0`, tag
  `v2026.8.31`, commit
  `29112bef099274229cadff79cdff7bf7b99c4b77`. The upstream annotated tag is
  not cryptographically verified. Supply-chain binding uses the exact tag,
  commit, source/archive hashes and reproducible deployment inputs.
- Side-by-side staging created `/opt/hermes-native/releases/0.21.0`. The
  staged binary reports Hermes Agent v0.21.0, release 2026.8.31 and Python
  3.13.14. The release-local dashboard runtime is Node 24.20.0 / npm 11.19.0.
- The release manifest records source archive SHA-256
  `b80dc110dc3f7fcbf7978f5f7c82c99022671acd2cdc7fdbd6ec5bfae6409e2a`,
  `uv.lock` SHA-256
  `383cd8f98ec23dc3fe4cf63759ec73be5a869cc953f068b4e79ec4e8ed00287d`,
  and Node archive SHA-256
  `2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2`.
- The isolated qualifying state probe is
  `/var/lib/hermes-native-change-c/probe/20260901T114021.1265427/`. The
  earlier failed config-drift probe is retained separately and was not reused
  as proof.
- The backend probe bound only `127.0.0.1:29119`, returned version 0.21.0
  from `/api/health` and `/api/status`, and left no process or listener after
  its clean stop.
- Gateway, dashboard, desktop serve and Root Executor remained active with
  `NRestarts=0`. Expected listeners remained 127.0.0.1:9119 and the Tailscale
  address on port 19119; ports 29119 and 8642 were absent after the probe.
- Exactly five `hermestrader-dryrun-*` containers were healthy. All four
  mounted Freqtrade runtime configurations were verified `dry_run=true`.

Commands used for runtime evidence included:

```text
readlink -f /opt/hermes-native/current
/opt/hermes-native/releases/0.21.0/bin/hermes --version
git -C <staged-source> rev-parse HEAD
git -C <staged-source> rev-list -n1 v2026.8.31
uv lock --check
uv sync --locked --python 3.13 --extra all
npm ci --workspace web --include-workspace-root=false
npm run build --workspace web
hermes-native-change-c.sh probe
hermes-native-change-c.sh rollback-probe
hermes-native-change-c.sh readiness
systemctl show ... -p ActiveState -p NRestarts
docker ps --filter name=hermestrader-dryrun-
ss -ltnp
```

## Ursache

The previous Change-C implementation still targeted 0.20.0, defaulted state
to the legacy `/home/hermes/.hermes`, fetched only a branch/tag checkout,
installed dependencies through unlocked editable `uv pip install`, did not
build the dashboard, had no isolated migration/backend probe, and restored
only the release symlink during rollback. It therefore could not support the
0.21 safety contract even after the backup gate passed.

The first isolated runtime probe also correctly failed closed: upstream's
33→39 config migration replaced three explicitly configured operating values
with new defaults. The corrected probe preserves only the canonical structured
values (`technical`, `50`, `all`) and intentionally does not restore the old
duplicated personality system-prompt text.

## Änderungen

- `scripts/hermes-native-change-c.sh`
  - exact 0.21.0/tag/commit pin and double verification;
  - canonical root/profile state paths and legacy-path rejection;
  - Python 3.13 reporting, pure lock validation and locked-only sync;
  - release-local checksum-pinned Node and locked dashboard build with artifact
    verification;
  - isolated state copy, config/DB migration, exact session/SQLite/config
    drift checks and isolated backend probe;
  - full isolated rollback rehearsal with failed-state quarantine, state hash
    restore, release pointer, service sequence and health proof;
  - aggregate readiness JSON; A1 production `cutover` remains fail-closed.
- `tests/test_hermes_native_change_c.py`
  - release/state/lock/Node/dashboard/probe/cutover/rollback contracts and
    functional failure-path coverage.
- `docs/state/current-operational-state.md`
  - superseding runtime truth and exact next gate.

## Validierung

| Gate | Result | Evidence |
|---|---|---|
| Release pin | PASS | staged HEAD and tag both `29112bef…`; binary v0.21.0; release manifest |
| Backup discovery | PASS | qualifying prior backup proof, exact canonical inventory |
| Backup run | PASS | Restic snapshot `781d93e1…` |
| Restore | PASS | prior isolated restore proof |
| Checksums | PASS | prior manifest/checksum proof; release/source/lock/Node hashes recorded |
| SQLite integrity | PASS | root/profile probe DBs exactly `ok`; foreign-key rows 0 |
| `backup-proof.json` | PASS | all required flags true; exact snapshot binding |
| Lock gate | PASS | `uv lock --check`; locked-only sync; no fallback |
| 0.21 staging | PASS | exact side-by-side release, Python 3.13.14, 60 dashboard artifacts |
| Migration probe | PASS | config 33→39; DB 22→26 on isolated copies |
| Session invariant | PASS | root 199→199; profile 993→993 |
| Rollback readiness | PASS | state hashes/pointer/service sequence/health/quarantine all verified |
| Fleet baseline | PASS | exactly 5/5 healthy; Freqtrade configs dry-run true |

Targeted repository validation:

```text
bash -n scripts/hermes-native-change-c.sh                    PASS
shellcheck scripts/hermes-native-change-c.sh                 PASS
pytest -q tests/test_hermes_native_change_c.py               25 passed
pytest -q tests/test_hermes_native_change_c.py \
  tests/test_hermestrader_backup_gate.py                     61 passed
ruff check tests/test_hermes_native_change_c.py              PASS
```

The complete root suite under Hermes UID 10000 produced 1,304 passed and 52
skipped. Its only failure is the known host-namespace-specific
`test_host_repo_path_is_rejected`: this host resolves `/workspace` to the host
repository path, so the test cannot observe the container/host distinction it
asserts. No full-suite green result is claimed; GitHub CI is the hermetic gate.

## PR / CI

```text
Branch: ops/hermes-021-stage-probe
Commit: pending
PR: pending
CI: pending
Merge SHA: pending
```

## Gate-Status

```text
CUTOVER_READY
CUTOVER_READY=YES
CUTOVER_EXECUTED=NO
```

## Nächster Roadmap-Schritt

A2: kontrollierter HermesTrader 0.19.0 → 0.21.0 Produktions-Cutover mit
Pre-Cutover-State-Snapshot, atomarem Wechsel, Acceptance Checks,
15-Minuten-Messfenster und automatisierbarem Rollback.
