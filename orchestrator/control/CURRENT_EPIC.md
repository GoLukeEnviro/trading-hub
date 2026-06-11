# Current Epic — SI v2 Planning Automation and Quality

## Scope

Issues #143–#154.

## Outcome

Turn the static rehearsal-planning layer into a deterministic, machine-checkable, offline quality system.

## Core Deliverables

- proposal package schema;
- typed package and finding models;
- semantic consistency engine;
- offline redaction and relative-path checks;
- end-to-end planning validator;
- package checker command with stable return codes;
- synthetic negative-test fixture corpus;
- deterministic JSON and Markdown reports;
- review checklist and package index;
- offline observation interface definitions;
- golden regression suite;
- expanded least-privilege offline CI.

## Required Quality Bar

- no unresolved BLOCKER or MAJOR review finding;
- deterministic outputs;
- fail-closed invalid-package behavior;
- synthetic data only;
- all tests and static validation green;
- one review-ready PR;
- PR remains unmerged.
