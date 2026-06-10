# Rehearsal Artifact Redaction Policy

> **SI v2 — Mandatory Redaction Rules for Rehearsal Artifacts**
>
> Defines sensitive-material categories, approved redaction placeholders,
> sanitised relative-path requirements, and fail-closed behaviour when
> unsafe artifact content is detected.
>
> **This policy does not access the live environment.**
> It defines static rules for offline artifact review.

---

## 1. Purpose

The redaction policy ensures that:

- Sensitive material is identified and removed from rehearsal artifacts
  before they are committed, archived, or shared.
- Redaction is deterministic and verifiable.
- Unsafe artifacts fail closed (blocked from proceeding) rather than
  being released with partial or incomplete redaction.
- Paths are sanitised to relative, non-identifying forms.

---

## 2. Sensitive-Material Categories

The following categories of sensitive material **must be redacted**
from all rehearsal artifacts:

| # | Category | Examples | Detection Method |
|---|----------|----------|-----------------|
| SM-01 | Exchange API keys | `apiKey`, `apiSecret`, `passphrase` | Pattern match |
| SM-02 | Wallet addresses | `0x[a-fA-F0-9]{40}`, `bc1[a-z0-9]{38}` | Pattern match |
| SM-03 | Private keys / secrets | `-----BEGIN.*PRIVATE KEY-----` | Pattern match |
| SM-04 | Bot tokens | `[0-9]{8,10}:[a-zA-Z0-9_-]{35}` (Telegram) | Pattern match |
| SM-05 | Absolute home paths | `/home/hermes`, `/root` | Pattern match |
| SM-06 | Absolute project paths | `/home/hermes/projects/trading` | Pattern match |
| SM-07 | Environment variable values | `export SECRET=...`, `password=...` | Pattern match |
| SM-08 | Docker container IDs | Long hex strings matching container IDs | Pattern match |
| SM-09 | IP addresses (internal) | `192.168.x.x`, `10.x.x.x`, `172.16-31.x.x` | Pattern match |
| SM-10 | Hostnames | Server hostnames, FQDNs | Pattern match |

---

## 3. Approved Redaction Placeholders

Redacted content must be replaced with one of the following
deterministic placeholders:

| Original Category | Placeholder | Example Result |
|-------------------|-------------|----------------|
| Exchange API key | `[REDACTED_API_KEY]` | `"apiKey": "[REDACTED_API_KEY]"` |
| Exchange API secret | `[REDACTED_API_SECRET]` | `"apiSecret": "[REDACTED_API_SECRET]"` |
| Wallet address | `[REDACTED_WALLET]` | `"0x...[REDACTED_WALLET]"` |
| Private key | `[REDACTED_PRIVATE_KEY]` | `[REDACTED_PRIVATE_KEY]` |
| Bot token | `[REDACTED_BOT_TOKEN]` | `[REDACTED_BOT_TOKEN]` |
| Absolute home path | `~/` or `/home/user` replacement | `~/config.json` |
| Absolute project path | `./` or relative path | `./config/config.json` |
| Environment secret value | `[REDACTED_ENV_VALUE]` | `password=[REDACTED_ENV_VALUE]` |
| Container ID | Container name or `[REDACTED_CID]` | `trading-freqforge-1` |
| Internal IP address | `[REDACTED_IP]` | `[REDACTED_IP]:8080` |
| Hostname | `[REDACTED_HOSTNAME]` | `[REDACTED_HOSTNAME].local` |

**Redaction must be lossless** — the same placeholder must be used
for the same original value throughout an artifact.

---

## 4. Sanitised Path Requirements

All absolute paths in rehearsal artifacts must be converted to
relative paths:

| Original | Sanitised |
|----------|-----------|
| `/home/hermes/projects/trading/config/config.json` | `config/config.json` |
| `/opt/data/...` | `data/...` (project-relative) |
| `/home/hermes/projects/trading/self_improvement_v2/...` | `self_improvement_v2/...` |

Rules:
- Paths must not contain usernames, real user home directories,
  or deployment-specific directory names.
- The project root should be represented as `.` or omitted.
- Subdirectories under the project root should use relative paths.

---

## 5. Fail-Closed Behaviour

| Condition | Verdict | Action |
|-----------|---------|--------|
| Unsafe artifact content detected (unredacted SM-01..SM-10) | **RED** | Do not proceed. Redact and re-validate. |
| Redaction incomplete (missing placeholder) | **RED** | Do not proceed. Complete redaction. |
| Placeholder used inconsistently (same value, different placeholders) | **YELLOW** | Warn. Fix for consistency. |
| Path not sanitised | **YELLOW** | Warn. Convert to relative path. |
| Redaction policy not referenced | **YELLOW** | Warn. Add policy reference to artifact. |
| No sensitive material found (clean artifact) | **GREEN** | Proceed. |

---

## 6. Unsafe Detection Patterns

The following regular expressions define what constitutes unsafe
artifact content. Artifacts matching any pattern (outside structured
Forbidden Conditions sections) must be treated as unsafe:

| Pattern ID | Regex | Category |
|-----------|-------|----------|
| `UP-01` | `api[_-]?key\s*[:=]\s*["\']?[^"\' ]{8,}` | SM-01 |
| `UP-02` | `api[_-]?secret\s*[:=]\s*["\']?[^"\' ]{8,}` | SM-01 |
| `UP-03` | `passphrase\s*[:=]\s*["\']?[^"\' ]{8,}` | SM-01 |
| `UP-04` | `0x[a-fA-F0-9]{40}\b` | SM-02 |
| `UP-05` | `-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----` | SM-03 |
| `UP-06` | `\b[0-9]{8,10}:[a-zA-Z0-9_-]{35}\b` | SM-04 |
| `UP-07` | `/home/[^/\s]+/projects/` | SM-05 |
| `UP-08` | `/opt/data/` | SM-06 |
| `UP-09` | `192\.168\.` | SM-09 |
| `UP-10` | `10\.\d{1,3}\.\d{1,3}\.\d{1,3}` | SM-09 |

---

## 7. Offline Fixtures

Safe and unsafe fixtures are maintained for validation:

- **Safe fixture**: All sensitive material redacted, all paths relative,
  policy referenced. Expected verdict: **GREEN**.
- **Unsafe fixture**: Contains unredacted API key and absolute home path.
  Expected verdict: **RED** — must fail closed.

Fixtures are stored under `tests/fixtures/redaction/`.

---

## 8. No-Live-Access Statement

> **This policy defines static redaction rules only.**
> It does not access the live environment, read credentials, or
> expose sensitive material.
> All validation is performed against offline artifact content.
>
> **This policy does not approve production trading, runtime
> activation, or deployment actions.**

---

## 9. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#146) |

---

*Maintained at `self_improvement_v2/security/rehearsal_artifact_redaction_policy.md`*
*Created as part of #146 — Rehearsal Artifact Redaction Policy*
