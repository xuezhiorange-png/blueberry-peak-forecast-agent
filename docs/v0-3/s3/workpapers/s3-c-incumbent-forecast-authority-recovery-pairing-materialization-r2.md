# V0.3-S3-C incumbent forecast authority recovery and pairing materialization R2

## Execution identity

```text
TASK_ID=V0_3_S3_C_INCUMBENT_FORECAST_AUTHORITY_RECOVERY_AND_PAIRING_MATERIALIZATION_R2
BASE_MAIN_SHA=2d93c308ece8238dbca8c43650ac93f7815c3992
BRANCH=ops/v0-3-s3-c-incumbent-forecast-authority-recovery-pairing-materialization-r2
ALEMBIC_HEAD=c1d4e8f2a9b3
USER_EXECUTION_GATE=可以执行评分
FINAL_STOP_GATE=COORDINATOR_PAIRING_MATERIALIZATION_R2_REVIEW
```

This execution started from freshly fetched `origin/main`, which contains the
PR #577 merge commit `2d93c308ece8238dbca8c43650ac93f7815c3992`. It used one
new task-isolated PostgreSQL lifecycle. It did not use Docker, the local
default PostgreSQL endpoint, a historical volume, or a new per-layer diagnosis
branch. TEST remained sealed throughout.

## SOURCE-002 rebuild and live obtain

The existing controlled Lane A → Lane B → Lane C → Lane D functions were used
with the verified frozen SOURCE-002 object. The Lane D storage rebuild parity
check passed. The result was then read through the existing production
attestation and partition-byte obtain paths.

```text
SOURCE_002_RAW_OBJECT_IDENTITY=PASS
SOURCE_002_RAW_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_002_RAW_OBJECT_BYTE_COUNT=28668416
SOURCE_002_RAW_OBJECT_ROW_COUNT=233171
SOURCE_002_REBUILD_PERFORMED=true
SOURCE_002_REBUILD_PARITY=PASS
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_MATERIALIZED_ROW_COUNT=0
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
SOURCE_002_ATTESTED=true
TEST_REMAINS_SEALED=true
```

No alternate parser, alternate SOURCE-002 reader, synthetic rows, raw SQL
authority insert, or TEST reader was used.

## Replay identity landing

The required production function
`land_replay_identity_origin_into_sync_session(...)` landed the three replay
identity rows. The landed identity is metadata only; it does not contain daily
forecast values.

```text
INCUMBENT_REPLAY_IDENTITY_LANDING_PERFORMED=true
INCUMBENT_REPLAY_IDENTITY_ROW_COUNT=3
REVIEW_CUTOFF_AT=2026-02-16T00:00:00+08:00
MODEL_ID=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
QUANTILES=P50,P80,P90
REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256=76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3
FORECAST_ARTIFACT_CONTENT_IDENTITY_SHA256=7114b43a9de6b6c8a77e4297f235faab943030fe8feb8c78aae76fa24dd4706d
```

## PIT-visible authority resolution

The existing PIT-visible loader was called for the exact TRAIN/VALIDATION
materialization grain union. It returned 434 unavailable grains and zero
ambiguous grains. A read-only layer check showed that all 434 grains failed at
the first formal business-grain resolution step: no persisted Season, Farm,
Subfarm, or Variety master rows were available in the task-isolated database.
The subsequent formal production authority layers were also empty:

```text
MATERIALIZATION_GRAIN_COUNT=434
PIT_VISIBLE_PROVIDER_OBTAINED=false
PIT_VISIBLE_PROVIDER_UNAVAILABLE_GRAIN_COUNT=434
PIT_VISIBLE_PROVIDER_AMBIGUOUS_GRAIN_COUNT=0
FORMAL_BUSINESS_GRAIN_UNRESOLVED_COUNT=434
FORMAL_BUSINESS_GRAIN_RESOLVED_COUNT=0
TASK8_VISIBLE_FORECAST_GRAIN_COUNT=0
CORE_FORECAST_AUTHORITY_RESOLVED_GRAIN_COUNT=0
TASK10_BINDING_RESOLVED_GRAIN_COUNT=0
```

The existing `materialize_train_validation_pairing_inputs_live()` entrypoint
was called after SOURCE-002 attestation, official byte obtain, and replay
identity landing. It fail-closed with its production blocker
`NO_LAWFUL_INCUMBENT_DAILY_CURVE_PROVIDER`.

The first non-derivable authority is recorded more precisely for coordinator
review as:

```text
MATERIALIZATION_BLOCKER=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_AUTHORITY_UNAVAILABLE_FOR_434_GRAINS
FIRST_NON_DERIVABLE_SOURCE_AUTHORITY=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_BINDING
```

The frozen SOURCE-002 partition bytes provide text grain keys, but no formal
master-row IDs or authoritative master relationships. The current repository
contains no durable daily forecast values, and the current production
reconstruction path requires the formal master binding plus effective plans,
weather/base-temperature authority, Task 8 rows, Core rows, and Task 10
bindings. Existing repository evidence explicitly keeps plans/weather
unavailable and forbids inventing them. Therefore continuing would require
inventing business data; no lawful pairing package was emitted.

## Pairing result and boundaries

```text
TRAIN_PAIRING_PACKAGE_MATERIALIZED=false
VALIDATION_PAIRING_PACKAGE_MATERIALIZED=false
PAIRING_REPLAY_COUNT=0
PAIRING_REPLAY_STATUS=NOT_RUN_AFTER_NON_DERIVABLE_SOURCE_AUTHORITY
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

This is a controlled SOURCE-002 rebuild, replay-identity landing, and precise
pairing-materialization blocker record. It is not a pairing-package
publication, trusted-authority issuance, S3-C backtest, metric result, or TEST
evaluation.
