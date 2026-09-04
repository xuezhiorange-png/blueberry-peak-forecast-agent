# V0.3-S3-B Quantile semantics verified-claim R2 (post-remediation)

## Artifact identity

```text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R2
ARTIFACT_VERSION=s3-b-quantile-semantics-verified-claim-r2-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R2
TASK_CLASS=DOCS_ONLY_POST_REMEDIATION_SEMANTICS_VERIFICATION
AUTHORIZATION_SCOPE=S3_B_POST_REMEDIATION_QUANTILE_SEMANTICS_VERIFICATION_ONLY
USER_GATE=可以实施
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R2_IMPLEMENTATION
VERIFICATION_R2_AUTHORIZED=true
BASE_MAIN_SHA=cda06c720212cf087e0edc11aa3b7fa22085b457
BASE_MAIN_TREE_SHA=c7d22f6563d43eda1dfd31d452469cd3c3d7805d
HISTORICAL_R1_PR=386
HISTORICAL_R1_RESULT_PRESERVED=true
PARENT_IMPLEMENTATION_PR=537
PARENT_CLOSEOUT_PR=540
CHECKLIST_EXECUTED=true
CURRENT_P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
ALL_QUANTILE_SEMANTICS_VERIFIED=true
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_B_COVERAGE_EXECUTED=false
EMPIRICAL_COVERAGE_EXECUTED=false
TEST_REMAINS_SEALED=true
R2_REVIEW_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R2_REVIEW
STOP_AFTER_R2_AUTHORING_AND_EXECUTION=true
NO_STEP_IMPLIES_THE_NEXT=true
EVIDENCE_JSON_SHA256=f5050f616e0386748f331ff4037dda33306dc94a2a5a2d5b7e9bbf5afc19ba76
```

Post-remediation semantics verification R2 re-traces the **current** main
implementation after remediation PR #537 and closeout PR #540. Historical failed
R1 (#386, `VERIFICATION_FAILED` for all three fields) is preserved and not
rewritten.

```text
DOCS_ONLY_VERIFICATION=true
FORBIDDEN_PRODUCTION_CODE_CHANGE=true
FORBIDDEN_TEST_CODE_CHANGE=true
FORBIDDEN_EMPIRICAL_COVERAGE=true
FORBIDDEN_HISTORICAL_R1_ARTIFACT_MUTATION=true
SEMANTICS_VERIFIED_DOES_NOT_EXECUTE_COVERAGE=true
SEMANTICS_VERIFIED_DOES_NOT_COMPLETE_S3=true
```

## Historical R1 (preserved)

```text
HISTORICAL_VERIFICATION_R1_PR=386
HISTORICAL_VERIFICATION_R1_MERGE=3463336d1539332cb9bb81117ff52cf70e9120e6
HISTORICAL_VERIFICATION_R1_EVIDENCE_JSON_SHA256=9500d7efce83102797655b5bf0fb0e7c6896a64a9449ea5007269bdd2bd7f723
HISTORICAL_R1_P50=VERIFICATION_FAILED
HISTORICAL_R1_P80=VERIFICATION_FAILED
HISTORICAL_R1_P90=VERIFICATION_FAILED
```

R1 traced pre-remediation blobs where Task 8 P80/P90 were P50+symmetric margins
and residual lane used structural_p50 + residual_quantile composition. R2 does
**not** re-validate those blobs.

## Step 1 — Final-target field trace (current main)

Published incumbent fields (core forecast daily curve):

| Quantile | Published field | `forecast_quantile` label |
| --- | --- | --- |
| P50 | `model_harvested_marketable_quantity_kg` | `P50` |
| P80 | `model_harvested_marketable_quantity_kg` | `P80` |
| P90 | `model_harvested_marketable_quantity_kg` | `P90` |

Trace (final-target quantile lane):

1. **Training label** — `dataset.py::build_final_target_training_matrix` uses
   `actual_harvest_quantity_kg` as regression label (`FINAL_TARGET_ACTUAL_LABEL`).
2. **Training objective** — `model.py::train_quantile_estimators` fits three
   independent `HistGradientBoostingRegressor(loss="quantile", quantile=q)` on the
   same label matrix with `q ∈ {0.50, 0.80, 0.90}`.
3. **Model family** — `config.py::FINAL_TARGET_MODEL_FAMILY=
   hist_gradient_boosting_final_target_quantile`; enforced in
   `train_final_target_model_from_manifest` / `run_final_target_quantile_prediction`.
4. **Prediction** — `service.py::predict_final_target_quantiles` calls
   `predict_quantiles` (raw estimator outputs) then
   `projection.py::project_final_target_quantiles` (nonnegative clamp + deterministic
   monotonic rearrangement per remediation §10).
5. **Published kg per row** — `model_harvested_marketable_quantity_kg` =
   `corrected_p50_kg` / `corrected_p80_kg` / `corrected_p90_kg` with matching
   `forecast_quantile` (`P50`/`P80`/`P90`).
6. **Persistence** — `persistence.py` stores canonical JSON snapshot for
   `prediction_target_kind=FINAL_TARGET_QUANTILE`, `mode=final_target_quantile`,
   lawful `task9_run_id=NULL`, `task9_result_hash=NULL`.
7. **Core forecast binding** — `core_forecast/service.py::
   apply_final_target_quantile_to_marketable_curve_rows` requires
   `FinalTargetPredictionAuthority` with `prediction_target_kind=FINAL_TARGET_QUANTILE`
   and `model_family=hist_gradient_boosting_final_target_quantile`; maps authority
   predictions into `model_harvested_marketable_quantity_kg` by
   `(farm, subfarm, variety, date, forecast_quantile)` without structural or Task9
   residual composition.

```text
LEGACY_RESIDUAL_MODEL_IS_NOT_FINAL_QUANTILE_AUTHORITY=true
STRUCTURAL_P50_IS_NOT_FINAL_P50_AUTHORITY=true
STRUCTURAL_P80_IS_NOT_FINAL_P80_AUTHORITY=true
STRUCTURAL_P90_IS_NOT_FINAL_P90_AUTHORITY=true
SAME_FINAL_TARGET_FOR_ALL_QUANTILES=true
DISTINCT_QUANTILE_LEVELS_BOUND_CORRECTLY=true
```

## Step 2–3 — Training objectives

```text
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
P50_LEVEL=0.50
P80_LEVEL=0.80
P90_LEVEL=0.90
P50_OBJECTIVE=PINBALL_LOSS_Q_0_50_ON_FINAL_TARGET
P80_OBJECTIVE=PINBALL_LOSS_Q_0_80_ON_FINAL_TARGET
P90_OBJECTIVE=PINBALL_LOSS_Q_0_90_ON_FINAL_TARGET
```

No P50+symmetric-margin derivation. No structural_p50 anchor in final-target path.

## Step 4 — Artifact identity

`model.py::validate_artifact_target_kind` and service loaders fail closed when
`prediction_target_kind` or `model_family` do not match `FINAL_TARGET_QUANTILE` /
`hist_gradient_boosting_final_target_quantile`.

```text
LEGACY_ARTIFACT_AS_FINAL_TARGET_REJECTED=true
ARTIFACT_IDENTITY_VERIFIED=true
```

## Step 5 — Post-processing audit

`project_final_target_quantiles`:

- applies nonnegative clamp only to negative kg estimates;
- applies deterministic monotonic rearrangement (`max` chain) when raw direct
  quantiles cross;
- records `raw_crossing_count`, `final_crossing_count`, `projection_reasons`;
- does **not** derive P80/P90 solely from P50+margin.

Remediation contract:

```text
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
MONOTONIC_PROJECTION_CONFERS_QUANTILE_SEMANTICS=false
```

R2 evaluates **final published** values after lawful rearrangement. Independent
direct quantile estimators on final Y remain the semantic authority; rearrangement
is an ordering safeguard only. Monotonic output alone is not cited as proof.

```text
POST_PROCESSING_AUDIT_PASS=true
POST_PROCESSING_IS_NOT_P50_PLUS_MARGIN=true
RAW_AND_FINAL_CROSSING_AUDITABLE=true
```

## Step 6 — Pairing definition audit (no coverage execution)

Frozen masks (V0.2 §11 / S3-B contract §3):

```text
P50_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P50 AND EXACT_ACTUAL_PAIRED
P80_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P80 AND EXACT_ACTUAL_PAIRED
P90_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P90 AND EXACT_ACTUAL_PAIRED
COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
COVERAGE_REQUIRES_VALID_PAIRING=true
PAIRING_FAILURE_STATUS=NOT_COMPUTABLE
PAIRING_FAILURE_IS_NOT_ZERO=true
PAIRING_DEFINITION_REVIEW_PASS=true
EMPIRICAL_COVERAGE_EXECUTED=false
```

## Step 7 — Pinball branch audit

`metrics.py::pinball_loss` uses `max(quantile * error, (quantile - 1) * error)`
matching V0.2 §10.1 branch assignment. No official scores published in R2.

```text
PINBALL_BRANCH_ASSIGNMENT_CORRECT=true
```

## Step 8 — Per-quantile classification

| Field | Primary | Direct objective | Trace complete | Artifact identity | Post-processing |
| --- | --- | --- | --- | --- | --- |
| P50 | `TRUE_UPPER_QUANTILE_CANDIDATE` | true | true | true | preserves identity under contract policy |
| P80 | `TRUE_UPPER_QUANTILE_CANDIDATE` | true | true | true | preserves identity under contract policy |
| P90 | `TRUE_UPPER_QUANTILE_CANDIDATE` | true | true | true | preserves identity under contract policy |

## Step 9 — Coordinator disposition (R2)

```text
CURRENT_P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
CURRENT_P50_SEMANTICS_VERIFIED=true
CURRENT_P80_SEMANTICS_VERIFIED=true
CURRENT_P90_SEMANTICS_VERIFIED=true
ALL_QUANTILE_SEMANTICS_VERIFIED=true
```

Semantics verification does **not** authorize coverage execution, TEST access,
S3 completion, or S4.

```text
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_B_COVERAGE_EXECUTED=false
SEMANTICS_VERIFIED_DOES_NOT_EXECUTE_COVERAGE=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
```
