# S4-C03 controlled validation execution — continuation R2

## Current status

This document records the current continuation on PR #591. The initial R1
attempt remains below as historical provenance, but it is not the current
execution result. The continuation recovered and independently verified the
exact SOURCE-002 binary, rebuilt the governed Lane A → Lane B → Lane C → Lane
D data plane, and established two task-isolated PostgreSQL databases. It then
stopped fail-closed before the first C03 `EVALUATION_STARTED` event because
the production maturity input authority required by the existing production
path is not durably available.

```text
TASK_ID=V0_3_S4_C03_CONTROLLED_VALIDATION_EXECUTION_CONTINUATION_R2
RESULT=BLOCKED_BEFORE_VALIDATION_START
BLOCK_REASON=C03_PRODUCTION_MATURITY_INPUT_AUTHORITY_UNAVAILABLE
FIRST_NON_DERIVABLE_AUTHORITY=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_BINDING
MATERIALIZATION_GRAIN_COUNT=434
C03_EXECUTION_PERFORMED=false
NEW_STARTED_EVENT_CREATED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
```

This is a source-authority stop, not a Docker, localhost:5432, or historical
volume recovery stop. No historical forecast values were synthesized, and no
TEST data was opened.

## Source-002 recovery and rebuild

The coordinator-provided object was fetched as the original Google Drive
binary, not as a Google Sheets export, converted workbook, CSV, or reconstructed
file:

```text
SOURCE_002_FILE_NAME=原果入库汇总表.xls
SOURCE_002_RECOVERY_CHANNEL=GOOGLE_DRIVE_PUBLIC_READ_ORIGINAL_BINARY
GOOGLE_DRIVE_FILE_ID=1L1WlljuU04dvkS8Owd8ekl9Vi1ZunlRa
SOURCE_002_OBSERVED_BYTE_COUNT=28668416
SOURCE_002_OBSERVED_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_002_RAW_OBJECT_IDENTITY=PASS
SOURCE_002_RAW_OBJECT_ROW_COUNT=233171
```

The repository-owned verifier passed in the execution environment. The
existing controlled materialization function was invoked with that verified
object and persisted the result into the task-isolated execution database:

```text
SOURCE_002_PIPELINE=LANE_A_TO_LANE_B_TO_LANE_C_TO_LANE_D
SOURCE_002_E2_ROW_COUNT=233171
SOURCE_002_E3_CANONICAL_GRAIN_COUNT=33894
SOURCE_002_E3_KG_EQUAL=true
SOURCE_002_IDFL_SQL_ROW_COUNT=233171
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_MATERIALIZED_ROW_COUNT=0
TEST_WINDOW_GRAINS_NOT_PERSISTED=9664
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
SOURCE_002_STORAGE_REBUILD_PARITY=PASS
```

The canonical row-level attestation was then executed against the rebuilt
execution database and passed:

```text
SOURCE_002_ATTESTED=true
SOURCE_002_ROW_LEVEL_READ=true
ATTESTATION_REASON_CODE=ATTESTED
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
TRAIN_BYTE_COUNT=9087071
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
VALIDATION_BYTE_COUNT=4484905
TEST_ROW_COUNT=0
TEST_PAYLOAD_OBTAINED=false
TEST_ACCESS_REQUESTED=false
```

The raw workbook and raw partition rows remain outside Git. No alternate
SOURCE-002 reader or synthetic row path was used.

## Controlled PostgreSQL authority

A native PostgreSQL 16.10 instance was created because the host had no usable
Docker runtime. It uses a task-specific data directory, loopback host, and
non-default port `55432`. Two separate databases run within that instance:

```text
POSTGRES_VERSION=16.10
HOST_CLASS=127.0.0.1_LOOPBACK
PORT=55432
TASK_ISOLATED=true
PERSISTENT_FOR_PR_LIFETIME=true
EPHEMERAL_PYTEST_DB=false
CI_DATABASE=false
DEFAULT_REPOSITORY_DB=false
S4_EXECUTION_DATABASE_CONFIGURED=true
S4_BUDGET_DATABASE_CONFIGURED=true
EXECUTION_DATABASE_NAME_SHA256=60723c1e489373d3d2ab0e7d045b9d9f7cf668f548d9f9d20c85c04f1b05250e
BUDGET_DATABASE_NAME_SHA256=9f1850883e7ab22ed36abef0a5f4d6b367eb9064de2849d214d84f9411696238
BINDING_FINGERPRINT_SHA256=d16d9a4be04bff602392dbbb7d509b8bffc0f7f34bcc2dd4786110b8fac09ccf
CONTROLLED_POSTGRES_AUTHORITY=PASS
```

Both databases were upgraded with the repository's current Alembic chain.
There is one head, `0032_s4_validation_budget_durable_persistence`. The budget
bootstrap was read back from PostgreSQL, not inferred from evidence or JSONL:

```text
AUTHORITY_KEY=V0_3_S4_VALIDATION_BUDGET
LEGACY_RECONCILED_VALIDATION_DEBIT=4
ACCEPTED_EVENT_COUNT=0
ACCEPTED_STARTED_COUNT=0
ACCEPTED_LAST_GLOBAL_EVALUATION_ORDINAL=0
EFFECTIVE_CONSUMED=4
REMAINING=28
FAKE_C01_STARTED_BACKFILL=false
BUDGET_READBACK_STATUS=PASS
```

No C01 rows were backfilled and no live validation budget was consumed.

## Authority discovery and stop boundary

The rebuilt S2 dataset is sufficient for SOURCE-002 actuals, but the existing
production maturity path requires formal business and model authority beyond
those actuals. Read-only discovery of the task-isolated execution database and
the durable repository evidence found no legal source for the first required
binding:

```text
MASTER_AUTHORITY_SOURCE_FOUND=false
PLAN_AUTHORITY_SOURCE_FOUND=false
WEATHER_INPUT_AUTHORITY_SOURCE_FOUND=false
TASK8_FORECAST_VALUE_SOURCE_FOUND=false
CORE_AUTHORITY_SOURCE_FOUND=false
TASK10_BINDING_SOURCE_FOUND=false
FORMAL_BUSINESS_GRAIN_RESOLVED_COUNT=0
TASK8_VISIBLE_FORECAST_GRAIN_COUNT=0
CORE_FORECAST_AUTHORITY_RESOLVED_GRAIN_COUNT=0
TASK10_BINDING_RESOLVED_GRAIN_COUNT=0
FIRST_NON_DERIVABLE_AUTHORITY=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_BINDING
```

The discovery was cross-checked against:

- `docs/v0-3/s3/evidence/s3-c-incumbent-forecast-durable-authority-source-recovery-r1.json`
- `docs/v0-3/s3/workpapers/s3-c-incumbent-forecast-durable-authority-source-recovery-r1.md`
- the existing production maturity resolver and persistence models

The repository's templates and test fixtures are not production authority.
The SOURCE-002 actual labels cannot be used to invent season/master/plan,
weather, Task8, Core, Task9, or Task10 facts. Therefore the required
production call chain cannot lawfully produce the 434 PIT-visible forecast
grains. The precise current blocker is:

```text
BLOCK_REASON=C03_PRODUCTION_MATURITY_INPUT_AUTHORITY_UNAVAILABLE
BLOCKER_DETAIL=NO_GOVERNED_FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_PLAN_WEATHER_BASE_TEMPERATURE_ANALYTICS_FACT_AUTHORITY
```

This boundary is before STARTED admission. Consequently no forecast horizon
identity or pairing identity was invented, and no scorer or metric was called.

## C03 parameter-effect preflight

The frozen C03 manifest itself was verified without executing a candidate. Its
configuration value reaches the production shift-model bound construction:

```text
C03_PARAMETER_EFFECT_REACHABLE=true
PRODUCTION_MATURITY_SHIFT_MODEL_PATH_USED=false
RUN_LOCAL_REPLAY_USED_AS_C03_SCORER=false
MANIFEST_HASH=cd2a50e3db6797ba6a81f32d2d3c510db51e202e755e00f3c5f1cdb85ca85825
RUN_1_VALUE=14
RUN_1_SHIFT_MODEL_BOUNDS=-14,+14
RUN_2_VALUE=18
RUN_2_SHIFT_MODEL_BOUNDS=-18,+18
RUN_3_VALUE=24
RUN_3_SHIFT_MODEL_BOUNDS=-24,+24
RUN_4_VALUE=28
RUN_4_SHIFT_MODEL_BOUNDS=-28,+28
```

This proves the frozen config-to-bound relationship only. It does not claim a
full maturity training/forecast execution, because the required authority
inputs are unavailable.

## Execution and sealed boundaries

The authorized values remained `14,18,24,28`, but the run loop never reached
the first durable event:

```text
C03_EXECUTION_AUTHORIZED=true
C03_EXECUTION_PERFORMED=false
RUN_1_STATUS=NOT_STARTED
RUN_2_STATUS=NOT_STARTED
RUN_3_STATUS=NOT_STARTED
RUN_4_STATUS=NOT_STARTED
NEW_STARTED_EVENT_ATTEMPTED=false
NEW_STARTED_EVENT_CREATED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
PAIRING_IDENTITIES_DERIVED=false
INCUMBENT_PAIRED_REFERENCE_EXECUTED=false
METRICS_COMPUTED=false
GUARDRAILS_COMPUTED=false
CANONICAL_STARTED_COUNT_BEFORE=0
CANONICAL_STARTED_COUNT_AFTER=0
EFFECTIVE_CONSUMED_BEFORE=4
EFFECTIVE_CONSUMED_AFTER=4
REMAINING_BEFORE=28
REMAINING_AFTER=28
```

No `run_local_replay`, C01 rerun, C02 execution, retry, TEST access, package
publication, model promotion, pilot, historical S3-C backtest, S3 metrics, or
S3-D attribution was performed. The historical S3-C NOT_COMPUTABLE boundary
is unchanged.

```text
TEST_ACCESS_REQUESTED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_C03_CONTROLLED_VALIDATION_EXECUTION_REVIEW_R2
```

## Historical R1 attempt (immutable provenance)

The previous blocked attempt is retained as historical provenance only. It
must not be read as the current R2 conclusion:

```text
INITIAL_ATTEMPT_RESULT=BLOCKED_BEFORE_VALIDATION_START
INITIAL_ATTEMPT_BLOCKER=SOURCE_002_FROZEN_OBJECT_UNAVAILABLE_FOR_CONTROLLED_EXECUTION
INITIAL_ATTEMPT_CI_RUN=34296368852
INITIAL_ATTEMPT_CI_HEAD_SHA=4557da46b988960534c61aa0535d35beb2b37607
INITIAL_ATTEMPT_CI_STATUS=SUCCESS
HISTORICAL_RECORD_ONLY=true
```

The current R2 evidence replaces those stale values as the live status. Its
final exact-head CI is recorded in the PR metadata and final review report
after the continuation commit is pushed; no old R1 CI is presented as the
current final CI.
