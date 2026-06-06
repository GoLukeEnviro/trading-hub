# SQLite Swamp Analysis — 2026-06-06

**Total:** 58 SQLite-Dateien gefunden (20 non-zero + 38 zero-byte)

## ACTIVE (non-zero, in use)
| File | Size | Bot | Status |
|------|------|-----|--------|
| freqforge/user_data/tradesv3.freqforge.dryrun.sqlite | 188K | FreqForge | ✅ Aktiv |
| freqforge-canary/user_data/tradesv3.freqforge_canary.dryrun.sqlite | 160K | Canary | ✅ Aktiv |
| freqtrade/bots/regime-hybrid/user_data/tradesv3.regime_hybrid.dryrun.sqlite | 160K | Regime-Hybrid | ✅ Aktiv |
| freqtrade/bots/freqai-rebel/user_data/tradesv3.freqai_rebel.dryrun.sqlite | 80K | Rebel | ✅ Aktiv |

## REFERENCED
| File | Size | Referenced-by |
|------|------|--------------|
| tradesv3.dryrun.sqlite (root) | 94K | Legacy (root dir) — not referenced by any active config |
| orchestrator/state/hermes_heartbeat.sqlite | 332K | heartbeat_writer.py |

## STALE CANDIDATE (non-zero but not referenced by any active config)
| File | Size | Bot dir | Reason |
|------|------|---------|--------|
| freqtrade/bots/freqai-rebel/user_data/tradesv3.rebel.dryrun.sqlite | 80K | rebel | Legacy — nicht in Config referenziert |
| freqtrade/bots/freqai-rebel/user_data/tradesv3.dryrun.sqlite | 80K | rebel | Generisch — nicht in Config referenziert |
| freqtrade/bots/freqai-rebel/user_data/tradesv3.sqlite | 80K | rebel | Generisch — nicht in Config referenziert |
| freqforge/user_data/tradesv3.dryrun.sqlite | 80K | freqforge | Generisch — nicht in Config referenziert |
| freqforge/user_data/tradesv3.sqlite | 80K | freqforge | Generisch — nicht in Config referenziert |
| freqforge-canary/user_data/tradesv3.dryrun.sqlite | 80K | canary | Generisch |
| freqforge-canary/user_data/tradesv3.sqlite | 80K | canary | Generisch |
| freqtrade/bots/regime-hybrid/user_data/tradesv3.dryrun.sqlite | 80K | regime | Generisch |
| freqtrade/bots/regime-hybrid/user_data/tradesv3.sqlite | 80K | regime | Generisch |
| freqtrade/bots/momentum/user_data/tradesv3.momentum.dryrun.sqlite | 80K | momentum | Bot inaktiv (Container existiert nicht!) |
| freqtrade/bots/momentum/user_data/tradesv3.momentum.sqlite | 80K | momentum | Bot inaktiv |
| freqtrade/bots/momentum/user_data/tradesv3.dryrun.sqlite | 80K | momentum | Bot inaktiv |
| freqtrade/bots/momentum/user_data/tradesv3.sqlite | 80K | momentum | Bot inaktiv |
| freqtrade/bots/rsi/user_data/tradesv3.dryrun.sqlite | 80K | rsi | Bot inaktiv |
| freqtrade/bots/rsi/user_data/tradesv3.sqlite | 80K | rsi | Bot inaktiv |
| freqtrade/bots/mvs/user_data/tradesv3.dryrun.sqlite | 80K | mvs | Bot inaktiv |

## ZERO-BYTE (38 files — sicher zu archivieren)
Alle 0-Byte-Dateien sind stale Artifakte von:
- Historischen Bot-Deployments (momentum, mvs, rsi, fomo-phase3)
- Fehlerhaften DB-Pfad-Konfigurationen (freqforge-canary hatte 3 DB-Pfad-Varianten)
- Container-Restarts mit neuem DB-Namen

**Empfehlung:**
1. Nur ZERO-BYTE Dateien archivieren → `mv` in `archive/db/2026-06-06/`
2. Keine non-zero DBs löschen (könnten Trade-Historie enthalten)
3. Momentum-Bot komplett aus Fleet-Manifest entfernen (Container existiert nicht)
4. Rolling-Archiv: nur Files > 30 Tage und non-zero UND nicht in Config referenziert

**AKTION ERFORDERLICH:** Momentum-Bot aus Watchdog-Config entfernen (meldet seit Wochen `not_found`)
