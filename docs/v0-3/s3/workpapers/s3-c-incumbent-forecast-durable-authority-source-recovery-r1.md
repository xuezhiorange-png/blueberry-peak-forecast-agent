# V0.3-S3-C durable incumbent forecast authority source recovery R1

## Decision

This task performed a read-only, repository-and-governed-source discovery for
the historical incumbent forecast authority required by the 434 exact
TRAIN/VALIDATION materialization grains. No lawful durable source containing
the formal business binding and persisted daily forecast values was found.

The execution therefore stops fail-closed at:

```text
FIRST_NON_DERIVABLE_AUTHORITY=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_BINDING
MATERIALIZATION_BLOCKER=NO_GOVERNED_HISTORICAL_INCUMBENT_FORECAST_AUTHORITY_SOURCE_AVAILABLE
```

This is a source-authority conclusion, not a Docker, localhost PostgreSQL, or
SOURCE-002 conclusion. The previously accepted SOURCE-002 rebuild, attestation,
and replay-identity facts remain closed inputs and were not re-investigated.

## Execution identity and scope

```text
TASK_ID=V0_3_S3_C_INCUMBENT_FORECAST_DURABLE_AUTHORITY_SOURCE_RECOVERY_R1
BASE_MAIN_SHA=54ffc7d24b28e536fc4c8ee0bd3bf000ba42cf15
PR578_MERGE_IN_BASE=true
BRANCH=ops/v0-3-s3-c-incumbent-forecast-durable-authority-source-recovery-r1
DURABLE_AUTHORITY_DISCOVERY_PERFORMED=true
FINAL_STOP_GATE=COORDINATOR_DURABLE_AUTHORITY_SOURCE_RECOVERY_REVIEW
```

The branch was created from a freshly fetched `origin/main`, which contains
the required PR #578 merge commit `54ffc7d24b28e536fc4c8ee0bd3bf000ba42cf15`.
The old dirty checkout was not accessed for mutation. This task did not run
Docker, query the local default PostgreSQL endpoint, recover a historical
volume, re-locate SOURCE-002, access TEST, or alter production code.

## Closed upstream inputs

These values are carried from the accepted PR #578 controlled execution. They
are recorded as prior evidence, not as a new database probe in this task.

```text
SOURCE_002_RAW_OBJECT_IDENTITY=PASS
SOURCE_002_RAW_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_002_REBUILD_PARITY=PASS
SOURCE_002_ATTESTED=true
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_MATERIALIZED_ROW_COUNT=0
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
INCUMBENT_REPLAY_IDENTITY_ROW_COUNT=3
REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256=76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3
FORECAST_ARTIFACT_CONTENT_IDENTITY_SHA256=7114b43a9de6b6c8a77e4297f235faab943030fe8feb8c78aae76fa24dd4706d
MATERIALIZATION_GRAIN_COUNT=434
TEST_REMAINS_SEALED=true
```

The three-row replay identity is metadata identity only. The production
reader intentionally does not read forecast kg, quantity, daily-curve, or
forecast-value columns. A replay identity therefore cannot serve as the
missing daily forecast authority.

## Discovery method

The discovery covered the current `main` tree, reachable Git history and
reachable archive contents, the existing production authority/loaders, and
governed evidence paths referenced by the S3-A2/S3-C lineage. User-controlled
locations were searched read-only for a durable artifact, but no candidate was
accepted merely because its name or semantic description resembled a forecast
artifact.

The distinction used throughout was:

```text
EMPTY_DATABASE                         = an observation, not the final root cause
NO_DURABLE_AUTHORITY_SOURCE            = the final classification here
DURABLE_SOURCE_EXISTS_BUT_NOT_MATERIALIZED = not established
DURABLE_SOURCE_EXISTS_AND_CAN_BE_REBUILT   = not established
```

No row values, source labels, fixture values, timestamps, run IDs, or hashes
were fabricated during discovery.

## Authority-layer findings

### Formal master-data authority

```text
MASTER_AUTHORITY_SOURCE_FOUND=false
MASTER_AUTHORITY_SOURCE_KIND=PARTIAL_SOURCE_002_COHORT_AND_VARIETY_MAPPING_ONLY
MASTER_AUTHORITY_RECOVERY_PERFORMED=false
```

The SOURCE-002 cohort manifest at
`docs/v0-3/s1/evidence/source-002-final-source-cohort-manifest.json` provides
source cohort farm/subfarm coverage. The governed
`backend/app/s3_daily_rowset/source_002_variety_master_identity.py` provides a
source-variety-to-master-variety mapping. These are useful identity inputs,
but neither supplies the formal Season/Farm/Subfarm/Variety master rows and
relationships required by the PIT-visible loader.

`backend/app/models/master_data.py` and its migrations define the formal
schema, not a populated historical authority. The committed Farm-total group
mapping and area packages are Farm-total aggregation authority, not formal
master rows and not incumbent forecast values.

### Production-plan authority

```text
PLAN_AUTHORITY_SOURCE_FOUND=false
PLAN_AUTHORITY_SOURCE_KIND=NO_POPULATED_VERSIONED_PRODUCTION_PLAN_SOURCE
PLAN_AUTHORITY_RECOVERY_PERFORMED=false
```

`backend/app/models/production_plan.py` and
`backend/app/planning/plan_importer.py` describe runtime import/persistence
paths. `data/templates/production_plans.csv` is explicitly a template and is
not a historical plan authority. No populated, versioned, point-in-time
production-plan source or source-bound import artifact was found.

### Weather and base-temperature authority

```text
WEATHER_INPUT_AUTHORITY_SOURCE_FOUND=false
WEATHER_INPUT_AUTHORITY_SOURCE_KIND=NO_POPULATED_PIT_VISIBLE_WEATHER_OR_BASE_TEMPERATURE_SOURCE
WEATHER_INPUT_AUTHORITY_RECOVERY_PERFORMED=false
```

The weather models/import paths and the files under `data/templates/` provide
contracts/templates only. The existing S3-A2 evidence explicitly records
weather/plans as unavailable and forbids inventing them. No populated,
point-in-time weather or base-temperature authority was found.

### Task 8 forecast-value authority

```text
TASK8_FORECAST_VALUE_SOURCE_FOUND=false
TASK8_FORECAST_VALUE_SOURCE_KIND=NO_DURABLE_TASK8_DAILY_FORECAST_VALUE_PAYLOAD
TASK8_FORECAST_RECOVERY_PERFORMED=false
```

The PIT-visible production loader requires formal business-grain resolution,
one cutoff-visible `MaturityForecastRun`, and cutoff-visible
`MaturityDailyPredictionModel` rows. The repository contains the model,
service, and persistence contracts, but no populated historical Task 8 daily
forecast-value payload. The reachable S3-A2 evidence and default catalog
packages classify the available catalog as metadata/in-memory identity, not a
versioned repository artifact containing daily values.

The golden test payloads under `backend/tests/` are test fixtures and are not
lawful production authority. They were excluded from recovery and evidence.

### Core Forecast authority

```text
CORE_AUTHORITY_SOURCE_FOUND=false
CORE_AUTHORITY_SOURCE_KIND=NO_DURABLE_CORE_FORECAST_RUN_OR_DAILY_ROW_SOURCE
CORE_AUTHORITY_RECOVERY_PERFORMED=false
```

`backend/app/core_forecast/` and the Core persistence models define the
canonical resolver and storage contract. Git history contains no populated
historical Core run/daily-row payload or database export that can be loaded
through the production authority path.

### Task 10 binding authority

```text
TASK10_BINDING_SOURCE_FOUND=false
TASK10_BINDING_SOURCE_KIND=NO_DURABLE_TASK10_PERSISTED_BINDING_SOURCE
TASK10_BINDING_RECOVERY_PERFORMED=false
```

The production writer/resolver under
`backend/app/rolling_backtest/persisted_task10_authority_binding.py` and the
corresponding model provide validation logic only. No persisted historical
Task 10 binding source, exact Core reference, or daily authority payload was
found. Test golden files were excluded.

## Evidence and artifact review

The following durable repository evidence was reviewed as part of the source
classification:

- `docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-r1.json`
  records the absence of a lawful versioned incumbent forecast artifact.
- `docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-observation-r1.json`
  records the unavailable weather/plan inputs and the versioned-artifact
  closeout preconditions.
- `docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-for-reviewed-grains-r1.json`
  records that an in-memory catalog is not a versioned repository artifact.
- `docs/v0-3/s3/evidence/s3-a2-default-catalog-bindable-repository-r1.json`
  and the committed default catalog JSON files contain identity/metadata, not
  daily forecast values.
- `docs/v0-3/s3/evidence/s3-a2-evaluation-instance-registry-available-closeout-r1.json`
  records `evaluation_instance_registry_available=false` and
  `no_bindable_catalog_in_repository=true`.
- `docs/v0-3/s3/evidence/s3-c-incumbent-forecast-authority-recovery-pairing-materialization-r2.json`
  records the accepted 434-grain PIT failure and identifies the first
  non-derivable formal master binding.

Reachable Git history and archive contents were also checked for a SQL dump,
database backup, populated master/plan/weather export, Task 8 daily values,
Core rows, Task 10 bindings, or a versioned forecast artifact. None was found.
The only relevant committed data-like files are source/actual receipts,
templates, test fixtures, metadata catalogs, and Farm-total aggregation
authority; none can lawfully substitute for the missing historical incumbent
forecast source.

## PIT and pairing result

The following counts are carried from the accepted PR #578 same-lifecycle
materialization attempt. They are not represented as a new live execution in
this discovery task:

```text
FORMAL_BUSINESS_GRAIN_RESOLVED_COUNT=0
TASK8_VISIBLE_FORECAST_GRAIN_COUNT=0
CORE_FORECAST_AUTHORITY_RESOLVED_GRAIN_COUNT=0
TASK10_BINDING_RESOLVED_GRAIN_COUNT=0
PIT_VISIBLE_PROVIDER_OBTAINED=false
PIT_VISIBLE_PROVIDER_UNAVAILABLE_GRAIN_COUNT=434
PIT_VISIBLE_PROVIDER_AMBIGUOUS_GRAIN_COUNT=0
TRAIN_PAIRING_PACKAGE_MATERIALIZED=false
VALIDATION_PAIRING_PACKAGE_MATERIALIZED=false
TRAIN_PAIRING_PACKAGE_IDENTITY=NONE
TRAIN_PAIRING_PACKAGE_HASH=NONE
VALIDATION_PAIRING_PACKAGE_IDENTITY=NONE
VALIDATION_PAIRING_PACKAGE_HASH=NONE
PAIRING_REPLAY_COUNT=0
PAIRING_REPLAY_STATUS=NOT_RUN_AFTER_NON_DERIVABLE_SOURCE_AUTHORITY
```

There was no lawful source from which to perform master materialization,
historical Task 8/Core/Task 10 recovery, or a fresh PIT obtain in this task.
Consequently no pairing package was emitted and no replay was attempted.

## Final classification and boundaries

```text
FIRST_NON_DERIVABLE_AUTHORITY=FORMAL_SEASON_FARM_SUBFARM_VARIETY_MASTER_BINDING
MATERIALIZATION_BLOCKER=NO_GOVERNED_HISTORICAL_INCUMBENT_FORECAST_AUTHORITY_SOURCE_AVAILABLE
DATABASE_EMPTY_IS_NOT_FINAL_ROOT_CAUSE=true
CONTINUATION_WOULD_REQUIRE_INVENTING_BUSINESS_DATA=true
SOURCE_002_REINVESTIGATION_PERFORMED=false
```

```text
PAIRING_PACKAGE_PUBLICATION_PERFORMED=false
AUTHORITY_ISSUANCE_PERFORMED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
MODEL_SEMANTIC_CHANGE=false
METRIC_SEMANTIC_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This workpaper is a durable authority-source discovery and fail-closed stop
record. It is not a pairing-package publication, trusted-authority issuance,
S3-C backtest, S3 metric result, or TEST evaluation.
