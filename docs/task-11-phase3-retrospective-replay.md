# Task 11 Phase 3 — retrospective_replay and Task 9 replay authority

Refs: #29, #21

## Governance status

This file is a Phase 3 bootstrap note for the Draft PR only.

Implementation status: **NOT STARTED**

This branch starts from Task 11 Phase 2 merge commit:

```text
67a595704b8582d9c62ca6d876a5fd8249e5767c
```

## Authorized scope

Phase 3 is limited to:

- `retrospective_replay` execution-mode semantics;
- leakage-safe replay source visibility;
- Task 9 replay authority creation through existing Task 9 service paths;
- downstream Task 10 binding to the replay-produced Task 9 authority;
- immutable replay metadata and integrity reload evidence.

## Explicit exclusions

This phase must not implement:

- evaluation materialization;
- Task 3 actuals;
- metrics;
- exports;
- CLI;
- API;
- frontend;
- Task 12;
- Task 13;
- production scheduling;
- drift monitoring;
- alerting;
- new Task 8 natural maturity behavior;
- new Task 9 harvest-state equations;
- new Task 10 residual-model semantics.

## Next required step

Before production code changes, produce a design amendment / implementation plan covering:

1. execution-mode separation between `historical_observed` and `retrospective_replay`;
2. replay runtime metadata boundaries;
3. Task 9 replay authority lifecycle;
4. Task 10 binding to replay-produced Task 9 authority;
5. blocker taxonomy and PostgreSQL acceptance evidence.
