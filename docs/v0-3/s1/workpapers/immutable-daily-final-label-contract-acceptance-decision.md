# IDFL v1 Atomic Cross-Contract Acceptance Decision

This decision record accepts the third actual-label mode as governing-contract
semantics only. It does not accept a source, cohort, target, rowset, or model
evaluation.

## Decision identity

```text
DECISION_ID=V0_3_S1_IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE
DECISION=ACCEPT
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1
IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE=true
IDFL_V1_I7_MODE_ACCEPTED=true
IDFL_V1_VISIBILITY_MODE_SEMANTICS_ACCEPTED=true
IDFL_V1_SOURCE_AUTHORITY_MODE_SEMANTICS_ACCEPTED=true
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=true
ATOMIC_ACCEPTANCE_REQUIRED=true
PARTIAL_ACCEPTANCE_ALLOWED=false
DESIGN_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
```

The accepted contract set is exactly:

```text
ACCEPTED_CONTRACT_SET=
docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md,
docs/v0-3/s1/visibility-inclusion-revision-contract.md,
docs/v0-3/s1/source-authority-and-cohort-manifest.md
```

The candidate that this decision supersedes as a candidate semantic artifact
is:

```text
SOURCE_CANDIDATE=
docs/v0-3/s1/workpapers/immutable-daily-final-label-contract-amendment-candidate.md
```

Acceptance is valid only when all three governing contracts carry the same
IDFL_V1 mode semantics. A change to only one or two contracts is not an
acceptance of IDFL_V1.

## Accepted design semantics

IDFL_V1 is a separate actual-label mode for an immutable daily business
aggregate:

```text
LABEL_VALUE_AUTHORITY=FINAL_OBSERVED_DAILY_BUSINESS_QUANTITY
LABEL_VISIBILITY_AUTHORITY=NOT_POINT_IN_TIME_REPLAYABLE
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
LABEL_OBSERVATION_CUTOFF_REQUIRED=false
REVISION_WINNER_REQUIRED=false
FINALIZED_AT_REQUIRED=false
SOURCE_RECORDED_AT_REQUIRED_FOR_LABEL_SIDE=false
SOURCE_SYSTEM_STABLE_RECORD_ID_REQUIRED=false
FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
EXISTING_AS_OF_EVALUATION_SEMANTICS_CHANGED=false
EXISTING_FINAL_ADJUDICATED_SEMANTICS_CHANGED=false
```

IDFL_V1 must not be called `AS_OF_EVALUATION`, `FINAL_ADJUDICATED`,
`POINT_IN_TIME_LABEL_REPLAY`, or `REVISION_WINNER_REPLAY`.
`FINAL_OBSERVED_LABEL != HISTORICAL_LABEL_REPLAY`.

## Atomic acceptance predicate

```text
IDFL_V1_ATOMIC_ACCEPTANCE_VALID=true
```

The predicate is true only because every required component is accepted in the
same contract set:

```text
IDFL_SOURCE_COMPLETENESS_AUTHORITY_REQUIREMENT_ACCEPTED=true
IDFL_SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIREMENT_ACCEPTED=true
IDFL_FORECAST_TARGET_INTERVAL_BINDING_ACCEPTED=true
IDFL_Q2C_INDEPENDENCE_PRESERVED=true
IDFL_MISSINGNESS_FAIL_CLOSED_PRESERVED=true
IDFL_FORECAST_SIDE_PIT_PRESERVED=true
AS_OF_SEMANTICS_PRESERVED=true
FINAL_ADJUDICATED_SEMANTICS_PRESERVED=true
```

If any predicate above becomes false, the mode acceptance is invalid and
`IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED` must be set to `false` in a new
reviewed decision.

## Completeness and lineage requirements

IDFL_V1 accepts the requirement for a completeness authority, not evidence
that the current Source 002 object satisfies it:

```text
SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED=true
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE_REQUIRED=true
SOURCE_COMPLETENESS_POLICY_VERSION_REQUIRED=true
SOURCE_COMPLETENESS_EVIDENCE_HASH_REQUIRED=true
SOURCE_COMPLETENESS_WATERMARK_AS_SOURCE_RECORDED_AT=false
SOURCE_COMPLETENESS_WATERMARK_AS_LABEL_VISIBILITY_TIME=false
EXPORT_TIME_AS_SOURCE_RECORDED_AT=false
LATE_ENTRY_NOT_APPLICABLE_IS_COMPLETENESS_PROOF=false
```

For every included label business date,
`HARVEST_BUSINESS_DATE <= SOURCE_COMPLETE_THROUGH_BUSINESS_DATE` must hold.
Without source-specific completeness evidence, source eligibility is blocked.

IDFL preserves audit lineage without inventing a source-system record identity:

```text
SOURCE_ROW_LINEAGE_REQUIRED=true
SOURCE_SYSTEM_STABLE_RECORD_ID_REQUIRED=false
SOURCE_SYSTEM_REVISION_LINEAGE_REQUIRED=false
SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_IS_SOURCE_SYSTEM_IDENTITY=false
```

The minimum derivation lineage is immutable source object identity, a
deterministic source-row locator or row-evidence identity, mapping evidence
identity, aggregation policy version, and canonical label identity. A locator
or row-evidence hash is internal audit lineage only. It is not an
`external_logical_record_id`, `external_revision_id`, source-system identity,
or revision lineage. Database row order is never an authority.

## Forecast, target, and missingness boundaries

Forecast-side point-in-time authority remains mandatory and is bound to the
accepted target-interval contract:

```text
FORECAST_TEMPORAL_ELIGIBILITY_AUTHORITY=
ACCEPTED_FORECAST_TARGET_INTERVAL_CONTRACT
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
FORECAST_CUTOFF_AT < FORECAST_TARGET_DATE_OR_WINDOW_END
HARVEST_BUSINESS_DATE_TO_FORECAST_TARGET_INTERVAL_MAPPING_REQUIRED=true
FARM_TIMEZONE=Asia/Shanghai
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

IDFL does not choose the physical target:

```text
IDFL_DOES_NOT_SELECT_Q2C_TARGET=true
TARGET_DECISION_REMAINS_SEPARATE=true
LABEL_TARGET_AUTHORITY=Q2C_ACCEPTED_TARGET
IDFL_TARGET_BINDING_STATUS=BLOCKED_PENDING_Q2C_ACCEPTANCE
Q2C_ACCEPTED=false
```

Missingness remains fail-closed and is not converted to zero by this mode
acceptance:

```text
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
NO_RECORD_TO_ZERO_MAPPING_STATUS=
BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
UNMAPPED_DATE_AUTO_ASSIGNMENT_ALLOWED=false
```

## What this decision accepts

- the IDFL third-mode definition and `IDFL_V1` version;
- the source-object completeness requirement;
- immutable-source-object-bound row derivation lineage;
- mode-aware actual-label visibility;
- preservation of forecast-side point-in-time authority;
- accepted forecast-target interval binding;
- independence of IDFL from Q2C target selection; and
- fail-closed missingness and unmapped-date boundaries.

## What this decision does not accept

```text
SOURCE_002_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
MISSING_DAY_ZERO_MAPPING_ACCEPTED=false
JULY_UNMAPPED_DATE_RESOLVED=false
S1_VISIBILITY_GATE_CLOSED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

No source-specific attestation, cohort manifest, Q2C decision, completeness
evidence, label rowset, ingestion, backtest, or model-quality claim is created
by this record.

## Operational boundary

```text
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
DATABASE_WRITE=false
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
REPOSITORY_RUNTIME_IMPLEMENTATION_CHANGED=false
```

The accepted status is `ACCEPTED_DESIGN_NOT_IMPLEMENTED`. Implementation,
source-specific acceptance, independent review of this package, Ready
transition, merge, S2, and backtest require separate authorization.

```text
NEXT_RECOMMENDED_ACTION=RUN_INDEPENDENT_REVIEW_OF_IDFL_V1_ATOMIC_ACCEPTANCE_PACKAGE
```
