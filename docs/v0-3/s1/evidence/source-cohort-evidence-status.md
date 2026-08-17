# Source Cohort Identity Evidence Status

## Current evidence state

    EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_COHORT_EVIDENCE
    EVIDENCE_RECORD_STATUS=ACCEPTED
    CURRENT_SOURCE_COHORT_FREEZE_STATUS=ACCEPTED
    SOURCE_COHORT_MANIFEST_STATUS=ACCEPTED
    SOURCE_COHORT_ID=source-002-s1-cohort-v1
    MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
    MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
    SOURCE_OBJECT_IDENTITY_HASHES=SOURCE_002_SHA256_FC83859871C544B584B3999B6796DDD518CDC8BB8DD9754F5B5C9D6AE62DB81A
    SOURCE_OBJECT_IDENTITY_HASHES_STATUS=ACCEPTED_MANIFEST_BOUND
    DECLARED_SOURCE_ROW_COUNT=233171
    DECLARED_SOURCE_BYTE_COUNT=28668416
    LOCAL_DAY_BOUNDARY=LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI
    KNOWN_EXCLUSIONS=NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE
    GOVERNED_SCOPE_IDENTITY_MANIFEST_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    GOVERNED_SCOPE_IDENTITY_MANIFEST_REFERENCE=source-002-mapping-and-scope-identity-v1
    GOVERNED_SCOPE_IDENTITY_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
    FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
    SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
    VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
    FARM_COUNT=84
    SUBFARM_COUNT=192
    VARIETY_COUNT=20
    INCLUSION_EXCLUSION_MANIFEST_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    INCLUSION_EXCLUSION_MANIFEST_REFERENCE=source-002-inclusion-exclusion-boundary-v1
    CUSTODY_RECORD_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
    MAPPED_SEASON_IDENTITIES=[2025~2026]
    MAPPED_CANONICAL_GROUP_COUNT=529
    UNMAPPED_ROW_COUNT=2
    UNMAPPED_DISTINCT_DATE_COUNT=1
    SOURCE_COHORT_MANIFEST_INDEPENDENT_REVIEW_STATUS=PASS

Current main contains the accepted final Source Cohort Manifest with its
version, cohort identity, manifest hash, concrete 84/192/20 scope arrays, and
aggregate coverage metadata. The manifest freezes the Source Cohort identity;
it does not issue or materialize the final clean rowset.

```text
SOURCE_COHORT_FACTS_RECONCILED=true
PACKAGE_A_FORMALIZATION_APPLIED=true
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=true
SOURCE_COHORT_MANIFEST_INDEPENDENTLY_ACCEPTED=true
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=true
CURRENT_CANONICAL_GATE_PASS_COUNT=7
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=10
STATUS_RECONCILIATION_APPLIED=true
PR241_INDEPENDENT_REVIEW_ID=4948013727
PR241_INDEPENDENT_REVIEWED_HEAD=b856d3823e51bb6e4f8b780363203a1c477677ca
PR241_EXACT_HEAD_CI_RUN_ID=31986614521
PR241_MERGE_SHA=5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b
FACT_LAYER_RECONCILED_FROM=docs/v0-3/s1/evidence/source-002-governed-snapshot-evidence.md
```

## S1/S2 boundary

    S1_FREEZES_SOURCE_COHORT_IDENTITY=true
    S1_FREEZES_FINAL_CLEAN_ROWSET=false
    S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
    SOURCE_ROW_COUNT_IS_DECLARED_SOURCE_METADATA=true
    SOURCE_ROW_COUNT_IS_NOT_S2_ACCEPTED_ROW_COUNT=true
    SOURCE_ROW_COUNT_DOES_NOT_FREEZE_FINAL_ROWSET=true

The reconciled counts and reviewed identity-package hashes remain aggregate
metadata, never an accepted S2 row count. The merged final manifest now contains
the concrete 84/192/20 arrays in Git and freezes the source-cohort identity; it
does not issue a final clean rowset identity or materialized rowset. S2 remains
unauthorized.

## Historical preparation gaps superseded by PR241

The following bullets describe the pre-PR241 preparation state and are retained
as historical provenance only; they are not current blockers after the merged
final manifest closeout:

- Governed cohort identity bound to a source attestation.
- Concrete scope arrays inside a schema-valid source-cohort manifest; the
  Package A reference intentionally stored counts and hashes only.
- Versioned mapping, visibility, inclusion, revision, and split policy
  identities.
- A versioned cohort manifest hash bound to the available source-object
  identity and aggregate scope evidence.
- Independent review of the resulting aggregate-only manifest.

## Historical post-PR241 pre-PR243/Q2C snapshot

`HISTORICAL_POST_PR241_PRE_LATER_ACCEPTANCE_SNAPSHOT=true`.
The values below are retained as historical provenance only; the current-main
refresh follows this section.

```text
POST_PR241_CURRENT_MAIN_REVALIDATION=PASS
PR241_MERGED=true
PR241_HEAD_SHA=b856d3823e51bb6e4f8b780363203a1c477677ca
PR241_MERGE_SHA=5caa63a20ee45b7e725b3c2c696a41cd3dd4a06b
PR241_INDEPENDENT_REVIEW_NUMERIC_ID=4948013727
PR241_INDEPENDENT_REVIEW_GRAPHQL_ID=PRR_kwDOS_gTTs8AAAABJuyynw
PR241_INDEPENDENT_REVIEW_SUBMITTED_AT=2026-08-17T02:25:52Z
PR241_INDEPENDENT_REVIEW_RESULT=PASS
PR241_EXACT_HEAD_CI_RUN_ID=31986614521
PR241_EXACT_HEAD_CI_CONCLUSION=success
MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
SOURCE_COHORT_ID=source-002-s1-cohort-v1
MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
FORMAL_SOURCE_COHORT_MANIFEST_CREATED=true
SOURCE_COHORT_MANIFEST_INDEPENDENTLY_ACCEPTED=true
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
S1_FREEZES_SOURCE_COHORT_IDENTITY=true
S1_FREEZES_FINAL_CLEAN_ROWSET=false
S2_OWNS_FINAL_MATERIALIZED_ROWSET=true
```

## Authority

    AUTHORITY_CONTRACT=docs/v0-3/s1/source-authority-and-cohort-manifest.md
    MANIFEST_SCHEMA=docs/v0-3/s1/schemas/source-cohort-manifest.schema.json

## HISTORICAL_PR199_PRE_LATER_ACCEPTANCE_SNAPSHOT: Task-3 preparation (2026-08-12)

This section records the Task-3 formalization candidate prepared from the
current-main governed evidence. It does not rewrite the historical
preparation state above and does not issue a final schema-valid cohort
manifest.

```text
TASK_ID=S1-REMAINING-03
TASK=FORMALIZE_SOURCE_COHORT_GRAIN_INCLUSION_AND_REVISION_ARTIFACTS
TASK_BASE_MAIN_SHA=b618e962b45844b037232befa9c0e066551996e9
TASK3_FORMALIZATION_PREPARED=true
MAPPING_POLICY_CANDIDATE_ISSUED=true
MAPPING_POLICY_VERSION=source-002-mapping-policy-v1
FORMAL_MAPPING_ACCEPTED=false
INCLUSION_POLICY_FORMALIZED=true
INCLUSION_POLICY_VERSION=source-002-inclusion-exclusion-boundary-v1
CANONICAL_GRAIN_FORMALIZED=true
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
IDFL_REVISION_WINNER_DISPOSITION_FORMALIZED=true
REVISION_POLICY_VERSION=source-002-idfl-revision-policy-v1
REVISION_WINNER_ALGORITHM=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
SOURCE_COHORT_MANIFEST_CANDIDATE_CREATED=true
SOURCE_COHORT_MANIFEST_CANDIDATE_REFERENCE=source-002-cohort-manifest-candidate-v1
FINAL_SOURCE_COHORT_MANIFEST_CREATED=false
FINAL_SOURCE_COHORT_MANIFEST_SCHEMA_READY=false
FINAL_SOURCE_COHORT_MANIFEST_CREATION_ALLOWED=false
SOURCE_COHORT_ACCEPTED=false
SOURCE_AUTHORITY_ACCEPTED=false
Q2C_ACCEPTED=false
S1_REMAINING_03_CANONICAL_CLOSURE=BLOCKED
S1_REMAINING_03_COMPLETE=false
INDEPENDENT_REVIEW_STATUS=NOT_STARTED
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
TEST_DATA_ACCESS=false
EXTERNAL_HOLDOUT_ACCESS=false
```

The candidate binds the current Source 002 identity, aggregate scope counts,
reviewed array hashes, approved July Option-A disposition, inclusion boundary,
canonical grain, IDFL revision/winner disposition, Q2C decision reference, and
custody record reference. Full farm/subfarm/variety arrays are not copied into
Git and no raw source was reopened.

The final manifest remains blocked by the unsigned/missing final source
attestation fields, unavailable concrete scope arrays and business date
bounds, and the later-task-owned visibility and split policy identities. The
candidate therefore uses null for unavailable values and is not a substitute
for `docs/v0-3/s1/evidence/source-cohort-manifest.json`.

## Task-3 artifact references

```text
DECISION_RECORD=source-002-cohort-grain-inclusion-revision-decision-v1
DECISION_RECORD_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
DECISION_RECORD_SHA256=1d737e1a6e2ce3cfaebf1d3449af86a51572d58333cdc1cdfe397a570084f955
DECISION_RECORD_DISPOSITION_COUNT=6
DECISION_RECORD_HASH_ALGORITHM=SHA256
DECISION_RECORD_HASH_SCOPE=FULL_RECORD_EXCLUDING_FIELD_decision_record_sha256
SOURCE_COHORT_MANIFEST_CANDIDATE=source-002-cohort-manifest-candidate-v1
MAPPING_EVIDENCE_REFERENCE=source-002-mapping-and-scope-identity-v1
INCLUSION_EVIDENCE_REFERENCE=source-002-inclusion-exclusion-boundary-v1
CUSTODY_RECORD_REFERENCE=source-002-custody-record-v1
```

The four source-cohort-related canonical runtime rows remain `BLOCKED` and no
canonical acceptance record was changed. This Task-3 status is preparation
evidence pending independent review, not gate acceptance.

## Current-main Task-3 formalization refresh

This is the authoritative current-main mirror for the present formalization
task. It supersedes the historical preparation values above without mutating
the reviewed PR #199 decision record.

```text
CURRENT_MAIN_TASK3_REFRESH_BASE_SHA=5e541dabeb66f8c569227ae9c769f2441aba210e
CURRENT_MAIN_TASK3_REFRESH_ISSUED=true
CANONICAL_GRAIN_GATE_EVIDENCE_PATH=docs/v0-3/s1/evidence/source-002-canonical-grain-mapping-gate-evidence.json
CANONICAL_GRAIN_GATE_EVIDENCE_VERSION=source-002-canonical-grain-mapping-gate-evidence-v1
CANONICAL_GRAIN_GATE_EVIDENCE_SHA256=6717ccd9d21aa3575f1ac66264d271c6371e55268633d786bcf7a29129b7fabc
INCLUSION_EXCLUSION_GATE_EVIDENCE_PATH=docs/v0-3/s1/evidence/source-002-inclusion-exclusion-gate-evidence.json
INCLUSION_EXCLUSION_GATE_EVIDENCE_VERSION=source-002-inclusion-exclusion-gate-evidence-v1
INCLUSION_EXCLUSION_GATE_EVIDENCE_SHA256=b5ef85cf54b54751c8407c21c252074b67fe61d7f8833466a681176690c6b580
REVISION_WINNER_GATE_EVIDENCE_PATH=docs/v0-3/s1/evidence/source-002-revision-winner-gate-evidence.json
REVISION_WINNER_GATE_EVIDENCE_VERSION=source-002-revision-winner-gate-evidence-v1
REVISION_WINNER_GATE_EVIDENCE_SHA256=5774ad13b89e72efb40f63c9b3f9fb5096621b1f0382e4f5d35c097c79b6fc5e
CURRENT_MAIN_FORMALIZATION_ISSUANCE_PATH=docs/v0-3/s1/evidence/source-002-grain-inclusion-revision-current-main-formalization-issuance.json
CURRENT_MAIN_FORMALIZATION_ISSUANCE_VERSION=source-002-grain-inclusion-revision-current-main-formalization-issuance-v1
CURRENT_MAIN_FORMALIZATION_ISSUANCE_SHA256=0ace453c549e95b3b1b6be29d0bdcd4904f00a5e27d6fee1d67028d5b2712c4c
PR199_REVIEW_ID=4912786743
PR199_REVIEW_RESULT=PASS
PR199_REVIEWED_HEAD_SHA=32fe6ce50cdd090df8eaeb0d92008e5748f168c5
TASK3_CURRENT_MAIN_FORMALIZATION_READY_FOR_INDEPENDENT_REVIEW=true
CANONICAL_GRAIN_FACT_THRESHOLD_SATISFIED=true
INCLUSION_EXCLUSION_FACT_THRESHOLD_SATISFIED=true
REVISION_WINNER_FACT_THRESHOLD_SATISFIED=true
S1-CANONICAL-GRAIN=BLOCKED
S1-CANONICAL-GRAIN_BLOCK_REASON=GRAIN_OR_DATE_AUTHORITY_MISSING
S1-INCLUSION-EXCLUSION=BLOCKED
S1-INCLUSION-EXCLUSION_BLOCK_REASON=INCLUSION_POLICY_NOT_FROZEN
S1-REVISION-WINNER=BLOCKED
S1-REVISION-WINNER_BLOCK_REASON=REVISION_WINNER_NOT_VERIFIED
S1_REMAINING_03_CANONICAL_CLOSURE=BLOCKED
S1_REMAINING_03_COMPLETE=false
INDEPENDENT_GATE_LOCAL_REVIEW_STATUS=NOT_STARTED
CANONICAL_GATE_LOCAL_CLOSEOUT_PERFORMED=false
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=true
CURRENT_CANONICAL_GATE_PASS_COUNT=7
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=10
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The three fact thresholds are satisfied for formalization purposes only. The
three canonical runtime rows remain blocked, and no accepted gate result is
claimed until the separately required independent gate-local reviews and
closeouts occur.
