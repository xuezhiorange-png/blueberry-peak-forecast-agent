# V0.3-S3-C SOURCE-002 isolated rebuild and pairing materialization R1

## Execution identity

```text
ARTIFACT_ID=V0_3_S3_C_SOURCE_002_ISOLATED_REBUILD_AND_PAIRING_MATERIALIZATION_R1
TASK_ID=V0_3_S3_C_SOURCE_002_ISOLATED_REBUILD_AND_PAIRING_MATERIALIZATION_R1
TASK_CLASS=CONTROLLED_ISOLATED_SOURCE_002_REBUILD_AND_PAIRING_MATERIALIZATION
BASE_MAIN_SHA=76c9fb0b8b734bcc90907e1c631d25f4cf200e04
BRANCH=ops/v0-3-s3-c-source-002-isolated-rebuild-pairing-materialization-r1
ALEMBIC_HEAD=c1d4e8f2a9b3
USER_EXECUTION_GATE=可以执行评分
SOURCE_002_RAW_OBJECT_IDENTITY=PASS
SOURCE_002_REBUILD_PERFORMED=true
SOURCE_002_REBUILD_PARITY=PASS
SOURCE_002_ATTESTED=true
FINAL_STOP_GATE=COORDINATOR_PAIRING_MATERIALIZATION_REVIEW
```

This execution used a fresh task-isolated PostgreSQL 16 instance on a
non-default loopback port. It did not use Docker, a historical container or
volume, the local default PostgreSQL endpoint, or the PR #576 branch. The
repository was fetched from the current `origin/main` before the branch was
created, and the worktree remained clean before the execution.

The frozen SOURCE-002 object was found through the existing governed object
access already present on the host. The repository Lane-A verifier accepted it
using the frozen byte count, SHA-256, workbook schema, and declared source row
count. No alternate parser, alternate SOURCE-002 reader, TEST reader, or
synthetic source rows were used.

## SOURCE-002 rebuild

The existing controlled Lane-A → Lane-B → Lane-C → Lane-D path was called with
the verified object and the current Alembic head. The result was persisted in
the new database and immediately checked using the existing storage rebuild
parity function.

```text
SOURCE_002_RAW_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_002_RAW_OBJECT_BYTE_COUNT=28668416
SOURCE_002_RAW_OBJECT_ROW_COUNT=233171
SOURCE_002_E2_ROW_COUNT=233171
SOURCE_002_E3_KG_EQUAL=true
SOURCE_002_E3_CANONICAL_GRAIN_COUNT=33894
SOURCE_002_IDFL_SQL_ROW_COUNT=233171
SOURCE_002_TRAIN_ROW_COUNT=16224
SOURCE_002_VALIDATION_ROW_COUNT=8006
SOURCE_002_TEST_MATERIALIZED_ROW_COUNT=0
SOURCE_002_TEST_WINDOW_GRAINS_NOT_PERSISTED=9664
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
SOURCE_002_STORAGE_REBUILD_PARITY=PASS
VALIDATION_USED_AS_TRAINING_INPUT=false
TEST_REMAINS_SEALED=true
```

The official partition identity was then read back through the production
SOURCE-002 live path. Both canonical row-level attestation and content-byte
obtain passed without returning TEST payload.

```text
SOURCE_002_ROW_LEVEL_ATTESTATION_REASON=ATTESTED
SOURCE_002_OFFICIAL_PARTITION_BYTES_OBTAINED=true
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
TRAIN_BYTE_COUNT=9087071
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
VALIDATION_BYTE_COUNT=4484905
```

## Existing production pairing materialization attempt

The existing `materialize_train_validation_pairing_inputs_live()` production
entrypoint was called against the same isolated database lifecycle. It
successfully passed attestation and official TRAIN/VALIDATION bytes obtain,
then fail-closed while reading the incumbent forecast replay identity source.

```text
PAIRING_MATERIALIZATION_COMPLETED=false
MATERIALIZATION_BLOCKER=NO_LAWFUL_INCUMBENT_FORECAST_REPLAY_ROWS
INCUMBENT_FORECAST_REPLAY_IDENTITY_ENTRY_COUNT=0
TRAIN_PAIRING_PACKAGE_MATERIALIZED=false
TRAIN_PAIRING_PACKAGE_IDENTITY=NONE
TRAIN_PAIRING_PACKAGE_HASH=NONE
VALIDATION_PAIRING_PACKAGE_MATERIALIZED=false
VALIDATION_PAIRING_PACKAGE_IDENTITY=NONE
VALIDATION_PAIRING_PACKAGE_HASH=NONE
```

To cover the PIT provider boundary explicitly, the existing provider obtain
helper used by that entrypoint was also called read-only with the exact union
of TRAIN/VALIDATION materialization grains. It returned no provider because all
434 requested grains were unavailable in the fresh database. No forecast
values were synthesized, copied from a historical database, or inserted to
make the result pass.

```text
PIT_VISIBLE_PROVIDER_OBTAIN_ATTEMPTED=true
PIT_VISIBLE_PROVIDER_OBTAINED=false
PIT_VISIBLE_PROVIDER_UNAVAILABLE_GRAIN_COUNT=434
PIT_VISIBLE_PROVIDER_AMBIGUOUS_GRAIN_COUNT=0
```

The blocker is therefore an existing lawful-input absence, not a Docker or
PostgreSQL runtime failure. No candidate TRAIN/VALIDATION pairing package was
emitted. A second pairing replay was not run after the deterministic blocker;
there was no successful package to replay.

## Validation

The relevant existing SOURCE-002 and S3-B pairing/data-plane regression tests
passed after invoking them through the repository virtual environment:

```text
TARGETED_REGRESSION_RESULT=PASS (81 passed)
JSON_VALIDATION_RESULT=PASS
DIFF_CHECK_RESULT=PASS
```

The initial test invocation had nine nested-subprocess failures because the
shell PATH did not expose the repository virtual environment's `pytest`; the
same tests passed on the explicit virtual-environment rerun. No repository
production file or test file was changed.

## Hard boundaries

```text
PAIRING_PACKAGE_PUBLICATION_PERFORMED=false
AUTHORITY_ISSUANCE_PERFORMED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
MODEL_SEMANTICS_CHANGED=false
METRIC_SEMANTICS_CHANGED=false
MIGRATION_CHANGED=false
SCHEMA_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This is a controlled rebuild and blocker record, not a pairing-package
acceptance, authority issuance, legal backtest package, or metric result.
The next action is the coordinator stop-gate review.
