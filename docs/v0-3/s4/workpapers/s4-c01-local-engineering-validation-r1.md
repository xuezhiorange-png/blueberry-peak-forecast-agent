# S4-C01 local engineering validation R1

## Disposition

This workpaper records the authorized local engineering lane only. It is not
production forecast authority, retained historical PIT authority, pilot
approval, or a final model-selection decision.

```text
TASK_ID=V0_3_S4_LOCAL_ENGINEERING_VALIDATION_BOOTSTRAP_AND_C01_EXECUTION_R1
BASE_MAIN_SHA=77e3d8ac63d794babfe0c8549fd34d0467f0d57e
EVALUATION_LANE=LOCAL_ENGINEERING_REPLAY
C01_RESULT_REVIEWED=true
C01_RESULT_ACCEPTED_FOR_SELECTION=false
C01_BUDGET_CONSUMPTION_RETAINED=true
C01_NUMERIC_EVIDENCE_INVALIDATED_FOR_GUARDRAIL_AUTHORITY=true
ORIGINAL_LOCAL_RUN_METRICS_PRESERVED_FOR_AUDIT=true
ORIGINAL_LOCAL_RUN_METRICS_SELECTION_AUTHORITY=false
ORIGINAL_LOCAL_RUN_METRICS_GUARDRAIL_AUTHORITY=false
EXECUTION_GATE_RECONCILIATION=FAIL
VALIDATION_LEDGER_RECONCILIATION=FAIL
BLOCK_REASON=METRIC_AND_EXECUTION_CONTRACT_INVALID
TEST_REMAINS_SEALED=true
TEST_EVALUATION_PERFORMED=false
PRODUCTION_DATABASE_MUTATION_PERFORMED=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The local PostgreSQL instance was created as an isolated user-owned database
named `blueberry_peak_s4_local_engineering` on loopback port `55435`. The
repository Alembic head applied was
`0031_forecast_authority_task10_extension`. No production endpoint, historical
authority store, Docker volume, or TEST payload was used.

## Frozen SOURCE-002 inputs

The raw object was verified before the local rebuild:

| identity | value |
| --- | --- |
| raw object SHA-256 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| raw object byte count | `28668416` |
| declared raw row count | `233171` |
| materialized dataset identity | `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785` |
| TRAIN rows / bytes | `16224 / 9087071` |
| TRAIN content SHA-256 | `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2` |
| VALIDATION rows / bytes | `8006 / 4484905` |
| VALIDATION content SHA-256 | `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06` |
| TEST rows | `0` |
| controlled rebuild parity | `PASS` |

The existing controlled Lane A → Lane B → Lane C → Lane D path was reused.
The runner reads only the persisted TRAIN and VALIDATION partition bytes from
the isolated database and checks them against the frozen partition hashes.
TEST metadata is checked only for zero rows; TEST content is not parsed or
scored.

## Replay contract

The regenerated incumbent is explicitly classified as
`LOCAL_ENGINEERING_REPLAY`, with model identity `V0_2_CURRENT_MODEL`. It uses
the current frozen configuration:

```text
curve.spline_knot_count=6
curve.ridge_alpha=0.10
random_seed=20260624
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
ORIGINAL_RUN_NO_FUTURE_LABEL_LEAKAGE_STATUS=NOT_ESTABLISHED
CORRECTED_IMPLEMENTATION_NO_FUTURE_LABEL_LEAKAGE_VERIFIED=true
NO_TEST_ACCESS=true
```

The incumbent replay was run twice. Row-set identity, forecast identity,
metrics, and aggregate payloads were exactly equal:

```text
LOCAL_INCUMBENT_REPLAY_STATUS=PASS
LOCAL_INCUMBENT_REPLAY_COUNT=2
LOCAL_INCUMBENT_REPLAY_DETERMINISTIC=true
INCUMBENT_PREDICTION_IDENTITY_SHA256=d27f732c4be8566e88ace8a141f9a5cd143ec61ddcf4bdddd94dd256e318a39f
ACTUAL_LABEL_SET_IDENTITY_SHA256=32844f7cb63fdee2c6f6adba83b7c7f1d748b28c3d3e52e8c53d5cf35ccfa8f4
BUSINESS_GRAIN_SET_IDENTITY_SHA256=3a417a95293bab196562ad035632f482427ff3e288699351c6ee82c98edbda6f
```

The incumbent aggregate metrics were:

| metric | value |
| --- | ---: |
| daily_wape | `0.824404` |
| daily_mae | `1177.913143` |
| cumulative_absolute_error_kg | `9159967.333977` |
| single_day_peak_quantity_absolute_error_kg_q | `23639.741893` |
| sustained_7day_quantity_absolute_error_kg_q | `2801815.894075` |
| P80_COVERAGE | `0.134649` |
| P90_COVERAGE | `0.193355` |

These values are retained as `OBSERVED_FROM_ORIGINAL_LOCAL_RUN` for audit
traceability only. They are not accepted S4 selection evidence or accepted
guardrail evidence after this correction. The original run did not have a
lawful forecast-cutoff authority, so its horizon breakdown cannot establish
the required `forecast_horizon_days` contract.

## Candidate 01 execution

The frozen Candidate 01 manifest was validated before execution:

```text
CANDIDATE_ID=01_parameter_calibration
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
RANDOM_SEED=20260624
RUN_COUNT=4
```

All four runs used the same TRAIN rows, VALIDATION rows, actual labels, and
business-grain inputs. The original runner recorded a cutoff/horizon policy,
but this correction establishes that it did not have valid cutoff authority
and therefore did not satisfy the frozen forecast-horizon or complete metric
contract. The incumbent reference replay is not counted as a candidate
evaluation. The four candidate invocations are real validation-driven
engineering evaluations whose budget consumption is retained:

| run | frozen delta | daily_wape | daily_mae | cumulative abs. error | P80 | P90 | primary relation | guardrail | coverage |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 1 | knot 5, alpha 0.10 | `0.833222` | `1190.512567` | `9278025.113961` | `0.128903` | `0.181864` | WORSE | BLOCKED | BLOCKED |
| 2 | knot 7, alpha 0.10 | `0.820739` | `1172.676475` | `9098307.074315` | `0.141519` | `0.202348` | IMPROVED | BLOCKED | BLOCKED |
| 3 | knot 6, alpha 0.05 | `0.823557` | `1176.703613` | `9147321.490436` | `0.135274` | `0.194479` | IMPROVED | BLOCKED | BLOCKED |
| 4 | knot 6, alpha 0.20 | `0.825535` | `1179.529266` | `9176280.083193` | `0.133525` | `0.193105` | WORSE | BLOCKED | BLOCKED |

The original run payload reported aggregate breakdown metrics for all six
named axes:

```text
forecast_horizon_days: 38 cells (historical hard-coded-anchor output)
farm_business_key: 74 cells
subfarm_business_key: 186 cells
variety_business_key: 17 cells
season_business_key: 1 cell
model_identity: 1 cell
BREAKDOWN_METRICS_SET_SHA256=47a4027f5a641faf13206c813fc5e869eefd8bab07e2b3655ff04327858ef058
```

The original local runs observed a `BELOW_MINIMUM` coverage outcome, but this
review found metric-contract and execution-governance defects that prevent
that outcome from serving as accepted S4 guardrail evidence. In particular,
the historical horizon cells used a hard-coded calendar anchor, and the
original invocation had no execution gate or validation-ledger reconciliation.
The corrected implementation now rejects missing forecast-cutoff authority,
rejects incomplete seven-day windows without zero fill, uses aggregation-aware
peak and cumulative formulas, and removes the VALIDATION-actual prediction
fallback. No cell was silently excluded in the original payload; its numeric
results are nevertheless not selection-authoritative.

The corrected disposition is:

```text
CANDIDATE_01_LOCAL_ENGINEERING_BEST_RUN=NONE
CANDIDATE_01_LOCAL_ENGINEERING_RESULT=BLOCKED
CANDIDATE_01_NUMERIC_EVIDENCE_ACCEPTED=false
CANDIDATE_01_GUARDRAIL_DECISION_ACCEPTED=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
```

This task does not issue Candidate 02 authorization. A future Candidate 02
task, if separately authorized, must consume the remaining budget under the
frozen governance contract.

## Budget and execution identity

```text
LOCAL_ENGINEERING_VALIDATION_EVALUATION_COUNT=4
CANDIDATE_01_ENGINEERING_RUN_COUNT=4
EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
REMAINING_EFFECTIVE_VALIDATION_BUDGET=28
VALIDATION_BUDGET_STATUS=FAIL
CANDIDATE_01_STARTED_EVALUATION_COUNT=4
CANDIDATE_01_RUN_COUNT=4
CANDIDATE_01_RERUN_REQUIRED_BY_THIS_TASK=false
CANDIDATE_01_RERUN_PERFORMED=false
CANDIDATE_01_RERUN_AUTHORIZED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
NEW_VALIDATION_SCORING_AUTHORIZED=false
NEW_CANDIDATE_EVALUATION_AUTHORIZED=false
VALIDATION_BUDGET_REWRITE_AUTHORIZED=false
PRIOR_EVALUATION_DELETION_AUTHORIZED=false
PRIOR_EVALUATION_RECLASSIFICATION_TO_ZERO_AUTHORIZED=false
```

The original run was generated by runner commit
`83084a583497547e317ccdfa2a6c5fbc91a9f9d9`; its numeric payload remains an
audit observation, not accepted guardrail evidence. The correction was not a
rerun: `CANDIDATE_01_RERUN_PERFORMED=false` and
`NEW_VALIDATION_SCORING_CALL_COUNT=0`. The four started evaluations remain
counted against the budget, and no prior evaluation row or budget consumption
was deleted or reclassified as zero.

The current runner still verifies SOURCE-002 and TEST sealing, but now fails
closed before scoring when the required forecast-cutoff authority is absent.
The metric implementation has no VALIDATION-actual fallback and does not use
missing-day zero fill.

## Boundaries

```text
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
FORECAST_HORIZON_BREAKDOWN_STATUS=BLOCKED
FORECAST_HORIZON_BREAKDOWN_REASON=FORECAST_HORIZON_AUTHORITY_UNAVAILABLE
SUSTAINED_7DAY_WINDOW_DAYS=7
MISSING_DAY_ZERO_FILL=false
SUSTAINED_7DAY_WINDOW_POLICY=REJECT_INCOMPLETE_WINDOW
CUMULATIVE_AGGREGATION_POLICY=ABS_OF_AGGREGATE_DIFFERENCE
FARM_PEAK_COMPUTED_AFTER_DAILY_SUBFARM_SUM=true
VALIDATION_ACTUAL_FALLBACK_REMOVED=true
CANDIDATE_02_EXECUTION_AUTHORIZED=false
PRODUCTION_DATABASE_MUTATION_PERFORMED=false
PRODUCTION_MODEL_CHANGE=false
PARAMETER_CHANGE_TO_PRODUCTION=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C01_LOCAL_ENGINEERING_RESULT_REVIEW
```

## Final contract and budget reconciliation R1

This append-only correction tightens the implementation contract without
rerunning Candidate 01. The original four started validation invocations are
retained as a legacy budget debit; they are not backfilled into the canonical
append-only journal and their numeric payload is not restored as selection
authority.

```text
VALIDATION_BUDGET_RECONCILIATION_ARTIFACT_PATH=docs/v0-3/s4/evidence/s4-validation-budget-reconciliation-r1.json
CANONICAL_LEDGER_ROW_COUNT=0
CANONICAL_LEDGER_STARTED_EVALUATION_COUNT=0
LEGACY_UNLEDGERED_C01_STARTED_EVALUATION_COUNT=4
LEGACY_UNLEDGERED_C01_BUDGET_DEBIT=4
EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
REMAINING_EFFECTIVE_VALIDATION_BUDGET=28
LEGACY_EXECUTION_CONTRACT_VALID=false
LEGACY_NUMERIC_EVIDENCE_SELECTION_AUTHORITY=false
LEGACY_ROWS_BACKFILLED=false
HISTORICAL_LEDGER_FABRICATION=false
CANDIDATE_01_RERUN_PERFORMED=false
VALIDATION_BUDGET_GATE_MACHINE_RECONCILED=true
```

The future budget preflight reads the durable reconciliation artifact and the
canonical journal together. It blocks on either artifact/hash drift or a
ledger-count mismatch, and reports the effective count as 4 of 32 for a
Candidate 02 preflight. It never creates synthetic journal rows.

The forecast-horizon contract is exact: only `{7, 14, 21}` calendar days from
an explicit forecast cutoff are accepted. A missing cutoff or any arbitrary
horizon fails closed with `FORECAST_HORIZON_NOT_IN_FROZEN_SET` (or the missing
cutoff authority blocker); a dataset-global cutoff alone is not a complete
window authority.

The complete-window metrics—cumulative absolute error, single-day peak, and
sustained seven-day peak—require explicit `daily_rowset_authority`,
`daily_rowset_identity`, `daily_rowset_completeness`, evaluation window start,
end and day count, cutoff identity, horizon identity, and
`no_missing_days=true`. Missing or incomplete authority emits
`COMPLETE_DAILY_ROW_SET_AUTHORITY_UNAVAILABLE`. Cutoff presence by itself does
not authorize these metrics.

WAPE uses the actual denominator. When the actual denominator is zero,
`daily_wape=null`, status is `NOT_COMPUTABLE`, and reason is
`WAPE_ACTUAL_DENOMINATOR_ZERO`; it is never reported as numeric zero and the
primary guardrail is blocked.

Farm peak aggregation retains the grain
`season × farm × variety × target_date × forecast_cutoff × model_identity ×
forecast_quantile` and sums subfarms only. Different varieties are not summed
into one farm peak. The sustained 3-versus-7-day owner conflict remains
explicitly unresolved by this task:
`SUSTAINED_3_VS_7_OWNER_CONFLICT_RESOLVED_BY_THIS_TASK=false`.

```text
S4_CANDIDATE_EXPERIMENT_EXECUTED=true
CANDIDATE_01_RERUN_PERFORMED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_PR587_FINAL_CONTRACT_AND_BUDGET_REVIEW
```

## Final narrow correction R2

This append-only correction closes the remaining preflight, budget-gate, and
farm-peak aggregation findings. It does not rerun Candidate 01, invoke the
official C01 scoring runner, consume additional validation budget, or access
TEST. The four historical Candidate 01 invocations remain an effective debit
of four evaluations even though the canonical ledger contains no rows.

```text
TASK_ID=V0_3_S4_C01_FINAL_NARROW_CORRECTION_R2
TARGET_PR=587
R2_NARROW_CORRECTION_APPLIED=true
CANDIDATE_01_RERUN_PERFORMED=false
OFFICIAL_C01_SCORING_RUNNER_CALL_COUNT=0
LOCAL_ENGINEERING_VALIDATION_RUNNER_CALL_COUNT=0
CANDIDATE_02_RUNNER_CALL_COUNT=0
TEST_EVALUATION_CALL_COUNT=0
CURRENT_LEDGER_ROW_COUNT=0
CANONICAL_LEDGER_STARTED_EVALUATION_COUNT=0
LEGACY_RECONCILED_VALIDATION_DEBIT=4
ACTUAL_VALIDATION_EVALUATION_COUNT=4
EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
REMAINING_GLOBAL_VALIDATION_BUDGET=28
BUDGET_RECONCILIATION_REQUIRED_AT_GATE=true
MISSING_BUDGET_RECONCILIATION_FAILS_CLOSED=true
GLOBAL_COUNT_ZERO_WITH_RECONCILED_FOUR_REJECTED=true
VARIETY_CURVE_NORMALIZATION_USES_CURRENT_GROUP_TOTAL=true
VARIETY_CURVE_GROUP_ORDER_INVARIANT=true
SINGLE_DAY_FARM_VARIETY_GRAIN_PRESERVED=true
SUSTAINED_7DAY_FARM_VARIETY_GRAIN_PRESERVED=true
CROSS_VARIETY_SUSTAINED_FARM_SUM_FORBIDDEN=true
C01_RESULT=BLOCKED
CANDIDATE_01_NUMERIC_EVIDENCE_ACCEPTED=false
CANDIDATE_01_GUARDRAIL_DECISION_ACCEPTED=false
CANDIDATE_01_LOCAL_ENGINEERING_BEST_RUN=NONE
CANDIDATE_01_LOCAL_ENGINEERING_RESULT=BLOCKED
FINAL_STOP_GATE=COORDINATOR_PR587_FINAL_NARROW_CORRECTION_REVIEW
```

The official preflight now reports the canonical ledger count separately from
the effective reconciled debit: `0` canonical rows, `4` consumed validation
evaluations, and `28` remaining global budget. A gate request cannot be built
without a resolved reconciliation artifact and rejects a stale global count
of zero. Variety-curve normalization uses each group's own total and is
invariant to group iteration order. Single-day and sustained seven-day farm
peaks retain the full farm-variety-cutoff-model-quantile grain; sustained
windows sum subfarms only and never combine different varieties.

No C01/C02 scoring, TEST evaluation, ledger rewrite, budget deletion, or
production model/parameter change was performed in R2.
