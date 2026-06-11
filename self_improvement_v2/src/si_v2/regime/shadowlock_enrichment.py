"""Shadowlock enrichment writer — derived enrichment records for regime events."""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from si_v2.regime.label import RegimeLabel
from si_v2.regime.legacy_adapter import LegacyLabelAdapter


class DuplicateConflictError(ValueError):
    """Raised when a source_event_id maps to a different semantic payload."""


class ExtractRegimeFn(Protocol):
    """Protocol for callable that extracts regime info from a ledger record.

    Receives a raw ledger record dict and returns
    (source_event_id, regime_label_str, confidence).
    """

    def __call__(self, record: dict) -> tuple: ...


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
        self._seen: dict[str, tuple[str, str, float, str, str, str]] = {}

    def _compute_input_hash(self, record: dict) -> str:
        """Compute SHA-256 of canonical JSON representation of a record."""
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _validate_source_event_id(self, source_event_id: str) -> None:
        """H6: Validate source_event_id is a non-empty string after strip."""
        if not isinstance(source_event_id, str) or not source_event_id.strip():
            raise ValueError(
                f"source_event_id must be a non-empty string; "
                f"got {source_event_id!r}"
            )

    def _validate_confidence(self, confidence: float) -> None:
        """H7: Validate confidence is finite and in [0.0, 1.0]."""
        if isinstance(confidence, bool):
            raise ValueError(
                f"confidence must be a float, not bool; got {confidence}"
            )
        if not isinstance(confidence, (int, float)):
            raise ValueError(
                f"confidence must be a numeric value; got {type(confidence).__name__}"
            )
        if not isinstance(confidence, float):
            confidence = float(confidence)
        if math.isnan(confidence) or math.isinf(confidence):
            raise ValueError(
                f"confidence must be finite; got {confidence}"
            )
        if confidence < 0.0 or confidence > 1.0:
            raise ValueError(
                f"confidence must be in [0.0, 1.0]; got {confidence}"
            )

    def _build_enrichment(
        self,
        source_event_id: str,
        regime: RegimeLabel,
        confidence: float,
        input_hash: str,
        enrichment_created_at: datetime,
    ) -> dict:
        """H9: Build a single enrichment record dict with explicit timestamp."""
        self._validate_source_event_id(source_event_id)
        self._validate_confidence(confidence)
        return {
            "source_event_id": source_event_id,
            "regime": str(regime),
            "confidence": confidence,
            "schema_version": self._schema_version,
            "model_version": self._model_version,
            "enrichment_created_at": enrichment_created_at.strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "input_hash": input_hash,
        }

    def process_ledger(
        self,
        ledger: Iterable[dict],
        output_path: str,
        extract_regime_fn: ExtractRegimeFn | None = None,
        enrichment_created_at: datetime | None = None,
    ) -> list[dict]:
        """Process a Shadowlock ledger and write enrichment records atomically.

        Args:
            ledger: Iterable of dicts representing Shadowlock JSONL records.
            output_path: Path to the output JSONL file (created/overwritten).
            extract_regime_fn: Optional callable to extract regime info from
                a ledger record. Receives a dict, returns (source_event_id,
                regime_label_str, confidence). If None, uses default extraction
                looking for 'regime_label' and 'source_event_id' keys.
            enrichment_created_at: Explicit timestamp for enrichment records.
                If None, each enrichment gets the detected_at from the source
                record if available, otherwise raises ValueError.

        Returns:
            List of enrichment dicts that were written.

        Raises:
            DuplicateConflictError: If the same source_event_id maps to a
                different semantic payload than previously seen.
            ValueError: If source_event_id is empty, confidence is invalid,
                or enrichment_created_at is None and no source timestamp found.

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

            # H6: Validate source_event_id
            try:
                self._validate_source_event_id(event_id)
            except ValueError:
                continue

            # H7: Validate confidence
            try:
                self._validate_confidence(confidence)
            except ValueError:
                continue

            input_hash = self._compute_input_hash(record)
            regime = LegacyLabelAdapter.to_canonical(regime_label_str)

            # H8: Duplicate detection uses full semantic identity
            semantic_key = (
                event_id,
                str(regime),
                confidence,
                input_hash,
                self._schema_version,
                self._model_version,
            )

            if event_id in self._seen:
                existing = self._seen[event_id]
                if existing != semantic_key:
                    raise DuplicateConflictError(
                        f"source_event_id {event_id!r} already exists with "
                        f"different semantic payload. "
                        f"Existing: (regime={existing[1]}, confidence={existing[2]}, "
                        f"hash={existing[3][:12]}...) "
                        f"New: (regime={semantic_key[1]}, confidence={semantic_key[2]}, "
                        f"hash={semantic_key[3][:12]}...)"
                    )
                # Idempotent: same full semantic identity, skip
                continue

            # H9: Determine enrichment_created_at
            if enrichment_created_at is not None:
                ts = enrichment_created_at
            else:
                # Fall back to detected_at from the source record if available
                source_ts = record.get("detected_at") or record.get(
                    "timestamp_utc"
                )
                if source_ts is not None:
                    if isinstance(source_ts, datetime):
                        ts = source_ts
                    else:
                        # Try parsing ISO string
                        try:
                            ts = datetime.fromisoformat(
                                source_ts.replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError):
                            raise ValueError(
                                "enrichment_created_at is required when source "
                                "record has no parseable timestamp"
                            ) from None
                else:
                    raise ValueError(
                        "enrichment_created_at is required when source "
                        "record has no timestamp"
                    )

            self._seen[event_id] = semantic_key
            enrichment = self._build_enrichment(
                source_event_id=event_id,
                regime=regime,
                confidence=confidence,
                input_hash=input_hash,
                enrichment_created_at=ts,
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
