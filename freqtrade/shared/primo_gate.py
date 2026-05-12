"""PrimoGate bridge for Freqtrade container.

This module provides the request_llm function that the exit_agent_v9.py
imports from the shared directory. In the container, it delegates to the
primo_gate module from the PrimoAgent system.
"""
import json
import logging

logger = logging.getLogger("PrimoGate")


def request_llm(agent_name: str, context: str, system_prompt: str) -> str:
    """Send a request to the LLM via primo_gate and return raw JSON response string.

    If primo_gate is not available (development/test mode), returns a HOLD response
    so the exit agent never blocks.
    """
    try:
        # Versuche den echten PrimoGate-Import
        import sys
        sys.path.insert(0, "/home/hermes/primoagent/src")
        from primo_gate import PrimoGate

        gate = PrimoGate()
        result = gate.request(system_prompt, context)

        # PrimoGate liefert entweder einen String (JSON) oder einen dict
        if isinstance(result, dict):
            return json.dumps(result)
        return result

    except Exception as e:
        logger.warning(f"primo_gate not available, fallback HOLD: {e}")
        return json.dumps({
            "decision": "HOLD",
            "confidence": 1.0,
            "reasoning": "PrimoGate not connected"
        })
