"""
FreqForge v0.1 Shadow Signal Evaluator — Deterministic Rule Engine

Three separate rule groups per Luke's A2 adjustment:
  ENTRY_RULES   — evaluated when a new trade opens
  OPEN_RISK_RULES — evaluated for currently open positions
  EXIT_RULES    — evaluated when a trade closes (post-hoc review)
"""

from typing import Dict, List, Optional, Tuple
from freqforge_config import (
    normalize_pair, CONFIDENCE_THRESHOLD, PNL_HARD_STOP,
    MAX_FLEET_OPEN, MIN_CANDLES_BREATHING,
    DECISION_APPROVE, DECISION_VETO, DECISION_UNCERTAIN,
    DECISION_REDUCE_SIZE, DECISION_FALSE_NEGATIVE,
    DECISION_VETO_HELPED, DECISION_MISSED_RISK,
)


# ── Data Structures ──────────────────────────────────────────

class SignalData:
    """Parsed ai-hedge-fund-crypto signal for one pair."""
    def __init__(self, pair: str, bias: str, confidence: float,
                 recommendation: str, action: str, reason: str):
        self.pair = pair
        self.bias = bias            # bullish | neutral | bearish
        self.confidence = confidence
        self.recommendation = recommendation  # allow | observe | block
        self.action = action        # hold | buy
        self.reason = reason

    def is_directionally_opposed(self, trade_side: str) -> bool:
        """Check if signal bias conflicts with trade direction."""
        if trade_side == "long" and self.bias == "bearish":
            return True
        if trade_side == "short" and self.bias == "bullish":
            return True
        return False


class SignalDeck:
    """All pairs from the signal file."""
    def __init__(self, pairs: Dict[str, SignalData], global_risk_mode: str):
        self.pairs = pairs            # key: normalized pair e.g. BTC/USDT:USDT
        self.global_risk_mode = global_risk_mode

    def get_signal(self, trade_pair: str) -> Optional[SignalData]:
        """Look up signal for a trade pair. Returns None if not covered."""
        normalized = normalize_pair(trade_pair)
        return self.pairs.get(normalized)


class RuleResult:
    """Result of rule evaluation."""
    def __init__(self, decision: str, reason_codes: List[str],
                 reason_text: str):
        self.decision = decision
        self.reason_codes = reason_codes
        self.reason_text = reason_text


# ── ENTRY RULES ──────────────────────────────────────────────
# Evaluated when a NEW trade opens (not seen in previous state).

def evaluate_entry(
    trade_pair: str,
    trade_side: str,
    signal: Optional[SignalData],
    signal_deck: SignalDeck,
) -> RuleResult:
    """Evaluate whether FreqForge would approve/veto/flag a new entry.

    Rule evaluation order: E4, E3, E1, E2, E5 — most severe first.
    """
    codes = []
    reasons = []

    # E4: global_risk_mode = risk_off → veto
    if signal_deck.global_risk_mode == "risk_off":
        codes.append("E4")
        reasons.append("Global risk mode is risk_off")
        return RuleResult(DECISION_VETO, codes, "; ".join(reasons))

    # E3: signal bias opposite to trade direction → veto
    if signal is not None and signal.is_directionally_opposed(trade_side):
        codes.append("E3")
        reasons.append(
            f"Signal bias '{signal.bias}' opposes {trade_side} direction"
        )
        return RuleResult(DECISION_VETO, codes, "; ".join(reasons))

    # E1: confidence < threshold → uncertain (NOT veto per A1 adjustment)
    if signal is not None and signal.confidence < CONFIDENCE_THRESHOLD:
        codes.append("E1")
        reasons.append(
            f"Signal confidence {signal.confidence:.2f} below {CONFIDENCE_THRESHOLD} threshold"
        )
        # Fall through — may accumulate more flags

    # E2: signal recommendation = observe + new entry → uncertain
    if signal is not None and signal.recommendation == "observe":
        if "E1" not in codes:  # avoid duplicate flagging
            codes.append("E2")
        reasons.append(
            f"Signal recommends 'observe' while entry occurred"
        )

    # E5: pair missing from signal deck → uncertain
    if signal is None:
        codes.append("E5")
        reasons.append(
            f"Pair {trade_pair} not covered by signal deck"
        )

    # Decision synthesis
    if codes:
        return RuleResult(DECISION_UNCERTAIN, codes, "; ".join(reasons))

    return RuleResult(
        DECISION_APPROVE, [],
        "Signal agrees with entry, no risk flags"
    )


# ── OPEN RISK RULES ──────────────────────────────────────────
# Evaluated for currently open positions each poll cycle.

def evaluate_open_risk(
    trade_pair: str,
    trade_side: str,
    pnl_pct: float,
    open_duration_candles: int,
    fleet_open_count: int,
    signal: Optional[SignalData],
    signal_deck: SignalDeck,
) -> RuleResult:
    """Evaluate open position risk. Called each poll for open trades."""
    codes = []
    reasons = []

    # O1: PnL < hard stop → veto_risk
    if pnl_pct < PNL_HARD_STOP:
        codes.append("O1")
        reasons.append(
            f"PnL {pnl_pct:+.2f}% below hard stop {PNL_HARD_STOP}%"
        )
        return RuleResult(DECISION_VETO, codes, "; ".join(reasons))

    # O3: duration < min candles → uncertain (let it breathe)
    if open_duration_candles < MIN_CANDLES_BREATHING:
        codes.append("O3")
        reasons.append(
            f"Trade only {open_duration_candles} candles old — needs breathing room"
        )

    # O2: fleet open > max → reduce_size
    if fleet_open_count > MAX_FLEET_OPEN:
        codes.append("O2")
        reasons.append(
            f"Fleet has {fleet_open_count} open trades (max {MAX_FLEET_OPEN})"
        )

    # Additional: directional conflict on open position
    if signal is not None and signal.is_directionally_opposed(trade_side):
        if "O1" not in codes:  # O1 already took priority
            codes.append("O1b")
            reasons.append(
                f"Signal bias '{signal.bias}' conflicts with open {trade_side}"
            )

    if codes:
        # Determine severity
        if "O1" in codes:
            return RuleResult(DECISION_VETO, codes, "; ".join(reasons))
        if "O2" in codes:
            return RuleResult(DECISION_REDUCE_SIZE, codes, "; ".join(reasons))
        return RuleResult(DECISION_UNCERTAIN, codes, "; ".join(reasons))

    return RuleResult(DECISION_APPROVE, [], "Open position within acceptable risk bounds")


# ── EXIT RULES (Post-Hoc Review) ─────────────────────────────
# Evaluated when a trade closes. Compares outcome with shadow opinion.

def evaluate_exit(
    trade_pair: str,
    close_profit: float,
    entry_shadow_decision: Optional[str],
    entry_shadow_codes: List[str],
) -> RuleResult:
    """Post-hoc review: would shadow decision have helped?

    entry_shadow_decision is the decision made at entry time
    (stored in state.json). If missing, we can't review.
    """
    codes = []
    reasons = []

    if entry_shadow_decision is None:
        return RuleResult(
            DECISION_UNCERTAIN, ["X0"],
            "No prior shadow decision recorded for this trade"
        )

    won = close_profit > 0

    # X1: closed trade WON after shadow veto → false_negative_review
    if won and entry_shadow_decision in (DECISION_VETO, DECISION_UNCERTAIN):
        codes.append("X1")
        reasons.append(
            f"Trade won ({close_profit*100:+.2f}%) despite shadow {entry_shadow_decision}"
        )
        return RuleResult(DECISION_FALSE_NEGATIVE, codes, "; ".join(reasons))

    # X2: closed trade LOST after shadow veto → veto_would_have_helped
    if not won and entry_shadow_decision in (DECISION_VETO,):
        codes.append("X2")
        reasons.append(
            f"Trade lost ({close_profit*100:+.2f}%) and shadow veto was correct"
        )
        return RuleResult(DECISION_VETO_HELPED, codes, "; ".join(reasons))

    # X3: closed trade LOST after shadow approve → missed_risk
    if not won and entry_shadow_decision == DECISION_APPROVE:
        codes.append("X3")
        reasons.append(
            f"Trade lost ({close_profit*100:+.2f}%) despite shadow approval"
        )
        return RuleResult(DECISION_MISSED_RISK, codes, "; ".join(reasons))

    # Default: trade won and shadow approved → clean
    return RuleResult(
        DECISION_APPROVE, [],
        f"Trade {'won' if won else 'lost'} ({close_profit*100:+.2f}%), shadow approved correctly"
    )


# ── Rule Registry (for reporting) ───────────────────────────

RULE_REGISTRY = {
    # Entry Rules
    "E1": "Signal confidence < 0.60 → uncertain",
    "E2": "Signal recommendation = observe + entry → uncertain",
    "E3": "Signal bias opposite to trade direction → veto",
    "E4": "Global risk_mode = risk_off → veto",
    "E5": "Pair not in signal deck → uncertain",
    # Open Risk Rules
    "O1": "PnL < -1.5% → veto",
    "O1b": "Signal conflicts with open direction → flag",
    "O2": "Fleet open trades > 6 → reduce_size",
    "O3": "Trade < 2 candles old → uncertain",
    # Exit Rules
    "X0": "No prior shadow decision → uncertain",
    "X1": "Won after veto → false_negative_review",
    "X2": "Lost after veto → veto_would_have_helped",
    "X3": "Lost after approve → missed_risk",
}
