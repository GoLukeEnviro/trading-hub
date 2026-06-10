"""Rainbow signal validation for trading-hub.

This package implements the Rainbow Signal Envelope Validator defined
in Issue #79.  It validates signal envelopes against the canonical
contract from ai4trade-bot #51 and consumes sanitized fixtures from
ai4trade-bot #56.

No network, Docker, Freqtrade, Telegram, or runtime calls are made.
The validator has no side effects and no stateful dependencies on
external systems.
"""

from si_v2.rainbow.drift_guard import (
    DriftReport,
    DriftVerdict,
    RainbowContractDriftGuard,
)
from si_v2.rainbow.validator import (
    RainbowSignalEnvelopeValidator,
    ValidationResult,
    ValidationVerdict,
    normalize_direction,
)

__all__ = [
    "DriftReport",
    "DriftVerdict",
    "RainbowContractDriftGuard",
    "RainbowSignalEnvelopeValidator",
    "ValidationResult",
    "ValidationVerdict",
    "normalize_direction",
]
