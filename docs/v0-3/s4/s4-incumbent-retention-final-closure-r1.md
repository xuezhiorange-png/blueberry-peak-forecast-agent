# V0.3 S4 incumbent-retention final closure

This document records the current terminal disposition of the frozen V0.3 S4
experiment plan. It is an append-only governance summary and does not rewrite
the historical candidate, execution, or evidence records.

## Decision

The canonical #602 closure reports that none of the eight candidates is
currently runnable under the frozen V2/V4 plan. Therefore S4 is closed with no
admissible replacement selected:

```text
S4_FINAL_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
CURRENT_FROZEN_PLAN_HAS_NO_REMAINING_EXECUTABLE_CANDIDATE=true
NEXT_EXECUTABLE_CANDIDATE=NONE
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
```

This is not a validation win for the incumbent. The only permitted retention
reason is:

```text
NO_ADMISSIBLE_REPLACEMENT_SELECTED_UNDER_FROZEN_PLAN
```

The incumbent remains the existing operational authority:

```text
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
INCUMBENT_RETAINED=true
INCUMBENT_IS_S4_SELECTED_CANDIDATE=false
INCUMBENT_DECLARED_VALIDATION_WINNER=false
```

## Source of candidate dispositions

The closure is built by
`backend.app.s4_remaining_candidate_viability.build_frozen_s4_closure`.
The final closure module consumes that object rather than maintaining a second
eight-candidate status table. At the closure point the dispositions are:

| Candidate | Current V4 runnability | Reason |
| --- | --- | --- |
| `01_parameter_calibration` | false | `CANDIDATE_01_RERUN_FORBIDDEN` |
| `02_quantile_calibration` | false | `C02_QUANTILE_ONLY_CANDIDATE_CANNOT_STRICTLY_IMPROVE_V4_PRIMARY_POINT_METRIC` |
| `03_phenology_offset` | false | `C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY` |
| `04_yield_parameter` | false | `C04_EXHAUSTED_EVIDENCE_INSUFFICIENT` |
| `05_marketable_rate` | false | `C05_CANONICAL_MARKETABLE_RATE_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE` |
| `06_weather_response` | false | `C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY` |
| `07_harvest_efficiency` | false | `C07_CANONICAL_HARVEST_EFFICIENCY_AUTHORITY_UNAVAILABLE_IN_SOURCE002_HISTORICAL_LANE` |
| `08_residual_feature` | false | `V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED` |

If the consumed canonical closure ever reports a runnable candidate, or a
non-`NONE` next candidate, `build_s4_final_closure()` raises a blocking error
instead of issuing this terminal object. A supplied selected candidate also
raises `S4SelectionStateConflict`; selection belongs to a separate governance
decision.

## Frozen plan and selection boundary

The current plan and V4 policy identities remain unchanged:

```text
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v2
EXPERIMENT_PLAN_HASH=c2bfab4ec38b4ca640f62d061494961c5b49afe5b52fa675326aa80fdf5f8ad9
EXPERIMENT_PLAN_EXECUTION_STATUS=CLOSED
EXPERIMENT_PLAN_REOPEN_AUTHORIZED=false
V4_GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor
V4_GUARDRAIL_POLICY_HASH=f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2
NEW_EXPERIMENT_PLAN_AUTHORIZED=false
NEW_EXPERIMENT_PLAN_VERSION=NOT_ISSUED
NEW_GUARDRAIL_POLICY_AUTHORIZED=false
```

No multiple-comparison selection is issued. In particular, no ranking,
Holm-Bonferroni adjustment, or statistical claim that the incumbent is
superior is made:

```text
MULTIPLE_COMPARISON_FINAL_SELECTION_PERFORMED=false
HOLM_ADJUSTMENT_PERFORMED=false
MULTIPLE_COMPARISON_REASON=NO_CANDIDATE_SELECTION_ISSUED
```

## TEST, model, and pilot boundaries

TEST remains sealed. The closure does not select rows, load labels or bytes, or
perform scoring. No model or parameter mutation, pilot deployment, or pilot
approval is authorized.

```text
TEST_EVALUATION_AUTHORIZED=false
TEST_ROWS_SELECTED=false
TEST_LABELS_LOADED=false
TEST_BYTES_READ=false
TEST_SCORING_PERFORMED=false
TEST_REMAINS_SEALED=true
S4_MODEL_CHANGE_AUTHORIZED=false
S4_PARAMETER_CHANGE_AUTHORIZED=false
PRODUCTION_MODEL_CHANGE_PERFORMED=false
PRODUCTION_PARAMETER_CHANGE_PERFORMED=false
MODEL_APPROVED_FOR_PILOT=false
PILOT_DEPLOYMENT_AUTHORIZED=false
```

`INCUMBENT_RETAINED=true` means the existing authority is left unchanged; it
does not authorize a new deployment or a TEST comparison.

## Validation budget

This task has no live PostgreSQL readback and writes no ledger event. The
numbers below are the last accepted durable snapshot already bound by #602 and
the immutable C04 execution evidence:

```text
DURABLE_BUDGET_READBACK_AVAILABLE=false
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
REMAINING_VALIDATION_BUDGET_UNUSED=24
BUDGET_CARRY_FORWARD_AUTHORIZED=false
BUDGET_DELTA=0
NEW_VALIDATION_EXECUTION=false
NEW_VALIDATION_SCORING=false
NEW_STARTED_EVENT_COUNT=0
NEW_TERMINAL_EVENT_COUNT=0
```

The provenance is
`docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json` with SHA-256
`78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3`.
`REMAINING_VALIDATION_BUDGET_UNUSED=24` is a status statement, not an
automatic carry-forward authorization. Any future experiment plan requires a
new governance decision and budget reconciliation.

## Historical evidence preservation

The C01, C03, C04 R1/R2/R3/R4/R5, and #602 evidence artifacts are immutable for
this task. This closure only adds a current terminal projection. It does not
rewrite any provisional, blocked, exhausted, or audit-only result into a
selection result.

## Execution boundary

No candidate execution, validation scoring, TEST opening, new experiment plan,
new guardrail policy, model change, parameter change, or pilot deployment was
performed. The stopping point is:

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_FINAL_CLOSURE_REVIEW
```
