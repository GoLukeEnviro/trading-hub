"""Tests for the SI-v2 apply-chain evaluation stage (AUTONOMOUS_DRY_RUN).

Covers the fail-closed and canary-only contract end to end on isolated
temp paths: marker validation, kill-switch and RiskGuard fail-closed
reads, cycle freshness, bundle handling, allowlist mapping, cooldown,
and the two terminal outcomes the stage produces in production today
(NO_QUALIFIED_PROPOSAL for a non-canary candidate; a prepared canary
candidate otherwise, with the runtime stage deliberately unwired).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from si_v2.pipeline.apply_chain_evaluation import (
    ACTIVATION_RECORD_NAME,
    MARKER_ID,
    STATUS_APPLY_PREPARED,
    STATUS_BLOCKED_ACTIVATION_RECORD,
    STATUS_BLOCKED_BUNDLE,
    STATUS_BLOCKED_CANDIDATE,
    STATUS_BLOCKED_KILL_SWITCH,
    STATUS_BLOCKED_MARKER,
    STATUS_BLOCKED_RISKGUARD,
    STATUS_BLOCKED_STALE_CYCLE,
    STATUS_NO_QUALIFIED_PROPOSAL,
    ApplyChainEvaluationInput,
    evaluate_apply_chain,
    write_evaluation_record,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

MARKER_TEXT = f"""# Test marker

**Marker:** `{MARKER_ID}`
**Author:** Luke (GoLukeEnviro)
**Scope:** Agent0, AUTONOMOUS_DRY_RUN, dry-run only.
"""


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_repo(
    tmp_path: Path,
    *,
    marker: str = MARKER_TEXT,
    kill_switch_mode: str = "NORMAL",
    riskguard_status: str = "ACTIVE",
    candidates: list[dict[str, object]] | None = None,
    canary_config: dict[str, object] | None = None,
    with_bundle: bool = True,
) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "decisions").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "decisions" / f"{MARKER_ID}.md").write_text(marker, encoding="utf-8")

    _write_json(
        repo / "var" / "kill_switch.json",
        {"version": 2, "mode": kill_switch_mode, "safety_state": kill_switch_mode},
    )
    _write_json(
        repo / "orchestrator" / "state" / "riskguard" / "riskguard_state.json",
        {
            "schema_version": 1,
            "summary": {"status": riskguard_status},
            "pairs": {"BTC/USDT": {"verdict": "ACCEPTED"}},
        },
    )
    _write_json(
        repo / "freqforge-canary" / "user_data" / "config.json",
        canary_config
        if canary_config is not None
        else {"dry_run": True, "max_open_trades": 3, "strategy": "FreqForge_Override"},
    )
    if with_bundle:
        _write_json(
            repo / "self_improvement_v2" / "reports" / "phase2" / "evidence"
            / "active_cycle_20990101T000000Z.json",
            {
                "cycle_id": "20990101T000000Z",
                "proposal_candidates": candidates or [],
            },
        )
    return repo


def _input(repo: Path, tmp_path: Path, **overrides: object) -> ApplyChainEvaluationInput:
    values: dict[str, object] = {
        "repo_root": repo,
        "state_dir": tmp_path / "state",
        "cycle_log_dir": None,
    }
    values.update(overrides)
    return ApplyChainEvaluationInput(**values)  # type: ignore[arg-type]


CANARY_CANDIDATE: dict[str, object] = {
    "candidate_id": "canary_trades_3_to_2",
    "target_bot_ids": ["freqtrade-freqforge-canary"],
    "candidate_overlay": {"max_open_trades_candidate": 2},
    "hypothesis": "test",
}
NON_CANARY_CANDIDATE: dict[str, object] = {
    "candidate_id": "hybrid_trades_3_to_2",
    "target_bot_ids": ["freqtrade-regime-hybrid"],
    "candidate_overlay": {"max_open_trades_candidate": 2},
    "hypothesis": "test",
}


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------


class TestMarkerGate:
    def test_missing_marker_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "docs" / "decisions" / f"{MARKER_ID}.md").unlink()
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_MARKER

    def test_incomplete_marker_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, marker="# something else entirely\n")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_MARKER
        assert "marker_incomplete" in result.reason

    def test_marker_without_author_blocks(self, tmp_path: Path) -> None:
        text = f"**Marker:** `{MARKER_ID}`\nScope: AUTONOMOUS_DRY_RUN\n"
        repo = _make_repo(tmp_path, marker=text)
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_MARKER

    def test_invalid_activation_record_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / ACTIVATION_RECORD_NAME).write_text("{not json", encoding="utf-8")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_ACTIVATION_RECORD

    def test_valid_activation_record_passes(self, tmp_path: Path) -> None:
        repo = _make_repo(
            tmp_path,
            candidates=[CANARY_CANDIDATE],
            canary_config={
                "dry_run": True,
                "max_open_trades": 3,
                "strategy": "FreqForge_Override",
            },
        )
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            state_dir / ACTIVATION_RECORD_NAME,
            {"marker": MARKER_ID, "mode": "AUTONOMOUS_DRY_RUN"},
        )
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status != STATUS_BLOCKED_ACTIVATION_RECORD
        assert result.status != STATUS_BLOCKED_MARKER


# ---------------------------------------------------------------------------
# Safety reads (fail-closed)
# ---------------------------------------------------------------------------


class TestSafetyReads:
    def test_halt_new_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, kill_switch_mode="HALT_NEW")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_KILL_SWITCH

    def test_emergency_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, kill_switch_mode="EMERGENCY")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_KILL_SWITCH

    def test_missing_kill_switch_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "var" / "kill_switch.json").unlink()
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_KILL_SWITCH

    def test_riskguard_inactive_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, riskguard_status="INACTIVE")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_RISKGUARD

    def test_riskguard_missing_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "orchestrator" / "state" / "riskguard" / "riskguard_state.json").unlink()
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_RISKGUARD

    def test_riskguard_block_entry_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        _write_json(
            repo / "orchestrator" / "state" / "riskguard" / "riskguard_state.json",
            {
                "schema_version": 1,
                "summary": {"status": "ACTIVE"},
                "pairs": {
                    "BTC/USDT": {"verdict": "ACCEPTED"},
                    "ETH/USDT": {"verdict": "BLOCK_ENTRY"},
                },
            },
        )
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_RISKGUARD


# ---------------------------------------------------------------------------
# Freshness + bundle
# ---------------------------------------------------------------------------


class TestFreshnessAndBundle:
    def test_stale_cycle_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[CANARY_CANDIDATE])
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stale = log_dir / "cycle-20990101T000000Z.log"
        stale.write_text("x", encoding="utf-8")
        old = 0.0
        os.utime(stale, (old, old))
        result = evaluate_apply_chain(
            _input(repo, tmp_path, cycle_log_dir=log_dir, cycle_stale_after_seconds=60)
        )
        assert result.status == STATUS_BLOCKED_STALE_CYCLE

    def test_fresh_cycle_passes(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[NON_CANARY_CANDIDATE])
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "cycle-20990101T000000Z.log").write_text("x", encoding="utf-8")
        result = evaluate_apply_chain(
            _input(repo, tmp_path, cycle_log_dir=log_dir, cycle_stale_after_seconds=3600)
        )
        assert result.status == STATUS_NO_QUALIFIED_PROPOSAL

    def test_missing_bundle_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, with_bundle=False)
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_BUNDLE

    def test_no_candidates_is_no_apply(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_NO_QUALIFIED_PROPOSAL
        assert result.event == "NO_APPLY"
        assert result.is_alert() is False


# ---------------------------------------------------------------------------
# Candidate scope + allowlist
# ---------------------------------------------------------------------------


class TestCandidateScope:
    def test_non_canary_is_no_qualified_proposal(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[NON_CANARY_CANDIDATE])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_NO_QUALIFIED_PROPOSAL
        assert result.event == "NO_APPLY"
        assert "stage1_canary_only" in result.reason
        assert result.target_bot == "freqtrade-regime-hybrid"

    def test_multiple_targets_block(self, tmp_path: Path) -> None:
        candidate = dict(CANARY_CANDIDATE)
        candidate["target_bot_ids"] = [
            "freqtrade-freqforge-canary",
            "freqtrade-regime-hybrid",
        ]
        repo = _make_repo(tmp_path, candidates=[candidate])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE

    def test_two_params_block(self, tmp_path: Path) -> None:
        candidate = dict(CANARY_CANDIDATE)
        candidate["candidate_overlay"] = {
            "max_open_trades_candidate": 2,
            "cooldown_candles_candidate": 12,
        }
        repo = _make_repo(tmp_path, candidates=[candidate])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE
        assert "exactly one required" in result.reason

    def test_out_of_range_blocks(self, tmp_path: Path) -> None:
        candidate = dict(CANARY_CANDIDATE)
        candidate["candidate_overlay"] = {"max_open_trades_candidate": 999}
        repo = _make_repo(tmp_path, candidates=[candidate])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE
        assert "outside_allowlist" in result.reason

    def test_non_numeric_blocks(self, tmp_path: Path) -> None:
        candidate = dict(CANARY_CANDIDATE)
        candidate["candidate_overlay"] = {"max_open_trades_candidate": "two"}
        repo = _make_repo(tmp_path, candidates=[candidate])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE
        assert "not_numeric" in result.reason

    def test_unknown_param_blocks(self, tmp_path: Path) -> None:
        candidate = dict(CANARY_CANDIDATE)
        candidate["candidate_overlay"] = {"stake_currency_candidate": "USDT"}
        repo = _make_repo(tmp_path, candidates=[candidate])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE

    def test_canary_config_not_dry_run_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(
            tmp_path,
            candidates=[CANARY_CANDIDATE],
            canary_config={"dry_run": False, "max_open_trades": 3},
        )
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE
        assert "not_dry_run" in result.reason


# ---------------------------------------------------------------------------
# Cooldown + positive path
# ---------------------------------------------------------------------------


class TestCooldownAndPositive:
    def _fresh_cooldown(self, state_dir: Path) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            state_dir / "cooldown_state.json",
            {"last_apply_utc": "2000-01-01T00:00:00+00:00", "candidate_sha": "x", "bot_id": "y"},
        )

    def test_active_cooldown_blocks(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[CANARY_CANDIDATE])
        state_dir = tmp_path / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            state_dir / "cooldown_state.json",
            {
                "last_apply_utc": datetime.now(UTC).isoformat(),
                "candidate_sha": "x",
                "bot_id": "y",
            },
        )
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_BLOCKED_CANDIDATE
        assert "cooldown" in result.reason

    def test_qualified_canary_candidate_is_prepared(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[CANARY_CANDIDATE])
        state_dir = tmp_path / "state"
        self._fresh_cooldown(state_dir)
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.status == STATUS_APPLY_PREPARED, result.reason
        assert result.event == "PREPARED"
        assert result.target_bot == "freqtrade-freqforge-canary"
        assert result.detail.get("parameter") == "max_open_trades"
        assert result.detail.get("value") == 2
        assert result.executed_runtime is False
        assert result.detail.get("runtime_execution_wired") is False

        # Prepared artifacts exist on isolated paths only.
        overlay = Path(str(result.detail["overlay_path"]))
        assert overlay.is_file()
        assert overlay.parent == repo / "freqforge-canary" / "user_data"
        assert overlay.name.startswith("overlay_")
        assert overlay.name.endswith(".json")
        rollback = Path(str(result.detail["rollback_plan_path"]))
        assert rollback.is_file()
        assert (state_dir / "audit" / "autonomous_dry_run_executor.jsonl").is_file()
        # The pipeline-level readiness check depends on the (unwritable)
        # orchestrator state dir on this host; both allowed statuses mean
        # "all policy gates passed".
        assert result.detail.get("pipeline_status") in (
            "READY_FOR_AUTONOMOUS_DRY_RUN_APPLY",
            "AUTO_DRY_RUN_APPROVED",
        )
        assert result.detail.get("ceremony_status") == "CEREMONY_READY"

    def test_positive_path_is_alert(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[CANARY_CANDIDATE])
        self._fresh_cooldown(tmp_path / "state")
        result = evaluate_apply_chain(_input(repo, tmp_path))
        assert result.is_alert() is True


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------


class TestRecording:
    def test_record_and_audit_written(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[NON_CANARY_CANDIDATE])
        result = evaluate_apply_chain(_input(repo, tmp_path))
        paths = write_evaluation_record(result, tmp_path / "state")
        record = Path(paths["record_path"])
        audit = Path(paths["audit_path"])
        assert record.is_file()
        assert audit.is_file()
        payload = json.loads(record.read_text(encoding="utf-8"))
        assert payload["status"] == STATUS_NO_QUALIFIED_PROPOSAL
        assert payload["executed_runtime"] is False
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["status"] == STATUS_NO_QUALIFIED_PROPOSAL

    def test_two_runs_append_audit(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path, candidates=[NON_CANARY_CANDIDATE])
        state_dir = tmp_path / "state"
        for _ in range(2):
            result = evaluate_apply_chain(_input(repo, tmp_path))
            write_evaluation_record(result, state_dir)
        lines = (
            (state_dir / "audit" / "apply_chain_audit.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        )
        assert len(lines) == 2
