# Proposals (advisory only)

Every proposal is `docs/proposals/<id>-<name>.md` with this frontmatter:

```yaml
authority: advisory
status: proposed        # proposed | REJECTED | DEFERRED | ACCEPTED_WITH_CHANGES | PROMOTED_TO_ADR
author: <name>
created_at: <utc>
affects_phases: [<ids>]
supersedes: null
```

A proposal is never binding. Only `PROMOTED_TO_ADR` plus a merged Accepted ADR
and contract/roadmap update changes direction.
