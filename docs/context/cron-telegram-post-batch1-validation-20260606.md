# Post-Batch1 Cron/Telegram Validation Report

> **Datum:** 2026-06-06T05:48 UTC  
> **Referenz:** docs/context/cron-hygiene-batch1-execution-20260606.md  
> **Read-only — keine Mutationen durchgeführt**

---

## 1. Executive Verdict

**GELB (YELLOW)** — Batch 1 Fixes wirken (config-diff-detector repariert, SI-Bot-A läuft). Aber **container-watchdog wurde als weitere Spam-Quelle entdeckt**, die nicht Teil von Batch 1 war und jetzt priorisiert werden muss.

---

## 2. Cron Listing

| Metrik | Batch 1 Vorher | Post-Batch1 | Delta |
|--------|---------------|-------------|-------|
| Gesamt Jobs | 58 | **57** | -1 (72h Research Monitor gelöscht) |
| Aktive (enabled) | 53 | **53** | 0 |
| Pausiert | 3 | **4** | +1 (morning-brief-1040, hermes-standby-monitor) |
| Error (last_status) | 7 | **4** | -3 (SI-Bot-A=OK) |
| Nie gelaufen | 12 | **12** | 0 |

---

## 3. SI Analyze-Jobs (Check 2)

| Job | Vorher | Nachher | Timing |
|-----|--------|---------|--------|
| `si-bot-a-analyze-15min` | ❌ error | **✅ ok** (05:46) | Erster erfolgreicher Run nach Script-Kopie |
| `si-bot-b-analyze-20min` | ❌ error | ❌ error (05:40) | Letzter Run VOR Script-Kopie, nächster Tick ~06:00 |
| `si-bot-c-analyze-30min` | ❌ error | ❌ error (05:31) | Letzter Run VOR Script-Kopie, nächster Tick ~06:00 |
| `si-bot-d-analyze-20min` | ❌ error | ❌ error (05:40) | Letzter Run VOR Script-Kopie, nächster Tick ~06:00 |

**Bewertung:** Bot A bestätigt Script-Pfad-Fix funktioniert. B/C/D stehen noch auf dem letzten error-Run vor dem Fix, aber der nächste Tick (06:00 UTC) sollte alle OK melden.

---

## 4. config-diff-detector (Check 3)

| Metrik | Vorher | Nachher |
|--------|--------|---------|
| errors | **4** | **0** ✅ |
| drift_detected | 0 | **3** |
| "No such container" | 4× | **0** ✅ |

**Log zeigt dreistufige Fix-Geschichte:**
```
05:00 → 4 Errors (alte Container-Namen + Proxy)
05:46:29 → 3 Errors (richtige Namen, falscher Container-Pfad)
05:46:47 → 0 Errors (alles korrekt, echte Drifts gemeldet)
```

**Verdict:** ✅ GREEN — Fix wirksam. Die 3 Drifts sind echte Config-Unterschiede (siehe Check 10).

---

## 5. critical-event-watchdog (Check 4)

C3 Check liest `config_diff_health.json`:
- `errors > 0` → alert "N config error(s) — unrepairable" 
- `drift > 0` → alert "N config drift(s) detected"

**Vorher:** `errors=4` → 🔴 "4 config error(s) — unrepairable" → Telegram-Spam alle 10min  
**Nachher:** `errors=0, drift=3` → 🔴 "3 config drift(s) detected" → weiterhin Telegram

**Bewertung:** Die false "error" Alerts sind weg. Aber der Watchdog meldet weiterhin drift>0, was korrektes Verhalten ist. Die 3 Drifts sind echter Config-Drift (nicht Batch 1 verursacht). **Allerdings:** Der Watchdog hat keine Schwelle zwischen "3 Drifts" und "unerheblicher Drift" — jeder Drift löst Alarm aus.

**Empfehlung:** Config-Drifts bewerten (Check 10). Wenn Drifts bewusst/akzeptabel sind, entweder Host-Configs aktualisieren oder C3-Check anpassen.

---

## 6. ⚠️ NEUER BEFUND: container-watchdog Spam-Quelle (Check 5)

**Dies war NICHT Teil von Batch 1 und wurde während der Post-Validation entdeckt.**

`container_watchdog.sh` Zeile 19 hat **alte Container-Namen:**

```bash
TRADING_CONTAINERS="freqtrade-freqforge freqtrade-freqforge-canary freqtrade-regime-hybrid freqai-rebel ai-hedge-fund-crypto"
```

Korrekt wäre:
```bash
TRADING_CONTAINERS="trading-freqtrade-freqforge-1 trading-freqtrade-freqforge-canary-1 trading-freqtrade-regime-hybrid-1 trading-freqai-rebel-1 trading-ai-hedge-fund-1"
```

**Auswirkung:**
- Alle 5 Container werden als `not_found` gemeldet
- Telegram-Alert alle 30 Minuten: `❌ freqtrade-freqforge: not_found` (×5)
- **State-File zeigt alle Container als down** seit mind. 05:30 Uhr
- Die `BOT_PROBES` Map hat auch alte Namen als Keys

**Warum wurde das in Batch 1 nicht erkannt?**
- Der Audit prüfte nur `config_diff_detector.py` auf alte Namen (grep nach `freqtrade-freqforge`)
- container-watchdog wurde als "OK, last_status=ok" eingestuft — weil der Script trotz falscher Namen *läuft* (nur falsche Ergebnisse liefert)

**Status:** 🟡 YELLOW — weitere Spam-Quelle gefunden. Muss in Batch 1B+ oder Batch 2 repariert werden.

---

## 7. Paused/Gelöschte Jobs Bestätigt (Checks 6-8)

| Job | Erwartet | Ist | Status |
|-----|----------|-----|--------|
| `hermes-standby-monitor` | paused | paused (enabled=false) | ✅ |
| `72h Research Fleet Monitor` | gelöscht | **nicht in listing** | ✅ |
| `morning-brief-1040` | paused | paused (enabled=false) | ✅ |

---

## 8. Echte Config-Drifts (Check 10)

| Bot | Parameter | Host | Container | Drift |
|-----|-----------|------|-----------|-------|
| **FreqForge** | stake_amount | 100 | **50** | ⚠️ 50% reduziert im Container |
| **FreqForge** | trailing_stop | None | **True** | ⚠️ trailing im Container aktiviert |
| **FreqForge-Canary** | stake_amount | 50 | **25** | ⚠️ 50% reduziert |
| **FreqForge-Canary** | trailing_stop | None | **True** | ⚠️ trailing aktiviert |
| **Regime-Hybrid** | stake_amount | 50 | **25** | ⚠️ 50% reduziert |
| **FreqAI-Rebel** | — | — | — | ✅ keine Drift (kein Host-Pfad) |

**Alle Drifts betreffen `stake_amount` und `trailing_stop`.** `dry_run=True` und `max_open_trades` stimmen überall überein.

**Mögliche Ursachen:**
1. **Bewusst:** Container-Config wurde manuell geändert (Konservativeres Position-Sizing, Trailing aktiviert)
2. **Auto-Deploy:** Docker-Compose oder Hot-Swap hat eine neuere Config in den Container geladen
3. **Host-Stale:** Host-Config wurde nie aktualisiert nach einer Änderung im Container

**⚠️ KEIN auto-restore ohne Klärung.** Stake-Reduktion 100→50/50→25 könnte eine bewusste Risikominimierung sein.

---

## 9. Zusammenfassung: Was funktioniert, was noch offen

### ✅ Behoben (Batch 1)
- SI Script-Pfade: Bot A bestätigt OK, B/C/D warten auf nächsten Tick
- config-diff-detector: 0 Errors, Container-Namen + Pfade korrekt
- hermes-standby-monitor: pausiert (kein SCHEDULER_STALLED mehr)
- 72h Research Fleet Monitor: entfernt
- morning-brief-1040: pausiert

### ⚠️ Neu entdeckt (Post-Validation)
- **container-watchdog** hat alte Container-Namen → sendet alle 30min "5 Container not_found" an Telegram
- **critical-event-watchdog** meldet weiterhin 3 Config-Drifts (korrektes Verhalten, aber Noise)
- **ai-hedge-fund-crypto** → korrekter Name ist `trading-ai-hedge-fund-1` (auch im container-watchdog)

### 🔍 Braucht Klärung
- 3 Config-Drifts (stake_amount + trailing_stop) — bewusst oder Stale?
- critical-event-watchdog: sollte drift>0 überhaupt alarmieren oder nur errors>0?

---

## 10. Empfehlung: Nächster Schritt

**Nicht Batch 2 starten.** Erste Priorität:

```
1. container-watchdog.sh Container-Namen fixen (URGENT — aktiver Telegram-Spam)
   → Gleicher Fix wie config-diff-detector
   → BOT_PROBES Keys ebenfalls aktualisieren
   → ai-hedge-fund-crypto → trading-ai-hedge-fund-1

2. Abwarten ob SI Bot B/C/D beim 06:00 Tick OK melden

3. Config-Drifts bewerten (manuelle Entscheidung, kein Auto-Restore)
```

**Erst wenn container-watchdog repariert ist** → einen vollständigen Telegram-Ruhe-Check machen (mindestens 1 Zyklus = 30min ohne Spam).

---

## Verdict: YELLOW

- Batch 1 Fixes wirken ✅
- Neue Spam-Quelle entdeckt (container-watchdog) ⚠️
- Config-Drifts sind legitim aber erzeugen Watchdog-Noise ⚠️
- Safety-Guards unverändert ✅
- Keine Regressionen ✅

---

*Post-Batch1 Validation 2026-06-06T05:48 UTC. Read-only.*
