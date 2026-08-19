# V0.3-S1 Test Custody and Split Hash Record

## Formalization identity

    ARTIFACT_ID=V0_3_S1_TEST_CUSTODY_AND_SPLIT_HASH_RECORD
    ARTIFACT_VERSION=v0-3-s1-test-custody-and-split-hash-record-v1
    ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    TASK_ID=S1_SPLIT_POLICY_MANIFEST_AND_TEST_CUSTODY_FORMALIZATION_R2
    AUTHORIZATION_COMMENT_ID=5338348772

This record binds the TEST logical membership identity to the split manifest
identity and to the existing non-sensitive custody record. It records no TEST
rows and does not grant access.

## Source and custody identity

    SOURCE_COHORT_ID=source-002-s1-cohort-v1
    SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
    SOURCE_COHORT_MANIFEST_SHA256=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
    SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
    SOURCE_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
    SOURCE_SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
    SOURCE_OWNER_ATTESTATION_SHA256=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
    SOURCE_OWNER_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1

    SOURCE_CUSTODY_RECORD_VERSION=source-002-custody-record-v1
    SOURCE_CUSTODY_RECORD_SHA256=99edffb9d076e9ab938a9021e1950a7d909dd7303e6d4677a46a5c1b8db8dde6
    SOURCE_EXTERNAL_OBJECT_BINDING_SHA256=1d64cc5e4e1e06fb40065e3e8a0dfc3da56d20afb04300db4c5c58d5c5243ece
    SOURCE_CUSTODY_RECORD_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
    SOURCE_CUSTODY_RECORD_ACCEPTED=false
    TEST_CUSTODY_RECORD_ACCEPTED=false

The bound custody record is an existing governed identity. This task does
not accept or mutate it. The external object binding is a hash identity and
not a storage locator.

## TEST logical membership

    TEST_PARTITION_NAME=TEST
    TEST_PURPOSE=SEALED_FINAL_EVALUATION_ONLY
    TEST_START_DATE=2026-03-10
    TEST_END_DATE=2026-04-16
    TEST_INTERVAL_START=2026-03-10
    TEST_INTERVAL_END=2026-04-16
    TEST_BOUNDARIES=BOTH_ENDS_INCLUSIVE
    TEST_LOGICAL_ROWSET_ID=source-002-s1-cohort-v1:TEST:2026-03-10..2026-04-16:HARVEST_BUSINESS_DATE:v0-3-s1-time-ordered-split-policy-v1
    TEST_LOGICAL_ROWSET_SHA256=fdee66cc86155f3f3d0a5084d621940d6f31a9d6f0f1b89849a8ed28f03555dd
    TEST_LOGICAL_ROWSET_HASH_REPLAY=PASS
    JSON_MARKDOWN_PARITY=true
    LOGICAL_ROWSET_IDENTITY_ONLY=true
    MATERIALIZED_ROWSET_CREATED=false
    MATERIALIZED_ROW_CONTENT_HASH=false
    ROW_COUNT_REQUIRED_FOR_S1=false

The TEST hash is computed only from the canonical logical identity payload
recorded in the companion split manifest. It does not attest to row count,
row contents, database identifiers, or query order.

## Split manifest binding

    SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
    SPLIT_MANIFEST_ARTIFACT_VERSION=v0-3-s1-time-ordered-split-manifest-v1
    SPLIT_MANIFEST_SHA256=9d659cf731eaec83d06011683e01aa6a4b48e0af829d0ae073b68ed0a852970b
    SPLIT_MANIFEST_HASH_REPLAY=PASS
    SPLIT_MANIFEST_HASH_IS_GOVERNANCE_IDENTITY=true
    SPLIT_MANIFEST_HASH_IS_MATERIALIZED_DATA_CONTENT_HASH=false

The JSON artifact uses the exact artifact version
v0-3-s1-time-ordered-split-manifest-v1; the uppercase field above preserves
the governance field label while the JSON value is authoritative. The hash
canonicalization is:

    CANONICALIZATION_VERSION=v0-3-s1-split-manifest-canonicalization-v1
    ENCODING=UTF-8
    ENSURE_ASCII=false
    JSON_KEYS=SORTED
    JSON_SEPARATORS=,:
    HASH_ALGORITHM=SHA-256
    HASH_HEX_CASE=LOWERCASE
    HASH_SCOPE=ALL_TOP_LEVEL_FIELDS_EXCEPT_SPLIT_MANIFEST_SHA256_AND_SPLIT_MANIFEST_HASH
    SERIALIZATION_IDENTITY=UTF-8 bytes of sorted-key compact JSON serialization

## TEST seal and access boundary

    TEST_IS_LATEST_TIME_INTERVAL=true
    TEST_MEMBERSHIP_IMMUTABLE_AFTER_SEAL=true
    TEST_SEALED_BEFORE_CANDIDATE_TUNING=true
    TEST_SEAL_IS_NOT_TEST_ACCESS_AUTHORIZATION=true
    TEST_ACCESS_AUTHORIZED=false
    TEST_DATA_ACCESS_AUTHORIZED=false
    TEST_DATA_ACCESS=false
    EXTERNAL_HOLDOUT_ACCESS=false
    REQUESTED_HORIZONS_DAYS=(7,14,21)

The seal protects membership from candidate-tuning changes. It is not a
permission to open, query, materialize, or evaluate TEST data. External
holdout access remains separately unauthorized and unperformed.

## Validation and data safety

    TEST_LOGICAL_ROWSET_HASH_REPLAY=PASS
    SPLIT_MANIFEST_HASH_REPLAY=PASS
    CUSTODY_BINDING_REPLAY=PASS
    EXTERNAL_OBJECT_BINDING_REPLAY=PASS
    MATERIALIZED_CONTENT_HASH_CREATED=false

    SOURCE_002_RAW_READ=false
    SOURCE_002_ROW_LEVEL_READ=false
    TEST_DATA_ACCESS=false
    EXTERNAL_HOLDOUT_ACCESS=false
    TEST_ROWSET_MATERIALIZED=false
    TEST_ROW_CONTENT_HASH_CREATED=false
    CREDENTIALS_READ=false
    PRIVATE_LOCATOR_RECORDED=false

No raw Source002 content, row-level value, TEST data, external holdout, test
fixture, credential, or private locator was accessed or committed.

## Canonical gate and authorization boundary

    TARGET_GATE_ID=S1-SPLIT-POLICY
    TARGET_GATE_STATUS=BLOCKED
    TARGET_GATE_BLOCK_REASON=SPLIT_POLICY_NOT_FROZEN
    CANONICAL_GATE_COUNT=17
    CURRENT_CANONICAL_GATE_PASS_COUNT=14
    CURRENT_CANONICAL_GATE_BLOCKED_COUNT=3
    CANONICAL_CLOSEOUT_PERFORMED=false
    TEST_CUSTODY_ACCEPTANCE_AUTHORIZED=false

    INDEPENDENT_REVIEW_AUTHORIZED=false
    READY_AUTHORIZED=false
    MERGE_AUTHORIZED=false
    NEXT_GATE_AUTHORIZED=false
    V0_3_S1_COMPLETE=false
    V0_3_S1_ACCEPTED=false
    V0_3_S2_AUTHORIZED=false
    NO_STEP_IMPLIES_THE_NEXT=true

This record is issued for later independent review only. It does not freeze
the canonical gate as PASS, accept test custody, authorize holdout use,
start another gate, complete S1, or authorize V0.3-S2.
