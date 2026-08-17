# S1 Source Authority and Cohort Manifest

## Purpose and current state

This contract defines the identity, scope, and custody of an approved source
cohort without including the cohort itself. It accepts a governed
source-system attestation or equivalent authority; a developer-selected table,
fixture, or file name is not sufficient.

```text
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=ACCEPTED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=ACCEPTED
CURRENT_SOURCE_MANIFEST_STATUS=ACCEPTED
CURRENT_SOURCE_OWNER_ROLE=农场数据负责人
CURRENT_SOURCE_SYSTEM=扫码称重系统
CURRENT_SOURCE_DATASET=田间商品果每日采摘净重汇总
CURRENT_SOURCE_VERSION=scan-weight-export:v0_3_s1:002
CURRENT_SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
CURRENT_SOURCE_COHORT_ID=source-002-s1-cohort-v1
CURRENT_SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
CURRENT_SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
CURRENT_SOURCE_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
CURRENT_SOURCE_ATTESTATION_EFFECTIVE_AT=2026-08-16T21:42:00+08:00
CURRENT_SOURCE_ATTESTATION_STATUS=ATTESTED
CURRENT_SOURCE_ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
```

The current source-authority fields above are bound to the merged final Source
Owner Attestation. The cohort and manifest fields are bound to the merged,
schema-valid final Source Cohort Manifest and its independently reviewed hash.
This freezes the Source Cohort identity only; it does not freeze or materialize
the final clean rowset owned by S2.

The source-authority contract is source-class and label-mode aware. The
accepted IDFL_V1 mode changes only the actual-label representation rules; it
does not relax forecast-input visibility or accept the current source:

```text
IDFL_V1_MODE_CONTRACT_ACCEPTED=true
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=true
IDFL_V1_SOURCE_AUTHORITY_MODE_SEMANTICS_ACCEPTED=true
DESIGN_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
```

## Source authority identity

An accepted source authority must bind all of the following fields in one
attestation version. `schema_version` is a logical schema identity and is not
interchangeable with the separately bound `schema_hash`. `effective_time` describes the source
authority's period of applicability and is not replaced by the attestation
signature time.

```text
REQUIRED_SOURCE_AUTHORITY_IDENTITY_FIELDS=
source_system,
source_dataset,
source_version,
schema_version,
schema_hash,
source_snapshot_reference,
source_owner_role,
attestation_version,
attestation_effective_at,
effective_time,
attestation_status,
attestation_hash,
coverage_scope,
revision_policy,
withdrawal_and_void_policy,
known_exclusions
```

`source_snapshot_reference` is an immutable, non-sensitive, governed opaque
identity. It must not be a private URL or plaintext storage path. When a
locator must be bound for custody, only `storage_locator_hash` may be recorded.

```text
effective_time=
  effective_from,
  effective_to_or_open_ended,
  authority_timezone

coverage_scope=
  seasons,
  farms,
  subfarms,
  varieties,
  business_date_start,
  business_date_end,
  known_scope_boundaries

revision_policy=
  revision_policy_version,
  revision_policy_identity,
  winner_and_lineage_rule

withdrawal_and_void_policy=
  withdrawal_policy_version,
  void_propagation_policy_version,
  withdrawal_status_rule,
  void_status_rule
```

`attestation_status` must be `ATTESTED` before an authority can be accepted.
`DRAFT`, `SUPERSEDED`, `REVOKED`, `UNSIGNED`, and inferred values are not
acceptable. The attestation hash covers the canonical attestation object,
excluding transport metadata and personal data.

## S1/S2 ownership boundary

S1 freezes the identity and policy references of the source cohort. S2 owns the
materialized cleaned rowset and all downstream split or snapshot rowsets.

```text
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true

SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA=true
SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT=true
SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET=true
declared_source_row_count=NOT_PROVIDED
declared_source_byte_count=NOT_PROVIDED
```

Missing counts remain `NOT_PROVIDED`; they must not be represented as zero.
S1 does not use `accepted_row_count`, `cleaned_row_count`, or
`materialized_row_count` as source-cohort fields.

## Cohort manifest identity

The cohort manifest is an aggregate source identity and custody record. It must
not contain raw rows, cleaned rowsets, split rowsets, label snapshots, or
sensitive payloads. It binds:

```text
REQUIRED_COHORT_MANIFEST_FIELDS=
manifest_version,
cohort_id,
source_system,
source_dataset,
source_version,
schema_version,
schema_hash,
source_snapshot_reference,
source_owner_role,
attestation_version,
attestation_effective_at,
effective_time,
attestation_status,
attestation_hash,
coverage_scope,
revision_policy,
withdrawal_and_void_policy,
known_exclusions,
mapping_policy_version,
visibility_policy_version,
inclusion_policy_version,
revision_policy_version,
split_policy_version,
source_object_identity_hashes,
custody_record,
manifest_hash
```

Source object identity roles are references only:

```text
RAW_SOURCE_AUTHORITY_REFERENCE
SOURCE_OBJECT_REFERENCE
SOURCE_SCHEMA_REFERENCE
SOURCE_MAPPING_REFERENCE
```

The roles above do not represent `FINAL_CLEAN_ROWSET`, materialized dataset
partitions, split manifests, or label snapshots. Each reference is immutable,
versioned, and represented by a SHA-256 digest plus an opaque identity. A
source object cannot be replaced in place.

## Cohort coverage scope and exclusions

Coverage metadata is aggregate-only and must describe the applicable seasons,
farms, subfarms, varieties, business-date range, and known scope boundaries.
It may include declared source row and byte counts, but it does not establish
accepted, cleaned, or materialized row counts. It must also record known
exclusions and representativeness limits. A narrow cohort must not support a
global accuracy claim.

## Required physical semantics

The historical Q2C vocabulary remains part of the compatibility history. It is
not the sole hard requirement for the current V0.3 recorded-label profile and
the historical Q2C contract is not rewritten here:

```text
HISTORICAL_Q2C_PHYSICAL_EVENT=FARM_PICK
HISTORICAL_Q2C_QUANTITY_BASIS=OBSERVED_WEIGHT
HISTORICAL_Q2C_QUANTITY_UNIT=KG
HISTORICAL_Q2C_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
HISTORICAL_Q2C_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
HISTORICAL_Q2C_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
HISTORICAL_Q2C_PLOT_SUPPORTED=false
HISTORICAL_Q2C_PHYSICAL_SEMANTICS_SCOPE=HISTORICAL_Q2C_COMPATIBILITY_ONLY
```

The current V0.3 actual-label authority uses the recorded business label
profile. Its business event remains harvest, while its measurement boundary
is the governed scan-and-weigh record rather than a reconstructed theoretical
weight at the instant fruit was removed from the plant:

```text
V0_3_RECORDED_LABEL_PROFILE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_BUSINESS_EVENT=HARVEST
V0_3_ACTUAL_LABEL_MEASUREMENT_EVENT=VALID_FIELD_SCAN_WEIGH_RECORD
V0_3_ACTUAL_LABEL_MEASUREMENT_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_UNIT=KG
V0_3_ACTUAL_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
PRE_MEASUREMENT_WEIGHT_RECONSTRUCTION_REQUIRED=false
V0_3_RECORDED_LABEL_REQUIRED_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
V0_3_RECORDED_LABEL_REQUIRED_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
V0_3_RECORDED_LABEL_REQUIRED_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
V0_3_RECORDED_LABEL_PLOT_SUPPORTED=false
```

For the V0.3 recorded-label profile, source authority must bind the governed
scan-weight record identity, recorded marketable net weight in KG, the valid
field scan-and-weigh boundary, marketability and sorting/rejection rules,
farm timezone and local-day boundary, canonical grain, applicable
finalization/missing/correction/visibility authority, source identity,
coverage, mapping, and governance. These are the current label-eligibility
semantics; they do not select a forecast-side target or issue source-specific
acceptance.

The following fields are optional process provenance or metrology evidence for
this profile. They may be recorded when available, but their absence does not
block V0.3 recorded-label eligibility and they are not mandatory
label-eligibility fields:

```text
V0_3_RECORDED_LABEL_OPTIONAL_EVIDENCE_FIELDS=
transport_before_weighing,
storage_before_weighing,
postharvest_loss_rule,
tare_policy,
scale_precision,
scale_calibration_authority
TRANSPORT_BEFORE_WEIGHING_EVIDENCE_CLASS=OPTIONAL_PROCESS_PROVENANCE
STORAGE_BEFORE_WEIGHING_EVIDENCE_CLASS=OPTIONAL_PROCESS_PROVENANCE
POSTHARVEST_LOSS_RULE_EVIDENCE_CLASS=OPTIONAL_PROCESS_PROVENANCE
TARE_POLICY_EVIDENCE_CLASS=OPTIONAL_PROCESS_PROVENANCE
SCALE_PRECISION_EVIDENCE_CLASS=OPTIONAL_METROLOGY_EVIDENCE
SCALE_CALIBRATION_AUTHORITY_EVIDENCE_CLASS=OPTIONAL_METROLOGY_EVIDENCE
PRE_WEIGH_TRANSPORT_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_STORAGE_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_POSTHARVEST_LOSS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
ABSENCE_DOES_NOT_BLOCK_V0_3_RECORDED_LABEL_ELIGIBILITY=true
```

These requirement flags describe label-eligibility policy, not facts about
whether a transport, storage, post-harvest, tare, precision, or calibration
condition exists. No unknown process, tare method, device precision, or
calibration authority is inferred by this contract.

## Mapping and revision identity

The manifest must freeze the mapping policy used to resolve farm, subfarm,
variety, season, and business date. A live master-data remap after freeze is
not evidence. Mapping evidence is a versioned object with a schema/policy hash
and deterministic identity.

For AS_OF_EVALUATION and FINAL_ADJUDICATED, revision identity must preserve
source record identity, revision number, superseded parent, status,
source-recorded time, source availability time, source revision time,
finalized time where required, cancellation time where required, and
source-system scope. The winner is computed by the Q2A/I7 lineage rules; it is
never selected by largest quantity, latest import, database order, or lexical
hash.

IDFL_V1 is a deliberate source-object-bound exception for the actual-label
side only. It does not invent a source-system record identity or revision
history:

```text
SOURCE_ROW_LINEAGE_REQUIRED=true
SOURCE_SYSTEM_STABLE_RECORD_ID_REQUIRED=false
SOURCE_SYSTEM_REVISION_LINEAGE_REQUIRED=false
SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_IS_SOURCE_SYSTEM_IDENTITY=false
```

The minimum derivation lineage for each canonical IDFL label row is:

```text
immutable source object identity
+ deterministic source-row locator or source-row evidence identity
+ mapping evidence identity
+ aggregation policy version
+ canonical label identity
```

A row locator or row-evidence hash identifies evidence inside an immutable
source object for audit purposes. It must not be called an
`external_logical_record_id`, `external_revision_id`, source-system record
identity, or revision lineage. Database row order is never an authority.

## Hash and custody rules

```text
HASH_ALGORITHM=SHA-256
CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
MANUAL_CORRECTION_AUDITED=true
SILENT_VALUE_REPLACEMENT=false
SOURCE_ROW_LINEAGE_REQUIRED=true
REAL_DATA_ALLOWED_IN_GIT=false
```

Visibility is an explicit source-class and label-mode policy. The IDFL
exception applies only to `ACTUAL_HARVEST_LABEL +
IMMUTABLE_DAILY_FINAL_LABEL` and never propagates to forecast inputs or the two
replay modes:

```text
SOURCE_AUTHORITY_REQUIREMENT_IS_SOURCE_CLASS_AND_LABEL_MODE_AWARE=true
FORECAST_INPUT_POINT_IN_TIME_VISIBILITY_REQUIRED=true
ACTUAL_LABEL_VISIBILITY_REQUIREMENT=LABEL_MODE_DEPENDENT
REPLAY_LABEL_POINT_IN_TIME_VISIBILITY_REQUIRED=true
AS_OF_LABEL_POINT_IN_TIME_REPLAY_REQUIRED=true
FINAL_ADJUDICATED_FINALIZATION_AUTHORITY_REQUIRED=true
IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

IDFL_V1 source-object completeness is a required authority, not a current
source acceptance:

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

For each included IDFL label date, the source-object completeness watermark
must satisfy `HARVEST_BUSINESS_DATE <= SOURCE_COMPLETE_THROUGH_BUSINESS_DATE`
and be bound to the immutable source object or snapshot authority. Without
source-specific completeness evidence, the current IDFL source eligibility is
blocked.

IDFL_V1 governed label snapshots must bind, at minimum:

```text
IDFL_V1_REQUIRED_LABEL_SNAPSHOT_BINDINGS=
source_system,
source_dataset,
source_version,
schema_version,
schema_hash,
source_snapshot_reference,
source_object_identity_hashes,
source_complete_through_business_date,
source_completeness_policy_version,
source_completeness_evidence_hash,
source_row_lineage_manifest_hash,
source_owner_role,
attestation_version,
attestation_hash,
coverage_scope,
mapping_policy_version,
visibility_policy_version,
inclusion_policy_version,
split_policy_version,
custody_record_hash,
label_mode_version,
aggregate_policy_version,
source_object_set_hash,
canonical_label_row_set_hash,
coverage_manifest_hash,
exclusion_manifest_hash,
label_snapshot_hash
```

All identities remain non-sensitive and opaque. `HASH_ALGORITHM=SHA-256`,
`CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS`, and
`REAL_DATA_ALLOWED_IN_GIT=false` continue to apply. Database IDs, storage
paths, and private URLs are not canonical identities.

The IDFL aggregation order is:

```text
governed immutable source object set
-> accepted source scope and inclusion policy
-> accepted season/date mapping
-> canonical identity mapping
-> source-dimension aggregation
-> canonical daily label grouping
-> exact Decimal SUM
-> deterministic coverage and exclusion manifest
-> immutable final-observed label snapshot
```

```text
REVISION_WINNER_ALGORITHM=NOT_APPLICABLE
LATEST_ROW_FALLBACK_ALLOWED=false
LARGEST_REVISION_FALLBACK_ALLOWED=false
DATABASE_ROW_ORDER_AUTHORITY=false
IDFL_DOES_NOT_SELECT_Q2C_TARGET=true
TARGET_DECISION_REMAINS_SEPARATE=true
LABEL_TARGET_AUTHORITY=Q2C_ACCEPTED_TARGET
IDFL_TARGET_BINDING_STATUS=BLOCKED_PENDING_Q2C_ACCEPTANCE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
NO_RECORD_TO_ZERO_MAPPING_STATUS=
BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
UNMAPPED_DATE_AUTO_ASSIGNMENT_ALLOWED=false
```

An unexplained duplicate or conflict fails closed; no implicit winner may be
selected.

Forecast-side temporal authority remains mandatory for IDFL:

```text
FORECAST_TEMPORAL_ELIGIBILITY_AUTHORITY=
ACCEPTED_FORECAST_TARGET_INTERVAL_CONTRACT
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
FORECAST_CUTOFF_AT < FORECAST_TARGET_DATE_OR_WINDOW_END
HARVEST_BUSINESS_DATE_TO_FORECAST_TARGET_INTERVAL_MAPPING_REQUIRED=true
FARM_TIMEZONE=Asia/Shanghai
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

IDFL does not redefine the forecast horizon and does not authorize a raw
timestamp-to-business-date comparison. A stricter interval-start predicate,
if required, comes from the accepted forecast-target contract.

The source object, schema, mapping, visibility, inclusion, split, attestation,
and final manifest each have a distinct identity. A ZIP digest, a checksum
manifest digest, and a source-object digest must never be used
interchangeably.

The versioned custody record must bind:

```text
CUSTODY_RECORD_FIELDS=
custody_policy_version,
storage_type,
access_owner_role,
source_owner_role,
approved_usage_purpose,
least_privilege_scope,
authorized_role_set,
credential_reference_policy,
retention_policy_version,
retention_period_or_rule,
withdrawal_policy_version,
void_propagation_policy_version,
downstream_propagation_targets,
external_object_binding_hash,
custody_record_hash
```

The record contains policy identities and non-sensitive hashes only. It does
not contain credentials, tokens, private URLs, plaintext storage locators, or
personal identity.

## Withdrawal and void propagation

Source withdrawal must not silently delete prior evidence. It creates a new
versioned custody/status record. A withdrawn or void source identity must be
propagated to the source cohort, any future split manifest, any future label
snapshot manifest, and the acceptance record. Every affected unfinished gate
becomes `BLOCKED`; accepted artifacts are never rewritten in place. A
replacement source creates a new identity and new hashes. Only non-sensitive
hashes and policy identities may be retained in Git.

## Current blockers and acceptance requirements

```text
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=ACCEPTED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=ACCEPTED
CURRENT_SOURCE_ATTESTATION_STATUS=ATTESTED
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
CURRENT_SOURCE_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
CURRENT_SOURCE_ATTESTATION_EFFECTIVE_AT=2026-08-16T21:42:00+08:00
CURRENT_SOURCE_ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
CURRENT_SOURCE_COHORT_ID=source-002-s1-cohort-v1
CURRENT_SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
CURRENT_SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
S1_ACCEPTANCE_REQUIRES_ATTESTATION_STATUS_ATTESTED=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SOURCE_VERSION=true
S1_ACCEPTANCE_REQUIRES_SCHEMA_VERSION=true
S1_ACCEPTANCE_REQUIRES_EFFECTIVE_TIME=true
S1_ACCEPTANCE_REQUIRES_COVERAGE_SCOPE=true
S1_ACCEPTANCE_REQUIRES_WITHDRAWAL_AND_VOID_POLICY=true
S1_ACCEPTANCE_REQUIRES_SOURCE_OBJECT_HASHES=true
S1_ACCEPTANCE_REQUIRES_COHORT_MANIFEST_HASH=true
S1_ACCEPTANCE_REQUIRES_LINEAGE_AND_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_CUSTODY_RECORD=true
```

This document does not itself issue a source-specific or cohort-specific
acceptance result. The current canonical acceptance record now records Source
Authority acceptance from the merged PR #238 final-attestation closeout and
Source Cohort acceptance from the merged PR #241 final-manifest closeout; this
contract still does not accept Q2C. It may carry
`IDFL_V1_SOURCE_AUTHORITY_MODE_SEMANTICS_ACCEPTED=true` because that is
mode-contract semantic acceptance, not source or cohort acceptance.

The atomic IDFL contract acceptance state is distinct from source/cohort
acceptance:

```text
NO_SOURCE_SPECIFIC_ACCEPTANCE_RESULT_ISSUED_BY_THIS_DOCUMENT=true
NO_COHORT_SPECIFIC_ACCEPTANCE_RESULT_ISSUED_BY_THIS_DOCUMENT=true
IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE=true
IDFL_V1_SOURCE_AUTHORITY_MODE_SEMANTICS_ACCEPTED=true
IDFL_SOURCE_COMPLETENESS_AUTHORITY_REQUIREMENT_ACCEPTED=true
IDFL_SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIREMENT_ACCEPTED=true
IDFL_FORECAST_TARGET_INTERVAL_BINDING_ACCEPTED=true
IDFL_Q2C_INDEPENDENCE_PRESERVED=true
IDFL_MISSINGNESS_FAIL_CLOSED_PRESERVED=true
IDFL_FORECAST_SIDE_PIT_PRESERVED=true
AS_OF_SEMANTICS_PRESERVED=true
FINAL_ADJUDICATED_SEMANTICS_PRESERVED=true
DESIGN_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
S1_VISIBILITY_GATE_CLOSED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
```

## Historical post-PR238 pre-PR241 Source Authority mirror

```text
POST_PR238_CURRENT_MAIN_REVALIDATION=PASS
SOURCE_AUTHORITY_ACCEPTANCE_RECORD_PATH=docs/v0-3/s1/evidence/s1-acceptance-record.json
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_ID=4946622009
SOURCE_AUTHORITY_INDEPENDENT_REVIEW_RESULT=PASS
SOURCE_AUTHORITY_REVIEWED_HEAD_SHA=9b181f4e160981dca7a28fa584855e70a9555f34
SOURCE_AUTHORITY_EXACT_HEAD_CI_RUN_ID=31955752008
SOURCE_AUTHORITY_EXACT_HEAD_CI_CONCLUSION=success
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
S1_ACCEPTED=false
```

This is a historical snapshot from after PR #238 and before PR #241; it is
preserved as provenance and is not the current Source Cohort state.

## Post-PR241 current-main Source Cohort mirror

```text
POST_PR241_CURRENT_MAIN_REVALIDATION=PASS
PR241_MERGED=true
PR241_HEAD_SHA=b856d3823e51bb6e4f8b780363203a1c477677ca
PR241_MERGE_COMMIT_SHA=5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b
SOURCE_COHORT_INDEPENDENT_REVIEW_ID=4948013727
SOURCE_COHORT_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJuyynw
SOURCE_COHORT_REVIEWED_AT=2026-08-17T02:25:52Z
SOURCE_COHORT_EXACT_HEAD_CI_RUN_ID=31986614521
SOURCE_COHORT_EXACT_HEAD_CI_CONCLUSION=success
CURRENT_SOURCE_COHORT_ID=source-002-s1-cohort-v1
CURRENT_SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
CURRENT_SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
CURRENT_SOURCE_COHORT_FREEZE_STATUS=ACCEPTED
CURRENT_SOURCE_MANIFEST_STATUS=ACCEPTED
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The PR #241 closeout is gate-local: it accepts Source Cohort identity and
manifest evidence only. It does not accept Q2C, canonical grain,
inclusion/exclusion, visibility, revision, custody, split, holdout, or overall
S1 acceptance.
