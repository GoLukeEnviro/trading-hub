#!/usr/bin/env python3
"""LEDGER Integrity Watchdog — Tier-1 Autonomous Monitor.

Prüft bei jedem Lauf:
  1. Source Completeness: aktive Bots ↔ portfolio.sources Schlüssel
  2. Drawdown Threshold: LEDGER drawdown > R2 (3.0%)
  3. Gap & Drift: LIVE_RISK ↔ LEDGER_RISK Equity-Differenz

Bei Findings wird autonom:
  - fleet_risk_state.json mit Audit-Trail-Eintrag ergänzt (idempotent via Signatur)
  - canonical_trading_status_latest.json + canonical-trading-status.md aktualisiert
  - docs/context/ledger-watchdog-<date>.md Report geschrieben
  - Log geschrieben (silent by default; Warnung im Log wenn Finding)

Niemals mutiert:
  - drawdown_state.json (LIVE_RISK)
  - Strategy-/Pairlist-/Risk-Parameter
  - Configs / docker / crontabs
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Pfade (spiegeln observation_common.py, um konsistent zu sein)
REPO_ROOT = Path("/home/hermes/projects/trading")
ORCH_ROOT = Path("/opt/data/profiles/orchestrator")
LEDGER_PATH = REPO_ROOT / "freqtrade" / "shared" / "fleet_risk_state.json"
DRAWDOWN_PATH = ORCH_ROOT / "state" / "drawdown_state.json"
CANONICAL_JSON = REPO_ROOT / "orchestrator" / "reports" / "canonical_trading_status_latest.json"
CANONICAL_MD = REPO_ROOT / "docs" / "state" / "canonical-trading-status.md"
CURRENT_OP_MD = REPO_ROOT / "docs" / "state" / "current-operational-state.md"
CONTEXT_DIR = REPO_ROOT / "docs" / "context"
STATE_FILE = ORCH_ROOT / "state" / "ledger_integrity_watchdog_state.json"
LOG_FILE = ORCH_ROOT / "logs" / "ledger_integrity_watchdog.log"
LOCK_DIR = ORCH_ROOT / "state" / "locks"
LOCK_NAME = "ledger_integrity.lock"
LOCK_STALE_SECONDS = 30 * 60

# Tier-1 Thresholds
R2_DRAWDOWN_THRESHOLD = 0.03  # 3.0%

# Aktive Bots (Ground Truth aus AGENTS.md). Falls canonical das widerspricht,
# wird das in jedem Lauf re-evaluiert — diese Liste ist nur der Fallback.
FALLBACK_ACTIVE_BOTS = {"freqforge", "regime-hybrid", "freqforge-canary", "freqai-rebel"}

LOGGER_NAME = "ledger_integrity_watchdog"


# ---------- Utility ----------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat(timespec="microseconds")


def _short_now() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H-%M-%S")


def _date_str() -> str:
    return _utc_now().strftime("%Y-%m-%d")


def _ensure_dirs() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def _configure_logging() -> logging.Logger:
    _ensure_dirs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")],
        force=True,
    )
    return logging.getLogger(LOGGER_NAME)


def _lock_path() -> Path:
    return LOCK_DIR / LOCK_NAME


def _acquire_lock(logger: logging.Logger) -> dict[str, Any]:
    path = _lock_path()
    try:
        os.mkdir(path)
        (path / "pid").write_text(str(os.getpid()))
        (path / "timestamp").write_text(_iso_now())
        return {"status": "acquired", "lock_taken_over": False}
    except FileExistsError:
        try:
            age = _utc_now().timestamp() - path.stat().st_mtime
        except OSError as exc:
            logger.error("Lock inspection failed: %s", exc)
            return {"status": "error", "exit_code": 1}
        if age <= LOCK_STALE_SECONDS:
            return {"status": "skipped"}
        logger.warning("Taking over stale lock (age=%.0fs)", age)
        shutil.rmtree(path, ignore_errors=True)
        os.mkdir(path)
        (path / "pid").write_text(str(os.getpid()))
        (path / "timestamp").write_text(_iso_now())
        return {"status": "acquired", "lock_taken_over": True}
    except OSError as exc:
        logger.error("Lock acquisition failed: %s", exc)
        return {"status": "error", "exit_code": 1}


def _release_lock(logger: logging.Logger) -> None:
    try:
        shutil.rmtree(_lock_path())
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Lock release failed: %s", exc)


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            json.dump(payload, h, ensure_ascii=False, indent=2)
            h.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as h:
            h.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass


# ---------- Reads ----------

def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open() as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logging.getLogger(LOGGER_NAME).error("Failed to read %s: %s", path, exc)
        return None


def _active_bots_from_canonical() -> set[str] | None:
    """Extrahiere aktive Bot-Namen aus canonical-trading-status.md.

    Greift nach der Active-Fleet-Tabelle. Returnt None wenn Datei fehlt.
    """
    try:
        text = CANONICAL_MD.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    # Suche nach Active-Fleet-Section; bis zur nächsten Section
    match = re.search(r"## Active Fleet\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not match:
        return None
    block = match.group(1)
    bots: set[str] = set()
    for line in block.splitlines():
        # Pipe-Tabellen-Rows, erste Spalte ist Bot-Name
        m = re.match(r"\|\s*([a-z][a-z0-9\-]*)\s*\|", line.strip())
        if m and m.group(1) not in {"bot", "container", "verdict", "classification", "dry-run", "strategy", "state", "match", "file"}:
            bots.add(m.group(1))
    return bots or None


# ---------- Core Checks ----------

def _check_source_completeness(ledger: dict[str, Any], active_bots: set[str]) -> dict[str, Any]:
    sources = ledger.get("portfolio", {}).get("sources", {})
    ledger_keys = set(sources.keys())

    # Mapping-Hypothese: aktive-Bot-Name → möglicher ledger-Key
    alias_map = {
        "freqforge":         {"baseline_v1_freqforge", "freqforge_v1"},
        "regime-hybrid":     {"regime_hybrid_dryrun", "regime_hybrid"},
        "freqforge-canary":  {"freqforge_canary_v1"},
        "freqai-rebel":      {"rebel", "freqai_rebel", "rebel_dryrun", "freqai-rebel"},
    }

    missing: list[dict[str, str]] = []
    for bot in sorted(active_bots):
        candidates = alias_map.get(bot, {bot})
        if not (candidates & ledger_keys):
            # Versuche auch direkten Substring-Match (z.B. "rebel" in key)
            if not any(bot.replace("-", "_") in k or bot.replace("-", "") in k for k in ledger_keys):
                missing.append({"bot": bot, "tried": sorted(candidates)})

    return {
        "active_bots": sorted(active_bots),
        "ledger_keys": sorted(ledger_keys),
        "missing": missing,
        "status": "OK" if not missing else "WARNING",
    }


def _check_drawdown(ledger: dict[str, Any]) -> dict[str, Any]:
    dd = float(ledger.get("portfolio", {}).get("current_drawdown", 0.0))
    threshold = R2_DRAWDOWN_THRESHOLD
    return {
        "current_drawdown": dd,
        "threshold": threshold,
        "exceeds_threshold": dd > threshold,
        "status": "OK" if dd <= threshold else "WARNING",
    }


def _check_live_gap(ledger: dict[str, Any], drawdown: dict[str, Any] | None) -> dict[str, Any]:
    if not drawdown:
        return {"status": "UNKNOWN", "reason": "drawdown_state.json missing or unreadable"}
    live_total = float(drawdown.get("portfolio_current", 0.0))
    ledger_total = float(ledger.get("portfolio", {}).get("current_equity", 0.0))
    delta = live_total - ledger_total
    return {
        "live_total": live_total,
        "ledger_total": ledger_total,
        "delta": delta,
        "status": "OK" if abs(delta) < 1.0 else "INFO",
    }


# ---------- Audit (idempotent via fingerprint) ----------

def _fingerprint(findings: dict[str, Any]) -> str:
    """Stabile Repräsentation der Findings — gleiche Findings → gleiche FP."""
    payload = {
        "missing": sorted([m["bot"] for m in findings["source_completeness"]["missing"]]),
        "dd_exceeds": findings["drawdown"]["exceeds_threshold"],
        "dd_value": round(findings["drawdown"]["current_drawdown"], 6),
        "live_ledger_delta": round(findings["live_gap"].get("delta", 0.0), 2),
    }
    return json.dumps(payload, sort_keys=True)


def _state_load() -> dict[str, Any]:
    s = _read_json(STATE_FILE) or {}
    return {
        "last_run_at": s.get("last_run_at"),
        "last_fingerprint": s.get("last_fingerprint"),
        "last_report_path": s.get("last_report_path"),
        "consecutive_runs_with_finding": int(s.get("consecutive_runs_with_finding", 0)),
    }


def _state_save(state: dict[str, Any]) -> None:
    _atomic_write_json(STATE_FILE, state)


def _append_audit_to_ledger(ledger: dict[str, Any], findings: dict[str, Any], report_path: Path) -> bool:
    """Hängt Audit-Eintrag an ledger._audit[] an, falls nicht schon vorhanden (idempotent).

    Returns True wenn etwas geschrieben wurde.
    """
    fp = _fingerprint(findings)
    audit = ledger.setdefault("_audit", [])
    # Idempotenz: wenn der letzte Eintrag den gleichen Fingerprint hat, skip
    if audit and isinstance(audit[-1], dict) and audit[-1].get("fingerprint") == fp:
        logging.getLogger(LOGGER_NAME).info("Audit-Eintrag bereits vorhanden (idempotent)")
        return False

    missing_bots = [m["bot"] for m in findings["source_completeness"]["missing"]]
    dd_exc = findings["drawdown"]["exceeds_threshold"]
    dd_val = findings["drawdown"]["current_drawdown"]

    severity = "warning"
    impact_parts: list[str] = []
    if missing_bots:
        impact_parts.append(f"missing source_keys: {','.join(missing_bots)}")
    if dd_exc:
        impact_parts.append(f"drawdown {dd_val*100:.2f}% > {R2_DRAWDOWN_THRESHOLD*100:.0f}% R2 threshold")

    entry = {
        "ts": _iso_now(),
        "action": "ledger_integrity_check",
        "fingerprint": fp,
        "finding": " | ".join(impact_parts) or "all checks OK",
        "impact": " | ".join(impact_parts) or "no impact",
        "severity": severity if impact_parts else "info",
        "active_bots": findings["source_completeness"]["active_bots"],
        "ledger_keys": findings["source_completeness"]["ledger_keys"],
        "drawdown_pct": round(dd_val * 100, 4),
        "drawdown_threshold_pct": R2_DRAWDOWN_THRESHOLD * 100,
        "live_ledger_delta": round(findings["live_gap"].get("delta", 0.0), 2),
        "report_path": str(report_path),
        "recommended_action": _recommended_action(findings),
    }
    audit.append(entry)
    return True


def _recommended_action(findings: dict[str, Any]) -> str:
    actions: list[str] = []
    if findings["source_completeness"]["missing"]:
        bots = ", ".join(m["bot"] for m in findings["source_completeness"]["missing"])
        actions.append(f"Tier-2: ledger-collector needs source_key for missing bot(s): {bots}")
    if findings["drawdown"]["exceeds_threshold"]:
        actions.append("Tier-2: drawdown approaching R2 threshold; review fleet_risk_auto_params")
    if not actions:
        return "none — all checks OK"
    return "; ".join(actions)


# ---------- Canonical update ----------

def _update_canonical(findings: dict[str, Any], report_path: Path, appended_audit: bool) -> None:
    """Mutiert canonical JSON + Markdown + current-op-state minimal."""
    canonical = _read_json(CANONICAL_JSON)
    if not canonical:
        logging.getLogger(LOGGER_NAME).warning("Canonical JSON missing — skip update")
        return

    ts = _iso_now()
    ledger = canonical.setdefault("truth_scopes", {}).setdefault("LEDGER_RISK", {})

    # LEDGER note
    missing_bots = [m["bot"] for m in findings["source_completeness"]["missing"]]
    dd_exc = findings["drawdown"]["exceeds_threshold"]
    dd_val = findings["drawdown"]["current_drawdown"]

    note_parts: list[str] = ["Secondary ledger / historical view."]
    if appended_audit:
        note_parts.append(
            f"Watchdog @ {ts}: missing source_keys={missing_bots or 'none'}, "
            f"drawdown={dd_val*100:.2f}% ({'above' if dd_exc else 'below'} R2 {R2_DRAWDOWN_THRESHOLD*100:.0f}%)."
        )
    else:
        note_parts.append(f"Watchdog @ {ts}: no new findings (idempotent).")
    ledger["note"] = " ".join(note_parts)

    # Timestamp
    ledger["timestamp"] = ts
    canonical.setdefault("source_timestamps", {})["fleet_risk_last_update"] = ts
    canonical["generated_at"] = ts

    # Reporting Health notes: immer GENAU EIN Watchdog-Eintrag, idempotent aktualisiert
    rh = canonical.setdefault("truth_scopes", {}).setdefault("REPORTING_HEALTH", {})
    notes: list[str] = list(rh.get("notes", []))
    watchdog_note = f"ledger-integrity-watchdog @ {ts[:19]} — {('ISSUES: ' + ', '.join(missing_bots) + ' | drawdown > R2') if (missing_bots or dd_exc) else 'OK'}"
    # Filter existierende Watchdog-Notes raus, hänge die neue vorne an
    notes = [n for n in notes if not n.startswith("ledger-integrity-watchdog @")]
    notes.insert(0, watchdog_note)
    rh["notes"] = notes[:8]

    # Auditability: idempotent — wird nur in `_update_canonical` neu berechnet,
    # wenn auch ein neuer Audit-Eintrag in ledger geschrieben wurde. Sonst unverändert lassen.
    if appended_audit:
        auditability = canonical.get("scores", {}).get("auditability_score", 80)
        if missing_bots and auditability > 75:
            auditability = max(75, auditability - 1)
        if dd_exc and auditability > 75:
            auditability = max(75, auditability - 1)
        canonical.setdefault("scores", {})["auditability_score"] = auditability
    # Overall re-evaluieren
    s = canonical.get("scores", {})
    canonical.setdefault("scores", {})["overall_operational_score"] = round(
        (s.get("runtime_health_score", 92)
         + s.get("reporting_health_score", 73)
         + s.get("data_quality_score", 84)
         + s.get("auditability_score", 80)) / 4
    )

    _atomic_write_json(CANONICAL_JSON, canonical)

    # Markdown minimal: generated_at + LEDGER-RISK Note-Zeile
    try:
        cm = CANONICAL_MD.read_text(encoding="utf-8")
        cm = re.sub(r"^Generated at: .+$",
                    f"Generated at: {ts}",
                    cm, count=1, flags=re.MULTILINE)
        # LEDGER_RISK Zeile in Truth Scopes — wir generieren sauber neu
        cm = re.sub(
            r"\| LEDGER_RISK \| WARNING \| [^\|]+ \| [^\|]+\|",
            f"| LEDGER_RISK | WARNING | {ts} | {' '.join(note_parts)} |",
            cm, count=1
        )
        _atomic_write_text(CANONICAL_MD, cm)
    except FileNotFoundError:
        pass

    # current-op-state.md: generated_at refresh + Note-Hinweis
    try:
        co = CURRENT_OP_MD.read_text(encoding="utf-8")
        co = re.sub(r"^Generated at: .+$",
                    f"Generated at: {ts}",
                    co, count=1, flags=re.MULTILINE)
        if "ledger-integrity-watchdog" not in co:
            addition = (
                f"\n- ledger-integrity-watchdog last run: {ts} — "
                f"{'ISSUES: ' + ', '.join(missing_bots) + ' | drawdown > R2' if (missing_bots or dd_exc) else 'OK'}.\n"
            )
            co = co.replace("## Notes\n\n", "## Notes\n\n" + addition, 1)
        _atomic_write_text(CURRENT_OP_MD, co)
    except FileNotFoundError:
        pass


# ---------- Report ----------

def _write_report(findings: dict[str, Any], state: dict[str, Any], appended_audit: bool) -> Path:
    date = _date_str()
    stamp = _short_now()
    report_path = CONTEXT_DIR / f"ledger-watchdog-{date}.md"
    # Idempotenz: gleicher Tag → gleiche Datei (überschrieben)
    # Damit hat jeder Tag höchstens 1 Report; Run-Details sind im Body + Log.

    missing_bots = [m["bot"] for m in findings["source_completeness"]["missing"]]
    dd_exc = findings["drawdown"]["exceeds_threshold"]
    dd_val = findings["drawdown"]["current_drawdown"]

    body = f"""# Ledger Integrity Watchdog Run — {date} {stamp}

## Ergebnis

| Check | Status | Detail |
|---|---|---|
| Sources Check | {'OK' if not missing_bots else 'WARNING (Missing: ' + ', '.join(missing_bots) + ')'} | {len(findings['source_completeness']['active_bots'])} active bots, {len(findings['source_completeness']['ledger_keys'])} ledger keys |
| Drawdown Check | {'OK' if not dd_exc else f'WARNING ({dd_val*100:.2f}% > {R2_DRAWDOWN_THRESHOLD*100:.0f}%)'} | LEDGER current_drawdown = {dd_val*100:.4f}% |
| Live Gap | {findings['live_gap'].get('status','UNKNOWN')} | Δ = {findings['live_gap'].get('delta','?')} USDT (LIVE {findings['live_gap'].get('live_total','?')} vs LEDGER {findings['live_gap'].get('ledger_total','?')}) |

## Aktionen ausgeführt

- {'Audit-Eintrag in `fleet_risk_state.json:_audit[]` angehängt' if appended_audit else 'Idempotent: kein neuer Audit-Eintrag (gleiche Findings wie letzter Run)'}
- Canonical Status aktualisiert (JSON + MD + current-op-state)
- {'Report geschrieben: ' + str(report_path.relative_to(REPO_ROOT)) if appended_audit else 'Report aktualisiert: ' + str(report_path.relative_to(REPO_ROOT))}

## Daten-Snapshot

```
LEDGER sources : {findings['source_completeness']['ledger_keys']}
Active bots    : {findings['source_completeness']['active_bots']}
Missing        : {missing_bots or 'none'}
Drawdown       : {dd_val*100:.4f}% (threshold {R2_DRAWDOWN_THRESHOLD*100:.0f}%)
LIVE-LEDGER Δ  : {findings['live_gap'].get('delta', '?')} USDT
```

## Empfohlener nächster Schritt

{_recommended_action(findings)}

## Tier-Eskalation

"""
    if missing_bots or dd_exc:
        body += f"""- **Tier 2 erforderlich** für Source-Vervollständigung
- Begründung: {'fehlende ledger-Key(s) verzerren aggregierte Equity' if missing_bots else ''} {'Drawdown überschreitet R2-Threshold' if dd_exc else ''}
"""
    else:
        body += "- Keine Eskalation nötig — alle Checks OK\n"

    body += f"""
## Meta
- Run timestamp: {_iso_now()}
- Fingerprint: {_fingerprint(findings)}
- Log: {LOG_FILE}
- State: {STATE_FILE}
"""
    _atomic_write_text(report_path, body)
    return report_path


# ---------- Main ----------

def run_watchdog() -> dict[str, Any]:
    logger = _configure_logging()
    logger.info("Watchdog started")

    lock_state = _acquire_lock(logger)
    if lock_state.get("status") == "skipped":
        logger.info("Another watchdog instance active; skipping")
        return {"status": "skipped", "exit_code": 0}
    if lock_state.get("status") == "error":
        return {"status": "error", "exit_code": 1}

    try:
        # Reads
        ledger = _read_json(LEDGER_PATH)
        drawdown = _read_json(DRAWDOWN_PATH)
        if not ledger:
            logger.error("LEDGER unreadable; cannot proceed")
            return {"status": "error", "exit_code": 2}

        # Active bots
        active_bots = _active_bots_from_canonical() or FALLBACK_ACTIVE_BOTS

        # Checks
        findings = {
            "source_completeness": _check_source_completeness(ledger, active_bots),
            "drawdown": _check_drawdown(ledger),
            "live_gap": _check_live_gap(ledger, drawdown),
        }

        # Idempotenz
        state = _state_load()
        fp = _fingerprint(findings)
        is_new = (fp != state.get("last_fingerprint"))

        # Audit
        appended = _append_audit_to_ledger(ledger, findings, Path("(see report)")) if is_new else False
        if appended:
            # Speichere ledger (nur _audit[] hat sich geändert)
            _atomic_write_json(LEDGER_PATH, ledger)
            logger.warning("Audit-Trail in fleet_risk_state.json:_audit[] ergänzt (fp=%s)", fp[:32])
        else:
            logger.info("Idempotent: identische Findings wie letzter Run — kein Audit-Eintrag")

        # Canonical update (auch idempotent — es ist explizit so gebaut, dass 'no new findings' geloggt wird)
        # Aber: Timestamp refreshen ist OK und sinnvoll
        report_path = _write_report(findings, state, is_new and appended)
        # Falls appended False aber fp neu, trotzdem report schreiben (für Transparenz)
        if not is_new:
            report_path = _write_report(findings, state, False)

        # Update report_path in ledger audit falls appended
        if appended and ledger.get("_audit"):
            ledger["_audit"][-1]["report_path"] = str(report_path)
            _atomic_write_json(LEDGER_PATH, ledger)

        _update_canonical(findings, report_path, appended)

        # State speichern
        state["last_run_at"] = _iso_now()
        state["last_fingerprint"] = fp
        state["last_report_path"] = str(report_path)
        state["consecutive_runs_with_finding"] = (
            state.get("consecutive_runs_with_finding", 0) + 1 if (findings["source_completeness"]["missing"] or findings["drawdown"]["exceeds_threshold"]) else 0
        )
        _state_save(state)

        missing = len(findings["source_completeness"]["missing"])
        dd_exc = findings["drawdown"]["exceeds_threshold"]
        logger.info("Run complete: missing=%d, dd_exceeds=%s, is_new=%s, appended=%s",
                    missing, dd_exc, is_new, appended)
        return {
            "status": "completed",
            "exit_code": 0,
            "timestamp": _iso_now(),
            "findings": findings,
            "appended_audit": appended,
            "report_path": str(report_path),
        }
    except Exception as exc:
        logger.exception("Watchdog internal error: %s", exc)
        return {"status": "error", "exit_code": 1, "error": str(exc)}
    finally:
        _release_lock(logger)


def main() -> int:
    parser = argparse.ArgumentParser(description="LEDGER Integrity Watchdog")
    parser.add_argument("--once", action="store_true", help="Run single check (default behavior)")
    args = parser.parse_args()
    result = run_watchdog()
    # stdout: kompakte Zusammenfassung (silent-by-default für Cron, aber sichtbar bei manuellem Run)
    if result.get("status") == "completed":
        f = result.get("findings", {})
        missing = [m["bot"] for m in f.get("source_completeness", {}).get("missing", [])]
        dd = f.get("drawdown", {})
        gap = f.get("live_gap", {})
        print(f"LEDGER Integrity Watchdog — Run {_iso_now()}")
        print(f"  Sources: {'OK' if not missing else f'WARNING missing={missing}'}")
        dd_pct = dd.get('current_drawdown', 0) * 100
        print(f"  Drawdown: {'OK' if not dd.get('exceeds_threshold') else f'WARNING {dd_pct:.2f}% > {R2_DRAWDOWN_THRESHOLD*100:.0f}%'}")
        print(f"  Live Gap: {gap.get('status','?')} (Δ={gap.get('delta','?')} USDT)")
        print(f"  Audit appended: {result.get('appended_audit')}")
        print(f"  Report: {result.get('report_path')}")
    else:
        print(f"Watchdog {result.get('status')}: {result}")
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
