# S1 Acceptance Package

## Acceptance identity

```text
ACCEPTANCE_PACKAGE_ID=V0_3_S1_ACCEPTANCE_PACKAGE
SLICE=V0.3-S1
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
CURRENT_ACCEPTANCE_RECORD_STATUS=BLOCKED
CURRENT_INDEPENDENT_REVIEW_STATUS=NOT_STARTED
```

This is the complete gate registry for S1. Every gate row uses the same runtime
field set. There is no separate initial-status authority. All rows are blocked
because the external source authority and cohort evidence are not present in
this repository and no independent S1 review has occurred.

## Runtime gate field set

```text
gate_id
gate_class
required_or_conditional
owner_role
authoritative_artifact
artifact_identity
artifact_hash_or_status
metric_contract_version
acceptance_threshold_source
acceptance_threshold
allowed_not_applicable_condition
status
block_reason
reviewer_role
reviewer
reviewed_at
notes
```

`status` is the only runtime status field. `block_reason` is the only runtime
blocking-reason field. For this unaccepted package, `artifact_hash_or_status`
records a concrete missing-evidence state rather than a fabricated hash.

## Gate registry

| gate_id | gate_class | required_or_conditional | owner_role | authoritative_artifact | artifact_identity | artifact_hash_or_status | metric_contract_version | acceptance_threshold_source | acceptance_threshold | allowed_not_applicable_condition | status | block_reason | reviewer_role | reviewer | reviewed_at | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S1-TARGET-Q2C` | business | required | business_data_owner_role | business source attestation | `BUSINESS_ATTESTATION_REQUIRED` | `BLOCKED_NO_EXTERNAL_ATTESTATION` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C contract | `Q2C_OUTCOME_CLOSED` | `NEVER` | `BLOCKED` | `MISSING_BUSINESS_ATTESTATION` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Six Q2C dimensions are not closed. |
| `S1-SOURCE-AUTHORITY` | source | required | source_governance_owner_role | attestation and source registry record | `SOURCE_AUTHORITY_REQUIRED` | `BLOCKED_NO_SOURCE_AUTHORITY` | `NOT_APPLICABLE_FOR_THIS_GATE` | source authority contract | `OWNER_ROLE_AND_ATTESTED_VERSION_PRESENT` | `NEVER` | `BLOCKED` | `MISSING_SOURCE_OWNER_AUTHORITY` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No source value is invented. |
| `S1-SOURCE-COHORT` | source | required | data_governance_owner_role | source cohort manifest | `COHORT_MANIFEST_REQUIRED` | `BLOCKED_NO_SOURCE_COHORT` | `NOT_APPLICABLE_FOR_THIS_GATE` | source cohort contract | `MANIFEST_HASH_AND_COVERAGE_SUMMARY_PRESENT` | `NEVER` | `BLOCKED` | `SOURCE_COHORT_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No raw rows are in this package. |
| `S1-PHYSICAL-BOUNDARY` | business | required | business_data_owner_role | physical measurement attestation | `MEASUREMENT_BOUNDARY_REQUIRED` | `BLOCKED_NO_MEASUREMENT_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical dimensions | `EVENT_UNIT_BOUNDARY_AND_CALIBRATION_EVIDENCED` | `NEVER` | `BLOCKED` | `MISSING_MEASUREMENT_BOUNDARY` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Farm-pick versus marketability remains unresolved. |
| `S1-TIME-GRAIN` | source | required | source_governance_owner_role | source and mapping manifest | `TIME_GRAIN_BINDING_REQUIRED` | `BLOCKED_NO_MAPPING_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `CANONICAL_GRAIN_AND_LOCAL_TIME_BOUND` | `NEVER` | `BLOCKED` | `GRAIN_OR_DATE_AUTHORITY_MISSING` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Canonical grain is fixed, source mapping is not. |
| `S1-VISIBILITY` | data | required | data_governance_owner_role | visibility and snapshot manifest | `VISIBILITY_MANIFEST_REQUIRED` | `BLOCKED_NO_VISIBILITY_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `AS_OF_RULE_AND_CUTOFF_EVIDENCED` | `NEVER` | `BLOCKED` | `HISTORICAL_VISIBILITY_NOT_RECONSTRUCTABLE` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No current-state fallback is allowed. |
| `S1-REVISION-WINNER` | data | required | data_governance_owner_role | revision lineage and winner manifest | `WINNER_MANIFEST_REQUIRED` | `BLOCKED_NO_REVISION_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `ONE_VALID_WINNER_PER_KEY` | `NEVER` | `BLOCKED` | `REVISION_WINNER_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Lineage cannot be inferred from import order. |
| `S1-INCLUSION-EXCLUSION` | data | required | data_quality_owner_role | inclusion and exclusion manifest | `EXCLUSION_MANIFEST_REQUIRED` | `BLOCKED_NO_COHORT_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `REASONS_AND_COUNTS_RECONCILED` | `NEVER` | `BLOCKED` | `INCLUSION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Unknown is not zero. |
| `S1-CORRECTION-MISSING` | data | required | data_quality_owner_role | correction and missing-day policy | `CORRECTION_POLICY_REQUIRED` | `BLOCKED_NO_SOURCE_POLICY` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `LATE_ENTRY_REVISION_VOID_RULES_PRESENT` | `NEVER` | `BLOCKED` | `REVISION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Delayed and corrected records need authority. |
| `S1-SPLIT-POLICY` | evaluation | required | model_validation_owner_role | split manifest and custody record | `SPLIT_MANIFEST_REQUIRED` | `BLOCKED_NO_SOURCE_COHORT` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `TIME_ORDERED_SPLITS_AND_NO_LEAKAGE` | `NEVER` | `BLOCKED` | `SPLIT_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No TEST or holdout is accessed. |
| `S1-EXTERNAL-HOLDOUT` | evaluation | conditional | model_validation_owner_role | external holdout feasibility record | `HOLDOUT_FEASIBILITY_REQUIRED` | `BLOCKED_NO_COHORT_FEASIBILITY_EVIDENCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `FEASIBILITY_REVIEWED_BEFORE_ACCESS` | `ONLY_IF_REVIEWED_NOT_APPLICABLE` | `BLOCKED` | `FEASIBILITY_NOT_YET_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Not applicable has not been independently accepted. |
| `S1-METRIC-CONTRACT` | metrics | required | model_validation_owner_role | S1 metric contract and S3 binding | `METRIC_CONTRACT_REQUIRED` | `BLOCKED_NO_ACCEPTED_SOURCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S3 contract | `ALL_METRIC_IDS_AND_STATES_BOUND` | `NEVER` | `BLOCKED` | `METRIC_CONTRACT_NOT_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Quantile and baseline gates remain fail-closed. |
| `S1-COVERAGE-THRESHOLD` | metrics | required | model_validation_owner_role | threshold decision record | `COVERAGE_THRESHOLD_REQUIRED` | `BLOCKED_NO_THRESHOLD_AUTHORITY` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S3 contract and approved threshold record | `THRESHOLD_VERSION_AND_PROVENANCE_PRESENT` | `NEVER` | `BLOCKED` | `COVERAGE_THRESHOLD_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No number is inferred from CI data. |
| `S1-QUALITY-THRESHOLD` | data | required | data_quality_owner_role | data quality threshold record | `QUALITY_THRESHOLD_REQUIRED` | `BLOCKED_NO_THRESHOLD_AUTHORITY` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | approved quality policy | `QUALITY_THRESHOLDS_VERSIONED` | `NEVER` | `BLOCKED` | `DATA_QUALITY_THRESHOLD_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Quality limits need explicit provenance. |
| `S1-CUSTODY` | governance | required | data_governance_owner_role | custody and access record | `CUSTODY_RECORD_REQUIRED` | `BLOCKED_NO_GOVERNED_CUSTODY_RECORD` | `NOT_APPLICABLE_FOR_THIS_GATE` | source custody contract | `ACCESS_AND_IMMUTABILITY_EVIDENCED` | `NEVER` | `BLOCKED` | `SOURCE_CUSTODY_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Credentials and private locations are excluded. |
| `S1-INDEPENDENT-REVIEW` | governance | required | independent_reviewer_role | complete S1 acceptance record | `ACCEPTANCE_RECORD_REQUIRED` | `BLOCKED_NO_INDEPENDENT_REVIEW` | `NOT_APPLICABLE_FOR_THIS_GATE` | S1 package | `ALL_REQUIRED_GATES_CLOSED` | `NEVER` | `BLOCKED` | `NOT_YET_INDEPENDENTLY_REVIEWED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Review cannot be self-attested. |

## Acceptance calculation

```text
COMPLETION_RULE=ALL_REQUIRED_GATE_ROWS_STATUS_PASS_AND_ALL_CONDITIONAL_ROWS_RESOLVED
CURRENT_REQUIRED_GATE_BLOCKED=true
CURRENT_ACCEPTANCE_RESULT=BLOCKED
CURRENT_S1_ACCEPTED=false
CURRENT_S2_AUTHORIZATION=false
```

The current package cannot issue a target, source cohort, split, holdout, or
metric acceptance. A future accepted record must use the JSON schema in this
directory, preserve prior evidence identities, and record an independent
reviewer and review time.
