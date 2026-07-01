"""Tests for fleet_rollout_policy.py — Phase 9A.

All tests use tmp_path and synthetic decision packs — no real runtime
access, no Docker, no API calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from si_v2.rollout.fleet_rollout_policy import (
    CANARY_BOT,
    CONTROL_BOT,
    FREQAI_REBEL_BOT,
    REGIME_HYBRID_BOT,
    FleetBot,
    FleetRolloutPolicyInput,
    _grade_meets_minimum,
    evaluate_fleet_rollout_policy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_serial = 0


def _make_decision_pack(
    tmp_path: Path,
    *,
    decision: str = "KEEP_CANARY_OVERLAY",
    status: str = "FINAL_DECISION_EMITTED",
    target_bot: str = CANARY_BOT,
    runtime_mutation: str = "NONE",
    change_id: str = "change-9a-001",
    candidate_id: str = "candidate-9a-001",
    stat_rec: str | None = "STAT_KEEP",
    stat_grade: str | None = "MODERATE",
    stat_conflict_severity: str = "NONE",
    stat_conflict_has: bool = False,
    stat_ready: bool = True,
) -> str:
    """Write a synthetic decision pack with a unique filename."""
    global _serial
    _serial += 1
    pack: dict[str, object] = {
        "event": "autonomous_measurement_decision",
        "change_id": change_id,
        "candidate_id": candidate_id,
        "target_bot": target_bot,
        "decision": decision,
        "status": status,
        "runtime_mutation": runtime_mutation,
    }

    stat_conflict: dict[str, object] = {
        "has_conflict": stat_conflict_has,
        "severity": stat_conflict_severity,
        "simple_decision": decision,
        "stat_recommendation": stat_rec,
        "reason": "",
    }
    pack["statistical_conflict"] = stat_conflict

    if stat_rec is not None:
        stat_ev: dict[str, object] = {
            "status": "STAT_READY" if stat_ready else "STAT_INSUFFICIENT",
            "recommendation": stat_rec,
            "evidence_grade": stat_grade or "MODERATE",
            "canary_mean_profit": 0.3,
            "control_mean_profit": 0.1,
            "mean_profit_diff": 0.2,
        }
        pack["statistical_evidence"] = stat_ev
    else:
        pack["statistical_evidence"] = None

    path = tmp_path / f"decision_pack_{_serial}.json"
    path.write_text(json.dumps(pack))
    return str(path)


def _make_default_fleet() -> tuple[FleetBot, ...]:
    """Return the standard 4-bot fleet config."""
    return (
        FleetBot(bot_id=CANARY_BOT, role="canary",
                 dry_run=True, allow_rollout_target=False),
        FleetBot(bot_id=CONTROL_BOT, role="control",
                 dry_run=True, allow_rollout_target=True),
        FleetBot(bot_id=REGIME_HYBRID_BOT, role="experimental",
                 dry_run=True, allow_rollout_target=True),
        FleetBot(bot_id=FREQAI_REBEL_BOT, role="freqai",
                 dry_run=True, allow_rollout_target=True),
    )


def _default_input(
    tmp_path: Path,
    pack_path: str | None = None,
    **kwargs: object,
) -> FleetRolloutPolicyInput:
    """Create a default valid policy input."""
    resolved_path = pack_path or _make_decision_pack(tmp_path)
    defaults: dict[str, object] = {
        "decision_pack_path": resolved_path,
        "fleet_bots": _make_default_fleet(),
        "allowed_target_bots": (REGIME_HYBRID_BOT, FREQAI_REBEL_BOT),
        "min_stat_evidence_grade": "MODERATE",
        "require_statistical_evidence": True,
        "allow_control_promotion": False,
        "allow_experimental_promotion": True,
        "max_targets": 1,
    }
    defaults.update(kwargs)
    return FleetRolloutPolicyInput(**defaults)  # type: ignore[arg-type]


# ======================================================================
# Tests
# ======================================================================


class TestDecisionPackValidation:
    def test_blocks_missing_decision_pack(self, tmp_path: Path) -> None:
        """1. Block when decision pack file doesn't exist."""
        result = evaluate_fleet_rollout_policy(
            FleetRolloutPolicyInput(
                decision_pack_path="/nonexistent/pack.json",
                fleet_bots=(),
                allowed_target_bots=(),
            ),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("not_readable" in r for r in result.blocked_reasons)

    def test_blocks_non_keep_decision(self, tmp_path: Path) -> None:
        """2. Block when decision is not KEEP."""
        p = _make_decision_pack(tmp_path, decision="UNKNOWN_DECISION")
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("unexpected_decision" in r for r in result.blocked_reasons)

    def test_extend_decision_returns_promotion_extend_measurement(
        self, tmp_path: Path,
    ) -> None:
        """3. EXTEND decision returns PROMOTION_EXTEND_MEASUREMENT."""
        p = _make_decision_pack(tmp_path, decision="EXTEND_MEASUREMENT")
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_EXTEND_MEASUREMENT"

    def test_rollback_decision_blocks_promotion(
        self, tmp_path: Path,
    ) -> None:
        """4. ROLLBACK decision blocks promotion."""
        p = _make_decision_pack(
            tmp_path, decision="ROLLBACK_CANARY_OVERLAY",
        )
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("rollback" in r.lower() for r in result.blocked_reasons)

    def test_blocks_runtime_mutation_not_none(
        self, tmp_path: Path,
    ) -> None:
        """5. Block when runtime_mutation is not NONE."""
        p = _make_decision_pack(
            tmp_path, runtime_mutation="ROLLBACK_EXECUTED",
        )
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("runtime_mutation" in r for r in result.blocked_reasons)


class TestStatisticalEvidence:
    def test_blocks_hard_statistical_conflict(
        self, tmp_path: Path,
    ) -> None:
        """6. HARD conflict blocks promotion."""
        p = _make_decision_pack(
            tmp_path,
            stat_conflict_severity="HARD",
            stat_conflict_has=True,
        )
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("hard" in r.lower() for r in result.blocked_reasons)

    def test_blocks_missing_statistical_evidence_when_required(
        self, tmp_path: Path,
    ) -> None:
        """7. Missing stat evidence blocks when required."""
        p = _make_decision_pack(tmp_path, stat_rec=None, stat_grade=None)
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("missing" in r.lower() for r in result.blocked_reasons)

    def test_blocks_stat_recommendation_not_keep(
        self, tmp_path: Path,
    ) -> None:
        """8. Stat recommendation not KEEP blocks promotion."""
        p = _make_decision_pack(tmp_path, stat_rec="STAT_EXTEND")
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("not_keep" in r.lower() for r in result.blocked_reasons)

    def test_blocks_stat_grade_below_minimum(
        self, tmp_path: Path,
    ) -> None:
        """9. Stat grade below MODERATE blocks promotion."""
        p = _make_decision_pack(tmp_path, stat_grade="WEAK")
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                min_stat_evidence_grade="MODERATE",
            ),
        )
        assert result.status == "PROMOTION_BLOCKED"
        assert any("below_minimum" in r.lower() for r in result.blocked_reasons)

    def test_grade_meets_minimum(self) -> None:
        """Unit test for _grade_meets_minimum helper."""
        meets, reason = _grade_meets_minimum("STRONG", "MODERATE")
        assert meets is True
        assert reason is None

        meets, reason = _grade_meets_minimum("WEAK", "MODERATE")
        assert meets is False
        assert reason is not None

        meets, reason = _grade_meets_minimum(None, "MODERATE")
        assert meets is False
        assert reason is not None


class TestTargetSelection:
    def test_selects_one_allowed_experimental_target(
        self, tmp_path: Path,
    ) -> None:
        """10. Selects one eligible experimental target."""
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert len(result.selected_targets) == 1
        assert result.selected_targets[0] == REGIME_HYBRID_BOT

    def test_does_not_select_canary(self, tmp_path: Path) -> None:
        """11. Canary is not selected as target."""
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert CANARY_BOT not in result.selected_targets

    def test_does_not_select_control_by_default(
        self, tmp_path: Path,
    ) -> None:
        """12. Control not selected by default."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                allowed_target_bots=(CONTROL_BOT, REGIME_HYBRID_BOT),
            ),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert CONTROL_BOT not in result.selected_targets

    def test_selects_control_when_explicitly_allowed(
        self, tmp_path: Path,
    ) -> None:
        """13. Control selected when allow_control_promotion=True."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                allowed_target_bots=(CONTROL_BOT, REGIME_HYBRID_BOT),
                allow_control_promotion=True,
            ),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert CONTROL_BOT in result.selected_targets

    def test_respects_allowed_target_bots(
        self, tmp_path: Path,
    ) -> None:
        """14. Only bots in allowed_target_bots are selected."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                allowed_target_bots=(FREQAI_REBEL_BOT,),
            ),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert result.selected_targets == (FREQAI_REBEL_BOT,)

    def test_respects_max_targets(
        self, tmp_path: Path,
    ) -> None:
        """15. Max targets is respected."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                allowed_target_bots=(REGIME_HYBRID_BOT, FREQAI_REBEL_BOT),
                allow_experimental_promotion=True,
                max_targets=2,
            ),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert len(result.selected_targets) == 2

    def test_not_eligible_when_no_targets(
        self, tmp_path: Path,
    ) -> None:
        """16. Not eligible when no eligible targets."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p, allowed_target_bots=()),
            rollout_policy_dir=tmp_path / "out",
        )
        assert result.status == "PROMOTION_NOT_ELIGIBLE"
        assert any("no_eligible_targets" in r for r in result.blocked_reasons)


class TestArtifact:
    def test_writes_rollout_policy_artifact(
        self, tmp_path: Path,
    ) -> None:
        """17. Rollout policy artifact is written."""
        p = _make_decision_pack(tmp_path)
        policy_dir = tmp_path / "rollout_policies"
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
            rollout_policy_dir=policy_dir,
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert result.rollout_policy_path
        artifact = Path(result.rollout_policy_path)
        assert artifact.exists()
        data = json.loads(artifact.read_text())
        assert data["event"] == "fleet_rollout_policy_decision"
        assert data["status"] == "PROMOTION_ELIGIBLE"

    def test_no_runtime_mutation_in_artifact(
        self, tmp_path: Path,
    ) -> None:
        """19. Artifact has runtime_mutation=NONE."""
        p = _make_decision_pack(tmp_path)
        policy_dir = tmp_path / "no_mut"
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
            rollout_policy_dir=policy_dir,
        )
        artifact = Path(result.rollout_policy_path)
        data = json.loads(artifact.read_text())
        assert data["runtime_mutation"] == "NONE"

    def test_result_serializable(
        self, tmp_path: Path,
    ) -> None:
        """18. Result is JSON-serializable."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
            rollout_policy_dir=tmp_path / "ser",
        )
        d = result.to_dict()
        serialized = json.dumps(d)
        assert len(serialized) > 0


class TestEdgeCases:
    def test_missing_event_field(self, tmp_path: Path) -> None:
        """Block when event field is wrong."""
        pack = {
            "event": "wrong_event",
            "change_id": "ch-1",
            "candidate_id": "cand-1",
            "target_bot": CANARY_BOT,
            "decision": "KEEP_CANARY_OVERLAY",
            "status": "FINAL_DECISION_EMITTED",
            "runtime_mutation": "NONE",
            "statistical_evidence": None,
            "statistical_conflict": {
                "has_conflict": False,
                "severity": "NONE",
                "simple_decision": "KEEP_CANARY_OVERLAY",
                "stat_recommendation": "STAT_KEEP",
                "reason": "",
            },
        }
        p = tmp_path / "bad_event.json"
        p.write_text(json.dumps(pack))
        result = evaluate_fleet_rollout_policy(
            FleetRolloutPolicyInput(
                decision_pack_path=str(p),
                fleet_bots=(),
                allowed_target_bots=(),
            ),
        )
        assert result.status == "PROMOTION_BLOCKED"

    def test_empty_allowed_targets_list(self, tmp_path: Path) -> None:
        """Empty allowed list with valid pack returns NOT_ELIGIBLE."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p, allowed_target_bots=()),
            rollout_policy_dir=tmp_path / "empty",
        )
        assert result.status == "PROMOTION_NOT_ELIGIBLE"

    def test_allow_control_false_with_control_only_targets(
        self, tmp_path: Path,
    ) -> None:
        """No targets when only control is in allowed list but not allowed."""
        p = _make_decision_pack(tmp_path)
        result = evaluate_fleet_rollout_policy(
            _default_input(
                tmp_path,
                pack_path=p,
                allowed_target_bots=(CONTROL_BOT,),
                allow_control_promotion=False,
            ),
            rollout_policy_dir=tmp_path / "control_only",
        )
        assert result.status == "PROMOTION_NOT_ELIGIBLE"

    def test_artifact_written_with_experimental_target(
        self, tmp_path: Path,
    ) -> None:
        """Artifact correctly records experimental target."""
        p = _make_decision_pack(tmp_path)
        policy_dir = tmp_path / "exp_target"
        result = evaluate_fleet_rollout_policy(
            _default_input(tmp_path, pack_path=p),
            rollout_policy_dir=policy_dir,
        )
        assert result.status == "PROMOTION_ELIGIBLE"
        assert REGIME_HYBRID_BOT in result.selected_targets
