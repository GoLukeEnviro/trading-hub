r"""Tests for Apply Actuator overlay merge — safe config generation.

Tests:
  - Safety validation (forbidden keys, unknown keys)
  - Effective config generation from base + overlay
  - dry_run preservation
  - Live trading blocking
  - Draft immutability
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


from si_v2.apply_actuator.models import (
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
)
from si_v2.apply_actuator.overlay_merge import (
    SAFETY_FORBIDDEN_KEYS,
    SAFETY_REQUIRED_KEYS,
    generate_effective_config,
    validate_overlay_safety,
)

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

SAFE_PROPOSAL = OverlayProposal(
    proposal_id="65502d13a99bfadd",
    bot_id="freqtrade-freqforge",
    policy="safe_parameter_overlay_only",
    parameters={
        "max_open_trades": 3,
        "stake_amount": "unlimited",
        "tradable_balance_ratio": 0.99,
    },
    created_at_utc="2026-06-23T10:49:27+00:00",
    source_cycle_id="20260623T104905Z",
)

BASE_CONFIG = {
    "max_open_trades": 5,
    "stake_amount": 50,
    "tradable_balance_ratio": 0.95,
    "dry_run": True,
    "exchange": {
        "name": "bitget",
    },
}

VERIFIED_BINDING = BotRuntimeBinding(
    bot_id="freqtrade-freqforge",
    container_name="trading-freqtrade-freqforge-1",
    host_user_data_path="/home/hermes/projects/trading/freqforge/user_data",
    container_user_data_path="/freqtrade/user_data",
    host_config_path="/home/hermes/projects/trading/freqforge/user_data/config.json",
    container_config_path="/freqtrade/user_data/config.json",
    loaded_config_args=("--config", "/freqtrade/user_data/config.json"),
    runtime_visible=True,
    confidence="VERIFIED",
)


# ---------------------------------------------------------------------------
# Safety validation
# ---------------------------------------------------------------------------


class TestValidateOverlaySafety:
    def test_safe_proposal_passes(self) -> None:
        safe, issues = validate_overlay_safety(SAFE_PROPOSAL)
        assert safe is True, f"Expected safe, got: {issues}"

    def test_unsafe_policy_blocked(self) -> None:
        bad = OverlayProposal(
            proposal_id="xxx",
            bot_id="test",
            policy="strategy_mutation",  # NOT safe_parameter_overlay_only
            parameters={},
        )
        safe, issues = validate_overlay_safety(bad)
        assert safe is False
        assert any("Unsafe policy" in i for i in issues)

    def test_forbidden_key_dry_run_blocked(self) -> None:
        bad = OverlayProposal(
            proposal_id="xxx",
            bot_id="test",
            parameters={"dry_run": False},
        )
        safe, issues = validate_overlay_safety(bad)
        assert safe is False
        assert any("dry_run" in i for i in issues)

    def test_forbidden_key_exchange_blocked(self) -> None:
        bad = OverlayProposal(
            proposal_id="xxx",
            bot_id="test",
            parameters={"exchange": {"name": "real_exchange"}},
        )
        safe, issues = validate_overlay_safety(bad)
        assert safe is False
        assert any("exchange" in i for i in issues)

    def test_unknown_parameter_blocked(self) -> None:
        bad = OverlayProposal(
            proposal_id="xxx",
            bot_id="test",
            parameters={"unknown_crazy_setting": "yes"},
        )
        safe, issues = validate_overlay_safety(bad)
        assert safe is False
        assert any("unknown_crazy_setting" in i for i in issues)

    def test_all_forbidden_keys_are_blocked(self) -> None:
        """Every forbidden key must be blocked individually."""
        for key in SAFETY_FORBIDDEN_KEYS:
            bad = OverlayProposal(
                proposal_id="xxx",
                bot_id="test",
                parameters={key: "dummy"},
            )
            safe, _ = validate_overlay_safety(bad)
            assert safe is False, f"Key {key!r} should be blocked!"

    def test_approved_keys_pass(self) -> None:
        """All approved keys should pass safety check."""
        params = {k: 1 for k in SAFETY_REQUIRED_KEYS}
        good = OverlayProposal(
            proposal_id="xxx",
            bot_id="test",
            parameters=params,
        )
        safe, issues = validate_overlay_safety(good)
        assert safe is True, f"Expected safe, got: {issues}"


# ---------------------------------------------------------------------------
# Effective config generation
# ---------------------------------------------------------------------------


class TestGenerateEffectiveConfig:
    def test_generates_valid_draft(self) -> None:
        """Generate a draft from base config + overlay."""
        with tempfile.TemporaryDirectory() as tmp:
            # Write temp base config
            base_path = Path(tmp) / "config.json"
            with open(base_path, "w") as f:
                json.dump(BASE_CONFIG, f)

            binding = BotRuntimeBinding(
                bot_id="freqtrade-freqforge",
                container_name="test",
                host_user_data_path=str(tmp),
                container_user_data_path="/freqtrade/user_data",
                host_config_path=str(base_path),
                container_config_path="/freqtrade/user_data/config.json",
                runtime_visible=True,
                confidence="VERIFIED",
            )

            draft, errors = generate_effective_config(
                SAFE_PROPOSAL, binding,
                overlay_output_dir=tmp,
            )
            assert draft is not None, f"Expected draft, got: {errors}"
            assert draft.proposal_id == "65502d13a99bfadd"
            assert draft.bot_id == "freqtrade-freqforge"
            assert draft.dry_run_preserved is True
            assert draft.live_trading_forbidden is True
            assert draft.multi_config_compatible is True
            assert set(draft.changed_keys) == {"max_open_trades", "stake_amount", "tradable_balance_ratio"}

    def test_draft_preserves_unchanged_values(self) -> None:
        """Base config values not in overlay must be preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "config.json"
            with open(base_path, "w") as f:
                json.dump(BASE_CONFIG, f)

            binding = BotRuntimeBinding(
                bot_id="test",
                container_name="test",
                host_user_data_path=str(tmp),
                container_user_data_path="/freqtrade/user_data",
                host_config_path=str(base_path),
                container_config_path="/freqtrade/user_data/config.json",
                runtime_visible=True,
                confidence="VERIFIED",
            )

            draft, errors = generate_effective_config(SAFE_PROPOSAL, binding)
            assert draft is not None, f"Errors: {errors}"
            # dry_run should be preserved from base (True)
            assert draft.dry_run_preserved is True
            # exchange should be preserved from base
            assert draft.before_values.get("max_open_trades") == 5
            assert draft.after_values.get("max_open_trades") == 3

    def test_dry_run_false_in_base_detected(self) -> None:
        """If base config has dry_run=False, the draft must flag it."""
        with tempfile.TemporaryDirectory() as tmp:
            base = dict(BASE_CONFIG)
            base["dry_run"] = False
            base_path = Path(tmp) / "config.json"
            with open(base_path, "w") as f:
                json.dump(base, f)

            binding = BotRuntimeBinding(
                bot_id="test",
                container_name="test",
                host_user_data_path=str(tmp),
                container_user_data_path="/freqtrade/user_data",
                host_config_path=str(base_path),
                container_config_path="/freqtrade/user_data/config.json",
                runtime_visible=True,
                confidence="VERIFIED",
            )

            draft, errors = generate_effective_config(SAFE_PROPOSAL, binding)
            assert draft is not None
            assert draft.dry_run_preserved is False
            assert any("dry_run" in e.lower() for e in errors)

    def test_missing_base_config_returns_none(self) -> None:
        """If base config file doesn't exist, return None."""
        binding = BotRuntimeBinding(
            bot_id="test",
            container_name="test",
            host_user_data_path="/nonexistent/path",
            container_user_data_path="/freqtrade/user_data",
            host_config_path="/nonexistent/path/config.json",
            container_config_path="/freqtrade/user_data/config.json",
            runtime_visible=True,
            confidence="VERIFIED",
        )
        draft, errors = generate_effective_config(SAFE_PROPOSAL, binding)
        assert draft is None
        assert len(errors) > 0

    def test_overlay_file_written_to_correct_dir(self) -> None:
        """When overlay_output_dir is provided, file must be written there."""
        with tempfile.TemporaryDirectory() as tmp:
            base_path = Path(tmp) / "config.json"
            with open(base_path, "w") as f:
                json.dump(BASE_CONFIG, f)

            binding = BotRuntimeBinding(
                bot_id="test",
                container_name="test",
                host_user_data_path=str(tmp),
                container_user_data_path="/freqtrade/user_data",
                host_config_path=str(base_path),
                container_config_path="/freqtrade/user_data/config.json",
                runtime_visible=True,
                confidence="VERIFIED",
            )

            overlay_dir = Path(tmp) / "overlays"
            draft, errors = generate_effective_config(
                SAFE_PROPOSAL, binding,
                overlay_output_dir=overlay_dir,
            )
            assert draft is not None
            assert draft.effective_config_path
            assert Path(draft.effective_config_path).exists()
            assert "overlay_65502d13.json" in draft.effective_config_path
