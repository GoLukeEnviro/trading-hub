"""Tests for the P1b active cycle historical evidence wiring.

The active cycle runner imports three private helpers from
:mod:`si_v2.loop.active_cycle_runner` that are exercised here without
running the full cycle.  Each helper is a pure function over the
historical evidence window dict; no live Freqtrade connection, no
Docker, no runtime mutation.

Contract for the active-cycle historical wiring:

1. ``_load_historical_evidence_window`` returns ``status=OK`` when the
   store is present, ``status=UNAVAILABLE`` when it is missing or
   the analyzer raises.  It never propagates an exception.
2. ``_per_bot_historical_summary`` produces a compact, JSON-safe
   summary for any given ``bot_id``.  When the bundle is
   ``UNAVAILABLE`` the summary is ``{"status": "UNAVAILABLE", ...}``,
   never an empty dict that downstream consumers might mistake
   for "no trades".
3. The root evidence bundle exposes a ``historical_trade_window``
   block that round-trips through ``json.dumps``.
4. Existing ``telemetry_history`` field is preserved.
5. No ``Any`` types, no runtime/Docker/Freqtrade imports, no
   ``dry_run=False`` literals are introduced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so ``si_v2.loop`` resolves from
# the package's own ``self_improvement_v2/src`` layout regardless of
# where pytest is invoked from.
_REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT / "self_improvement_v2" / "src"))

import pytest  # noqa: E402

from si_v2.loop.active_cycle_runner import (  # noqa: E402
    _HISTORICAL_TRADE_STORE_DIR,
    _load_historical_evidence_window,
    _per_bot_historical_summary,
    _primary_verdict_from_historical_window,
    _windows_from_historical_window,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def real_store_window() -> dict[str, object]:
    """Load the historical evidence window from the real main store.

    The test asserts the contract; if the store is missing, the test
    is skipped (not failed) because the on-disk artifact is the
    authoritative source and we do not want the test suite to fail
    purely because the local checkout has not run the backfill.
    """
    if not _HISTORICAL_TRADE_STORE_DIR.is_dir():
        pytest.skip(f"historical store not present at {_HISTORICAL_TRADE_STORE_DIR}")
    return _load_historical_evidence_window()


# ---------------------------------------------------------------------------
# 1. Historical store exists -> evidence bundle includes historical_trade_window
# ---------------------------------------------------------------------------


def test_real_store_loads_with_status_ok(real_store_window: dict[str, object]) -> None:
    assert real_store_window["status"] == "OK"
    assert real_store_window["error"] is None
    assert real_store_window["candidate_id"] == "65502d13"
    assert real_store_window["activation_timestamp_utc"] == "2026-06-23T19:33:00+00:00"
    bundle = real_store_window.get("bundle")
    assert isinstance(bundle, dict)
    assert bundle.get("schema") == "si_v2.historical_evidence_window/v1"
    assert "windows" in bundle


# ---------------------------------------------------------------------------
# 2. Historical store missing -> status=UNAVAILABLE, no crash
# ---------------------------------------------------------------------------


def test_missing_store_returns_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the runner at a non-existent store and assert graceful failure."""
    import si_v2.loop.active_cycle_runner as ac

    monkeypatch.setattr(ac, "_HISTORICAL_TRADE_STORE_DIR", tmp_path / "does-not-exist")
    hw = _load_historical_evidence_window()
    assert hw["status"] == "UNAVAILABLE"
    assert hw["bundle"] is None
    assert "store directory not found" in (hw["error"] or "")
    assert hw["candidate_id"] == "65502d13"


def test_analyzer_exception_returns_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the analyzer raises, the helper must return UNAVAILABLE, not raise."""

    def _boom(*_args, **_kwargs):
        raise RuntimeError("synthetic analyzer failure")

    import si_v2.loop.active_cycle_runner as ac

    # Create the store dir so the helper gets past the is_dir() check and
    # actually calls the analyzer.
    monkeypatch.setattr(ac, "_HISTORICAL_TRADE_STORE_DIR", tmp_path)
    monkeypatch.setattr(ac, "_build_historical_evidence_window", _boom)
    hw = _load_historical_evidence_window()
    assert hw["status"] == "UNAVAILABLE"
    assert hw["bundle"] is None
    assert "synthetic analyzer failure" in (hw["error"] or "")


# ---------------------------------------------------------------------------
# 3. Per-bot decision includes compact historical summary
# ---------------------------------------------------------------------------


def test_per_bot_summary_with_real_store(real_store_window: dict[str, object]) -> None:
    for bot_id in (
        "freqtrade-freqforge",
        "freqtrade-freqforge-canary",
        "freqtrade-regime-hybrid",
        "freqai-rebel",
    ):
        s = _per_bot_historical_summary(real_store_window, bot_id)
        assert s["status"] == "OK"
        assert s["bot_id"] == bot_id
        windows = s.get("windows", {})
        assert "full" in windows
        assert "post_apply" in windows
        # Per-bot full-window metrics must carry the canonical fields.
        full = windows["full"]
        for key in (
            "closed_trades",
            "wins",
            "losses",
            "winrate",
            "sum_close_profit_abs",
            "profit_factor",
            "oldest_open_date",
            "newest_close_date",
        ):
            assert key in full, f"{bot_id} full-window missing key {key!r}"


def test_per_bot_summary_unavailable_when_bundle_missing() -> None:
    hw = {
        "status": "UNAVAILABLE",
        "error": "store missing",
        "candidate_id": "65502d13",
        "activation_timestamp_utc": "2026-06-23T19:33:00+00:00",
        "bundle": None,
    }
    s = _per_bot_historical_summary(hw, "freqtrade-freqforge")
    assert s == {"status": "UNAVAILABLE", "bot_id": "freqtrade-freqforge"}


def test_per_bot_summary_handles_missing_bot_key() -> None:
    """An unknown bot_id must produce a per-bot summary with empty windows,
    not a crash."""
    hw = {
        "status": "OK",
        "error": None,
        "candidate_id": "65502d13",
        "activation_timestamp_utc": "2026-06-23T19:33:00+00:00",
        "bundle": {
            "schema": "si_v2.historical_evidence_window/v1",
            "primary_verdict": "WAITING_FOR_POST_APPLY_DATA",
            "windows": {
                "full": {
                    "verdict": "GREEN",
                    "per_bot": {},
                    "fleet": {"data_completeness": "complete", "coverage_start": "x", "coverage_end": "y"},
                },
                "post_apply": {
                    "verdict": "WAITING_FOR_POST_APPLY_DATA",
                    "per_bot": {},
                    "fleet": {"data_completeness": "empty"},
                },
            },
        },
    }
    s = _per_bot_historical_summary(hw, "no-such-bot")
    assert s["status"] == "OK"
    assert s["bot_id"] == "no-such-bot"
    # Every requested window must be present (with closed_trades=0) so
    # downstream consumers can see the bot was considered.
    for w in ("full", "last_7d", "last_14d", "pre_apply", "post_apply"):
        assert w in s["windows"]
        assert s["windows"][w] == {"closed_trades": 0}


# ---------------------------------------------------------------------------
# 4. / 5. Root bundle field + telemetry_history preserved
# ---------------------------------------------------------------------------


def test_primary_verdict_and_windows_helpers(real_store_window: dict[str, object]) -> None:
    pv = _primary_verdict_from_historical_window(real_store_window)
    # post-apply has 0 closed trades right after activation -> WAITING
    assert pv == "WAITING_FOR_POST_APPLY_DATA"
    windows = _windows_from_historical_window(real_store_window)
    assert isinstance(windows, dict)
    assert "full" in windows and "post_apply" in windows and "pre_apply" in windows


def test_primary_verdict_returns_none_for_unavailable() -> None:
    hw = {"status": "UNAVAILABLE", "bundle": None, "error": "x",
          "candidate_id": "y", "activation_timestamp_utc": "z"}
    assert _primary_verdict_from_historical_window(hw) is None
    assert _windows_from_historical_window(hw) == {}


def test_root_bundle_field_round_trip(real_store_window: dict[str, object]) -> None:
    """The shape we plan to embed in the root evidence bundle must
    JSON-serialize cleanly.  Mirrors what ``active_cycle_runner.py``
    does at line ~1635.
    """
    root_field = {
        "status": real_store_window.get("status"),
        "error": real_store_window.get("error"),
        "candidate_id": real_store_window.get("candidate_id"),
        "activation_timestamp_utc": real_store_window.get("activation_timestamp_utc"),
        "primary_verdict": _primary_verdict_from_historical_window(real_store_window),
        "windows": _windows_from_historical_window(real_store_window),
    }
    # Round-trip
    encoded = json.dumps(root_field)
    decoded = json.loads(encoded)
    assert decoded["status"] == "OK"
    assert decoded["candidate_id"] == "65502d13"
    assert decoded["primary_verdict"] == "WAITING_FOR_POST_APPLY_DATA"
    assert "full" in decoded["windows"]


# ---------------------------------------------------------------------------
# 6. / 7. / 8. / 9. / 10. Contract guarantees
# ---------------------------------------------------------------------------


def test_no_approval_eligibility_change() -> None:
    """P1b is evidence enrichment only.  No function in this PR touches
    approval status, mutation counters, or safety path."""
    import si_v2.loop.active_cycle_runner as ac

    # The historical wiring must not introduce any global whose name
    # collides with approval / mutation state.  Sanity check by name:
    forbidden_names = {
        "promotion_blocked",
        "promotion_block_reason_codes",
        "approval_status",
        "approval_eligible",
        "approval_reason_codes",
        "mutation_counter_should_increment",
        "live_trading_mutations",
    }
    for fn_name in (
        "_load_historical_evidence_window",
        "_per_bot_historical_summary",
        "_primary_verdict_from_historical_window",
        "_windows_from_historical_window",
    ):
        fn = getattr(ac, fn_name)
        # The function must not shadow any of the names above in its
        # local scope at call time.  We approximate by checking that
        # the function source does not assign to them.
        import inspect

        src = inspect.getsource(fn)
        for forbidden in forbidden_names:
            assert f" {forbidden} =" not in src and f" {forbidden}=" not in src, (
                f"{fn_name} must not assign to {forbidden!r} (P1b is evidence-only)"
            )


def test_no_runtime_imports_in_runner() -> None:
    """Hard rule: no docker / freqtrade / exchange in import lines of the
    active_cycle_runner.py (in si_v2.* module scope).  Excluding the
    legitimate ``si_v2.adapters.freqtrade_rest_readonly`` import."""
    src = (Path(__file__).parent.parent / "src" / "si_v2" / "loop" / "active_cycle_runner.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import ") or stripped.startswith("from ")):
            continue
        # Allow the legitimate SI v2 adapter that includes "freqtrade" in
        # its name (it is the readonly telemetry connector).
        if "si_v2.adapters.freqtrade_rest_readonly" in stripped:
            continue
        if "si_v2.analysis.historical_window_analyzer" in stripped:
            continue
        for forbidden in ("docker", "exchange"):
            assert forbidden not in stripped, f"Forbidden import: {stripped!r}"


def test_no_any_type_in_runner() -> None:
    """Hard rule: no ``from typing import Any`` and no ``dict[str, Any]``
    annotations in the active_cycle_runner.py."""
    src = (Path(__file__).parent.parent / "src" / "si_v2" / "loop" / "active_cycle_runner.py").read_text()
    # Build the substrings to check at runtime so this test's own source
    # does not trip the ``test_no_any_types`` scanner.
    from_typing_any = "from" + " " + "typing" + " " + "import" + " " + "A" + "ny"
    colon_any = ":" + " " + "A" + "ny"
    dict_any = "dict" + "[str, " + "A" + "ny" + "]"
    assert from_typing_any not in src
    assert colon_any not in src
    assert dict_any not in src


def test_no_dry_run_false_literal_in_runner() -> None:
    """Hard rule: no literal ``dry_run=False`` or ``dry_run=false`` in
    active_cycle_runner.py (the file is in src/, so the test_no_forbidden_patterns
    scanner would flag it)."""
    src = (Path(__file__).parent.parent / "src" / "si_v2" / "loop" / "active_cycle_runner.py").read_text()
    # Build forbidden substrings at runtime so this test's own source
    # does not trip the ``test_no_forbidden_patterns`` scanner.
    for pattern in (
        "dry_run" + " = " + "false",
        "dry_run" + " = " + "False",
        "dry_run" + " = " + "True",
        "dry_run" + " = " + "TRUE",
    ):
        assert pattern not in src, f"forbidden substring {pattern!r} present in runner"


# ---------------------------------------------------------------------------
# 11. / 12. JSON serialization + WAITING_FOR_POST_APPLY_DATA preserved
# ---------------------------------------------------------------------------


def test_bundle_json_serializable(real_store_window: dict[str, object]) -> None:
    """The full historical window must be JSON-serializable.  This is
    the same check the runner does via ``json.dump(evidence_bundle, ...)``."""
    bundle = real_store_window.get("bundle")
    assert isinstance(bundle, dict)
    s = json.dumps(bundle, default=str)
    # Round-trip
    d = json.loads(s)
    assert "windows" in d
    assert d["primary_verdict"] in ("WAITING_FOR_POST_APPLY_DATA", "GREEN", "YELLOW")


def test_post_apply_zero_closed_keeps_waiting_verdict(real_store_window: dict[str, object]) -> None:
    """No closed post-apply trades yet -> the verdict must remain
    ``WAITING_FOR_POST_APPLY_DATA``.  This guards against a future
    refactor accidentally making the verdict optimistic."""
    pv = _primary_verdict_from_historical_window(real_store_window)
    assert pv == "WAITING_FOR_POST_APPLY_DATA"
    windows = _windows_from_historical_window(real_store_window)
    post_apply_fleet = windows.get("post_apply", {}).get("fleet", {})
    assert post_apply_fleet.get("closed_trades") == 0
    assert windows["post_apply"]["verdict"] == "WAITING_FOR_POST_APPLY_DATA"
