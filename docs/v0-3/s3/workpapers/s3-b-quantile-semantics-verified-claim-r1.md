# V0.3-S3-B Quantile semantics verified-claim R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R1
ARTIFACT_VERSION=s3-b-quantile-semantics-verified-claim-r1-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_VERIFIED_CLAIM_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_B_SEMANTICS_VERIFIED_CLAIM_IMPLEMENTATION_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
ENGLISH_ID=QUANTILE_SEMANTICS_VERIFIED_CLAIM
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=37f6fa7acfb4c6e516e2021c083002fed7001da0
BASE_MAIN_TREE_SHA=c95635c95490245072eeaece78aa83e280cfb341
PARENT_GRANT_PR=385
PARENT_GRANT_MERGE=37f6fa7acfb4c6e516e2021c083002fed7001da0
GRANT_EVIDENCE_JSON_SHA256=0697b9bac264f71f2465f057f1bf3f7df35ed33b5c69f94ca8a44e2ec3ec7413
GRANT_WORKPAPER=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics-verified-claim-r1.json
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
IMPLEMENTATION_R1=true
VERIFIED_CLAIM_R1_IS_DOCS_ONLY=true
CHECKLIST_EXECUTED=true
~~~

This workpaper records docs-only verified-claim R1 per grant (#385) and frozen
`docs/v0-3/s3/s3-quantile-semantics-contract.md` §7.1–§7.5. Code-read traced
P50/P80/P90 on `origin/main` at base `37f6fa7` with git blob bindings. This R1
does not modify Python, models, parameters, coverage execution, or TEST.

~~~text
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
~~~

`CHECKLIST_EXECUTED=true` ≠ `VERIFIED_TRUE_UPPER_QUANTILE`. All three fields
failed verification — not PASS, not coverage computable, not model change
allowed, not `NO_VERSIONED` flip. #301 preliminary conclusions are not this R1
result. This evidence is not a coverage package or versioned forecast artifact.
Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Frozen §7 execution summary

### 1.1 Step 7.1 — Field trace (blob-bound)

~~~text
backend/app/maturity/service.py=80632f330973baa844ae1fbe62684b9beeb687bd
backend/app/maturity/calibration.py=05dfbef10fca8ea4ccd190cad4d331f3cec15a20
backend/app/residual_model/model.py=c4c6d2907cf3a0b67787606b9b538edc1e1277c6
backend/app/residual_model/projection.py=4ce69012d4596f396d4d963c96c02f5d20a7e5c3
backend/app/harvest_state/service.py=049dff1b93db15b681b352fb99b40c4b86bc598d
backend/app/core_forecast/service.py=71fa1780b1737c2e525b0649c799447b5a3c8b1b
backend/app/residual_model/metrics.py=pinball branch audit only
~~~

**P50:** `reconcile_p50_mass(expected_total_kg, density)` allocates normalized
maturity density to daily `p50_kg` (point mass). Task 9 persists separate
`forecast_quantile=P50` rows. Residual layer adds `predicted_residual_p50` to
structural P50 anchor. Core forecast reconciles Task 8 `p50_kg` to member supply.

**P80:** Task 8 `p80 = p50 + (effective_total * p80_margin_share * widening)` with
margin shares from `calibration.py` `empirical_quantile` on held-out curve error
(`interval_semantics=pointwise_marginal`). Residual layer fits quantile=0.8 on
residual label but publishes `structural_arrival_p50_kg + predicted_residual_p80_kg`
with `projected_p80 = max(projected_p50, clamped_p80)`.

**P90:** Same structure as P80 with `p90_margin_share` and quantile=0.9 residual
estimator; `projected_p90 = max(projected_p80, clamped_p90)`.

### 1.2 Step 7.2 — Classification

~~~text
P50_PRIMARY=POINT_ESTIMATE
P50_SECONDARY=MONOTONIC_PROJECTION_ARTIFACT
P80_PRIMARY=SYMMETRIC_MARGIN
P80_SECONDARY=MONOTONIC_PROJECTION_ARTIFACT
P90_PRIMARY=SYMMETRIC_MARGIN
P90_SECONDARY=MONOTONIC_PROJECTION_ARTIFACT
TRUE_UPPER_QUANTILE_CANDIDATE=false (all three)
~~~

Residual quantile regressors on the residual label do not yield verified true
upper quantiles of harvest outcome after P50 anchoring and monotonic projection.

### 1.3 Step 7.3 — Pairing validity

~~~text
P50_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P50 AND EXACT_ACTUAL_PAIRED
P80_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P80 AND EXACT_ACTUAL_PAIRED
P90_COVERAGE_MASK=S2_STATUS_COMPARABLE AND FORECAST_QUANTILE_P90 AND EXACT_ACTUAL_PAIRED
PAIRING_RULES_CONFIRMED=true
COVERAGE_PUBLICATION_STATUS=NOT_COMPUTABLE
REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
COVERAGE_RATIOS_PUBLISHED=false
~~~

Complete daily row set is not a prerequisite for this semantics step. No coverage
ratios or tonnage invented.

### 1.4 Step 7.4 — Pinball branch audit

~~~text
IMPLEMENTATION=backend/app/residual_model/metrics.py pinball_loss
FORMULA=mean(max(q*(actual-forecast_q),(q-1)*(actual-forecast_q)))
UNDER_BRANCH=actual>=forecast_q → q*(actual-forecast_q)
OVER_BRANCH=actual<forecast_q → (q-1)*(actual-forecast_q)
BRANCH_REVERSAL_DETECTED=false
PINBALL_SCORES_PUBLISHED=false
PINBALL_VERIFICATION_FAILED=false
~~~

### 1.5 Step 7.5 — Disposition

~~~text
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
IS_SEMANTICS_VERIFIED_TRUE_UPPER_QUANTILE_PACKAGE=false
~~~

Checklist completed; none of the three fields are `VERIFIED_TRUE_UPPER_QUANTILE`.
Classification is not `UNRESOLVED`, therefore disposition is `VERIFICATION_FAILED`
(not lingering `NOT_VERIFIED`).

## 2. Live registry update

Only `CURRENT_P*_SEMANTICS_STATUS` updated in `docs/v0-3/development-plan.md`
§4.4 live state block to match evidence JSON. `CURRENT_P*_SEMANTICS_VERIFIED`
remain `false`. `S3_B_COVERAGE_EXECUTION_AUTHORIZED` remains `false`.

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and R1 pointer
- `docs/v0-3/s3/s3-quantile-semantics-contract.md` §14 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §93 pointer
- `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §15 pointer

Historical live-authority and grant pointer snapshots are not refreshed.

## 3. Honest boundary

~~~text
CHECKLIST_EXECUTED_TRUE_DOES_NOT_MEAN_VERIFIED_TRUE_UPPER_QUANTILE=true
VERIFICATION_FAILED_NOT_PASS=true
VERIFICATION_FAILED_NOT_COVERAGE_COMPUTABLE=true
FORBIDDEN_TREAT_301_PRELIMINARY_AS_R1_RESULT=true
FORBIDDEN_CHANGE_MODEL_TO_FORCE_PASS=true
FORBIDDEN_TREAT_FAILED_CLAIM_AS_VERIFIED_TRUE_UPPER_QUANTILE=true
FORBIDDEN_PUBLISH_COVERAGE_RATIOS=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COVERAGE_EXECUTION=true
IMPLEMENTATION_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_COVERAGE_PACKAGE=true
FORBIDDEN_TREAT_THIS_EVIDENCE_AS_VERSIONED_FORECAST_ARTIFACT=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 4. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=9500d7efce83102797655b5bf0fb0e7c6896a64a9449ea5007269bdd2bd7f723
~~~

## 5. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
