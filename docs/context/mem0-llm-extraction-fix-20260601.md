# Mem0 LLM Extraction Fix -- 2026-06-01

## Problem

Mem0 LLM Extraction schlug bei jedem Memory-Add mit 401 Unauthorized fehl:
```
HTTP Request: POST https://ollama.com/v1/chat/completions "HTTP/1.1 401 Unauthorized"
ERROR mem0.memory.main: LLM extraction failed: unauthorized
```

## Architecture Decision

`MEM0_LLM_BASE_URL` bleibt auf `https://ollama.com/v1` (Ollama Cloud).
Kein Wechsel auf lokalen `green-ollama`.

## Root Cause

green-mem0 received no fresh `OLLAMA_API_KEY` from `/opt/hermes-green/.env` because the service had an explicit `environment:` list that did not include `OLLAMA_API_KEY`. The container fell back to an old/default key baked into the Docker image, which caused 401 Unauthorized.

## Fix

1 Zeile in `/opt/hermes-green/docker-compose.yml` hinzugefuegt:

```yaml
# green-mem0 environment section:
- OLLAMA_API_KEY=${OLLAMA_API_KEY}
```

Docker Compose interpoliert den Wert aus `/opt/hermes-green/.env`.

## Verification

```
vor Fix:  POST https://ollama.com/v1/chat/completions "HTTP/1.1 401 Unauthorized"
nach Fix: POST https://ollama.com/v1/chat/completions "HTTP/1.1 200 OK"
```

- Key present im Container: `OLLAMA_API_KEY_PRESENT`
- Memory Add funktioniert: status=ok
- Trading-Bots: unveraendert, kein Restart
- Nur `green-mem0` wurde recreated

## Korrektur zum Audit-Report

Der Audit-Report (`hermes-trading-runtime-audit-20260601-0541.md`) empfahl urspruenglich, `MEM0_LLM_BASE_URL` auf lokalen `green-ollama:11434/v1` umzustellen. Diese Empfehlung wurde verworfen. Kanonische Entscheidung: Ollama Cloud mit korrekter Authentifizierung nutzen.
