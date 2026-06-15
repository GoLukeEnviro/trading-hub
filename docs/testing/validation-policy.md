# Validation Coverage Policy

Issues: #250, #254

Every new module, integration, route, job, dependency, script, or operational artifact must ship with validation evidence in the same PR.

## Acceptable validation types

At least one of the following must be present, and safety-critical changes should include more than one:

- unit test
- integration test using local fixtures/mocks only
- contract test
- smoke test
- dry-run proof with no Docker/runtime mutation unless explicitly approved
- typecheck or compile check
- lint check
- explicit validation plan when automation is not possible

## Required PR notes

PRs must document:

1. what changed
2. why the validation type is sufficient
3. exact local reproduction commands
4. whether Docker/runtime mutation is required
5. rollback path for operational changes
6. for new dependencies: reason, scope, and validation command

## Exceptions

An exception is allowed only when it includes a written rationale and a follow-up issue. Examples:

- third-party service unavailable in CI
- runtime-only proof requiring explicit L3 approval
- historical documentation update with no executable path

Exceptions must not be used to bypass live-trading, credential, or destructive-operation safety gates.

## Local baseline commands

```bash
python3 -m pip install -e ".[dev]"
python3 scripts/secret_scan.py --tracked
python3 -m compileall bridge primo shadowlock intelligence orchestrator tests scripts
python3 -m pytest tests -q
PYTHONPATH=self_improvement_v2/src:self_improvement_v2 python3 -m pytest self_improvement_v2/tests -q
PYTHONPATH=/home/hermes/projects/trading python3 -m pytest orchestrator/control/tests -q
```

## CI integration

The always-reporting `main-gate` workflow must remain the required branch-protection check. Path-filtered workflows may provide additional coverage, but they must not be the only required check because skipped checks can deadlock unrelated PRs.
