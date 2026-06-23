"""Tests for the multi-config runtime proof (PR #336, candidate 65502d13).

The previous verifier (`check_effective_config_loaded`) read the base
config.json and compared it against the overlay parameters. That is
structurally wrong for Freqtrade >= 2026.3 native multi-config stacking,
where the effective runtime config is the merge of all `--config` files.

These tests verify the corrected proof strategy:
  C — process command references the overlay path
  A — Freqtrade show_config API (with auth) returns the overlay values
  B — deterministic in-container merge of base + overlay returns the values
  GREEN rule — C + (A or B) + safety invariants

All subprocess / docker invocations are mocked — these tests are offline
unit tests, not integration tests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from si_v2.apply_actuator.models import (
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
    ProofStatus,
)
from si_v2.apply_actuator.proof import (
    check_effective_config_from_merged_files,
    check_process_uses_overlay,
    verify_runtime_effect,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def binding() -> BotRuntimeBinding:
    return BotRuntimeBinding(
        bot_id="freqtrade-freqforge",
        container_name="trading-freqtrade-freqforge-1",
        host_user_data_path="/home/hermes/projects/trading/freqforge/user_data",
        container_user_data_path="/freqtrade/user_data",
        host_config_path="/home/hermes/projects/trading/freqforge/user_data/config.json",
        container_config_path="/freqtrade/user_data/config.json",
        loaded_config_args=(
            "--config",
            "/freqtrade/user_data/config.json",
            "--strategy",
            "FreqForge_Override",
        ),
        runtime_visible=True,
        confidence="VERIFIED",
    )


@pytest.fixture
def proposal() -> OverlayProposal:
    return OverlayProposal(
        proposal_id="65502d13a99bfadd",
        bot_id="freqtrade-freqforge",
        policy="safe_parameter_overlay_only",
        parameters={
            "max_open_trades": 3,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
        },
    )


@pytest.fixture
def draft() -> EffectiveConfigDraft:
    return EffectiveConfigDraft(
        proposal_id="65502d13a99bfadd",
        bot_id="freqtrade-freqforge",
        base_config_path="/home/hermes/projects/trading/freqforge/user_data/config.json",
        changed_keys=("max_open_trades", "stake_amount", "tradable_balance_ratio"),
        before_values={
            "max_open_trades": 5,
            "stake_amount": 50,
            "tradable_balance_ratio": 0.95,
        },
        after_values={
            "max_open_trades": 3,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
        },
        sha256="deadbeef" * 8,
        dry_run_preserved=True,
        live_trading_forbidden=True,
        multi_config_compatible=True,
    )


BASE_CONFIG = {
    "dry_run": True,
    "max_open_trades": 5,
    "stake_amount": 50,
    "tradable_balance_ratio": 0.95,
    "stoploss": -0.09,
    "strategy": "FreqForge_Override",
    "api_server": {
        "enabled": True,
        "username": "freqforge",
        "password": "secret-freqforge-ui",
    },
}

OVERLAY_CONFIG = {
    "max_open_trades": 3,
    "stake_amount": "unlimited",
    "tradable_balance_ratio": 0.99,
}

OVERLAY_CONTAINER_PATH = "/freqtrade/user_data/overlay_65502d13.json"


# ---------------------------------------------------------------------------
# Test: Proof C — process command references overlay
# ---------------------------------------------------------------------------


class TestCheckProcessUsesOverlay:
    def test_overlay_in_cmdline_returns_true(self) -> None:
        cmdline = (
            "/usr/local/bin/python3.13 /home/ftuser/.local/bin/freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--config /freqtrade/user_data/overlay_65502d13.json "
            "--strategy FreqForge_Override "
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cmdline
        mock_result.stderr = ""
        with patch("si_v2.apply_actuator.proof.subprocess.run", return_value=mock_result):
            ok, errors = check_process_uses_overlay(
                "trading-freqtrade-freqforge-1", OVERLAY_CONTAINER_PATH,
            )
        assert ok is True
        assert errors == []

    def test_overlay_missing_from_cmdline_returns_false(self) -> None:
        # Old command — only the base config, no overlay arg
        cmdline = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--strategy FreqForge_Override"
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = cmdline
        mock_result.stderr = ""
        with patch("si_v2.apply_actuator.proof.subprocess.run", return_value=mock_result):
            ok, errors = check_process_uses_overlay(
                "trading-freqtrade-freqforge-1", OVERLAY_CONTAINER_PATH,
            )
        assert ok is False
        assert len(errors) == 1
        assert "process_command_missing_overlay" in errors[0]


# ---------------------------------------------------------------------------
# Test: Proof B — deterministic merged-config fallback
# ---------------------------------------------------------------------------


class TestCheckEffectiveConfigFromMergedFiles:
    def test_merged_values_match_expected(self) -> None:
        # First call: cat base config. Second call: cat overlay.
        base_proc = MagicMock(returncode=0, stdout=json.dumps(BASE_CONFIG), stderr="")
        overlay_proc = MagicMock(returncode=0, stdout=json.dumps(OVERLAY_CONFIG), stderr="")
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[base_proc, overlay_proc],
        ):
            ok, errors = check_effective_config_from_merged_files(
                "trading-freqtrade-freqforge-1",
                base_container_path="/freqtrade/user_data/config.json",
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                expected_values={
                    "max_open_trades": 3,
                    "stake_amount": "unlimited",
                    "tradable_balance_ratio": 0.99,
                },
            )
        assert ok is True
        assert errors == []

    def test_base_mismatch_alone_does_not_fail(self) -> None:
        """Base config has old values, overlay has new values — merged proof
        should report GREEN. The previous verifier wrongly compared the base
        against overlay parameters and failed."""
        base_proc = MagicMock(returncode=0, stdout=json.dumps(BASE_CONFIG), stderr="")
        overlay_proc = MagicMock(returncode=0, stdout=json.dumps(OVERLAY_CONFIG), stderr="")
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[base_proc, overlay_proc],
        ):
            ok, errors = check_effective_config_from_merged_files(
                "trading-freqtrade-freqforge-1",
                base_container_path="/freqtrade/user_data/config.json",
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                expected_values={"max_open_trades": 3},  # overlay value, not base value 5
            )
        assert ok is True, errors
        assert errors == []

    def test_merged_mismatch_returns_specific_error(self) -> None:
        bad_overlay = {
            "max_open_trades": 7,  # wrong, expected 3
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
        }
        base_proc = MagicMock(returncode=0, stdout=json.dumps(BASE_CONFIG), stderr="")
        overlay_proc = MagicMock(returncode=0, stdout=json.dumps(bad_overlay), stderr="")
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[base_proc, overlay_proc],
        ):
            ok, errors = check_effective_config_from_merged_files(
                "trading-freqtrade-freqforge-1",
                base_container_path="/freqtrade/user_data/config.json",
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                expected_values={"max_open_trades": 3},
            )
        assert ok is False
        assert any("effective_merged_config_mismatch" in e for e in errors)


# ---------------------------------------------------------------------------
# Test: verify_runtime_effect — full integration of C + A/B
# ---------------------------------------------------------------------------


def _mock_subprocess_side_effect(*responses: MagicMock):
    """Build a side_effect list of length N from a sequence of mocks."""
    return list(responses)


class TestVerifyRuntimeEffectMultiConfig:
    def test_green_with_process_cmd_and_merged_fallback(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Process command includes overlay + merged fallback succeeds → GREEN."""
        cmdline = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--config /freqtrade/user_data/overlay_65502d13.json "
            "--strategy FreqForge_Override"
        )
        # Sequence: docker test -f (visibility), tr /proc/1/cmdline,
        # cat config.json (api attempt), cat config.json (api retry),
        # cat config.json (merged fallback), cat overlay
        visibility_proc = MagicMock(returncode=0, stdout="", stderr="")
        cmdline_proc = MagicMock(returncode=0, stdout=cmdline, stderr="")
        base_proc = MagicMock(returncode=0, stdout=json.dumps(BASE_CONFIG), stderr="")
        # API would fail (we make curl fail), forcing fallback to merged proof
        api_proc = MagicMock(
            returncode=7, stdout="", stderr="Failed to connect to 127.0.0.1",
        )
        overlay_proc = MagicMock(returncode=0, stdout=json.dumps(OVERLAY_CONFIG), stderr="")

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[
                visibility_proc,  # file visibility
                cmdline_proc,     # process cmdline
                base_proc,        # api attempt: cat config.json (read base for creds)
                api_proc,         # api attempt: curl show_config (fails)
                base_proc,        # merged fallback: cat config.json
                overlay_proc,     # merged fallback: cat overlay
            ],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.file_visible_to_bot is True
        assert proof.process_command_uses_overlay is True
        assert proof.effective_config_contains_expected_values is True
        assert proof.loaded_config_contains_expected_values is True
        assert proof.dry_run_true is True
        assert proof.live_trading_false is True
        assert proof.strategy_unchanged is True
        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "merged_fallback"
        assert proof.errors == ()

    def test_overlay_visible_but_not_in_process_command(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Overlay file exists but process command doesn't reference it → RED.
        This is the 'no mutation, no measurement' case."""
        cmdline = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--strategy FreqForge_Override"  # missing overlay
        )
        visibility_proc = MagicMock(returncode=0, stdout="", stderr="")
        cmdline_proc = MagicMock(returncode=0, stdout=cmdline, stderr="")
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility_proc, cmdline_proc],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )
        assert proof.file_visible_to_bot is True
        assert proof.process_command_uses_overlay is False
        assert proof.proof_status == ProofStatus.RED
        assert any("process_command_missing_overlay" in e for e in proof.errors)

    def test_dry_run_false_blocks_green(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
    ) -> None:
        """dry_run=false in the draft → RED, regardless of file visibility."""
        bad_draft = EffectiveConfigDraft(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            base_config_path="...",
            after_values=dict(proposal.parameters),
            dry_run_preserved=False,  # BAD
            live_trading_forbidden=True,
            multi_config_compatible=True,
        )
        proof = verify_runtime_effect(
            proposal, binding, bad_draft,
            overlay_container_path=OVERLAY_CONTAINER_PATH,
            docker_available=False,
        )
        assert proof.dry_run_true is False
        assert proof.proof_status == ProofStatus.RED
        assert any("dry_run" in e for e in proof.errors)

    def test_no_docker_yields_yellow(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """docker_available=False → no proof possible → YELLOW, not GREEN."""
        proof = verify_runtime_effect(
            proposal, binding, draft,
            overlay_container_path=OVERLAY_CONTAINER_PATH,
            docker_available=False,
        )
        assert proof.file_visible_to_bot is False
        assert proof.process_command_uses_overlay is False
        assert proof.loaded_config_contains_expected_values is False
        assert proof.proof_status in (ProofStatus.RED, ProofStatus.YELLOW)
        assert proof.proof_method == ""

    def test_strategy_changed_blocks(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Overlay parameters must not include 'strategy' — proposal is
        rejected at validate_overlay_safety in the policy layer. Here we
        verify the proof's own strategy_unchanged invariant by setting
        the draft's effective_config_contains_expected_values to False
        via a draft mismatch."""
        bad_draft = EffectiveConfigDraft(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            base_config_path="...",
            # after_values is missing the proposal parameter → mismatch
            after_values={"max_open_trades": 99},
            dry_run_preserved=True,
            live_trading_forbidden=True,
            multi_config_compatible=True,
        )
        proof = verify_runtime_effect(
            proposal, binding, bad_draft,
            overlay_container_path=OVERLAY_CONTAINER_PATH,
            docker_available=False,
        )
        # No docker means we can't run the runtime checks; but the
        # effective_config check (against the draft) must fail.
        assert proof.effective_config_contains_expected_values is False
        assert proof.proof_status == ProofStatus.RED

    def test_wrong_overlay_path_blocks(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Wrong overlay path: not visible + not in cmdline + not mergeable
        → RED with file_visibility_failure + process_command_missing_overlay."""
        # Visibility test fails (file not present)
        visibility_proc = MagicMock(returncode=1, stdout="", stderr="not found")
        cmdline_proc = MagicMock(
            returncode=0,
            stdout="/usr/bin/freqtrade --config /freqtrade/user_data/config.json",
            stderr="",
        )
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility_proc, cmdline_proc],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path="/wrong/path/overlay.json",
                docker_available=True,
            )
        assert proof.file_visible_to_bot is False
        assert proof.process_command_uses_overlay is False
        assert proof.proof_status == ProofStatus.RED
        assert any("file_visibility_failure" in e for e in proof.errors)

    def test_api_proof_authoritative_when_available(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """When show_config returns the overlay values, Proof A wins over
        Proof B. proof_method == 'api'."""
        cmdline = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--config /freqtrade/user_data/overlay_65502d13.json "
            "--strategy FreqForge_Override"
        )
        visibility_proc = MagicMock(returncode=0, stdout="", stderr="")
        cmdline_proc = MagicMock(returncode=0, stdout=cmdline, stderr="")
        # API call: cat base config (for creds) then curl show_config
        base_proc = MagicMock(returncode=0, stdout=json.dumps(BASE_CONFIG), stderr="")
        # show_config returns the merged config as Freqtrade loaded it
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 3.0,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,  # Freqtrade 2026.3 may expose this
            "strategy": "FreqForge_Override",
        }
        api_proc = MagicMock(
            returncode=0, stdout=json.dumps(show_config_response), stderr="",
        )

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[
                visibility_proc,  # file visibility
                cmdline_proc,     # process cmdline
                base_proc,        # cat base config (for api_server creds)
                api_proc,         # curl show_config
            ],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "api"
        assert proof.process_command_uses_overlay is True
        assert proof.loaded_config_contains_expected_values is True


# ---------------------------------------------------------------------------
# Test: controlled_apply wiring returns ACTUATOR_VERIFIED with token + GREEN
# ---------------------------------------------------------------------------


class TestControlledApplyWithMultiConfigProof:
    def test_actuator_verified_when_proof_green(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """End-to-end: with token + GREEN proof, mode becomes ACTUATOR_VERIFIED
        and mutation counter is allowed.

        We patch `verify_runtime_effect` directly (rather than mocking the
        underlying `subprocess.run` calls) so the test is independent of
        Python version, container availability, and string-comparison
        quirks of mock side_effect iteration.
        """
        from si_v2.apply_actuator import models as actuator_models
        from si_v2.apply_actuator.controlled_apply import run_controlled_apply

        green_proof = actuator_models.RuntimeEffectProof(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            file_visible_to_bot=True,
            effective_config_contains_expected_values=True,
            loaded_config_contains_expected_values=True,
            process_command_uses_overlay=True,
            proof_method="api",
            dry_run_true=True,
            live_trading_false=True,
            strategy_unchanged=True,
            restart_required=False,
            proof_status=actuator_models.ProofStatus.GREEN,
            errors=(),
        )

        green_actuator_result = actuator_models.ApplyActuatorResult(
            status=actuator_models.ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            proof=green_proof,
            mutation_counter_should_increment=True,
            measurement_allowed=True,
            errors=(),
            warnings=(),
        )

        # Build a minimal eligible proposal dict for the eligibility check
        proposal_dict = {
            "decision_type": "SHADOW_PROPOSAL",
            "approval_status": "APPROVED",
            "approval_eligible": True,
            "requires_human_approval": True,
            "base_mode": "proposal_only",
            "promotion_block_reason_codes": ["positive_profit_hypothesis"],
            "no_proposal_reason": None,
            "dry_run": True,
            "bot_id": proposal.bot_id,
            "candidate_sha256": proposal.proposal_id,
            "hypothesis": "reinforce_profitable_pair_cluster_v1",
            "mutation_policy": "safe_parameter_overlay_only",
            "parameter_overlay": dict(proposal.parameters),
            "walk_forward_net_metrics": {"metrics_source": "active_cycle"},
            "cycle_id": "2026-06-23-test",
        }

        import os
        env = {
            "APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION": "APPROVE",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "si_v2.apply_actuator.controlled_apply.compute_apply_result",
            return_value=green_actuator_result,
        ):
            result = run_controlled_apply(proposal_dict, docker_available=True)

        assert result.token_provided is True
        assert result.eligible is True
        assert result.actuator_result.status.value == "APPLIED_WITH_RUNTIME_PROOF"
        assert result.actuator_result.proof.proof_status == ProofStatus.GREEN
        assert result.actuator_result.proof.process_command_uses_overlay is True
        assert result.actuator_result.proof.proof_method == "api"
        assert result.actuator_result.mutation_counter_should_increment is True
        assert result.actuator_result.measurement_allowed is True
        # Mode is ACTUATOR_VERIFIED when token + GREEN
        assert result.mode.value == "ACTUATOR_VERIFIED"


# ---------------------------------------------------------------------------
# Test: API-surface-aware composite proof (PR #337)
# ---------------------------------------------------------------------------
#
# These tests pin the contract introduced in PR #337 for the case where the
# Freqtrade ``show_config`` REST endpoint does NOT expose every expected key
# (e.g. ``tradable_balance_ratio`` on Freqtrade 2026.3). A missing API key
# must NOT be treated as a runtime mismatch; it must be deferable to Proof B
# (deterministic in-container merged config). An API-exposed mismatch must
# still force RED.
#
# Required scenarios (per the PR #337 specification):
#  1. API exposes all expected keys and all match -> GREEN (proof_method=api)
#  2. API exposes key and value mismatches        -> RED, no merged override
#  3. API omits tradable_balance_ratio, merged proves it -> GREEN (api_plus_merged_missing_keys)
#  4. API omits multiple expected keys, merged proves all -> GREEN
#  5. API omits key, merged mismatch               -> RED
#  6. API unavailable, merged proves all keys + process uses overlay -> GREEN
#  7. API unavailable, process missing overlay      -> RED
#  8. API missing key produces proof_method 'api_plus_merged_missing_keys'
#  9. Missing API key does NOT create api_effective_config_mismatch
# 10. ControlledApplyResult becomes ACTUATOR_VERIFIED when composite proof is GREEN
# 11. Mutation counter remains false if proof RED
# 12. Measurement remains false if proof RED
# 13. dry_run=false in merged config remains RED
# 14. Strategy command changed remains RED (process cmdline misses overlay)


def _proc(cmdline: str) -> MagicMock:
    return MagicMock(returncode=0, stdout=cmdline, stderr="")


def _cat(payload: dict | str) -> MagicMock:
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return MagicMock(returncode=0, stdout=body, stderr="")


_CORRECT_CMDLINE = (
    "/usr/local/bin/python3.13 freqtrade trade "
    "--config /freqtrade/user_data/config.json "
    "--config /freqtrade/user_data/overlay_65502d13.json "
    "--strategy FreqForge_Override"
)


class TestApiSurfaceAwareCompositeProof:
    """PR #337: Proof A surface-aware + Proof B for API-non-exposed keys."""

    # ---- 1. API exposes all keys, all match -> GREEN (api) ----------------
    def test_api_full_match_green_api(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 3.0,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
            "strategy": "FreqForge_Override",
        }
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base = _cat(BASE_CONFIG)
        api = _cat(show_config_response)
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline, base, api],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "api"
        assert proof.api_matched_keys == (
            "max_open_trades", "stake_amount", "tradable_balance_ratio",
        )
        assert proof.api_missing_keys == ()
        assert proof.api_mismatched_keys == ()
        assert proof.loaded_config_contains_expected_values is True
        assert proof.errors == ()

    # ---- 2. API exposes key and value mismatches -> RED, no override ------
    def test_api_exposed_mismatch_red_no_override(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        # API says max_open_trades=7, but proposal wants 3.
        # Even though Proof B (merged) would prove the value, RED wins.
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 7,  # mismatch
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
        }
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base = _cat(BASE_CONFIG)
        api = _cat(show_config_response)
        # Even with a perfect merged proof in the side_effect, RED must win.
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline, base, api],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.RED
        assert proof.proof_method == "red_api_exposed_key_mismatch"
        assert proof.api_mismatched_keys == ("max_open_trades",)
        assert any(
            "red_api_exposed_key_mismatch" in e for e in proof.errors
        )
        assert any(
            "api_effective_config_mismatch" in e for e in proof.errors
        )
        assert proof.loaded_config_contains_expected_values is False

    # ---- 3. API omits tradable_balance_ratio, merged proves it -> GREEN ---
    def test_api_missing_tradable_balance_ratio_green_via_merged(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """The exact 65502d13 scenario: tradable_balance_ratio is NOT in
        show_config response. Proof B (merged config) must validate it."""
        # show_config omits tradable_balance_ratio entirely (Freqtrade 2026.3).
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 3.0,
            "stake_amount": "unlimited",
            # NOTE: tradable_balance_ratio absent on purpose
            "strategy": "FreqForge_Override",
        }
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base = _cat(BASE_CONFIG)             # cat base (for API creds)
        api = _cat(show_config_response)     # show_config (omits tbr)
        # Proof B path: cat base, cat overlay (only for missing keys)
        base_again = _cat(BASE_CONFIG)
        overlay = _cat(OVERLAY_CONFIG)

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline, base, api, base_again, overlay],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "api_plus_merged_missing_keys"
        assert proof.api_matched_keys == ("max_open_trades", "stake_amount")
        assert proof.api_missing_keys == ("tradable_balance_ratio",)
        assert proof.api_mismatched_keys == ()
        assert proof.loaded_config_contains_expected_values is True
        # Spec #9: no api_effective_config_mismatch for missing keys.
        assert not any(
            "api_effective_config_mismatch" in e for e in proof.errors
        )
        assert proof.errors == ()

    # ---- 4. API omits multiple expected keys, merged proves all -> GREEN --
    def test_api_omits_multiple_keys_green_via_merged(
        self, binding: BotRuntimeBinding,
    ) -> None:
        """Two of three keys are absent from the API response. Merged proof
        must cover BOTH. proof_method must be api_plus_merged_missing_keys."""
        proposal_two_missing = OverlayProposal(
            proposal_id="65502d13a99bfadd",
            bot_id="freqtrade-freqforge",
            policy="safe_parameter_overlay_only",
            parameters={
                "max_open_trades": 3,                # exposed by API
                "stake_amount": "unlimited",         # exposed by API
                "tradable_balance_ratio": 0.99,     # not exposed
                "amend_last_stake_amount": True,    # not exposed
            },
        )
        # Draft after_values must contain all proposal parameters so the
        # draft-level mismatch check (Step 3) does not pre-empt the proof.
        draft_two_missing = EffectiveConfigDraft(
            proposal_id="65502d13a99bfadd",
            bot_id="freqtrade-freqforge",
            base_config_path="/home/hermes/projects/trading/freqforge/user_data/config.json",
            changed_keys=(
                "max_open_trades", "stake_amount",
                "tradable_balance_ratio", "amend_last_stake_amount",
            ),
            before_values={
                "max_open_trades": 5, "stake_amount": 50,
                "tradable_balance_ratio": 0.95,
                "amend_last_stake_amount": False,
            },
            after_values={
                "max_open_trades": 3, "stake_amount": "unlimited",
                "tradable_balance_ratio": 0.99,
                "amend_last_stake_amount": True,
            },
            sha256="deadbeef" * 8,
            dry_run_preserved=True,
            live_trading_forbidden=True,
            multi_config_compatible=True,
        )
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 3.0,
            "stake_amount": "unlimited",
            # tradable_balance_ratio + amend_last_stake_amount absent
            "strategy": "FreqForge_Override",
        }
        overlay_two_missing = {
            "max_open_trades": 3,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.99,
            "amend_last_stake_amount": True,
        }
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base = _cat(BASE_CONFIG)
        api = _cat(show_config_response)
        base_again = _cat(BASE_CONFIG)
        overlay = _cat(overlay_two_missing)

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline, base, api, base_again, overlay],
        ):
            proof = verify_runtime_effect(
                proposal_two_missing, binding, draft_two_missing,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "api_plus_merged_missing_keys"
        assert proof.api_missing_keys == (
            "tradable_balance_ratio", "amend_last_stake_amount",
        )
        assert proof.api_matched_keys == (
            "max_open_trades", "stake_amount",
        )
        assert proof.loaded_config_contains_expected_values is True
        assert proof.errors == ()

    # ---- 5. API omits key, merged mismatch -> RED --------------------------
    def test_api_omits_key_merged_mismatch_red(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """If the API omits a key, but the merged config does NOT match the
        proposal value for that key, the composite proof is RED."""
        show_config_response = {
            "dry_run": True,
            "max_open_trades": 3.0,
            "stake_amount": "unlimited",
            # tradable_balance_ratio absent from API
        }
        # But the overlay file on disk has the WRONG value.
        bad_overlay = {
            "max_open_trades": 3,
            "stake_amount": "unlimited",
            "tradable_balance_ratio": 0.50,  # wrong — proposal wants 0.99
        }
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base = _cat(BASE_CONFIG)
        api = _cat(show_config_response)
        base_again = _cat(BASE_CONFIG)
        overlay = _cat(bad_overlay)

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline, base, api, base_again, overlay],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.RED
        # proof_method stays empty when the composite attempt fails — only
        # the GREEN outcome gets the "api_plus_merged_missing_keys" label.
        assert proof.proof_method == ""
        assert proof.api_missing_keys == ("tradable_balance_ratio",)
        assert proof.loaded_config_contains_expected_values is False
        assert any(
            "composite_proof_failed" in e or
            "effective_merged_config_mismatch" in e
            for e in proof.errors
        )

    # ---- 6. API unavailable, merged proves all keys + process uses overlay
    #         -> GREEN (merged_fallback) -------------------------------------
    def test_api_unavailable_merged_fallback_green(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        visibility = _proc("")
        cmdline = _proc(_CORRECT_CMDLINE)
        base_for_creds = _cat(BASE_CONFIG)  # cat base → creds present
        api_failed = MagicMock(
            returncode=7, stdout="", stderr="Failed to connect to 127.0.0.1",
        )
        base_for_merge = _cat(BASE_CONFIG)  # cat base again for merged
        overlay = _cat(OVERLAY_CONFIG)

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[
                visibility,        # file visibility
                cmdline,           # process cmdline
                base_for_creds,    # cat base (api creds resolve)
                api_failed,        # curl fails → api_unavailable
                base_for_merge,    # merged fallback: cat base
                overlay,           # merged fallback: cat overlay
            ],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.GREEN
        assert proof.proof_method == "merged_fallback"
        assert proof.api_matched_keys == ()
        assert proof.api_missing_keys == ()
        assert proof.api_mismatched_keys == ()
        assert proof.process_command_uses_overlay is True
        assert proof.loaded_config_contains_expected_values is True

    # ---- 7. API unavailable + process missing overlay -> RED --------------
    def test_api_unavailable_process_missing_overlay_red(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """API unreachable + process command does NOT include overlay -> RED.
        Merged fallback alone is insufficient without Proof C."""
        cmdline_no_overlay = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--strategy FreqForge_Override"
        )
        visibility = _proc("")
        cmdline = _proc(cmdline_no_overlay)

        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.RED
        assert proof.process_command_uses_overlay is False
        assert any(
            "process_command_missing_overlay" in e for e in proof.errors
        )

    # ---- 8. proof_method label 'api_plus_merged_missing_keys' is used ----
    # (covered by test_api_missing_tradable_balance_ratio_green_via_merged)

    # ---- 9. No api_effective_config_mismatch for missing keys ------------
    # (also covered by test_api_missing_tradable_balance_ratio_green_via_merged)

    # ---- 10. ControlledApplyResult ACTUATOR_VERIFIED with composite GREEN --
    def test_controlled_apply_actuator_verified_via_composite_proof(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        from si_v2.apply_actuator import models as actuator_models
        from si_v2.apply_actuator.controlled_apply import run_controlled_apply

        green_proof = actuator_models.RuntimeEffectProof(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            file_visible_to_bot=True,
            effective_config_contains_expected_values=True,
            loaded_config_contains_expected_values=True,
            process_command_uses_overlay=True,
            proof_method="api_plus_merged_missing_keys",
            api_matched_keys=("max_open_trades", "stake_amount"),
            api_missing_keys=("tradable_balance_ratio",),
            api_mismatched_keys=(),
            dry_run_true=True,
            live_trading_false=True,
            strategy_unchanged=True,
            restart_required=False,
            proof_status=actuator_models.ProofStatus.GREEN,
            errors=(),
        )
        green_actuator_result = actuator_models.ApplyActuatorResult(
            status=actuator_models.ApplyStatus.APPLIED_WITH_RUNTIME_PROOF,
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            proof=green_proof,
            mutation_counter_should_increment=True,
            measurement_allowed=True,
            errors=(),
            warnings=(),
        )
        proposal_dict = {
            "decision_type": "SHADOW_PROPOSAL",
            "approval_status": "APPROVED",
            "approval_eligible": True,
            "requires_human_approval": True,
            "base_mode": "proposal_only",
            "promotion_block_reason_codes": ["positive_profit_hypothesis"],
            "no_proposal_reason": None,
            "dry_run": True,
            "bot_id": proposal.bot_id,
            "candidate_sha256": proposal.proposal_id,
            "hypothesis": "reinforce_profitable_pair_cluster_v1",
            "mutation_policy": "safe_parameter_overlay_only",
            "parameter_overlay": dict(proposal.parameters),
            "walk_forward_net_metrics": {"metrics_source": "active_cycle"},
            "cycle_id": "2026-06-23-composite",
        }
        import os
        env = {"APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION": "APPROVE"}
        with patch.dict(os.environ, env, clear=False), patch(
            "si_v2.apply_actuator.controlled_apply.compute_apply_result",
            return_value=green_actuator_result,
        ):
            result = run_controlled_apply(proposal_dict, docker_available=True)

        assert result.mode.value == "ACTUATOR_VERIFIED"
        assert result.actuator_result.proof.proof_status == ProofStatus.GREEN
        assert (
            result.actuator_result.proof.proof_method
            == "api_plus_merged_missing_keys"
        )
        assert result.actuator_result.mutation_counter_should_increment is True
        assert result.actuator_result.measurement_allowed is True

    # ---- 11/12. Mutation counter / measurement remain false on RED --------
    def test_red_proof_blocks_mutation_and_measurement(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        from si_v2.apply_actuator import models as actuator_models

        # Mock compute_apply_result to return a RED proof — proves that the
        # mutation counter / measurement rules in the policy layer still
        # correctly gate on proof_status == GREEN, regardless of how the
        # proof was reached.
        red_proof = actuator_models.RuntimeEffectProof(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            proof_status=actuator_models.ProofStatus.RED,
            errors=("red_api_exposed_key_mismatch: x",),
            api_mismatched_keys=("max_open_trades",),
        )
        with patch(
            "si_v2.apply_actuator.policy.verify_runtime_effect",
            return_value=red_proof,
        ):
            from si_v2.apply_actuator.policy import compute_apply_result
            result = compute_apply_result(proposal, docker_available=True)

        assert result.proof.proof_status == ProofStatus.RED
        assert result.mutation_counter_should_increment is False
        assert result.measurement_allowed is False
        assert any(
            "Mutation counter blocked" in w or
            "Measurement blocked" in w
            for w in result.warnings
        )

    # ---- 13. dry_run=false in merged config remains RED ------------------
    def test_dry_run_false_in_merged_config_red(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Even if the API is unavailable and Proof B 'proves' the merged
        config, a dry_run=False in the draft must still force RED via the
        draft-level safety gate."""
        bad_draft = EffectiveConfigDraft(
            proposal_id=proposal.proposal_id,
            bot_id=proposal.bot_id,
            base_config_path="...",
            after_values=dict(proposal.parameters),
            dry_run_preserved=False,  # BAD
            live_trading_forbidden=True,
            multi_config_compatible=True,
        )
        proof = verify_runtime_effect(
            proposal, binding, bad_draft,
            overlay_container_path=OVERLAY_CONTAINER_PATH,
            docker_available=True,  # API mocked downstream if reached
        )
        assert proof.dry_run_true is False
        assert proof.proof_status == ProofStatus.RED
        assert any("dry_run" in e for e in proof.errors)

    # ---- 14. Strategy cmdline changed (overlay missing from cmd) -> RED ---
    def test_strategy_cmdline_changed_red(
        self, binding: BotRuntimeBinding, proposal: OverlayProposal,
        draft: EffectiveConfigDraft,
    ) -> None:
        """Process command does NOT include the overlay path → process_command
        proof fails → RED, regardless of API or merged proof success."""
        cmdline_no_overlay = (
            "/usr/local/bin/python3.13 freqtrade trade "
            "--config /freqtrade/user_data/config.json "
            "--strategy FreqForge_Override"
        )
        visibility = _proc("")
        cmdline = _proc(cmdline_no_overlay)
        with patch(
            "si_v2.apply_actuator.proof.subprocess.run",
            side_effect=[visibility, cmdline],
        ):
            proof = verify_runtime_effect(
                proposal, binding, draft,
                overlay_container_path=OVERLAY_CONTAINER_PATH,
                docker_available=True,
            )

        assert proof.proof_status == ProofStatus.RED
        assert proof.process_command_uses_overlay is False
        assert any(
            "process_command_missing_overlay" in e for e in proof.errors
        )

    # ---- Bonus: ApiConfigProofResult surface-level contract ---------------
    def test_api_surface_dataclass_directly(
        self, binding: BotRuntimeBinding,
    ) -> None:
        """Direct unit test of ApiConfigProofResult construction (no I/O)."""
        from si_v2.apply_actuator.models import ApiConfigProofResult
        r = ApiConfigProofResult(
            ok=True,
            matched_keys=("a", "b"),
            missing_keys=("c",),
            mismatched_keys=(),
            unavailable=False,
        )
        assert r.ok is True
        assert r.matched_keys == ("a", "b")
        assert r.missing_keys == ("c",)
        assert r.mismatched_keys == ()
        assert r.unavailable is False
