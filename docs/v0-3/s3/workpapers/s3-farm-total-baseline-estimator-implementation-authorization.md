# V0.3-S3 Farm-total Baseline Estimator Implementation Authorization (R1)

> Scope: docs-only implementation authorization issuance — no estimator code, execution, or scoring
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_IMPLEMENTATION_AUTHORIZATION_R1`
> Task class: `DOCS_ONLY_IMPLEMENTATION_AUTHORIZATION_ISSUANCE`
> Parent: PR #562 merge `c8719c31489ff6fe1bd33b0e31603066d784c3d2`

## Machine-readable header

```text
ARTIFACT_ID=V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=R1
TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_IMPLEMENTATION_AUTHORIZATION_ISSUANCE

BASE_MAIN_SHA=c8719c31489ff6fe1bd33b0e31603066d784c3d2
PARENT_PR=562
PARENT_MERGE_SHA=c8719c31489ff6fe1bd33b0e31603066d784c3d2

USER_GATE=可以继续

OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463

V0_3_S3_FARM_TOTAL_BASELINE_ESTIMATOR_IMPLEMENTATION_AUTHORIZED=true
ESTIMATOR_IMPLEMENTATION_AUTHORIZED=true

ESTIMATOR_IMPLEMENTED=false
LIVE_ESTIMATOR_EXECUTED=false
VALIDATION_BASELINE_MATERIALIZED=false
VALIDATION_BASELINE_SCORED=false

AUTHORIZATION_GRANTED=true
IMPLEMENTATION_PERFORMED=false
EXECUTION_PERFORMED=false

AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_ESTIMATOR=true
AUTHORIZATION_MERGE_DOES_NOT_EXECUTE_ESTIMATOR=true
AUTHORIZATION_MERGE_DOES_NOT_SCORE_VALIDATION=true
AUTHORIZATION_MERGE_DOES_NOT_READ_TEST=true

S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false

TEST_ACCESS=false
TEST_USE=SEALED

MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false

IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The user gate `可以继续` authorizes issuance of this **implementation grant**
only. A later deterministic implementation PR requires a separate user gate
`可以实施`.

```text
IMPLEMENTATION_AUTHORIZED=true
≠
ESTIMATOR_IMPLEMENTED=true

IMPLEMENTATION_AUTHORIZED=true
≠
LIVE_ESTIMATOR_EXECUTED=true

IMPLEMENTATION_AUTHORIZED=true
≠
VALIDATION_BASELINE_SCORED=true

IMPLEMENTATION_AUTHORIZED=true
≠
TEST_ACCESS=true
```

## 1. Upstream authority (reference only)

| Role | Path |
| --- | --- |
| Parent contract | `docs/v0-3/s3/s3-farm-total-baseline-estimator-contract.md` |
| Owner decision binding | `docs/v0-3/s3/s3-farm-total-baseline-estimator-owner-decision-binding.md` |
| Owner decision evidence | `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-owner-decision-binding.json` |
| Farm-total dataset types | `backend/app/forecast_quality/farm_total_dataset.py` |
| Farm-total data plane | `backend/app/forecast_quality/farm_total_data_plane.py` |

```text
OWNER_DECISION_SHA256=39722ff8e8a520813975cd7270b6453db388633bffee9c90fb12140440431463
OWNER_DECISION_STATUS=ACCEPTED
OWNER_DECISION_COMPLETE=true
```

This authorization does not modify the owner-decision binding artifacts.

## 2. Frozen estimator semantics (implementation-bound)

Future implementation is authorized **only** for this owner-frozen configuration:

```text
BASELINE_ESTIMATOR_FAMILY=GROUP_SPECIFIC_HISTORICAL_STATISTIC
TIME_AXIS=HARVEST_BUSINESS_DATE
AREA_NORMALIZATION_POLICY=NO_AREA_NORMALIZATION
POOLING_GRAIN=BASELINE_FARM_GROUP_SPECIFIC
TRAIN_AGGREGATION_STATISTIC=MEDIAN

MIN_TRAIN_SUPPORT=5
MIN_TRAIN_SUPPORT_UNIT=DISTINCT_VALID_TRAIN_HARVEST_DAYS_PER_BASELINE_FARM_GROUP
MIN_TRAIN_SUPPORT_UNIT_CLASS=DERIVED_SEMANTIC_NORMALIZATION
MIN_TRAIN_SUPPORT_UNIT_DERIVED_FROM=MIN_TRAIN_SUPPORT

UNSEEN_GROUP_POLICY=FAIL_CLOSED
MISSING_DAY_POLICY=SKIP_OUTPUT
COLD_START_POLICY=FAIL_CLOSED

VALIDATION_USE_POLICY=EVALUATION_ONLY
OUTPUT_SEMANTICS=DAILY_HARVEST_KG_PER_BASELINE_FARM_GROUP

BASELINE_OUTPUT_DISTRIBUTION_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
BASELINE_P80_P90_REASON=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
```

## 3. Authorized future implementation behavior

For each `baseline_farm_group_key` independently:

1. Derivation input is TRAIN only.
2. Use only governed Farm-total TRAIN data-plane rows.
3. Do not redefine “valid row” — `EXISTING_FARM_TOTAL_DATA_PLANE_VALIDATION` is authoritative.
4. Support = number of distinct `harvest_business_date` rows for the group.
5. Minimum support = **5**.
6. If support &lt; 5: `FAIL_CLOSED` — no pool/global/prior-period/synthetic fallback.
7. If support ≥ 5: median of `actual_harvest_quantity_kg` over governed TRAIN rows.
8. Median semantics: odd → middle ordered value; even → arithmetic mean of two middle ordered values.
9. Do not use `area_mu` mathematically.
10. Do not pool across `baseline_farm_group_key`.
11. Output unit is **kg**.
12. Output key: `baseline_farm_group_key` × `harvest_business_date`.
13. `MISSING_DAY_POLICY=SKIP_OUTPUT` — no synthesized dates absent from governed target keys.

### 3.1 Recommended functional separation

Architectural separation is authorized and preferred (names not frozen):

- `derive_farm_total_baseline_estimator(train_dataset)` — TRAIN-only derivation
- `project_farm_total_baseline(estimator_state, target_keys)` — deterministic projection

The implementation must make it structurally impossible for VALIDATION actual
quantities to affect TRAIN median derivation.

## 4. Validation boundary

```text
VALIDATION_USE_POLICY=EVALUATION_ONLY
VALIDATION_USES_FOR_FITTING=false
VALIDATION_USES_FOR_FAMILY_SELECTION=false
VALIDATION_USES_FOR_PARAMETER_TUNING=false
VALIDATION_USES_FOR_EVALUATION=true
```

Future implementation may generate baseline point values for governed VALIDATION
evaluation keys, but estimator state must be derived entirely from TRAIN.
`actual_harvest_quantity_kg` on VALIDATION rows must not affect medians, support,
family selection, parameters, or fallbacks.

If an interface receives VALIDATION rows, it may consume only the minimum governed
identity fields needed to establish eligible evaluation keys.

## 5. TEST boundary

```text
TEST_ACCESS=false
TEST_USE=SEALED
```

TEST remains completely out of scope. No TEST partition acceptance or byte reads.

## 6. Quantile boundary

Future implementation must **not** emit P80/P90, create a baseline distribution,
infer uncertainty from TRAIN, copy incumbent quantiles, or fit residual
distributions.

## 7. Model / S4 boundary

```text
MODEL_CHANGE=false
PARAMETER_CHANGE=false
V0_3_S4_AUTHORIZED=false
```

This baseline is for S3 diagnosis/evaluation. It must not modify incumbent model
behavior, tune model parameters, or authorize S4.

## 8. Persistence boundary

```text
PERSISTENCE=IN_MEMORY_ONLY
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
```

No Alembic, DB schema, ORM model, new table, or persistence migration.

## 9. Authorized future paths (later implementation PR only)

After separate user gate `可以实施`, a later implementation PR may add **exactly**:

| Kind | Path |
| --- | --- |
| Production | `backend/app/forecast_quality/farm_total_baseline_estimator.py` |
| Tests | `backend/tests/forecast_quality/test_farm_total_baseline_estimator.py` |

```text
EXISTING_FILE_MUTATION_AUTHORIZED=false
```

If implementation later proves an existing-file modification unavoidable, stop
and report the required path and reason before changing it.

### 9.1 Authorized future module capabilities

- Immutable estimator/result dataclasses
- Deterministic blocker/result types
- TRAIN-only estimator derivation
- Group support computation
- Deterministic Decimal median computation
- Target-key projection
- Fail-closed outcomes
- Canonical deterministic ordering
- Explicit output point rows

Must consume existing types from `farm_total_dataset.py` without duplicating or
replacing the Farm-total data plane.

### 9.2 Authorized future test themes (deterministic, in-memory)

Minimum coverage themes: odd/even median; Decimal preservation; support=5 pass;
support&lt;5 fail-closed; independent group medians; no cross-group pooling;
`area_mu` immaterial; unseen group fail-closed; skip absent target keys;
deterministic ordering; VALIDATION actuals cannot affect derivation; no P80/P90;
no TEST path.

Tests use synthetic in-memory governed-style fixtures only. No official TEST bytes.

## 10. Live execution boundary (not authorized)

This grant does **not** authorize the later implementation PR to:

- run against official TRAIN/VALIDATION live datasets;
- compute real group medians;
- publish real baseline values;
- score real VALIDATION performance;
- compare baseline against incumbent;
- produce S3 metric results;
- access TEST.

Live execution requires a separate execution task/gate.

## 11. This PR boundary

```text
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
```

This docs-only authorization PR changes exactly two new artifacts under
`docs/v0-3/s3/workpapers/` and `docs/v0-3/s3/evidence/`.

Evidence: `docs/v0-3/s3/evidence/s3-farm-total-baseline-estimator-implementation-authorization.json`
