# V0.3-S1 Source 002 Formalization Gap Matrix

## Matrix identity and interpretation

```text
MATRIX_ID=V0_3_S1_SOURCE_002_FORMALIZATION_GAP_MATRIX
MATRIX_STATUS=PACKAGE_A_FORMALIZATION_RECONCILED_FOR_REVIEW
BASELINE_MAIN_SHA=431a88fb4b542264fcf60d95a840202cc578f394
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
FORMALIZATION_GAP_COUNT=21
FROZEN_MATRIX_GAP_COUNT=21
EFFECTIVE_REMAINING_S1_GAP_COUNT=26
CANONICAL_S1_GATE_COUNT=17
PACKAGE_A_FORMALIZATION_APPLIED=true
FORMAL_ARTIFACTS_MISSING_AFTER_PACKAGE_A=4
```

`RESOLVED` below means resolved for Source 002 preparation only. It never
means that a formal source authority, cohort, Q2C decision, or S1 acceptance
has been issued. `PENDING` means a governance or formal evidence input is
still required. `BLOCKED` means the dependent formal artifact or acceptance
gate cannot be issued in the current state.

## Resolved for Source 002 preparation only

| item | status | evidence boundary |
| --- | --- | --- |
| immutable source object identity | RESOLVED | Source SHA-256 and byte count were machine-generated during the authorized read; no source file is committed here. |
| observed schema identity | RESOLVED | `observed-source-schema-v1` and the observed schema SHA-256 are recorded in the companion evidence file. |
| required source field presence | RESOLVED | All seven required headers were observed; no row-level values are retained. |
| canonical grain support | RESOLVED | Date, farm, subfarm, and variety support the frozen grain; plot remains unsupported. |
| aggregate coverage preparation | RESOLVED | Mapped season, counts, date bounds, and July boundary evidence are recorded as aggregates. |
| source quantity precision observation | RESOLVED | Source 002 accepted precision is 0.001 kg with no observed value above three decimals. |

## Remaining formalization gaps

| gap | status | current state | required next evidence or decision |
| --- | --- | --- | --- |
| `FORMAL_SOURCE_ATTESTATION` | BLOCKED | The authority evidence record remains `NOT_ISSUED`; this preparation file is not an attestation. | Source-owner attestation with all 16 authority identity fields, `ATTESTED` status, and an attestation hash. |
| `FORMAL_SOURCE_COHORT_MANIFEST` | BLOCKED | No cohort identity or manifest hash is issued. | A separately reviewed aggregate cohort manifest with scope, policy identities, object identities, and custody record. |
| `FORMAL_CORRECTION_POLICY` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | Current business statements do not define formal correction semantics; this is not a current Source 002 IDFL label-side blocker. | Versioned correction policy and source-system evidence if `AS_OF_EVALUATION`, `FINAL_ADJUDICATED`, or a used forecast-input class requires replayable correction visibility. |
| `FORMAL_VOID_POLICY` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | Current business statements do not define formal void semantics; this is not a current Source 002 IDFL label-side blocker. | Versioned void policy and propagation evidence if a replay mode or used forecast-input class requires it. |
| `FORMAL_REVISION_POLICY` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | Q2A/I7 winner semantics remain authoritative for replay modes; source-specific revision evidence is not a current IDFL label-side prerequisite. | Source-specific revision policy identity and lineage evidence if a replay mode or used forecast-input class requires it. |
| `REVISION_POLICY_VERSION` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | No source-specific version is issued; the absence does not block the current immutable IDFL label side. | Governance owner issues a stable revision-policy identity when the applicable mode or input class needs it. |
| `WITHDRAWAL_POLICY_VERSION` | FORMALIZED_UNACCEPTED | Package A custody record issues `source-002-withdrawal-policy-v1`; issuance is not custody acceptance. | Separate custody/source-authority acceptance decision. |
| `VOID_PROPAGATION_POLICY_VERSION` | FORMALIZED_UNACCEPTED | Package A custody record issues `source-002-void-propagation-policy-v1`; this is object-level propagation governance, not source-system record-void capability. | Separate custody/source-authority acceptance decision. |
| `FORMAL_MISSING_DAY_RULE` | PENDING | `UNKNOWN_NOT_ZERO` is the fail-closed semantic; source completeness and July handling remain unresolved. | Formal missing-day/completeness rule and reviewed evidence. |
| `POINT_IN_TIME_VISIBILITY_RULE` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | The repository contract requires source availability/recorded/revised/finalized visibility evidence for replay modes and applicable forecast inputs; Source 002 IDFL does not use record-level label replay. | Source-system visibility fields or an approved policy-null rule, with cutoff reconstruction evidence, when the applicable mode or input class requires it. |
| `LATE_ENTRY_RULE` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | Business context says the reported late-entry scenario is not applicable; this is not formal technical evidence, but it is not a current IDFL label-side blocker. | Formal late-entry policy or source-system evidence when replay or a used forecast-input class requires the applicable rule. |
| `FINAL_CONFIRMATION_FORMAL_EVIDENCE` | OPTIONAL_AUDIT_REPLAY_EVIDENCE_FOR_IDFL | Immediate scan completion is business-confirmed but not formally evidenced; independent finalization remains required for `FINAL_ADJUDICATED`, not current IDFL. | Source-owner confirmation bound to the attestation and source-system event semantics when that mode or input class requires it. |
| `UNMAPPED_DATE_POLICY` | PENDING | July 2025 contains 2 rows on 1 date and is deliberately not auto-assigned. | Business/governance decision for July ownership, exclusion, or exception handling. |
| `TARE_DEDUCTION_METHOD` | PENDING | Tare is business-confirmed as already deducted, but the method is not specified. | Formal tare method and measurement evidence. |
| `SCALE_PRECISION_FORMAL_EVIDENCE` | PENDING | Source 002 supports the exported quantity representation at 0.001 kg and three decimal places; this does not establish weighing-device precision or scale resolution. | Formal device precision/calibration evidence for the governed source. |
| `MAPPING_POLICY_IDENTITY` | PENDING | Dimension support is observed and Package A binds reviewed source-derived identity hashes, but `FORMAL_MAPPING_ACCEPTED=false`; no accepted source-specific semantic mapping identity is frozen. | Versioned mapping policy/registry identity and review/acceptance evidence. |
| `COVERAGE_SCOPE_ENTITY_ID_LISTS` | FORMALIZED_REFERENCE_ONLY | The reviewed package binds counts and array hashes without storing row-derived identity arrays in Git; `FORMAL_MAPPING_ACCEPTED=false` and the schema-valid source-cohort manifest remains unissued. | Separate source-cohort manifest preparation and independent acceptance. |
| `CUSTODY_RECORD` | FORMALIZED_UNACCEPTED | The versioned custody record binds the non-sensitive source identity hash, access roles, retention, withdrawal, replacement, and downstream propagation policy; `custody_record_accepted=false`. | Separate custody/source-authority acceptance decision. |
| `INCLUSION_POLICY_AND_KNOWN_EXCLUSIONS` | FORMALIZED_BOUNDARY_UNACCEPTED | The inclusion/exclusion boundary is issued; no-known-exclusions is not an all-rows-valid claim, and future S2 technical/data-quality exclusions remain allowed. | Separate source/cohort acceptance plus source completeness and July policy. |
| `Q2C_DECISION` | BLOCKED | Q2C draft facts are not formally accepted; IDFL lifecycle replay fields are not the blocker, but target binding remains unissued. | Independent Q2C decision record after the remaining target/source evidence required by the current contract closes. |
| `S1_INDEPENDENT_REVIEW` | BLOCKED | This package has not been independently reviewed as a complete S1 acceptance package. | Independent review of the complete S1 evidence package. |

## Package A formalization reconciliation

```text
PACKAGE_A_FORMALIZATION_APPLIED=true
LOCAL_DAY_BOUNDARY_FORMALIZED=true
KNOWN_EXCLUSIONS_FORMALIZED=true
COVERAGE_SCOPE_IDENTITY_PACKAGE_BOUND=true
VERSIONED_CUSTODY_RECORD_ISSUED=true
FORMAL_ARTIFACTS_MISSING_AFTER_PACKAGE_A=4
FORMAL_MAPPING_ACCEPTED=false
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_002_COMPLETENESS_AUTHORITY_ACCEPTED=false
CUSTODY_RECORD_ACCEPTED=false
INCLUSION_EXCLUSION_ACCEPTED=false
```

The three Package A artifacts formalize scoped evidence and policy boundaries
without issuing source authority, source cohort, completeness authority, Q2C,
or any canonical S1 gate.

## Explicit non-closure statements

```text
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

## Source quantity and device precision boundary

The Source 002 quantity result and the weighing-device precision are separate
contracts. The first is already available for preparation; the second remains
unprovided and formally pending.

```text
SOURCE_QUANTITY_PRECISION=0.001 kg
SOURCE_QUANTITY_PRECISION_STATUS=BUSINESS_CONFIRMED_AND_SOURCE_002_OBSERVED
SOURCE_QUANTITY_DECIMAL_PLACES=3
SOURCE_QUANTITY_INTEGER_ROUNDING=false
SOURCE_QUANTITY_ROUNDING_RULE=保留三位小数，不取整
SOURCE_QUANTITY_PRECISION_GAP=false

SCALE_DEVICE_PRECISION=NOT_PROVIDED
SCALE_DEVICE_PRECISION_BUSINESS_RULE_STATUS=NOT_CONFIRMED
SCALE_DEVICE_PRECISION_FORMAL_EVIDENCE_STATUS=PENDING
SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
```

The verification statement does not prove the device minimum division,
resolution, calibration precision, certificate identity, or certificate
validity. Source 002's three-decimal representation must not be used to infer
any of those properties.

Source 002 evidence does not create a second authority contract. The existing
source-authority, business-attestation, and source-cohort schemas remain the
canonical contracts. No formal source attestation or cohort JSON artifact is
generated because their required authority and acceptance conditions are not
all satisfied.

## Next gate impact

The package directly supports preparation for source identity, observed schema
identity, aggregate coverage, canonical-grain support, quantity precision,
and Package A governance references. It does not close source authority,
cohort freeze, custody acceptance, source-object-bound row lineage, mapping or
inclusion acceptance, split, metric, minimum-coverage, quality-threshold,
holdout, or independent-review gates.

## Optional audit/replay evidence scope

The lifecycle package is deliberately narrower than the full S1 visibility
gate and is applicable only when a replay mode or a forecast-input source class
actually uses these fields. It covers the actual-harvest label produced by the
scan-and-weigh source: source record identity, recorded/available time,
revision capability or an approved policy-null rule, finalization capability,
cancellation capability or policy-null rule, lineage, late-entry technical
semantics, and winner compatibility. It is not a current Source 002 IDFL
label-side hard blocker.

```text
ACTUAL_LABEL_LIFECYCLE_NEXT_PACKAGE_SCOPE_DEFINED=true
NEXT_PACKAGE=V0_3_S1_ACTUAL_HARVEST_LABEL_RECORD_LIFECYCLE_AND_POINT_IN_TIME_AUTHORITY_FREEZE
NEXT_PACKAGE_APPLICABILITY=AS_OF_EVALUATION_OR_FINAL_ADJUDICATED_OR_USED_FORECAST_INPUT_SOURCE_CLASS
CURRENT_SOURCE_002_IDFL_LIFECYCLE_AUDIT_BLOCKER=false
ACTUAL_LABEL_VISIBILITY_CLOSED=false
S1_VISIBILITY_GATE_CLOSED=false
S1_VISIBILITY_FULL_CLOSURE_NOT_CLAIMED=true
```

The full `S1-VISIBILITY` gate covers forecast-input source classes actually
used by the evaluated forecast. Closing or reclassifying actual-label
lifecycle evidence alone cannot close the full S1 visibility gate.

## Forecast relevance and current IDFL blocker reconciliation

The current Source 002 actual label is `IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1`
and is used as a historical final actual for forecast evaluation. Its
record-level lifecycle fields are therefore not current IDFL label-side hard
blockers. The forecast-input point-in-time rule remains mandatory for source
classes actually used as forecast inputs and is not relaxed by the IDFL label
mode.

```text
SOURCE_002_ACTUAL_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
ACTUAL_LABEL_PURPOSE=HISTORICAL_FINAL_ACTUAL_FOR_FORECAST_EVALUATION
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
SOURCE_RECORD_ID_REQUIRED_FOR_CURRENT_IDFL_LABEL=false
SOURCE_RECORDED_AT_REQUIRED_FOR_CURRENT_IDFL_LABEL=false
SOURCE_FINALIZED_AT_REQUIRED_FOR_CURRENT_IDFL_LABEL=false
REVISION_WINNER_REQUIRED_FOR_CURRENT_IDFL_LABEL=false
SOURCE_002_RECORD_LEVEL_LIFECYCLE_AUDIT_BLOCKER=false
FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY

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

V0_3_S1_NON_BLOCKING_AUDIT_ITEMS=
SOURCE_RECORD_ID,
SOURCE_RECORDED_AT_FOR_LABEL_SIDE,
SOURCE_AVAILABLE_AT_FOR_LABEL_SIDE,
SOURCE_REVISED_AT,
SOURCE_FINALIZED_AT,
SOURCE_CANCELLED_AT,
REVISION_NUMBER,
SUPERSEDED_PARENT,
FULL_RECORD_REVISION_LINEAGE

SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
SOURCE_COMPLETENESS_POLICY_VERSION=NOT_ISSUED
SOURCE_COMPLETENESS_EVIDENCE_HASH=NOT_ISSUED
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
DESCRIPTIVE_CALENDAR_GAP_COUNT_IS_FORMAL_MISSING_DAY_COUNT=false
UNMAPPED_DATE=2025-07-22
UNMAPPED_ROW_COUNT=2
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
CURRENT_SOURCE_002_IDFL_V1_ELIGIBILITY=false
CURRENT_SOURCE_002_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
```

The seven direct forecast-readiness items are a prioritization list, not a
replacement for the complete source-specific IDFL eligibility gates. The
observed maximum harvest date is not a completeness watermark. The historical
lifecycle workpaper and source-system request remain available as optional
audit/replay evidence and are required when a replay mode or a used
forecast-input source class needs those semantics; they are not current Source
002 IDFL label-side acceptance prerequisites.
