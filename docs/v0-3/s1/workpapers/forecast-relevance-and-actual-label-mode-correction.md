# V0.3-S1 Forecast Relevance and Actual-Label Mode Correction

## Correction identity and scope

```text
CORRECTION_ID=V0_3_S1_FORECAST_RELEVANCE_AND_ACTUAL_LABEL_MODE_CORRECTION
BASE_MAIN_SHA=94bc13be073e49ab62b102019a8e8de9bb2306c2
DOCUMENT_STATUS=CORRECTION_CANDIDATE_FOR_INDEPENDENT_REVIEW
SOURCE_002_ACTUAL_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
ACTUAL_LABEL_PURPOSE=HISTORICAL_FINAL_ACTUAL_FOR_FORECAST_EVALUATION
SOURCE_002_REREAD=false
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
DATABASE_WRITE=false
MODEL_CHANGE=false
BACKTEST_STARTED=false
```

This correction aligns the current V0.3 actual-label governance with the
confirmed forecast business meaning. Source 002 is a governed recorded
business label: the final daily actual quantity recorded by the scan-and-weigh
system. It is not a replay of every source-system record version and it is not
an attempt to reconstruct a theoretical farm-pick weight before the governed
scan-weigh event.

```text
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
PRE_MEASUREMENT_WEIGHT_RECONSTRUCTION_REQUIRED=false
V0_3_RECORDED_LABEL_PROFILE_OVERRIDES_STRICT_PRE_WEIGH_RECONSTRUCTION=true
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
```

The correction does not issue a Q2C decision. It does not establish that a
particular forecast-side quantity is physically equivalent to the recorded
label, and it does not make Source 002 source-specific eligible.

## Current IDFL label-side authority

For the current Source 002 IDFL mode, the label-side authority is the
immutable source object, its accepted completeness authority, its
source-object-bound derivation lineage, and the separately accepted target
binding. Record-level replay fields are not hard prerequisites for this label
mode.

```text
V0_3_ACTUAL_LABEL_MODE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_BUSINESS_EVENT=HARVEST
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_MEASUREMENT_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_UNIT=KG
V0_3_ACTUAL_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
LABEL_REVISION_WINNER_REQUIRED=false
SOURCE_RECORDED_AT_REQUIRED_FOR_LABEL_SIDE=false
SOURCE_AVAILABLE_AT_REQUIRED_FOR_LABEL_SIDE=false
SOURCE_FINALIZED_AT_REQUIRED_FOR_LABEL_SIDE=false
SOURCE_CANCELLED_AT_REQUIRED_FOR_LABEL_SIDE=false
SOURCE_002_RECORD_LEVEL_LIFECYCLE_FIELDS_BLOCK_CURRENT_IDFL_ELIGIBILITY=false
FULL_LIFECYCLE_AUDIT_BLOCKER_REMOVED=true
```

`FULL_LIFECYCLE_AUDIT_BLOCKER_REMOVED=true` means that the record-level
lifecycle audit is no longer treated as a hard blocker for the current Source
002 IDFL label side. It does not mean the historical lifecycle evidence has
been collected, that replay modes are eligible, or that source authority has
been accepted.

The following fields remain useful evidence, but are non-blocking audit or
replay fields for the current IDFL label side:

```text
NON_BLOCKING_AUDIT_ITEMS=
SOURCE_RECORD_ID,
SOURCE_RECORDED_AT_FOR_LABEL_SIDE,
SOURCE_AVAILABLE_AT_FOR_LABEL_SIDE,
SOURCE_REVISED_AT,
SOURCE_FINALIZED_AT,
SOURCE_CANCELLED_AT,
REVISION_NUMBER,
SUPERSEDED_PARENT,
FULL_RECORD_REVISION_LINEAGE
```

They remain required when the selected mode is `AS_OF_EVALUATION` or
`FINAL_ADJUDICATED`, and when an accepted forecast-input source class uses
record-level historical visibility or revision semantics.

## Forecast-input relevance audit

The current repository implementation was checked at the feature-domain and
feature-construction level. This was a code-path audit only; it did not read
Source 002 or any business row-level data.

```text
FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY
FORECAST_INPUT_SOURCE_CLASS_USAGE_MUST_BE_ESTABLISHED_FROM_MODEL_OR_CONTRACT=true
CURRENT_MODEL_IMPLEMENTATION_FEATURE_SOURCE_DOMAINS=TASK9,ANALYTICS,WEATHER,PLANNING,CALENDAR
FORECAST_INPUT_SOURCE_CLASS_USED_BY_CURRENT_MODEL=AREA,YIELD_PLAN,PHENOLOGY,WEATHER_OBSERVATION,PICKER_COUNT,HARVEST_EFFICIENCY,MARKETABLE_RATE
CURRENT_MODEL_ANALYTICS_FEATURE_PATH=FACTORY_RECEIPT_LAG_ROLLING_AND_CUMULATIVE
FORECAST_INPUT_SOURCE_CLASS_TAXONOMY_GAP=ANALYTICS_FACTORY_RECEIPT
SOURCE_002_RECENT_ACTUAL_HARVEST_USED_AS_FEATURE=false
CURRENT_MODEL_HISTORICAL_WEATHER_FORECAST_FEATURE_PATH_FOUND=false
```

The relevant implementation paths are:

- `backend/app/residual_model/feature_registry.py` for source domains,
  availability classes, and feature provenance;
- `backend/app/residual_model/prediction_features.py` for factory-receipt lag,
  rolling, and cumulative analytics feature construction plus weather/planning
  inputs;
- `backend/app/residual_model/training_manifest.py` for the `FactReceiptDaily`
  factory-receipt fact path and its source-cutoff visibility checks;
- `backend/app/maturity/service.py` for area, expected-yield, marketable-rate,
  and phenology inputs;
- `backend/app/harvest_state/service.py` for picker-count and harvest
  efficiency inputs;
- `backend/app/core_forecast/cli.py` for the forecast input schema and fixture
  path.

The analytics path above is factory-receipt data, not Source 002 field
scan-and-weigh actual-harvest data. Because the current S1 source-class
vocabulary does not expose a confirmed canonical class name for that analytics
receipt path, this correction records a taxonomy gap rather than inventing a
new accepted source class. The forecast-input point-in-time control remains
mandatory for every source class actually used by a forecast. The IDFL
exemption is limited to the actual-label side and cannot authorize future
input leakage.

## Retained blockers and non-blocking boundaries

The seven items below are the direct forecast-readiness workstream: they are
what must be resolved to move from the governed label boundary toward a fair
historical evaluation. They are not a complete replacement for Source 002's
source-specific IDFL eligibility gates.

```text
DIRECT_FORECAST_READINESS_BLOCKERS=
SOURCE_COMPLETENESS,
MISSING_DAY_RULE,
JULY_UNMAPPED_DATE_POLICY,
FORMAL_ACTUAL_LABEL_DATASET_FREEZE,
TRAIN_VALIDATION_TEST_SPLIT_POLICY,
FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_CONTROL,
Q2C_TARGET_BINDING

CURRENT_SOURCE_002_IDFL_ELIGIBILITY_BLOCKERS=
SOURCE_AUTHORITY_ACCEPTANCE,
SOURCE_COHORT_ACCEPTANCE,
SOURCE_CUSTODY_ACCEPTANCE,
SOURCE_COMPLETENESS,
SOURCE_OBJECT_BOUND_ROW_LINEAGE,
MAPPING_POLICY_IDENTITY,
COVERAGE_SCOPE_ENTITY_IDENTITIES,
INCLUSION_EXCLUSION_ACCEPTANCE,
MISSING_DAY_RULE,
JULY_UNMAPPED_DATE_POLICY,
Q2C_TARGET_BINDING

SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
SOURCE_COMPLETENESS_POLICY_VERSION=NOT_ISSUED
SOURCE_COMPLETENESS_EVIDENCE_HASH=NOT_ISSUED

MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_NO_HARVEST_COUNT=false
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_DATA_ERROR_COUNT=false

UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING

SOURCE_002_IDFL_V1_ELIGIBILITY=false
SOURCE_002_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
```

Package A has issued governed mapping/scope, inclusion/exclusion, and custody
artifacts, but issuance is not acceptance. The full eligibility list therefore
keeps the corresponding acceptance/binding gates until they are separately
closed. The observed maximum harvest business date is not a completeness
watermark:

```text
OBSERVED_MAX_HARVEST_BUSINESS_DATE_IS_COMPLETENESS_WATERMARK=false
```

The lifecycle request remains available as an optional technical evidence
request. It is applicable to replay modes and to a forecast-input source class
only when that class actually uses the requested fields:

```text
SOURCE_002_RECORD_LEVEL_LIFECYCLE_AUDIT_SCOPE=OPTIONAL_AUDIT_AND_REPLAY_MODE_EVIDENCE
REQUIRED_IF_LABEL_MODE=AS_OF_EVALUATION_OR_FINAL_ADJUDICATED
REQUIRED_FOR_CURRENT_SOURCE_002_IDFL_MODE=false
SOURCE_002_RECORD_LEVEL_LIFECYCLE_REQUEST_RETAINED=true
```

## Governance boundary

This is a contract and evidence-scope correction only. It does not change the
canonical S1 acceptance record or any canonical gate status.

```text
CANONICAL_GATE_STATUS_CHANGED=false
GATE_PASS_COUNT=0
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

The current Source 002 IDFL mode remains blocked by source-specific authority,
cohort, custody acceptance, completeness, source-object-bound row lineage,
mapping/scope, inclusion/exclusion acceptance, missing-day and July policy,
target binding, and related S1 gates. Removing an inapplicable replay blocker
is not acceptance of any of those gates.

## Correction conclusion

```text
RECORDED_LABEL_BUSINESS_BOUNDARY_EXPLICIT=true
FULL_LIFECYCLE_AUDIT_BLOCKER_REMOVED=true
FORECAST_INPUT_POINT_IN_TIME_CONTROL_PRESERVED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
SOURCE_002_REREAD=false
DATABASE_WRITE=false
MODEL_CHANGE=false
BACKTEST_STARTED=false
INDEPENDENT_REVIEW_REQUIRED=true
```

The next action is an independent review of this forecast-relevance and
actual-label-mode correction. No source attestation, cohort manifest, Q2C
decision, S1 acceptance, S2 authorization, or backtest is authorized by this
document.
