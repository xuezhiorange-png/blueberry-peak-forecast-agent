# S1 Acceptance Package

## Acceptance identity and current state

```text
ACCEPTANCE_PACKAGE_ID=V0_3_S1_ACCEPTANCE_PACKAGE
SLICE=V0.3-S1
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=7
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=10
CURRENT_PHYSICAL_MEANING_ATTESTATION_STATUS=ACCEPTED
CURRENT_PHYSICAL_MEANING_ATTESTATION_VERSION=source-002-physical-meaning-attestation-v1
CURRENT_PHYSICAL_MEANING_ATTESTATION_HASH=1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944
CURRENT_UNIT_TIME_BASIS_ATTESTATION_STATUS=ACCEPTED
CURRENT_UNIT_TIME_BASIS_ATTESTATION_VERSION=source-002-unit-time-basis-attestation-v1
CURRENT_UNIT_TIME_BASIS_ATTESTATION_HASH=d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee
PHYSICAL_MEANING_ACCEPTED=true
UNIT_TIME_BASIS_ACCEPTED=true
Q2C_ACCEPTED=true
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=true
CANONICAL_Q2C_GATE_STATUS=PASS
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
SLICE_S1_COMPLETE=BLOCKED
CURRENT_ACCEPTANCE_RECORD_STATUS=BLOCKED
CURRENT_INDEPENDENT_REVIEW_STATUS=NOT_STARTED
S1_INDEPENDENT_REVIEW=BLOCKED
PR245_INDEPENDENT_REVIEW_NUMERIC_ID=4949133128
PR245_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJv3HSA
PR245_REVIEWED_HEAD_SHA=7acea813d3f0ae17579da325dfa2f38c7ea9d0c8
PR245_EXACT_HEAD_CI_RUN_ID=32002755230
PR245_MERGE_SHA=1ee6da741fe13e163b53c26b2a6705ac8eb28a72
```

This is the single runtime gate registry for S1. Every row uses the same
runtime field set; there is no separate initial-status authority. Ten required
rows remain blocked because other gate-specific evidence and final independent
review are not present. Source Authority is accepted by the
PR #238 exact-head reviewed attestation closeout, and Source Cohort is accepted
by the PR #241 exact-head reviewed final manifest closeout. The standalone
`S1-MINIMUM-COVERAGE` and `S1-DATA-QUALITY-THRESHOLDS` rows are now `PASS` and
bind the independently reviewed owner decision hash. The S1-Q2C-TARGET row is
also `PASS` from the PR #243 exact-head reviewed Q2C closeout. PR #245
independently reviewed and merged the two issued Physical Meaning and
Unit/Time Basis attestations; no row-level data is issued by this package.

```text
COMPLETION_GATE_REGISTRY_IS_AUTHORITATIVE=true
LEGACY_COMPLETION_BOOLEANS_DERIVED_ONLY=true
LEGACY_COMPLETION_BOOLEANS_MAY_OVERRIDE_GATE_STATUS=false
```

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

The `status` field is the only runtime status field and `block_reason` is the
only runtime blocking-reason field. All seventeen S1 decision gates are
`required`; the holdout-feasibility gate is a required feasibility decision and
is not the future external-holdout materialization gate.

For `S1-HOLDOUT-FEASIBILITY`, a reviewed `FEASIBLE` decision or a reviewed
`NOT_FEASIBLE` decision can both close this required S1 decision gate as
`PASS`. Neither outcome materializes an external holdout. A future
external-holdout materialization gate is conditional and is outside this
package; it is not permitted to turn this required feasibility gate into
`NOT_APPLICABLE`.

## Canonical gate registry

| gate_id | gate_class | required_or_conditional | owner_role | authoritative_artifact | artifact_identity | artifact_hash_or_status | metric_contract_version | acceptance_threshold_source | acceptance_threshold | allowed_not_applicable_condition | status | block_reason | reviewer_role | reviewer | reviewed_at | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S1-Q2C-TARGET` | business | required | business_data_owner_role | Source002 Q2C business-source attestation and final Q2C decision | `source-002-q2c-final-decision-v1` | `c7feccd6791b6e9879f82c034552e53d5cc96922314cffa4d21fe5ee1e5d0e18` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C contract | `Q2C_OUTCOME_CLOSED` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4948542090` | `2026-08-17T04:52:16Z` | PR #243 exact-head independent review 4948542090 returned PASS on reviewed head 88082afb26c33a69e119a3c8b1ce2d215b815f54; exact-head CI 31995247463 completed success; all six dimensions are PROVEN_EXACT, no transformation is required, and merge fa828e05ac5599ba2bce87e4260749210516376b entered current main. This closes S1-Q2C-TARGET only. |
| `S1-SOURCE-AUTHORITY` | source | required | source_governance_owner_role | Source002 final Source Owner Attestation | `source-002-final-source-owner-attestation-v1` | `2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1` | `NOT_APPLICABLE_FOR_THIS_GATE` | source authority contract | `OWNER_ROLE_AND_ATTESTED_VERSION_PRESENT` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4946622009` | `2026-08-16T16:17:55Z` | PR #238 exact-head independent acceptance and CI 31955752008 verified the final Source Owner Attestation; this closes Source Authority only. |
| `S1-SOURCE-COHORT` | source | required | data_governance_owner_role | Source002 final Source Cohort Manifest | `source-002-final-source-cohort-manifest-v1` | `27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca` | `NOT_APPLICABLE_FOR_THIS_GATE` | source cohort contract | `MANIFEST_HASH_AND_SCOPE_PRESENT` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4948013727` | `2026-08-17T02:25:52Z` | PR #241 exact-head review 4948013727 returned PASS on reviewed head b856d3823e51bb6e4f8b780363203a1c477677ca; exact-head CI 31986614521 completed success; final Source Cohort Manifest hash replay passed; PR #241 merge 5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b entered current main. This closes Source Cohort only: S1 freezes the cohort identity but does not freeze the final clean/materialized rowset; S2 owns the final materialized rowset. Q2C and all other canonical gates remain separate. |
| `S1-PHYSICAL-MEANING` | business | required | business_data_owner_role | Source002 Physical Meaning Attestation | `source-002-physical-meaning-attestation-v1` | `1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical dimensions | `EVENT_AND_MARKETABILITY_BOUNDARY_EVIDENCED` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4949133128` | `2026-08-17T06:58:24Z` | Physical Meaning Attestation was independently reviewed PASS on PR #245 exact head `7acea813d3f0ae17579da325dfa2f38c7ea9d0c8`; exact-head CI `32002755230` completed success and PR #245 merge `1ee6da741fe13e163b53c26b2a6705ac8eb28a72` entered current main. The first valid governed field scan-weigh event and marketability boundary are bound. This closes Physical Meaning only. |
| `S1-UNIT-AND-TIME-BASIS` | business | required | business_data_owner_role | Source002 Unit/Time Basis Attestation | `source-002-unit-time-basis-attestation-v1` | `d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical and time dimensions | `KG_AND_FARM_LOCAL_DATE_BOUND` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4949133128` | `2026-08-17T06:58:24Z` | Unit/Time Basis Attestation was independently reviewed PASS on PR #245 exact head `7acea813d3f0ae17579da325dfa2f38c7ea9d0c8`; exact-head CI `32002755230` completed success and PR #245 merge `1ee6da741fe13e163b53c26b2a6705ac8eb28a72` entered current main. KG, farm-local HARVEST_BUSINESS_DATE, and Asia/Shanghai are bound; 0.001 kg remains a representation, not device metrology. Canonical Grain and Inclusion/Exclusion remain separate and BLOCKED. |
| `S1-CANONICAL-GRAIN` | source | required | source_governance_owner_role | source and mapping manifest | `CANONICAL_GRAIN_REQUIRED` | `BLOCKED_NO_MAPPING_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `CANONICAL_GRAIN_AND_MAPPING_BOUND` | `NEVER` | `BLOCKED` | `GRAIN_OR_DATE_AUTHORITY_MISSING` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Plot support remains false. |
| `S1-VISIBILITY` | data | required | data_governance_owner_role | visibility and snapshot manifest | `VISIBILITY_MANIFEST_REQUIRED` | `BLOCKED_NO_VISIBILITY_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `SOURCE_CLASS_CUTOFF_RULES_EVIDENCED` | `NEVER` | `BLOCKED` | `HISTORICAL_VISIBILITY_NOT_RECONSTRUCTABLE` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Canonical visibility remains BLOCKED solely because S1-CANONICAL-GRAIN and S1-INCLUSION-EXCLUSION have not been accepted; S1-Q2C-TARGET is accepted separately. |
| `S1-REVISION-WINNER` | data | required | data_governance_owner_role | revision lineage and winner manifest | `WINNER_MANIFEST_REQUIRED` | `BLOCKED_NO_REVISION_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `ONE_VALID_WINNER_PER_KEY` | `NEVER` | `BLOCKED` | `REVISION_WINNER_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Lineage cannot be inferred from import order. |
| `S1-INCLUSION-EXCLUSION` | data | required | data_quality_owner_role | inclusion and exclusion manifest | `EXCLUSION_MANIFEST_REQUIRED` | `BLOCKED_NO_COHORT_EVIDENCE` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `REASONS_AND_COUNTS_RECONCILED` | `NEVER` | `BLOCKED` | `INCLUSION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Unknown is not zero. |
| `S1-MISSING-CORRECTION-CANCELLATION` | data | required | data_quality_owner_role | correction, missing-day, and cancellation policy | `MISSING_CORRECTION_CANCELLATION_REQUIRED` | `BLOCKED_NO_SOURCE_POLICY` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `LATE_ENTRY_REVISION_VOID_RULES_PRESENT` | `NEVER` | `BLOCKED` | `REVISION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Delayed, corrected, and void records need authority. |
| `S1-SPLIT-POLICY` | evaluation | required | model_validation_owner_role | split policy and custody record | `SPLIT_POLICY_REQUIRED` | `BLOCKED_SPLIT_POLICY_NOT_FROZEN` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `TIME_ORDERED_SPLITS_AND_NO_LEAKAGE` | `NEVER` | `BLOCKED` | `SPLIT_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | No TEST or holdout is accessed. |
| `S1-METRIC-CONTRACT` | metrics | required | model_validation_owner_role | S1 metric contract and S3 binding | `METRIC_CONTRACT_REQUIRED` | `BLOCKED_NO_ACCEPTED_SOURCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S3 contract | `ALL_CANONICAL_METRIC_IDS_AND_STATES_BOUND` | `NEVER` | `BLOCKED` | `METRIC_CONTRACT_NOT_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Quantile and baseline gates remain fail-closed. |
| `S1-MINIMUM-COVERAGE` | metrics | required | model_validation_owner_role | coverage threshold decision record | `v0-3-s1-minimum-coverage-threshold-v1` | `a9361145eaa04e93e6b7bc3a4e4faa7a42c542b29de4978988658f53fa11f692` | `v0.3-metric-contract-v1` | S3 contract and independently reviewed owner decision `4937929668` | `S3_COVERAGE_RATIO_GREATER_THAN_OR_EQUAL_0.900000_PER_APPLICATION_CELL` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4937929668` | `2026-08-14T14:04:08Z` | Owner decision payload/hash and exact-head CI were independently reviewed on PR #219 head `5775e908cfe072fa962c99e822901b7157128418`; S3 reporting floor 10 is not the S1 threshold. |
| `S1-DATA-QUALITY-THRESHOLDS` | data | required | data_quality_owner_role | `v0-3-s1-data-quality-threshold-policy-v1` | `v0-3-s1-data-quality-threshold-policy-v1` | `11e810f4385965f173c6a269d08a1469f6eb4f6173610d272b4ecc09b2171969` | `v0.3-metric-contract-v1` | reviewed versioned data-quality owner policy | `VALID_INCLUDED_CANONICAL_GROUP_COVERAGE_GREATER_THAN_OR_EQUAL_1.000000_PER_APPLICATION_CELL` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4943327077` | `2026-08-15T08:09:57Z` | Owner decision comment `5301040523` and exact-head CI `31872490353` are bound; this accepts the policy only, not data execution or any other gate. |
| `S1-DATA-CUSTODY` | governance | required | data_governance_owner_role | versioned custody record | `CUSTODY_RECORD_REQUIRED` | `BLOCKED_NO_GOVERNED_CUSTODY_RECORD` | `NOT_APPLICABLE_FOR_THIS_GATE` | source custody contract | `ACCESS_RETENTION_WITHDRAWAL_VOID_EVIDENCED` | `NEVER` | `BLOCKED` | `SOURCE_CUSTODY_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Policy identities and hashes only. |
| `S1-HOLDOUT-FEASIBILITY` | evaluation | required | model_validation_owner_role | external holdout feasibility record | `HOLDOUT_FEASIBILITY_REQUIRED` | `BLOCKED_NO_COHORT_FEASIBILITY_EVIDENCE` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | split contract | `REVIEWED_FEASIBLE_OR_REVIEWED_NOT_FEASIBLE` | `NEVER` | `BLOCKED` | `FEASIBILITY_NOT_YET_ACCEPTED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | This gate is required; it is not materialization. |
| `S1-INDEPENDENT-REVIEW` | governance | required | independent_reviewer_role | complete S1 acceptance record | `ACCEPTANCE_RECORD_REQUIRED` | `BLOCKED_NO_INDEPENDENT_REVIEW` | `NOT_APPLICABLE_FOR_THIS_GATE` | S1 package | `ALL_REQUIRED_GATES_CLOSED` | `NEVER` | `BLOCKED` | `NOT_YET_INDEPENDENTLY_REVIEWED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Review cannot be self-attested. |

## Acceptance calculation

```text
COMPLETION_RULE=ALL_17_REQUIRED_GATE_ROWS_STATUS_PASS
CURRENT_REQUIRED_GATE_PASS_COUNT=7
CURRENT_REQUIRED_GATE_BLOCKED_COUNT=10
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
CURRENT_SOURCE_COHORT_ACCEPTED=true
CURRENT_Q2C_ACCEPTED=true
CURRENT_CANONICAL_Q2C_GATE_STATUS=PASS
CURRENT_REQUIRED_GATE_BLOCKED=true
CURRENT_ACCEPTANCE_RESULT=BLOCKED
CURRENT_S1_ACCEPTED=false
CURRENT_S2_AUTHORIZATION=false
```

The current package records the minimum-coverage, data-quality policy, Source
Authority, Source Cohort, Q2C target, Physical Meaning, and Unit/Time Basis
gates as closed, but it cannot close canonical grain, split, holdout-feasibility,
metric-contract, custody, or final S1 acceptance. Source Cohort acceptance
freezes identity only; S2 still owns the final materialized rowset. All
downstream and unrelated gates remain fail-closed. A future accepted record
must preserve prior evidence identities and record the final independent S1
reviewer and review time.

The JSON schema in this directory requires exactly these seventeen canonical
gate IDs once each. A required gate cannot be `NOT_APPLICABLE`; only a future
conditional gate outside this package could use that state after reviewed
evidence.
