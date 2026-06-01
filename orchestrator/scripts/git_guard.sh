#!/usr/bin/env bash
set -euo pipefail

PROJECT="/home/hermes/projects/trading"
cd "$PROJECT"

echo "🔍 Hermes Git Guard v1.3 – final (alle Runtime-Dateien ignoriert)"

[[ "$(whoami)" == "hermes" ]] || { echo "❌ FALSCHER USER"; exit 1; }

# Ignoriere ALLE bekannten Runtime/Generated Dateien und Ordner
BAD=$(find . -not -user hermes -o -not -group hermes | \
      grep -vE 'orchestrator/logs|freqtrade/(logs|shared|bots/.*/user_data)|freqforge(-canary)?/user_data|ai-hedge-fund-crypto/output' | \
      head -10)

[[ -z "$BAD" ]] || { echo "❌ Ownership-Probleme (außer Runtime-Dateien): $BAD"; exit 1; }

# SSH-Key
[[ -f .ssh_local/id_ed25519_trading_hub ]] && chmod 600 .ssh_local/id_ed25519_trading_hub 2>/dev/null

echo "✅ Git Guard v1.3: Alles grün. Keine Permission-Scheiße mehr."
exit 0
