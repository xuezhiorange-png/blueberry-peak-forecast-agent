# V0.3-S3 Farm-total Baseline Evaluation Package Contract and Implementation Authorization (R1)

> Scope: docs-only contract freeze + implementation authorization issuance — no Python, no execution, no scoring
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_CONTRACT_AND_IMPLEMENTATION_AUTHORIZATION_R1`
> Task class: `DOCS_ONLY_CONTRACT_AND_IMPLEMENTATION_AUTHORIZATION`
> Parent estimator: PR #564 merge `9eb5f115c1f41e2d0f1156df4440f5eb4872860a`

## Machine-readable header

```text
ARTIFACT_ID=V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=R1

TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_CONTRACT_AND_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_CONTRACT_AND_IMPLEMENTATION_AUTHORIZATION

BASE_MAIN_SHA=9eb5f115c1f41e2d0f1156df4440f5eb4872860a

PARENT_ESTIMATOR_PR=564
PARENT_ESTIMATOR_MERGE_SHA=9eb5f115c1f41e2d0f1156df4440f5eb4872860a

USER_GATE=可以继续

V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_CONTRACT_AUTHORIZED=true
V0_3_S3_FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_IMPLEMENTATION_AUTHORIZED=true

FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_IMPLEMENTED=false

IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true

LIVE_BASELINE_EXECUTION_AUTHORIZED=false
LIVE_TRAIN_EXECUTION_AUTHORIZED=false
LIVE_VALIDATION_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_AUTHORIZED=false

S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false

TEST_ACCESS=false
TEST_USE=SEALED

MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The user gate `可以继续` authorizes issuance of this **contract freeze and
implementation grant** only. A later deterministic implementation PR requires a
separate user gate `可以实施`.

```text
CONTRACT_AUTHORIZED=true
≠
IMPLEMENTED=true

IMPLEMENTATION_AUTHORIZED=true
≠
LIVE_EXECUTION_AUTHORIZED=true

IMPLEMENTATION_AUTHORIZED=true
≠
VALIDATION_SCORING_AUTHORIZED=true

IMPLEMENTATION_AUTHORIZED=true
≠
S3_METRIC_EXECUTION_AUTHORIZED=true

IMPLEMENTATION_AUTHORIZED=true
≠
TEST_ACCESS=true
```

## 1. Upstream authority (reference only)

| Role | Path |
| --- | --- |
| Parent estimator module | `backend/app/forecast_quality/farm_total_baseline_estimator.py` |
| Owner decision binding | `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-binding.md` |
| Estimator implementation authorization | `docs/v0-3/s3/workpapers/s3-farm-total-baseline-estimator-implementation-authorization.md` |
| Farm-total dataset types | `backend/app/forecast_quality/farm_total_dataset.py` |
| Farm-total data plane | `backend/app/forecast_quality/farm_total_data_plane.py` |
| Canonical hash authority | `backend/app/forecast_quality/canonical.py` |

```text
OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463
PARENT_ESTIMATOR_PR=564
PARENT_ESTIMATOR_MERGE_SHA=9eb5f115c1f41e2d0f1156df4440f5eb4872860a
```

This authorization does not modify upstream binding or estimator artifacts.

## 2. Package purpose

The future module is an **in-memory deterministic evaluation-preparation package**.

```text
EVALUATION_PACKAGE_IS_NOT_METRIC_EXECUTION=true
EVALUATION_PACKAGE_IS_NOT_BACKTEST_EXECUTION=true
PERSISTENCE=IN_MEMORY_ONLY
```

### 2.1 Authorized future capabilities

The future implementation MAY:

- accept an already-governed `FarmTotalTrainingDataset`;
- accept an already-governed `FarmTotalValidationDataset`;
- construct identity-only VALIDATION target keys;
- derive the already-authorized TRAIN estimator via `derive_farm_total_baseline_estimator`;
- project baseline points to governed VALIDATION identities via `project_farm_total_baseline`;
- preserve per-target fail-closed outcomes;
- compute deterministic canonical hashes;
- emit a reproducible in-memory package;
- expose provenance identities.

### 2.2 Prohibited future capabilities

The future implementation MUST NOT:

- read SOURCE-002 bytes;
- invoke live Farm-total data-plane materialization;
- read files or databases;
- write files or persist results;
- score VALIDATION;
- calculate MAE/WAPE/SMAPE/MAPE/bias;
- compare baseline to incumbent;
- produce S3 metric results;
- touch TEST.

## 3. Governed target-key construction

The future implementation must expose a deterministic operation equivalent to:

```text
build_farm_total_validation_target_keys(
    validation_dataset: FarmTotalValidationDataset,
) -> FarmTotalBaselineTargetKeySet
```

Target identity fields are exactly:

```text
season_business_key
baseline_farm_group_key
harvest_business_date
```

The builder must construct `FarmTotalBaselineTargetKey` from the already-implemented
estimator module.

```text
TARGET_KEY_IDENTITY_ONLY=true
TARGET_KEY_CONTAINS_ACTUAL_HARVEST=false
TARGET_KEY_CONTAINS_AREA=false
```

The target-key builder must not carry `actual_harvest_quantity_kg`,
`actual_harvest_kg_per_mu`, `area_mu`, or source actual quantities into the target
identity.

Canonical target order:

```text
season_business_key
baseline_farm_group_key
harvest_business_date
```

## 4. VALIDATION partition fail-closed boundary

Before extracting any target keys, the future implementation must verify:

1. `validation_dataset.partition_dataset.partition == "VALIDATION"`
2. every `row.partition == "VALIDATION"`

Required explicit blockers (or semantically equivalent enum values):

```text
NON_VALIDATION_PARTITION
NON_VALIDATION_ROW_PARTITION
```

Do not skip invalid rows. Do not accept mixed TRAIN/VALIDATION rows. Do not coerce
labels. Do not partially materialize a package after a partition violation.

## 5. Duplicate target fail-closed

Governed row grain is expected to provide a unique
`(season_business_key, baseline_farm_group_key, harvest_business_date)` target identity.

The future package must not silently deduplicate duplicate target identities.

If duplicate target identity is encountered:

```text
FAIL_CLOSED
DUPLICATE_VALIDATION_TARGET_KEY
```

Silently dropping a duplicate could hide an upstream authority violation.

## 6. TRAIN estimator orchestration

The future package must call the existing:

```text
derive_farm_total_baseline_estimator(train_dataset)
```

Do not reimplement support counting, median, group statuses, TRAIN row guards, or
Decimal median arithmetic.

```text
ESTIMATOR_IMPLEMENTATION_DUPLICATION_ALLOWED=false
```

The existing estimator module remains the sole authority for estimator derivation.

## 7. Baseline projection orchestration

The future package must call:

```text
project_farm_total_baseline(estimator_state, target_keys)
```

Do not implement a second projection algorithm.

Preserve:

| Condition | Behavior |
| --- | --- |
| Supported group | point emitted |
| `INSUFFICIENT_TRAIN_SUPPORT` | no numeric point + explicit outcome |
| `UNSEEN_GROUP` | no numeric point + explicit outcome |
| `MISSING_DAY_POLICY=SKIP_OUTPUT` | no synthesized calendar dates |

Do not interpolate, forward fill, or zero fill.

## 8. Package schema

Authorize a local schema identity constant:

```text
FARM_TOTAL_BASELINE_EVALUATION_PACKAGE_SCHEMA_VERSION=v0-3-s3-farm-total-baseline-evaluation-package-v1
```

This is an artifact-schema identity only. It is not `MODEL_CHANGE` or
`PARAMETER_CHANGE`.

## 9. Required future immutable types

Future implementation should use `@dataclass(frozen=True, slots=True)` for:

- `FarmTotalBaselineTargetKeySet`
- `FarmTotalBaselineEvaluationPackage`
- `FarmTotalBaselineEvaluationPackageDiagnostics`
- `FarmTotalBaselineEvaluationPackageBlocker` / error type as appropriate

The package must expose at least:

```text
schema_version
train_dataset_sha256
validation_dataset_sha256
target_keys
estimator_state
projection_result
target_count
emitted_point_count
blocked_target_count
estimator_state_sha256
target_identity_set_sha256
baseline_point_set_sha256
target_outcome_set_sha256
prediction_identity_sha256
package_sha256
```

No quantile fields. No metric-result fields.

## 10. Canonical hash authority

Future implementation must reuse:

```text
backend.app.forecast_quality.canonical.canonical_json_bytes
backend.app.forecast_quality.canonical.emit_s3_decimal
```

Do not invent a second JSON canonicalization system.

```text
HASH_ALGORITHM=SHA-256
ENCODING=UTF-8
JSON_KEYS=SORTED_BY_EXISTING_CANONICAL_JSON_BYTES
NATIVE_FLOAT_SERIALIZATION_FORBIDDEN=true
```

All hashes must be reproducible.

### 10.1 Required hash layers

**A. `estimator_state_sha256`**

Hash semantic group-estimate state only:

```text
baseline_farm_group_key
train_support_count
status
baseline_harvest_quantity_kg
```

Canonical group ordering by `baseline_farm_group_key`.

**B. `target_identity_set_sha256`**

Hash only identity-only target keys:

```text
season_business_key
baseline_farm_group_key
harvest_business_date
```

No validation actual quantity. No area.

**C. `baseline_point_set_sha256`**

Hash emitted point rows:

```text
season_business_key
baseline_farm_group_key
harvest_business_date
baseline_harvest_quantity_kg
```

No P80/P90.

**D. `target_outcome_set_sha256`**

Hash all target outcomes including target identity, status, whether point exists,
and point quantity when it exists.

**E. `prediction_identity_sha256`**

Deterministic prediction semantic identity. Must depend on at least:

```text
schema_version
train_dataset_sha256
estimator_state_sha256
target_identity_set_sha256
baseline_point_set_sha256
target_outcome_set_sha256
frozen estimator semantic identity
```

`prediction_identity_sha256` MUST NOT depend on:

```text
validation actual_harvest_quantity_kg
validation actual_harvest_kg_per_mu
validation area_mu
```

except indirectly through target identity fields, which themselves exclude these values.

**F. `package_sha256`**

Full provenance-bound package identity. MAY additionally bind
`validation_dataset_sha256`.

Therefore:

- VALIDATION actual quantities MAY change `package_sha256` through provenance.
- VALIDATION actual quantities MUST NOT change `target_identity_set_sha256`,
  baseline point values, `baseline_point_set_sha256`, or `prediction_identity_sha256`.

## 11. Validation actual leakage rule

```text
VALIDATION_USE_POLICY=EVALUATION_ONLY
VALIDATION_ACTUALS_USED_FOR_ESTIMATOR_DERIVATION=false
VALIDATION_ACTUALS_USED_FOR_BASELINE_PREDICTION=false
VALIDATION_ACTUALS_ALLOWED_IN_PROVENANCE_HASH_ONLY=true
```

No validation actual may affect TRAIN median, support count, group readiness, target
identity, emitted baseline quantity, or `prediction_identity_sha256`.

The full source validation dataset SHA may be retained only as provenance.

## 12. Provenance binding

The future package should preserve:

```text
train_dataset.partition_dataset.dataset_sha256
validation_dataset.partition_dataset.dataset_sha256
```

These are provenance identities only. The package must not claim those hashes were
independently re-materialized from live bytes. The future implementation PR is
synthetic-test-only.

## 13. Deterministic ordering

| Collection | Canonical order |
| --- | --- |
| Target keys | `season_business_key`, `baseline_farm_group_key`, `harvest_business_date` |
| Group estimates | `baseline_farm_group_key` |
| Points | `season_business_key`, `baseline_farm_group_key`, `harvest_business_date` |
| Target outcomes | same as target identity order |

Input row ordering must not alter semantic prediction outputs or semantic hashes.

## 14. Empty target set

Do not invent an owner policy for empty VALIDATION target sets.

Future implementation may deterministically return a valid empty package:

```text
target_count=0
emitted_point_count=0
blocked_target_count=0
```

with stable canonical hashes.

```text
EMPTY_TARGET_SET_IS_NOT_VALIDATION_SCORE=true
```

Do not reinterpret empty targets as PASS, FAIL, zero harvest, or metric success.

## 15. Quantile boundary

```text
BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

Future package MUST NOT define p80, p90, quantile distribution, variance, standard
deviation, confidence interval, or residual distribution.

## 16. Metric / scoring boundary

The future package must not contain functions named or semantically equivalent to:

```text
score_validation
compute_mae
compute_wape
compute_smape
compute_mape
compute_bias
compare_incumbent
metric_result
```

```text
VALIDATION_SCORING_AUTHORIZED=false
S3_METRIC_EXECUTION_AUTHORIZED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
```

The package stops at deterministic baseline prediction preparation.

## 17. Live execution boundary

The later implementation PR is allowed to use synthetic/in-memory
`FarmTotalTrainingDataset` and `FarmTotalValidationDataset` for unit/integration
tests only.

It is NOT authorized to:

- read official TRAIN bytes;
- read official VALIDATION bytes;
- call `load_authority_bundle_from_paths`;
- call `materialize_farm_total_baseline_data_plane` on official data;
- run `scripts/run_v03_farm_total_data_plane_verification.py`;
- compute real farm-group medians;
- emit real baseline predictions;
- persist real packages.

```text
LIVE_ESTIMATOR_EXECUTED=false
LIVE_TRAIN_EXECUTION_AUTHORIZED=false
LIVE_VALIDATION_EXECUTION_AUTHORIZED=false
```

## 18. TEST boundary

```text
TEST_ACCESS=false
TEST_USE=SEALED
TEST_EXECUTION_AUTHORIZED=false
```

No TEST bytes, target keys, package, or fixture pretending to be governed live data.

## 19. Model / S4 boundary

```text
MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false
```

The future module must not import or alter incumbent model logic. This baseline
package is diagnostic infrastructure only.

## 20. Persistence boundary

```text
PERSISTENCE=IN_MEMORY_ONLY
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
```

No DB, ORM, Alembic, migration, table, object storage, filesystem writer, or artifact
repository mutation.

## 21. Authorized future paths (later implementation PR only)

After separate user gate `可以实施`, a later implementation PR may add **exactly**:

| Kind | Path |
| --- | --- |
| Production | `backend/app/forecast_quality/farm_total_baseline_evaluation_package.py` |
| Tests | `backend/tests/forecast_quality/test_farm_total_baseline_evaluation_package.py` |

```text
EXISTING_FILE_MUTATION_AUTHORIZED=false
FUTURE_AUTHORIZED_PRODUCTION_PATH_COUNT=1
FUTURE_AUTHORIZED_TEST_PATH_COUNT=1
```

The future implementation must reuse, without modification:

- `backend/app/forecast_quality/farm_total_baseline_estimator.py`
- `backend/app/forecast_quality/farm_total_dataset.py`
- `backend/app/forecast_quality/farm_total_data_plane.py`
- `backend/app/forecast_quality/farm_total_policy.py`

If implementation later proves an existing-file modification unavoidable, stop and
report the required path before changing it.

## 22. Required future test matrix

The future implementation PR must contain a substantial synthetic integration suite.
Minimum required cases (38):

### A. Target construction

1. VALIDATION rows produce identity-only target keys.
2. Target keys contain no actual quantity field.
3. Target keys contain no area field.
4. Target order deterministic.
5. Outer non-VALIDATION partition fails closed.
6. Inner non-VALIDATION row fails closed before target construction.
7. Duplicate target identity fails closed.
8. Empty VALIDATION target set returns deterministic empty package.

### B. Estimator orchestration

9. Supported group emits correct existing-estimator baseline.
10. Insufficient-support group preserves `INSUFFICIENT_TRAIN_SUPPORT`.
11. Unseen group preserves `UNSEEN_GROUP`.
12. Mixed supported/blocked groups do not globally fail.
13. No cross-group pooling.
14. No date synthesis.

### C. Leakage

15. Two validation datasets with identical identities but radically different
    `actual_harvest_quantity_kg` produce identical target keys.
16. Same pair produces identical baseline point values.
17. Same pair produces identical `target_identity_set_sha256`.
18. Same pair produces identical `baseline_point_set_sha256`.
19. Same pair produces identical `prediction_identity_sha256`.
20. Their `validation_dataset_sha256` values differ.
21. Their full `package_sha256` values MAY differ because provenance changed.

### D. TRAIN dependency

22. Changing TRAIN actual quantities while identities remain fixed changes the
    appropriate estimator output and prediction identity.
23. Changing TRAIN `area_mu` only, with actual quantities unchanged, does not alter
    baseline point values.

### E. Hash / replay

24. `estimator_state_sha256` replay equality.
25. `target_identity_set_sha256` replay equality.
26. `baseline_point_set_sha256` replay equality.
27. `target_outcome_set_sha256` replay equality.
28. `prediction_identity_sha256` replay equality.
29. `package_sha256` replay equality.
30. Input-order permutation does not change semantic hashes.

### F. Output surface

31. Point output contains Decimal kg only.
32. No native float baseline arithmetic.
33. No P80 field.
34. No P90 field.
35. No metric result fields.
36. Blocked outcomes contain no synthetic numeric baseline.

### G. Regression

37. Existing estimator test suite remains green.
38. Farm-total data-plane R1/R2 suites remain green.

No official live data is needed for any test above.

## 23. Required future validation commands

The later implementation task must run, at minimum:

```bash
uv run pytest backend/tests/forecast_quality/test_farm_total_baseline_estimator.py backend/tests/forecast_quality/test_farm_total_baseline_evaluation_package.py -q
```

```bash
uv run pytest backend/tests/forecast_quality/test_farm_total_baseline_data_plane_r1.py backend/tests/forecast_quality/test_farm_total_baseline_data_plane_r2.py backend/tests/forecast_quality/test_farm_total_baseline_estimator.py backend/tests/forecast_quality/test_farm_total_baseline_evaluation_package.py -q
```

plus existing `ruff check`, `ruff format --check`, and `mypy` for the relevant new
files.

## 24. This PR boundary

```text
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
```

This docs-only authorization PR changes exactly two new artifacts under
`docs/v0-3/s3/workpapers/` and `docs/v0-3/s3/evidence/`.

Evidence:
`docs/v0-3/s3/evidence/s3-farm-total-baseline-evaluation-package-implementation-authorization.json`
