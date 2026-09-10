# S4 C04 validation eligibility policy correction R2

## Scope and non-execution boundary

This correction is a selection-policy readjudication of the four completed C04
R1 runs. It does not re-run a scorer, read SOURCE-002 or VALIDATION rows, call
`S4CandidateExecutionAuthority.execute`, or create STARTED/terminal events.
The original R1 evidence remains immutable and continues to describe the
policy that was in force at execution time.

The durable ledger therefore remains unchanged:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
C04_CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
R2_BUDGET_DELTA=0
TEST_ACCESS_REQUESTED=false
TEST_REMAINS_SEALED=true
```

## Defect corrected

The former V3 wiring treated every breakdown cell with fewer than ten
comparable rows as a global candidate blocker. The frozen S3 reporting
contract gives that threshold a reporting purpose only. V4 therefore retains
every cell and records:

```text
comparable_rows < 10
reporting_status=INSUFFICIENT_SAMPLE
reporting_reason=BELOW_MINIMUM
selection_blocking=false
```

This correction does not relax the structural or global data-quality gates.
Missing, unknown, duplicate, empty, or conflicting required axes still fail
closed; silent exclusion still fails; and the global coverage, canonical-group
coverage, and missing-data thresholds remain mandatory.

The three complete-window metrics remain honest sparse-surface diagnostics:

```text
cumulative_absolute_error_kg=NOT_COMPUTABLE
single_day_peak_quantity_absolute_error_kg_q=NOT_COMPUTABLE
sustained_7day_quantity_absolute_error_kg_q=NOT_COMPUTABLE
selection_blocking=false
diagnostic_only=true
reason=COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE
```

No missing day is zero-filled or interpolated.

## Versioning and replayability

V1, V2, and V3 policy identities are preserved byte-for-byte. The corrected
policy is a new V4 identity whose predecessor is the V3 sparse-horizon policy:

```text
V4_GUARDRAIL_POLICY_VERSION=v0.3-s4-guardrail-policy-v4-breakdown-reporting-floor
V4_GUARDRAIL_POLICY_HASH=f2b5c808d5a72170f055f891422f4253834a977cd5c74b450c8e4546653f46d2
PREDECESSOR_POLICY_VERSION=v0.3-s4-guardrail-policy-v3-sparse-horizon
PREDECESSOR_POLICY_HASH=004be89a726ea4afd90ac895ea10f885f749b2f222e0fca5a67d57ba4e2bd3e0
```

The V4 execution-gate route is explicit, but this R2 correction does not
authorize a new execution. The re-adjudication helper accepts only frozen R1
metric observations and uses no dataset or scorer entry point.

## Pure R1 readjudication

The frozen R1 facts are compared against the same incumbent:

```text
INCUMBENT_WAPE=0.773022
INCUMBENT_MAE=952.100208
INCUMBENT_P80=0.139535
INCUMBENT_P90=0.223837
```

Applying V4 yields:

| Run | Multiplier | WAPE | MAE | V4 eligibility |
| --- | ---: | ---: | ---: | --- |
| 1 | 3.802757 | 0.725160 | 893.149826 | PASS |
| 2 | 4.961884 | 0.885404 | 1090.516549 | FAIL |
| 3 | 5.182238 | 0.921748 | 1135.280015 | FAIL |
| 4 | 4.152099 | 0.766618 | 944.212641 | PASS |

The resulting readjudication is:

```text
C04_ELIGIBLE_RUN_COUNT=2
C04_BEST_VALIDATION_RUN=1
C04_BEST_MULTIPLIER=3.802757
C04_BEST_DAILY_WAPE=0.725160
C04_BEST_DAILY_MAE=893.149826
C04_VALIDATION_OUTCOME=HAS_ELIGIBLE_WINNER
GLOBAL_SELECTION_ISSUED=false
FINAL_S4_WINNER_ISSUED=false
TEST_AUTHORIZATION=false
```

`C04_BEST_VALIDATION_RUN` is only the best eligible run within the already
completed C04 validation set. It is not a final S4 model selection, TEST
authorization, or production-model decision.

## Evidence and verification

The machine-readable correction is
`docs/v0-3/s4/evidence/s4-c04-validation-eligibility-policy-correction-r2.json`.
It records the R1 evidence digest, the as-executed V3 adjudication, the V4
policy identity, and the pure R2 result. The R1 evidence file is not mutated.

The focused regression suite proves policy preservation, V4 dispatch,
reporting-only handling of small cells, fail-closed structural gates, the
expected four-run readjudication, and no scorer/dataset/ledger access.

```text
NEW_VALIDATION_EXECUTION=false
NEW_VALIDATION_SCORING=false
NEW_STARTED_EVENT_COUNT=0
NEW_TERMINAL_EVENT_COUNT=0
VALIDATION_DATA_REREAD=false
TEST_ACCESS_REQUESTED=false
```

This correction stops at the coordinator review gate.
