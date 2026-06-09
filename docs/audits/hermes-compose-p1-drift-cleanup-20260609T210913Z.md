# P1 Compose Drift Cleanup — 20260609T210913Z

## Scope
- Removed stale green-qdrant `command: ["sleep", "infinity"]` override (container uses default Qdrant entrypoint).
- Updated freqai-rebel compose image to `freqtrade-freqai-rebel:custom` (matches runtime).

## Validation
- `docker compose config --quiet`: PASS

## Safety
- No restart.
- No rebuild.
- No recreate.
- No docker compose up/down.
- No docker system prune.
- No secret output.
- No commit.

## Backups
- `.env.bak-20260609T210408Z`
- `docker-compose.yml.bak-20260609T210913Z`

## Diff Summary
Only two targeted changes in `docker-compose.yml`:
1. green-qdrant: removed sleep infinity command (3 lines)
2. freqai-rebel: image -> freqtrade-freqai-rebel:custom (1 line)
