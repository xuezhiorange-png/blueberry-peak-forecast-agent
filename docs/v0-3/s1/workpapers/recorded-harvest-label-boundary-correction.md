# V0.3-S1 Recorded Harvest Label Boundary Correction

## Workpaper identity and scope

```text
WORKPAPER_ID=V0_3_S1_RECORDED_HARVEST_LABEL_BOUNDARY_CORRECTION
BASE_MAIN_SHA=b7e59e24750f6eebf73819d0b62baf2cb50a7597
WORKPAPER_STATUS=PREPARED_FOR_INDEPENDENT_REVIEW
CORRECTION_REASON=V0_3_Q2C_PREVIOUSLY_CONFLATED_RECORDED_BUSINESS_LABEL_WITH_PRE_WEIGH_THEORETICAL_FARM_PICK_WEIGHT
BUSINESS_DECISION_ID=V0_3_RECORDED_HARVEST_LABEL_BOUNDARY
RECORDED_LABEL_BUSINESS_BOUNDARY_EXPLICIT=true
```

This correction applies only to the V0.3 actual-harvest recorded-business-label
profile. It does not rewrite the historical accepted design in
`docs/forecast-quality/q2c-physical-target-equivalence-contract.md`, select a
forecast-side target, issue a Q2C decision, or accept a canonical S1 gate.

## Confirmed V0.3 business boundary

```text
ACTUAL_HARVEST_LABEL_SOURCE=扫码称重系统
ACTUAL_HARVEST_LABEL_DATASET=田间商品果每日采摘净重汇总
ACTUAL_HARVEST_LABEL_MEASUREMENT_EVENT=田间采收点首次有效扫码称重
ACTUAL_HARVEST_LABEL_QUANTITY=扫码称重系统正式记录的商品果净重
ACTUAL_HARVEST_LABEL_UNIT=KG
RECORDED_NET_WEIGHT_IS_BUSINESS_TRUTH=true
V0_3_ACTUAL_LABEL_MODE=RECORDED_BUSINESS_LABEL
V0_3_ACTUAL_LABEL_BUSINESS_EVENT=HARVEST
V0_3_ACTUAL_LABEL_MEASUREMENT_BOUNDARY=RECORDED_VALID_FIELD_SCAN_WEIGH
V0_3_ACTUAL_LABEL_QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
V0_3_ACTUAL_LABEL_SOURCE_OF_TRUTH=GOVERNED_SCAN_WEIGHT_RECORD
```

The actual label is the governed scan-weight record's marketable fruit net
weight. It is not a reconstructed estimate of the theoretical weight at the
instant fruit was removed from the plant. Transport, storage, natural loss and
other pre-weigh history are inside the upstream history of the recorded label
and are not used to calculate a different label value.

```text
PRE_WEIGH_TRANSPORT_LOSS_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_STORAGE_LOSS_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_POSTHARVEST_LOSS_RECONSTRUCTION_REQUIRED=false
PRE_WEIGH_TRANSPORT_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_STORAGE_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_WEIGH_POSTHARVEST_LOSS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
TARE_METHOD_RECONSTRUCTION_REQUIRED=false
TARE_METHOD_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_DEVICE_PRECISION_REQUIRED_FOR_LABEL_ELIGIBILITY=false
SCALE_CALIBRATION_AUTHORITY_REQUIRED_FOR_LABEL_ELIGIBILITY=false
PRE_MEASUREMENT_WEIGHT_RECONSTRUCTION_REQUIRED=false
V0_3_RECORDED_LABEL_PROFILE_OVERRIDES_STRICT_PRE_WEIGH_RECONSTRUCTION=true
```

These flags mean `NOT_REQUIRED_FOR_V0_3_RECORDED_LABEL_ELIGIBILITY`. They do not
mean `FALSE`, `ZERO`, or that an unknown process, tare method, or device
property does not exist. The following business statements remain unchanged:

```text
FACTORY_SORTING_RETROACTIVE_ADJUSTMENT=false
FACTORY_REJECTION_RETROACTIVE_ADJUSTMENT=false
FACTORY_RETURN_RETROACTIVE_ADJUSTMENT=false
```

## Forecast and acceptance boundary

```text
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
Q2C_ACCEPTED=false
CURRENT_Q2C_OUTCOME=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
CANONICAL_GATE_STATUS_CHANGED=false
GATE_PASS_COUNT=0
```

This correction does not establish that `effective_marketable_quantity_kg`,
`model_harvested_marketable_quantity_kg`, or any other forecast output is
exactly equivalent to the recorded actual label. Forecast-side target binding
requires a separate reviewed Q2C decision. It also does not change the
canonical acceptance record or authorize source authority, source cohort, S1,
S2, data import, or backtesting.

## Six-dimensional recorded-label interpretation

For the V0.3 recorded-label profile, the required boundary evidence is:

1. the record is a governed scan-weight record;
2. the quantity is the formally recorded marketable fruit net weight;
3. the unit is kilograms;
4. marketability, field sorting, packhouse sorting and rejection boundaries
   match the record definition;
5. harvest business date and canonical grain are determinable; and
6. source identity, coverage, visibility and governance can be frozen.

The absence of a pre-weigh transport, storage, post-harvest or tare method
description does not, by itself, block this recorded-label profile. Device
precision and calibration authority remain optional metrology evidence. The
historical `FARM_PICK`/`OBSERVED_WEIGHT` vocabulary remains in the historical
contract for compatibility; this V0.3 profile scopes the label boundary to the
governed valid scan-weigh record without rewriting that historical document.

## Attestation schema correction

```text
SCHEMA_FILE=docs/v0-3/s1/schemas/business-source-attestation.schema.json
SCHEMA_REQUIRED_FIELDS_REMOVED_COUNT=6
SCHEMA_OPTIONAL_PROPERTIES_RETAINED_COUNT=6
OPTIONAL_NONBLOCKING_FIELDS=transport_before_weighing,storage_before_weighing,postharvest_loss_rule,tare_policy,scale_precision,scale_calibration_authority
```

The six properties remain available for future process-provenance or
metrology evidence and retain string validation. They are no longer in the
top-level `required` list for V0.3 recorded-label eligibility. This is a
schema-contract correction, not a claim that any missing property has a
specific value.

## D-class reconciliation

```text
PREVIOUS_D_CLASS_COUNT=9
CORRECTED_D_CLASS_COUNT=3
REMOVED_HARD_BLOCKER_COUNT=6
REMAINING_D_CLASS_INPUT_IDS=LOCAL_DAY_BOUNDARY,KNOWN_EXCLUSIONS,COVERAGE_SCOPE_ENTITY_IDENTITIES
```

The six reclassified fields are optional/non-blocking for this label profile;
they are not marked resolved and no values are invented. The remaining three
factual absences continue to block the relevant formal preparation steps.

| INPUT_ID | PREVIOUS_CLASSIFICATION | CORRECTED_CLASSIFICATION | HARD_BLOCKER_AFTER_CORRECTION | RATIONALE |
| --- | --- | --- | --- | --- |
| TARE_DEDUCTION_METHOD | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Recorded net weight is the label truth; tare reconstruction is not required. |
| SCALE_DEVICE_PRECISION | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Export decimal representation is distinct from device metrology. |
| SCALE_CALIBRATION_AUTHORITY | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Calibration authority remains optional metrology evidence. |
| TRANSPORT_BEFORE_WEIGHING | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Pre-weigh transport history is not reconstructed for label eligibility. |
| STORAGE_BEFORE_WEIGHING | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Pre-weigh storage history is not reconstructed for label eligibility. |
| POSTHARVEST_LOSS_RULE | D | OPTIONAL_NONBLOCKING_EVIDENCE | false | Pre-record process history is not used to derive another label value. |
| LOCAL_DAY_BOUNDARY | D | TRULY_MISSING_FACTUAL_INPUT | true | Timezone alone does not supply the explicit local-day boundary required for date binding. |
| KNOWN_EXCLUSIONS | D | TRULY_MISSING_FACTUAL_INPUT | true | No bounded exclusion list is currently available. |
| COVERAGE_SCOPE_ENTITY_IDENTITIES | D | TRULY_MISSING_FACTUAL_INPUT | true | Aggregate counts do not provide governed entity identity arrays. |

## Recomputed Package A decision candidates

All canonical gate statuses remain `BLOCKED`. The following are decision
candidates only; `READY_FOR_FORMAL_ARTIFACT_PREPARATION` does not mean `PASS` or
acceptance.

### S1-Q2C-TARGET

```text
GATE_ID=S1-Q2C-TARGET
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=LOCAL_DAY_BOUNDARY;KNOWN_EXCLUSIONS;COVERAGE_SCOPE_ENTITY_IDENTITIES
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=remaining date, exclusion and governed scope facts must be resolved or authorized before formal Q2C artifact preparation; pre-weigh reconstruction fields are no longer hard label blockers
RECOMMENDED_NEXT_ACTION=TRIAGE_AND_RESOLVE_REMAINING_Q2C_D_CLASS_INPUTS_BEFORE_FORMAL_ARTIFACT_PREPARATION
```

### S1-SOURCE-AUTHORITY

```text
GATE_ID=S1-SOURCE-AUTHORITY
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=LOCAL_DAY_BOUNDARY;KNOWN_EXCLUSIONS;COVERAGE_SCOPE_ENTITY_IDENTITIES
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=source attestation still lacks required date, exclusion and governed scope facts; optional pre-weigh/metrology properties do not block the V0.3 recorded-label profile
RECOMMENDED_NEXT_ACTION=TRIAGE_REMAINING_SOURCE_ATTESTATION_D_CLASS_INPUTS_BEFORE_FORMAL_ATTESTATION_PREPARATION
```

### S1-SOURCE-COHORT

```text
GATE_ID=S1-SOURCE-COHORT
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=KNOWN_EXCLUSIONS;COVERAGE_SCOPE_ENTITY_IDENTITIES
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=known exclusions remain absent and governed scope identity preparation is separately authorized work
RECOMMENDED_NEXT_ACTION=TRIAGE_KNOWN_EXCLUSIONS_AND_AUTHORIZE_SCOPE_IDENTITY_PREPARATION_BEFORE_COHORT_MANIFEST
```

### S1-PHYSICAL-MEANING

```text
GATE_ID=S1-PHYSICAL-MEANING
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
TRULY_MISSING_BUSINESS_INPUTS=NONE
REQUIRES_NEW_EXTERNAL_INPUT=false
EXTERNAL_INPUT_DESCRIPTION=recorded label business facts are available at the required boundary; formal physical attestation and independent review remain missing
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_RECORDED_LABEL_PHYSICAL_ATTESTATION_FOR_INDEPENDENT_REVIEW
```

### S1-UNIT-AND-TIME-BASIS

```text
GATE_ID=S1-UNIT-AND-TIME-BASIS
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=LOCAL_DAY_BOUNDARY
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=explicit local-day boundary remains absent; recorded quantity unit and exported decimal representation are already available
RECOMMENDED_NEXT_ACTION=RESOLVE_LOCAL_DAY_BOUNDARY_BEFORE_FORMAL_UNIT_TIME_ARTIFACT_PREPARATION
```

### S1-CANONICAL-GRAIN

```text
GATE_ID=S1-CANONICAL-GRAIN
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=COVERAGE_SCOPE_ENTITY_IDENTITIES
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=governed scope entity identities are absent; preparation requires separate source-derived authorization
RECOMMENDED_NEXT_ACTION=AUTHORIZE_GOVERNED_SCOPE_IDENTITY_PREPARATION_BEFORE_MAPPING_SCOPE_FORMALIZATION
```

### S1-INCLUSION-EXCLUSION

```text
GATE_ID=S1-INCLUSION-EXCLUSION
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT
TRULY_MISSING_BUSINESS_INPUTS=KNOWN_EXCLUSIONS;COVERAGE_SCOPE_ENTITY_IDENTITIES
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=known exclusions and governed scope identities remain absent; answered historical business questions are not re-asked
RECOMMENDED_NEXT_ACTION=RESOLVE_SCOPE_AND_EXCLUSION_INPUTS_BEFORE_INCLUSION_MANIFEST_PREPARATION
```

### S1-DATA-CUSTODY

```text
GATE_ID=S1-DATA-CUSTODY
CANONICAL_CURRENT_STATUS=BLOCKED
DECISION_CANDIDATE_STATUS=BLOCKED_BY_NOT_FORMALIZED_GOVERNANCE
TRULY_MISSING_BUSINESS_INPUTS=NONE
REQUIRES_NEW_EXTERNAL_INPUT=true
EXTERNAL_INPUT_DESCRIPTION=the current custody facts are available but access role, retention and withdrawal governance remain not formalized
RECOMMENDED_NEXT_ACTION=REVIEW_CURRENT_CUSTODY_REALITY_AND_GOVERNANCE_GAPS_BEFORE_FORMAL_CUSTODY_RECORD_PREPARATION
```

```text
DECISION_CANDIDATE_READY_COUNT=1
DECISION_CANDIDATE_BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT_COUNT=6
DECISION_CANDIDATE_BLOCKED_BY_NOT_FORMALIZED_GOVERNANCE_COUNT=1
```

## Explicit non-acceptance and data boundary

```text
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
SOURCE_002_RE_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
DATABASE_WRITE=false
CANONICAL_GATE_STATUS_CHANGED=false
GATE_PASS_COUNT=0
NO_NEW_BUSINESS_FACT_INVENTED=true
NO_NEW_GOVERNANCE_POLICY_INVENTED=true
```

Existing aggregate evidence is referenced only as repository evidence. This
correction does not read Source 002, generate entity identity arrays, issue an
attestation, issue a cohort, decide local-day/exclusion/scope policy, or start
any downstream package.
