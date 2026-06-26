r"""Tests for Phase 1 Controlled Apply Actuator — Canary-First Human Gate (#363).

Test coverage matrix:

  1. Canary bot gate
     - Accepted: freqtrade-freqforge-canary
     - Rejected: all other bot IDs (freqforge, regime-hybrid, freqai-rebel)
  2. Safe overlay keys gate
     - Accepted: keys from SAFE_OVERLAY_KEYS (cooldown_candles, max_open_trades, etc.)
     - Rejected: unsafe keys (dry_run, exchange, secret)
     - Rejected: unrecognised keys not in SAFE_OVERLAY_KEYS
  3. Human approval flag gate
     - Accepted: requires_human_approval=True
     - Rejected: requires_human_approval=False
  4. L3 activation token gate
     - Accepted: env var set to APPROVE
     - Rejected: env var not set
     - Rejected: env var set to wrong value
  5. Cooldown gate
     - Accepted: no cooldown state file (first apply)
     - Accepted: cooldown expired (>7 days ago)
     - Rejected: cooldown active (<7 days ago)
  6. dry_run invariance
     - Accepted: dry_run=True
     - Rejected: dry_run=False
  7. Full end-to-end apply
     - All gates pass -> APPLIED
     - Overlay file written
     - Rollback plan created
     - Cooldown state updated
     - Shadow logs written (4 events)
  8. Blocked scenarios
     - Wrong bot, unsafe key, no approval, no token, cooldown, dry_run=False
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from si_v2.apply_actuator.controlled_apply_actuator import (
    CANARY_BOT_ID,
    COOLDOWN_DAYS,
    L3_TOKEN_ENV,
    L3_TOKEN_VALUE,
    SAFE_OVERLAY_KEYS,
    SHADOW_LOG_EVENTS,
    ControlledApplyDecision,
    check_activation_token,
    check_canary_bot,
    check_cooldown,
    check_human_approval_flag,
    check_safe_overlay_keys,
    create_rollback_plan,
    CooldownState,
    log_shadow_event,
    run_controlled_apply_canary,
    summarize_decision,
    write_overlay_file,
)

# -- Fixtures -----------------------------------------------------------------


@pytest.fixture
def canary_bot_id() -> str:
    return CANARY_BOT_ID


@pytest.fixture
def f68a_overlay() -> dict[str, int]:
    return {"cooldown_candles": 4, "max_open_trades": 3}


@pytest.fixture
def pre_apply_config() -> dict[str, object]:
    return {"cooldown_candles": 3, "max_open_trades": 3, "dry_run": True}


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d


@pytest.fixture
def tmp_overlay_dir(tmp_path: Path) -> Path:
    d = tmp_path / "overlays"
    d.mkdir()
    return d


@pytest.fixture
def tmp_plan_dir(tmp_path: Path) -> Path:
    d = tmp_path / "rollback_plans"
    d.mkdir()
    return d


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    d = tmp_path / "shadow_log"
    d.mkdir()
    return d


@pytest.fixture
def with_l3_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(L3_TOKEN_ENV, L3_TOKEN_VALUE)


@pytest.fixture
def without_l3_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(L3_TOKEN_ENV, raising=False)


# -- 1. Canary bot gate -------------------------------------------------------


class TestCanaryBotGate:
    def test_accepts_canary(self) -> None:
        assert check_canary_bot(CANARY_BOT_ID)

    def test_rejects_freqforge(self) -> None:
        assert not check_canary_bot("freqtrade-freqforge")

    def test_rejects_regime_hybrid(self) -> None:
        assert not check_canary_bot("freqtrade-regime-hybrid")

    def test_rejects_freqai_rebel(self) -> None:
        assert not check_canary_bot("freqai-rebel")

    def test_rejects_empty_string(self) -> None:
        assert not check_canary_bot("")


# -- 2. Safe overlay keys gate ------------------------------------------------


class TestSafeOverlayKeysGate:
    def test_accepts_cooldown_candles(self) -> None:
        assert check_safe_overlay_keys({"cooldown_candles": 4})

    def test_accepts_max_open_trades(self) -> None:
        assert check_safe_overlay_keys({"max_open_trades": 3})

    def test_accepts_all_safe_keys(self) -> None:
        assert check_safe_overlay_keys({k: 1 for k in SAFE_OVERLAY_KEYS})

    def test_rejects_dry_run(self) -> None:
        assert not check_safe_overlay_keys({"dry_run": False})

    def test_rejects_exchange(self) -> None:
        assert not check_safe_overlay_keys({"exchange": "binance"})

    def test_rejects_unsafe_key(self) -> None:
        assert not check_safe_overlay_keys({"stake_currency": "BTC"})

    def test_rejects_unrecognised_key(self) -> None:
        assert not check_safe_overlay_keys({"unknown_param": 42})

    def test_rejects_empty_overlay(self) -> None:
        assert not check_safe_overlay_keys({})

    def test_rejects_mixed_safe_and_unsafe(self) -> None:
        assert not check_safe_overlay_keys({"cooldown_candles": 4, "secret": "hunter2"})


# -- 3. Human approval flag gate ----------------------------------------------


class TestHumanApprovalGate:
    def test_accepts_true(self) -> None:
        assert check_human_approval_flag({"requires_human_approval": True})

    def test_rejects_false(self) -> None:
        assert not check_human_approval_flag({"requires_human_approval": False})

    def test_rejects_missing(self) -> None:
        assert not check_human_approval_flag({})

    def test_rejects_none(self) -> None:
        assert not check_human_approval_flag({"requires_human_approval": None})


# -- 4. L3 activation token gate ----------------------------------------------


class TestActivationTokenGate:
    def test_accepts_with_token(self, with_l3_token: None) -> None:
        assert check_activation_token()

    def test_rejects_without_token(self, without_l3_token: None) -> None:
        assert not check_activation_token()

    def test_rejects_wrong_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(L3_TOKEN_ENV, "WRONG_VALUE")
        assert not check_activation_token()


# -- 5. Cooldown gate ---------------------------------------------------------


class TestCooldownGate:
    def test_no_state_file(self, tmp_state_dir: Path) -> None:
        cd = check_cooldown(tmp_state_dir)
        assert not cd.is_on_cooldown()
        assert cd.remaining_seconds() == 0.0

    def test_recent_apply_on_cooldown(self, tmp_state_dir: Path) -> None:
        state = CooldownState(
            last_apply_utc=datetime.now(UTC).isoformat(),
            candidate_sha="f68a031923d0",
            bot_id=CANARY_BOT_ID,
        )
        state.save(tmp_state_dir)
        cd = check_cooldown(tmp_state_dir)
        assert cd.is_on_cooldown()
        assert cd.remaining_seconds() > 0.0

    def test_old_apply_cooldown_expired(self, tmp_state_dir: Path) -> None:
        past = datetime.now(UTC) - timedelta(days=COOLDOWN_DAYS + 1, hours=1)
        state = CooldownState(
            last_apply_utc=past.isoformat(),
            candidate_sha="f68a031923d0",
            bot_id=CANARY_BOT_ID,
        )
        state.save(tmp_state_dir)
        cd = check_cooldown(tmp_state_dir)
        assert not cd.is_on_cooldown()
        assert cd.remaining_seconds() == 0.0

    def test_persists_and_loads(self, tmp_state_dir: Path) -> None:
        state = CooldownState(
            last_apply_utc="2026-06-20T12:00:00+00:00",
            candidate_sha="abc123",
            bot_id=CANARY_BOT_ID,
        )
        state.save(tmp_state_dir)
        loaded = CooldownState.load(tmp_state_dir)
        assert loaded.last_apply_utc == "2026-06-20T12:00:00+00:00"
        assert loaded.candidate_sha == "abc123"


# -- 6. Overlay file writer ---------------------------------------------------


class TestOverlayWriter:
    def test_writes_file(self, tmp_overlay_dir: Path) -> None:
        path, sha = write_overlay_file(
            "f68a031923d0", {"cooldown_candles": 4}, overlay_dir=tmp_overlay_dir
        )
        assert Path(path).exists()
        assert len(sha) == 64
        data = json.loads(Path(path).read_text())
        assert data["candidate_sha"] == "f68a031923d0"
        assert data["overlay"] == {"cooldown_candles": 4}

    def test_overlay_dir_created(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "new_overlays"
        path, _ = write_overlay_file("abc", {"cooldown_candles": 4}, overlay_dir=new_dir)
        assert Path(path).exists()


# -- 7. Rollback plan ---------------------------------------------------------


class TestRollbackPlan:
    def test_creates_plan(self, tmp_plan_dir: Path) -> None:
        path = create_rollback_plan(
            "f68a031923d0",
            CANARY_BOT_ID,
            "/tmp/overlay.json",
            {"cooldown_candles": 3, "dry_run": True},
            plan_dir=tmp_plan_dir,
        )
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["candidate_sha"] == "f68a031923d0"
        assert data["bot_id"] == CANARY_BOT_ID
        assert data["pre_apply_config_snapshot"]["cooldown_candles"] == 3
        assert "restore_instructions" in data


# -- 8. ShadowLogger integration ----------------------------------------------


class TestShadowLogger:
    def test_logs_event(self, tmp_log_dir: Path) -> None:
        log_shadow_event(
            "apply_requested", "f68a031923d0", CANARY_BOT_ID,
            details={"param": "cooldown_candles"}, log_dir=tmp_log_dir,
        )
        log_path = tmp_log_dir / "controlled_apply.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["event"] == "apply_requested"
        assert entry["bot_id"] == CANARY_BOT_ID

    def test_append_only(self, tmp_log_dir: Path) -> None:
        for event in SHADOW_LOG_EVENTS:
            log_shadow_event(event, "f68a031923d0", CANARY_BOT_ID, log_dir=tmp_log_dir)
        log_path = tmp_log_dir / "controlled_apply.jsonl"
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == len(SHADOW_LOG_EVENTS)
        events = [json.loads(l)["event"] for l in lines]
        assert events == list(SHADOW_LOG_EVENTS)


# -- 9. End-to-end apply (all gates pass) -------------------------------------


class TestEndToEndApply:
    def test_full_apply_success(
        self,
        canary_bot_id: str,
        f68a_overlay: dict[str, int],
        pre_apply_config: dict[str, object],
        with_l3_token: None,
        tmp_state_dir: Path,
        tmp_overlay_dir: Path,
        tmp_plan_dir: Path,
        tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0",
            bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay,
            requires_human_approval=True,
            state_dir=tmp_state_dir,
            overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir,
            log_dir=tmp_log_dir,
            pre_apply_config=pre_apply_config,
        )
        assert decision.overall_status == "APPLIED", decision.errors
        assert decision.overlay_path
        assert decision.overlay_sha256
        assert decision.rollback_plan_path

        overlay = json.loads(Path(decision.overlay_path).read_text())
        assert overlay["candidate_sha"] == "f68a031923d0"
        assert overlay["overlay"]["cooldown_candles"] == 4

        plan = json.loads(Path(decision.rollback_plan_path).read_text())
        assert plan["pre_apply_config_snapshot"]["cooldown_candles"] == 3

        cd = CooldownState.load(tmp_state_dir)
        assert cd.last_apply_utc
        assert cd.candidate_sha == "f68a031923d0"

        log_path = tmp_log_dir / "controlled_apply.jsonl"
        events = [json.loads(l)["event"] for l in log_path.read_text().strip().split("\n")]
        assert events == ["apply_requested", "apply_approved", "apply_executed", "rollback_ready"]


# -- 10. Blocked scenarios ----------------------------------------------------


class TestBlockedScenario:
    def test_blocked_wrong_bot(
        self, f68a_overlay: dict[str, int],
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id="freqtrade-regime-hybrid",
            parameter_overlay=f68a_overlay,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
            pre_apply_config={"dry_run": True},
        )
        assert decision.overall_status == "BLOCKED"
        log_path = tmp_log_dir / "controlled_apply.jsonl"
        assert not log_path.exists()

    def test_blocked_unsafe_key(
        self, canary_bot_id: str,
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay={"secret": "hunter2"},
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
        )
        assert decision.overall_status == "BLOCKED"

    def test_blocked_no_human_approval(
        self, canary_bot_id: str, f68a_overlay: dict[str, int],
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay, requires_human_approval=False,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
        )
        assert decision.overall_status == "BLOCKED"

    def test_blocked_no_token(
        self, canary_bot_id: str, f68a_overlay: dict[str, int],
        without_l3_token: None,
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay, requires_human_approval=True,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
        )
        assert decision.overall_status == "BLOCKED"

    def test_blocked_cooldown(
        self, canary_bot_id: str, f68a_overlay: dict[str, int],
        pre_apply_config: dict[str, object], with_l3_token: None,
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        d1 = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay, requires_human_approval=True,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
            pre_apply_config=pre_apply_config,
        )
        assert d1.overall_status == "APPLIED"

        d2 = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay, requires_human_approval=True,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
            pre_apply_config=pre_apply_config,
        )
        assert d2.overall_status == "COOLDOWN_ACTIVE"

    def test_blocked_dry_run_false(
        self, canary_bot_id: str, f68a_overlay: dict[str, int],
        pre_apply_config: dict[str, object], with_l3_token: None,
        tmp_state_dir: Path, tmp_overlay_dir: Path,
        tmp_plan_dir: Path, tmp_log_dir: Path,
    ) -> None:
        decision = run_controlled_apply_canary(
            candidate_sha="f68a031923d0", bot_id=canary_bot_id,
            parameter_overlay=f68a_overlay, requires_human_approval=True,
            state_dir=tmp_state_dir, overlay_dir=tmp_overlay_dir,
            plan_dir=tmp_plan_dir, log_dir=tmp_log_dir,
            pre_apply_config={"dry_run": False},
        )
        assert decision.overall_status == "BLOCKED"


# -- 11. summarise_decision ---------------------------------------------------


class TestSummarize:
    def test_summarize_applied(self) -> None:
        d = ControlledApplyDecision(
            overall_status="APPLIED", candidate_sha="f68a031923d0",
            bot_id=CANARY_BOT_ID, overlay_path="/tmp/o.json",
            rollback_plan_path="/tmp/r.json",
        )
        s = summarize_decision(d)
        assert s["status"] == "APPLIED"
        assert s["overlay_written"] is True

    def test_summarize_blocked(self) -> None:
        d = ControlledApplyDecision(
            overall_status="BLOCKED", candidate_sha="",
            bot_id="wrong-bot", errors=("Bot blocked",),
        )
        s = summarize_decision(d)
        assert s["status"] == "BLOCKED"
        assert s["overlay_written"] is False
