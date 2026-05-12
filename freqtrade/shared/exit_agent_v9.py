"""v9.0 Sentient Exit Agent — Shared version for Freqtrade container."""
import json
import logging

logger = logging.getLogger("ExitAgentV9")

SYSTEM_PROMPT = (
    "Du bist der Momentum-Evaluator eines autonomen Trading-Systems.\n"
    "Du bist KEIN Forecaster. Du bewertest NUR den aktuellen Momentum-Zustand (15m/5m).\n\n"
    "ENTSCHEIDUNGS-LOGIK:\n"
    "- HOLD: Momentum neutral/stabil. RSI 40-60. Kein Reversal auf 5m.\n"
    "- CUT: Klares Momentum-Reversal. 3+ rote 5m-Candles mit Volumen. RSI < 35.\n"
    "- MOVE_SL: Trade war > +0.5% im Plus, verliert Schwung. Einstieg absichern.\n\n"
    "OUTPUT-FORMAT (ausschliesslich JSON):\n"
    '{"decision": "HOLD"|"CUT"|"MOVE_SL", "confidence": 0.0-1.0, "reasoning": "..."}\n\n'
    "Confidence < 0.60 immer HOLD. Sei entscheidungsfreudig, aber nicht panisch."
)


class ExitAgent:
    """v9.0 Sentient Exit Agent with Guardrails — container-safe version."""

    def __init__(self):
        self.logger = logger

    def evaluate(self, context: dict) -> dict:
        trade = context.get('trade', {})
        market = context.get('market_context', {})
        portfolio = context.get('portfolio', {})

        # G1: Trade zu jung
        if trade.get('open_duration_candles', 0) < 2:
            return self._gr("HOLD", "G1: Trade too young (< 2 candles)")

        # G2: PnL > +1.5% — ROI-Exit hat Priorität
        if trade.get('unrealized_pnl_pct', 0) > 1.5:
            return self._gr("HOLD", "G2: PnL > 1.5%, ROI-Exit has priority")

        # G3: Hard Stop -1.5%
        if trade.get('unrealized_pnl_pct', 0) <= -1.5:
            return self._gr("CUT", "G3: Hard Stop -1.5% reached")

        # G4: Max offene Trades
        if portfolio.get('open_trades_count', 0) > 3:
            return self._gr("HOLD", "G4: Max open trades exceeded (> 3)")

        # G5: Flash Crash
        btc_change = market.get('btc_change_15m', 0.0)
        if btc_change < -2.0:
            return self._gr("CUT", "G5: Flash Crash (BTC -2% in 15min)")

        return self._call_llm(context)

    def _gr(self, decision: str, reasoning: str) -> dict:
        return {"decision": decision, "confidence": 1.0, "reasoning": reasoning}

    def _call_llm(self, context: dict) -> dict:
        import sys
        sys.path.insert(0, "/freqtrade/shared")
        from primo_gate import request_llm

        try:
            raw = request_llm("v9_sentient_exit", json.dumps(context), SYSTEM_PROMPT)
            response = json.loads(raw)
            if response.get('confidence', 0.0) < 0.60:
                return {
                    "decision": "HOLD",
                    "confidence": response.get('confidence', 0.0),
                    "reasoning": f"Low Confidence ({response.get('confidence', 0.0)}): {response.get('reasoning')}"
                }
            return response
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self.logger.error(f"LLM parse error: {e}")
            return self._gr("HOLD", f"LLM parse error, HOLD")
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}")
            return self._gr("HOLD", f"LLM call failed, HOLD")

    def evaluate_safe(self, context: dict) -> dict:
        """evaluate() with blanket try/except — never crashes."""
        try:
            return self.evaluate(context)
        except Exception as e:
            self.logger.error(f"ExitAgent crashed: {e}")
            return self._gr("HOLD", f"Agent crash, HOLD")
