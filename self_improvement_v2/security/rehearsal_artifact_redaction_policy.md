# Rehearsal Artifact Redaction Policy

> **SI v2 — Mandatory Redaction Policy for All Rehearsal Artifacts**
>
> This policy defines what constitutes sensitive content in rehearsal
> artifacts, how sensitive content must be redacted, and the automated
> checks that enforce compliance.
>
> **All rehearsal artifacts must pass redaction checking before they
> can be included in a rehearsal proposal package.**

---

## 1. Purpose

The redaction policy ensures that:

- No API keys, secrets, passphrases, wallet addresses, private keys,
  or bot tokens appear in rehearsal artifacts.
- No absolute home directory paths (`/home/...`) or deployment paths
  (`/opt/data/`) appear in rehearsal artifacts.
- No internal IP addresses (192.168.x.x, 10.x.x.x) appear in rehearsal
  artifacts.
- All sensitive content is replaced with `[REDACTED_<type>]` placeholders.
- The automated `RedactionChecker` can verify compliance deterministically.

---

## 2. Sensitive Content Patterns

The following patterns **must be redacted** in all rehearsal artifacts:

| # | Pattern | Description | Example | Severity |
|---|---------|-------------|---------|----------|
| R-01 | `api[_-]?key` | API key identifiers | `api_key`, `api-key`, `apikey` | BLOCKER |
| R-02 | `api[_-]?secret` | API secret identifiers | `api_secret`, `api-secret`, `apisecret` | BLOCKER |
| R-03 | `passphrase` | Passphrase references | `passphrase` | BLOCKER |
| R-04 | `0x[a-fA-F0-9]{40}` | Ethereum-style wallet addresses | `0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18` | BLOCKER |
| R-05 | `-----BEGIN.*PRIVATE KEY-----` | Private key blocks | `-----BEGIN RSA PRIVATE KEY-----` | BLOCKER |
| R-06 | `[0-9]{8,10}:[a-zA-Z0-9_-]{35}` | Bot/discord tokens | `12345678:ABCdefGHIjklmNOPqrstUVwxyzABCDEF` | BLOCKER |
| R-07 | `/home/.*?/projects/` | Absolute home paths | `/home/hermes/projects/trading/` | BLOCKER |
| R-08 | `/opt/data/` | Deployment paths | `/opt/data/config.json` | BLOCKER |
| R-09 | `192\.168\.` | Internal IP (class C) | `192.168.1.100` | WARNING |
| R-10 | `10\.\d{1,3}\.\d{1,3}\.\d{1,3}` | Internal IP (class A) | `10.0.0.5` | WARNING |

---

## 3. Safe Content (Not Redacted)

The following are **exempt** from redaction checking:

- Content already inside `[REDACTED_*]` placeholders (e.g. `[REDACTED_API_KEY]`,
  `[REDACTED_PATH]`, `[REDACTED_IP]`).
- Content inside explicit **"Forbidden Conditions"** sections of governance
  docs, where sensitive patterns are used as examples or in condition
  descriptions.
- Relative paths (e.g. `./config.json`, `src/si_v2/main.py`).

---

## 4. Redaction Format

All sensitive content must be replaced with a standard placeholder:

```
[REDACTED_<TYPE>]
```

Where `<TYPE>` is one of:

| Type | Applies To |
|------|------------|
| `API_KEY` | API keys and secrets |
| `PASSPHRASE` | Passphrases |
| `WALLET` | Wallet addresses |
| `PRIVATE_KEY` | Private key blocks |
| `TOKEN` | Bot/discord tokens |
| `PATH` | Absolute home or deployment paths |
| `IP` | Internal IP addresses |
| `CREDENTIAL` | Any other credential |

---

## 5. Automated Enforcement (RedactionChecker)

The `RedactionChecker` class in `rehearsal/redaction_checker.py`
implements this policy. Key behaviour:

- `check_artifact(text: str) -> list[Finding]`: Scans text for unredacted
  sensitive patterns.
- **BLOCKED** findings are returned for any unredacted BLOCKER-severity pattern.
- **WARNING** findings are returned for absolute paths (YELLOW severity).
- Content inside `[REDACTED_*]` placeholders is skipped.
- Content inside explicit "Forbidden Conditions" sections is skipped.
- Findings are returned in **deterministic order** (sorted by reason_code).
- All findings use `ReasonCode` from `rehearsal.planning_models`.

---

## 6. Policy Exceptions

Any exception to this policy must be:

1. Documented in the rehearsal proposal package.
2. Approved by a human operator.
3. Time-boxed with an explicit expiration date.
4. Reviewed after the rehearsal concludes.

---

## 7. Change Log

| Date | Change | Author |
|------|--------|--------|
| YYYY-MM-DD | Initial version | SI v2 (#146) |

---

*Maintained at `self_improvement_v2/security/rehearsal_artifact_redaction_policy.md`*
*Created as part of #146 — Redaction Checker and Policy*
