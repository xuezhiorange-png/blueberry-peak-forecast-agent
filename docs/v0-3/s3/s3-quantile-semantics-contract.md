# V0.3-S3-B Quantile Semantics Verification Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_CONTRACT
CONTRACT_VERSION=v0-3-s3-b-quantile-semantics-contract-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_CONTRACT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
ENGLISH_ID=QUANTILE_SEMANTICS_VERIFICATION_PROCEDURE
USER_GATE=可以下一步 并行开发
CONTRACT_ONLY=true
BASE_MAIN_SHA=fd793de12bfe2df646925d9e7adc1d59c046ecdf
BASE_MAIN_TREE_SHA=61d8550f1311e3c0949f5bf08814fc69ddf0fde5
BASE_REF=origin/main
PARENT_CONTRACT_ID=V0_3_S3_BACKTEST_AND_DIAGNOSIS_CONTRACT
PARENT_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
PARENT_CONTRACT_GIT_BLOB_SHA=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
PARENT_CONTRACT_SHA256=490f48cde5fd7543f2d7608b0dff388c9a7f99f44d77ed4337f55331e950d7a8
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
S3_A_AMENDMENT_GIT_BLOB_SHA=1baf930287598f5df78ac28d49c159b4231c0fc6
S3_A_AMENDMENT_SHA256=f2b2473bd7ebe52349010403cbcc45a8a18f3ae7ad3512c97d8b2a30b205a7be
S3_A_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
Q1_PATH=docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md
Q1_SECTION=§9.7
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
REVIEWER_ROLE=COORDINATOR
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
NO_STEP_IMPLIES_THE_NEXT=true
~~~

~~~text
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
LLM_MUST_NOT_INVENT_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes the V0.3-S3-B quantile semantics **verification procedure**
and metric-definition bindings for P50 / P80 / P90. It is a governance contract,
not a semantics verification run, not a coverage computation, not a backtest, and
not a model change.

Field names `P50`, `P80`, and `P90` in incumbent output are **labels only** until
a separately authorized verification pass records
`VERIFIED_TRUE_UPPER_QUANTILE`. Empirical coverage near 0.8 is **not** semantics
verification.

Merging this contract does **not** set `CURRENT_P50_SEMANTICS_STATUS`,
`CURRENT_P80_SEMANTICS_STATUS`, or `CURRENT_P90_SEMANTICS_STATUS` to
`VERIFIED_TRUE_UPPER_QUANTILE`.

## 1. Inherited authority (not reopened)

### 1.1 Parent S3 P0 contract

~~~text
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_VERSION=v0-3-s3-backtest-and-diagnosis-contract-v1
P0_CONTRACT_GIT_BLOB_SHA=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
P0_CONTRACT_SHA256=490f48cde5fd7543f2d7608b0dff388c9a7f99f44d77ed4337f55331e950d7a8
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
NOT_VERIFIED_IS_NOT_PASS=true
~~~

### 1.2 S3-A daily rowset amendment (reference only; do not mutate)

~~~text
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_VERSION=v0-3-s3-daily-rowset-amendment-v1
S3_A_DOES_NOT_DEFINE_QUANTILE_SEMANTICS=true
COVERAGE_BLOCKED_BY_S3_B=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=false
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=false
~~~

S3-B does not amend S3-A. Coverage pairing may use sparse valid forecast/actual
pairs without a complete daily row set; peak metrics remain blocked by S3-A
materialization status.

### 1.3 Q1 and V0.2 metric authority (reference only; do not mutate)

~~~text
Q1_PATH=docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md
Q1_QUANTILE_CALIBRATION_SECTION=§9.7
Q1_INTERVAL_WIDTH_SECTION=§9.8
Q1_PINBALL_LOSS_SECTION=§9.9
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
V0_2_QUANTILE_COVERAGE_SECTION=§10
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
~~~

## 2. Verification objective (Q1 §9.7)

For each published field `forecast_p50`, `forecast_p80`, and `forecast_p90`, the
verification target is:

> Is the field a **true upper quantile** of the forecast target distribution at
> the stated level (0.50 / 0.80 / 0.90), such that
> `P(actual ≤ forecast_q) ≈ q` under valid pairing?

The only legal post-verification status name is:

~~~text
VERIFIED_TRUE_UPPER_QUANTILE
~~~

Rejected or pending statuses:

~~~text
NOT_VERIFIED
VERIFICATION_FAILED
NOT_COMPUTABLE
~~~

Forbidden interpretations (automatic `VERIFICATION_FAILED` if claimed as PASS):

~~~text
POINT_ESTIMATE_ONLY
INTERVAL_LABEL_ONLY
SCENARIO_LABEL_ONLY
SYMMETRIC_MARGIN_AROUND_P50
MONOTONIC_PROJECTION_ONLY
EMPIRICAL_COVERAGE_ONLY
FIELD_NAME_ONLY
~~~

`NOT_VERIFIED` is not `PASS`. `VERIFICATION_FAILED` is not `PASS`.
`NOT_COMPUTABLE` is not zero.

## 3. Frozen coverage definitions

Inherited from V0.2 §10 and Q1 §9.7 without mutation:

~~~text
P80_COVERAGE_DEFINITION=actual<=forecast_p80
P90_COVERAGE_DEFINITION=actual<=forecast_p90
P50_COVERAGE_DEFINITION=actual<=forecast_p50
COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
COVERAGE_REQUIRES_VALID_PAIRING=true
PAIRING_FAILURE_STATUS=NOT_COMPUTABLE
PAIRING_FAILURE_IS_NOT_ZERO=true
~~~

Coverage numerators and denominators:

~~~text
P80_UPPER_COVERAGE=count(actual<=forecast_p80 over P80_COVERAGE_MASK)/p80_coverage_comparable_row_count
P90_UPPER_COVERAGE=count(actual<=forecast_p90 over P90_COVERAGE_MASK)/p90_coverage_comparable_row_count
P50_UPPER_COVERAGE=count(actual<=forecast_p50 over P50_COVERAGE_MASK)/p50_coverage_comparable_row_count
P80_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P80 AND EXACT_ACTUAL_PAIRED
P90_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P90 AND EXACT_ACTUAL_PAIRED
P50_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P50 AND EXACT_ACTUAL_PAIRED
~~~

Coverage publication gate:

~~~text
COVERAGE_PUBLICATION_REQUIRES_P50_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE
COVERAGE_PUBLICATION_REQUIRES_P80_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE
COVERAGE_PUBLICATION_REQUIRES_P90_SEMANTICS=VERIFIED_TRUE_UPPER_QUANTILE
COVERAGE_BLOCKED_WHILE_SEMANTICS_NOT_VERIFIED=true
COVERAGE_BLOCKED_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
~~~

Until all three semantics are `VERIFIED_TRUE_UPPER_QUANTILE`:

~~~text
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_P50_COVERAGE_COMPUTABLE=false
~~~

## 4. Frozen upper-quantile spread (not interval width)

~~~text
P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
P90_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
FORBIDDEN_INTERVAL_WIDTH_PROXY=P90-P50
FORBIDDEN_INTERVAL_WIDTH_PROXY=P80-P50
~~~

`upper_spread_p80_minus_p50` and `upper_spread_p90_minus_p50` are permitted
**spread** metrics and must be labeled as spread, not interval width.

### 4.1 Interval width when lower bound unavailable

~~~text
P80_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
P90_INTERVAL_WIDTH=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
IS_PREDICTION_INTERVAL_WIDTH=false
INTERVAL_WIDTH_REASON_CODE=LOWER_BOUND_NOT_AVAILABLE
~~~

No lower quantile is published by the incumbent pipeline. Interval width is
`NOT_COMPUTABLE`, not approximated by `P90-P50` or `P80-P50`.

## 5. Frozen pinball loss (V0.2 §10.1 branch assignment)

Pinball loss is gated on semantics verification. Formula (unchanged from V0.2
§10.1 and Q1 §9.9):

~~~text
pinball_loss_q=mean(max(q*(actual-forecast_q),(q-1)*(actual-forecast_q)))
PINBALL_UNDER_PREDICTION_CONDITION=actual>=forecast_q
PINBALL_UNDER_PREDICTION_TERM=q*(actual-forecast_q)
PINBALL_OVER_PREDICTION_CONDITION=actual<forecast_q
PINBALL_OVER_PREDICTION_TERM=(q-1)*(actual-forecast_q)
~~~

Branch reversal is forbidden. The prior reversed wording
(`q*(actual-forecast_q)` for over-prediction and `(q-1)*(actual-forecast_q)`
for under-prediction) is rejected per V0.2 §10.1.

Until semantics verified:

~~~text
PINBALL_LOSS_P50_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_P80_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_P90_STATUS=NOT_COMPUTABLE
PINBALL_LOSS_REASON=QUANTILE_SEMANTICS_NOT_VERIFIED
~~~

Quantile levels for pinball:

~~~text
PINBALL_Q_P50=0.5
PINBALL_Q_P80=0.8
PINBALL_Q_P90=0.9
~~~

## 6. Incumbent field production bindings (read-only audit scope)

Verification evidence must cite `origin/main` code paths and contract sections.
The bindings below name the incumbent V0.2 pipeline layers that emit
`P50` / `P80` / `P90` fields. This contract records audit scope only; it does
not execute verification and does not publish coverage numbers.

### 6.1 Canonical quantile labels

| Layer | Path (origin/main) | Field / enum | Role |
|---|---|---|---|
| Harvest state enum | `backend/app/harvest_state/enums.py` | `ForecastQuantile.P50/P80/P90` | canonical label set |
| Core forecast schema | `backend/app/core_forecast/schemas.py` | `QUANTILES=("P50","P80","P90")` | composition triplet |
| DB constraints | `backend/alembic/versions/0010_harvest_state_persistence.py`, `0017_core_forecast_run_persistence.py` | `forecast_quantile in ('P50','P80','P90')` | persistence labels |
| Residual artifact | `backend/app/models/residual_model.py` | `quantile_label`, `quantile_value` 0.5/0.8/0.9 | residual model metadata |

### 6.2 Task 8 maturity curve (structural supply)

| Path | Lines (indicative) | Semantics observed |
|---|---|---|
| `backend/app/maturity/service.py` | `reconcile_p50_mass(...)` | P50 daily kg = curve density × expected total (point mass allocation) |
| `backend/app/maturity/service.py` | `p80 = p50 + (effective_total * p80_margin_share * widening)` | P80 = P50 + symmetric margin on total, not independent upper quantile |
| `backend/app/maturity/service.py` | `p90 = p50 + (effective_total * p90_margin_share * widening)` | P90 = P50 + symmetric margin on total |
| `backend/app/maturity/service.py` | calibration payload `interval_semantics: "pointwise_marginal"` | explicit non-predictive-distribution label |
| `backend/app/maturity/calibration.py` | `empirical_quantile(...)` | residual-share margins from held-out curve error |

Task 8 P50 is a **point estimate** from normalized maturity density. Task 8
P80/P90 are **symmetric margins around P50**, not independently fitted upper
quantiles of the harvest outcome.

### 6.3 Residual correction layer

| Path | Semantics observed |
|---|---|
| `backend/app/residual_model/model.py` | `HistGradientBoostingRegressor(loss="quantile", quantile=0.5/0.8/0.9)` — quantile regression on **residual** label |
| `backend/app/residual_model/projection.py` | `raw_p80 = structural_arrival_p50_kg + predicted_residual_p80_kg` — structural anchor always P50 |
| `backend/app/residual_model/projection.py` | `projected_p80 = max(projected_p50, clamped_p80)` — monotonic projection |
| `backend/app/residual_model/projection.py` | `quantile_projection_applied` when monotonic correction applied |

Residual estimators are quantile regressors on the residual, but final published
values pass through P50-anchored addition and monotonic projection. That
composition is not automatically a true upper quantile of the target.

### 6.4 Task 9 harvest state and core forecast composition

| Path | Semantics observed |
|---|---|
| `backend/app/harvest_state/service.py` | separate simulation rows per `forecast_quantile` |
| `backend/app/core_forecast/service.py` | `_task8_supply` reconciles Task 8 `p50_kg/p80_kg/p90_kg` to Task 9 member `natural_maturity_supply_kg` per quantile |
| `backend/app/core_forecast/service.py` | `QUANTILE_RANK` ordering P50 < P80 < P90 in output rows |

Downstream persistence stores three labeled curves. Label presence does not
prove quantile semantics.

### 6.5 Preliminary code-read conclusion (contract freeze only)

~~~text
INCUMBENT_PIPELINE_USES_P50_P80_P90_LABELS=true
INCUMBENT_PIPELINE_SINGLE_TRUE_QUANTILE_MODEL=false
INCUMBENT_TASK8_P50_IS_POINT_MASS_ALLOCATION=true
INCUMBENT_TASK8_P80_P90_ARE_P50_PLUS_MARGIN=true
INCUMBENT_RESIDUAL_USES_QUANTILE_REGRESSION_ON_RESIDUAL=true
INCUMBENT_RESIDUAL_FINAL_VALUES_USE_MONOTONIC_PROJECTION=true
PRELIMINARY_SEMANTICS_VERIFICATION_OUTCOME=PENDING_COORDINATOR_EXECUTION
AUTOMATIC_PASS_FROM_FIELD_NAMES_FORBIDDEN=true
AUTOMATIC_PASS_FROM_EMPIRICAL_COVERAGE_FORBIDDEN=true
~~~

If coordinator execution finds any field is not `VERIFIED_TRUE_UPPER_QUANTILE`,
status remains `NOT_VERIFIED` or becomes `VERIFICATION_FAILED`. The model must
not be changed to force PASS.

## 7. Frozen verification procedure (execution not authorized)

The following checklist is frozen for a future separately authorized
`S3_B_SEMANTICS_VERIFIED_CLAIM` pass. This contract does not execute it.

### 7.1 Step 1 — Field trace

For each quantile `q ∈ {P50,P80,P90}`:

1. Trace `forecast_q` from persisted incumbent output back through core forecast,
   harvest state, residual projection, and Task 8 maturity layers.
2. Record code path, formula, and whether the value is fitted as a quantile,
   derived as a margin, or post-processed.
3. Bind `origin/main` git blob SHA for every cited file.

### 7.2 Step 2 — Semantic classification

Classify each field:

~~~text
TRUE_UPPER_QUANTILE_CANDIDATE
POINT_ESTIMATE
SYMMETRIC_MARGIN
MONOTONIC_PROJECTION_ARTIFACT
INTERVAL_LABEL
SCENARIO_LABEL
UNRESOLVED
~~~

Only `TRUE_UPPER_QUANTILE_CANDIDATE` with supporting evidence may advance to
`VERIFIED_TRUE_UPPER_QUANTILE`.

### 7.3 Step 3 — Pairing validity (no coverage numbers required here)

1. Confirm `P*_COVERAGE_MASK` pairing rules from V0.2 §11.2–§11.3.
2. If pairing fails, record `NOT_COMPUTABLE` with explicit `reason_code`; never 0.
3. Sparse binding rows are allowed; complete daily row set is not required for
   coverage **definition**, but semantics must be verified first.

### 7.4 Step 4 — Pinball branch audit

1. Confirm implementation uses V0.2 §10.1 branch assignment (§5 above).
2. If branches are reversed, record `VERIFICATION_FAILED` for pinball and
   coverage publication.

### 7.5 Step 5 — Coordinator disposition

Coordinator writes `CURRENT_P50_SEMANTICS_STATUS`, `CURRENT_P80_SEMANTICS_STATUS`,
`CURRENT_P90_SEMANTICS_STATUS` in evidence JSON only after this checklist
completes. Legal values:

~~~text
VERIFIED_TRUE_UPPER_QUANTILE
NOT_VERIFIED
VERIFICATION_FAILED
~~~

This S3-B contract PR ends with all three at `NOT_VERIFIED`.

## 8. Naive baseline quantile policy

~~~text
NAIVE_BASELINE_NAME=PRIOR_SEASON_ANALOG_DAY_ACTUAL
NAIVE_BASELINE_TYPE=POINT_FORECAST
NAIVE_BASELINE_POINT_FORECAST_ONLY=true
NAIVE_BASELINE_P80_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P90_STATUS=NOT_COMPUTABLE
NAIVE_BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
~~~

S3-B must not define baseline P80/P90 as "match incumbent labels". Baseline
quantile head-to-head comparison remains blocked per V0.2 §15–§16 until a
baseline quantile distribution is separately defined and accepted.

~~~text
BASELINE_P80_COVERAGE_COMPARISON=BLOCKED
BASELINE_P90_COVERAGE_COMPARISON=BLOCKED
BASELINE_P80_P90_PEAK_COMPARISON=BLOCKED
BASELINE_INTERVAL_WIDTH_COMPARISON=BLOCKED
BASELINE_PASS_BY_INCUMBENT_MATCH_FORBIDDEN=true
~~~

## 9. Current status at S3-B contract freeze

~~~text
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P50_COVERAGE_COMPUTABLE=false
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_BASELINE_P80_COMPUTABLE=false
CURRENT_BASELINE_P90_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
P50_SEMANTICS_VERIFIED=false
P80_SEMANTICS_VERIFIED=false
P90_SEMANTICS_VERIFIED=false
P50_P80_P90_SEMANTICS_VERIFIED=false
NOT_VERIFIED_IS_NOT_PASS=true
NOT_COMPUTABLE_IS_NOT_ZERO=true
~~~

## 10. Future gates (all false at S3-B contract freeze)

~~~text
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_C_AUTHORIZED=false
S3_D_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
next_subtask_not_implied=true
NO_STEP_IMPLIES_THE_NEXT=true
~~~

## 11. Explicit non-goals

This contract does not:

- mutate `docs/forecast-quality/s3-quality-metrics-contract.md`
- mutate S3-A daily rowset files
- execute coverage or pinball metrics
- publish empirical coverage ratios
- invent hashes, row counts, or tonnage
- change incumbent model code or parameters
- set `READY_AUTHORIZED=true` or `MERGE_AUTHORIZED=true` for downstream execution

## 12. S3-B quantile semantics contract live-authority pointer

~~~text
S3_B_QUANTILE_SEMANTICS_CONTRACT_LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md
S3_B_QUANTILE_SEMANTICS_CONTRACT_LIVE_AUTHORITY_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-b-quantile-semantics-contract-live-authority.json
EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9
PARENT_S3_B_PR=301
PARENT_S3_B_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
PARENT_S3_B_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
PARENT_S3_B_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=8456c9b4412a68680033995605c82356d0a322e0
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=8456c9b4412a68680033995605c82356d0a322e0
S3_B_CONTRACT_EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
S3_B_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics.md
PARENT_P0_CONTRACT_GIT_BLOB_SHA_AT_S3_B_FREEZE=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=cdf636b645345a41223ec2854c87d7ed2308cb63
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
PARENT_S3_A_AMENDMENT_GIT_BLOB_SHA_AT_S3_B_FREEZE=1baf930287598f5df78ac28d49c159b4231c0fc6
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=2119ed47ac2e53e0eeac5f505b976c0b972665a9
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=21c3b2d31a4fa40039d054c1cc82fffcb1f978b0
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=29dd5d3183a9f9bd4c096d1e8724fd6582a47caa
PARENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b9d3daad7eb8aa172b2ad241d7b78223d362c82b
TASK_CLASS=CONTRACT_DEFINITION_ONLY
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
PARALLEL_LANE=S3-B
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
PENDING_COORDINATOR_EXECUTION_NOT_VERIFIED_CLAIM=true
S3_B_CONTRACT_LIVE_AUTHORITY_IS_NOT_CHECKLIST_EXECUTION=true
S3_B_CONTRACT_LIVE_AUTHORITY_IS_NOT_VERIFIED_CLAIM=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_FLIP_VERIFIED_CLAIM=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_FLIP_COVERAGE_COMPUTABLE=true
CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_SEMANTICS_VERIFIED_CLAIM=true
FORBIDDEN_TREAT_S3_B_CONTRACT_FREEZE_AS_VERIFIED_UPPER_QUANTILE=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED` is maintained in `docs/v0-3/development-plan.md` §4.4 live state block and `docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md` (`EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9`). S3-B quantile semantics verification procedure contract is on main (#301). This live-authority insert records that the frozen procedure contract is authorized in the development-plan live registry. `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true` ≠ `CURRENT_P*_SEMANTICS_VERIFIED` ≠ `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED` ≠ checklist executed ≠ P50/P80/P90 are `VERIFIED_TRUE_UPPER_QUANTILE` ≠ coverage computable ≠ model change allowed. #301 preliminary conclusions (e.g. P80/P90 as P50+margin) remain `PENDING_COORDINATOR_EXECUTION`, not verified claim results. This evidence JSON is not a semantics-verified claim package. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed; this insert is not origin / members / artifact authority. Historical pointer snapshots may remain without `S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED`.

## 13. S3-B quantile semantics verified-claim authorization pointer

~~~text
S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_AUTHORIZATION_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md
S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_AUTHORIZATION_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-b-quantile-semantics-verified-claim-authorization.json
EVIDENCE_JSON_SHA256=0697b9bac264f71f2465f057f1bf3f7df35ed33b5c69f94ca8a44e2ec3ec7413
PARENT_LIVE_AUTHORITY_PR=384
PARENT_LIVE_AUTHORITY_MERGE=d92e9d11d3930a5f7a93d61402bb363327ffebec
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=7d47de8c84dcd52d6feea8aff3ecdcd3ecf6d4e9f7879c32f076dafae559a9c9
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-contract-live-authority.md
PARENT_S3_B_PR=301
PARENT_S3_B_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
PARENT_S3_B_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
PARENT_S3_B_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=8456c9b4412a68680033995605c82356d0a322e0
S3_B_CONTRACT_CONTENT_SHA256_AT_FREEZE=28dfb92b96caf6cef9124c80abcd23feb3a569a01131cad94a56089cf30fa6f1
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=2eed2f1366080059e3f250e52f9dd1c64dfa6f2c
S3_B_CONTRACT_EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
S3_B_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics.md
PARENT_P0_CONTRACT_GIT_BLOB_SHA_AT_S3_B_FREEZE=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=247ad7c41dec35c7e299f73eb66c610aec5fbcf6
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_EVIDENCE_JSON_SHA256=580f09e306e4e32db0e72d65158d455bd9fea57b4279497909ff0d54cb91259c
PARENT_S3_A_AMENDMENT_GIT_BLOB_SHA_AT_S3_B_FREEZE=1baf930287598f5df78ac28d49c159b4231c0fc6
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=63bcee78e659663e568bafcc7fd70edabdb79105
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_EVIDENCE_JSON_SHA256=b50948c9529dd7f87b844e61e48fbb3b89d6eae31211f43d6fc5189360553e0a
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=8728188f5468e8ec5c9adc958b547cf840e307ee
S3_C0_CONTRACT_PATH=docs/v0-3/s3/s3-pit-backtest-execution-contract.md
S3_C0_EVIDENCE_JSON_SHA256=12c40e013c60de9f9dbcfd7b5e7788281d9c7d6adcde641d6d436b3e65b5d7e1
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=29dd5d3183a9f9bd4c096d1e8724fd6582a47caa
PARENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b9d3daad7eb8aa172b2ad241d7b78223d362c82b
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
GRANT_ONLY=true
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
PARALLEL_LANE=S3-B
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=true
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
S3_BACKTEST_EXECUTION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
PENDING_COORDINATOR_EXECUTION_NOT_VERIFIED_CLAIM=true
GRANT_MERGE_DOES_NOT_EXECUTE_CHECKLIST=true
GRANT_MERGE_DOES_NOT_FLIP_CURRENT_P_SEMANTICS_STATUS=true
GRANT_MERGE_DOES_NOT_FLIP_COVERAGE_EXECUTION=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_SEMANTICS_VERIFIED_CLAIM=true
FORBIDDEN_TREAT_S3_B_CONTRACT_FREEZE_AS_VERIFIED_UPPER_QUANTILE=true
FORBIDDEN_TREAT_301_PRELIMINARY_AS_R1_RESULT=true
FORBIDDEN_CHANGE_MODEL_TO_FORCE_PASS=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
~~~

Live `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED` is maintained in `docs/v0-3/development-plan.md` §4.4 live state block and `docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md` (`EVIDENCE_JSON_SHA256=0697b9bac264f71f2465f057f1bf3f7df35ed33b5c69f94ca8a44e2ec3ec7413`). S3-B quantile semantics procedure contract is on main (#301); live contract authority is on main (#384). This grant authorizes a **later** docs-only verified-claim R1 to execute the frozen §7 checklist when the user again says 「可以实施」. `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=true` ≠ checklist executed ≠ `CURRENT_P*_SEMANTICS_VERIFIED` ≠ P50/P80/P90 are `VERIFIED_TRUE_UPPER_QUANTILE` ≠ coverage computable ≠ model change allowed. This evidence JSON is not a semantics-verified claim package. #301 preliminary conclusions remain `PENDING_COORDINATOR_EXECUTION`, not verification results. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set family remains fail-closed; this grant is not origin / members / artifact authority. Historical pointer snapshots may remain `S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false`.
