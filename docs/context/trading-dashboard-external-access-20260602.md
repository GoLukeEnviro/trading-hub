# Trading Dashboard External Access — 2026-06-02

## What changed
- A single-file Flask dashboard was created at `/home/hermes/projects/trading/dashboard.py`.
- The dashboard runs in a dedicated Docker container `trading-dashboard` and serves on port 5000 inside the container.
- The dashboard now reads the four Freqtrade SQLite databases and `hermes_signal.json` via `docker exec` because the dashboard container cannot access those paths directly.
- The active dashboard container mounts `/var/run/docker.sock` and has the Docker CLI available so those exec-based reads work at request time.
- Observation report status is also resolved through the signal container and falls back to a timestamp/placeholder when JSON is missing or invalid.
- Caddy was updated to route `agent0.taile6801f.ts.net/dashboard` to the dashboard service.
- The runtime Caddy config now proxies `/dashboard*` to `172.17.0.2:5000` with `127.0.0.1:5000` kept as fallback.

## Verification
- Dashboard HTML returns `200` when requested directly from the Caddy container with `Host: agent0.taile6801f.ts.net`.
- The dashboard container listens on `172.17.0.2:5000` and `127.0.0.1:5000` inside its own namespace.

## Notes
- Existing Caddy addresses were preserved; the dashboard route was only added/extended.
- The legacy `a0-v2:8080` upstream in Caddy remains unresolved in the current runtime config and is unrelated to the dashboard route.
