"""Strategy mutator for building safe mutation candidates.

Generates mutation proposals based on analysis results, always using
safe parameter overlays and proposal_only mode.
"""

from __future__ import annotations

import hashlib
import json

from si_v2.propose.safe_parameters import guard_candidate, validate_safe_parameter
from si_v2.state.schemas import AnalysisResult, MutationCandidate


class StrategyMutator:
    """Builds mutation candidates from analysis results."""

    def build_candidate(
        self,
        bot_id: str,
        analysis: AnalysisResult,
        history: list[dict[str, float | int]],
    ) -> MutationCandidate | None:
        """Build a mutation candidate if warranted by the analysis.

        Args:
            bot_id: Bot identifier.
            analysis: Current analysis result.
            history: List of previous parameter sets for similarity checking.

        Returns:
            MutationCandidate if mutation is warranted, None otherwise.
        """
        if analysis.decision == "hold":
            return None

        # Compute proposed parameters from analysis
        params = self._compute_proposed_params(analysis)
        if not params:
            return None

        if not guard_candidate(params):
            return None

        for name, value in params.items():
            if not validate_safe_parameter(name, value):
                return None

        sha = self._compute_sha256(params)
        active_overlay: dict[str, float | int] = {
            k: v
            for k, v in params.items()
            if k in ("max_open_trades", "stake_factor", "stoploss_pct", "take_profit_pct")
        }
        metadata_only: dict[str, int] = {
            k: int(v) for k, v in params.items() if k in ("rsi_period", "cooldown_candles")
        }

        requires_adapter = list(metadata_only.keys())

        return MutationCandidate(
            bot_id=bot_id,
            bot_name=analysis.bot_name,
            candidate_sha256=sha,
            source_decision=analysis.decision,
            parameters=params,
            active_overlay_candidates=active_overlay,
            metadata_only_candidates=metadata_only,
            requires_strategy_adapter=requires_adapter,
            review_notes=[f"auto_proposed from decision={analysis.decision}"],
        )

    def _compute_proposed_params(self, analysis: AnalysisResult) -> dict[str, float | int]:
        """Compute proposed parameter adjustments from analysis.

        Args:
            analysis: Current analysis result.

        Returns:
            Dictionary of proposed parameter values.
        """
        # Default conservative parameters
        params: dict[str, float | int] = {
            "rsi_period": 14,
            "stoploss_pct": -0.02,
            "take_profit_pct": 0.035,
            "stake_factor": 1.0,
            "max_open_trades": 2,
            "cooldown_candles": 9,
        }

        # Check if we have negative metrics to respond to
        for _window_name, stats in analysis.windows.items():
            if stats.pnl_abs < 0 and stats.trades > 0:
                # Tighten stop-loss and reduce exposure
                params["stoploss_pct"] = -0.015
                params["stake_factor"] = 0.8
                params["cooldown_candles"] = 12
                break

        return params

    def _compute_sha256(self, params: dict[str, float | int]) -> str:
        """Compute a short SHA256 hash of the parameters.

        Args:
            params: Parameter dictionary to hash.

        Returns:
            First 16 hex characters of the SHA256 digest.
        """
        serialized = json.dumps(params, sort_keys=True)
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        return digest[:16]
