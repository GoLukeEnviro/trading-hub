"""Shadowlock enrichment writer — derived enrichment records for regime events."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from datetime import UTC, datetime

from si_v2.regime.label import RegimeLabel
from si_v2.regime.legacy_adapter import LegacyLabelAdapter


class DuplicateConflictError(ValueError):
    """Raised when a source_event_id maps to a different regime."""


class ShadowlockEnrichmentWriter:
    """Writes derived enrichment records to a separate JSONL file.

    Reads an existing Shadowlock JSONL ledger (as an iterable of dicts),
    and writes enrichment records to a NEW, separate output file.
    The original ledger is NEVER modified (read-only consumption).

    Enrichment records contain:
      - source_event_id: ID of the source Shadowlock event
      - regime: canonical regime label
      - confidence: detection confidence
      - schema_version: enrichment schema version
      - model_version: detection model version
      - enrichment_created_at: UTC ISO timestamp
      - input_hash: SHA-256 of the source JSON line
    """

    def __init__(
        self,
        schema_version: str = "1",
        model_version: str = "v1.0.0",
    ) -> None:
        """Initialize the enrichment writer.

        Args:
            schema_version: Schema version for enrichment records.
            model_version: Model version for enrichment records.
        """
        self._schema_version = schema_version
        self._model_version = model_version
        self._seen: dict[str, RegimeLabel] = {}

    def _compute_input_hash(self, record: dict) -> str:
        """Compute SHA-256 of canonical JSON representation of a record."""
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _build_enrichment(
        self,
        source_event_id: str,
        regime: RegimeLabel,
        confidence: float,
        input_hash: str,
    ) -> dict:
        """Build a single enrichment record dict."""
        return {
            "source_event_id": source_event_id,
            "regime": str(regime),
            "confidence": confidence,
            "schema_version": self._schema_version,
            "model_version": self._model_version,
            "enrichment_created_at": datetime.now(UTC).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "input_hash": input_hash,
        }

    def process_ledger(
        self,
        ledger: Iterable[dict],
        output_path: str,
        extract_regime_fn=None,
    ) -> list[dict]:
        """Process a Shadowlock ledger and write enrichment records atomically.

        Args:
            ledger: Iterable of dicts representing Shadowlock JSONL records.
            output_path: Path to the output JSONL file (created/overwritten).
            extract_regime_fn: Optional callable to extract regime info from
                a ledger record. Receives a dict, returns (source_event_id,
                regime_label_str, confidence). If None, uses default extraction
                looking for 'regime_label' and 'source_event_id' keys.

        Returns:
            List of enrichment dicts that were written.

        Raises:
            DuplicateConflictError: If the same source_event_id maps to a
                different regime than previously seen.

        Note:
            Writes are atomic via tempfile + os.replace. The output file
            contains complete state only after a successful replace.
        """
        if extract_regime_fn is None:
            extract_regime_fn = self._default_extract

        enrichments: list[dict] = []
        self._seen = {}

        for record in ledger:
            if not isinstance(record, dict):
                continue

            try:
                event_id, regime_label_str, confidence = extract_regime_fn(
                    record
                )
            except (KeyError, TypeError, ValueError):
                continue

            if event_id is None or regime_label_str is None:
                continue

            input_hash = self._compute_input_hash(record)
            regime = LegacyLabelAdapter.to_canonical(regime_label_str)

            # Check for conflicting duplicate
            if event_id in self._seen:
                existing = self._seen[event_id]
                if existing != regime:
                    raise DuplicateConflictError(
                        f"source_event_id {event_id!r} already mapped to "
                        f"{existing}, but got {regime}"
                    )
                # Idempotent: same regime, skip
                continue

            self._seen[event_id] = regime
            enrichment = self._build_enrichment(
                source_event_id=event_id,
                regime=regime,
                confidence=confidence,
                input_hash=input_hash,
            )
            enrichments.append(enrichment)

        # Atomic write: tempfile → os.replace
        fd, tmp_path = tempfile.mkstemp(
            suffix=".jsonl",
            dir=os.path.dirname(output_path) or ".",
        )
        try:
            with os.fdopen(fd, "w") as tmp_fp:
                for enrichment in enrichments:
                    line = (
                        json.dumps(enrichment, sort_keys=True) + "\n"
                    )
                    tmp_fp.write(line)
            os.replace(tmp_path, output_path)
        except BaseException:
            # Clean up temp file on any error
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

        return enrichments

    @staticmethod
    def _default_extract(record: dict) -> tuple:
        """Default extraction: look for source_event_id and regime_label.

        Args:
            record: A Shadowlock ledger record dict.

        Returns:
            (source_event_id, regime_label_str, confidence) tuple.
        """
        event_id = str(record.get("source_event_id", ""))
        regime_label = str(record.get("regime_label", ""))
        confidence = float(record.get("confidence", 0.0))
        return event_id, regime_label, confidence
