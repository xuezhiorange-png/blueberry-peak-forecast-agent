# S3-B quantile semantics remediation contract R1 workpaper

## Task envelope

~~~text
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AUTHORING_ONLY
CONTRACT_AUTHORING_AUTHORIZED=true
GRANT_AUTHORIZED=false
IMPLEMENTATION_AUTHORIZED=false
BASE_MAIN_SHA=323c5e7b886b594e6f1cb76dd7d621d03f00a461
BASE_MAIN_TREE_SHA=9ccface3c206687fb2ba8a838a058c34fdeea04d
PARENT_CLOSEOUT_PR=534
PARENT_CLOSEOUT_MERGE=323c5e7b886b594e6f1cb76dd7d621d03f00a461
PARENT_OBSERVATION_TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_OBSERVATION_R0
PARENT_OBSERVATION_REVIEW_STATUS=PASS
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1_IMPLEMENTATION=true
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_MUTATION_AUTHORIZED=false
STOP_AFTER_CONTRACT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_REVIEW
~~~

## Purpose

Freeze remediation architecture to replace incumbent unverified P50/P80/P90
semantics with direct final-target quantile modeling. This workpaper records
contract authoring only.

## Parent observation inheritance

Observation R0 reviewed `PASS` with:

- `CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL`
- incumbent classes: P50 point estimate; P80/P90 symmetric margin
- `CURRENT_RESIDUAL_QUANTILE_COMPOSITION_VALID_FOR_FINAL_TARGET=UNPROVEN`
- `CURRENT_MONOTONIC_PROJECTION_CONFERS_QUANTILE_SEMANTICS=false`

This Contract resolves `MIGRATION_REQUIRED=false` and binds final target Y from
frozen S1/S2/S3 authority rather than the residual-manifest factory-receipt
field.

## Final target authority resolution

Repository inspection at base `323c5e7`:

| Question | Resolution |
| --- | --- |
| Lawful S3 forecast target Y? | `model_harvested_marketable_quantity_kg` |
| Authority | `docs/v0-3/s1/target-decision-and-quantity-contract.md` `CURRENT_FORECAST_TARGET` |
| Lawful actual for pairing? | `actual_harvest_quantity_kg` |
| Actuals authority | `V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION` per `s3-backtest-and-diagnosis-contract.md` §2 |
| Pairing rule | V0.2 §11 `EXACT_ACTUAL_PAIRED`; one actual physical row across quantiles |
| Grain | `SEASON×FARM×SUBFARM×VARIETY×TARGET_DATE×FORECAST_CUTOFF×MODEL_IDENTITY×FORECAST_QUANTILE` |
| Is `observed_effective_receipt_kg` lawful final Y? | **No** — factory receipt proxy; incumbent residual label only |

`FINAL_TARGET_AUTHORITY_STATUS=RESOLVED`.

## Canonical remediation architecture

~~~text
CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
P50_OBJECTIVE=PINBALL_LOSS_Q_0_50_ON_FINAL_TARGET
P80_OBJECTIVE=PINBALL_LOSS_Q_0_80_ON_FINAL_TARGET
P90_OBJECTIVE=PINBALL_LOSS_Q_0_90_ON_FINAL_TARGET
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
~~~

## Mandatory vs potential mutation surfaces

Mandatory production responsibilities:

- `backend/app/residual_model/dataset.py` (`build_training_matrix`)
- `backend/app/residual_model/model.py` (train/predict/artifact metadata)
- `backend/app/residual_model/service.py` (train/predict/metrics/finalization)
- `backend/app/residual_model/projection.py` (composition removal)
- `backend/app/residual_model/config.py` (`prediction_target_kind`)

Read-only upstream:

- `backend/app/maturity/model.py`
- `backend/app/maturity/service.py`
- `backend/app/maturity/calibration.py`

Potential (classified in contract §6 with `CHANGE_REQUIRED` flags).

## Migration

~~~text
MIGRATION_REQUIRED=false
~~~

Artifact identity versioning via new `model_family`, `artifact_schema_version`,
`model_version`, and `prediction_target_kind` in existing JSON metadata with
fail-closed loader checks. Historical manifest columns remain historical.

## Historical chain preservation

~~~text
ORIGINAL_S3_B_CONTRACT_PR=301
ORIGINAL_S3_B_GRANT_PR=385
FAILED_VERIFICATION_R1_PR=386
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
CONTRACT_DOES_NOT_FLIP_SEMANTICS_STATUS=true
~~~

## Changed files (this PR)

1. `docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md` (create)
2. `docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-contract-r1.md` (create)
3. `docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-contract-r1.json` (create)
4. `docs/v0-3/development-plan.md` (pointer only)

~~~text
PRODUCTION_CHANGED_FILES=NONE
TEST_CHANGED_FILES=NONE
MIGRATION_CHANGED_FILES=NONE
WORKFLOW_CHANGED_FILES=NONE
~~~

## Contract review readiness

All acceptance criteria from the remediation contract §18 are explicit in
evidence JSON. `CONTRACT_REVIEW_READY=true`.

Grant remains required before implementation.

Evidence digest:

~~~text
EVIDENCE_JSON_SHA256=08eb0ff2530e7b971f2d617556aba88fdd8774e6ad5f66a12b5ebf62510f1ad0
~~~
