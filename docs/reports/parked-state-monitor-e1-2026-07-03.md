# Parked-State Monitor and Drift Report — E1

> Issue: #456 — Track E1  
> Date: 2026-07-03  
> Scope: read-only roadmap/state report  
> Runtime mutation: none  
> Docker/Cron/Freqtrade mutation: none  
> D1/live rollout: not started

---

## 1. Verdict

**Status: YELLOW — safe parked state still holds, but operator/security drift exists outside E1 scope.**

D1 remains blocked. The current live-fleet roadmap must not proceed because #423 still requires a future C4 `KEEP` decision and `APPROVED_LIVE_FLEET_ROLLOUT`; the current evidence remains the opposite: C4 produced `ROLLBACK_RECOMMENDED` and the canary was returned to a stopped dry-run-safe baseline.

The uploaded 2026-07-03 read-only VPS audit reports critical operator/security findings. Those findings do **not** authorize runtime repair inside E1. They should be handled as separate scoped issues after this parked-state report is merged.

---

## 2. Sources Read

| Source | Purpose | Result |
|---|---|---|
| `AGENTS.md` | Binding agent scope and safety rules | Runtime/Docker/Cron work is out of scope unless explicitly approved |
| `SOUL.md` | Non-negotiable safety boundaries | Dry-run-first, no secrets in Git, proof/audit required |
| `docs/state/current-operational-state.md` | Canonical state snapshot | D1/live remains blocked; dry-run only |
| Issue #423 | Canonical SI-v2 → Live roadmap | D1 blocked by missing `KEEP` and missing approval marker |
| Issue #456 | Post-closure recovery backlog | E1 is the first unblocked task |
| PR #455 | Final closure reconciliation | Confirms D1 blocker, canary stopped, 0 open PRs at closure |
| GitHub open PR search | Check for dependency PRs | 0 open PRs observed at execution time |
| GitHub open roadmap issue search | Check roadmap issue inventory | #423 and #456 are the open roadmap issues observed |
| User-provided VPS audit, 2026-07-03 11:45 UTC | Fresh read-only drift evidence | Critical operator/security drift found; no mutation performed |

---

## 3. E1 Acceptance Criteria

| Criterion | Status | Evidence / Note |
|---|---:|---|
| Read #423 and PR #455 | ✅ | #423 and PR #455 reviewed |
| Confirm only #423 and this backlog are open roadmap issues | ✅ | GitHub search returned #423 and #456 for open `roadmap` issues |
| Confirm no open PRs | ✅ | GitHub open PR search returned `[]` |
| Confirm canary remains stopped or otherwise safe | ✅ | #423/#456/PR #455 say stopped; uploaded audit also reports canary `EXITED (130)` |
| Confirm kill switch remains NORMAL | 🟡 | #423/#456/PR #455 state NORMAL; no direct VPS shell verification was performed in this PR |
| Confirm fleet baseline remains unaffected | 🟡 | #423/#456/PR #455 state 3 baseline bots unaffected; uploaded audit reports 3/5 bots running and canary stopped |
| Produce a read-only parked-state report | ✅ | This file |
| Do not mutate runtime | ✅ | GitHub docs-only change; no runtime access or mutation |
| Do not start D1 | ✅ | D1 explicitly remains blocked |

---

## 4. Parked-State Assessment

| Area | Assessment | Decision Impact |
|---|---|---|
| D1 eligibility | Not eligible | Blocks live fleet rollout |
| C4 decision | `ROLLBACK_RECOMMENDED` | Blocks D1 unless a future clean measurement emits `KEEP` or a separate approved override exists |
| Approval marker | `APPROVED_LIVE_FLEET_ROLLOUT` not present in the reviewed roadmap state | Blocks D1 |
| Canary | Stopped / safe baseline | Supports parked state |
| Kill switch | Reported NORMAL by roadmap/closure sources | Supports parked state, but should be rechecked by the next live operator preflight |
| Fleet baseline | 3 non-canary bots reported running/unaffected | Supports parked state |
| Open PR queue | Empty | No dependency PR blocker |
| Open roadmap issues | #423 and #456 | Expected after post-closure backlog creation |

---

## 5. Drift Findings From Uploaded Audit

These findings are **not** fixed by E1. They are tracked here to prevent silent drift and to route them into later scoped issues.

| Finding Area | Audit Signal | Severity | E1 Decision |
|---|---|---:|---|
| Docker socket exposure | `hermes-green` and `trading-guardian` reportedly mount raw `docker.sock` despite proxy architecture | Critical | Create separate L3 security/operator issue; no change in E1 |
| API/session key weakness | `API_SERVER_KEY=hermes-api-key-123` and dashboard token exposure reported | Critical | Create separate L3 secrets/auth issue; no change in E1 |
| Secret exposure via env | DeepSeek/Ollama/GLM keys reportedly exposed through container env inspection | High/Critical | Create separate L3 secrets migration issue; no change in E1 |
| Memory stack | Qdrant collection reportedly empty / missing and embedder drift observed | Critical | Create separate memory recovery issue; no change in E1 |
| Canary | Canary still exited/stopped | Expected for parked state | No restart in E1 |
| Pipeline state | `bridge_state.json` / `riskguard_state.json` reportedly missing | Medium/High | Investigate in separate read-only pipeline issue |
| Reboot required | Kernel update pending | Medium/High | Separate maintenance issue; requires operator window |
| Disk growth | `/` at ~70%, +7% since previous audit | Medium | Monitor / cleanup issue only after current PR merge |

---

## 6. Recommended Follow-up Backlog

### SEC-1 — Remove raw docker.sock bypass from operative agents

- **Goal:** ensure `hermes-green` and `trading-guardian` use only the intended Docker proxy path.
- **Acceptance:** inspect compose/runtime mounts, document current exposure, propose minimal reversible change, require explicit L3 approval before runtime mutation.
- **Blocked by:** explicit operator approval for Docker/runtime change.

### SEC-2 — Replace trivial Hermes API/session key and prevent client-side token exposure

- **Goal:** eliminate `hermes-api-key-123` and hardcoded dashboard token exposure.
- **Acceptance:** locate key sources, define rotation plan, avoid committing secrets, add validation that defaults fail closed.
- **Blocked by:** explicit secrets rotation approval.

### MEM-1 — Memory stack recovery plan, no mutation

- **Goal:** determine whether `hermes_memories_v2` is empty, missing, or pointed at the wrong Qdrant instance.
- **Acceptance:** compare docs, Qdrant collections, Ollama model inventory, backups, and restore options; no data mutation in planning PR.
- **Blocked by:** none for read-only plan; restore requires approval.

### OPS-1 — Canary parked-state live preflight

- **Goal:** direct operator preflight before any E2/E3 dry-run redeployment planning.
- **Acceptance:** confirm canary stopped, kill switch NORMAL, dry_run config preserved, fleet unaffected, no D1.
- **Blocked by:** none if read-only.

---

## 7. Stop Conditions

Stop and report `BLOCKED_BY_SCOPE` if any of the following are required:

- Docker compose edits.
- Container restart/start/stop.
- Cron or scheduler mutation.
- Freqtrade config mutation.
- Secret rotation.
- Qdrant/Ollama restore.
- D1/live rollout implementation.
- `dry_run=false`.

---

## 8. Final Decision

E1 is complete as a docs-only/read-only parked-state report.

**Next valid roadmap task after merge:** E2 — Canary Dry-Run Redeployment Plan, No Execution.

However, based on the uploaded audit, the safer immediate operator sequence is to open separate scoped SEC/MEM/OPS issues before any redeployment execution is considered. Those issues must remain separate from D1 and must not bypass #423/#456 gates.
