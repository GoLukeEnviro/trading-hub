# Hermes GitHub Multi-Repository Auth

This runbook describes the local-only GitHub authentication layer used by Hermes agents for Trading Hub and related repositories.

---

## Purpose

Hermes agents need one stable, reusable way to authenticate against multiple GitHub repositories. The token lives only on the Hermes host. No secret is committed to any repository.

---

## Secret location

```bash
/opt/data/profiles/orchestrator/secrets/github.env
```

## Repository list location

```bash
/opt/data/profiles/orchestrator/secrets/github-repositories.json
```

---

## First-time setup

```bash
# 1. Create the local secret files (safe, no real token written)
bash orchestrator/scripts/github_auth_bootstrap.sh --init

# 2. Paste the real fine-grained GitHub token
nano /opt/data/profiles/orchestrator/secrets/github.env

# 3. Validate that the token is no longer a placeholder
bash orchestrator/scripts/github_auth_bootstrap.sh --check

# 4. Validate repository access
python3 orchestrator/scripts/github_repo_access_check.py
```

Before the token is pasted, steps 3 and 4 are expected to fail with a clear message pointing to the edit command.

---

## Edit the repository list

```bash
nano /opt/data/profiles/orchestrator/secrets/github-repositories.json
```

Only exact GitHub repository names (`owner/repo`) are allowed. Do not guess repository names.

---

## Load token into current shell

```bash
set -a
source /opt/data/profiles/orchestrator/secrets/github.env
set +a
```

After sourcing, `GITHUB_TOKEN` and `GH_TOKEN` are available. Scripts and agents should read the env file directly rather than requiring it to be sourced.

---

## Required GitHub token permissions

For a fine-grained GitHub token, grant access at least to:

- `GoLukeEnviro/trading-hub`
- `GoLukeEnviro/ai4trade-bot`
- `GoLukeEnviro/TradeAgentsView_Control_Center`
- `GoLukeEnviro/Algorithmisches_Trading`

Required repository permissions:

| Permission    | Level          |
| ------------- | -------------- |
| Metadata      | Read           |
| Contents      | Read and write |
| Issues        | Read and write |
| Pull requests | Read and write |
| Actions       | Read (optional, useful for CI inspection) |

Do not grant broader permissions unless explicitly needed.

---

## Scripts

### `orchestrator/scripts/github_auth_bootstrap.sh`

| Flag | Purpose |
| ---- | ------- |
| `--init` | Create local secret files if missing, set strict permissions. |
| `--check` | Verify that the token is present and not the placeholder. |
| `--print-source-command` | Print the command to source the env file. |
| `--print-edit-command` | Print the command to edit the token file. |
| `--print-repo-edit-command` | Print the command to edit the repo list. |

### `orchestrator/scripts/github_repo_access_check.py`

Validates every repository listed in the local JSON config via the GitHub REST API. Works without `gh`. Never prints the token.

---

## Important note about nested repositories

The Trading Hub parent repository explicitly ignores several local nested or external repositories. They must not be treated as normal subdirectories of Trading Hub.

Known nested/external repos include:

- `Agenten_Auto_Trade`
- `Polymarket-BTC-15-Minute-Trading-Bot`
- `btc5m-bot`
- `weatherbot`
- `ai-hedge-fund-crypto`

If any of these needs GitHub access from Hermes, add its **exact GitHub repository name** to:

```bash
/opt/data/profiles/orchestrator/secrets/github-repositories.json
```

Do not guess repository names. Only validate names listed in the local repo config.

---

## Safety guarantees

- The token file is created with `chmod 600`.
- The secrets directory is created with `chmod 700`.
- The bootstrap script never prints the token value.
- The access-check script never prints the token value.
- No tracked file contains a real token.
- `.gitignore` ignores `github.env`, `.env.github*`, and related local secret files.

---

## Validation

```bash
bash -n orchestrator/scripts/github_auth_bootstrap.sh
python3 -m py_compile orchestrator/scripts/github_repo_access_check.py
bash orchestrator/scripts/github_auth_bootstrap.sh --check
python3 orchestrator/scripts/github_repo_access_check.py
```

If the token is still the placeholder, the expected output is:

```text
ERROR: GitHub token is missing or still the placeholder.
Edit the token file: nano /opt/data/profiles/orchestrator/secrets/github.env
```

This is the intended behavior before a human pastes the token.

---

## Troubleshooting

| Problem | Solution |
| ------- | -------- |
| `github.env` missing | Run `bash orchestrator/scripts/github_auth_bootstrap.sh --init` |
| Token still placeholder | Run `nano /opt/data/profiles/orchestrator/secrets/github.env` |
| Repo list missing or invalid JSON | Run `nano /opt/data/profiles/orchestrator/secrets/github-repositories.json` |
| Repository not reachable | Verify token permissions and exact repo name |
| `gh` not available | The access check works without `gh` via `urllib.request` |

---

## See also

- `orchestrator/scripts/github_auth_bootstrap.sh`
- `orchestrator/scripts/github_repo_access_check.py`
- `orchestrator/config/github-repositories.example.json`
- `.gitignore` — local GitHub auth secret ignores
