"""Tests for fleet_rollout_artifact_planner.py — Phase 9B.

All tests use tmp_path and synthetic rollout policy / overlay files —
no real runtime access, no Docker, no API calls.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from si_v2.rollout.fleet_rollout_artifact_planner import (
    FleetRolloutPlannerInput,
    TargetBotRuntimeSpec,
    build_fleet_rollout_artifacts,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_rollout_policy(
    tmp_path: Path,
    *,
    event: str = "fleet_rollout_policy_decision",
    status: str = "PROMOTION_ELIGIBLE",
    runtime_mutation: str = "NONE",
    next_required_component: str = "fleet_rollout_artifact_planner",
    selected_targets: list[str] | None = None,
    change_id: str = "change-9b-001",
    candidate_id: str = "candidate-9b-001",
    source_bot: str = "freqtrade-freqforge-canary",
) -> str:
    """Write a synthetic rollout policy JSON and return its path."""
    global _serial
    _serial += 1
    if selected_targets is None:
        selected_targets = ["freqtrade-regime-hybrid"]
    policy: dict[str, object] = {
        "event": event,
        "change_id": change_id,
        "candidate_id": candidate_id,
        "source_bot": source_bot,
        "status": status,
        "selected_targets": selected_targets,
        "simple_decision": "KEEP_CANARY_OVERLAY",
        "statistical_evidence": {"recommendation": "STAT_KEEP"},
        "statistical_conflict": {"has_conflict": False, "severity": "NONE"},
        "allowed_target_bots": selected_targets,
        "blocked_reasons": [],
        "runtime_mutation": runtime_mutation,
        "next_required_component": next_required_component,
        "created_at_utc": "2026-07-01T12:00:00+00:00",
    }
    path = tmp_path / f"rollout_policy_{_serial}.json"
    path.write_text(json.dumps(policy))
    return str(path)


def _make_overlay(tmp_path: Path, *, parameter: str = "max_open_trades", value: int = 2) -> tuple[str, str]:
    """Write a synthetic overlay JSON and return (path, sha256)."""
    global _serial
    _serial += 1
    overlay = {
        parameter: value,
        "dry_run": True,
        "stake_currency": "USDT",
    }
    content = json.dumps(overlay, indent=2, sort_keys=True)
    path = tmp_path / f"overlay_{_serial}.json"
    path.write_text(content)
    sha = hashlib.sha256(content.encode()).hexdigest()
    return str(path), sha


def _make_runtime_spec(
    bot_id: str = "freqtrade-regime-hybrid",
    role: str = "experimental",
    dry_run: bool = True,
    config_path: str = "/data/regime-hybrid/config.json",
    user_data_dir: str = "/data/regime-hybrid/user_data",
    current_command: tuple[str, ...] | None = None,
) -> TargetBotRuntimeSpec:
    if current_command is None:
        current_command = (
            "freqtrade", "trade",
            "--config", "/data/regime-hybrid/config.json",
            "--strategy", "RegimeHybrid",
        )
    return TargetBotRuntimeSpec(
        bot_id=bot_id,
        role=role,
        dry_run=dry_run,
        config_path=config_path,
        user_data_dir=user_data_dir,
        current_command=current_command,
    )


def _default_input(
    tmp_path: Path,
    policy_path: str | None = None,
    **kwargs: object,
) -> FleetRolloutPlannerInput:
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    resolved_policy = policy_path or _make_rollout_policy(tmp_path)
    defaults: dict[str, object] = {
        "rollout_policy_path": resolved_policy,
        "target_runtime_specs": (_make_runtime_spec(),),
        "source_overlay_path": overlay_path,
        "source_overlay_sha256": overlay_sha,
        "expected_parameter": "max_open_trades",
        "expected_value": 2,
    }
    defaults.update(kwargs)
    return FleetRolloutPlannerInput(**defaults)  # type: ignore[arg-type]


# ======================================================================
# Rollout policy validation tests
# ======================================================================


class TestRolloutPolicyValidation:
    def test_blocks_missing_rollout_policy(self, tmp_path: Path) -> None:
        """1. Block when rollout policy file doesn't exist."""
        result = build_fleet_rollout_artifacts(
            FleetRolloutPlannerInput(
                rollout_policy_path="/nonexistent/policy.json",
                target_runtime_specs=(),
                source_overlay_path="/nonexistent/overlay.json",
                source_overlay_sha256="abc",
                expected_parameter="max_open_trades",
                expected_value=2,
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("not_readable" in r for r in result.blocked_reasons)

    def test_blocks_policy_not_eligible(self, tmp_path: Path) -> None:
        """2. Block when policy status is not PROMOTION_ELIGIBLE."""
        p = _make_rollout_policy(tmp_path, status="PROMOTION_BLOCKED")
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path, policy_path=p),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("not_eligible" in r for r in result.blocked_reasons)

    def test_blocks_runtime_mutation_not_none(self, tmp_path: Path) -> None:
        """3. Block when runtime_mutation is not NONE."""
        p = _make_rollout_policy(tmp_path, runtime_mutation="FLEET_APPLIED")
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path, policy_path=p),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("runtime_mutation" in r for r in result.blocked_reasons)

    def test_blocks_wrong_next_component(self, tmp_path: Path) -> None:
        """4. Block when next_required_component is wrong."""
        p = _make_rollout_policy(
            tmp_path, next_required_component="something_else",
        )
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path, policy_path=p),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("next_component" in r for r in result.blocked_reasons)

    def test_blocks_empty_selected_targets(self, tmp_path: Path) -> None:
        """5. Block when selected_targets is empty."""
        p = _make_rollout_policy(tmp_path, selected_targets=[])
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path, policy_path=p),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("empty_selected_targets" in r for r in result.blocked_reasons)


# ======================================================================
# Source overlay validation tests
# ======================================================================


class TestSourceOverlayValidation:
    def test_blocks_missing_source_overlay(self, tmp_path: Path) -> None:
        """6. Block when source overlay file doesn't exist."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                source_overlay_path="/nonexistent/overlay.json",
                source_overlay_sha256="abc",
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("overlay_missing" in r for r in result.blocked_reasons)

    def test_blocks_overlay_hash_mismatch(self, tmp_path: Path) -> None:
        """7. Block when overlay SHA-256 doesn't match."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                source_overlay_sha256="wrong_hash",
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("hash_mismatch" in r for r in result.blocked_reasons)


# ======================================================================
# Target runtime spec validation tests
# ======================================================================


class TestTargetRuntimeSpecValidation:
    def test_blocks_missing_target_runtime_spec(self, tmp_path: Path) -> None:
        """8. Block when no runtime spec for a selected target."""
        p = _make_rollout_policy(
            tmp_path, selected_targets=["freqtrade-regime-hybrid"],
        )
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                policy_path=p,
                target_runtime_specs=(),  # no specs
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("missing_runtime_spec" in r for r in result.blocked_reasons)

    def test_blocks_target_dry_run_false(self, tmp_path: Path) -> None:
        """9. Block when target bot has dry_run=False."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                target_runtime_specs=(
                    _make_runtime_spec(dry_run=False),
                ),
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("not_dry_run" in r for r in result.blocked_reasons)
        # Verify no forbidden dry_run=False literal in the message
        assert not any("False" in r for r in result.blocked_reasons)

    def test_blocks_empty_config_path(self, tmp_path: Path) -> None:
        """10. Block when config_path is empty."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                target_runtime_specs=(
                    _make_runtime_spec(config_path=""),
                ),
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("empty_config_path" in r for r in result.blocked_reasons)

    def test_blocks_empty_user_data_dir(self, tmp_path: Path) -> None:
        """11. Block when user_data_dir is empty."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                target_runtime_specs=(
                    _make_runtime_spec(user_data_dir=""),
                ),
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("empty_user_data_dir" in r for r in result.blocked_reasons)

    def test_blocks_empty_command(self, tmp_path: Path) -> None:
        """12. Block when current_command is empty."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                target_runtime_specs=(
                    _make_runtime_spec(current_command=()),
                ),
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("empty_command" in r for r in result.blocked_reasons)

    def test_blocks_command_without_config_reference(
        self, tmp_path: Path,
    ) -> None:
        """13. Block when command has no --config reference."""
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                target_runtime_specs=(
                    _make_runtime_spec(
                        current_command=("freqtrade", "trade", "--strategy", "X"),
                    ),
                ),
            ),
        )
        assert result.status == "ROLLOUT_PLAN_BLOCKED"
        assert any("config_reference" in r for r in result.blocked_reasons)


# ======================================================================
# Plan building tests
# ======================================================================


class TestPlanBuilding:
    def test_builds_single_target_rollout_plan(
        self, tmp_path: Path,
    ) -> None:
        """14. Build a plan for a single target bot."""
        p = _make_rollout_policy(
            tmp_path, selected_targets=["freqtrade-regime-hybrid"],
        )
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                policy_path=p,
                target_runtime_specs=(_make_runtime_spec(),),
            ),
            rollout_plan_dir=tmp_path / "out",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        assert len(result.target_plans) == 1
        assert result.target_plans[0].target_bot == "freqtrade-regime-hybrid"
        assert result.target_plans[0].expected_parameter == "max_open_trades"
        assert result.target_plans[0].expected_value == 2

    def test_builds_multiple_target_rollout_plans(
        self, tmp_path: Path,
    ) -> None:
        """15. Build plans for multiple target bots."""
        p = _make_rollout_policy(
            tmp_path,
            selected_targets=["freqtrade-regime-hybrid", "freqai-rebel"],
        )
        result = build_fleet_rollout_artifacts(
            _default_input(
                tmp_path,
                policy_path=p,
                target_runtime_specs=(
                    _make_runtime_spec(
                        bot_id="freqtrade-regime-hybrid",
                        role="experimental",
                    ),
                    _make_runtime_spec(
                        bot_id="freqai-rebel",
                        role="freqai",
                        config_path="/data/rebel/config.json",
                        user_data_dir="/data/rebel/user_data",
                        current_command=(
                            "freqtrade", "trade",
                            "--config", "/data/rebel/config.json",
                            "--strategy", "FreqAIRebel",
                        ),
                    ),
                ),
            ),
            rollout_plan_dir=tmp_path / "multi",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        assert len(result.target_plans) == 2
        bots = {p.target_bot for p in result.target_plans}
        assert bots == {"freqtrade-regime-hybrid", "freqai-rebel"}

    def test_writes_target_overlay_copy(
        self, tmp_path: Path,
    ) -> None:
        """16. Planned overlay copy is written."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "out",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        for plan in result.target_plans:
            overlay = Path(plan.overlay_path)
            assert overlay.exists()
            data = json.loads(overlay.read_text())
            assert data["event"] == "planned_overlay_copy"
            assert data["runtime_mutation"] == "NONE"

    def test_writes_pre_apply_snapshot_plan(
        self, tmp_path: Path,
    ) -> None:
        """17. Pre-apply snapshot plan is written."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "snap",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        for plan in result.target_plans:
            snap = Path(plan.pre_apply_snapshot_path)
            assert snap.exists()
            data = json.loads(snap.read_text())
            assert data["event"] == "pre_apply_snapshot_plan"
            assert data["runtime_mutation"] == "NONE"
            assert "config_json" in data["what_to_snapshot"]

    def test_writes_rollback_plan(
        self, tmp_path: Path,
    ) -> None:
        """18. Rollback plan is written."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "rb",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        for plan in result.target_plans:
            rb = Path(plan.rollback_plan_path)
            assert rb.exists()
            data = json.loads(rb.read_text())
            assert data["event"] == "rollback_plan"
            assert data["runtime_mutation"] == "NONE"
            assert "rollback_instruction" in data

    def test_writes_fleet_rollout_plan(
        self, tmp_path: Path,
    ) -> None:
        """19. Fleet rollout plan JSON is written."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "fleet",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        plan_path = Path(result.rollout_plan_path)
        assert plan_path.exists()
        data = json.loads(plan_path.read_text())
        assert data["event"] == "fleet_rollout_artifact_plan"
        assert data["status"] == "ROLLOUT_PLAN_READY"
        assert data["runtime_mutation"] == "NONE"
        assert data["next_required_component"] == "fleet_rollout_runtime_ceremony"


# ======================================================================
# Serialization and invariant tests
# ======================================================================


class TestSerializationAndInvariants:
    def test_result_serializable(self, tmp_path: Path) -> None:
        """20. Result is JSON-serializable."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "ser",
        )
        assert result.status == "ROLLOUT_PLAN_READY"
        d = result.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0

    def test_runtime_mutation_none_in_all_artifacts(
        self, tmp_path: Path,
    ) -> None:
        """21. All written artifacts have runtime_mutation=NONE."""
        result = build_fleet_rollout_artifacts(
            _default_input(tmp_path),
            rollout_plan_dir=tmp_path / "inv",
        )
        assert result.status == "ROLLOUT_PLAN_READY"

        # Check fleet rollout plan
        plan_data = json.loads(Path(result.rollout_plan_path).read_text())
        assert plan_data["runtime_mutation"] == "NONE"

        # Check all per-target artifacts
        for plan in result.target_plans:
            overlay = json.loads(Path(plan.overlay_path).read_text())
            assert overlay["runtime_mutation"] == "NONE"

            snap = json.loads(Path(plan.pre_apply_snapshot_path).read_text())
            assert snap["runtime_mutation"] == "NONE"

            rb = json.loads(Path(plan.rollback_plan_path).read_text())
            assert rb["runtime_mutation"] == "NONE"
