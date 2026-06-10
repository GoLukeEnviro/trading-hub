"""Test state roundtrip: load v1 JSON files and parse into v2 schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from si_v2.state.schemas import (
    AnalysisResult,
    ApprovalGate,
    LoopStatus,
    MutationCandidate,
    MutationOverlay,
)

V1_STATE_DIR = Path("/home/hermes/projects/trading/var/trading-self-improvement/bot_a")


def _load_json(filename: str) -> dict[str, object]:
    """Load a JSON file from the v1 state directory.

    Args:
        filename: Name of the JSON file.

    Returns:
        Parsed JSON dictionary.
    """
    filepath = V1_STATE_DIR / filename
    with open(filepath) as f:
        data: dict[str, object] = json.load(f)
    return data


@pytest.mark.skipif(not V1_STATE_DIR.exists(), reason="v1 state directory not found")
class TestV1Roundtrip:
    """Tests for loading v1 state files into v2 schemas."""

    def test_approval_gate_roundtrip(self) -> None:
        """Parse v1 approval_gate.json into ApprovalGate schema."""
        data = _load_json("approval_gate.json")
        gate = ApprovalGate.model_validate(data)
        assert gate.approved is True
        assert gate.candidate_sha256 == "9acaf521d47eb514"
        # Verify roundtrip
        dumped = gate.model_dump()
        assert dumped["approved"] is True

    def test_loop_status_roundtrip(self) -> None:
        """Parse v1 loop_status.json into LoopStatus schema."""
        data = _load_json("loop_status.json")
        status = LoopStatus.model_validate(data)
        assert status.alias == "bot_a"
        assert status.health_score_0_100 == 40
        assert status.status == "flagged"
        assert "no_trades" in status.stale_flags
        assert status.last_decision == "hold"
        # Verify roundtrip
        dumped = status.model_dump()
        assert dumped["alias"] == "bot_a"

    def test_latest_analysis_roundtrip(self) -> None:
        """Parse v1 latest_analysis.json into AnalysisResult schema."""
        data = _load_json("latest_analysis.json")
        result = AnalysisResult.model_validate(data)
        assert result.bot_id == "bot_a"
        assert result.decision == "hold"
        assert "12h" in result.windows
        assert result.windows["12h"].trades == 0
        assert result.mode == "proposal_only"
        # Verify roundtrip
        dumped = result.model_dump()
        assert dumped["bot_id"] == "bot_a"

    def test_config_candidate_roundtrip(self) -> None:
        """Parse v1 config.candidate.json into MutationCandidate schema."""
        data = _load_json("config.candidate.json")
        candidate = MutationCandidate.model_validate(data)
        assert candidate.bot_id == "bot_a"
        assert candidate.candidate_sha256 == "0f7be7f8cf14f546"
        assert candidate.mutation_policy == "safe_parameter_overlay_only"
        assert candidate.parameters["rsi_period"] == 14
        # Verify roundtrip
        dumped = candidate.model_dump()
        assert dumped["bot_id"] == "bot_a"

    def test_mutation_overlay_roundtrip(self) -> None:
        """Parse v1 mutation_overlay.json into MutationOverlay schema."""
        data = _load_json("mutation_overlay.json")
        overlay = MutationOverlay.model_validate(data)
        assert overlay.max_open_trades == 2
        assert overlay.stoploss == -0.02
        assert overlay.minimal_roi["0"] == 0.035
        # Verify roundtrip
        dumped = overlay.model_dump()
        assert dumped["max_open_trades"] == 2
