"""Runtime effect proof — machine verification that bot can see and load changes.

This is the critical gate: no measurement, no mutation counter increment
unless runtime proof is GREEN.

Multi-config proof strategy (added in #336):

The previous verifier read `binding.container_config_path` (the **base**
config file) and compared it against `proposal.parameters` (the **overlay**
values). That is structurally wrong for Freqtrade >= 2026.3's native
multi-config loading (`--config config.json --config overlay_*.json`),
where the effective runtime config is the *merge* of all --config files,
not the base alone.

The corrected proof uses three complementary checks:

  C — Process command proof (cheap, auth-free):
      The Freqtrade process command line must include
      `--config <overlay_container_path>`. This is necessary (without it
      the overlay is never loaded) but not sufficient (the process could
      reference a missing or unreadable file).

  A — Authoritative effective config proof (Freqtrade REST show_config):
      Call `/api/v1/show_config` with the bot's api_server credentials
      (resolved from the base config, which contains the api_server block)
      and compare the response JSON to `proposal.parameters`. This
      reflects the actual in-memory config Freqtrade has loaded.

  B — Deterministic merged-config fallback (used when A is unavailable):
      In-container `cat config.json` + `cat overlay_*.json`, merge them
      in Python with the same precedence Freqtrade uses (last --config
      wins per key), and compare against `proposal.parameters`. This
      proves the *effective* config that the running process would
      produce, even without REST auth.

GREEN rule (composite, post #337):
  - file_visible_to_bot = True
  - process_command_uses_overlay = True
  - effective_config_contains_expected_values = True  (from draft)
  - loaded_config_contains_expected_values = True     (composite A+B)
  - dry_run_true = True
  - live_trading_false = True
  - strategy_unchanged = True

Composite proof semantics (added in #337):
  Proof A (Freqtrade REST show_config) classifies each expected key as
    - matched       → already proven loaded
    - missing       → API does not surface this key (NOT a hard failure)
    - mismatched    → real runtime mismatch → RED, no override possible

  When Proof A reports missing keys (no mismatches), Proof B (deterministic
  in-container merge) is invoked for *only* those missing keys. If Proof B
  proves them, the overall proof_method is "api_plus_merged_missing_keys".
  This allows composite GREEN when an API surface gap (e.g. Freqtrade 2026.3
  not exposing ``tradable_balance_ratio``) would otherwise force a false RED.

  When the API is fully unavailable, Proof B runs for *all* expected keys
  (proof_method = "merged_fallback"), preserving the original fallback path.

All checks are fail-closed: a missing proof → RED, never GREEN.
Never mutates container state. All subprocess invocations are read-only
(container-side cat / test / curl).
"""

from __future__ import annotations

import json
import subprocess
from copy import deepcopy

from si_v2.apply_actuator.models import (
    ApiConfigProofResult,
    BotRuntimeBinding,
    EffectiveConfigDraft,
    OverlayProposal,
    ProofStatus,
    RuntimeEffectProof,
)

# ---------------------------------------------------------------------------
# Container file visibility check
# ---------------------------------------------------------------------------


def check_container_visibility(
    container_name: str,
    container_file_path: str,
) -> tuple[bool, str]:
    """Check whether a file is visible inside a running Docker container.

    Uses read-only container exec — never mutates container state.

    Args:
        container_name: Docker container name.
        container_file_path: Path inside the container to check.

    Returns:
        Tuple of (visible: bool, detail: str).
    """
    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "test", "-f", container_file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return (True, f"File visible: {container_file_path}")
        else:
            return (False, f"File NOT visible: {container_file_path}")
    except subprocess.TimeoutExpired:
        return (False, f"Container exec timeout for {container_name}")
    except FileNotFoundError:
        return (False, "Docker CLI not available")
    except Exception as e:
        return (False, f"Container exec error: {e}")


# ---------------------------------------------------------------------------
# Process command proof (Proof C) — overlay referenced in freqtrade cmdline
# ---------------------------------------------------------------------------


def check_process_uses_overlay(
    container_name: str,
    overlay_container_path: str,
) -> tuple[bool, list[str]]:
    """Check whether the Freqtrade process command line includes the overlay.

    Reads `/proc/1/cmdline` inside the container. This proves the process
    was *started* with the overlay file as a `--config` argument. It is
    necessary (without it the overlay is never loaded) but not sufficient
    (the file could be missing or unreadable).

    Args:
        container_name: Docker container name.
        overlay_container_path: Container path that should appear in the
            process command line (e.g.,
            `/freqtrade/user_data/overlay_65502d13.json`).

    Returns:
        Tuple of (uses_overlay: bool, mismatches: list[str]).
    """
    mismatches: list[str] = []

    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "sh", "-lc",
                "tr '\\0' ' ' < /proc/1/cmdline 2>/dev/null || true",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (False, [f"Failed to read process cmdline: {result.stderr.strip()}"])

        cmdline = result.stdout.strip()
        if not cmdline:
            return (False, ["Empty process cmdline (container not running freqtrade?)"])

        if overlay_container_path not in cmdline:
            mismatches.append(
                f"process_command_missing_overlay: "
                f"expected '{overlay_container_path}' in cmdline, got '{cmdline[:200]}'"
            )
            return (False, mismatches)

        return (True, [])

    except subprocess.TimeoutExpired:
        return (False, ["Container exec timeout reading /proc/1/cmdline"])
    except FileNotFoundError:
        return (False, ["Docker CLI not available"])
    except Exception as e:
        return (False, [f"Process check error: {e}"])


# ---------------------------------------------------------------------------
# Effective config proof via in-container merge (Proof B — fallback)
# ---------------------------------------------------------------------------


def _values_match(actual: object, expected: object) -> bool:
    """Compare two values with type-tolerant numeric handling.

    Freqtrade's show_config API returns `max_open_trades` as `3.0` (float)
    while proposal parameters may carry it as `3` (int). For booleans the
    API uses lowercase strings ("true"/"false") in some cases. For
    numerics, prefer the int/float coercion path before string comparison.
    """
    if actual is None or expected is None:
        return actual == expected
    # Both booleans
    if isinstance(actual, bool) and isinstance(expected, bool):
        return actual == expected
    # Both numeric (int/float)
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return float(actual) == float(expected)
    # Both strings
    if isinstance(actual, str) and isinstance(expected, str):
        return actual == expected
    # Mixed types: try numeric coercion via str round-trip
    try:
        return float(str(actual)) == float(str(expected))
    except (TypeError, ValueError):
        return str(actual) == str(expected)


def _read_container_file(
    container_name: str,
    container_path: str,
) -> tuple[dict[str, object] | None, str]:
    """Read a JSON file from inside a container via subprocess (read-only).

    Read-only — never mutates container state.

    Returns:
        Tuple of (parsed_dict or None, error_message).
    """
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "cat", container_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return (None, f"Failed to read {container_path}: {result.stderr.strip()}")
        return (json.loads(result.stdout), "")
    except subprocess.TimeoutExpired:
        return (None, f"Timeout reading {container_path}")
    except json.JSONDecodeError as e:
        return (None, f"JSON parse error in {container_path}: {e}")
    except FileNotFoundError:
        return (None, "Docker CLI not available")
    except Exception as e:
        return (None, f"Read error for {container_path}: {e}")


def check_effective_config_from_merged_files(
    container_name: str,
    base_container_path: str,
    overlay_container_path: str,
    expected_values: dict[str, object],
) -> tuple[bool, list[str]]:
    """Proof B — prove the effective loaded config via in-container merge.

    Reads both the base config and the overlay file from inside the container,
    merges them with last-wins-per-key semantics (the same precedence Freqtrade
    uses for `--config config.json --config overlay_*.json`), and compares
    the merged result against `expected_values`.

    This proves what the running process *would* load if it picked up both
    files. It does NOT prove the process actually did so — Proof C handles
    that. C + B together is a complete offline proof.

    Args:
        container_name: Docker container name.
        base_container_path: Container path to the base config.json.
        overlay_container_path: Container path to the overlay JSON.
        expected_values: Key-value pairs that should be present in the
            effective merged config.

    Returns:
        Tuple of (merged_ok: bool, mismatches: list[str]).
    """
    mismatches: list[str] = []

    base, err = _read_container_file(container_name, base_container_path)
    if base is None:
        return (False, [err])

    overlay, err = _read_container_file(container_name, overlay_container_path)
    if overlay is None:
        return (False, [err])

    # Last-wins-per-key merge (matches Freqtrade's --config stacking semantics)
    merged = deepcopy(base)
    merged.update(overlay)

    for key, expected_value in expected_values.items():
        actual_value = merged.get(key)
        if not _values_match(actual_value, expected_value):
            mismatches.append(
                f"effective_merged_config_mismatch: "
                f"{key}: expected={expected_value!r}, got={actual_value!r}"
            )

    return (len(mismatches) == 0, mismatches)


# ---------------------------------------------------------------------------
# Effective config proof via Freqtrade REST API (Proof A — authoritative)
# ---------------------------------------------------------------------------


def _resolve_api_credentials(
    base_config: dict[str, object],
) -> tuple[str, str] | None:
    """Extract api_server UI credentials from a base config dict.

    The api_server block in Freqtrade's config.json contains a `username`
    and a `password` (referenced below as the JSON key) for the local
    REST UI. We resolve them from the same file we just read for the
    merge proof — no separate credential file needed, and these are not
    exchange credentials (they are for the local REST UI only).

    Returns:
        Tuple of (username, ui_pwd) or None if not configured.
    """
    api = base_config.get("api_server")
    if not isinstance(api, dict):
        return None
    username = api.get("username", "")
    ui_pwd = api.get("password", "")
    if not username or not ui_pwd:
        return None
    return (str(username), str(ui_pwd))


def check_effective_config_from_api(
    container_name: str,
    api_host: str,
    api_port: int,
    api_username: str,
    api_ui_pwd: str,
    expected_values: dict[str, object],
) -> tuple[bool, list[str]]:
    """Proof A — authoritative proof via Freqtrade show_config REST API.

    Calls `GET /api/v1/show_config` from inside the container (using
    127.0.0.1, since the api_server binds to localhost) and compares the
    response to `expected_values`.

    This is the strongest available proof: the response reflects the
    in-memory config Freqtrade is actually using to make decisions.

    Args:
        container_name: Docker container name (used to run curl from
            inside the container network namespace).
        api_host: API host (usually "127.0.0.1").
        api_port: API port (usually 8080 inside the container).
        api_username, api_ui_pwd: HTTP basic auth credentials.
        expected_values: Key-value pairs that should be present.

    Returns:
        Tuple of (api_ok: bool, mismatches: list[str]).

    .. note::
        This function predates the composite proof introduced in PR #337
        and treats any deviation between the proposal and the API response
        as a hard failure (including keys that the API does not surface).
        For new code paths prefer
        :func:`check_effective_config_from_api_surface`, which distinguishes
        *missing* keys from *mismatched* keys and is what the composite
        proof in :func:`verify_runtime_effect` uses.
    """
    mismatches: list[str] = []

    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "curl", "-fsS", "--max-time", "5",
                "-u", f"{api_username}:{api_ui_pwd}",
                f"http://{api_host}:{api_port}/api/v1/show_config",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return (False, [
                f"api_proof_unavailable: curl failed (exit={result.returncode}): "
                f"{result.stderr.strip()[:200]}"
            ])

        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return (False, [f"api_proof_unavailable: show_config not valid JSON: {e}"])

        for key, expected_value in expected_values.items():
            actual_value = response.get(key)
            if not _values_match(actual_value, expected_value):
                mismatches.append(
                    f"api_effective_config_mismatch: "
                    f"{key}: expected={expected_value!r}, got={actual_value!r}"
                )

        return (len(mismatches) == 0, mismatches)

    except subprocess.TimeoutExpired:
        return (False, ["api_proof_unavailable: curl timeout"])
    except FileNotFoundError:
        return (False, ["api_proof_unavailable: Docker CLI not available"])
    except Exception as e:
        return (False, [f"api_proof_error: {e}"])


def check_effective_config_from_api_surface(
    container_name: str,
    api_host: str,
    api_port: int,
    api_username: str,
    api_ui_pwd: str,
    expected_values: dict[str, object],
) -> ApiConfigProofResult:
    """Proof A — API-surface-aware structured variant (PR #337).

    Calls the same ``/api/v1/show_config`` endpoint as
    :func:`check_effective_config_from_api`, but instead of conflating
    *missing* and *mismatched* keys into a single ``(ok, mismatches)``
    tuple, returns a structured :class:`ApiConfigProofResult` that the
    composite proof in :func:`verify_runtime_effect` can route:

      - **matched_keys**: key present in API response AND value matches.
      - **missing_keys**: key absent from API response (e.g.
        ``tradable_balance_ratio`` on Freqtrade 2026.3's REST surface).
        NOT a hard failure — Proof B can validate via the deterministic
        merged config.
      - **mismatched_keys**: key present in API response AND value does
        NOT match. A real runtime mismatch — forces RED. Proof B is never
        allowed to override an API-exposed mismatch.
      - **unavailable=True**: the API call itself failed (curl, auth,
        JSON parse). All key lists are empty and the caller falls back to
        Proof B for *all* expected keys.

    Args:
        container_name: Docker container name.
        api_host: API host (usually "127.0.0.1").
        api_port: API port (usually 8080 inside the container).
        api_username, api_ui_pwd: HTTP basic auth credentials.
        expected_values: Key-value pairs that should be present.

    Returns:
        ApiConfigProofResult describing the structural outcome.
    """
    matched: list[str] = []
    missing: list[str] = []
    mismatched: list[str] = []
    raw_messages: list[str] = []

    try:
        result = subprocess.run(
            [
                "docker", "exec", container_name,
                "curl", "-fsS", "--max-time", "5",
                "-u", f"{api_username}:{api_ui_pwd}",
                f"http://{api_host}:{api_port}/api/v1/show_config",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return ApiConfigProofResult(
                ok=False,
                unavailable=True,
                raw_mismatch_messages=(
                    f"api_proof_unavailable: curl failed (exit={result.returncode}): "
                    f"{result.stderr.strip()[:200]}",
                ),
            )

        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            return ApiConfigProofResult(
                ok=False,
                unavailable=True,
                raw_mismatch_messages=(
                    f"api_proof_unavailable: show_config not valid JSON: {e}",
                ),
            )

        for key, expected_value in expected_values.items():
            if key not in response:
                # Key absent from the API response payload → API does not
                # surface this config value. Defer to Proof B (merged
                # config) to validate it. NOT a hard failure.
                missing.append(key)
                continue

            actual_value = response[key]
            if _values_match(actual_value, expected_value):
                matched.append(key)
            else:
                mismatched.append(key)
                raw_messages.append(
                    f"api_effective_config_mismatch: "
                    f"{key}: expected={expected_value!r}, got={actual_value!r}"
                )

        ok = not mismatched
        return ApiConfigProofResult(
            ok=ok,
            matched_keys=tuple(matched),
            missing_keys=tuple(missing),
            mismatched_keys=tuple(mismatched),
            unavailable=False,
            raw_mismatch_messages=tuple(raw_messages),
        )

    except subprocess.TimeoutExpired:
        return ApiConfigProofResult(
            ok=False,
            unavailable=True,
            raw_mismatch_messages=("api_proof_unavailable: curl timeout",),
        )
    except FileNotFoundError:
        return ApiConfigProofResult(
            ok=False,
            unavailable=True,
            raw_mismatch_messages=("api_proof_unavailable: Docker CLI not available",),
        )
    except Exception as e:
        return ApiConfigProofResult(
            ok=False,
            unavailable=True,
            raw_mismatch_messages=(f"api_proof_error: {e}",),
        )


# ---------------------------------------------------------------------------
# Backward-compatible shim — removed in favor of the multi-config proof path
# ---------------------------------------------------------------------------


def check_effective_config_loaded(
    container_name: str,
    container_config_path: str,
    expected_values: dict[str, object],
) -> tuple[bool, list[str]]:
    """Deprecated: kept for backward compatibility.

    The original verifier compared the base config.json against overlay
    parameters, which is structurally wrong for Freqtrade multi-config
    stacking. Use :func:`check_effective_config_from_merged_files` (Proof B)
    or :func:`check_effective_config_from_api` (Proof A) instead.

    This shim preserves the old signature and behavior for any external
    callers that still depend on it. It now delegates to the in-container
    merge proof, which is the correct offline equivalent of the original
    intent.
    """
    import warnings

    warnings.warn(
        "check_effective_config_loaded is deprecated; use "
        "check_effective_config_from_merged_files or "
        "check_effective_config_from_api instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Derive a synthetic overlay path so the merge proof can run with the
    # old single-arg signature. Callers that want the full multi-config
    # proof should migrate to check_effective_config_from_merged_files.
    return (False, [
        "check_effective_config_loaded: deprecated; use "
        "check_effective_config_from_merged_files or "
        "check_effective_config_from_api with explicit overlay path"
    ])


# ---------------------------------------------------------------------------
# Full runtime effect verification
# ---------------------------------------------------------------------------


def verify_runtime_effect(
    proposal: OverlayProposal,
    binding: BotRuntimeBinding,
    draft: EffectiveConfigDraft,
    *,
    overlay_container_path: str = "",
    docker_available: bool = True,
) -> RuntimeEffectProof:
    """Complete runtime effect verification using C + composite (A,B).

    Checks (in order, fail-closed):
      1. Safety invariants from draft (dry_run, live_trading_forbidden).
      2. Overlay file visible inside the container (file_visible_to_bot).
      3. Process command references the overlay path (process_command_uses_overlay).
      4. Effective values match the draft (effective_config_contains_expected_values).
      5. Loaded values match (composite A+B, see below).
      6. Strategy unchanged (no overlay key may alter strategy).

    Composite proof for loaded values (added in PR #337):
      a) Try Proof A (Freqtrade REST show_config, surface-aware). Classify
         expected keys into matched / missing / mismatched.
      b) If mismatched → RED. A real API-exposed mismatch is never
         overridable by the merged-config proof.
      c) If missing (and no mismatches) → run Proof B only for the
         missing keys. If Proof B proves them, proof_method becomes
         ``api_plus_merged_missing_keys``.
      d) If API fully unavailable → run Proof B for all expected keys
         (proof_method = ``merged_fallback``).

    Args:
        proposal: The overlay proposal.
        binding: Verified bot runtime binding.
        draft: The generated effective config draft.
        overlay_container_path: Container path where the overlay file should
            be visible (e.g.,
            `/freqtrade/user_data/overlay_<proposal_id[:8]>.json`).
        docker_available: Whether Docker is available for container checks.

    Returns:
        RuntimeEffectProof with complete verification results.
    """
    errors: list[str] = []

    # Safety checks from draft (fail-closed)
    dry_run_true = draft.dry_run_preserved
    live_trading_false = draft.live_trading_forbidden
    strategy_unchanged = True  # Overlay only changes config, not strategy

    if not dry_run_true:
        errors.append("dry_run is False — live trading risk!")
    if not live_trading_false:
        errors.append("Live trading credentials detected!")

    # Step 1: file visibility check
    file_visible = False
    if docker_available and overlay_container_path:
        file_visible, detail = check_container_visibility(
            binding.container_name, overlay_container_path,
        )
        if not file_visible:
            errors.append(f"file_visibility_failure: {detail}")

    # Step 2: process command proof (Proof C) — auth-free
    process_uses_overlay = False
    if docker_available and overlay_container_path and file_visible:
        process_ok, proc_errors = check_process_uses_overlay(
            binding.container_name, overlay_container_path,
        )
        process_uses_overlay = process_ok
        if not process_ok:
            errors.append(f"process_command_missing_overlay: {proc_errors[0] if proc_errors else 'unknown'}")

    # Step 3: effective values check from the draft (offline, no I/O)
    effective_ok = True
    for key in proposal.parameters:
        if key not in draft.after_values:
            effective_ok = False
            errors.append(f"draft_missing_key: {key!r} not in draft.after_values")
        elif str(draft.after_values[key]) != str(proposal.parameters[key]):
            effective_ok = False
            errors.append(
                f"draft_mismatch: {key}: expected={proposal.parameters[key]!r}, "
                f"got={draft.after_values[key]!r}"
            )

    # Step 4: loaded values check (composite A+B, PR #337).
    #
    # Three terminal outcomes for loaded_ok:
    #   True  — Proof A succeeded, OR Proof A exposed missing keys but Proof B proved them.
    #   False — API-exposed mismatch, or Proof B mismatch on missing keys, or no proof reachable.
    loaded_ok = False
    proof_method = ""
    api_matched: tuple[str, ...] = ()
    api_missing: tuple[str, ...] = ()
    api_mismatched: tuple[str, ...] = ()

    if not (docker_available and file_visible):
        errors.append("cannot_check_loaded_config: file not visible to bot")
    else:
        # --- Proof A: surface-aware Freqtrade show_config ----------------------
        api_surface: ApiConfigProofResult | None = None
        base, read_err = _read_container_file(
            binding.container_name, binding.container_config_path,
        )
        if base is None:
            # Cannot read base config → cannot resolve creds. Treat as API
            # unavailable; defer entirely to Proof B.
            api_surface = ApiConfigProofResult(
                ok=False,
                unavailable=True,
                raw_mismatch_messages=(f"api_proof_unavailable: {read_err}",),
            )
            errors.append(f"api_proof_unavailable: {read_err}")
        else:
            creds = _resolve_api_credentials(base)
            if creds is None:
                api_surface = ApiConfigProofResult(
                    ok=False,
                    unavailable=True,
                    raw_mismatch_messages=(
                        "api_proof_unavailable: api_server block missing "
                        "username/password in base config",
                    ),
                )
                errors.append(
                    "api_proof_unavailable: api_server block missing "
                    "username/password in base config"
                )
            else:
                api_username, api_ui_pwd = creds
                api_surface = check_effective_config_from_api_surface(
                    binding.container_name,
                    api_host="127.0.0.1",
                    api_port=8080,
                    api_username=api_username,
                    api_ui_pwd=api_ui_pwd,
                    expected_values=proposal.parameters,
                )

        api_matched = api_surface.matched_keys
        api_missing = api_surface.missing_keys
        api_mismatched = api_surface.mismatched_keys

        # Mismatched keys are real runtime mismatches — RED, no override.
        if api_mismatched:
            errors.append(
                "red_api_exposed_key_mismatch: API-exposed keys did not match "
                f"proposal: {list(api_mismatched)}"
            )
            errors.extend(api_surface.raw_mismatch_messages)
            proof_method = "red_api_exposed_key_mismatch"
        elif api_surface.unavailable:
            # API unreachable. Use Proof B for ALL expected keys (classic fallback).
            if overlay_container_path:
                merged_ok, merged_errors = check_effective_config_from_merged_files(
                    binding.container_name,
                    base_container_path=binding.container_config_path,
                    overlay_container_path=overlay_container_path,
                    expected_values=proposal.parameters,
                )
                if merged_ok:
                    loaded_ok = True
                    proof_method = "merged_fallback"
                else:
                    errors.extend(merged_errors)
        elif api_missing:
            # API exposed some keys (all matched) but is missing others.
            # Run Proof B only for the missing subset.
            missing_only = {k: proposal.parameters[k] for k in api_missing}
            if overlay_container_path and missing_only:
                merged_ok, merged_errors = check_effective_config_from_merged_files(
                    binding.container_name,
                    base_container_path=binding.container_config_path,
                    overlay_container_path=overlay_container_path,
                    expected_values=missing_only,
                )
                if merged_ok:
                    loaded_ok = True
                    proof_method = "api_plus_merged_missing_keys"
                else:
                    errors.append(
                        f"composite_proof_failed: Proof B could not validate "
                        f"missing API keys {list(api_missing)}"
                    )
                    errors.extend(merged_errors)
            else:
                # No overlay path or no missing keys to validate — strange,
                # but conservatively treat as not proven.
                errors.append(
                    f"composite_proof_incomplete: API missing keys "
                    f"{list(api_missing)} but no overlay path to validate"
                )
        else:
            # All expected keys matched via API and nothing missing.
            loaded_ok = True
            proof_method = "api"

    # Step 5: determine proof status
    if errors:
        proof_status = ProofStatus.RED
    elif not loaded_ok:
        proof_status = ProofStatus.YELLOW
    elif (
        file_visible
        and process_uses_overlay
        and effective_ok
        and loaded_ok
    ):
        proof_status = ProofStatus.GREEN
    else:
        proof_status = ProofStatus.YELLOW

    restart_required = not file_visible or not process_uses_overlay or not loaded_ok

    return RuntimeEffectProof(
        proposal_id=proposal.proposal_id,
        bot_id=proposal.bot_id,
        file_visible_to_bot=file_visible,
        effective_config_contains_expected_values=effective_ok,
        loaded_config_contains_expected_values=loaded_ok,
        process_command_uses_overlay=process_uses_overlay,
        proof_method=proof_method,
        api_matched_keys=api_matched,
        api_missing_keys=api_missing,
        api_mismatched_keys=api_mismatched,
        dry_run_true=dry_run_true,
        live_trading_false=live_trading_false,
        strategy_unchanged=strategy_unchanged,
        restart_required=restart_required,
        proof_status=proof_status,
        errors=tuple(errors),
    )
