# S4 C04 controlled real validation R1

This record reports the one authorized historical-only C04 validation
execution. It is an execution record, not a model-promotion or TEST-
authorization record.

## Frozen execution authority

- Candidate: `04_yield_parameter`
- Experiment plan: `v0.3-experiment-plan-v2`
- Guardrail policy: `v0.3-s4-guardrail-policy-v3-sparse-horizon`
- Evaluation surface: `V0_3_S4_SOURCE002_SPARSE_HORIZON_7_14_21_V1`
- Horizons: 7, 14, 21
- Target rows: 688
- Complete daily rowset authority: false
- Missing-day zero fill: false
- C04 manifest: `1e3433b9216f8ebe63db44ba0bc1353e1d4664cef3c1cc3f2a57bb794fe280ee`
- Execution code commit: `0394d63d83d78d95064689d0c0e58c652d4db8df`

The four authorized values were used exactly once and in order:

| Run | Multiplier | Evaluation ID | Execution | Eligibility |
| --- | ---: | --- | --- | --- |
| 1 | 3.802757 | `v0-3-s4-c04-v3-real-validation-01` | COMPLETED | BLOCKED |
| 2 | 4.961884 | `v0-3-s4-c04-v3-real-validation-02` | COMPLETED | BLOCKED |
| 3 | 5.182238 | `v0-3-s4-c04-v3-real-validation-03` | COMPLETED | BLOCKED |
| 4 | 4.152099 | `v0-3-s4-c04-v3-real-validation-04` | COMPLETED | BLOCKED |

All four STARTED events were `NORMAL_RUN` events, used the same execution
code SHA, and received a durable terminal event. No retry or additional run
was performed.

## Paired metrics

The incumbent reference was generated once from the same SOURCE-002 TRAIN,
cutoff, 688 target identities, horizon set, and metric contract. Its frozen
identities are recorded in the machine-readable evidence. Incumbent metrics
were identical for all four comparisons:

- daily WAPE: `0.773022`
- daily MAE: `952.100208`
- P80 coverage: `0.139535`
- P90 coverage: `0.223837`

Candidate daily metrics were:

| Run | Daily WAPE | Daily MAE | P80 | P90 |
| --- | ---: | ---: | ---: | ---: |
| 1 | 0.725160 | 893.149826 | 0.585756 | 0.665698 |
| 2 | 0.885404 | 1090.516549 | 0.655523 | 0.726744 |
| 3 | 0.921748 | 1135.280015 | 0.665698 | 0.735465 |
| 4 | 0.766618 | 944.212641 | 0.613372 | 0.686047 |

Runs 1 and 4 improved the primary and point metrics, but all runs were
blocked by the existing required-breakdown policy (`BELOW_MINIMUM`). The
policy was not changed during this execution. Complete-window metrics remain
`NOT_COMPUTABLE` and diagnostic-only with reason
`COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE`; no missing days were filled or
interpolated.

Therefore:

```text
C04_ELIGIBLE_RUN_COUNT=0
C04_BEST_RUN_ORDINAL=NONE
C04_VALIDATION_OUTCOME=BLOCKED
```

This is not a selected model and does not authorize TEST, promotion, or
production rollout.

## Durable budget reconciliation

The PostgreSQL authority was read before and after every run. The observed
progression was `4/28`, `5/27`, `6/26`, `7/25`, and `8/24` for effective
consumed/remaining budget. Final readback:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
C04_CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
ACCEPTED_LAST_GLOBAL_EVALUATION_ORDINAL=4
```

TEST remained sealed. No C01 rerun, other candidate, TEST evaluation, model
promotion, or merge/Ready action occurred.
