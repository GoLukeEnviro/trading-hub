# Compose GAP Follow-Up Plan

Issues: #253, #256

This note translates the GAP report compose findings into a safe follow-up path. It does not change running Docker services and does not require `docker compose up`, restart, recreate, or prune.

## Current rule

The root compose layout remains the source of truth until a separately approved L3 rollout. Repository PRs may add static validation and documentation, but runtime adoption requires explicit approval and rollback evidence.

## Target domain split

| Domain | Target file | Scope |
| --- | --- | --- |
| Infra | `compose/infra.yml` | socket proxy, dashboard, shared networks |
| Fleet | `compose/fleet.yml` | dry-run Freqtrade services only |
| Memory | `compose/memory.yml` | Qdrant, Ollama, Mem0 services |
| Signal | `compose/signal.yml` | ai-hedge-fund-crypto, Primo/bridge signal services |

## Static validation commands

Use static checks first:

```bash
python3 -m pytest tests/test_docker_compose_contracts.py -q
python3 - <<'PY'
import yaml
for path in ["docker-compose.yml", "freqtrade/docker-compose.fleet.yml", "docker-compose.ai-hedge-fund-crypto.yml"]:
    with open(path, encoding="utf-8") as fh:
        yaml.safe_load(fh)
    print(f"OK {path}")
PY
```

If Docker Compose CLI is available in a non-production clone, validation can additionally run:

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f freqtrade/docker-compose.fleet.yml config --quiet
docker compose -f docker-compose.ai-hedge-fund-crypto.yml config --quiet
```

Do not run `up`, `restart`, `recreate`, `down`, `prune`, or volume operations without approval.

## Rollout plan

1. Add split compose files preserving service names, volumes, networks and localhost-only port bindings.
2. Validate `docker compose config` output in an isolated clone.
3. Compare rendered config with the current root/fleet compose files.
4. Request explicit L3 approval with rollback commands.
5. Apply to runtime one domain at a time.

## Rollback plan

Rollback is to keep using the existing compose files. If a split-file rollout is approved later, rollback must restore the previous compose invocation and previously snapshotted config files without deleting volumes.
