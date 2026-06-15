# #200 Phase B2 — L3 Compose Adoption Execution Plan

**Title:** #200 Phase B2 — L3 Compose Adoption for Qdrant, Ollama, Mem0 and Hermes Watchdog  
**Date:** 2026-06-15  
**Repository:** `GoLukeEnviro/trading-hub`  
**Base commit:** `3c6b6a2709546f043322c5024c5615bac9461865` (PR #218 merge commit)  
**Operation Level of this document:** L2 planning/documentation  
**Operation Level of the future run:** L3 runtime mutation  
**Status:** PENDING HUMAN APPROVAL  

---

## 1. Executive Verdict

#200 Phase B2 is technically prepared but **not authorized for execution**.

The Phase B1 blocker is resolved: `hermes-watchdog` now targets
`trading_hermes-net`, and `watchdog-logs` is declared `external: true`.

The remaining gate is explicit human L3 approval with the exact token:

```text
APPROVE_PHASE_B2_L3_COMPOSE_ADOPTION_FOR_QDRANT_OLLAMA_MEM0_WATCHDOG
```

Without that exact token, the commands in this runbook must not be executed.

### Critical corrections from the draft artifact

The current `docker-compose.yml` service names on `origin/main` are:

| Runtime container | Compose service |
|---|---|
| `green-qdrant` | `green-qdrant` |
| `green-ollama` | `green-ollama` |
| `green-mem0` | `green-mem0` |
| `trading-hermes-watchdog-1` | `hermes-watchdog` |

Therefore, the future L3 commands must use:

```bash
docker compose up -d --no-deps green-qdrant
docker compose up -d --no-deps green-ollama
docker compose up -d --no-deps green-mem0
docker compose up -d --no-deps hermes-watchdog
```

Do **not** use non-existent services `qdrant`, `ollama`, or `mem0`.

---

## 2. Scope

Adopt exactly four currently-running unmanaged containers into the existing
Compose authority:

```text
green-qdrant
green-ollama
green-mem0
trading-hermes-watchdog-1
```

The goal is only to align runtime ownership and Compose labels. This is not a
refactor, optimization, healthcheck expansion, scheduler migration, scoring
change, apply implementation, or trading change.

---

## 3. Hard Rules

```text
- No docker compose down
- No docker system prune
- No volume deletion
- No network deletion
- No image rebuilds
- No scheduler change
- No Freqtrade config change
- No strategy change
- No scoring
- No apply
- No live trading
- No dry_run=false
- No secrets printed
- Each container one at a time: snapshot -> stop -> rename backup -> compose up -> verify -> next
- Abort on first RED
```

`docker rm` is avoided as the primary path. The preferred method is to rename
the pre-adoption container after snapshot so rollback remains possible without
reconstructing `docker run` flags.

---

## 4. Required Approval Token

Execution requires exact user confirmation:

```text
APPROVE_PHASE_B2_L3_COMPOSE_ADOPTION_FOR_QDRANT_OLLAMA_MEM0_WATCHDOG
```

No paraphrase, partial token, or implied approval is sufficient.

---

## 5. Phase 0 — Host Preflight

**Goal:** prove we are on the correct host, repo, branch, and merge commit.

```bash
set -euo pipefail

cd /home/hermes/projects/trading

export DOCKER_HOST=unix:///var/run/docker.sock

: "${PHASE_B2_APPROVAL_TOKEN:?PHASE_B2_APPROVAL_TOKEN must be set by the human operator}"
test "$PHASE_B2_APPROVAL_TOKEN" = "APPROVE_PHASE_B2_L3_COMPOSE_ADOPTION_FOR_QDRANT_OLLAMA_MEM0_WATCHDOG" || {
  echo "ABORT: approval token mismatch" >&2
  exit 1
}

echo "== identity =="
date -u
hostname
id

echo "== git state =="
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short

echo "== expected main after PR #218 =="
git fetch origin main --prune
git rev-parse refs/remotes/origin/main
```

### Abort gates

Abort if any condition is true:

```text
- Branch is not main.
- HEAD does not match refs/remotes/origin/main.
- HEAD does not include PR #218 merge commit 3c6b6a2709546f043322c5024c5615bac9461865.
- Working tree has unstaged source/config drift not explicitly identified as runtime artifact.
- Docker socket is unavailable.
- Docker Compose CLI is unavailable.
- docker-compose.yml is not parseable.
```

### Secret-safe Compose validation

Do not render full environment blocks. Prefer YAML parse + service listing.

```bash
python3 - <<'PY'
import yaml
from pathlib import Path
p = Path("docker-compose.yml")
dc = yaml.safe_load(p.read_text())
services = dc.get("services") or {}
volumes = dc.get("volumes") or {}
required = ["green-qdrant", "green-ollama", "green-mem0", "hermes-watchdog"]
missing = [s for s in required if s not in services]
if missing:
    raise SystemExit(f"missing compose services: {missing}")
watchdog = services["hermes-watchdog"]
if "trading_hermes-net" not in (watchdog.get("networks") or []):
    raise SystemExit("hermes-watchdog is not on trading_hermes-net")
if volumes.get("watchdog-logs") != {"external": True}:
    raise SystemExit("watchdog-logs is not external:true")
print("COMPOSE_YAML_SAFE_CHECK=PASS")
print("services=" + ",".join(required))
PY

# Optional only if available and known secret-safe on this host:
docker compose config --services >/tmp/phase-b2-compose-services.txt
```

If `docker compose config --services` is unavailable, Phase B2 is **BLOCKED**
until a safe Compose CLI path is installed or a human provides the exact runtime
execution environment.

---

## 6. Phase 1 — Read-only Snapshot

**Goal:** preserve evidence before mutation.

```bash
set -euo pipefail

cd /home/hermes/projects/trading
export DOCKER_HOST=unix:///var/run/docker.sock

ts="$(date -u +%Y%m%dT%H%M%SZ)"
export PHASE_B2_DIR="/home/hermes/reports/phase-b2-compose-adoption-$ts"
mkdir -p "$PHASE_B2_DIR"

echo "$ts" > "$PHASE_B2_DIR/timestamp.txt"
git rev-parse HEAD > "$PHASE_B2_DIR/git-head-before.txt"
git status --short > "$PHASE_B2_DIR/git-status-before.txt"

docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}' \
  > "$PHASE_B2_DIR/docker-ps-before.txt"

docker network ls > "$PHASE_B2_DIR/docker-networks-before.txt"
docker volume ls > "$PHASE_B2_DIR/docker-volumes-before.txt"

for c in green-qdrant green-ollama green-mem0 trading-hermes-watchdog-1; do
  docker inspect "$c" > "$PHASE_B2_DIR/inspect-before-$c.json"
  docker logs --tail 300 "$c" > "$PHASE_B2_DIR/logs-before-$c.txt" 2>&1 || true
  docker inspect "$c" --format '{{.Image}}' > "$PHASE_B2_DIR/image-id-before-$c.txt"
done

docker volume inspect green-qdrant-data > "$PHASE_B2_DIR/volume-before-green-qdrant-data.json"
docker volume inspect green-ollama-data > "$PHASE_B2_DIR/volume-before-green-ollama-data.json"
docker volume inspect watchdog-logs > "$PHASE_B2_DIR/volume-before-watchdog-logs.json"
docker network inspect trading_hermes-net > "$PHASE_B2_DIR/network-before-trading_hermes-net.json"
cp docker-compose.yml "$PHASE_B2_DIR/docker-compose-before.yml"
```

### Snapshot abort gates

Abort if:

```text
- Any of the four containers does not exist.
- Any inspect file is empty.
- green-qdrant-data does not exist.
- green-ollama-data does not exist.
- watchdog-logs does not exist.
- trading_hermes-net does not exist.
```

Check:

```bash
for f in "$PHASE_B2_DIR"/*.json "$PHASE_B2_DIR"/*.txt "$PHASE_B2_DIR"/*.yml; do
  test -s "$f" || { echo "EMPTY_SNAPSHOT_FILE: $f"; exit 1; }
done
```

---

## 7. Phase 2 — Service Mapping Check

```bash
docker compose ps -a > "$PHASE_B2_DIR/compose-ps-before.txt"
docker compose config --services > "$PHASE_B2_DIR/compose-services.txt"

for s in green-qdrant green-ollama green-mem0 hermes-watchdog; do
  grep -Fx "$s" "$PHASE_B2_DIR/compose-services.txt"
done
```

Expected mapping:

| Runtime container | Compose service | Expected compose project | Expected service label |
|---|---|---|---|
| `green-qdrant` | `green-qdrant` | `trading` | `green-qdrant` |
| `green-ollama` | `green-ollama` | `trading` | `green-ollama` |
| `green-mem0` | `green-mem0` | `trading` | `green-mem0` |
| `trading-hermes-watchdog-1` | `hermes-watchdog` | `trading` | `hermes-watchdog` |

Abort if:

```text
- A listed service is missing.
- Compose would create a different container name than expected.
- hermes-watchdog is not on trading_hermes-net.
- watchdog-logs is not external:true.
```

---

## 8. Phase 3 — Sequential Adoption

### Common helper variables

```bash
backup_suffix="pre-adopt-$ts"
```

The pattern is:

```text
snapshot -> docker stop -> docker rename old container -> docker compose up -> verify
```

Do not continue to the next container unless the current container is GREEN.

---

### 8.1 Adopt `green-qdrant`

**Risk:** medium. Qdrant holds vector-store state on `green-qdrant-data`.
No volume loss is acceptable.

```bash
docker stop green-qdrant
docker rename green-qdrant "green-qdrant-$backup_suffix"
docker compose up -d --no-deps green-qdrant
```

Verify:

```bash
docker inspect green-qdrant > "$PHASE_B2_DIR/inspect-after-green-qdrant.json"

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}' \
  | grep green-qdrant

docker inspect green-qdrant \
  --format 'project={{ index .Config.Labels "com.docker.compose.project" }} service={{ index .Config.Labels "com.docker.compose.service" }}' \
  | tee "$PHASE_B2_DIR/labels-after-green-qdrant.txt"

# Qdrant has no host port in compose. Verify through an existing container on trading_hermes-net.
docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-qdrant:6333/collections' \
  > "$PHASE_B2_DIR/qdrant-collections-after.json"
```

Expected:

```text
project=trading
service=green-qdrant
network includes trading_hermes-net
green-qdrant-data remains mounted at /qdrant/storage
collections endpoint responds
```

Rollback:

```bash
docker logs --tail 200 green-qdrant > "$PHASE_B2_DIR/qdrant-failed-logs.txt" 2>&1 || true
docker compose stop green-qdrant || true
docker rename green-qdrant "green-qdrant-compose-failed-$ts" || true
docker rename "green-qdrant-$backup_suffix" green-qdrant
docker start green-qdrant
# No volume deletion. No prune.
```

---

### 8.2 Adopt `green-ollama`

**Risk:** low to medium. Model server can restart briefly; no model pull or
image rebuild is allowed.

```bash
docker stop green-ollama
docker rename green-ollama "green-ollama-$backup_suffix"
docker compose up -d --no-deps green-ollama
```

Verify:

```bash
docker inspect green-ollama > "$PHASE_B2_DIR/inspect-after-green-ollama.json"

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}' \
  | grep green-ollama

docker inspect green-ollama \
  --format 'project={{ index .Config.Labels "com.docker.compose.project" }} service={{ index .Config.Labels "com.docker.compose.service" }}' \
  | tee "$PHASE_B2_DIR/labels-after-green-ollama.txt"

# No host port in compose. Verify inside the container and via Docker DNS.
docker exec green-ollama ollama list > "$PHASE_B2_DIR/ollama-list-after.txt"
docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-ollama:11434/api/tags' \
  > "$PHASE_B2_DIR/ollama-tags-after.json"
```

Expected:

```text
project=trading
service=green-ollama
network includes trading_hermes-net
green-ollama-data remains mounted at /root/.ollama
ollama list/api tags respond
no model pull executed
no image rebuild
```

Rollback:

```bash
docker logs --tail 200 green-ollama > "$PHASE_B2_DIR/ollama-failed-logs.txt" 2>&1 || true
docker compose stop green-ollama || true
docker rename green-ollama "green-ollama-compose-failed-$ts" || true
docker rename "green-ollama-$backup_suffix" green-ollama
docker start green-ollama
```

---

### 8.3 Adopt `green-mem0`

**Risk:** medium. Mem0 depends on Qdrant and Ollama and is central to Hermes
memory. Run only after Qdrant and Ollama are GREEN.

```bash
docker stop green-mem0
docker rename green-mem0 "green-mem0-$backup_suffix"
docker compose up -d --no-deps green-mem0
```

Verify:

```bash
docker inspect green-mem0 > "$PHASE_B2_DIR/inspect-after-green-mem0.json"

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}' \
  | grep green-mem0

docker inspect green-mem0 \
  --format 'project={{ index .Config.Labels "com.docker.compose.project" }} service={{ index .Config.Labels "com.docker.compose.service" }}' \
  | tee "$PHASE_B2_DIR/labels-after-green-mem0.txt"

# Host port from compose is 127.0.0.1:8788 -> container 8787.
curl -fsS --max-time 10 http://127.0.0.1:8788/health \
  > "$PHASE_B2_DIR/mem0-health-host-after.json"

# Docker-DNS verification from Hermes container uses container port 8787.
docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-mem0:8787/health' \
  > "$PHASE_B2_DIR/mem0-health-from-hermes-after.json"
```

Expected:

```text
project=trading
service=green-mem0
network includes trading_hermes-net
host health endpoint responds on 127.0.0.1:8788/health
container-network health endpoint responds on green-mem0:8787/health
Qdrant remains reachable
Ollama remains reachable
```

Rollback:

```bash
docker logs --tail 200 green-mem0 > "$PHASE_B2_DIR/mem0-failed-logs.txt" 2>&1 || true
docker compose stop green-mem0 || true
docker rename green-mem0 "green-mem0-compose-failed-$ts" || true
docker rename "green-mem0-$backup_suffix" green-mem0
docker start green-mem0
```

---

### 8.4 Adopt `trading-hermes-watchdog-1`

**Risk:** medium. PR #218 fixed the prior network mismatch. This step must
confirm the container lands on `trading_hermes-net` and mounts `watchdog-logs`.

```bash
docker stop trading-hermes-watchdog-1
docker rename trading-hermes-watchdog-1 "trading-hermes-watchdog-1-$backup_suffix"
docker compose up -d --no-deps hermes-watchdog
```

Verify:

```bash
docker inspect trading-hermes-watchdog-1 > "$PHASE_B2_DIR/inspect-after-trading-hermes-watchdog-1.json"

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Networks}}' \
  | grep trading-hermes-watchdog-1

docker inspect trading-hermes-watchdog-1 \
  --format 'project={{ index .Config.Labels "com.docker.compose.project" }} service={{ index .Config.Labels "com.docker.compose.service" }}' \
  | tee "$PHASE_B2_DIR/labels-after-trading-hermes-watchdog-1.txt"

docker inspect trading-hermes-watchdog-1 \
  --format '{{json .NetworkSettings.Networks}}' \
  > "$PHASE_B2_DIR/watchdog-networks-after.json"

grep -q 'trading_hermes-net' "$PHASE_B2_DIR/watchdog-networks-after.json"

docker inspect trading-hermes-watchdog-1 \
  --format '{{json .Mounts}}' \
  > "$PHASE_B2_DIR/watchdog-mounts-after.json"

grep -q 'watchdog-logs' "$PHASE_B2_DIR/watchdog-mounts-after.json"
```

Bot reachability using the same DNS names as the watchdog command:

```bash
docker exec trading-hermes-watchdog-1 sh -lc '
for h in \
  trading-freqtrade-freqforge-1 \
  trading-freqtrade-freqforge-canary-1 \
  trading-freqtrade-regime-hybrid-1 \
  trading-freqai-rebel-1 \
  trading-freqtrade-webserver-1; do
  echo "== $h =="
  wget -qO- --timeout=5 "http://$h:8080/api/v1/ping" || exit 1
done
wget -qO- --timeout=5 http://trading-ai-hedge-fund-1:8080/health || exit 1
' > "$PHASE_B2_DIR/watchdog-bot-ping-after.txt"
```

Expected:

```text
project=trading
service=hermes-watchdog
network contains trading_hermes-net
watchdog-logs is mounted
Freqtrade bots are reachable by Docker DNS
no false alert storm
```

Rollback:

```bash
docker logs --tail 200 trading-hermes-watchdog-1 > "$PHASE_B2_DIR/watchdog-failed-logs.txt" 2>&1 || true
docker compose stop hermes-watchdog || true
docker rename trading-hermes-watchdog-1 "trading-hermes-watchdog-1-compose-failed-$ts" || true
docker rename "trading-hermes-watchdog-1-$backup_suffix" trading-hermes-watchdog-1
docker start trading-hermes-watchdog-1
```

---

## 9. Phase 4 — Full Post-Adoption Verification

### 9.1 Container ownership

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}' \
  > "$PHASE_B2_DIR/docker-ps-after.txt"

for c in green-qdrant green-ollama green-mem0 trading-hermes-watchdog-1; do
  echo "== $c =="
  docker inspect "$c" \
    --format 'project={{ index .Config.Labels "com.docker.compose.project" }} service={{ index .Config.Labels "com.docker.compose.service" }}'
done | tee "$PHASE_B2_DIR/compose-labels-after.txt"
```

Expected:

```text
green-qdrant                service=green-qdrant
green-ollama                service=green-ollama
green-mem0                  service=green-mem0
trading-hermes-watchdog-1   service=hermes-watchdog
```

### 9.2 Core service health

```bash
docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-qdrant:6333/collections' \
  > "$PHASE_B2_DIR/qdrant-final.json"

docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-ollama:11434/api/tags' \
  > "$PHASE_B2_DIR/ollama-final.json"

curl -fsS --max-time 10 http://127.0.0.1:8788/health \
  > "$PHASE_B2_DIR/mem0-final-host.json"

docker exec hermes-green sh -lc \
  'curl -fsS --max-time 10 http://green-mem0:8787/health' \
  > "$PHASE_B2_DIR/mem0-final-from-hermes.json"
```

### 9.3 SI v2 safe active cycle proof

Only run this if all previous checks are GREEN.

```bash
docker exec hermes-green bash -lc '
cd /home/hermes/projects/trading
python3 -m self_improvement_v2.src.si_v2.loop.active_cycle_runner
' > "$PHASE_B2_DIR/si-v2-active-cycle-after.txt" 2>&1
```

If that module path is stale, do not guess. Use the current wrapper only if it
is known and present:

```bash
docker exec hermes-green bash -lc '/opt/data/scripts/si-v2-active-cycle-runner.sh' \
  > "$PHASE_B2_DIR/si-v2-wrapper-cycle-after.txt" 2>&1
```

Expected:

```text
4/4 bots processed
fleet verdict GREEN or GREEN_WITH_LEDGER_WARNING
runtime_mutations=0
config_mutations=0
live_trading_mutations=0
approval=PENDING_HUMAN
controller=PAUSED / L3_REPOSITORY_ONLY
```

### 9.4 Log and safety scan

```bash
for c in green-qdrant green-ollama green-mem0 trading-hermes-watchdog-1 hermes-green; do
  docker logs --since 10m "$c" > "$PHASE_B2_DIR/logs-after-$c.txt" 2>&1 || true
done

grep -RniE 'error|exception|traceback|fatal|unhealthy|permission denied|false alert' \
  "$PHASE_B2_DIR"/logs-after-* \
  > "$PHASE_B2_DIR/error-scan-after.txt" || true

# Dry-run safety scan. Do not print secrets; only fail on dry_run=false.
if grep -RniE 'dry_run[" ]*[:=][" ]*false' freqtrade docker-compose.yml self_improvement_v2 orchestrator 2>/dev/null \
    > "$PHASE_B2_DIR/dry-run-false-scan.txt"; then
  echo "RED: dry_run=false found" >&2
  exit 1
fi
```

---

## 10. GREEN / YELLOW / RED Gates

### GREEN

```text
- All 4 containers running.
- All 4 containers have compose project=trading labels.
- Expected compose service labels present.
- green-qdrant data volume mounted and collections reachable.
- green-ollama data volume mounted and tags/list responds.
- green-mem0 health responds on host and Docker DNS.
- watchdog is on trading_hermes-net.
- watchdog-logs is mounted.
- Watchdog can reach Freqtrade bots by Docker DNS.
- SI v2 active cycle: 4/4 bots, mutations=0.
- No dry_run=false found.
```

### YELLOW

```text
- Services are healthy, but non-critical log warnings exist.
- SI v2 returns GREEN_WITH_LEDGER_WARNING while 4/4 bots and mutations=0.
- Verification had to use a fallback path, but evidence is complete.
```

### RED

```text
- Any adopted container is not running.
- Compose labels missing or wrong.
- watchdog is not on trading_hermes-net.
- watchdog-logs is not mounted.
- Qdrant collections unreachable.
- Ollama API/list unreachable.
- Mem0 health fails.
- SI v2 cannot read 4/4 bots.
- Any mutation counter is non-zero.
- dry_run=false appears.
- Secret values are printed to logs or reports.
```

---

## 11. Phase 5 — Verification Report

If final verdict is GREEN or YELLOW, write:

```text
docs/reports/phase2-b2-compose-adoption-verification-20260615.md
```

Template:

```markdown
# Phase B2 — Compose Adoption Verification

## Verdict
GREEN | YELLOW | RED

## Scope
Adopted:
- green-qdrant -> green-qdrant
- green-ollama -> green-ollama
- green-mem0 -> green-mem0
- trading-hermes-watchdog-1 -> hermes-watchdog

## Approval Token
APPROVE_PHASE_B2_L3_COMPOSE_ADOPTION_FOR_QDRANT_OLLAMA_MEM0_WATCHDOG

## Evidence Directory
/home/hermes/reports/phase-b2-compose-adoption-<timestamp>

## Pre-State
- Git HEAD:
- PR #218 merge commit: 3c6b6a2709546f043322c5024c5615bac9461865
- Docker snapshot path:

## Adoption Results
| Container | Service | Compose Labels | Network | Volume | Health | Verdict |
|---|---|---|---|---|---|---|
| green-qdrant | green-qdrant | PASS | PASS | PASS | PASS | GREEN |
| green-ollama | green-ollama | PASS | PASS | PASS | PASS | GREEN |
| green-mem0 | green-mem0 | PASS | PASS | PASS | PASS | GREEN |
| trading-hermes-watchdog-1 | hermes-watchdog | PASS | PASS | PASS | PASS | GREEN |

## SI v2 Post-Adoption Proof
- Bots processed:
- Fleet verdict:
- Ledger status:
- Mutations:
- Controller state:
- Approval state:

## Safety Confirmation
- No volume deletion
- No network deletion
- No docker compose down
- No prune
- No rebuild
- No scheduler change
- No scoring/apply/trading
- No secrets printed

## Remaining Follow-ups
- Update or close #200 only if all acceptance criteria are met.
- Optional: #201 hardening later.
- Repo hygiene #178 after runtime ownership is stable.
```

If final verdict is RED, do **not** write a success report. Write a RED incident
report instead:

```text
docs/reports/phase2-b2-compose-adoption-red-YYYYMMDD.md
```

---

## 12. Commit Rule After Execution

Only after GREEN or acceptable YELLOW:

```bash
git checkout main
git pull --ff-only origin main

git add docs/reports/phase2-b2-compose-adoption-verification-20260615.md
git commit -m "docs: add phase B2 compose adoption verification"
git push origin main
```

If RED:

```text
Do not commit a success report.
Do not continue adoption.
Create RED incident report only.
Escalate to human.
```

---

## 13. External Containers

The following unmanaged containers remain external and are **not** adopted by
this runbook:

```text
btc5m-bot
claude-worker
weatherhermes
```

They stay outside Trading Hub Compose ownership and should be documented as
external dependencies only.

---

## 14. Backlog Entry

**Title:** #200 Phase B2 — Execute guarded L3 Compose adoption for 4 unmanaged-but-defined services

**Goal:** Adopt four Compose-defined but unmanaged runtime containers under
Compose ownership and then prove SI v2 still reads 4/4 bots with 0 mutations and
controller paused.

**Acceptance criteria:**

- [ ] Approval token is provided exactly.
- [ ] Pre-snapshot complete under `/home/hermes/reports/phase-b2-compose-adoption-<ts>/`.
- [ ] `green-qdrant` adopted; Compose labels correct; collections reachable.
- [ ] `green-ollama` adopted; Compose labels correct; API/list reachable.
- [ ] `green-mem0` adopted; Compose labels correct; health via host and Hermes reachable.
- [ ] `trading-hermes-watchdog-1` adopted; Compose labels correct; `trading_hermes-net`; `watchdog-logs` mounted.
- [ ] SI v2 active cycle after adoption: 4/4 bots, mutations=0.
- [ ] No `dry_run=false`, no apply, no scoring, no scheduler change.
- [ ] Verification report in repo.
- [ ] #200 closed only after all acceptance criteria are met.

**Dependencies:**

- PR #218 merged — satisfied.
- Docker socket access.
- Working Docker Compose CLI.
- Explicit L3 approval token.
- No parallel runtime work during adoption window.

---

## 15. Exact Next Recommended Task

Do not execute this runbook yet.

Next gate:

```text
Human must provide exact token:
APPROVE_PHASE_B2_L3_COMPOSE_ADOPTION_FOR_QDRANT_OLLAMA_MEM0_WATCHDOG
```

After token: run Phase 0 and Phase 1 only, report snapshot/preflight result,
then proceed container-by-container only if all abort gates remain GREEN.
