# Incident Report Directory Convention

> **Directory:** `docs/incidents/`
> **Purpose:** Post-mortem reports for trading incidents
> **Created:** 2026-07-03 (C3 Rollback Readiness — #443)

---

## File Naming Convention

```
incident-<YYYY-MM-DD>-<short-description>.md
```

Examples:
- `incident-2026-07-03-canary-rollback.md`
- `incident-2026-07-04-exchange-outage.md`

## Required Sections

Every incident report must include:

| Section | Description |
|---------|-------------|
| **Trigger event and timestamp** | What happened and when |
| **Kill switch state** | Mode at time of trigger |
| **All actions taken** | Chronological log of operator/system actions |
| **Current bot/position state** | Status of all affected bots |
| **Root cause analysis** | Why the incident occurred |
| **Recovery actions** | What was done to restore normal operation |
| **Prevention** | What changes prevent recurrence |

## Template

```markdown
# Incident: <YYYY-MM-DD> — <short-description>

**Status:** Open | Resolved
**Severity:** Low | Medium | High | Critical
**Reported by:** <name>
**Date:** <YYYY-MM-DD>

---

## Summary

<one-paragraph summary>

## Timeline

| Time (UTC) | Event |
|------------|-------|
| HH:MM | <event> |

## Kill Switch State

- **Mode:** NORMAL | HALT_NEW | EMERGENCY
- **Triggered at:** <timestamp>
- **Triggered by:** <source>

## Actions Taken

1. <action>
2. <action>

## Root Cause

<analysis>

## Recovery

<what was done to restore>

## Prevention

<changes to prevent recurrence>

## References

- Emergency record: `var/si_v2/emergency/emergency_<timestamp>.json`
- Related issues: #<number>
```

## Lifecycle

| Event | Action |
|-------|--------|
| Incident occurs | Create incident report in this directory |
| Investigation complete | Fill root cause and prevention sections |
| Incident resolved | Set status to Resolved |
| Review | Reports are preserved — never deleted |

## Safety Rules

- Reports are **tracked in git** (this directory is under `docs/`)
- Never include API keys, passwords, or secrets in reports
- Reference emergency audit records by path (not by copying content)
- Link to related GitHub issues for traceability
