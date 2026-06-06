#!/opt/hermes/.venv/bin/python3
"""fleet_risk_auto_params.py — Auto Parameter Adjuster v1.0

Reads fleet_risk_state.json + consec_loss_state.json and dynamically
adjusts trading parameters based on fleet risk metrics.

Rules:
  R1: Consecutive losses > 3 → MOT = max(1, current-2) for ALL bots
  R2: Drawdown > 2% → Halve stakes (round up)
  R3: Drawdown > 5% → Set MOT=0 for ALL bots (emergency pause)
  R4: Drawdown < 1% AND consec losses < 2 → Restore baseline MOT + stakes
  R5: Consecutive losses > 6 → Set CONFIDENCE_MIN to 0.75 for 24h
  R6: Fleet PnL > +5% → Increase stakes by 25% (profit mode)

Runs as cron job. Advisory only — no forced trades.

Usage:
  /opt/hermes/.venv/bin/python3 fleet_risk_auto_params.py
  --dry-run : print actions without executing
"""

import json, os, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = "/home/hermes/projects/trading"
STATE_DIR = Path(BASE) / "orchestrator/state/auto_params"
HEALTH_FILE = STATE_DIR / "auto_params_health.json"
ACTION_LOG = STATE_DIR / "auto_params_actions.jsonl"

FLEET_RISK_FILE = Path(BASE) / "freqtrade/shared/fleet_risk_state.json"
CONSEC_STATE_FILE = Path(BASE) / "orchestrator/state/consec_loss_state.json"
SIGNAL_CONFIDENCE_FILE = Path(BASE) / "orchestrator/state/signal_confidence_adjust.json"

# Baseline configs
BASELINE_CONFIGS = {
    "trading-freqtrade-freqforge-1": {"mot": 5, "stake": 100, "config_host": "/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json",
                            "config_container": "/freqtrade/config/config_freqforge_dryrun.json"},
    "trading-freqtrade-freqforge-canary-1": {"mot": 3, "stake": 50, "config_host": "/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json",
                                    "config_container": "/freqtrade/config/config_canary_dryrun.json"},
    "trading-freqtrade-regime-hybrid-1": {"mot": 5, "stake": 50, "config_host": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json",
                                 "config_container": "/freqtrade/config/config_regime_hybrid_dryrun.json"},
    "trading-freqai-rebel-1": {"mot": 2, "stake": 50, "config_host": None,
                      "config_container": "/freqtrade/user_data/config.json"},
}

TOTAL_CAPITAL = 10000.0


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] [auto-params] {msg}")


def load_json(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except: return {}


def write_config(container: str, info: dict, cfg: dict) -> bool:
    """Write config to a bot (host path or docker exec)."""
    cfg_json = json.dumps(cfg, indent=4)
    host_path = info.get("config_host")
    if host_path and os.path.exists(host_path):
        try:
            with open(host_path, "w") as f:
                f.write(cfg_json + "\n")
            log(f"  Written: {host_path}")
            return True
        except Exception as e:
            log(f"  ERROR writing {host_path}: {e}")
            return False
    # Docker exec fallback
    container_path = info.get("config_container", "")
    try:
        escaped = cfg_json.replace("'", "'\\''")
        r = subprocess.run(
            ["docker", "exec", container, "bash", "-lc",
             f"tmp=$(mktemp {container_path}.tmp.XXXXXX) && printf '%s\\n' '{escaped}' > \"$tmp\" && chmod 664 \"$tmp\" && mv \"$tmp\" {container_path}"],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            log(f"  Written: {container}:{container_path}")
            return True
        log(f"  ERROR writing {container}:{container_path}: {r.stderr.strip()}")
        return False
    except Exception as e:
        log(f"  ERROR: {e}")
        return False


def read_bot_config(container: str, info: dict) -> dict | None:
    """Read current config from a bot."""
    host_path = info.get("config_host")
    if host_path and os.path.exists(host_path):
        try:
            with open(host_path) as f:
                return json.load(f)
        except: pass
    container_path = info.get("config_container", "")
    try:
        r = subprocess.run(["docker", "exec", container, "cat", container_path],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return json.loads(r.stdout)
    except: pass
    return None


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    now = datetime.now(timezone.utc)

    fleet = load_json(FLEET_RISK_FILE)
    consec = load_json(CONSEC_STATE_FILE)

    portfolio = fleet.get("portfolio", {})
    drawdown_pct = portfolio.get("current_drawdown", 0) * 100  # convert to percentage
    consec_losses = consec.get("consecutive_losses", 0)
    fleet_pnl = sum(
        s.get("current_equity", 0) - s.get("peak_equity", 0)
        for s in portfolio.get("sources", {}).values()
    )

    log(f"Drawdown: {drawdown_pct:.2f}% | Consec losses: {consec_losses} | Fleet PnL: {fleet_pnl:+.2f}")

    actions = []
    rules_fired = []

    # ── R4: Recovery check first ──
    recovery_mode = drawdown_pct < 1.0 and consec_losses < 2
    if recovery_mode:
        log("R4: Recovery conditions met — restoring baselines")
        rules_fired.append("R4")

    # ── R3: Emergency pause ──
    if drawdown_pct > 5.0:
        log(f"R3: CRITICAL drawdown {drawdown_pct:.1f}% > 5% — pausing ALL bots")
        rules_fired.append("R3")
        for container, info in BASELINE_CONFIGS.items():
            cfg = read_bot_config(container, info)
            if cfg is None: continue
            if cfg.get("max_open_trades") != 0:
                if dry_run:
                    log(f"  DRY-RUN: would set {container} MOT=0 (emergency pause)")
                    continue
                cfg["max_open_trades"] = 0
                if write_config(container, info, cfg):
                    subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
                    log(f"  EMERGENCY PAUSE: {container} set MOT=0")
                    actions.append(f"emergency_pause:{container}")
        if not dry_run:
            with open(str(STATE_DIR / "emergency_pause.json"), "w") as f:
                json.dump({"paused_at": now.isoformat(), "reason": f"drawdown {drawdown_pct:.1f}%"}, f)
        return 1

    # ── R5: Extreme consec loss ──
    if consec_losses > 6:
        log(f"R5: {consec_losses} consecutive losses — raising confidence threshold to 0.75")
        rules_fired.append("R5")
        expires = (now + timedelta(hours=24)).isoformat()
        adj = {"min_confidence": 0.75, "reason": f"Auto: {consec_losses} consec losses",
               "expires": expires}
        if not dry_run:
            with open(SIGNAL_CONFIDENCE_FILE, "w") as f:
                json.dump(adj, f, indent=2)
            log(f"  Confidence threshold raised to 0.75 until {expires[:16]}")
            actions.append(f"confidence_raised:0.75")

    # ── R1: Consecutive losses > 3 ──
    if consec_losses > 3:
        log(f"R1: {consec_losses} consecutive losses — reducing MOT for all bots")
        rules_fired.append("R1")
        for container, info in BASELINE_CONFIGS.items():
            cfg = read_bot_config(container, info)
            if cfg is None: continue
            baseline_mot = info["mot"]
            new_mot = max(1, baseline_mot - 2)
            current_mot = cfg.get("max_open_trades", baseline_mot)
            if current_mot != new_mot:
                if dry_run:
                    log(f"  DRY-RUN: would set {container} MOT={current_mot}->{new_mot}")
                    continue
                cfg["max_open_trades"] = new_mot
                if write_config(container, info, cfg):
                    subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
                    log(f"  MOT REDUCED: {container} {current_mot}->{new_mot}")
                    actions.append(f"mot_reduced:{container}:{new_mot}")

    # ── R2: Drawdown > 2% ──
    if drawdown_pct > 3.0:
        log(f"R2: Drawdown {drawdown_pct:.1f}% > 3% — halving stakes")
        rules_fired.append("R2")
        for container, info in BASELINE_CONFIGS.items():
            cfg = read_bot_config(container, info)
            if cfg is None: continue
            baseline_stake = info["stake"]
            new_stake = max(10, round(baseline_stake * 0.5))
            current_stake = cfg.get("stake_amount", baseline_stake)
            if current_stake != new_stake:
                if dry_run:
                    log(f"  DRY-RUN: would set {container} stake={current_stake}->{new_stake}")
                    continue
                cfg["stake_amount"] = new_stake
                if write_config(container, info, cfg):
                    subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
                    log(f"  STAKE HALVED: {container} {current_stake}->{new_stake}")
                    actions.append(f"stake_halved:{container}:{new_stake}")

    # ── R6: Profit mode ──
    if fleet_pnl > 500:  # +5% of 10k capital
        log(f"R6: Fleet PnL {fleet_pnl:+.2f} > +500 — increasing stakes by 25%")
        rules_fired.append("R6")
        for container, info in BASELINE_CONFIGS.items():
            cfg = read_bot_config(container, info)
            if cfg is None: continue
            baseline_stake = info["stake"]
            new_stake = round(baseline_stake * 1.25)
            current_stake = cfg.get("stake_amount", baseline_stake)
            if current_stake != new_stake:
                if dry_run:
                    log(f"  DRY-RUN: would set {container} stake={current_stake}->{new_stake}")
                    continue
                cfg["stake_amount"] = new_stake
                if write_config(container, info, cfg):
                    subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
                    log(f"  STAKE INCREASED: {container} {current_stage}->{new_stake}")
                    actions.append(f"stake_increased:{container}:{new_stake}")

    # ── R4: Recovery ──
    if recovery_mode:
        for container, info in BASELINE_CONFIGS.items():
            cfg = read_bot_config(container, info)
            if cfg is None: continue
            target_mot = info["mot"]
            target_stake = info["stake"]
            current_mot = cfg.get("max_open_trades", target_mot)
            current_stake = cfg.get("stake_amount", target_stake)
            changed = False
            if current_mot != target_mot:
                if dry_run:
                    log(f"  DRY-RUN: would restore {container} MOT={current_mot}->{target_mot}")
                else:
                    cfg["max_open_trades"] = target_mot
                    changed = True
                actions.append(f"mot_restored:{container}:{target_mot}")
            if current_stake != target_stake:
                if dry_run:
                    log(f"  DRY-RUN: would restore {container} stake={current_stake}->{target_stake}")
                else:
                    cfg["stake_amount"] = target_stake
                    changed = True
                actions.append(f"stake_restored:{container}:{target_stake}")
            if changed and not dry_run:
                write_config(container, info, cfg)

    # ── Log actions ──
    os.makedirs(str(STATE_DIR), exist_ok=True)
    entry = {
        "timestamp": now.isoformat(),
        "drawdown_pct": round(drawdown_pct, 2),
        "consec_losses": consec_losses,
        "fleet_pnl": round(fleet_pnl, 2),
        "rules_fired": rules_fired,
        "actions": actions,
        "dry_run": dry_run,
    }
    with open(str(ACTION_LOG), "a") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    with open(str(HEALTH_FILE), "w") as f:
        json.dump(entry, f, indent=2)

    if actions:
        log(f"Actions taken: {len(actions)}")
        for a in actions:
            log(f"  -> {a}")
    else:
        log("No actions needed — parameters within limits")

    return 0


if __name__ == "__main__":
    sys.exit(main())
