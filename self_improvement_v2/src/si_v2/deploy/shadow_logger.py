"""Shadow logger for deploy-phase tracking.

Logs proposed mutations and their outcomes for later review
without affecting live trading.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime


class ShadowLogger:
    """Logs mutation proposals and outcomes to a shadow log file."""

    def __init__(self, log_path: str = "/tmp/si_v2_shadow.log") -> None:
        """Initialize with a log file path.

        Args:
            log_path: Path to the shadow log file.
        """
        self._log_path = log_path

    def log_proposal(
        self,
        bot_id: str,
        candidate_sha: str,
        params: dict[str, float | int],
        outcome: str | None = None,
    ) -> None:
        """Log a mutation proposal to the shadow log.

        Args:
            bot_id: Bot identifier.
            candidate_sha: SHA256 hash of the candidate.
            params: Proposed parameters.
            outcome: Optional outcome string.
        """
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "bot_id": bot_id,
            "candidate_sha": candidate_sha,
            "params": params,
            "outcome": outcome,
        }
        with open(self._log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_log(self) -> list[dict[str, str]]:
        """Read all shadow log entries.

        Returns:
            List of log entry dictionaries.
        """
        entries: list[dict[str, str]] = []
        try:
            with open(self._log_path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except FileNotFoundError:
            pass
        return entries
