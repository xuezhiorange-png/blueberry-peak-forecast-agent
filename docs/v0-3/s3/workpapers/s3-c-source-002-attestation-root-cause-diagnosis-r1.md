# V0.3 S3-C SOURCE-002 attestation root-cause diagnosis R1

## Scope and authorization

```text
TASK_ID=V0_3_S3_C_SOURCE_002_ATTESTATION_ROOT_CAUSE_DIAGNOSIS_R1
TASK_CLASS=CONTROLLED_PRODUCTION_READ_ONLY_DIAGNOSIS
BASE_MAIN_SHA=7a4b61092ffb24a4faacaddc4b8ef9e7ebac5bef
PARENT_PR=573
PARENT_MERGE_COMMIT=7a4b61092ffb24a4faacaddc4b8ef9e7ebac5bef
BRANCH=diag/v0-3-s3-c-source-002-attestation-root-cause-diagnosis-r1
USER_GATE=可以
AUTHORIZATION_SCOPE=SOURCE_002_ATTESTATION_ROOT_CAUSE_DIAGNOSIS_ONLY
SOURCE_002_DIAGNOSIS_AUTHORIZED=true
SOURCE_002_RECOVERY_AUTHORIZED=false
SOURCE_002_REBUILD_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
DATABASE_MUTATION_AUTHORIZED=false
PAIRING_MATERIALIZATION_RERUN_AUTHORIZED=false
PAIRING_PACKAGE_PUBLICATION_AUTHORIZED=false
AUTHORITY_ISSUANCE_AUTHORIZED=false
TEST_ACCESS_AUTHORIZED=false
TEST_EVALUATION_AUTHORIZED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This record is a diagnosis only. It does not authorize SOURCE-002 recovery,
data reconstruction, pairing materialization, authority issuance, legal
backtest construction, metric execution, or TEST access.

## Historical boundary

PR #573 recorded the first and only materialization attempt as an aggregate
failure:

```text
PR573_RUN_1_COMPLETED=false
PR573_RUN_1_BLOCKER=SOURCE_002_ROW_LEVEL_READ_NOT_ATTESTED
PR573_SOURCE_002_ATTESTED=false
```

That historical fact is preserved; it is not overwritten by the more specific
diagnostic result below. PR #570's successful recovery was explicitly tied to
an isolated local PostgreSQL instance populated from frozen raw source:

```text
HISTORICAL_PR570_DATABASE_RECOVERY_MODE=ISOLATED_LOCAL_POSTGRES_FROM_FROZEN_RAW_SOURCE
CURRENT_DATABASE_PROVEN_SAME_AS_PR570_ISOLATED_DATABASE=UNKNOWN
```

Consequently, this diagnosis does not claim that SOURCE-002 was deleted, that
the current database lost SOURCE-002, or that the current binding is the PR
#570 database.

## Canonical attestation result

The only SOURCE-002 data-plane diagnostic call was the existing canonical
`attest_accepted_s2_train_val_source_002_row_level_read()` function. The full
pairing materialization function was not called, and no run 1/run 2 retry was
performed.

```text
DIAGNOSTIC_ATTESTATION_EXECUTED=true
ATTESTED=false
SOURCE_002_ROW_LEVEL_READ=false
OFFICIAL_HASHES_ATTESTED_FROM_A_LIVE_READ=false
SOURCE_002_ATTESTATION_REASON_CODE=FAIL_CLOSED_ASYNC_SESSION_UNREADABLE
DATASET_ID=NONE
DATASET_VERSION=NONE
MATERIALIZED_DATASET_IDENTITY_SHA256=NONE
TRAIN_ROW_COUNT=NONE
TRAIN_BYTE_COUNT=NONE
TRAIN_CONTENT_SHA256=NONE
VALIDATION_ROW_COUNT=NONE
VALIDATION_BYTE_COUNT=NONE
VALIDATION_CONTENT_SHA256=NONE
TEST_ROW_COUNT=NONE
TEST_REMAINS_SEALED=true
DIAGNOSTIC_ATTESTATION_AT=2026-09-07T08:23:06Z
```

Because session establishment failed before the accepted dataset could be
read, the official TRAIN/VALIDATION identities remain unobserved in this
diagnosis. The frozen official oracle is retained only as a comparison target:

```text
EXPECTED_DATASET_ID=source-002
EXPECTED_DATASET_VERSION=e5-live-v1
EXPECTED_MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
EXPECTED_TRAIN_ROW_COUNT=16224
EXPECTED_TRAIN_BYTE_COUNT=9087071
EXPECTED_TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
EXPECTED_VALIDATION_ROW_COUNT=8006
EXPECTED_VALIDATION_BYTE_COUNT=4484905
EXPECTED_VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
```

No raw TRAIN/VALIDATION rows, partition bytes, TEST bytes, or TEST payload were
returned or persisted.

## Read-only session diagnosis

The application-owned `AsyncSessionMaker` resolver was available. To
distinguish session construction from database reachability, one minimal
read-only `SELECT 1` probe was run through the existing
`run_live_source_002_sync_reader` seam. It failed with a sanitized `OSError`
classified as a loopback PostgreSQL endpoint being unreachable.

```text
CURRENT_DATABASE_BINDING_CLASS=LOCAL_POSTGRES
CURRENT_DATABASE_BINDING_FINGERPRINT=73c49c9cf07f4f457a5850f08e7c3ed9189f09eca22633cdb1c7c2826e6acca4
LIVE_ASYNC_SESSION_MAKER_AVAILABLE=true
DATABASE_CONNECTION_PROBE=FAIL
DATABASE_CONNECTION_PROBE_OPERATION=SELECT 1
DATABASE_CONNECTION_PROBE_EXCEPTION_TYPE=OSError
DATABASE_CONNECTION_PROBE_FAILURE_CLASS=LOOPBACK_POSTGRES_ENDPOINT_UNREACHABLE
FULL_DSN_RECORDED=false
CREDENTIALS_RECORDED=false
```

The binding fingerprint is a sanitized deterministic fingerprint of the
driver/host/port binding class; it is not a database-content identity. No
username, password, token, secret, full DSN, database dump, or filesystem
credential was recorded.

## Root-cause determination

```text
ROOT_CAUSE_CATEGORY=LIVE_DATABASE_SESSION_BINDING_FAILURE
ROOT_CAUSE_DETERMINATION=DETERMINED
SOURCE_002_RECOVERY_REQUIRED=UNKNOWN
PRODUCTION_CODE_FIX_REQUIRED=false
DATABASE_STATE_REPAIR_REQUIRED=UNKNOWN
IMPLEMENTATION_DEFECT_SUSPECTED=false
IMPLEMENTATION_DEFECT_PROVEN=false
```

The evidence determines why attestation did not pass at the current runtime
boundary: the configured application session maker could not reach its local
PostgreSQL endpoint. It does not determine whether the service is stopped,
whether the runtime has the wrong environment binding, or whether SOURCE-002
exists in an intended persistent database, because no database session was
established. Those remain coordinator-level hypotheses, not assertions.

## TEST and downstream boundaries

```text
TEST_ACCESS_PERFORMED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
PAIRING_MATERIALIZATION_RERUN_PERFORMED=false
DATABASE_MUTATION=false
SOURCE_002_RECOVERY_PERFORMED=false
TRAIN_PAIRING_PACKAGE_MATERIALIZED=false
VALIDATION_PAIRING_PACKAGE_MATERIALIZED=false
TRAIN_PAIRING_PACKAGE_PUBLISHED=false
VALIDATION_PAIRING_PACKAGE_PUBLISHED=false
AUTHORITY_ISSUANCE_PERFORMED=false
LEGAL_BACKTEST_PACKAGE_CURRENTLY_AVAILABLE=false
LIVE_LEGAL_BACKTEST_PACKAGE_CONSTRUCTED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
```

The existing attestation seal behavior returned `test_remains_sealed=true`.
No extra TEST read was made to confirm it.

## Repository validation and next gate

Only the two diagnosis documents and the append-only development-plan pointer
are in scope:

```text
EXPECTED_CHANGED_FILE_COUNT=3
CHANGED_PATH_EXACTNESS_RESULT=PASS
DEVELOPMENT_PLAN_FILE_TAIL_APPEND_ONLY=PASS
JSON_VALIDATION_RESULT=PASS
DIFF_CHECK_RESULT=PASS
```

The next gate is coordinator review of this root-cause diagnosis. It is not an
authorization for SOURCE-002 recovery, a materialization retry, or any
downstream S3-C execution.

```text
NEXT_GATE=COORDINATOR_SOURCE_002_ROOT_CAUSE_REVIEW
FINAL_STOP_GATE=COORDINATOR_SOURCE_002_ROOT_CAUSE_REVIEW
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
