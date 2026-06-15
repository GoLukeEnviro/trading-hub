# Contributing

This document defines the conventions and workflow for contributing to the
Trading Hub repository.

---

## Branch naming

Use one of these prefixes followed by a short `kebab-case` description:

| Prefix | Purpose |
|--------|---------|
| `feat/` | New feature or capability |
| `fix/` | Bug fix or regression repair |
| `docs/` | Documentation only changes |
| `chore/` | Maintenance, cleanup, deps |
| `ci/` | CI/CD workflow changes |
| `test/` | Test additions or fixes |

Examples:
```
feat/si-v2-active-cycle-runner
fix/primo-signal-staleness-check
docs/kill-switch-runbook
chore/cleanup-archive-reports
```

---

## Commit format

```
type(scope): description

Optional body explaining motivation and context.
```

- **type:** `feat`, `fix`, `docs`, `chore`, `ci`, `test`
- **scope:** component or subsystem (e.g., `si-v2`, `freqtrade`, `docs`, `kill-switch`)
- **description:** present tense, lowercase, no period at end
- **body:** optional, explain *why* not just *what*

Examples:
```
feat(si-v2): add multi-bot authenticated telemetry proof
fix(kill-switch): handle missing fleet_risk_state.json gracefully
docs(ARCHITECTURE): add kill-switch wiring Mermaid diagram
```

---

## PR workflow

1. Create a feature branch from `main`
2. Make changes, commit using the format above
3. Verify **all** CI gates pass (main-gate workflow must be green)
4. Open a PR against `main` with a descriptive title and summary of changes
5. Squash-merge to `main` only after review

### PR checklist

Before opening a PR, verify:

- [ ] `main-gate` CI is green (or CI is not applicable to this change)
- [ ] Local validation commands are listed in the PR body
- [ ] New modules, routes, jobs, scripts, integrations, or dependencies include tests or an explicit validation plan
- [ ] New dependencies include a reason, scope, and reproduction command
- [ ] `python3 scripts/secret_scan.py --tracked` passes for repository changes
- [ ] No `dry_run=false` changes in the diff
- [ ] No credentials, secrets, or API keys in the diff
- [ ] No force-push or history rewrite
- [ ] No `git add .` — files are staged explicitly by path
- [ ] `docs/context/` is updated if the change is meaningful
- [ ] `docs/state/current-operational-state.md` is updated if runtime state changed

---

## Code standards

- **Python:** Ruff linting (line-length 120). Run `ruff check` before committing.
- **Markdown:** Prefer clean, readable markdown. Mermaid diagrams for architecture.
- **Docs:** Keep root docs (`README.md`, `AGENTS.md`, `SOUL.md`) in sync with reality.
  Update `docs/context/` after meaningful changes.

---

## Safety rules (non-negotiable)

- **Never** set `dry_run=false`
- **Never** commit secrets, API keys, or credentials
- **Never** force-push, `git reset --hard`, or `git clean -fdx`
- **Never** `git add .` — stage files explicitly by path
- **Never** restart Docker containers without explicit approval
- **Never** modify Freqtrade configs, strategy logic, or signal thresholds without approval
- **Respect the Kill Switch** — if `HALT_NEW` or `EMERGENCY` is active, no new entries may be proposed or applied

---

## Documentation structure

```
trading-hub/
├── README.md                   # Repository overview, component table
├── CHANGELOG.md                # Keep-a-Changelog
├── AGENTS.md                   # Agent safety and architecture guide
├── SOUL.md                     # Project identity and operating principles
├── docs/
│   ├── README.md               # Documentation index
│   ├── ARCHITECTURE.md         # System architecture (Mermaid)
│   ├── state/                  # Operational snapshots
│   ├── runbooks/               # Operational runbooks
│   ├── decisions/              # ADR decision records
│   ├── context/                # Append-only historical reports
│   └── archive/                # Archived historical documents
└── self_improvement_v2/
    └── README.md               # SI v2 module map and entry points
```
