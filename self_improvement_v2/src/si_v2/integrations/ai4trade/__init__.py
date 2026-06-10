"""Integration boundary for the ai4trade-bot upstream signal intelligence layer.

In Phase F, only in-memory Protocol definitions and DryRun adapters
exist. No code imports from the ai4trade-bot repository, no REST
clients, no submodules.

Phase H (future) will add REST API adapters consuming the
ai4trade-bot Rainbow API distribution endpoint.
"""

from __future__ import annotations

from si_v2.integrations.ai4trade.protocols import (
    AdvisorySignal,
    OutcomeProvider,
    RiskGateProvider,
    SignalOutcome,
    SignalProvider,
)

__all__ = [
    "AdvisorySignal",
    "OutcomeProvider",
    "RiskGateProvider",
    "SignalOutcome",
    "SignalProvider",
]
