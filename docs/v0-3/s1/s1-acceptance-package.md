# S1 Acceptance Package

## Acceptance identity and current state

```text
ACCEPTANCE_PACKAGE_ID=V0_3_S1_ACCEPTANCE_PACKAGE
SLICE=V0.3-S1
CANONICAL_GATE_COUNT=17
CURRENT_CANONICAL_GATE_PASS_COUNT=10
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=7
CURRENT_PHYSICAL_MEANING_ATTESTATION_STATUS=ACCEPTED
CURRENT_PHYSICAL_MEANING_ATTESTATION_VERSION=source-002-physical-meaning-attestation-v1
CURRENT_PHYSICAL_MEANING_ATTESTATION_HASH=1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944
CURRENT_UNIT_TIME_BASIS_ATTESTATION_STATUS=ACCEPTED
CURRENT_UNIT_TIME_BASIS_ATTESTATION_VERSION=source-002-unit-time-basis-attestation-v1
CURRENT_UNIT_TIME_BASIS_ATTESTATION_HASH=d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee
PHYSICAL_MEANING_ACCEPTED=true
UNIT_TIME_BASIS_ACCEPTED=true
Q2C_ACCEPTED=true
CURRENT_TASK3_FORMALIZATION_STATUS=INDEPENDENT_REVIEW_PASS
CURRENT_TASK3_CLOSEOUT_STATUS=GRAIN_AND_INCLUSION_PASS_REVISION_WINNER_HARD_PREREQUISITE_BLOCKED
CURRENT_CANONICAL_GRAIN_GATE_EVIDENCE_VERSION=source-002-canonical-grain-mapping-gate-evidence-v1
CURRENT_CANONICAL_GRAIN_GATE_EVIDENCE_HASH=6717ccd9d21aa3575f1ac66264d271c6371e55268633d786bcf7a29129b7fabc
CURRENT_INCLUSION_EXCLUSION_GATE_EVIDENCE_VERSION=source-002-inclusion-exclusion-gate-evidence-v1
CURRENT_INCLUSION_EXCLUSION_GATE_EVIDENCE_HASH=b5ef85cf54b54751c8407c21c252074b67fe61d7f8833466a681176690c6b580
CURRENT_REVISION_WINNER_GATE_EVIDENCE_VERSION=source-002-revision-winner-gate-evidence-v1
CURRENT_REVISION_WINNER_GATE_EVIDENCE_HASH=5774ad13b89e72efb40f63c9b3f9fb5096621b1f0382e4f5d35c097c79b6fc5e
CURRENT_TASK3_CANONICAL_GRAIN_FACT_THRESHOLD_SATISFIED=true
CURRENT_TASK3_INCLUSION_EXCLUSION_FACT_THRESHOLD_SATISFIED=true
CURRENT_TASK3_REVISION_WINNER_FACT_THRESHOLD_SATISFIED=true
CURRENT_TASK3_CANONICAL_GRAIN_ACCEPTED=true
CURRENT_TASK3_INCLUSION_EXCLUSION_ACCEPTED=true
CURRENT_TASK3_REVISION_WINNER_ACCEPTED=false
CURRENT_TASK3_REVISION_WINNER_BLOCKED_BY=S1-MISSING-CORRECTION-CANCELLATION
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
PR247_GATE_LOCAL_REVIEW_NUMERIC_ID=4951647818
PR247_GATE_LOCAL_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJyQmSg
PR247_REVIEWED_HEAD_SHA=ac2ad97579c005c488701e4d3be22531a595ee5f
PR247_REVIEW_SUBMITTED_AT=2026-08-17T12:37:08Z
PR247_EXACT_HEAD_CI_RUN_ID=32018019710
PR247_EXACT_HEAD_CI_CONCLUSION=success
VISIBILITY_ACCEPTED=true
PR250_VISIBILITY_GATE_LOCAL_REVIEW_ID=4956221333
PR250_VISIBILITY_REVIEWED_HEAD_SHA=65eff0186094f5bae5e4bdd5283a2a1491099041
PR250_VISIBILITY_EXACT_HEAD_CI_RUN_ID=32086692500
PR250_VISIBILITY_CLOSEOUT_DECISION_COMMENT_ID=5322269014
```

This is the single runtime gate registry for S1. Every row uses the same
runtime field set; there is no separate initial-status authority. Seven required
rows remain blocked because other gate-specific evidence and final independent
review are not present. Source Authority is accepted by the PR #238 exact-head
reviewed attestation closeout, Source Cohort by PR #241, Q2C by PR #243, and
Physical Meaning / Unit-Time by PR #246. PR #247 exact-head review
`4951647818` accepted the Task-3 formalization evidence; the separately
authorized bounded closeout accepts Canonical Grain and Inclusion/Exclusion.
Revision Winner remains blocked because `S1-MISSING-CORRECTION-CANCELLATION`
is still a declared hard prerequisite and remains `BLOCKED`. No row-level data
is issued by this package.

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
| `S1-PHYSICAL-MEANING` | business | required | business_data_owner_role | Source002 Physical Meaning Attestation | `source-002-physical-meaning-attestation-v1` | `1cacd18aa17797ba229b0198240ef41e753cb9db2763fd7681828e7a77ff3944` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical dimensions | `EVENT_AND_MARKETABILITY_BOUNDARY_EVIDENCED` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4949133128` | `2026-08-17T06:58:24Z` | PR #245 independently reviewed the attestation PASS on exact head `7acea813d3f0ae17579da325dfa2f38c7ea9d0c8`; exact-head CI `32002755230` completed success and merge `1ee6da741fe13e163b53c26b2a6705ac8eb28a72` entered the reviewed evidence on current main. PR #246 performed the separate canonical closeout to PASS/NONE. |
| `S1-UNIT-AND-TIME-BASIS` | business | required | business_data_owner_role | Source002 Unit/Time Basis Attestation | `source-002-unit-time-basis-attestation-v1` | `d6a58c61a8e0f789e928ef26e864a7e995c50a891b3452c7dc6a6fc6645f17ee` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2C physical and time dimensions | `KG_AND_FARM_LOCAL_DATE_BOUND` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4949133128` | `2026-08-17T06:58:24Z` | PR #245 independently reviewed the attestation PASS on exact head `7acea813d3f0ae17579da325dfa2f38c7ea9d0c8`; exact-head CI `32002755230` completed success and merge `1ee6da741fe13e163b53c26b2a6705ac8eb28a72` entered the reviewed evidence on current main. PR #246 performed the separate canonical closeout to PASS/NONE. KG, farm-local HARVEST_BUSINESS_DATE, and Asia/Shanghai remain bound. |
| `S1-CANONICAL-GRAIN` | source | required | source_governance_owner_role | current-main canonical grain/mapping gate evidence | `source-002-canonical-grain-mapping-gate-evidence-v1` | `6717ccd9d21aa3575f1ac66264d271c6371e55268633d786bcf7a29129b7fabc` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `CANONICAL_GRAIN_AND_MAPPING_BOUND` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4951647818` | `2026-08-17T12:37:08Z` | PR #247 exact-head review accepted the canonical grain evidence on `ac2ad97579c005c488701e4d3be22531a595ee5f`; CI `32018019710` succeeded. This bounded closeout changes only this row from BLOCKED/GRAIN_OR_DATE_AUTHORITY_MISSING to PASS/NONE. |
| `S1-VISIBILITY` | data | required | data_governance_owner_role | visibility and snapshot manifest | `V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT@forecast-input-pit-leakage-audit-v2` | `eeaa91cd1121664d87e129dd4099d976e34d35da66df35299449d311055fb050` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `SOURCE_CLASS_CUTOFF_RULES_EVIDENCED` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4956221333` | `2026-08-18T01:22:10Z` | PR #250 exact-head Visibility gate-local review 4956221333 returned PASS on reviewed formalization head `65eff0186094f5bae5e4bdd5283a2a1491099041`; exact-head CI `32086692500` completed success. The reviewed evidence confirms the Visibility threshold, PIT 22 audited inputs with 21 PASS / 0 PARTIAL / 0 BLOCKED / 1 NOT_USED, minimum implementation gap count 0, S1-REMAINING-04 complete with reexecution_required=false, and all five strict hard prerequisites PASS/NONE. Separately authorized closeout decision `5322269014` approved this S1-VISIBILITY-only transition. No downstream gate, final S1, or S2 acceptance is implied. |
| `S1-REVISION-WINNER` | data | required | data_governance_owner_role | current-main revision/winner gate evidence | `source-002-revision-winner-gate-evidence-v1` | `5774ad13b89e72efb40f63c9b3f9fb5096621b1f0382e4f5d35c097c79b6fc5e` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `ONE_VALID_WINNER_PER_KEY` | `NEVER` | `BLOCKED` | `REVISION_WINNER_NOT_VERIFIED` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | PR #247 reviewed the IDFL mode-specific evidence PASS, but canonical closeout is blocked because `S1-MISSING-CORRECTION-CANCELLATION` remains a declared hard prerequisite and is still BLOCKED. |
| `S1-INCLUSION-EXCLUSION` | data | required | data_quality_owner_role | current-main inclusion/exclusion gate evidence | `source-002-inclusion-exclusion-gate-evidence-v1` | `b5ef85cf54b54751c8407c21c252074b67fe61d7f8833466a681176690c6b580` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 and Q2C | `REASONS_AND_COUNTS_RECONCILED` | `NEVER` | `PASS` | `NONE` | independent S1 reviewer | `github-review-4951647818` | `2026-08-17T12:37:08Z` | PR #247 exact-head review accepted the inclusion/exclusion evidence on `ac2ad97579c005c488701e4d3be22531a595ee5f`; CI `32018019710` succeeded. This bounded closeout changes only this row from BLOCKED/INCLUSION_POLICY_NOT_FROZEN to PASS/NONE. |
| `S1-MISSING-CORRECTION-CANCELLATION` | data | required | data_quality_owner_role | correction, missing-day, and cancellation policy | `MISSING_CORRECTION_CANCELLATION_REQUIRED` | `BLOCKED_NO_SOURCE_POLICY` | `NOT_APPLICABLE_FOR_THIS_GATE` | Q2A/I7 contract | `LATE_ENTRY_REVISION_VOID_RULES_PRESENT` | `NEVER` | `BLOCKED` | `REVISION_POLICY_NOT_FROZEN` | independent S1 reviewer | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | Delayed, corrected, and void records need authority; this row is the declared hard prerequisite preventing Revision Winner closeout. |
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
CURRENT_REQUIRED_GATE_PASS_COUNT=10
CURRENT_REQUIRED_GATE_BLOCKED_COUNT=7
CURRENT_SOURCE_AUTHORITY_ACCEPTED=true
CURRENT_SOURCE_COHORT_ACCEPTED=true
CURRENT_Q2C_ACCEPTED=true
CURRENT_CANONICAL_Q2C_GATE_STATUS=PASS
CURRENT_REQUIRED_GATE_BLOCKED=true
CURRENT_ACCEPTANCE_RESULT=BLOCKED
CURRENT_S1_ACCEPTED=false
CURRENT_S2_AUTHORIZATION=false
VISIBILITY_ACCEPTED=true
```

The current package records ten closed gates. Canonical Grain and
Inclusion/Exclusion are now accepted through the reviewed Task-3 evidence and
this separately authorized bounded closeout. Visibility is accepted through
PR #250 exact-head gate-local review `4956221333`, reviewed formalization head
`65eff0186094f5bae5e4bdd5283a2a1491099041`, exact-head CI `32086692500`, and
closeout decision `5322269014`. This bounded closeout changes only
S1-VISIBILITY from BLOCKED/HISTORICAL_VISIBILITY_NOT_RECONSTRUCTABLE to
PASS/NONE. Revision Winner is not accepted: its reviewed IDFL evidence is
preserved, but `S1-MISSING-CORRECTION-CANCELLATION` remains a declared hard
prerequisite. This closeout does not execute `S1-REMAINING-04`, accept any
downstream gate, or imply final S1 acceptance. Source Cohort acceptance freezes
identity only; S2 still owns the final materialized rowset. All downstream and
unrelated gates remain fail-closed.

The JSON schema in this directory requires exactly these seventeen canonical
gate IDs once each. A required gate cannot be `NOT_APPLICABLE`; only a future
conditional gate outside this package could use that state after reviewed
evidence.
