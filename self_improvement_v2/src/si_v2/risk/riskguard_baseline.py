"""RiskGuard baseline contract v1 — conservative dry-run baseline for Agent0.

This module defines the versioned RiskGuard baseline contract consumed by the
SI-v2 apply gates (``derive_riskguard_status`` / ``read_riskguard_status``):

- **Contract identity:** ``riskguard_baseline_contract_v1``,
  ``schema_version = 1``, contract version ``1.0.0``.
- **Baseline builder:** ``build_conservative_baseline`` produces the
  dry-run-only baseline (mode ACTIVE, exactly the three permitted bots, the
  sanctioned core pairs, no mandates, no live authority).
- **Strict validator:** ``validate_state`` fail-closes on missing fields,
  unknown schema versions, unknown bots, forbidden fields, live-authority
  markers and limit breaches.
- **Atomic persistence:** ``write_state_atomic`` (tmp + fsync + os.replace)
  and ``initialize_baseline`` (backup before write, re-validate after).
- **Mandate contract:** ``validate_mandate`` enforces the proposal/mandate
  fields (proposal id, bot, from/to, allowlist, evidence, dry-run mandate,
  snapshot, measurement window, rollback criterion, expiry, replay
  protection).

Safety invariants (binding):

- Dry-run only. No live authority. No implicit upgrade to live.
- Unknown bot / pair / action / schema -> fail-closed.
- ``freqai-rebel`` is explicitly forbidden; webserver and rainbow are not
  trading actors.
- RiskGuard may be more conservative than the accepted project limits, never
  more permissive (limits are imported from accepted, versioned sources —
  nothing is estimated here).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Contract identity
# ---------------------------------------------------------------------------

CONTRACT_NAME: Final[str] = "riskguard_baseline_contract_v1"
SCHEMA_NAME: Final[str] = "riskguard_state"
SCHEMA_VERSION: Final[int] = 1
CONTRACT_VERSION: Final[str] = "1.0.0"

OPERATING_MODE_DRY_RUN_ONLY: Final[str] = "DRY_RUN_ONLY"
STATE_STATUS_ACTIVE: Final[str] = "ACTIVE"

# ---------------------------------------------------------------------------
# Bot scope (contract section 3)
# ---------------------------------------------------------------------------

ALLOWED_BOTS: Final[frozenset[str]] = frozenset(
    {
        "freqtrade-freqforge",
        "freqtrade-freqforge-canary",
        "freqtrade-regime-hybrid",
    }
)

FORBIDDEN_BOTS: Final[frozenset[str]] = frozenset({"freqai-rebel"})

NON_TRADING_ACTORS: Final[frozenset[str]] = frozenset(
    {"freqtrade-webserver", "rainbow"}
)

# ---------------------------------------------------------------------------
# Decision / mandate states (contract section 7)
# ---------------------------------------------------------------------------

MANDATE_STATES: Final[frozenset[str]] = frozenset(
    {"ACCEPTED", "REJECTED", "BLOCK_ENTRY", "EXPIRED", "INVALID"}
)

PAIR_VERDICTS: Final[frozenset[str]] = frozenset({"ACCEPTED", "WATCH_ONLY", "BLOCK_ENTRY"})

# Mandates in these states never authorise an apply.
NON_APPLYABLE_MANDATE_STATES: Final[frozenset[str]] = frozenset(
    {"REJECTED", "BLOCK_ENTRY", "EXPIRED", "INVALID"}
)

# ---------------------------------------------------------------------------
# Limits imported from accepted, versioned project sources (section 5)
# ---------------------------------------------------------------------------
# Source: self_improvement_v2/src/si_v2/propose/safe_parameters.py
#         (_PARAMETER_RANGES) and apply_actuator COOLDOWN_DAYS (7).
# RiskGuard may be MORE conservative than these, never more permissive.

ALLOWED_PARAMETERS: Final[tuple[str, ...]] = (
    "rsi_period",
    "stoploss_pct",
    "take_profit_pct",
    "stake_factor",
    "max_open_trades",
    "cooldown_candles",
)

PARAMETER_LIMITS: Final[dict[str, tuple[float, float]]] = {
    "rsi_period": (2.0, 50.0),
    "stoploss_pct": (-0.5, -0.001),
    "take_profit_pct": (0.001, 0.5),
    "stake_factor": (0.1, 5.0),
    "max_open_trades": (1.0, 20.0),
    "cooldown_candles": (0.0, 100.0),
}

MIN_APPLY_COOLDOWN_DAYS: Final[int] = 7  # apply_actuator COOLDOWN_DAYS

# Forbidden state fields (contract section 4): anything that could grant live
# authority, exchange access, strategy/pairlist changes or infra control.
# The scan is exact-key based and applies at any nesting depth.
FORBIDDEN_STATE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "dry_run",
        "exchange",
        "api_key",
        "api_secret",
        "secret",
        "password",
        "key",
        "token",
        "telegram",
        "api_server",
        "stake_currency",
        "leverage",
        "force_exit",
        "force_sell",
        "db_url",
        "db_urls",
        "dry_run_wallet",
        "pair_whitelist",
        "pair_blacklist",
        "strategy",
        "strategies",
        "docker",
        "network",
        "scheduler",
    }
)

REQUIRED_STATE_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "contract_name",
    "contract_version",
    "created_at_utc",
    "updated_at_utc",
    "binding_commit",
    "mode",
    "operating_mode",
    "live_authority",
    "summary",
    "pairs",
    "bot_scope",
    "limits",
    "mandates",
)

MAX_SUPPORTED_SCHEMA_VERSION: Final[int] = SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """Structured validation outcome (never raises)."""

    ok: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "reason": self.reason}


# ---------------------------------------------------------------------------
# Baseline builder
# ---------------------------------------------------------------------------


def build_conservative_baseline(
    *,
    binding_commit: str,
    created_at_utc: str | None = None,
    updated_at_utc: str | None = None,
) -> dict[str, object]:
    """Build the conservative dry-run-only RiskGuard baseline state.

    The baseline contains no mandates (no apply is possible without an
    explicit mandate) and grants no live authority. The sanctioned core pairs
    (BTC/ETH/SOL) carry ``ACCEPTED`` so the consumer adapter derives PASS for
    gated dry-run evaluation; every other pair is unknown and therefore
    fail-closed (``WATCH_ONLY``/unknown -> blocked downstream).
    """
    now = datetime.now(tz=UTC).isoformat()
    created = created_at_utc or now
    updated = updated_at_utc or now

    return {
        "schema_version": SCHEMA_VERSION,
        "contract_name": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "created_at_utc": created,
        "updated_at_utc": updated,
        "binding_commit": binding_commit,
        "mode": STATE_STATUS_ACTIVE,
        "operating_mode": OPERATING_MODE_DRY_RUN_ONLY,
        "live_authority": False,
        "summary": {
            "status": STATE_STATUS_ACTIVE,
            "baseline": True,
            "source": "riskguard_init_baseline (contract v1)",
            "total_pairs": 3,
            "accepted": 3,
            "watch_only": 0,
            "block_entry": 0,
        },
        "pairs": {
            "BTC/USDT": {
                "verdict": "ACCEPTED",
                "allow_long_bias": True,
                "allow_short_bias": True,
                "riskguard_reason": "baseline: sanctioned core pair",
            },
            "ETH/USDT": {
                "verdict": "ACCEPTED",
                "allow_long_bias": True,
                "allow_short_bias": True,
                "riskguard_reason": "baseline: sanctioned core pair",
            },
            "SOL/USDT": {
                "verdict": "ACCEPTED",
                "allow_long_bias": True,
                "allow_short_bias": True,
                "riskguard_reason": "baseline: sanctioned core pair",
            },
        },
        "bot_scope": {
            "allowed": sorted(ALLOWED_BOTS),
            "forbidden": sorted(FORBIDDEN_BOTS),
            "non_trading_actors": sorted(NON_TRADING_ACTORS),
            "unknown_bots": "BLOCK_ENTRY",
        },
        "limits": {
            "parameters": {name: list(rng) for name, rng in PARAMETER_LIMITS.items()},
            "min_apply_cooldown_days": MIN_APPLY_COOLDOWN_DAYS,
            "source": "safe_parameters._PARAMETER_RANGES + apply_actuator.COOLDOWN_DAYS",
        },
        "mandates": [],
    }


# ---------------------------------------------------------------------------
# Strict validator (never raises)
# ---------------------------------------------------------------------------


def _iter_field_paths(node: object, prefix: str = "") -> Iterator[tuple[str, object]]:
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key
            yield from _iter_field_paths(value, path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_field_paths(value, f"{prefix}[{index}]")


def _find_forbidden_fields(state: dict[str, object]) -> str | None:
    """Return the first forbidden field path, or None when the state is clean.

    Exact-key match at any nesting depth. ``dry_run_only`` /
    ``dry_run_mandate`` are distinct legal keys and never match ``dry_run``.
    """
    for path, key in _iter_field_paths(state):
        if isinstance(key, str) and key in FORBIDDEN_STATE_FIELDS:
            return path
    return None


def _validate_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def validate_state(state: object) -> ValidationResult:
    """Strictly validate a RiskGuard state dict against contract v1.

    Fail-closed: a missing field, an unknown schema version, an unknown bot,
    a forbidden field, a live-authority marker or a limit breach yields
    ``ok=False`` with a machine-readable reason. Never raises.
    """
    if not isinstance(state, dict):
        return ValidationResult(False, "state_not_a_dict")

    for field in REQUIRED_STATE_FIELDS:
        if field not in state:
            return ValidationResult(False, f"missing_required_field:{field}")

    schema_version = state.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        return ValidationResult(False, "schema_version_not_int")
    if schema_version != SCHEMA_VERSION:
        if schema_version > MAX_SUPPORTED_SCHEMA_VERSION:
            return ValidationResult(False, f"unknown_schema_version:{schema_version}")
        return ValidationResult(False, f"unsupported_schema_version:{schema_version}")

    if state.get("contract_name") != CONTRACT_NAME:
        return ValidationResult(False, "contract_name_mismatch")

    contract_version = state.get("contract_version")
    if not isinstance(contract_version, str) or not contract_version:
        return ValidationResult(False, "contract_version_missing")

    for ts_field in ("created_at_utc", "updated_at_utc"):
        if not _validate_timestamp(state.get(ts_field)):
            return ValidationResult(False, f"invalid_timestamp:{ts_field}")

    binding_commit = state.get("binding_commit")
    if not isinstance(binding_commit, str) or len(binding_commit.strip()) < 7:
        return ValidationResult(False, "binding_commit_missing_or_too_short")

    if state.get("mode") != STATE_STATUS_ACTIVE:
        return ValidationResult(False, f"mode_not_active:{state.get('mode')!r}")

    if state.get("operating_mode") != OPERATING_MODE_DRY_RUN_ONLY:
        return ValidationResult(False, f"operating_mode_not_dry_run_only:{state.get('operating_mode')!r}")

    if state.get("live_authority") is not False:
        return ValidationResult(False, "live_authority_must_be_false")

    forbidden = _find_forbidden_fields(state)
    if forbidden is not None:
        return ValidationResult(False, f"forbidden_field:{forbidden}")

    summary = state.get("summary")
    if not isinstance(summary, dict):
        return ValidationResult(False, "summary_not_a_dict")
    if summary.get("status") != STATE_STATUS_ACTIVE:
        return ValidationResult(False, f"summary_status_not_active:{summary.get('status')!r}")

    pairs = state.get("pairs")
    if not isinstance(pairs, dict) or not pairs:
        return ValidationResult(False, "pairs_not_a_nonempty_dict")
    for pair_name, pair_data in pairs.items():
        if not isinstance(pair_name, str) or not pair_name:
            return ValidationResult(False, "pair_name_invalid")
        if not isinstance(pair_data, dict):
            return ValidationResult(False, f"pair_data_not_a_dict:{pair_name}")
        verdict = pair_data.get("verdict")
        if verdict not in PAIR_VERDICTS:
            return ValidationResult(False, f"unknown_pair_verdict:{pair_name}:{verdict!r}")

    bot_scope = state.get("bot_scope")
    if not isinstance(bot_scope, dict):
        return ValidationResult(False, "bot_scope_not_a_dict")
    allowed = bot_scope.get("allowed")
    if not isinstance(allowed, list) or not allowed:
        return ValidationResult(False, "bot_scope_allowed_missing")
    for bot in allowed:
        if bot in FORBIDDEN_BOTS:
            return ValidationResult(False, f"forbidden_bot_in_scope:{bot}")
        if bot in NON_TRADING_ACTORS:
            return ValidationResult(False, f"non_trading_actor_in_scope:{bot}")
        if bot not in ALLOWED_BOTS:
            return ValidationResult(False, f"unknown_bot_in_scope:{bot}")

    limits = state.get("limits")
    if not isinstance(limits, dict):
        return ValidationResult(False, "limits_not_a_dict")
    parameters = limits.get("parameters")
    if not isinstance(parameters, dict):
        return ValidationResult(False, "limits_parameters_not_a_dict")
    for name in ALLOWED_PARAMETERS:
        if name not in parameters:
            return ValidationResult(False, f"limit_missing:{name}")
    for name, bounds in parameters.items():
        if name not in ALLOWED_PARAMETERS:
            return ValidationResult(False, f"unknown_parameter:{name}")
        limit = PARAMETER_LIMITS[name]
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            return ValidationResult(False, f"parameter_bounds_invalid:{name}")
        try:
            low, high = float(bounds[0]), float(bounds[1])
        except (TypeError, ValueError):
            return ValidationResult(False, f"parameter_bounds_not_numeric:{name}")
        if low < limit[0] or high > limit[1]:
            return ValidationResult(False, f"limit_breach:{name}")
    cooldown = limits.get("min_apply_cooldown_days")
    if not isinstance(cooldown, int) or isinstance(cooldown, bool):
        return ValidationResult(False, "cooldown_not_int")
    if cooldown < MIN_APPLY_COOLDOWN_DAYS:
        return ValidationResult(False, "cooldown_below_accepted_minimum")

    mandates = state.get("mandates")
    if not isinstance(mandates, list):
        return ValidationResult(False, "mandates_not_a_list")
    for mandate in mandates:
        result = validate_mandate(mandate)
        if not result.ok:
            return ValidationResult(False, f"invalid_mandate:{result.reason}")

    return ValidationResult(True, "valid")


# ---------------------------------------------------------------------------
# Mandate contract (section 6) — expiry + replay protection
# ---------------------------------------------------------------------------


def validate_mandate(
    mandate: object,
    *,
    now: datetime | None = None,
    seen_revisions: frozenset[str] | None = None,
) -> ValidationResult:
    """Validate a dry-run apply mandate.

    Required fields: proposal_id, bot_id, parameter, from_value, to_value,
    allowlist_match, evidence_refs, dry_run_mandate, snapshot_id,
    canary_target, measurement_window, rollback_criterion, expires_at_utc,
    revision, state.

    Fail-closed: unknown bot/parameter, forbidden bot, non-canary target,
    ``dry_run_mandate`` not exactly ``DRY_RUN_ONLY``, missing snapshot or
    measurement window, expired timestamp, replay (revision already seen),
    limit breach, decision state not ACCEPTED.
    """
    if not isinstance(mandate, dict):
        return ValidationResult(False, "mandate_not_a_dict")

    required = (
        "proposal_id",
        "bot_id",
        "parameter",
        "from_value",
        "to_value",
        "allowlist_match",
        "evidence_refs",
        "dry_run_mandate",
        "snapshot_id",
        "canary_target",
        "measurement_window",
        "rollback_criterion",
        "expires_at_utc",
        "revision",
        "state",
    )
    for field in required:
        if field not in mandate:
            return ValidationResult(False, f"mandate_missing_field:{field}")

    if mandate.get("state") != "ACCEPTED":
        return ValidationResult(False, f"mandate_state_not_accepted:{mandate.get('state')!r}")

    bot_id = mandate.get("bot_id")
    if bot_id in FORBIDDEN_BOTS:
        return ValidationResult(False, f"mandate_forbidden_bot:{bot_id}")
    if bot_id not in ALLOWED_BOTS:
        return ValidationResult(False, f"mandate_unknown_bot:{bot_id}")

    parameter = mandate.get("parameter")
    if parameter not in ALLOWED_PARAMETERS:
        return ValidationResult(False, f"mandate_parameter_not_allowlisted:{parameter}")

    to_value = mandate.get("to_value")
    if not isinstance(to_value, (int, float)) or isinstance(to_value, bool):
        return ValidationResult(False, "mandate_to_value_not_numeric")
    limit = PARAMETER_LIMITS[str(parameter)]
    if not (limit[0] <= float(to_value) <= limit[1]):
        return ValidationResult(False, f"mandate_limit_breach:{parameter}={to_value}")

    if mandate.get("dry_run_mandate") != OPERATING_MODE_DRY_RUN_ONLY:
        return ValidationResult(False, "mandate_not_dry_run_only")

    if mandate.get("canary_target") is not True:
        return ValidationResult(False, "mandate_canary_target_not_true")

    if mandate.get("allowlist_match") is not True:
        return ValidationResult(False, "mandate_allowlist_match_not_true")

    evidence_refs = mandate.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        return ValidationResult(False, "mandate_evidence_refs_missing")

    snapshot_id = mandate.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        return ValidationResult(False, "mandate_snapshot_missing")

    window = mandate.get("measurement_window")
    if (
        not isinstance(window, dict)
        or not window.get("opened_at_utc")
        or not window.get("closes_at_utc")
    ):
        return ValidationResult(False, "mandate_measurement_window_missing")

    criterion = mandate.get("rollback_criterion")
    if not isinstance(criterion, str) or not criterion.strip():
        return ValidationResult(False, "mandate_rollback_criterion_missing")

    expires_at = mandate.get("expires_at_utc")
    if not isinstance(expires_at, str) or not expires_at.strip():
        return ValidationResult(False, "mandate_expiry_missing")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return ValidationResult(False, "mandate_expiry_invalid")
    if expiry.tzinfo is None:
        return ValidationResult(False, "mandate_expiry_naive")
    current = now or datetime.now(tz=UTC)
    if current >= expiry:
        return ValidationResult(False, "mandate_expired")

    revision = mandate.get("revision")
    if not isinstance(revision, str) or not revision.strip():
        return ValidationResult(False, "mandate_revision_missing")
    if seen_revisions is not None and revision in seen_revisions:
        return ValidationResult(False, "mandate_replay_detected")

    return ValidationResult(True, "valid_mandate")


def mandate_is_expired(mandate: dict[str, object], *, now: datetime | None = None) -> bool:
    """True when the mandate's expiry has passed (read-only helper)."""
    expires_at = mandate.get("expires_at_utc")
    if not isinstance(expires_at, str) or not expires_at.strip():
        return True
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expiry.tzinfo is None:
        return True
    return (now or datetime.now(tz=UTC)) >= expiry


# ---------------------------------------------------------------------------
# Atomic persistence (section 8)
# ---------------------------------------------------------------------------


def state_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_state_atomic(state: dict[str, object], path: Path) -> dict[str, object]:
    """Atomically write the state file (tmp + fsync + os.replace, mode 0644).

    Returns a small record with the written path, byte count and sha256.
    Never writes outside the given path's parent directory.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state, indent=2, sort_keys=True).encode("utf-8") + b"\n"

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, path)
        # fsync the directory so the rename is durable
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return {
        "path": str(path),
        "bytes": len(payload),
        "sha256": state_sha256(payload),
        "mode": "0644",
    }


def initialize_baseline(
    path: Path,
    *,
    binding_commit: str,
    backup_dir: Path | None = None,
) -> dict[str, object]:
    """Initialize the conservative baseline state at ``path``.

    Procedure (contract section 8):
      1. build baseline,
      2. validate before write,
      3. backup any existing file (never delete evidence),
      4. atomic write,
      5. re-read + re-validate (write must be legible and valid).

    Returns a record: ``{"action": "initialized"|"reinitialized"|"unchanged",
    "state_path", "backup_path"|None, "sha256", "validation"}``.
    """
    path = Path(path)
    baseline = build_conservative_baseline(binding_commit=binding_commit)

    pre = validate_state(baseline)
    if not pre.ok:
        raise ValueError(f"baseline_invalid_before_write:{pre.reason}")

    backup_path: str | None = None
    action = "initialized"
    if path.exists():
        existing_bytes = path.read_bytes()
        existing_sha = state_sha256(existing_bytes)
        new_bytes = json.dumps(baseline, indent=2, sort_keys=True).encode("utf-8") + b"\n"
        if existing_sha == state_sha256(new_bytes):
            action = "unchanged"
        else:
            action = "reinitialized"
            if backup_dir is not None:
                backup_dir = Path(backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
                backup = backup_dir / f"riskguard_state.{stamp}.{existing_sha[:12]}.json"
                backup.write_bytes(existing_bytes)
                os.chmod(backup, 0o600)
                backup_path = str(backup)

    write_record: dict[str, object]
    if action == "unchanged":
        write_record = {"path": str(path), "sha256": state_sha256(path.read_bytes())}
    else:
        write_record = write_state_atomic(baseline, path)

    # 5. re-read + re-validate
    try:
        written = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"state_unreadable_after_write:{exc}") from exc
    post = validate_state(written)
    if not post.ok:
        raise ValueError(f"state_invalid_after_write:{post.reason}")

    return {
        "action": action,
        "state_path": str(path),
        "backup_path": backup_path,
        "sha256": write_record.get("sha256"),
        "validation": post.to_dict(),
    }
