# SI-v2 Runtime Proof Rerun 65502d13 (tokened) — 2026-06-23

## Ergebnis
**RUNTIME_PROOF_RED** 🔴 — Tokened rerun completed; proof path still RED due to a Proof A API-surface gap (not a runtime/effect gap).

## Was passiert ist
- Beide L3-Tokens gesetzt in der ausführenden Shell:
  - `APPROVE_SI_V2_RUNTIME_ACTUATOR_ACTIVATION=APPROVE`
  - `APPROVE_SI_V2_FREQFORGE_RELOAD_65502D13=APPROVE`
- Repo-Preflight: `main`, HEAD `a29ed6c` = PR-336-Merge-Commit, ancestor von HEAD ✅
- Runtime-Preflight: 4/4 Bots Up, Rainbow GREEN+frisch, FreqForge healthy ✅
- FreqForge direkt: overlay Datei existiert, Prozess-Cmdline referenziert Overlay, Base `dry_run=true` ✅
- RuntimeEffectProof (`compute_apply_result`):
  - Proof C: `file_visible_to_bot=true`, `process_command_uses_overlay=true` ✅
  - Proof A (`show_config` API): `max_open_trades=3.0` ✅, `stake_amount="unlimited"` ✅, `strategy="FreqForge_Override"` ✅
  - Proof A: `tradable_balance_ratio` **nicht im Response-Payload** → Vergleich liefert `got=None` → RED
- ControlledApplyResult: `BLOCKED`, `mutation_counter_should_increment=false`, `measurement_allowed=false`

## Aktueller Blocker
**Proof A API-Surface Gap.** `tradable_balance_ratio` wird vom Freqtrade-`show_config`-REST-Endpoint nicht als Feld exponiert. Der Overlay **ist** in Freqtrade geladen (Proof C + 3 von 4 API-Feldern bestätigen das), aber die strenge `proof_status`-Logik in `proof.py` wertet das `got=None` als Hard-Mismatch → RED.

Zwei User-Entscheidungspfade (in separater PR zu lösen, kein Hotfix):
1. Konservativ: `tradable_balance_ratio` aus Proof-A-Expected-Keys entfernen, Proof B (`compute_merged_config`) und Proof C tragen das Signal.
2. Breiter: `show_config` durch `balance`-RPC oder in-container Config-Dump ersetzen, der alle gemergten Keys liefert.

## Nächster Schritt
User-Entscheidung über Pfad (1) oder (2) abwarten. Keine Messung. Kein Mutation-Counter-Inkrement. Keine neue Optimierungs-Iteration. Report + Evidence liegen vor; kein PR erstellt (RED-Gate). Wenn Pfad-Entscheidung getroffen: separater PR mit eigenem Proof-Rerun.

## Safety-Status
- `dry_run=false`: nie gesetzt ✅
- Live-Trading: nicht aktiviert ✅
- Andere Bots: unangetastet ✅
- Strategy-Files: unverändert ✅
- Pairlists: unverändert ✅
- Docker-Compose: keine breiten Aktionen ✅
- Secrets: nicht exponiert ✅

## Evidence
- Verzeichnis: `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-tokened-20260623T191005Z/`
- Report: `docs/reports/si-v2-runtime-proof-red-api-surface-65502d13-2026-06-23.md`
- Vorheriger Versuch (token-missing): `/opt/data/reports/si-v2-runtime-proof-rerun-65502d13-20260623T175317Z/`
- PR #336 merge commit: `a29ed6c88329fb1475a8799db63140fd841586c3`
