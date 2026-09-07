# S3-C historical PIT disposition and prospective forecast-authority retention R1

## Decision boundary

This workpaper records two deliberately separate outcomes:

1. The historical S3-C PIT backtest is terminally `NOT_COMPUTABLE` because the
   incumbent daily forecast authority was not durably retained.
2. A prospective production retention path is implemented so a future forecast
   can be replayed at its lawful cutoff without reconstructing mutable business
   inputs.

The first outcome is supported by the durable-source discovery recorded by PR
#579. It is not a request to retry the old database, recover Docker state, or
reconstruct the missing 434 historical daily forecast curves.

## Historical S3-C terminal state

~~~text
SOURCE_002_AVAILABLE=true
SOURCE_002_REBUILD_PARITY=PASS
SOURCE_002_ATTESTED=true
TRAIN_ACTUALS_AVAILABLE=true
VALIDATION_ACTUALS_AVAILABLE=true
INCUMBENT_REPLAY_IDENTITY_AVAILABLE=true
HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_AVAILABLE=false
DURABLE_SOURCE_DISCOVERY_PR=579
DURABLE_SOURCE_DISCOVERY_RESULT=NO_GOVERNED_HISTORICAL_INCUMBENT_FORECAST_AUTHORITY_SOURCE_AVAILABLE

S3_C_HISTORICAL_PIT_STATUS=NOT_COMPUTABLE
S3_C_HISTORICAL_PIT_REASON=HISTORICAL_INCUMBENT_DAILY_FORECAST_AUTHORITY_NOT_DURABLY_RETAINED
HISTORICAL_PIT_PASS=false
HISTORICAL_PIT_FAILURE=false
HISTORICAL_PIT_NOT_COMPUTABLE=true
HISTORICAL_PIT_BACKTEST_EXECUTED=false
HISTORICAL_PIT_FORECAST_VALUES_SYNTHESIZED=false
HISTORICAL_REPLAY_IDENTITY_REINTERPRETED_AS_FORECAST_VALUES=false
~~~

`NOT_COMPUTABLE` is a terminal result for this historical question. It is not
`PASS`, `FAIL`, or `BLOCKED` awaiting another implementation. The replay
identity remains metadata only; it is not a daily forecast-value source.

## Prospective retention owner

The new retention envelope consists of:

- `forecast_authority_capture`: one immutable capture for a completed
  production forecast;
- `forecast_authority_daily`: the complete persisted Task 8 daily P50/P80/P90
  curve and its cumulative/phenology fields;
- Alembic migration
  `0030_prospective_forecast_authority_retention` with database immutability
  guards;
- the production completion boundary
  `write_persisted_task10_authority_binding_and_capture`, which first delegates
  the Core↔Task 10 relation to the existing Task 10 writer and then appends the
  retention envelope;
- `load_pit_visible_forecast_authority`, which is the strict future PIT
  readback path.

The existing Core Forecast, Task 8, Task 9, and Task 10 objects remain owners of
their own business results. The envelope binds their exact IDs, hashes,
canonical snapshots, timestamps, and lineage in one immutable identity. It
does not run an estimator, read labels, access TEST, or create a parallel
forecast truth.

The capture contract freezes:

~~~text
APPEND_ONLY_OR_EQUIVALENT_IMMUTABLE=true
EXACT_REPLAYABLE=true
DETERMINISTIC_CANONICAL_HASH=true
SAME_REQUEST_EXACT_REPLAY_ZERO_WRITE=true
SAME_IDENTITY_SAME_CONTENT_ACCEPTED=true
CONFLICTING_REPLAY_REJECTED=true
POST_HOC_AUTHORITY_REWRITE_FORBIDDEN=true
DAILY_FORECAST_VALUES_DURABLY_RETAINED=true
FORECAST_CUTOFF_DURABLY_RETAINED=true
SOURCE_LINEAGE_DURABLY_RETAINED=true
~~~

The retained parent binds forecast identity/cutoff/availability, Core and code
authority, season/factory and canonical business-grain snapshot, exact plan
version/row hash and inputs, weather mapping/source/base-temperature identity,
Task 8 model/run/artifact/config and daily artifact hash, Task 9 run/result,
Task 10 training/prediction/binding identities, Core row hashes, and governance
identities. Daily rows retain the exact persisted values and per-row canonical
hashes.

## PIT readback fail-closed rules

Readback rejects a capture when any of the following is true:

- no matching production capture exists or more than one exists;
- the capture, owner timestamps, or any daily-row timestamp is after the
  requested cutoff;
- the parent canonical payload, parent hash, lineage hash, snapshot hash, or
  identity hash differs from its stored value;
- a daily row is missing, duplicated, non-contiguous, attached to another
  Task 8 run, or has a mismatched row/artifact hash;
- the retained quantile values are not finite, nonnegative, monotone, and at
  the existing database precision;
- required owner IDs, snapshots, or Task 10 prediction-row hashes are absent;
- a test, synthetic, or fixture marker appears in the authority payload.

No repair, latest-row fallback, post-cutoff filtering, or test-fixture
promotion is performed.

## Verification

The focused retention contract tests cover:

| Theme | Verification |
| --- | --- |
| A | Production capture entrypoint creates a durable production envelope |
| B | P50/P80/P90 daily values survive commit/readback exactly |
| C | Cutoff is retained and enforced |
| D | Master, plan, Task 8, Core, Task 9, and Task 10 identities share one capture |
| E | Canonical authority hash is deterministic |
| F | Exact replay returns zero writes |
| G | Conflicting replay is rejected |
| H | Post-hoc mutation is detected by readback |
| I | Missing authority fails closed |
| J | Ambiguous authority fails closed |
| K | Post-cutoff daily authority fails closed |
| L | Test-fixture authority cannot be promoted |
| M | PostgreSQL commit/session-boundary test is available as an opt-in integration profile |

The local contract suite passes with the PostgreSQL integration test skipped
when the integration profile is not enabled. The migration installs the
database-level update/delete guards for both retention tables; the loader also
recomputes all canonical relationships, so an out-of-band mutation is
detected even where a test database does not install the migration triggers.

## Governance boundary

~~~text
PROSPECTIVE_FORECAST_AUTHORITY_CAPTURE_IMPLEMENTED=true
PROSPECTIVE_FORECAST_AUTHORITY_CAPTURE_VERIFIED=true
HISTORICAL_PIT_BACKTEST_EXECUTED=false
HISTORICAL_PIT_FORECAST_VALUES_SYNTHESIZED=false
PAIRING_PACKAGE_PUBLICATION_PERFORMED=false
AUTHORITY_ISSUANCE_PERFORMED=false
S3_C_BACKTEST_EXECUTION_PERFORMED=false
S3_METRIC_EXECUTION_PERFORMED=false
S3_D_ATTRIBUTION_EXECUTION_PERFORMED=false
TEST_EVALUATION=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=true
SCHEMA_CHANGE=true
V0_3_S3_ENGINEERING_IMPLEMENTATION_COMPLETE=true
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_S3_NONCOMPUTABLE_AND_PROSPECTIVE_AUTHORITY_REVIEW
~~~

This is an engineering closeout candidate only. It does not independently set
`CURRENT_V0_3_S3_COMPLETE`, authorize S4, authorize a historical backtest, or
release V0.3.
