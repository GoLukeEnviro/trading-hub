# Real Adapter Design — SI v2 Phase E

> **Design Review — NO code implementation in this phase.**
> This document defines *when* and *how* real adapters may be built,
> without writing any production code that touches Docker, Freqtrade,
> or Telegram.

---

## 1. Scope

This document covers three real adapter implementations that are
currently stubbed with `DryRun*` implementations:

| Adapter | Dry-Run Stub | Real Target | Current Safety |
|---------|-------------|-------------|----------------|
| `DockerAdapter` | `DryRunStubDocker` | `docker exec` via socket | Read-only methods only |
| `FreqtradeAdapter` | `DryRunStubFreqtrade` | `docker exec` into Freqtrade container | Read-only methods only |
| `TelegramAdapter` | `DryRunTelegramAdapter` | Telegram Bot API HTTP | Captures in memory |

---

## 2. Preconditions for Real Adapter Development

A real adapter MUST NOT be written unless ALL of the following are true:

### 2.1 Code-Level Preconditions

- [ ] A new `LIVE_FORBIDDEN` → `LIVE_APPROVED` state machine check exists
- [ ] The real adapter extends the existing Protocol, NOT a new interface
- [ ] The real adapter wraps every invocation with ShadowLogger audit
- [ ] Every real adapter method has a timeout (default: 30s)
- [ ] Every real adapter method has a call budget (max 60 calls/min)
- [ ] No retry for write-adjacent operations (backtest is read-only, but
      still has call budget)

### 2.2 Human Preconditions

- [ ] Documented human approval in a GitHub Issue or approved PR
- [ ] Approval comment references this design document
- [ ] System is in `proposal_only` mode (verified at runtime)
- [ ] All 178+ Phase D tests pass on the target branch

### 2.3 Infrastructure Preconditions

- [ ] Docker socket is accessible from the Hermes runtime
- [ ] Freqtrade containers are running and named consistently with
      `BotConfig.container`
- [ ] Telegram bot token is stored in a Hermes-managed secret store
      (NOT in source code, NOT in `.env` files committed to repo)
- [ ] Network ACLs permit outbound HTTPS to `api.telegram.org`

---

## 3. Adapter Contract — Must Extend Protocols

Every real adapter MUST satisfy the existing `@runtime_checkable` Protocol
from Phase B. The Protocol defines the minimum contract; real adapters
may add configuration parameters but MUST NOT change return types.

### 3.1 RealDockerAdapter

```python
class RealDockerAdapter:
    """Wraps docker exec calls. READ-ONLY ONLY.

    Configuration:
        docker_host: str = "unix:///var/run/docker.sock"
        timeout_sec: int = 30
        audit_logger: ShadowLogger | None = None
    """

    def exec_readonly(self, container: str, command: list[str]) -> str: ...
    def container_is_running(self, container: str) -> bool: ...
    def get_container_ip(self, container: str) -> str: ...

    # NOT ALLOWED:
    # def restart(self, ...) — not in Protocol
    # def stop(self, ...) — not in Protocol
    # def start(self, ...) — not in Protocol
    # def exec_write(self, ...) — not in Protocol
```

### 3.2 RealFreqtradeAdapter

```python
class RealFreqtradeAdapter:
    """Wraps freqtrade CLI via docker exec. READ-ONLY ONLY.

    Configuration:
        docker_adapter: DockerAdapter  # injected, NOT created here
        timeout_sec: int = 120  # backtests can be slow
        audit_logger: ShadowLogger | None = None
    """

    def read_config(self, bot_id: str) -> dict: ...
    def get_trade_history(self, bot_id: str, limit: int = 100) -> list[dict]: ...
    def run_backtest(self, bot_id: str, overlay: MutationOverlay) -> dict: ...
```

### 3.3 RealTelegramAdapter

```python
class RealTelegramAdapter:
    """Wraps Telegram Bot API. SEND-ONLY.

    Configuration:
        bot_token: str  # from Hermes secret store, NEVER hardcoded
        default_chat_id: str  # from config, NEVER hardcoded
        audit_logger: ShadowLogger | None = None
    """

    def send_message(self, chat_id_hint: str, message: TelegramMessage) -> None: ...
    def send_approval_request(self, chat_id_hint: str, bot_id: str,
                               candidate_sha: str, backtest_summary: str,
                               walk_forward_summary: str, risk_reason: str) -> None: ...
```

---

## 4. Failure Modes & Handling

| Failure Mode | Likelihood | Impact | Mitigation | Residual Risk |
|-------------|-----------|--------|------------|---------------|
| Docker socket timeout | Medium | Backtest delayed | Timeout + retry (1x, idempotent) | Low |
| Docker socket unavailable | Low | All ops fail | Health check before each call | Medium |
| Freqtrade container down | Medium | All ops fail | `container_is_running()` check | Low |
| Freqtrade backtest timeout | High | Result lost | Timeout + partial result | Medium |
| Telegram API down | Low | Approval not sent | Queue + retry | Low |
| Telegram rate limit | Medium | Messages dropped | Call budget (60/min) | Low |
| Network partition | Low | All remote ops fail | Fail closed | Low (no trades) |

### 4.1 Fail-Closed Policy

- Any network/container error → `BacktestResult(passed=False)`
- Any timeout → `WalkForwardResult(passed=False, reason="timeout")`
- Any Telegram send failure → Log warning, continue pipeline
  (approval can be checked manually)

### 4.2 Retry Policy

| Operation | Max Retries | Backoff | Idempotent? |
|-----------|-------------|---------|-------------|
| `exec_readonly` | 1 | 5s linear | Yes |
| `run_backtest` | 0 | N/A | Yes |
| `send_message` | 3 | 2s, 5s, 10s | Yes |
| `send_approval_request` | 3 | 2s, 5s, 10s | Yes |

> **NOTE:** `run_backtest` has 0 retries because it is expensive and
> duplicate runs waste resources. The caller must re-request if needed.

---

## 5. Audit Logging

Every real adapter invocation MUST log to `ShadowLogger`:

```jsonl
{"timestamp_utc": "...", "adapter": "RealFreqtradeAdapter",
 "method": "run_backtest", "bot_id": "bot_a",
 "duration_ms": 4231, "success": true,
 "candidate_sha": "abc123", "error": null}
```

The audit log is **append-only** and **never truncated** by the adapter.

---

## 6. Switching from Dry-Run to Real

The switch is a SINGLE configuration change:

```python
# Current (Phase D):
adapter = DryRunStubFreqtrade()

# After Phase E approval:
adapter = RealFreqtradeAdapter(
    docker_adapter=RealDockerAdapter(),
    timeout_sec=120,
    audit_logger=ShadowLogger(log_dir="state/si_v2_logs/"),
)
```

The orchestration layer (`DeploymentPlanOrchestrator`) injects the adapter.
No other code changes are needed because all consumers depend on the
Protocol, not the concrete class.

---

## 7. Rollback Plan

If a real adapter is found to be unsafe:

1. Revert the adapter instantiation to `DryRunStub*`
2. The pipeline continues with mock data (no live reads)
3. The system remains fully functional
4. File a GitHub Issue describing the safety failure
5. The adapter is redesigned before re-enabling