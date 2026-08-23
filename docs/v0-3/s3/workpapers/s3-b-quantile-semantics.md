# V0.3-S3-B quantile semantics verification contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_CONTRACT
ARTIFACT_VERSION=s3-b-quantile-semantics-contract-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_CONTRACT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
USER_GATE=可以下一步 并行开发
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
COORDINATOR_AGENT=https://cursor.com/agents/bc-01a02307-c032-7da6-8a02-00d9b3518794
AUDITED_REPOSITORY_SHA=fd793de12bfe2df646925d9e7adc1d59c046ecdf
AUDITED_REPOSITORY_TREE_SHA=61d8550f1311e3c0949f5bf08814fc69ddf0fde5
AUDITED_REF=origin/main
CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
CONTRACT_VERSION=v0-3-s3-b-quantile-semantics-contract-v1
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-b-quantile-semantics.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics.json
EVIDENCE_JSON_SHA256=52dfe07eb6a17004704a1545c136a51c4646fbc7b7f7bca80b13f87a71e2d3e7
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This workpaper records the S3-B quantile semantics **verification contract**
freeze after user authorization 「可以下一步 并行开发」. This PR defines how
P50/P80/P90 semantics must be verified before coverage or pinball metrics may
publish. It does **not** claim semantics are verified and does **not** publish
coverage results.

~~~text
S3_B_QUANTILE_SEMANTICS_CONTRACT_AUTHORIZED=true
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE_ALLOWED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NOT_VERIFIED_IS_NOT_PASS=true
~~~

## 1. Parent bindings

~~~text
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
P0_CONTRACT_GIT_BLOB_SHA=45f900f4dfa1ef5da8ea898a39bdded4c8c11f08
P0_CONTRACT_SHA256=490f48cde5fd7543f2d7608b0dff388c9a7f99f44d77ed4337f55331e950d7a8
S3_A_AMENDMENT_PATH=docs/v0-3/s3/s3-daily-rowset-amendment.md
S3_A_AMENDMENT_GIT_BLOB_SHA=1baf930287598f5df78ac28d49c159b4231c0fc6
S3_A_AMENDMENT_SHA256=f2b2473bd7ebe52349010403cbcc45a8a18f3ae7ad3512c97d8b2a30b205a7be
Q1_PATH=docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md
Q1_SECTION=§9.7
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
~~~

P0 §5 left all quantile semantics `NOT_VERIFIED`. S3-B supplies the
verification procedure; it does not flip those flags.

## 2. Verification objective

Q1 §9.7 requires confirming each `forecast_pq` field is a **true upper
quantile**, not a point estimate, interval label, or scenario label.

Legal post-verification status (coordinator-written only):

~~~text
VERIFIED_TRUE_UPPER_QUANTILE
~~~

This PR ends with:

~~~text
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
~~~

## 3. Frozen metric definitions (summary)

| Topic | Frozen binding |
|---|---|
| P80 coverage | `actual <= forecast_p80` |
| P90 coverage | `actual <= forecast_p90` |
| P80 spread | `P80 - P50`; not interval width |
| P90 spread | `P90 - P50`; not interval width |
| Interval width | `NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE` |
| Pinball branches | V0.2 §10.1: under when `actual >= forecast_q` |
| Pairing failure | `NOT_COMPUTABLE`, not 0 |
| Complete daily rowset | not required for coverage definition |
| Baseline P80/P90 | `BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED` |

Empirical coverage ≈ 0.8 is not semantics verification.

## 4. Read-only incumbent code audit (origin/main)

Audit performed read-only on `origin/main` at
`fd793de12bfe2df646925d9e7adc1d59c046ecdf`. No code changed. No coverage
numbers computed.

### 4.1 Label layer

- `backend/app/harvest_state/enums.py` — `ForecastQuantile` enum `P50/P80/P90`
- `backend/app/core_forecast/schemas.py` — `QUANTILES = ("P50", "P80", "P90")`
- Alembic CHECK constraints on `forecast_quantile`

Labels exist; semantics unverified.

### 4.2 Task 8 maturity (structural)

`backend/app/maturity/service.py`:

- P50: `reconcile_p50_mass(expected_total_kg, density)` — point mass from curve
- P80/P90: `p50 + effective_total * margin_share` — symmetric margin, not
  independent quantile fit
- Calibration records `interval_semantics: "pointwise_marginal"`

### 4.3 Residual layer

`backend/app/residual_model/model.py` — `HistGradientBoostingRegressor` with
`loss="quantile"` at 0.5/0.8/0.9 on residual label.

`backend/app/residual_model/projection.py`:

- Adds residual quantiles to `structural_arrival_p50_kg` (P50 structural only)
- Applies `max(P50, P80, P90)` monotonic projection
- Sets `quantile_projection_applied` when monotonic correction runs

### 4.4 Composition

`backend/app/core_forecast/service.py` reconciles Task 8 triplet to Task 9 per
quantile. `backend/app/harvest_state/service.py` simulates separate quantile
rows.

### 4.5 Preliminary finding

The incumbent pipeline mixes point-mass P50, margin-based P80/P90, quantile
regression on residuals, and monotonic post-processing. Field names alone do not
establish `VERIFIED_TRUE_UPPER_QUANTILE`. Coordinator execution required.

## 5. What this PR does not do

- Does not set `CURRENT_*_SEMANTICS_STATUS` to `VERIFIED_TRUE_UPPER_QUANTILE`
- Does not compute or publish coverage ratios
- Does not mutate V0.2 metric contract or S3-A files
- Does not change model, tests, or backend code
- Does not authorize backtest execution

## 6. Current status flags

~~~text
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P50_COVERAGE_COMPUTABLE=false
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
P50_SEMANTICS_VERIFIED=false
P80_SEMANTICS_VERIFIED=false
P90_SEMANTICS_VERIFIED=false
NOT_VERIFIED_IS_NOT_PASS=true
~~~

Coordinator closeout may advance statuses only after separately authorized
`S3_B_SEMANTICS_VERIFIED_CLAIM` execution.
