# Workspace Baseline — HermesTrader (trading-hub-orchestrator)

> Canonical paths, permissions, and access posture for the trading-hub operator workspace.

## Paths (canonical)
- **Host path (working tree):** `/opt/data/projects/trading-hub` (owner `deploy:deploy`, `755`)
- **Hermes container mount:** `/workspace/projects/trading-hub` (**read-only**, via `compose.override.yaml`)
- **Legacy (DO NOT USE as canonical):** `/home/hermes/projects/trading` — historical agent0 path.

## Users / UIDs
- Host operator: `deploy` (uid 1000; groups: deploy, sudo, hermes/10000, docker)
- Hermes runtime: uid/gid **10000** (container)
- `docker exec hermes <binary>` runs as **root** (container shim drops only `hermes`-invocations to uid 10000) — verify operator-relevant reads with `docker exec --user 10000:10000`.

## Access posture
- Hermes sees the repo **read-only** (`:ro`); Hermes plans, `deploy`/Claude executes.
- **No `/var/run/docker.sock`** mounted into Hermes (intentional).
- `gh` auth lives on the host (`/home/deploy/.config/gh/hosts.yml`, account `GoLukeEnviro`); not required inside the container for read-only roadmap work.

## git in container (known caveat)
- `git` in the container raises `dubious ownership` (repo owner `deploy/1000` != exec uid `10000`).
- Workaround: `git -c safe.directory=/workspace/projects/trading-hub ...` per call (non-persistent).
- Persistent fix (git config / `GIT_CONFIG_GLOBAL`) is a C1+ follow-up.

## Related
- Identity: `vps-hermestrader-identity` (memory). Dashboard auth: `hermes-dashboard-auth-configyaml` (memory).
- Phase reports under `/root/reports/hermestrader-*.md`.
