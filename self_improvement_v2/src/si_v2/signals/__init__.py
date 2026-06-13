"""SI v2 Signal Fusion package.

Provides typed models for collecting, summarizing, and fusing read-only
Freqtrade REST API signals into deterministic proposals.
"""

from si_v2.signals.freqtrade_signals import collect_bot_signals
from si_v2.signals.fusion import build_proposal_evidence, fuse_signals
from si_v2.signals.models import (
    BotSignalSnapshot,
    FleetSignalSnapshot,
    ProposalEvidenceSummary,
    SignalAvailability,
    SignalQuality,
)

__all__ = [
    "BotSignalSnapshot",
    "FleetSignalSnapshot",
    "ProposalEvidenceSummary",
    "SignalAvailability",
    "SignalQuality",
    "build_proposal_evidence",
    "collect_bot_signals",
    "fuse_signals",
]
