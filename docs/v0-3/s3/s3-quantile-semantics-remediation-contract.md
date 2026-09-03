# V0.3-S3-B Quantile Semantics Remediation Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT
CONTRACT_VERSION=v0-3-s3-b-quantile-semantics-remediation-contract-v1
TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_ONLY
PARALLEL_LANE=S3-B
SLICE=V0.3-S3
ENGLISH_ID=QUANTILE_SEMANTICS_REMEDIATION_ARCHITECTURE
USER_GATE=授权
INTERPRETED_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AUTHORING_ONLY
CONTRACT_AUTHORING_AUTHORIZED=true
CONTRACT_ONLY=true
BASE_MAIN_SHA=323c5e7b886b594e6f1cb76dd7d621d03f00a461
BASE_MAIN_TREE_SHA=9ccface3c206687fb2ba8a838a058c34fdeea04d
BASE_REF=origin/main
PARENT_CLOSEOUT_PR=534
PARENT_CLOSEOUT_MERGE=323c5e7b886b594e6f1cb76dd7d621d03f00a461
PARENT_COMPLETED_FAMILY=DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY
ORIGINAL_S3_B_PROCEDURE_CONTRACT_PR=301
ORIGINAL_S3_B_PROCEDURE_CONTRACT_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
ORIGINAL_S3_B_VERIFIED_CLAIM_GRANT_PR=385
ORIGINAL_S3_B_VERIFIED_CLAIM_GRANT_MERGE=37f6fa7acfb4c6e516e2021c083002fed7001da0
FAILED_VERIFICATION_R1_PR=386
FAILED_VERIFICATION_R1_MERGE=3463336d1539332cb9bb81117ff52cf70e9120e6
FAILED_VERIFICATION_R1_EVIDENCE_JSON_SHA256=9500d7efce83102797655b5bf0fb0e7c6896a64a9449ea5007269bdd2bd7f723
PARENT_OBSERVATION_TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_OBSERVATION_R0
PARENT_OBSERVATION_REVIEW_STATUS=PASS
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE=true
GRANT_REQUIRES_SEPARATE_USER_GATE_授权=true
~~~

~~~text
S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_AUTHORIZED=true
S3_B_QUANTILE_SEMANTICS_REMEDIATION_GRANT_AUTHORIZED=false
S3_B_QUANTILE_SEMANTICS_REMEDIATION_IMPLEMENTATION_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
PARAMETER_CHANGE_AUTHORIZED=false
TRAINING_AUTHORIZED=false
BACKTEST_AUTHORIZED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_MUTATION_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NEXT_TASK_AUTHORIZED=false
STOP_AFTER_CONTRACT_AUTHORING=true
NEXT_GATE=S3_B_QUANTILE_SEMANTICS_REMEDIATION_CONTRACT_REVIEW
~~~

This document freezes the **lawful remediation architecture** required to
replace the current unverified P50 / P80 / P90 production semantics with final
published quantiles that may later be independently verified against the frozen
S3-B quantile-semantics procedure contract
(`docs/v0-3/s3/s3-quantile-semantics-contract.md`). It defines future
implementation authority boundaries only.

It **must not**:

- implement, train, or tune a model;
- read TEST or compute coverage or new pinball scores;
- flip `CURRENT_P*_SEMANTICS_STATUS`;
- issue an implementation Grant;
- mutate historical S3-B procedure / grant / failed-R1 meaning.

Historical statuses remain:

~~~text
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent observation (PASS)

~~~text
OBSERVATION_TASK_ID=V03_S3_B_QUANTILE_SEMANTICS_REMEDIATION_OBSERVATION_R0
OBSERVATION_REVIEW_STATUS=PASS
OBSERVATION_REPOSITORY_MUTATION_PERFORMED=false
OBSERVED_CURRENT_CLASSES=P50=POINT_ESTIMATE;P80=SYMMETRIC_MARGIN;P90=SYMMETRIC_MARGIN
CURRENT_RESIDUAL_QUANTILE_COMPOSITION_VALID_FOR_FINAL_TARGET=UNPROVEN
CURRENT_MONOTONIC_PROJECTION_CONFERS_QUANTILE_SEMANTICS=false
OBSERVATION_RECOMMENDED_CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
~~~

### 1.2 Frozen S3-B procedure and failed verification chain

~~~text
S3_B_PROCEDURE_CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-contract.md
S3_B_PROCEDURE_CONTRACT_PR=301
S3_B_PROCEDURE_CONTRACT_MERGE=f9e7b221722d74789112142aebb77a5c69687ea3
S3_B_GRANT_PR=385
S3_B_GRANT_MERGE=37f6fa7acfb4c6e516e2021c083002fed7001da0
S3_B_FAILED_R1_PR=386
S3_B_FAILED_R1_MERGE=3463336d1539332cb9bb81117ff52cf70e9120e6
S3_B_FAILED_R1_EVIDENCE_JSON_SHA256=9500d7efce83102797655b5bf0fb0e7c6896a64a9449ea5007269bdd2bd7f723
DO_NOT_REWRITE_HISTORICAL_S3_B_CHAIN=true
~~~

### 1.3 Q1 / V0.2 metric authority (reference only)

~~~text
Q1_PATH=docs/forecast-quality/slice-q1-forecast-target-and-evaluation-contract.md
Q1_QUANTILE_CALIBRATION_SECTION=§9.7
V0_2_METRIC_CONTRACT_PATH=docs/forecast-quality/s3-quality-metrics-contract.md
V0_2_QUANTILE_COVERAGE_SECTION=§10
V0_2_PAIRING_SECTION=§11.1–§11.3
DO_NOT_MUTATE_V0_2_METRIC_CONTRACT=true
~~~

## 2. Canonical remediation architecture

~~~text
CANONICAL_OPTION=FINAL_TARGET_DIRECT_QUANTILE_MODEL
FINAL_PUBLISHED_QUANTILES_DIRECTLY_TARGET_FINAL_Y=true
P50_LEVEL=0.50
P80_LEVEL=0.80
P90_LEVEL=0.90
~~~

Required production semantics after a separately authorized implementation:

- P50 must be produced from a `q=0.50` quantile objective on the **same final
  target random variable Y** defined in §3.
- P80 must be produced from a `q=0.80` quantile objective on the **same Y**.
- P90 must be produced from a `q=0.90` quantile objective on the **same Y**.

Forbidden as final semantics authority:

~~~text
POINT_ESTIMATE_ONLY=true
SYMMETRIC_MARGIN_AROUND_P50=true
FIELD_NAME_ONLY=true
EMPIRICAL_COVERAGE_ONLY=true
MONOTONIC_PROJECTION_ONLY=true
STRUCTURAL_P50_PLUS_RESIDUAL_QUANTILE_WITHOUT_PROVEN_COMPOSITION=true
~~~

Training objectives (future implementation):

~~~text
P50_OBJECTIVE=PINBALL_LOSS_Q_0_50_ON_FINAL_TARGET
P80_OBJECTIVE=PINBALL_LOSS_Q_0_80_ON_FINAL_TARGET
P90_OBJECTIVE=PINBALL_LOSS_Q_0_90_ON_FINAL_TARGET
~~~

Do **not** train `q=0.8/0.9` on `Y - structural_p50` and then claim
`structural_p50 + q(residual)` is automatically `q(Y)`.

## 3. Final target authority resolution (repository-bound)

### 3.1 Authority status

~~~text
FINAL_TARGET_AUTHORITY_STATUS=RESOLVED
CONTRACT_REVIEW_READY_REQUIRES_RESOLVED_FINAL_TARGET=true
~~~

`observed_effective_receipt_kg` is **not** promoted as lawful final target Y
for the S3 quantile verification lane. It is the incumbent residual-manifest
factory-receipt label and is explicitly **not** the frozen S1/S2 forecast
target.

### 3.2 Frozen final target Y

~~~text
FINAL_TARGET_AUTHORITY_PATH=docs/v0-3/s1/target-decision-and-quantity-contract.md
FINAL_TARGET_AUTHORITY_SECTION=CURRENT_FORECAST_TARGET / Existing forecast vocabulary
FINAL_TARGET_Y=model_harvested_marketable_quantity_kg
FINAL_TARGET_GRAIN=SEASON×FARM×SUBFARM×VARIETY×TARGET_DATE×FORECAST_CUTOFF×MODEL_IDENTITY×FORECAST_QUANTILE
FINAL_TARGET_PHYSICAL_LABEL_GRAIN=FARM×SUBFARM×VARIETY×HARVEST_BUSINESS_DATE
FINAL_TARGET_ACTUALS_AUTHORITY=actual_harvest_quantity_kg
FINAL_TARGET_ACTUALS_AUTHORITY_PATH=docs/v0-3/s1/target-decision-and-quantity-contract.md
FINAL_TARGET_ACTUALS_AUTHORITY_SECTION=CURRENT_ACTUAL_LABEL
FINAL_TARGET_PAIRING_RULE=V0.2 §11.1–§11.3 EXACT_ACTUAL_PAIRED; one actual physical row reused across P50/P80/P90 forecast rows at the same physical grain
~~~

Supporting repository bindings (not reopened):

| Authority | Path | Binding |
| --- | --- | --- |
| S1 forecast target | `docs/v0-3/s1/target-decision-and-quantity-contract.md` | `CURRENT_FORECAST_TARGET=model_harvested_marketable_quantity_kg` |
| S1 actual label | same | `CURRENT_ACTUAL_LABEL=actual_harvest_quantity_kg` |
| S2 materialized target | `docs/v0-3/s2/s2-materialized-dataset-contract.md` | `FORECAST_TARGET=model_harvested_marketable_quantity_kg` |
| S3 backtest forecasts | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §2 | `V0_3_S3_FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` |
| S3 backtest actuals | same §2.1 | `V0_3_S3_ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION` |
| Incumbent binding forecast field | `backend/app/rolling_backtest/orchestration.py` | `forecast_value_kg=core_row.model_harvested_marketable_quantity_kg` |
| S3-B verification objective | `docs/v0-3/s3/s3-quantile-semantics-contract.md` §2 | `P(actual ≤ forecast_q) ≈ q` under valid pairing |
| Calculation grain | `docs/forecast-quality/s3-quality-metrics-contract.md` §11 | `CALCULATION_BASE_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE` |

Explicit exclusions:

~~~text
OBSERVED_EFFECTIVE_RECEIPT_KG_IS_NOT_S3_FINAL_TARGET_Y=true
FACTORY_RECEIPT_PROXY_IS_NOT_PRIMARY_HARVEST_LABEL=true
FINAL_CORRECTED_ARRIVAL_QUANTITY_IS_MODEL_OUTPUT_NOT_LABEL=true
CURRENT_RESIDUAL_TARGET_IS_NOT_FINAL_TARGET_Y=true
~~~

Incumbent residual lane facts preserved:

~~~text
INCUMBENT_RESIDUAL_LABEL_FIELD=residual_label_kg
INCUMBENT_RESIDUAL_LABEL_FORMULA=observed_effective_receipt_kg - structural_arrival_p50_kg
INCUMBENT_RESIDUAL_MANIFEST_GRAIN=DESTINATION_FACTORY×TARGET_ARRIVAL_LOCAL_DATE
CURRENT_STRUCTURAL_P50_ANCHOR_IS_NOT_FINAL_QUANTILE_AUTHORITY=true
CURRENT_MONOTONIC_PROJECTION_IS_ORDERING_ONLY=true
~~~

## 4. Structural model boundary

Task 8 maturity formulas may remain for structural forecasting, feature
generation, fallback, diagnostics, or compatibility.

~~~text
STRUCTURAL_MODEL_MAY_REMAIN_FEATURE_SOURCE=true
STRUCTURAL_P50_MAY_BE_FEATURE=true
STRUCTURAL_P80_MAY_BE_FEATURE=true
STRUCTURAL_P90_MAY_BE_FEATURE=true
STRUCTURAL_P50_IS_NOT_FINAL_P50_AUTHORITY=true
STRUCTURAL_P80_IS_NOT_FINAL_P80_AUTHORITY=true
STRUCTURAL_P90_IS_NOT_FINAL_P90_AUTHORITY=true
~~~

Read-only upstream dependencies (not mandatory mutation merely because they
participate in the old pipeline):

~~~text
READ_ONLY_UPSTREAM_DEPENDENCIES=backend/app/maturity/model.py;backend/app/maturity/service.py;backend/app/maturity/calibration.py
~~~

## 5. Future mandatory change surface

Semantic responsibilities currently violated by the incumbent residual lane:

1. select `residual_label_kg` as training target instead of final Y;
2. train `q=0.50/0.80/0.90` on residual label;
3. publish `structural_p50 + predicted_residual_q`;
4. serialize artifact identity without `prediction_target_kind`;
5. treat monotonic projection as semantics proof.

| Path | Symbols / responsibility | Mandatory |
| --- | --- | --- |
| `backend/app/residual_model/dataset.py` | `build_training_matrix` — label must be final Y | yes |
| `backend/app/residual_model/model.py` | `train_quantile_estimators`, `predict_quantiles`, artifact metadata | yes |
| `backend/app/residual_model/service.py` | training, prediction, metrics inputs, projection/finalization | yes |
| `backend/app/residual_model/projection.py` | remove `structural_p50 + residual_q` as final semantics path | yes |
| `backend/app/residual_model/config.py` | `prediction_target_kind` / model-family discriminator | yes |

## 6. Potential change surface (not pre-authorized)

Each entry must be resolved at implementation Grant; Contract records current
classification:

| Path | `CHANGE_REQUIRED` | Reason |
| --- | --- | --- |
| `backend/app/residual_model/training_manifest.py` | true | must build lawful `model_harvested_marketable_quantity_kg` labels at member/farm grain instead of factory `observed_effective_receipt_kg` / `residual_label_kg` |
| `backend/app/residual_model/schemas.py` | true | manifest row and artifact metadata types for `prediction_target_kind` and final-Y label fields |
| `backend/app/residual_model/persistence.py` | true | fail-closed load/serialize of `prediction_target_kind` in artifact metadata |
| `backend/app/residual_model/application.py` | true | publish final-target kg predictions without residual composition semantics |
| `backend/app/models/residual_model.py` | false | existing JSON metadata columns suffice when `MIGRATION_REQUIRED=false` |
| `backend/app/api/rolling_backtest_replay_trained.py` | false | S2 binding already reads `model_harvested_marketable_quantity_kg`; remediation aligns production semantics to that field |
| `backend/app/core_forecast/service.py` | true | wire remediated final-target quantiles into `model_harvested_marketable_quantity_kg` publication consumed by S3 binding |
| `backend/app/harvest_state/service.py` | false | structural/feature source only; not final quantile authority |

## 7. Downstream compatibility

~~~text
FORECAST_QUANTILE_ENUM_CHANGE_REQUIRED=false
CORE_FORECAST_SCHEMA_LABEL_CHANGE_REQUIRED=false
HARVEST_STATE_QUANTILE_LABEL_CHANGE_REQUIRED=false
PUBLIC_P50_P80_P90_LABELS_PRESERVED=true
DOWNSTREAM_REQUIRES_SEMANTIC_SOURCE_SUBSTITUTION_ONLY=true
~~~

External quantile labels `P50`, `P80`, `P90` remain. Downstream consumers
require semantic source substitution, not label renames.

Downstream semantic consumers:

~~~text
DOWNSTREAM_SEMANTIC_CONSUMERS=backend/app/rolling_backtest/orchestration.py;backend/app/forecast_quality/*;backend/app/trial.py;docs/forecast-quality/s3-quality-metrics-contract.md §10–§11
~~~

## 8. Model family / artifact identity

~~~text
NEW_MODEL_SEMANTIC_VERSION_REQUIRED=true
IN_PLACE_INCUMBENT_ARTIFACT_OVERWRITE_FORBIDDEN=true
INCUMBENT_MODEL_HISTORY_PRESERVED=true
REMEDIATION_MODEL_TARGET_KIND=FINAL_TARGET_QUANTILE
~~~

Future artifact identity must include at minimum:

~~~text
model_family
model_version
artifact_schema_version
prediction_target_kind
quantile_level
feature_schema_hash
training_manifest_hash
training_signature
training_cutoff_authority
~~~

Incumbent residual-target artifacts must fail closed when loaded as final-target
artifacts.

## 9. Train / validation authority

~~~text
TRAIN_AND_VALIDATION_ONLY=true
TEST_REMAINS_SEALED=true
TEST_EVALUATION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
FEATURES_AVAILABLE_AT_FORECAST_CUTOFF=true
NO_POST_CUTOFF_FEATURE_LEAKAGE=true
LABEL_OBSERVATION_AUTHORITY_VALID=true
FORECAST_TARGET_GRAIN_MATCH=true
LAWFUL_TARGET_PAIRING_UNAVAILABLE_FAIL_CLOSED=true
~~~

## 10. Crossing / projection contract

~~~text
MONOTONIC_ORDERING_REQUIRED=true
MONOTONIC_PROJECTION_CONFERS_QUANTILE_SEMANTICS=false
QUANTILE_CROSSING_POLICY=DETERMINISTIC_REARRANGEMENT_WITH_FINAL_OUTPUT_VERIFICATION
~~~

If deterministic monotonic rearrangement remains:

- it is an ordering safeguard only;
- it cannot be cited as semantic proof;
- later semantics verification must evaluate **final published** values after all
  clamping / rearrangement / projection;
- raw and final crossing counts must be auditable.

## 11. Fallback policy

~~~text
FALLBACK_QUANTILE_SEMANTICS_POLICY=FAIL_CLOSED_NO_VERIFIED_QUANTILE_OUTPUT
STRUCTURAL_ONLY_FALLBACK_PRETENDS_VERIFIED_QUANTILES=false
~~~

Structural-only fallback may not silently publish structural P50/P80/P90 under
verified-quantile semantics.

## 12. Migration decision

~~~text
MIGRATION_REQUIRED=false
~~~

Rationale: truthful target-kind separation does not require Alembic schema
mutation. Incumbent `residual_model_artifact` metadata is JSON; incumbent
`residual_model_manifest_row` historical columns (`observed_effective_receipt_kg`,
`structural_p*_kg`, `residual_label_kg`) remain append-only historical record of
the factory-receipt residual lane. Future remediation binds identity through:

- new `model_family` / `model_version` / `artifact_schema_version`;
- new `prediction_target_kind=FINAL_TARGET_QUANTILE` in artifact metadata;
- `training_signature` and loader fail-closed checks that reject incumbent
  residual-target artifacts.

No migration is authored in this Contract PR.

## 13. Future test obligations

### 13.1 Mandatory test change surface

Future implementation evidence must cover at minimum:

1. training label is final target Y (`model_harvested_marketable_quantity_kg`),
   not `residual_label_kg`;
2. q levels are exactly `0.50 / 0.80 / 0.90` on the same Y;
3. predictions are final-target kg before downstream publication;
4. no structural-P50 addition in final-target mode;
5. target-kind artifact identity is fail-closed;
6. forecast-cutoff feature visibility remains legal;
7. `P50 ≤ P80 ≤ P90` final published ordering;
8. fallback cannot claim verified quantile semantics;
9. same inputs + same artifact produce deterministic outputs;
10. legacy incumbent residual-target artifact cannot load as final-target artifact.

Likely affected families:

~~~text
MANDATORY_TEST_CHANGE_SURFACE=backend/tests/residual_model/test_projection.py;backend/tests/residual_model/test_service.py;core forecast / Task8 / Task9 integration acceptance touching model_harvested_marketable_quantity_kg publication
~~~

### 13.2 Conditional test change surface

~~~text
CONDITIONAL_TEST_CHANGE_SURFACE=backend/tests/maturity/test_model.py;backend/tests/maturity/test_maturity_golden.py
MATURITY_TESTS_MANDATORY_ONLY_IF_MATURITY_PRODUCTION_SEMANTICS_MUTATED=true
~~~

### 13.3 Unchanged compatibility tests

Tests that assert label enums, schema field names, or non-quantile structural
behavior without depending on residual composition semantics remain compatible
when production semantics are substituted at the publication boundary.

## 14. Post-implementation verification gate

~~~text
IMPLEMENTATION_SUCCESS_IS_NOT_SEMANTICS_VERIFICATION=true
POST_IMPLEMENTATION_VERIFICATION_REQUIRES_SEPARATE_S3_B_R1=true
CONTRACT_MERGE_DOES_NOT_FLIP_CURRENT_P_STAR_SEMANTICS_STATUS=true
~~~

Only a separate semantics-verification R1 may produce
`VERIFIED_TRUE_UPPER_QUANTILE`.

## 15. Coverage / pinball gate

~~~text
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
NO_EMPIRICAL_COVERAGE_IN_THIS_CONTRACT=true
NO_NEW_PINBALL_SCORES_IN_THIS_CONTRACT=true
TRAINING_PINBALL_OBJECTIVE_IS_NOT_CALIBRATION_PROOF=true
~~~

## 16. Companion version state (preserved)

~~~text
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_A2_COMPLETENESS_PASS_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
THIS_REMEDIATION_CONTRACT_DOES_NOT_COMPLETE_S3=true
~~~

## 17. Contract artifacts

Created by this family:

~~~text
CONTRACT_PATH=docs/v0-3/s3/s3-quantile-semantics-remediation-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-b-quantile-semantics-remediation-contract-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-b-quantile-semantics-remediation-contract-r1.json
~~~

Do **not** modify:

~~~text
docs/v0-3/s3/s3-quantile-semantics-contract.md
docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-authorization.md
docs/v0-3/s3/workpapers/s3-b-quantile-semantics-verified-claim-r1.md
docs/v0-3/s3/evidence/s3-b-quantile-semantics-verified-claim-r1.json
~~~

## 18. Acceptance criteria

Contract review `PASS` requires all §2–§17 fields explicit and
`CONTRACT_REVIEW_READY=true` in evidence JSON. Grant and implementation remain
separately authorized.
