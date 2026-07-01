"""Tests for fleet_rollout_input_resolver.py — Phase 10.1.

All tests use tmp_path, fake decision packs, fake overlays, and fake
bot registries — no real runtime, no API, no Docker.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from si_v2.rollout.fleet_rollout_chain_runner import (
    FleetRolloutChainInput,
    maybe_resolve_and_run_fleet_rollout_chain,
    run_fleet_rollout_chain,
)
from si_v2.rollout.fleet_rollout_input_resolver import (
    resolve_fleet_rollout_chain_input,
)
from si_v2.rollout.fleet_rollout_policy import (
    CANARY_BOT,
    CONTROL_BOT,
    FREQAI_REBEL_BOT,
    REGIME_HYBRID_BOT,
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
    change_id: str = "change-10-001",
    candidate_id: str = "candidate-10-001",
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


def _make_overlay(
    tmp_path: Path,
    *,
    parameter: str = "max_open_trades",
    value: int = 2,
    dry_run: bool = True,
) -> tuple[str, str]:
    """Write a synthetic overlay JSON and return (path, sha256)."""
    global _serial
    _serial += 1
    overlay: dict[str, object] = {
        parameter: value,
        "dry_run": dry_run,
        "stake_currency": "USDT",
    }
    content = json.dumps(overlay, indent=2, sort_keys=True)
    path = tmp_path / f"overlay_{_serial}.json"
    path.write_text(content)
    sha = hashlib.sha256(content.encode()).hexdigest()
    return str(path), sha


def _make_bot_registry(
    tmp_path: Path,
    *,
    enabled_bots: tuple[str, ...] | None = None,
) -> str:
    """Write a synthetic fleet bot registry JSON."""
    global _serial
    _serial += 1

    all_bots = [
        {
            "bot_id": "freqtrade-freqforge",
            "base_url": "http://trading-freqtrade-freqforge-1:8080",
            "dry_run_expected": True,
            "enabled": True,
        },
        {
            "bot_id": "freqtrade-freqforge-canary",
            "base_url": "http://trading-freqtrade-freqforge-canary-1:8080",
            "dry_run_expected": True,
            "enabled": True,
        },
        {
            "bot_id": "freqtrade-regime-hybrid",
            "base_url": "http://trading-freqtrade-regime-hybrid-1:8080",
            "dry_run_expected": True,
            "enabled": True,
        },
        {
            "bot_id": "freqai-rebel",
            "base_url": "http://trading-freqai-rebel-1:8080",
            "dry_run_expected": True,
            "enabled": True,
        },
    ]

    if enabled_bots is not None:
        enabled_set = set(enabled_bots)
        for bot in all_bots:
            bot["enabled"] = bot["bot_id"] in enabled_set

    registry = {"schema_version": 2, "bots": all_bots}
    path = tmp_path / f"bot_registry_{_serial}.json"
    path.write_text(json.dumps(registry, indent=2))
    return str(path)


def _make_candidate_overlay(
    *,
    max_open_trades_candidate: int | None = 2,
    cooldown_candles_candidate: int | None = None,
    stop_duration_candles_candidate: int | None = None,
    entry_threshold_candidate: float | None = None,
    exit_threshold_candidate: float | None = None,
    pair_cluster_action: str | None = None,
) -> dict[str, object]:
    """Build a synthetic candidate overlay dict."""
    overlay: dict[str, object] = {}
    if max_open_trades_candidate is not None:
        overlay["max_open_trades_candidate"] = max_open_trades_candidate
    if cooldown_candles_candidate is not None:
        overlay["cooldown_candles_candidate"] = cooldown_candles_candidate
    if stop_duration_candles_candidate is not None:
        overlay["stop_duration_candles_candidate"] = stop_duration_candles_candidate
    if entry_threshold_candidate is not None:
        overlay["entry_threshold_candidate"] = entry_threshold_candidate
    if exit_threshold_candidate is not None:
        overlay["exit_threshold_candidate"] = exit_threshold_candidate
    if pair_cluster_action is not None:
        overlay["pair_cluster_action"] = pair_cluster_action
    return overlay


# ---------------------------------------------------------------------------
# Test 1: Disabled Hook
# ---------------------------------------------------------------------------


def test_resolver_hook_default_disabled(tmp_path: Path) -> None:
    """Active cycle hook returns None when disabled."""
    result = maybe_resolve_and_run_fleet_rollout_chain(
        fleet_rollout_chain_enabled=False,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Test 2: Missing Decision Pack
# ---------------------------------------------------------------------------


def test_resolver_missing_decision_pack(tmp_path: Path) -> None:
    """Missing decision pack -> CHAIN_INPUT_NOT_FOUND."""
    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=str(tmp_path / "nonexistent.json"),
        bot_registry_path=_make_bot_registry(tmp_path),
    )
    assert result.status == "CHAIN_INPUT_NOT_FOUND"
    assert any("not_readable" in r for r in result.blocked_reasons)
    assert result.chain_input is None


def test_resolver_missing_decision_pack_dir(tmp_path: Path) -> None:
    """Non-existent decision pack dir -> CHAIN_INPUT_NOT_FOUND."""
    result = resolve_fleet_rollout_chain_input(
        decision_pack_dir=str(tmp_path / "nonexistent_dir"),
        bot_registry_path=_make_bot_registry(tmp_path),
    )
    assert result.status == "CHAIN_INPUT_NOT_FOUND"
    assert any("not_found" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 3: Deterministischer Lookup
# ---------------------------------------------------------------------------


def test_resolver_deterministic_lookup(tmp_path: Path) -> None:
    """Multiple decision packs: picks the newest qualified one."""
    import time
    # Create an older qualified pack
    _make_decision_pack(
        tmp_path, change_id="change-old", candidate_id="candidate-old",
    )
    time.sleep(0.05)  # Ensure different mtime
    # Create a newer qualified pack
    _make_decision_pack(
        tmp_path, change_id="change-new", candidate_id="candidate-new",
    )

    result = resolve_fleet_rollout_chain_input(
        decision_pack_dir=str(tmp_path),
        bot_registry_path=_make_bot_registry(tmp_path),
        explicit_overlay_path=_make_overlay(tmp_path)[0],
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    # Should pick the newest qualified pack — verify by reading the pack
    pack_data = json.loads(Path(result.decision_pack_path).read_text())
    assert pack_data.get("change_id") == "change-new"


def test_resolver_ignores_unqualified_packs(tmp_path: Path) -> None:
    """Unqualified packs (wrong decision, wrong status) are ignored."""
    # Create an unqualified pack (EXTEND_MEASUREMENT)
    _make_decision_pack(tmp_path, decision="EXTEND_MEASUREMENT")
    # Create a qualified pack
    _make_decision_pack(tmp_path, change_id="change-qualified")

    result = resolve_fleet_rollout_chain_input(
        decision_pack_dir=str(tmp_path),
        bot_registry_path=_make_bot_registry(tmp_path),
        explicit_overlay_path=_make_overlay(tmp_path)[0],
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None


# ---------------------------------------------------------------------------
# Test 4: Valid Decision Pack + Registry + Overlay
# ---------------------------------------------------------------------------


def test_resolver_valid_artifacts_ready(tmp_path: Path) -> None:
    """Valid artifacts -> CHAIN_INPUT_READY."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, overlay_sha = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    assert result.chain_input.source_overlay_path == overlay_path
    assert result.chain_input.source_overlay_sha256 == overlay_sha
    assert result.chain_input.expected_parameter == "max_open_trades"
    assert result.chain_input.expected_value == 2
    assert result.chain_input.execute_fleet_runtime is False


def test_resolver_chain_ready_from_resolved_input(tmp_path: Path) -> None:
    """Resolved input -> run_fleet_rollout_chain -> FLEET_CHAIN_READY."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    resolution = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert resolution.status == "CHAIN_INPUT_READY"
    assert resolution.chain_input is not None

    chain_result = run_fleet_rollout_chain(
        resolution.chain_input,
        chain_output_dir=tmp_path,
    )
    assert chain_result.status == "FLEET_CHAIN_READY"
    assert chain_result.chain_audit_path != ""
    audit_path = Path(chain_result.chain_audit_path)
    assert audit_path.exists()
    audit = json.loads(audit_path.read_text())
    assert audit["event"] == "fleet_rollout_chain_audit"
    assert audit["status"] == "FLEET_CHAIN_READY"
    assert audit["runtime_mutation"] == "NONE"


# ---------------------------------------------------------------------------
# Test 5: Candidate Overlay Materialisierung
# ---------------------------------------------------------------------------


def test_resolver_materializes_candidate_overlay(tmp_path: Path) -> None:
    """Resolver materializes source_overlay.json from candidate_overlay."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(max_open_trades_candidate=2)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
        resolver_output_dir=str(tmp_path / "resolver_output"),
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    assert result.source_overlay_path != ""
    assert result.source_overlay_sha256 != ""

    # Verify the materialized file exists
    overlay_path = Path(result.source_overlay_path)
    assert overlay_path.exists()
    overlay_data = json.loads(overlay_path.read_text())
    assert overlay_data.get("max_open_trades") == 2
    assert overlay_data.get("dry_run") is True

    # Verify SHA256 matches actual file content
    actual_sha = hashlib.sha256(overlay_path.read_bytes()).hexdigest()
    assert result.source_overlay_sha256 == actual_sha

    # Verify expected parameter/value
    assert result.chain_input.expected_parameter == "max_open_trades"
    assert result.chain_input.expected_value == 2


def test_resolver_materialized_overlay_sha256_matches(tmp_path: Path) -> None:
    """SHA256 from resolver matches actual file content."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(
        max_open_trades_candidate=None,
        cooldown_candles_candidate=12,
    )

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
        resolver_output_dir=str(tmp_path / "resolver_output"),
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None

    overlay_path = Path(result.source_overlay_path)
    actual_sha = hashlib.sha256(overlay_path.read_bytes()).hexdigest()
    assert result.source_overlay_sha256 == actual_sha
    assert result.chain_input.expected_parameter == "cooldown_candles"
    assert result.chain_input.expected_value == 12


# ---------------------------------------------------------------------------
# Test 6: Unsafe Overlay Key
# ---------------------------------------------------------------------------


def test_resolver_blocks_unsafe_overlay_key(tmp_path: Path) -> None:
    """stake_amount / stoploss / minimal_roi / pair_whitelist -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    for unsafe_key in ("stake_amount", "stoploss", "minimal_roi", "pair_whitelist", "pair_blacklist"):
        overlay_path, _ = _make_overlay(tmp_path, parameter=unsafe_key, value=100)
        result = resolve_fleet_rollout_chain_input(
            decision_pack_path=pack_path,
            bot_registry_path=registry_path,
            explicit_overlay_path=overlay_path,
        )
        assert result.status == "CHAIN_INPUT_BLOCKED", f"Expected BLOCKED for {unsafe_key}"
        assert any("blocked_key" in r for r in result.blocked_reasons), (
            f"Expected blocked_key reason for {unsafe_key}, got {result.blocked_reasons}"
        )


# ---------------------------------------------------------------------------
# Test 7: Mehrere rolloutfähige Parameter
# ---------------------------------------------------------------------------


def test_resolver_blocks_multiple_rollout_params(tmp_path: Path) -> None:
    """Multiple rollout parameters in candidate_overlay -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(
        max_open_trades_candidate=2,
        cooldown_candles_candidate=12,
    )

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("multiple" in r for r in result.blocked_reasons)


def test_resolver_blocks_multiple_params_in_explicit_overlay(tmp_path: Path) -> None:
    """Multiple rollout params in explicit overlay -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    # Create an overlay with two rollout parameters
    overlay = {
        "max_open_trades": 2,
        "cooldown_candles": 12,
        "dry_run": True,
    }
    overlay_path = tmp_path / "multi_param_overlay.json"
    overlay_path.write_text(json.dumps(overlay))

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=str(overlay_path),
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("multiple" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 8: Non-numeric Value
# ---------------------------------------------------------------------------


def test_resolver_blocks_non_numeric_value(tmp_path: Path) -> None:
    """Non-numeric value in candidate_overlay -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(max_open_trades_candidate=2)
    # Add a non-numeric candidate key
    candidate["entry_threshold_candidate"] = "high"  # type: ignore[assignment]

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("non_numeric" in r for r in result.blocked_reasons)


def test_resolver_blocks_non_numeric_in_explicit_overlay(tmp_path: Path) -> None:
    """Non-numeric value in explicit overlay -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    overlay = {
        "max_open_trades": "two",  # type: ignore[assignment]
        "dry_run": True,
    }
    overlay_path = tmp_path / "non_numeric_overlay.json"
    overlay_path.write_text(json.dumps(overlay))

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=str(overlay_path),
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("non_numeric" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 9: Runtime Execution Fail-Closed
# ---------------------------------------------------------------------------


def test_chain_execute_blocks_without_runtime_executor(tmp_path: Path) -> None:
    """Block execute_fleet_runtime=True when runtime_executor is None."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    resolution = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert resolution.status == "CHAIN_INPUT_READY"
    assert resolution.chain_input is not None

    # Override execute_fleet_runtime to True
    chain_input = FleetRolloutChainInput(
        decision_pack_path=resolution.chain_input.decision_pack_path,
        fleet_bots=resolution.chain_input.fleet_bots,
        allowed_target_bots=resolution.chain_input.allowed_target_bots,
        target_runtime_specs=resolution.chain_input.target_runtime_specs,
        source_overlay_path=resolution.chain_input.source_overlay_path,
        source_overlay_sha256=resolution.chain_input.source_overlay_sha256,
        expected_parameter=resolution.chain_input.expected_parameter,
        expected_value=resolution.chain_input.expected_value,
        execute_fleet_runtime=True,
    )

    result = run_fleet_rollout_chain(
        chain_input,
        chain_output_dir=tmp_path,
        runtime_executor=None,
    )
    assert result.status == "FLEET_CHAIN_BLOCKED"
    assert any("runtime_executor_required" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 10: Fleet Bot Registry Edge Cases
# ---------------------------------------------------------------------------


def test_resolver_blocks_missing_registry(tmp_path: Path) -> None:
    """Missing bot registry -> CHAIN_INPUT_BLOCKED."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=str(tmp_path / "nonexistent.json"),
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("not_readable" in r for r in result.blocked_reasons)


def test_resolver_blocks_no_enabled_bots(tmp_path: Path) -> None:
    """No enabled bots in registry -> CHAIN_INPUT_BLOCKED."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    # All bots disabled
    registry_path = _make_bot_registry(tmp_path, enabled_bots=())

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("no_enabled_bots" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 11: Allowed Targets
# ---------------------------------------------------------------------------


def test_resolver_default_allowed_targets(tmp_path: Path) -> None:
    """Default allowed targets exclude canary and control."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    assert CANARY_BOT not in result.chain_input.allowed_target_bots
    assert CONTROL_BOT not in result.chain_input.allowed_target_bots
    assert REGIME_HYBRID_BOT in result.chain_input.allowed_target_bots
    assert FREQAI_REBEL_BOT in result.chain_input.allowed_target_bots


def test_resolver_explicit_allowed_targets(tmp_path: Path) -> None:
    """Explicit allowed targets are respected."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
        explicit_allowed_targets=(REGIME_HYBRID_BOT,),
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    assert REGIME_HYBRID_BOT in result.chain_input.allowed_target_bots
    assert FREQAI_REBEL_BOT not in result.chain_input.allowed_target_bots


# ---------------------------------------------------------------------------
# Test 12: Dry Run False in Overlay
# ---------------------------------------------------------------------------


def test_resolver_blocks_dry_run_false_overlay(tmp_path: Path) -> None:
    """Overlay with dry_run=false -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path, dry_run=False)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("dry_run_disabled" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 13: Pair Cluster Action is Not a Rollout Parameter
# ---------------------------------------------------------------------------


def test_resolver_blocks_pair_cluster_action_only(tmp_path: Path) -> None:
    """pair_cluster_action alone is not a rollout parameter -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(
        max_open_trades_candidate=None,
        pair_cluster_action="reduce_exposure",
    )

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("no_rollout_candidates" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 14: Unknown Candidate Key
# ---------------------------------------------------------------------------


def test_resolver_blocks_unknown_candidate_key(tmp_path: Path) -> None:
    """Unknown candidate key -> blocked."""
    pack_path = _make_decision_pack(tmp_path)
    registry_path = _make_bot_registry(tmp_path)
    candidate = _make_candidate_overlay(max_open_trades_candidate=2)
    candidate["unknown_key_candidate"] = 99  # type: ignore[assignment]

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        candidate_overlay=candidate,
    )
    assert result.status == "CHAIN_INPUT_BLOCKED"
    assert any("unknown_candidate_key" in r for r in result.blocked_reasons)


# ---------------------------------------------------------------------------
# Test 15: Resolver Result Serialization
# ---------------------------------------------------------------------------


def test_resolver_result_serializable(tmp_path: Path) -> None:
    """FleetRolloutInputResolutionResult fields are JSON-serializable."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_READY"

    # All string fields should be serializable
    serializable = {
        "status": result.status,
        "decision_pack_path": result.decision_pack_path,
        "source_overlay_path": result.source_overlay_path,
        "source_overlay_sha256": result.source_overlay_sha256,
        "next_step": result.next_step,
        "blocked_reasons": list(result.blocked_reasons),
    }
    serialized = json.dumps(serializable)
    assert isinstance(serialized, str)
    deserialized = json.loads(serialized)
    assert deserialized["status"] == "CHAIN_INPUT_READY"


# ---------------------------------------------------------------------------
# Test 16: No Live Trading Fields
# ---------------------------------------------------------------------------


def test_resolver_no_live_trading_fields(tmp_path: Path) -> None:
    """Resolver output must not contain live trading fields."""
    pack_path = _make_decision_pack(tmp_path)
    overlay_path, _ = _make_overlay(tmp_path)
    registry_path = _make_bot_registry(tmp_path)

    result = resolve_fleet_rollout_chain_input(
        decision_pack_path=pack_path,
        bot_registry_path=registry_path,
        explicit_overlay_path=overlay_path,
    )
    assert result.status == "CHAIN_INPUT_READY"
    assert result.chain_input is not None
    assert result.chain_input.execute_fleet_runtime is False
    # No live trading fields in chain input
    d = {
        "decision_pack_path": result.chain_input.decision_pack_path,
        "execute_fleet_runtime": result.chain_input.execute_fleet_runtime,
    }
    assert "api_key" not in str(d.keys())
    assert "secret" not in str(d.keys())
    assert "LIVE" not in result.status
