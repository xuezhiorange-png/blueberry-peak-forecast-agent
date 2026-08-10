# V0.3-S1 Package A Foundational Gate Evidence Decision Reconciliation

## 1. Scope and authority

```text
WORKPAPER_ID=V0_3_S1_PKG_A_FOUNDATIONAL_EVIDENCE_DECISION_RECONCILIATION
PACKAGE_ID=S1-PKG-A
PHASE=1
WORKPAPER_STATUS=PREPARED_FOR_GOVERNANCE_DECISION_REVIEW
BASE_SHA=4101e161e9b92f415e0e5274388b703e69ff8d80
RECONCILED_GATE_COUNT=8
CANONICAL_GATE_STATUS_CHANGED=false
GATE_PASS_COUNT=0
CORRECTION_R1_APPLIED=true
CORRECTION_R1_REVIEWED_PREVIOUS_HEAD=60d3d902799aea647bd88e81ac8f60ed7ba80270
CORRECTION_R1_P1_COUNT=2
CORRECTION_R1_P2_COUNT=1
RECORDED_HARVEST_LABEL_BOUNDARY_CORRECTION_APPLIED=true
BUSINESS_DECISION_ID=V0_3_RECORDED_HARVEST_LABEL_BOUNDARY
FORECAST_SIDE_TARGET_BINDING_CHANGED=false
```

This workpaper reconciles only the eight Package A gates:

```text
S1-Q2C-TARGET
S1-SOURCE-AUTHORITY
S1-SOURCE-COHORT
S1-PHYSICAL-MEANING
S1-UNIT-AND-TIME-BASIS
S1-CANONICAL-GRAIN
S1-INCLUSION-EXCLUSION
S1-DATA-CUSTODY
```

The authority chain is the current main branch: the V0.3 development plan,
the S1 acceptance package and acceptance schema, the Q2C, source authority,
visibility, split/custody and metric contracts, and the current
`s1-acceptance-record.json`. The canonical acceptance record remains
authoritative for gate status. All seventeen canonical rows remain
`BLOCKED`; this document cannot issue a gate acceptance.

## 2. Four-layer interpretation

```text
L1_BUSINESS_FACT=reported or reused factual meaning
L2_GOVERNANCE_FORMALIZATION=role, policy, scope or decision formalization
L3_FORMAL_ARTIFACT=attestation, manifest, custody record or decision hash
L4_GATE_ACCEPTANCE=canonical S1 acceptance status and independent review
```

An L1 fact is not an L2 policy, an L3 artifact, or an L4 gate acceptance.
`NOT_FORMALIZED`, `NO_FORMAL_RULE`, and `NO_EXPLICIT_ROLE_RESTRICTION` are
received current-state facts with governance gaps; they are not missing
answers.

## 3. Existing evidence consumed

```text
CONTRACTS_CONSUMED=
docs/v0-3/development-plan.md,
docs/v0-3/s1/index.md,
docs/v0-3/s1/s1-acceptance-package.md,
docs/v0-3/s1/target-decision-and-quantity-contract.md,
docs/v0-3/s1/source-authority-and-cohort-manifest.md,
docs/v0-3/s1/visibility-inclusion-revision-contract.md,
docs/v0-3/s1/split-holdout-and-custody-contract.md,
docs/v0-3/s1/metric-coverage-and-quality-contract.md

WORKPAPERS_CONSUMED=
docs/v0-3/s1/workpapers/q2c-target-decision-draft.md,
docs/v0-3/s1/workpapers/business-source-attestation-draft.md,
docs/v0-3/s1/workpapers/source-measurement-and-finalization-rules-draft.md,
docs/v0-3/s1/workpapers/season-calendar-rule-draft.md,
docs/v0-3/s1/workpapers/source-schema-field-map-and-gap-register.md,
docs/v0-3/s1/workpapers/source-002-idfl-v1-source-specific-eligibility-package.md,
docs/v0-3/s1/workpapers/source-002-completeness-authority-and-custody-preparation.md

EVIDENCE_CONSUMED=
docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md,
docs/v0-3/s1/evidence/source-002-formalization-gap-matrix.md,
docs/v0-3/s1/evidence/source-002-completeness-and-custody-business-evidence.md,
docs/v0-3/s1/evidence/q2c-physical-alignment-evidence-status.md,
docs/v0-3/s1/evidence/source-authority-evidence-status.md,
docs/v0-3/s1/evidence/source-cohort-evidence-status.md,
docs/v0-3/s1/evidence/data-custody-evidence-status.md,
docs/v0-3/s1/evidence/business-acceptance-evidence-package.md,
docs/v0-3/s1/evidence/evidence-package-manifest.json
```

No Source 002 export, row, record ID, timestamp, storage locator or external
system was read in this task. Existing governed source-object metadata is
reused only as repository evidence.

## 4. Known business facts already available

The following factual groups are present in current evidence. The count is a
deduplicated semantic-field count, not a line count or an acceptance count.

```text
SOURCE_IDENTITY_AND_OBJECT_FACTS=10
Q2C_PHYSICAL_FACTS=11
SOURCE_COVERAGE_AND_GRAIN_FACTS=20
MEASUREMENT_AND_TIME_FACTS=5
COMPLETENESS_ANSWER_FACTS=4
CUSTODY_ANSWER_FACTS=6
MISSINGNESS_AND_CALENDAR_FACTS=3
BUSINESS_FACTS_RECOVERED_FROM_EXISTING_EVIDENCE_COUNT=59
```

Known facts include the Source 002 system/dataset/owner/version/snapshot/hash,
the field-side marketable-fruit weighing meaning, kg and farm-local calendar,
canonical grain support, aggregate coverage metadata, Q1–Q4, and C1–C6.

## 5. Facts present but not formalized

```text
FACTS_PRESENT_BUT_NOT_FORMALIZED_COUNT=18
FACTS_PRESENT_BUT_NOT_FORMALIZED=
Q2_FORMAL_POLICY_STATUS,
COMPLETENESS_DECLARATION_OWNER_ROLE,
COMPLETENESS_EXCEPTION_HANDLING_POLICY,
C2_ROLE_FORMALIZATION_STATUS,
ACCESS_OWNER_ROLE,
AUTHORIZED_ROLE_SET,
RETENTION_POLICY,
WITHDRAWAL_REPLACEMENT_POLICY,
REVISION_POLICY,
WITHDRAWAL_AND_VOID_POLICY,
LATE_ENTRY_RULE,
MISSING_DAY_RULE,
CORRECTION_RULE,
VOID_RULE,
VISIBILITY_BOUNDARY_POLICY,
MAPPING_POLICY_IDENTITY,
INCLUSION_POLICY,
UNMAPPED_DATE_POLICY
```

The `NOT_FORMALIZED`, `NO_FORMAL_RULE`, and `NO_EXPLICIT_ROLE_RESTRICTION`
answers are retained as current reality. This reconciliation does not create
retention, role, completeness, withdrawal, mapping, exclusion, or missing-day
policies. `TARE_DEDUCTION_METHOD`, `SCALE_DEVICE_PRECISION`, and
`SCALE_CALIBRATION_AUTHORITY`, together with
`TRANSPORT_BEFORE_WEIGHING`, `STORAGE_BEFORE_WEIGHING`, and
`POSTHARVEST_LOSS_RULE`, are not in this governance-gap or D-class hard-blocker category after
the recorded-label correction: they remain optional evidence fields with no
invented values.

## 6. Formal artifacts still missing

```text
FORMAL_ARTIFACTS_MISSING_COUNT=4
FORMAL_ARTIFACTS_MISSING=
Q2C_DECISION_RECORD_AND_HASH,
BUSINESS_SOURCE_ATTESTATION_AND_HASH,
SOURCE_COHORT_MANIFEST_AND_HASH,
SOURCE_COMPLETENESS_AUTHORITY_RECORD_AND_HASH
FORMAL_ARTIFACTS_FORMALIZED_THIS_PACKAGE=
MAPPING_AND_SCOPE_IDENTITY_MANIFEST,
INCLUSION_EXCLUSION_MANIFEST,
VERSIONED_CUSTODY_RECORD_AND_HASH
```

These are artifact gaps, not grounds to relabel already supplied business
facts as missing. Canonical acceptance remains separate.

## 7. Attestation required-field audit

The corrected business-source-attestation schema has 36 required fields. Six
process-provenance/metrology properties remain available but are optional for
the V0.3 recorded-business-label profile. The following audit distinguishes an
available business fact (`A`), a supplied fact whose governance or technical
rule is not formalized (`B`), a missing formal artifact value (`C`), and a
factual value not present in current repository evidence (`D`). A
schema-required field is not automatically an immediate user question.

```text
ATTESTATION_SCHEMA_REQUIRED_FIELD_COUNT=36
ATTESTATION_SCHEMA_FIELD_CLASS_A_COUNT=21
ATTESTATION_SCHEMA_FIELD_CLASS_B_COUNT=7
ATTESTATION_SCHEMA_FIELD_CLASS_C_COUNT=5
ATTESTATION_SCHEMA_FIELD_CLASS_D_COUNT=0
OPTIONAL_RECORDED_LABEL_EVIDENCE_FIELD_COUNT=6
OPTIONAL_RECORDED_LABEL_EVIDENCE_FIELDS=transport_before_weighing,storage_before_weighing,postharvest_loss_rule,tare_policy,scale_precision,scale_calibration_authority
OPTIONAL_RECORDED_LABEL_EVIDENCE_HARD_BLOCKER=false
```

| FIELD | CURRENT_EVIDENCE_VALUE | CLASSIFICATION | SOURCE_ARTIFACT | RATIONALE |
| --- | --- | --- | --- | --- |
| attestation_version | NOT_PROVIDED | C | business-source-attestation-draft.md | Version belongs to the missing formal attestation. |
| source_system | 扫码称重系统 | A | source-002-governed-snapshot-evidence.md | Existing source identity fact. |
| source_dataset | 田间商品果每日采摘净重汇总 | A | source-002-governed-snapshot-evidence.md | Existing dataset identity fact. |
| source_version | scan-weight-export:v0_3_s1:002 | A | source-002-governed-snapshot-evidence.md | Existing governed snapshot identity. |
| schema_version | observed-source-schema-v1 | A | source-002-governed-snapshot-evidence.md | Existing observed schema identity. |
| schema_hash | 919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867 | A | source-002-governed-snapshot-evidence.md | Existing schema hash; not attestation hash. |
| source_snapshot_reference | snapshot:v0_3_s1:002 | A | source-002-governed-snapshot-evidence.md | Existing opaque snapshot reference. |
| source_owner_role | 农场数据负责人 | A | source-002-completeness-and-custody-business-evidence.md | Existing role fact; not all authority roles. |
| attestation_effective_at | NOT_PROVIDED | C | source-authority-evidence-status.md | Formal attestation metadata is not issued. |
| effective_time | NOT_PROVIDED | C | source-authority-evidence-status.md | Formal applicability object is not issued. |
| attestation_status | NOT_ISSUED | C | source-authority-evidence-status.md | No formal attestation status exists. |
| attestation_hash | NOT_ISSUED | C | source-authority-evidence-status.md | No canonical attestation payload/hash exists. |
| coverage_scope | GOVERNED_PACKAGE_REFERENCE_ONLY | A_GOVERNED_EXTERNAL_IDENTITY_PACKAGE_REFERENCE | source-002-mapping-and-scope-identity-manifest.json | Reviewed counts and array hashes are bound to a governed external preparation package; full arrays remain outside Git. |
| revision_policy | IDFL source-system revision lineage not required; object replacement policy not formalized | B | IDFL contract; source-002-completeness-and-custody-business-evidence.md | Mode semantics exist, source-object governance is not formalized. |
| withdrawal_and_void_policy | NOT_FORMALIZED | B | source-002-completeness-and-custody-business-evidence.md | C6 states no formal withdrawal/replacement rule. |
| known_exclusions | NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE | A | source-002-inclusion-exclusion-manifest.json | The confirmed boundary is formalized without claiming all rows are valid or excluding future S2 cleaning. |
| physical_event | 田间采收点首次有效扫码称重 | A | source-measurement-and-finalization-rules-draft.md | Business physical event is recorded. |
| weighing_point_and_relation_to_pick | 田间采摘点; first valid scan/weigh | A | q2c-target-decision-draft.md | Business weighing point and relation are recorded. |
| quantity_basis | 商品果净重 | A | q2c-target-decision-draft.md | Business quantity basis is recorded. |
| quantity_unit | kg | A | q2c-target-decision-draft.md | Business unit is recorded. |
| all_picked_or_marketable | MARKETABLE_ONLY / 仅统计商品果 | A | q2c-physical-alignment-evidence-status.md | Marketability boundary is recorded. |
| field_sorting_rule | 田间剔除的非商品果不计入 | A | q2c-target-decision-draft.md | Field sorting fact is recorded. |
| packhouse_sorting_rule | 加工厂后续分选不追溯调整 | A | q2c-target-decision-draft.md | Packhouse boundary fact is recorded. |
| rejected_fruit_rule | 加工厂拒收或退货不追溯调整 | A | q2c-target-decision-draft.md | Rejection boundary fact is recorded. |
| measurement_method | 田间采收点首次有效扫码称重 | A | source-schema-field-map-and-gap-register.md | Business-level method description exists; formal method code remains artifact work. |
| farm_timezone | Asia/Shanghai | A | q2c-target-decision-draft.md | Farm-local timezone fact is recorded. |
| local_day_boundary | LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI | A | source-002-inclusion-exclusion-manifest.json | The confirmed local-day rule is now recorded in the Package A inclusion boundary. |
| late_entry_rule | NOT_APPLICABLE scenario; technical rule not formalized | B | source-schema-field-map-and-gap-register.md | Current business scenario exists; formal/technical rule does not. |
| missing_day_rule | UNKNOWN_NOT_ZERO; formal rule pending | B | q2c-target-decision-draft.md | Fail-closed semantics exist; formal rule is pending. |
| correction_rule | NO_FORMAL_RULE / business no-correction statement | B | source-measurement-and-finalization-rules-draft.md | Current business statement does not create a formal policy. |
| void_rule | NO_FORMAL_RULE / business no-void statement | B | source-measurement-and-finalization-rules-draft.md | Current business statement does not create a formal policy. |
| final_confirmation_rule | 扫码称重完成; immediate | A | q2c-target-decision-draft.md | Business event/timing fact exists; formal artifact remains missing. |
| visibility_boundary | IDFL_V1 label-side not point-in-time replayable | B | IDFL governing contracts | Mode boundary exists; source-specific formal visibility artifact is not issued. |
| grain | SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE | A | source-002-governed-snapshot-evidence.md | Canonical grain support is recorded. |
| plot_supported | false | A | source-002-governed-snapshot-evidence.md | Source capability fact is recorded. |
| coverage_summary | aggregate counts and date bounds; preparation only | A | source-002-governed-snapshot-evidence.md | Aggregate summary exists, not a cohort acceptance. |
```

The following six fields remain available as optional process-provenance or
metrology evidence. Their absence is no longer a D-class hard blocker for the
V0.3 recorded-label profile, and no value is invented:

```text
transport_before_weighing=NOT_PROVIDED; OPTIONAL_NONBLOCKING_EVIDENCE
storage_before_weighing=NOT_PROVIDED; OPTIONAL_NONBLOCKING_EVIDENCE
postharvest_loss_rule=NOT_PROVIDED; OPTIONAL_NONBLOCKING_EVIDENCE
tare_policy=TARE_ALREADY_DEDUCTED=true; method NOT_PROVIDED; OPTIONAL_NONBLOCKING_EVIDENCE
scale_precision=NOT_PROVIDED; OPTIONAL_NONBLOCKING_EVIDENCE
scale_calibration_authority=NOT_COLLECTED_OUTSIDE_CURRENT_PREDICTION_SCOPE; OPTIONAL_NONBLOCKING_EVIDENCE
```

The former three D-class fields are now reconciled into Package A evidence:

```text
LOCAL_DAY_BOUNDARY_CLASSIFICATION=A
KNOWN_EXCLUSIONS_CLASSIFICATION=A
COVERAGE_SCOPE_ENTITY_IDENTITIES_CLASSIFICATION=A_GOVERNED_EXTERNAL_IDENTITY_PACKAGE_REFERENCE
MEASUREMENT_METHOD_EVIDENCE_STATUS=FACT_AVAILABLE_BUSINESS_LEVEL_NOT_FORMALIZED
```

The existing source measurement facts remain unchanged. In particular,
`SOURCE_QUANTITY_PRECISION=0.001 kg` describes exported quantity
representation, not device precision. The six optional fields are not
counted as missing hard-blocker inputs after this contract correction.

## 8. Truly missing external business inputs

```text
TRULY_MISSING_BUSINESS_INPUT_COUNT=0
TRULY_MISSING_BUSINESS_INPUT_IDS=NONE
IMMEDIATE_USER_QUESTION_REQUIRED_COUNT=0
IMMEDIATE_USER_QUESTION_IDS=NONE
NO_FURTHER_BUSINESS_QUESTION_REQUIRED_FOR_PHASE_1=true
```

Q1=`NOT_CONFIRMED`, Q3=`NOT_FORMALIZED`, Q4=`NO_FORMAL_RULE`, and
C5/C6=`NOT_FORMALIZED` remain current-state answers and are not re-asked. The
three former D-class inputs are now represented by the reviewed Package A
artifacts: the local-day boundary and exclusion boundary are explicit, while
scope identity is bound by counts and array hashes without committing full
entity arrays. The six optional process-provenance and metrology fields remain
non-blocking and are not counted as D-class hard blockers for the V0.3
recorded-label profile. July handling, source completeness, Q2C, source
attestation, source cohort, and gate acceptance remain separate decisions.

`NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=true` in a gate block means that the
listed factual value must be supplied before that gate can be prepared for
formal review. It does not authorize an immediate user question in this R1;
the current `IMMEDIATE_USER_QUESTION_REQUIRED_COUNT=0` is intentionally
separate.

### D-class input audit

| INPUT_ID | CURRENT_VALUE | GATES_AFFECTED | SOURCE_ARTIFACT | WHY_CLASSIFIED_TRULY_MISSING | IMMEDIATE_USER_QUESTION_REQUIRED |
| --- | --- | --- | --- | --- | --- |
| LOCAL_DAY_BOUNDARY | LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI | S1-Q2C-TARGET; S1-SOURCE-AUTHORITY; S1-UNIT-AND-TIME-BASIS | source-002-inclusion-exclusion-manifest.json | Confirmed local-day authority is recorded; formal gate acceptance remains separate. | false |
| KNOWN_EXCLUSIONS | NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE | S1-Q2C-TARGET; S1-SOURCE-AUTHORITY; S1-SOURCE-COHORT; S1-INCLUSION-EXCLUSION | source-002-inclusion-exclusion-manifest.json | Confirmed boundary is recorded without claiming all rows are valid or ruling out future S2 cleaning exclusions. | false |
| COVERAGE_SCOPE_ENTITY_IDENTITIES | A_GOVERNED_EXTERNAL_IDENTITY_PACKAGE_REFERENCE | S1-Q2C-TARGET; S1-SOURCE-AUTHORITY; S1-SOURCE-COHORT; S1-CANONICAL-GRAIN; S1-INCLUSION-EXCLUSION | source-002-mapping-and-scope-identity-manifest.json | Reviewed counts and array hashes bind the external preparation package; full arrays are deliberately not stored in Git. | false |

## 9. Eight-gate field-level reconciliation

### S1-Q2C-TARGET

```text
GATE_ID=S1-Q2C-TARGET
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=11
FORMALIZED_GOVERNANCE_FACT_COUNT=3
FORMAL_ARTIFACT_PRESENT_COUNT=2
FACTS_ALREADY_AVAILABLE=physical event; quantity basis; kg; weighing point; marketability and sorting boundaries; farm timezone; tare result
FACTS_PRESENT_BUT_NOT_FORMALIZED=physical attestation; target decision; transformation authority; formal policy bindings
FORMAL_ARTIFACTS_MISSING=Q2C decision; attestation; decision hash
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_GOVERNANCE_DECISION
AUTHORITATIVE_REQUIREMENT=accepted Q2C target and quantity contract with source/physical meaning binding
CURRENT_SUPPORTING_ARTIFACTS=target-decision-and-quantity-contract.md; q2c-target-decision-draft.md; q2c-physical-alignment-evidence-status.md; source-002-inclusion-exclusion-manifest.json; source-002-mapping-and-scope-identity-manifest.json
EVIDENCE_ALREADY_AVAILABLE=business physical event, quantity basis, unit, weighing point, marketability boundary, and local time facts
EVIDENCE_STILL_MISSING=formal Q2C decision, attestation, target binding, transformation authority, and decision hash
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=Package A now records the local-day, exclusion and governed scope boundaries; remaining work is formal Q2C decision preparation and independent review, while pre-weigh reconstruction fields remain non-blocking
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_Q2C_DECISION_ARTIFACT_AFTER_PACKAGE_A_REVIEW
```

### S1-SOURCE-AUTHORITY

```text
GATE_ID=S1-SOURCE-AUTHORITY
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=10
FORMALIZED_GOVERNANCE_FACT_COUNT=4
FORMAL_ARTIFACT_PRESENT_COUNT=3
FACTS_ALREADY_AVAILABLE=source system; dataset; source owner role; version; snapshot reference; source/schema hashes; object metadata
FACTS_PRESENT_BUT_NOT_FORMALIZED=revision policy; withdrawal/void policy; source authority binding
FORMAL_ARTIFACTS_MISSING=business source attestation; attestation hash; source registry binding
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=governed source identity, applicability, authority, custody and withdrawal binding
CURRENT_SUPPORTING_ARTIFACTS=source-authority-and-cohort-manifest.md; source-002-governed-snapshot-evidence.md; source-authority-evidence-status.md; business-source-attestation-draft.md; source-002-mapping-and-scope-identity-manifest.json; source-002-custody-record.json
EVIDENCE_ALREADY_AVAILABLE=source system, dataset, owner role, version, snapshot reference, source hash, schema identity, byte count, and row count
EVIDENCE_STILL_MISSING=formal source attestation, effective time, completeness authority, attestation hash, and independent review
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=source identity, local-day boundary, exclusion boundary, scope package reference and custody policy are now formalized for review; source attestation and completeness authority remain unissued
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_SOURCE_ATTESTATION_AFTER_COMPLETENESS_AND_PACKAGE_A_REVIEW
```

### S1-SOURCE-COHORT

```text
GATE_ID=S1-SOURCE-COHORT
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=20
FORMALIZED_GOVERNANCE_FACT_COUNT=4
FORMAL_ARTIFACT_PRESENT_COUNT=3
FACTS_ALREADY_AVAILABLE=canonical grain support; mapped season; aggregate counts; date bounds; July unresolved boundary; source-object identity
FACTS_PRESENT_BUT_NOT_FORMALIZED=mapping policy; inclusion/exclusion binding; cohort custody binding
FORMAL_ARTIFACTS_MISSING=source cohort manifest; manifest hash; mapping/scope manifest
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=versioned source cohort identity, scope, mapping, inclusion and manifest authority
CURRENT_SUPPORTING_ARTIFACTS=source-authority-and-cohort-manifest.md; source-002-governed-snapshot-evidence.md; source-cohort-evidence-status.md; source-schema-field-map-and-gap-register.md; source-002-mapping-and-scope-identity-manifest.json; source-002-inclusion-exclusion-manifest.json; source-002-custody-record.json
EVIDENCE_ALREADY_AVAILABLE=source-object identity, canonical grain support, mapped season, aggregate counts, date bounds, and unresolved July boundary
EVIDENCE_STILL_MISSING=approved mapping policy, formal source cohort manifest/version/hash, concrete arrays in the cohort artifact, source attestation binding, and independent review
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=Package A now binds reviewed scope counts and array hashes without storing full arrays in Git; source cohort creation remains a separate formal artifact step and does not imply source-cohort acceptance
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_SOURCE_COHORT_MANIFEST_AFTER_SOURCE_ATTESTATION_REVIEW
```

### S1-PHYSICAL-MEANING

```text
GATE_ID=S1-PHYSICAL-MEANING
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=11
FORMALIZED_GOVERNANCE_FACT_COUNT=0
FORMAL_ARTIFACT_PRESENT_COUNT=0
FACTS_ALREADY_AVAILABLE=field-side first valid scan/weigh; marketable fruit; field sorting; packhouse/rejection non-retroactivity
FACTS_PRESENT_BUT_NOT_FORMALIZED=physical measurement attestation; measurement authority; formal boundary policy
FORMAL_ARTIFACTS_MISSING=physical measurement section of source attestation; Q2C decision hash
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES_FOR_FACT_LAYER
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=accepted physical event, marketability and post-harvest boundary semantics
CURRENT_SUPPORTING_ARTIFACTS=target-decision-and-quantity-contract.md; q2c-target-decision-draft.md; source-measurement-and-finalization-rules-draft.md; q2c-physical-alignment-evidence-status.md
EVIDENCE_ALREADY_AVAILABLE=first valid field scan/weigh event, marketable-fruit boundary, field sorting rule, and non-retroactive packhouse/rejection rules
EVIDENCE_STILL_MISSING=formal physical-measurement attestation, measurement authority, and Q2C decision hash
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=recorded label business facts are available at the required boundary; formal physical attestation and independent review remain missing
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_RECORDED_LABEL_PHYSICAL_ATTESTATION_FOR_INDEPENDENT_REVIEW
```

### S1-UNIT-AND-TIME-BASIS

```text
GATE_ID=S1-UNIT-AND-TIME-BASIS
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=5
FORMALIZED_GOVERNANCE_FACT_COUNT=1
FORMAL_ARTIFACT_PRESENT_COUNT=1
FACTS_ALREADY_AVAILABLE=kg; 0.001 kg exported precision; three decimals; no integer rounding; Asia/Shanghai calendar
FACTS_PRESENT_BUT_NOT_FORMALIZED=formal farm-local time attestation; source precision/rounding binding
FORMAL_ARTIFACTS_MISSING=unit/time attestation and measurement binding
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=accepted quantity unit, precision, tare and farm-local time basis
CURRENT_SUPPORTING_ARTIFACTS=source-measurement-and-finalization-rules-draft.md; q2c-target-decision-draft.md; q2c-physical-alignment-evidence-status.md; source-002-inclusion-exclusion-manifest.json
EVIDENCE_ALREADY_AVAILABLE=kg, exported 0.001 kg precision, three decimal representation, no integer rounding, and Asia/Shanghai calendar
EVIDENCE_STILL_MISSING=formal unit/time attestation binding and independent review
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=the local-day boundary is now formalized in the inclusion boundary; remaining work is formal attestation binding, not a new factual question
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_UNIT_TIME_ATTESTATION_AFTER_PACKAGE_A_REVIEW
```

### S1-CANONICAL-GRAIN

```text
GATE_ID=S1-CANONICAL-GRAIN
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=2
FORMALIZED_GOVERNANCE_FACT_COUNT=2
FORMAL_ARTIFACT_PRESENT_COUNT=1
FACTS_ALREADY_AVAILABLE=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE; PLOT_SUPPORTED=false
FACTS_PRESENT_BUT_NOT_FORMALIZED=mapping policy; canonical identity registry; source scope binding
FORMAL_ARTIFACTS_MISSING=mapping/scope manifest and cohort binding
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=canonical label grain and deterministic identity/mapping scope
CURRENT_SUPPORTING_ARTIFACTS=source-authority-and-cohort-manifest.md; source-002-governed-snapshot-evidence.md; source-schema-field-map-and-gap-register.md; q2c-physical-alignment-evidence-status.md; source-002-mapping-and-scope-identity-manifest.json
EVIDENCE_ALREADY_AVAILABLE=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE and PLOT_SUPPORTED=false
EVIDENCE_STILL_MISSING=approved mapping policy, formal source cohort binding, and cohort manifest hash
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=the reviewed scope identity package is now bound by counts and array hashes; full arrays remain outside Git and formal cohort creation remains a separate artifact step
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=PREPARE_FORMAL_SOURCE_COHORT_SCOPE_BINDING_AFTER_PACKAGE_A_REVIEW
```

### S1-INCLUSION-EXCLUSION

```text
GATE_ID=S1-INCLUSION-EXCLUSION
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=3
FORMALIZED_GOVERNANCE_FACT_COUNT=3
FORMAL_ARTIFACT_PRESENT_COUNT=2
FACTS_ALREADY_AVAILABLE=July automatic assignment false; unmapped date pending; missing-day remains UNKNOWN_NOT_ZERO
FACTS_PRESENT_BUT_NOT_FORMALIZED=approved source scope; July exception policy; no-record mapping rule
FORMAL_ARTIFACTS_MISSING=inclusion/exclusion manifest; coverage-scope binding
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_FORMAL_ARTIFACT_PREPARATION
AUTHORITATIVE_REQUIREMENT=approved inclusion, exclusion, unmapped-date and missingness semantics
CURRENT_SUPPORTING_ARTIFACTS=source-002-governed-snapshot-evidence.md; source-002-formalization-gap-matrix.md; season-calendar-rule-draft.md; source-002-idfl-v1-source-specific-eligibility-package.md; source-002-inclusion-exclusion-manifest.json; source-002-mapping-and-scope-identity-manifest.json
EVIDENCE_ALREADY_AVAILABLE=July automatic assignment false, unmapped date pending, and UNKNOWN_NOT_ZERO missingness boundary
EVIDENCE_STILL_MISSING=formal source cohort binding, July exception policy, formal no-record rule, and independent review
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=the inclusion/exclusion boundary and governed scope package are now issued for review; July assignment remains pending and future S2 cleaning exclusions remain allowed
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=REVIEW_INCLUSION_EXCLUSION_MANIFEST_BEFORE_SOURCE_COHORT_PREPARATION
```

### S1-DATA-CUSTODY

```text
GATE_ID=S1-DATA-CUSTODY
CANONICAL_CURRENT_STATUS=BLOCKED
RECONCILED_CLASSIFICATION=PARTIAL_EVIDENCE
KNOWN_BUSINESS_FACT_COUNT=6
FORMALIZED_GOVERNANCE_FACT_COUNT=6
FORMAL_ARTIFACT_PRESENT_COUNT=1
FACTS_ALREADY_AVAILABLE=C1 enterprise server; C2 IT department; C3 no explicit role restriction; C4 approved intended purpose; C5/C6 not formalized
FACTS_PRESENT_BUT_NOT_FORMALIZED=access owner job role; authorized role set; retention; withdrawal/replacement; downstream invalidation
FORMAL_ARTIFACTS_MISSING=versioned custody record; external object binding; custody hash
TRULY_MISSING_BUSINESS_INPUTS=NONE
CAN_BE_DERIVED_FROM_EXISTING_REPOSITORY_EVIDENCE=YES
REQUIRES_NEW_EXTERNAL_INPUT=false
NEW_FACTUAL_BUSINESS_ANSWER_REQUIRED=false
DECISION_CANDIDATE_STATUS=READY_FOR_GOVERNANCE_DECISION
AUTHORITATIVE_REQUIREMENT=versioned custody, access, retention, withdrawal and external-object binding
CURRENT_SUPPORTING_ARTIFACTS=split-holdout-and-custody-contract.md; source-002-completeness-and-custody-business-evidence.md; data-custody-evidence-status.md; source-002-custody-record.json
EVIDENCE_ALREADY_AVAILABLE=enterprise server, IT department control fact, no explicit role restriction, intended use, and C5/C6 not-formalized answers
EVIDENCE_STILL_MISSING=independent review and custody gate decision; the issued record remains non-accepted
EXTERNAL_INPUT_REQUIRED=false
EXTERNAL_INPUT_DESCRIPTION=the confirmed custody roles, purpose, retention, withdrawal, replacement and propagation policy are issued in a versioned record; acceptance remains a separate review decision
SOURCE_002_SPECIFIC_ONLY=true
FULL_S1_SCOPE_COVERED=false
FORMAL_ACCEPTANCE_EXISTS=false
INDEPENDENT_REVIEW_EXISTS=false
RECOMMENDED_NEXT_ACTION=REVIEW_ISSUED_CUSTODY_RECORD_BEFORE_CUSTODY_GATE_DECISION
```

## 10. Current eight-gate classification summary

```text
RECONCILED_CLASSIFICATION_PASS_CANDIDATE_READY_COUNT=0
RECONCILED_CLASSIFICATION_PARTIAL_EVIDENCE_COUNT=8
RECONCILED_CLASSIFICATION_BLOCKED_EXTERNAL_BUSINESS_OR_GOVERNANCE_INPUT_COUNT=0
RECONCILED_CLASSIFICATION_NOT_YET_WORKED_COUNT=0
DECISION_CANDIDATE_READY_COUNT=8
DECISION_CANDIDATE_BLOCKED_BY_TRULY_MISSING_BUSINESS_INPUT_COUNT=0
DECISION_CANDIDATE_BLOCKED_BY_NOT_FORMALIZED_GOVERNANCE_COUNT=0
```

All eight Package A candidates now have the factual inputs and scoped
supporting artifacts needed for the next formal-artifact or governance-review
step. These decision-candidate classifications are not canonical gate
statuses, and the four remaining formal artifacts still block any acceptance.

## 11. Status-artifact drift reconciliation

```text
STATUS_RECONCILIATION_DRIFT_FOUND=true
STATUS_RECONCILIATION_DRIFT_FIXED=true
STATUS_RECONCILIATION_ONLY=true
CANONICAL_GATE_STATUS_CHANGED=false
```

The following artifacts were updated only in their factual and explanatory
layers:

- custody status now records `ENTERPRISE_SERVER`, `IT部门`, the intended
  purpose, and the still-unformalized role/policy fields;
- source-authority status now records Source 002 identity/schema/hash facts;
- source-cohort status now records object and aggregate coverage facts;
- Q2C status now records business-provided physical facts;
- business-acceptance package and manifest now point to later evidence while
  preserving blocked formal status.

## 11A. Package A formalization reconciliation

```text
PACKAGE_A_FORMALIZATION_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
LOCAL_DAY_BOUNDARY_FORMALIZED=true
KNOWN_EXCLUSIONS_FORMALIZED=true
COVERAGE_SCOPE_IDENTITY_PACKAGE_BOUND=true
VERSIONED_CUSTODY_RECORD_ISSUED=true
FULL_ENTITY_ARRAYS_COMMITTED_TO_GIT=false
FORMAL_MAPPING_ACCEPTED=false
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=false
SOURCE_002_COMPLETENESS_AUTHORITY_ACCEPTED=false
```

The three new artifacts formalize Package A evidence and policy boundaries
only. The reviewed scope package is referenced by counts and array hashes;
the 84/192/20 entity arrays remain outside Git. The custody record is issued
for independent review but is not custody acceptance. The source attestation,
source cohort manifest, Q2C decision, and completeness authority record remain
unissued.

`s1-acceptance-record.json` was not changed. Its seventeen rows remain
`BLOCKED`, so later evidence cannot be mistaken for gate acceptance.

## 12. Explicit non-acceptance boundary

```text
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
SOURCE_002_COMPLETENESS_AUTHORITY_ACCEPTED=false
SOURCE_002_CUSTODY_ACCEPTED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
DATABASE_WRITE=false
PRODUCTION_CODE_CHANGED=false
TEST_CHANGED=false
MIGRATION_CREATED=false
```

`SOURCE_SYSTEM=扫码称重系统` remains bound to the exact source/schema
identity. Package A formalizes the confirmed local-day, exclusion boundary,
scope-package reference and custody policy; it does not create completeness,
Q2C, source-attestation, source-cohort, or target authority.

## 13. Recommended Phase 2

```text
NEXT_PHASE_CANDIDATE=PACKAGE_A_FORMALIZATION_INDEPENDENT_REVIEW
NEXT_PHASE_STATUS=CANDIDATE_ONLY
NEXT_PHASE_SCOPE=independently review the three Package A artifacts and their exact source/hash bindings before preparing the four remaining formal artifacts
NEXT_PHASE_REQUIRES_SEPARATE_USER_AUTHORIZATION=true
```

The next review must not issue a gate acceptance, alter the canonical
acceptance record, start Package B, authorize S2, read Source 002, or run a
backtest.
