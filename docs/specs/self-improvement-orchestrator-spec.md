# Self-Improvement Orchestrator — Implementation Spec

## Purpose

This specification defines the concrete episode execution contract for the Self-Improvement Orchestrator.
It complements `ORCHESTRATOR_CHARTER.md` (vision and governance) with implementation-level behavior and artifacts.

## Episode Lifecycle

Each self-improvement episode MUST execute the lifecycle below in order:

1. **Proposal**
   - Create a proposal from forensics output and assign an episode ID.
2. **Validation**
   - Validate proposal schema completeness and authority boundaries.
3. **Backtest**
   - Execute backtest for the target bot and proposal parameters over the defined test window.
4. **Pass/Fail Evaluation**
   - Evaluate pass/fail criteria exactly as defined in this spec.
5. **Shadowlock Entry**
   - Append a `self_improvement_episode` event to shadowlock JSONL.
6. **Next Proposal**
   - Continue with next candidate from the recovery queue.

## Episode ID Format

Episode IDs MUST match:

`episode-{bot}-{YYYYMMDD}-{short-hash}`

Where:
- `{bot}` = target bot identifier
- `{YYYYMMDD}` = UTC date for episode start
- `{short-hash}` = short deterministic identifier for proposal content

## Proposal Schema

Each proposal MUST include:

- `target_bot` (string)
- `hypothesis` (string)
- `parameters_to_test` (array of objects):
  - `name`
  - `current_value`
  - `proposed_value`
- `expected_PF_floor` (number)
- `stop_conditions` (array of strings)
- `source_forensics_run_id` (string)

## Pass/Fail Criteria

### Pass Criteria (all required)

An episode is **PASS** only if all are true over the test window:

- `PF >= 1.5`
- `net_profit > 0`
- `max_DD < 10%`

### Fail Criteria

An episode is **FAIL** if either condition is true:

- `PF < 1.0`
- `max_DD >= 15%` (**hard stop**)

If neither explicit pass nor explicit fail criteria are met, status MUST be recorded as `NO_PASS` and treated as non-promotable.

## Integration Points

The orchestrator integrates with existing system artifacts as follows:

- **Reads candidates from Forensics output:**
  - `docs/context/recovery-candidates-YYYY-MM-DD.md`
- **Writes per-episode report:**
  - `docs/context/self-improvement-run-{episode_id}.md`
- **Appends immutable event to shadowlock log:**
  - `var/trading-shadowlock/logs/YYYY/MM/DD.jsonl`
- **Writes backtest reproducibility record:**
  - `var/trading-shadowlock/backtests/{episode_id}.jsonl`

## Authority Boundaries

### Permitted

- Run backtests
- Read configs
- Write to `docs/context/` and shadowlock paths
- Propose parameter changes

### Prohibited

- Modify live strategy files directly
- Place trades
- Deploy to production
- Merge PRs

## Output Artifacts Per Episode

Every episode MUST produce all artifacts below:

1. `docs/context/self-improvement-run-{episode_id}.md`
   - Human-readable report with proposal, test setup, metrics, and verdict.
2. `var/trading-shadowlock/backtests/{episode_id}.jsonl`
   - Reproducibility record (inputs, command/config snapshot, outputs).
3. Shadowlock JSONL entry with:
   - `event_type: self_improvement_episode`

## Termination Criteria

An episode is complete only when all are true:

- All pass/fail criteria were evaluated
- All required artifacts were written
- Shadowlock JSONL entry was appended
- `schema_version` is present in emitted records
