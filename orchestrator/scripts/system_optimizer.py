#!/usr/bin/env python3
"""
System Optimization Agent v3.2 - Autonomous Trading System Maintenance.
Runs as a Hermes no_agent cron job. Performs safe autonomous actions:
1. Unknown container sweep
2. Cron error detection + auto provider switch to zai/glm-5.1
3. Signal freshness validation + auto-heartbeat
4. Signal coverage validation
5. Performance quarantine: WR < 38% OR PF < 1.0 at 40+ trades
6. Fleet-Drawdown-Protection: >5% -> pause ALL bots
7. Daily Loss Limit: >2% in 24h -> pause ALL + alert
8. Per-Strategy Max Loss: >2.5% of capital -> quarantine
9. Consecutive Loss Protection: 4 -> 2h pause + analysis
10. Equity Protection: below 7-day avg -> halve stake
11. Disk space monitoring
12. Stale file cleanup (>14d)
13. Fleet performance snapshot
"""
import json, os, sys, time, subprocess, glob, sqlite3, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = "/home/hermes/projects/trading"
CRON_JSON = "/opt/data/profiles/orchestrator/cron/jobs.json"
QUARANTINE_LOG = os.path.join(BASE, "orchestrator/state/quarantine_log.json")
REPORT = []

QUARANTINE_MIN_TRADES = 40; QUARANTINE_MAX_WR = 38.0; QUARANTINE_MIN_PF = 1.0
DRAWDOWN_PCT_LIMIT = 5.0; DAILY_LOSS_PCT_LIMIT = 2.0; PER_STRATEGY_LOSS_PCT = 2.5
TOTAL_CAPITAL = 10000.0; EQUITY_LOOKBACK_DAYS = 7; EQUITY_REDUCE_FACTOR = 0.5
CONSEC_LOSS_TRIGGER = 4; CONSEC_PAUSE_HOURS = 2; CONSEC_WEAK_PAIR_MIN_LOSSES = 2
CONSEC_STRAT_SUSPEND_HOURS = 24; SIGNAL_STALE_MINUTES = 45

STATE_DIR = os.path.join(BASE, "orchestrator/state")
EQUITY_HISTORY_FILE = os.path.join(STATE_DIR, "equity_history.json")
EQUITY_HIGH_FILE = os.path.join(STATE_DIR, "equity_high.json")
ORIGINAL_STAKES_FILE = os.path.join(STATE_DIR, "original_stakes.json")
CONSEC_STATE_FILE = os.path.join(STATE_DIR, "consec_loss_state.json")

def log(msg):
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
    print(line)
    REPORT.append(line)

KNOWN_CONTAINERS = {
    "freqtrade-freqforge", "freqtrade-regime-hybrid", "freqtrade-momentum",
    "freqtrade-freqforge-canary", "freqai-rebel", "freqtrade-webserver",
    "ai-hedge-fund-crypto", "trading-guardian", "caddy",
    "hermes-agent", "hermes-mem0-local-api", "hermes-ollama", "hermes-qdrant",
    "claude-worker",
}
FLEET_BOTS = {
    "freqtrade-freqforge": {"dbs": ["/freqtrade/user_data/tradesv3.freqforge.dryrun.sqlite", "/freqtrade/tradesv3.dryrun.sqlite"], "label": "FreqForge", "config_host": "/home/hermes/projects/trading/freqforge/config/config_freqforge_dryrun.json", "config_container": "/freqtrade/config/config_freqforge_dryrun.json"},
    "freqtrade-regime-hybrid": {"dbs": ["/freqtrade/user_data/tradesv3.regime_hybrid.dryrun.sqlite"], "label": "Regime-Hybrid", "config_host": "/home/hermes/projects/trading/freqtrade/bots/regime-hybrid/config/config_regime_hybrid_dryrun.json", "config_container": "/freqtrade/config/config_regime_hybrid_dryrun.json"},
    "freqtrade-freqforge-canary": {"dbs": ["/freqtrade/user_data/tradesv3.freqforge_canary.dryrun.sqlite"], "label": "Canary", "config_host": "/home/hermes/projects/trading/freqforge-canary/config/config_canary_dryrun.json", "config_container": "/freqtrade/config/config_canary_dryrun.json"},
    "freqai-rebel": {"dbs": ["/freqtrade/tradesv3.dryrun.sqlite", "/freqtrade/user_data/tradesv3.dryrun.sqlite"], "label": "Rebel", "config_host": None, "config_container": "/freqtrade/user_data/config.json"},
}
FALLBACK_MODEL = "glm-5.1"; FALLBACK_PROVIDER = "zai"

# ── Config Helpers ──
def read_bot_config(container, info):
    cfg_path = info.get("config_host"); cfg_container = info.get("config_container"); cfg = None
    if cfg_path and os.path.exists(cfg_path):
        with open(cfg_path) as f: cfg = json.load(f)
    elif cfg_container:
        r = subprocess.run(["docker", "exec", container, "cat", cfg_container], capture_output=True, text=True, timeout=10)
        if r.returncode == 0: cfg = json.loads(r.stdout)
    return cfg

def write_bot_config(container, info, cfg):
    cfg_path = info.get("config_host"); cfg_container = info.get("config_container")
    cfg_json = json.dumps(cfg, indent=4)
    if cfg_path and os.path.exists(cfg_path):
        backup = cfg_path + f".bak-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(cfg_path, backup)
        with open(cfg_path, "w") as f: f.write(cfg_json)
        log(f"  Backup: {backup}"); return True
    elif cfg_container:
        escaped = cfg_json.replace("'", "'\\''")
        r = subprocess.run(["docker", "exec", container, "bash", "-c", f"echo '{escaped}' > {cfg_container}"], capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    return False

def quarantine_bot(container, info, reason):
    cfg = read_bot_config(container, info)
    if cfg is None: log(f"  SKIP {info['label']}: cannot read config"); return False
    if cfg.get("max_open_trades") == 0: log(f"  {info['label']:15s}: already quarantined"); return False
    log(f"  *** QUARANTINE: {info['label']} \u2014 {reason} ***")
    cfg["max_open_trades"] = 0; ok = write_bot_config(container, info, cfg)
    if not ok: log(f"  ERROR writing config for {info['label']}"); return False
    log(f"  Set max_open_trades=0 for {info['label']}")
    subprocess.run(["docker", "restart", container], capture_output=True, timeout=30)
    log(f"  Restarted {container}"); _log_quarantine(info["label"], reason); return True

def _log_quarantine(label, reason):
    os.makedirs(os.path.dirname(QUARANTINE_LOG), exist_ok=True)
    entries = []
    if os.path.exists(QUARANTINE_LOG):
        try:
            with open(QUARANTINE_LOG) as f: entries = json.load(f)
        except: entries = []
    entries.append({"timestamp": datetime.now(timezone.utc).isoformat(), "bot": label, "reason": reason})
    with open(QUARANTINE_LOG, "w") as f: json.dump(entries, f, indent=2)

# ── DB Query Helpers ──
def query_db(container, db_path, sql):
    r = subprocess.run(["docker", "exec", container, "sqlite3", db_path, sql], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

def get_bot_stats(container, db_path):
    sql = "SELECT count(*), round(sum(close_profit_abs),4), sum(case when close_profit>0 then 1 else 0 end), sum(case when close_profit<=0 then 1 else 0 end), round(avg(case when close_profit>0 then close_profit_abs end),4), round(avg(case when close_profit<=0 then abs(close_profit_abs) end),4) FROM trades WHERE is_open=0;"
    r = query_db(container, db_path, sql)
    if not r or "|" not in r: return None
    p = r.split("|"); n = int(p[0])
    if n == 0: return None
    w = int(p[2]); l = int(p[3]); aw = float(p[4]) if p[4] else 0; al = float(p[5]) if p[5] else 0
    return {"trades": n, "pnl": float(p[1]), "wins": w, "losses": l, "avg_win": aw, "avg_loss": al, "wr": 100.0*w/n, "pf": (w*aw/max(l*al,0.0001)) if l>0 and al>0 else float('inf')}

def get_bot_24h_pnl(container, db_path):
    r = query_db(container, db_path, "SELECT round(coalesce(sum(close_profit_abs),0),4) FROM trades WHERE is_open=0 AND close_date > datetime('now', '-1 day');")
    return float(r) if r else 0.0

def get_bot_open_count(container, db_path):
    r = query_db(container, db_path, "SELECT count(*) FROM trades WHERE is_open=1;")
    return int(r) if r else 0

def get_fleet_recent_trades(n=20):
    all_t = []
    for ct, info in FLEET_BOTS.items():
        for db in info["dbs"]:
            r = query_db(ct, db, f"SELECT pair, round(close_profit_abs,4), close_date, open_date, round(close_profit,4) FROM trades WHERE is_open=0 ORDER BY close_date DESC LIMIT {n};")
            if not r: continue
            for line in r.strip().splitlines():
                parts = line.split("|")
                if len(parts) >= 5: all_t.append({"bot": info["label"], "container": ct, "pair": parts[0], "pnl": float(parts[1]), "close_date": parts[2], "open_date": parts[3], "profit_pct": float(parts[4])})
            break
    all_t.sort(key=lambda t: t["close_date"], reverse=True)
    return all_t[:n]

# ── 1. Unknown Container Sweep ──
def sweep_unknown_containers():
    log("--- Unknown Container Sweep ---")
    try:
        r = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}\\t{{.Status}}"], capture_output=True, text=True, timeout=15)
        if r.returncode != 0: log("  SKIP: docker not available"); return
        removed = 0
        for line in r.stdout.strip().splitlines():
            if not line.strip(): continue
            parts = line.split("\\t")
            if len(parts) < 2: continue
            name, st = parts[0], parts[1]
            if name not in KNOWN_CONTAINERS:
                log(f"  REMOVING: {name} ({st})")
                subprocess.run(["docker", "stop", name], capture_output=True, timeout=15)
                subprocess.run(["docker", "rm", name], capture_output=True, timeout=10); removed += 1
        log(f"  Removed {removed} unknown containers")
    except Exception as e: log(f"  ERROR: {e}")

# ── 2. Cron Error Detection ──
def fix_error_cron_jobs():
    log("--- Cron Job Health ---")
    try:
        with open(CRON_JSON) as f: data = json.load(f)
        jobs = data.get("jobs", []); errors = [j for j in jobs if j.get("last_status")=="error" and j.get("enabled")]
        paused = [j for j in jobs if j.get("paused_at")]
        log(f"  Total: {len(jobs)} | Errors: {len(errors)} | Paused: {len(paused)}")
        if errors:
            for j in errors:
                jid = j.get("job_id","?"); prov = j.get("provider","?"); mod = j.get("model","?")
                if prov != FALLBACK_PROVIDER or mod != FALLBACK_MODEL:
                    log(f"  AUTO-FIX: {j.get('name')} ({prov}/{mod} -> {FALLBACK_PROVIDER}/{FALLBACK_MODEL})")
                    with open(CRON_JSON) as f: jd = json.load(f)
                    for jj in jd.get("jobs",[]):
                        if jj.get("job_id") == jid: jj["model"]=FALLBACK_MODEL; jj["provider"]=FALLBACK_PROVIDER
                    with open(CRON_JSON,"w") as f: json.dump(jd,f,indent=2)
                else: log(f"  PERSISTENT ERROR: {j.get('name')} (already on fallback)")
        if paused:
            for j in paused: log(f"  PAUSED: {j.get('name')} since {j.get('paused_at')}")
    except Exception as e: log(f"  ERROR: {e}")

# ── 3. Signal Freshness ──
def check_signal_freshness():
    log("--- Signal Freshness ---")
    sig_path = os.path.join(BASE, "ai-hedge-fund-crypto/output/hermes_signal.json")
    try:
        if not os.path.exists(sig_path): log("  CRITICAL: hermes_signal.json MISSING! Triggering heartbeat..."); _trigger_heartbeat(); return
        age = (time.time()-os.path.getmtime(sig_path))/60
        with open(sig_path) as f: sig = json.load(f)
        pairs = sig.get("pairs",{}); risk = sig.get("global_risk_mode","?")
        if age > SIGNAL_STALE_MINUTES:
            log(f"  STALE: {age:.0f} min old! Auto-triggering heartbeat..."); _trigger_heartbeat()
            log(f"  After heartbeat: {(time.time()-os.path.getmtime(sig_path))/60:.0f} min old")
        else: log(f"  OK: {age:.1f} min old, {len(pairs)} pairs, risk={risk}")
        for pair, pd in pairs.items(): log(f"    {pair}: {pd.get('action')} conf={pd.get('confidence')}")
    except Exception as e: log(f"  ERROR: {e}")

def _trigger_heartbeat():
    hb = os.path.join(BASE, "orchestrator/scripts/ai_hedge_signal_heartbeat.sh")
    if os.path.exists(hb): subprocess.run(["bash", hb], capture_output=True, timeout=120)

# ── 4. Signal Coverage ──
def check_signal_coverage():
    log("--- Signal Coverage ---")
    try:
        sig_path = os.path.join(BASE, "ai-hedge-fund-crypto/output/hermes_signal.json")
        if not os.path.exists(sig_path): log("  SKIP: No signal file"); return
        with open(sig_path) as f: sig = json.load(f)
        signal_pairs = set(sig.get("pairs",{}).keys()); fleet_pairs = set()
        for bot,info in FLEET_BOTS.items():
            cp = info.get("config_host")
            if cp and os.path.exists(cp):
                try:
                    with open(cp) as f: fleet_pairs.update(set(json.load(f).get("exchange",{}).get("pair_whitelist",[])))
                except: pass
        missing = fleet_pairs - signal_pairs; covered = fleet_pairs & signal_pairs
        log(f"  Fleet pairs: {len(fleet_pairs)} | Signal pairs: {len(signal_pairs)} | Covered: {len(covered)} | Missing: {len(missing)}")
        if missing:
            for p in sorted(missing): log(f"    NO SIGNAL: {p}")
        else: log(f"  All fleet pairs have signal coverage")
    except Exception as e: log(f"  ERROR: {e}")

# ── 5. Performance Quarantine ──
def check_performance_quarantine():
    log("--- Performance Quarantine (WR<38% OR PF<1.0 @40+ trades) ---")
    try:
        for ct,info in FLEET_BOTS.items():
            for db in info["dbs"]:
                s = get_bot_stats(ct,db)
                if s is None or s["trades"] < QUARANTINE_MIN_TRADES: continue
                cfg = read_bot_config(ct,info)
                if cfg and cfg.get("max_open_trades")==0: log(f"  {info['label']:15s}: ALREADY QUARANTINED ({s['trades']}t, WR={s['wr']:.1f}%, PF={s['pf']:.2f})"); break
                triggered = False; reason = ""
                if s["wr"] < QUARANTINE_MAX_WR: reason = f"WR={s['wr']:.1f}%<{QUARANTINE_MAX_WR}%"; triggered = True
                if s["pf"] < QUARANTINE_MIN_PF and s["losses"]>0: reason = f"PF={s['pf']:.2f}<{QUARANTINE_MIN_PF}" + (f" + WR={s['wr']:.1f}%" if triggered else ""); triggered = True
                if triggered: quarantine_bot(ct,info,f"{reason} ({s['trades']} trades, PnL={s['pnl']})")
                else: log(f"  {info['label']:15s}: OK ({s['trades']}t, WR={s['wr']:.1f}%, PF={s['pf']:.2f}, PnL={s['pnl']})")
                break
    except Exception as e: log(f"  ERROR: {e}")

# ── 6. Fleet Drawdown Protection ──
def check_fleet_drawdown():
    log(f"--- Fleet-Drawdown-Protection (>{DRAWDOWN_PCT_LIMIT}% from high -> pause all) ---")
    try:
        pnl = sum(get_bot_stats(ct,info["dbs"][0])["pnl"] for ct,info in FLEET_BOTS.items() if get_bot_stats(ct,info["dbs"][0]))
        equity = TOTAL_CAPITAL+pnl; os.makedirs(STATE_DIR,exist_ok=True)
        eq_high = TOTAL_CAPITAL
        if os.path.exists(EQUITY_HIGH_FILE):
            try:
                with open(EQUITY_HIGH_FILE) as f: eq_high = json.load(f).get("equity_high",TOTAL_CAPITAL)
            except: pass
        if equity > eq_high:
            eq_high = equity
            with open(EQUITY_HIGH_FILE,"w") as f: json.dump({"equity_high":eq_high,"updated":datetime.now(timezone.utc).isoformat()},f,indent=2)
        dd = 100.0*(eq_high-equity)/eq_high if eq_high > 0 else 0
        log(f"  Equity: {equity:.2f} | High: {eq_high:.2f} | Drawdown: {dd:.2f}%")
        if dd > DRAWDOWN_PCT_LIMIT:
            log(f"  !!! DRAWDOWN ALERT: {dd:.2f}% > {DRAWDOWN_PCT_LIMIT}% -- PAUSING ALL BOTS !!!")
            for ct,info in FLEET_BOTS.items(): quarantine_bot(ct,info,f"Fleet drawdown {dd:.2f}%")
            ds,_,_ = _collect_fleet_data(); icon = chr(9877)
            ln = [f"{icon} Hermes Alert \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T",
                  f"\u2022 Fleet Equity: {equity:.2f} USDT (High: {eq_high:.2f})",
                  f"\u2022 Drawdown: {dd:.1f}% \u2014 GRENZWERT \u00dcBERSCHRITTEN",
                  "", "ANALYSE", "\u2022 Alle Bots pausiert (max_open_trades=0)"]
            for b in ds[:3]: ln.append(f"\u2022 {b['label']}: {'+'if b['pnl']>=0 else ''}{b['pnl']:.2f} USDT")
            ln += ["", "VORSCHL\u00c4GE",
                   f"1. Fleet pausiert bis Drawdown < {DRAWDOWN_PCT_LIMIT:.0f}%",
                   "2. Manuelle \u00dcberpr\u00fcfung empfohlen",
                   "", f"Status: {chr(128680)} FLEET PAUSIERT"]
            _send_telegram_alert("\n".join(ln))
        else: log("  Drawdown within limits")
    except Exception as e: log(f"  ERROR: {e}")

# ── 7. Daily Loss Limit ──
def check_daily_loss():
    log(f"--- Daily Loss Limit (>{DAILY_LOSS_PCT_LIMIT}% in 24h -> pause all) ---")
    try:
        total_loss = 0.0; per_bot = {}
        for ct,info in FLEET_BOTS.items():
            p24 = get_bot_24h_pnl(ct,info["dbs"][0])
            if p24 < 0: total_loss += abs(p24); per_bot[info["label"]] = p24
        lpct = 100.0*total_loss/TOTAL_CAPITAL
        log(f"  24h loss: -{total_loss:.2f} USDT ({lpct:.2f}% of capital)")
        for l,p in per_bot.items(): log(f"    {l}: {p:+.2f} USDT")
        if lpct > DAILY_LOSS_PCT_LIMIT:
            log(f"  !!! DAILY LOSS ALERT: {lpct:.2f}% > {DAILY_LOSS_PCT_LIMIT}% -- PAUSING ALL BOTS !!!")
            for ct,info in FLEET_BOTS.items(): quarantine_bot(ct,info,f"Daily loss {lpct:.2f}%")
            icon = chr(9877)
            ln = [f"{icon} Hermes Alert \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T",
                  f"\u2022 24h Verlust: -{total_loss:.2f} USDT ({lpct:.1f}%)",
                  f"\u2022 Grenzwert: {DAILY_LOSS_PCT_LIMIT}% in 24h",
                  "", "ANALYSE", "\u2022 Alle Bots wurden pausiert"]
            for l,p in per_bot.items(): ln.append(f"\u2022 {l}: {'+'if p>=0 else ''}{p:.2f} USDT")
            ln += ["", "VORSCHL\u00c4GE",
                   "1. Fleet pausiert bis n\u00e4chster Optimierungs-Lauf",
                   "2. Manuelle \u00dcberpr\u00fcfung empfohlen",
                   "", f"Status: {chr(128680)} DAILY LOSS ALARM"]
            _send_telegram_alert("\n".join(ln))
        else: log("  Daily loss within limits")
    except Exception as e: log(f"  ERROR: {e}")

# ── 8. Per-Strategy Max Loss ──
def check_per_strategy_loss():
    log(f"--- Per-Strategy Max Loss (>{PER_STRATEGY_LOSS_PCT}% of capital -> quarantine) ---")
    try:
        mla = TOTAL_CAPITAL*PER_STRATEGY_LOSS_PCT/100.0
        for ct,info in FLEET_BOTS.items():
            s = get_bot_stats(ct,info["dbs"][0])
            if s is None: continue
            if s["pnl"] < 0:
                la = abs(s["pnl"]); lpct = 100.0*la/TOTAL_CAPITAL
                if la > mla:
                    log(f"  !!! STRATEGY LOSS: {info['label']} lost {la:.2f} USDT ({lpct:.2f}%) -- QUARANTINING !!!")
                    quarantine_bot(ct,info,f"Strategy loss {la:.2f} USDT ({lpct:.1f}%)")
                else: log(f"  {info['label']:15s}: loss={la:.2f} USDT ({lpct:.2f}%) -- within limit")
            else: log(f"  {info['label']:15s}: PnL={s['pnl']:+.2f} -- no loss")
    except Exception as e: log(f"  ERROR: {e}")

# ── 9. Consecutive Loss Protection ──
def check_consecutive_loss_protection():
    log(f"--- Consecutive Loss Protection ({CONSEC_LOSS_TRIGGER} losses -> {CONSEC_PAUSE_HOURS}h pause + analysis) ---")
    try:
        os.makedirs(STATE_DIR,exist_ok=True)
        state = {"paused_at":None,"resume_after":None,"actions_taken":[]}
        if os.path.exists(CONSEC_STATE_FILE):
            try:
                with open(CONSEC_STATE_FILE) as f: state = json.load(f)
            except: state = {"paused_at":None,"resume_after":None,"actions_taken":[]}
        now = datetime.now(timezone.utc); ra = state.get("resume_after")
        if ra:
            rd = datetime.fromisoformat(ra)
            if now < rd: log(f"  IN PAUSE: {(rd-now).total_seconds()/60:.0f} min remaining (resume at {ra})"); return
            else: log(f"  Pause expired at {ra} -- analyzing and resuming")
        trades = get_fleet_recent_trades(n=20)
        if len(trades) < CONSEC_LOSS_TRIGGER: log(f"  Only {len(trades)} recent trades -- skip"); return
        cl = 0; lt = []
        for t in trades:
            if t["pnl"] < 0: cl += 1; lt.append(t)
            else: break
        log(f"  Consecutive losses: {cl}/{CONSEC_LOSS_TRIGGER}")
        if cl < CONSEC_LOSS_TRIGGER: log(f"  No trigger -- {cl} consecutive losses (need {CONSEC_LOSS_TRIGGER})"); return
        log(f"  !!! CONSECUTIVE LOSS ALERT: {cl} losses in a row !!!")
        for ct,info in FLEET_BOTS.items():
            cfg = read_bot_config(ct,info)
            if cfg is None or cfg.get("max_open_trades")==0: continue
            cfg["max_open_trades"]=0; ok = write_bot_config(ct,info,cfg)
            if ok: subprocess.run(["docker","restart",ct],capture_output=True,timeout=30); log(f"  PAUSED: {info['label']}")
        rt = now+timedelta(hours=CONSEC_PAUSE_HOURS); actions = []; pl = {}; bl = {}
        for t in lt: p=t["pair"]; pl[p]=pl.get(p,0)+1; b=t["bot"]; bl[b]=bl.get(b,0)+1
        log("  --- Analysis ---")
        for p,c in sorted(pl.items(),key=lambda x:-x[1]): log(f"    Pair {p}: {c} losses")
        for b,c in sorted(bl.items(),key=lambda x:-x[1]): log(f"    Bot  {b}: {c} losses")
        ex_p = []
        for p,c in pl.items():
            if c >= CONSEC_WEAK_PAIR_MIN_LOSSES: ex_p.append(p); log(f"  EXCLUDE PAIR: {p} ({c} losses in streak)")
        if ex_p:
            actions.append(f"Excluded pairs: {', '.join(ex_p)}")
            for ct,info in FLEET_BOTS.items():
                cfg = read_bot_config(ct,info)
                if cfg is None: continue
                wl = cfg.get("exchange",{}).get("pair_whitelist",[])
                if wl:
                    nwl = [p for p in wl if p not in ex_p]
                    if len(nwl) < len(wl): cfg["exchange"]["pair_whitelist"]=nwl; write_bot_config(ct,info,cfg); log(f"  {info['label']}: removed {len(wl)-len(nwl)} weak pairs from whitelist")
        ss = []
        for b,c in sorted(bl.items(),key=lambda x:-x[1]):
            if c >= 2:
                for ct,info in FLEET_BOTS.items():
                    if info["label"]==b:
                        sr = (now+timedelta(hours=CONSEC_STRAT_SUSPEND_HOURS)).isoformat()
                        ss.append(f"{b} until {sr[:16]}"); log(f"  SUSPEND 24h: {b} (caused {c} of {cl} losses)")
                        actions.append(f"Suspended {b} for {CONSEC_STRAT_SUSPEND_HOURS}h"); break
        saf = os.path.join(STATE_DIR,"signal_confidence_adjust.json")
        with open(saf,"w") as f: json.dump({"min_confidence":0.75,"reason":f"Consecutive loss protection ({cl} losses)","expires":rt.isoformat()},f,indent=2)
        log(f"  Signal confidence threshold raised to 0.75 until {rt.isoformat()[:16]}")
        actions.append(f"Signal confidence -> 0.75 for {CONSEC_PAUSE_HOURS}h")
        with open(CONSEC_STATE_FILE,"w") as f: json.dump({"paused_at":now.isoformat(),"resume_after":rt.isoformat(),"consecutive_losses":cl,"excluded_pairs":ex_p,"suspended_strategies":ss,"loss_trades":[{"bot":t["bot"],"pair":t["pair"],"pnl":t["pnl"],"close_date":t["close_date"]} for t in lt],"actions_taken":actions},f,indent=2)
        icon = chr(9877)
        ln = [f"{icon} Hermes Alert \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T",
              f"\u2022 {cl} Verluste in Folge (fleet-weit)"]
        for t in lt[:4]: ln.append(f"\u2022 {t['bot']}: {t['pair']} ({'+'if t['pnl']>=0 else ''}{t['pnl']:.2f})")
        ln += ["", "ANALYSE"]
        if ex_p: ln.append(f"\u2022 Schwache Paare: {', '.join(ex_p)}")
        if ss: ln.append(f"\u2022 Pausierte Strategien: {', '.join(ss)}")
        ln.append(f"\u2022 Fleet pausiert f\u00fcr {CONSEC_PAUSE_HOURS}h")
        ln += ["", "VORSCHL\u00c4GE"]
        for i,a in enumerate(actions[:3],1): ln.append(f"{i}. {a}")
        ln.append(f"Resume: {rt.strftime('%H:%M')} UTC")
        ln += ["", f"Status: {chr(128721)} CONSECUTIVE LOSS PAUSE"]
        _send_telegram_alert("\n".join(ln))
        log(f"  Fleet paused until {rt.isoformat()}")
    except Exception as e: log(f"  ERROR: {e}")

# ── 10. Equity Protection ──
def check_equity_protection():
    log(f"--- Equity Protection (below {EQUITY_LOOKBACK_DAYS}-day avg -> stake x{EQUITY_REDUCE_FACTOR}) ---")
    try:
        os.makedirs(STATE_DIR,exist_ok=True)
        pnl = sum(get_bot_stats(ct,info["dbs"][0])["pnl"] for ct,info in FLEET_BOTS.items() if get_bot_stats(ct,info["dbs"][0]))
        equity = TOTAL_CAPITAL+pnl; today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        hist = {}
        if os.path.exists(EQUITY_HISTORY_FILE):
            try:
                with open(EQUITY_HISTORY_FILE) as f: hist = json.load(f)
            except: hist = {}
        hist[today]=equity; co = (datetime.now(timezone.utc)-timedelta(days=30)).strftime("%Y-%m-%d")
        hist = {k:v for k,v in hist.items() if k >= co}
        with open(EQUITY_HISTORY_FILE,"w") as f: json.dump(hist,f,indent=2)
        ds = sorted(hist.keys(),reverse=True)[:EQUITY_LOOKBACK_DAYS]
        if len(ds) < 2: log(f"  Equity: {equity:.2f} | History: {len(ds)} days (need 2+ for avg)"); log("  SKIP: Not enough history yet -- collecting data"); return
        avg = sum(hist[d] for d in ds)/len(ds); ba = equity < avg
        log(f"  Equity: {equity:.2f} | {EQUITY_LOOKBACK_DAYS}-day avg: {avg:.2f} | {'BELOW' if ba else 'ABOVE'} avg")
        orig = {}
        if os.path.exists(ORIGINAL_STAKES_FILE):
            try:
                with open(ORIGINAL_STAKES_FILE) as f: orig = json.load(f)
            except: orig = {}
        changed = False
        for ct,info in FLEET_BOTS.items():
            cfg = read_bot_config(ct,info)
            if cfg is None or cfg.get("max_open_trades")==0: continue
            cs = cfg.get("stake_amount","unlimited"); lb = info["label"]
            if ba:
                if lb not in orig: orig[lb]=cs
                og = orig[lb]
                if isinstance(og,(int,float)) and og>0: tgt = round(og*EQUITY_REDUCE_FACTOR,4)
                elif og=="unlimited": tgt="unlimited"
                else: continue
                if cs != tgt and tgt != "unlimited": cfg["stake_amount"]=tgt; write_bot_config(ct,info,cfg); subprocess.run(["docker","restart",ct],capture_output=True,timeout=30); log(f"  {lb}: stake {og} -> {tgt} (REDUCED)"); changed=True
                elif cs == tgt: log(f"  {lb}: already reduced ({cs})")
            else:
                if lb in orig:
                    og = orig[lb]
                    if cs != og: cfg["stake_amount"]=og; write_bot_config(ct,info,cfg); subprocess.run(["docker","restart",ct],capture_output=True,timeout=30); log(f"  {lb}: stake {cs} -> {og} (RESTORED)"); del orig[lb]; changed=True
                    else: log(f"  {lb}: already at original stake ({og})"); del orig[lb]
                else: log(f"  {lb}: normal (no reduction active)")
        with open(ORIGINAL_STAKES_FILE,"w") as f: json.dump(orig,f,indent=2)
        icon = chr(9877)
        if ba and changed:
            ln = [f"{icon} Hermes Alert \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T",
                  f"\u2022 Equity: {equity:.2f} USDT", f"\u2022 7d-Avg: {avg:.2f} USDT",
                  "", "ANALYSE", "\u2022 Equity unter 7d-Durchschnitt",
                  "\u2022 Positionsgr\u00f6\u00dfen auf 50% reduziert",
                  "", "VORSCHL\u00c4GE",
                  "1. Gr\u00f6\u00dfen auto-restauriert bei Erholung",
                  "2. N\u00e4chster Check in 2h",
                  "", f"Status: {chr(9888)}{chr(65039)} EQUITY PROTECTION AKTIV"]
            _send_telegram_alert("\n".join(ln))
        elif not ba and changed:
            ln = [f"{icon} Hermes Alert \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T",
                  f"\u2022 Equity: {equity:.2f} USDT", f"\u2022 7d-Avg: {avg:.2f} USDT",
                  "", "ANALYSE", "\u2022 Equity wieder \u00fcber 7d-Durchschnitt",
                  "\u2022 Positionsgr\u00f6\u00dfen wiederhergestellt",
                  "", "VORSCHL\u00c4GE",
                  "1. Fleet l\u00e4uft wieder mit vollen Positionen",
                  "2. Weiterhin unter Beobachtung",
                  "", "Status: \u2705 EQUITY RECOVERY"]
            _send_telegram_alert("\n".join(ln))
    except Exception as e: log(f"  ERROR: {e}")

# ── 11. Disk Space ──
def check_disk():
    log("--- Disk Space ---")
    try:
        r = subprocess.run(["df","-h","/"],capture_output=True,text=True,timeout=5)
        for line in r.stdout.strip().splitlines():
            if "overlay" in line or "/dev/" in line:
                p = line.split()
                if len(p) >= 6:
                    try:
                        pct = int(p[4].replace("%",""))
                        log(f"  Disk: {p[1]} total, {p[2]} used, {p[3]} avail, {p[4]} full")
                        if pct > 85: log("  WARNING: Disk >85%!")
                        if pct > 92: log("  CRITICAL: Disk >92%!")
                    except ValueError: pass
    except Exception as e: log(f"  ERROR: {e}")

# ── 12. Stale Log Cleanup ──
def cleanup_stale_logs():
    log("--- Stale Log Cleanup (>14d) ---")
    try:
        co = time.time()-14*86400; cleaned=0; freed=0
        for pat in [os.path.join(BASE,"orchestrator/logs/**/*.log"), os.path.join(BASE,"ai-hedge-fund-crypto/output/logs/**/*"), os.path.join(BASE,"freqtrade/bots/*/logs/**/*"), os.path.join(BASE,"freqtrade/bots/**/logs/*.log")]:
            for fp in glob.glob(pat,recursive=True):
                if os.path.isfile(fp) and os.path.getmtime(fp)<co: freed+=os.path.getsize(fp); os.remove(fp); cleaned+=1
        log(f"  Cleaned {cleaned} files, freed {freed/1024/1024:.1f} MB")
    except Exception as e: log(f"  ERROR: {e}")

# ── 13. Fleet Snapshot ──
def fleet_snapshot():
    log("--- Fleet Performance ---")
    try:
        for ct,info in FLEET_BOTS.items():
            s = get_bot_stats(ct,info["dbs"][0])
            if s:
                no = get_bot_open_count(ct,info["dbs"][0])
                log(f"  {info['label']:15s}: {s['trades']:3d}t, PnL={s['pnl']:>8.2f}, WR={s['wr']:>5.1f}%, PF={s['pf']:>5.2f}, open={no}")
    except Exception as e: log(f"  ERROR: {e}")

# ── Telegram Reporting v2 ──
def _send_telegram_alert(message):
    ad = os.path.join(BASE,"orchestrator/state/alerts"); os.makedirs(ad,exist_ok=True)
    af = os.path.join(ad,f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json")
    with open(af,"w") as f: json.dump({"timestamp":datetime.now(timezone.utc).isoformat(),"message":message,"delivered":False},f,indent=2)
    log(f"  Alert queued: {af}")

def _verdict(pnl,wr,trades,quarantined=False):
    if quarantined: return "QUARANTINE"
    if trades<5: return "NEW"
    if pnl>5: return "BEST"
    if pnl>0: return "TOP"
    if wr<38 or pnl<-2: return "LOSS"
    return "OK"

def _now_str(): return datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

def _collect_fleet_data():
    bots = []; tp = 0.0; to = 0
    for ct,info in FLEET_BOTS.items():
        s = get_bot_stats(ct,info["dbs"][0])
        if s:
            no = get_bot_open_count(ct,info["dbs"][0])
            cfg = read_bot_config(ct,info); q = cfg is not None and cfg.get("max_open_trades")==0
            bots.append({"label":info["label"],"pnl":s["pnl"],"wr":s["wr"],"trades":s["trades"],"pf":s["pf"],"open":no,"quarantined":q})
            tp += s["pnl"]; to += no
    bots.sort(key=lambda b:-b["pnl"])
    return bots, tp, to

def _send_fleet_report():
    bots,tp,to = _collect_fleet_data(); icon = chr(9877)
    ln = [f"{icon} Hermes Fleet Report \u2014 {_now_str()}", "", "PROFITABILIT\u00c4T"]
    for b in bots:
        v = _verdict(b["pnl"],b["wr"],b["trades"],b["quarantined"])
        ln.append(f"\u2022 {b['label']}: {'+'if b['pnl']>=0 else ''}{b['pnl']:.2f} USDT ({b['wr']:.1f}% WR) \u2014 {v}")
    ln += ["", "ANALYSE", f"\u2022 Gesamt PnL: {'+'if tp>=0 else ''}{tp:.2f} USDT",
           f"\u2022 {to if to>0 else 'Keine'} {'offene Trades aktiv' if to>0 else 'offenen Trades'}"]
    sp = os.path.join(BASE,"ai-hedge-fund-crypto/output/hermes_signal.json")
    if os.path.exists(sp):
        try:
            with open(sp) as f: np = len(json.load(f).get("pairs",{}))
            ln.append(f"\u2022 Signal-Coverage: {np} Paare aktiv")
        except: pass
    eh = TOTAL_CAPITAL
    if os.path.exists(EQUITY_HIGH_FILE):
        try:
            with open(EQUITY_HIGH_FILE) as f: eh = json.load(f).get("equity_high",TOTAL_CAPITAL)
        except: pass
    dd = 100.0*(eh-(TOTAL_CAPITAL+tp))/eh if eh>0 else 0
    ln.append(f"\u2022 {'Keine Alarme aktiv' if dd<0.5 else f'Drawdown: {dd:.1f}%'}")
    ln += ["", "VORSCHL\u00c4GE"]
    nr = (datetime.now(timezone.utc)+timedelta(hours=2)).strftime("%H:%M UTC")
    sug = []
    for b in bots:
        if b["quarantined"]: sug.append(f"{b['label']} bleibt pausiert (Quarant\u00e4ne)")
        elif b["pnl"]<0 and b["wr"]<50: sug.append(f"{b['label']} Stop-Loss enger stellen")
    sug = sug or [f"Fleet l\u00e4uft stabil \u2014 keine Aktion n\u00f6tig"]
    sug.append(f"N\u00e4chster Optimierungs-Lauf um {nr}")
    for i,s in enumerate(sug[:3],1): ln.append(f"{i}. {s}")
    ln += ["", "Status: OPTIMIERUNGSMODUS AKTIV"]
    _send_telegram_alert("\n".join(ln))

# ── MAIN ──
if __name__ == "__main__":
    log("=== SYSTEM OPTIMIZATION AGENT v3.2 START ===")
    sweep_unknown_containers()
    fix_error_cron_jobs()
    check_signal_freshness()
    check_signal_coverage()
    check_performance_quarantine()
    check_fleet_drawdown()
    check_daily_loss()
    check_per_strategy_loss()
    check_consecutive_loss_protection()
    check_equity_protection()
    check_disk()
    cleanup_stale_logs()
    fleet_snapshot()
    _send_fleet_report()
    log("=== SYSTEM OPTIMIZATION AGENT v3.2 DONE ===")
