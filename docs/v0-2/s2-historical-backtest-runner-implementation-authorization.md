# V0.2-S2 Historical Backtest Runner Implementation Authorization Brief

This document defines a future implementation boundary. It does not
self-authorize code, tests, schema, migration, synthetic execution, or
real-data execution.

```text
BRIEF_STATUS=PROPOSED_AWAITING_INDEPENDENT_REVIEW
BRIEF_MERGED=false
S2_RUNNER_IMPLEMENTATION_AUTHORIZED=false
BRANCH_FOR_IMPLEMENTATION_AUTHORIZED=false
WORKTREE_FOR_IMPLEMENTATION_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
TEST_CHANGE_AUTHORIZED=false
SCHEMA_CHANGE_AUTHORIZED=false
MIGRATION_CHANGE_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
AUTHORIZATION_BECOMES_EFFECTIVE_AUTOMATICALLY=false
CHARLES_EXPLICIT_IMPLEMENTATION_AUTHORIZATION_REQUIRED=true
NO_STEP_IMPLIES_THE_NEXT=true
```

## 1. Source authority and audit boundary

The source baseline is the merged `main` commit
`71d879a00ec38d5fcefb2910b5118e2ab8b5bcef`, the merge commit for PR #128.
The audit covers repository documents and current code structure at that
baseline. It does not inspect business rows, connect to a business system,
infer an owner, or create a positive attestation.

```text
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
ISSUE_NUMBER=102
SOURCE_MAIN_SHA=71d879a00ec38d5fcefb2910b5118e2ab8b5bcef
SOURCE_MAIN_MESSAGE=Merge pull request #128 from xuezhiorange-png/docs/v0-2-s2-scope-reconciliation
ISSUE102_STATE=OPEN
SOURCE_AUDIT_SCOPE=DOCUMENTS_AND_CURRENT_CODE_STRUCTURE_ONLY
DATABASE_ROWS_INSPECTED=false
REAL_DATA_OPENED=false
```

The highest-level version authority is `docs/v0-2/development-plan.md`:

```text
VERSION=0.2.0
VERSION_NAME=FORECAST_QUALITY_TRIAL
V0_2_TOTAL_SLICES=5
S1=ACTUAL_HARVEST_ATOMIC_COMMIT
S2=POINT_IN_TIME_ACTUAL_LABELS_AND_HISTORICAL_BACKTEST
S3=FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE
S4=FRONTEND_APPLICATION_API
S5=TWO_PAGE_RESPONSIVE_FRONTEND_AND_BROWSER_E2E
NO_ADDITIONAL_SLICE_WITHOUT_VERSION_REPLAN=true
```

The reconciliation document and Q2B-Q2F design records remain historical
design and governance evidence. They are not rewritten by this brief. The
development plan contains completion markers broader than the implementation
state found by this audit; that is a source-audit finding, not evidence that
S2 runner implementation or V0.2 release acceptance is complete.

## 2. Current implementation inventory

The following paths and symbols were found in the current source baseline.
Names not listed as current are deliberately treated as proposed future
symbols rather than asserted existing APIs.

### 2.1 Actual-label snapshot authority

`backend/app/actual_harvest_labels/service.py` contains the current
`create_label_snapshot` service and its source-evidence preflight, visibility
selection, revision winner computation, aggregation, deterministic hashing,
and caller-owned transaction behavior. Relevant helpers include
`_preflight_source_evidence`, `_preflight_record_evidence`,
`_compute_winners_and_exclusions`, `_effective_status_for_as_of`, and
`_flush_snapshot_phase`.

`backend/app/actual_harvest_labels/persistence.py` contains snapshot load and
integrity helpers, including `get_existing_snapshot_by_idempotency_key`. It
does not commit or roll back the caller transaction.

`backend/app/actual_harvest_labels/models.py` contains these current tables and
model classes:

```text
actual_harvest_label_snapshot=ActualHarvestLabelSnapshotModel
actual_harvest_label_snapshot_winner=ActualHarvestLabelSnapshotWinnerModel
actual_harvest_label_snapshot_label=ActualHarvestLabelSnapshotLabelModel
actual_harvest_label_snapshot_exclusion=ActualHarvestLabelSnapshotExclusionModel
```

`backend/app/actual_harvest_labels/hashes.py` contains current snapshot
request, instance, manifest, winner, label-row, exclusion, and snapshot hash
helpers. They reuse the rolling-backtest canonical JSON serializer and do not
use database identifiers as business hashes.

### 2.2 Forecast and Task 9 authority

`backend/app/models/core_forecast.py` contains current
`CoreForecastRunModel` and `CoreForecastDailyRowModel` persistence. The daily
row contains Task 8/9 references and forecast quantiles, including
`model_harvested_marketable_quantity_kg`; it is forecast authority, not an
actual label.

`backend/app/core_forecast/repository.py` contains current
`Task8DailyPredictionSource`, `Task8AuthoritySource`, `Task9MemberSource`,
`Task9AuthoritySource`, `CoreForecastRepository`,
`SqlAlchemyCoreForecastRepository`, `load_task8_authority`, and
`load_task9_authority` paths. These expose artifact, run, result, and member
evidence for an exact future adapter binding.

The current Task 9 persisted authority is represented by models in
`backend/app/models/task9_authority.py`, including
`Task9AuthorityLifecycleEvent`. No generic current symbol named
`Task9ForecastAuthorityBundle` was found.

### 2.3 Task 10 and rolling orchestration

`backend/app/rolling_backtest/replay_task10_binding.py` contains current
`ReplayTask9BindingContext`, `build_replay_task9_binding_context`,
`ReplayTask10BindingOutcome`, `validate_replay_task10_model_policy`, and
`evaluate_replay_task10_binding`. This is an existing Task 10 replay-binding
path, not a complete S2 forecast/label runner.

`backend/app/rolling_backtest/orchestration.py` contains current
`OrchestrationStage`, `NodeExecutionContext`, `ResolvedInputOutcome`,
`AvailabilityAuditOutcome`, `Task9AuthorityOutcome`, `Task10AuthorityOutcome`,
and `NodeOrchestrationOutcome`.

`backend/app/rolling_backtest/persistence.py` contains current
`create_or_load_logical_run`, `load_logical_run_with_integrity`,
`create_execution_attempt`, `finalize_attempt_status`,
`persist_stage_event`, `persist_orchestration_snapshot`, and
`finalize_attempt_with_snapshot`. These support rolling-backtest identity and
concurrency, but do not persist S2 comparison-ready binding rows,
coverage/exclusion manifests, or a dual-cutoff immutable backtest manifest.

`backend/app/models/rolling_backtest.py` contains current
`RollingBacktestRun`, `RollingBacktestNode`, `RollingBacktestAttempt`,
`RollingBacktestStageEvent`, `RollingBacktestOrchestrationSnapshot`,
`RollingBacktestResolvedInput`, `RollingBacktestAvailabilityAudit`, and
`RollingBacktestDagSnapshot` models. Reuse or adaptation must be decided by a
future implementation review; this brief does not treat them as a complete
S2 schema.

### 2.4 Canonical hashing, migrations, tests, and CI

`backend/app/rolling_backtest/canonical.py` contains current
`canonical_json_value`, `canonical_json_dumps`, and `sha256_payload` helpers.
The serializer sorts object keys, normalizes supported values, rejects native
float ambiguity, and applies explicit UTC handling for datetimes.

The current unique Alembic head is:

```text
ALEMBIC_HEAD=0022_finalized_at_lineage_basis_member
ALEMBIC_HEAD_COUNT=1
```

The relevant migration lineage is `0019_actual_harvest_validation_evidence`,
`0020_actual_harvest_commit_manifest`, `0021_actual_harvest_label_snapshot`,
and `0022_finalized_at_lineage_basis_member`. No migration is created here.

Current test ownership is split across actual-harvest import and label tests,
rolling-backtest contract/unit tests, PostgreSQL domain shards, concurrency
tests, and isolated Alembic tests. `.github/workflows/ci.yml` assigns the
PR-only jobs `static`, `unit-contract-golden`, `postgres-migration`,
`postgres-domain-1`, `postgres-domain-2`, `postgres-task11`,
`postgres-concurrency`, and `compose-smoke`. `full-suite-canary` is a
non-PR main-push job. This brief does not modify test ownership or workflow.

## 3. Three-stage gate model

These stages are independent. Passing an earlier stage does not grant the
next stage.

### 3.1 Implementation start eligibility

An independently authorized S2 runner implementation may begin with
repository-owned synthetic fixtures even while the following remain open:

- approved real `FARM_PICK` data;
- source owner or governed source authority;
- external business attestation;
- physical target equivalence;
- real-data coverage;
- S3 quantile metric semantics;
- forecast authority and historical code identity, until the runner implements
  and tests those bindings.

This is only an eligibility classification:

```text
IMPLEMENTATION_START_ELIGIBILITY=ELIGIBLE_AFTER_INDEPENDENT_AUTHORIZATION
S2_RUNNER_IMPLEMENTATION_AUTHORIZED=false
```

### 3.2 S2 technical acceptance

Before technical acceptance, a future implementation must close
`FORECAST_AUTHORITY_NOT_FULLY_BOUND` and
`HISTORICAL_CODE_IDENTITY_NOT_BOUND`, and must prove all deterministic
identity, persistence, transaction, concurrency, manifest, binding, and
synthetic end-to-end gates in Section 11.

```text
FORECAST_AUTHORITY_NOT_FULLY_BOUND=S2_RUNNER_IMPLEMENTATION_DELIVERABLE_AND_TECHNICAL_ACCEPTANCE_GATE
HISTORICAL_CODE_IDENTITY_NOT_BOUND=S2_RUNNER_IMPLEMENTATION_DELIVERABLE_AND_TECHNICAL_ACCEPTANCE_GATE
S2_IMPLEMENTATION_START_REQUIRES_THESE_GATES_PRE_CLOSED=false
S2_IMPLEMENTATION_ACCEPTANCE_REQUIRES_THESE_GATES_CLOSED=true
IMPLEMENTATION_TECHNICAL_ACCEPTANCE=BLOCKED_PENDING_S2_RUNNER_EVIDENCE
```

Synthetic engineering evidence cannot close real-data gates and cannot be
described as business or forecast-quality acceptance.

### 3.3 Real-data execution and release acceptance

The following remain blocked until separately supplied, reviewable evidence
exists and later gates are authorized:

- real-data historical backtest execution;
- forecast-quality conclusions or model comparison;
- V0.2 release acceptance;
- source-owner or business-attestation conclusions;
- physical-target equivalence conclusions;
- sufficient real coverage;
- S3 metric semantics and the one naive baseline.

```text
REAL_DATA_EXECUTION_AND_RELEASE_ACCEPTANCE=BLOCKED_PENDING_APPROVED_REAL_DATA_EVIDENCE
REAL_DATA_BACKTEST_AUTHORIZED=false
```

## 4. Future S2 implementation scope

If separately authorized, the next implementation round is limited to:

```text
BacktestRequest contract
BacktestRun identity
forecast_cutoff_at
label_observation_cutoff_at
label_visibility_mode
historical forecast authority bundle
forecast code identity
model identity
parameter identity
forecast data identity
Task 9 exact authority binding
Task 10 exact authority binding
I7 immutable label snapshot binding
forecast-label grain alignment
physical_alignment_status
7-day horizon binding rows
14-day horizon binding rows
21-day horizon binding rows
coverage manifest
exclusion manifest
immutable backtest manifest
deterministic request hash
deterministic instance hash
idempotent replay
evidence drift rejection
PostgreSQL persistence
transaction boundaries
concurrency acceptance
synthetic deterministic end-to-end fixture
```

S2 output is limited to comparison-ready forecast/actual binding rows,
coverage, exclusions, authority evidence, an immutable manifest, and explicit
blocked or not-computable states.

### 4.1 S3 exclusions

The future S2 runner must not calculate or publish:

```text
daily MAE
daily WAPE
daily sMAPE
daily MAPE
daily bias
daily relative bias
cumulative quality metrics
single-day peak quality metrics
sustained 7-day peak quality metrics
P80 coverage
P90 coverage
pinball loss
interval width
naive baseline
previous-model comparison
forecast-quality report
```

These belong to `S3=FORECAST_QUALITY_METRICS_AND_ONE_NAIVE_BASELINE`. P0
metrics listed in Issue #102 do not move them into S2.

## 5. Authority and fail-closed contract

The future runner must use exact, versioned authority and reject or classify
as blocked rather than substitute any of the following:

```text
LATEST_MODEL_FALLBACK
LATEST_PARAMETER_FALLBACK
LATEST_DATA_SNAPSHOT_FALLBACK
LATEST_LABEL_SNAPSHOT_FALLBACK
UNVERSIONED_AUTHORITY
RECEIPT_AS_ACTUAL_LABEL
ARRIVAL_AS_ACTUAL_LABEL
MODEL_OUTPUT_AS_ACTUAL_LABEL
ZERO_FILL_MISSING_ACTUAL
SYNTHETIC_PLACEHOLDER_AS_REAL_EVIDENCE
```

The actual-label physical contract remains:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
```

The runner must preserve two independent cutoffs:

```text
FORECAST_CUTOFF=forecast_cutoff_at
LABEL_CUTOFF=label_observation_cutoff_at
```

Forecast visibility and label visibility are independent. The revision winner
is selected using the label cutoff and visibility policy. A future revision
must not leak into an earlier evaluation. The manifest binds every selected
forecast, Task 9/10 authority, I7 label snapshot, source identity, and policy
identity. Missing or drifted authority is a structural failure, not a latest
value fallback.

## 6. Identity and hash contract

These are minimum future fields, not claims about a current concrete class.
Any new class or function must be marked `PROPOSED_NEW_SYMBOL` in the future
implementation review.

### 6.1 Request identity

The canonical request identity covers at least:

```text
season
farm
subfarm_or_plot
variety
requested_horizons
forecast_cutoff_at
label_observation_cutoff_at
label_visibility_mode
authority_selection_policy_version
```

It must not include a database auto-increment ID, creation time, process host,
attempt ID, query order, or run order.

### 6.2 Instance identity

The canonical instance identity covers at least:

```text
request_hash
exact_forecast_run_identity
code_identity
model_identity
parameter_identity
forecast_data_identity
task9_authority_identity
task10_authority_identity
label_snapshot_identity
actual_source_identity
manifest_schema_version
```

The implementation must define and test how each identity is loaded from
persisted evidence. No identity may use an unversioned or latest fallback.

### 6.3 Serialization

```text
HASH_ALGORITHM=SHA256
HASH_INPUT=CANONICAL_JSON
HASH_FIELD_ORDER=DETERMINISTIC
HASH_TIME_ENCODING=EXPLICIT_UTC_OR_FROZEN_DOMAIN_POLICY
HASH_NULL_POLICY=EXPLICIT
```

The existing `backend/app/rolling_backtest/canonical.py` serializer is the
audited reuse candidate. Hash parity tests must prove logical input parity and
must prove that authority, cutoff, policy, or selected-row drift changes the
correct hash.

## 7. Coverage and exclusion semantics

The runner must separate structural failure from ordinary coverage exclusion
and inability to compute:

```text
STRUCTURAL_FAILURE=authority or integrity contract is invalid
ORDINARY_EXCLUSION=record is valid but outside requested computable coverage
NOT_COMPUTABLE=required input or metric semantics are unavailable
NO_APPROVED_REAL_DATA=real-data execution is not approved or not supplied
```

Structural failures include missing authority identity, cutoff violation,
evidence drift, duplicate conflicting identity, manifest/hash mismatch,
indeterminate label grain, and future-information leakage.

Ordinary exclusions include no complete forecast rows for a requested horizon,
no label visible at the label cutoff, physical alignment not yet verified,
insufficient real coverage, and a revision outside the requested farm,
variety, or season.

An exclusion must never be silently deleted. It must appear in an exclusion
manifest with a machine-readable reason code, stable row identity, and
authority/cutoff context. Missing actual is unknown, not zero. No S3 quality
metric may be emitted merely because a binding row is excluded.

## 8. Persistence and migration decision

The current rolling-backtest schema supports orchestration, attempts, stage
evidence, resolved inputs, availability audits, and DAG snapshots. It does not
provide a dedicated S2 object set for a dual-cutoff request/run identity,
comparison-ready binding rows, coverage/exclusion evidence, authority
references, and an immutable final backtest manifest with the required
idempotency and concurrency semantics.

```text
PERSISTENCE_DECISION=NEW_SCHEMA_REQUIRED
SCHEMA_REQUIRED_FOR_FUTURE_IMPLEMENTATION=true
MIGRATION_REQUIRED_FOR_FUTURE_IMPLEMENTATION=true
CURRENT_ALEMBIC_PARENT=0022_finalized_at_lineage_basis_member
```

This is a future implementation review input only. No schema or migration is
authorized or created in this brief.

### 8.1 Proposed future object responsibilities

The following are `PROPOSED_NEW_SYMBOL` and `PROPOSED_NEW_SCHEMA_OBJECT`
descriptions, not current model claims:

| Proposed object | Responsibility | Required integrity |
| --- | --- | --- |
| `BacktestRequest` | Canonical request and dual-cutoff identity | SHA-256 request hash; explicit visibility mode; no DB ID in hash |
| `BacktestRun` | Immutable execution instance and status | request hash, instance hash, authority refs, blocked/not-computable status |
| `BacktestBindingRow` | One comparison-ready forecast/actual/horizon binding | stable grain, horizon, physical alignment status, source refs |
| `BacktestCoverageManifest` | Coverage counts and computability evidence | deterministic ordered rows and hash |
| `BacktestExclusionManifest` | Non-silent exclusions and blocked reasons | machine-readable reason code and stable identity |
| `BacktestAuthorityReference` | Task 9/10, forecast, label, code, data and policy refs | persisted hashes and drift checks |
| `BacktestManifest` | Immutable final evidence package | request/instance/authority/coverage/exclusion hashes |
| `BacktestIdempotencyKey` | Same-request replay lookup | unique source/request identity; conflict on different request |

### 8.2 Future migration requirements

If a future review approves the new-schema decision, it must propose a new
Alembic revision with parent `0022_finalized_at_lineage_basis_member`. That
review must specify upgrade creation, dependency-safe downgrade, an
upgrade/downgrade/upgrade round trip, PostgreSQL unique/FK/immutable-evidence
acceptance, rollback with no partial evidence, idempotency conflicts, and
foreign-key ownership. No future migration is approved here.

## 9. File allocation matrix

The matrix distinguishes audited current paths from proposed future paths.
Anything marked `PROPOSED_NEW_PATH` is not an existing module.

| Concern | Current canonical path | Current symbols/evidence | Future change kind | Proposed new path if any | Test ownership | Schema impact |
| --- | --- | --- | --- | --- | --- | --- |
| Application contract | `backend/app/rolling_backtest/schemas.py` | `RollingBacktestConfig`, `RollingNodeDefinition` | Add S2 contract | `backend/app/historical_backtest/contracts.py` (`PROPOSED_NEW_SYMBOL` `BacktestRequest`) | contract/golden | request/run |
| Domain identity | actual-label schemas and rolling schemas | snapshot request and rolling identity payloads | Add S2 identity contract | `backend/app/historical_backtest/identity.py` (`PROPOSED_NEW_PATH`) | identity tests | uniqueness |
| Canonical hashing | `backend/app/rolling_backtest/canonical.py`; actual-label hashes | `canonical_json_dumps`, `sha256_payload` | Reuse and compose | no new path unless review proves adapter needed | golden tests | hash columns |
| Forecast authority adapter | `backend/app/core_forecast/repository.py` | `load_task8_authority`, `load_task9_authority` | Add exact historical adapter | `backend/app/historical_backtest/forecast_authority.py` (`PROPOSED_NEW_PATH`) | authority tests | authority refs |
| Label snapshot adapter | actual-label service and persistence | `create_label_snapshot`, idempotency loader | Read immutable I7 snapshot | `backend/app/historical_backtest/label_authority.py` (`PROPOSED_NEW_PATH`) | I7 binding tests | label refs |
| Runner orchestration | `backend/app/rolling_backtest/orchestration.py` | `OrchestrationStage`, authority outcomes | Add S2 orchestration | `backend/app/historical_backtest/service.py` (`PROPOSED_NEW_PATH`) | synthetic E2E | run/binding |
| Persistence | `backend/app/rolling_backtest/persistence.py` | logical run and integrity persistence | Add S2 repository/finalization | `backend/app/historical_backtest/persistence.py` (`PROPOSED_NEW_PATH`) | PostgreSQL tests | new schema likely |
| API exposure | no approved S2 public endpoint found | existing internal/CLI paths only | Excluded; internal-only | none | no public API tests | none |
| Migration | `backend/alembic/versions/0022_finalized_at_lineage_basis_member.py` | current unique head | Future migration if approved | `backend/alembic/versions/0023_historical_backtest_runner.py` (`PROPOSED_NEW_PATH`) | Alembic/PG tests | new revision |
| Unit tests | actual-harvest and rolling-backtest test paths | current domain and canonical tests | Add S2 unit tests | `backend/tests/historical_backtest/test_contract.py` (`PROPOSED_NEW_PATH`) | unit-contract-golden | none |
| Contract/golden tests | existing rolling/core forecast contract tests | canonical and authority parity tests | Add S2 golden fixtures | `backend/tests/historical_backtest/test_identity_contract.py` (`PROPOSED_NEW_PATH`) | unit-contract-golden | none |
| PostgreSQL tests | actual-harvest lifecycle and rolling PG tests | persistence acceptance patterns | Add S2 persistence tests | `backend/tests/historical_backtest/test_persistence_postgres.py` (`PROPOSED_NEW_PATH`) | postgres-domain | new schema if approved |
| Concurrency tests | existing rolling-backtest concurrency ownership | race/idempotency patterns | Add S2 race tests | `backend/tests/historical_backtest/test_concurrency_postgres.py` (`PROPOSED_NEW_PATH`) | postgres-concurrency | unique constraints |
| Synthetic E2E | existing rolling-backtest integration fixtures | synthetic orchestration fixtures | Add S2 fixture | `backend/tests/historical_backtest/test_synthetic_e2e.py` (`PROPOSED_NEW_PATH`) | integration/domain | evidence rows |

## 10. Future implementation changed-file ceiling

Based on the audited ownership, a future implementation can be bounded without
touching frontend, model, parameter, maturity, weather, harvest equation,
Q2G, S3 metrics, dependency, or workflow files:

```text
IMPLEMENTATION_ALLOCATION_READY=true
FUTURE_CHANGED_FILE_CEILING=12
FUTURE_CHANGED_FILES_ARE_PROVISIONAL=true
```

The ceiling is a review bound, not authorization. It permits at most five
application/adapter/persistence paths under `backend/app/historical_backtest/`,
one model path, one Alembic revision only if separately approved, four S2 test
paths, and one existing focused path only if exact adapter reuse requires it.
The final implementation must stay below this ceiling or obtain a new review.
It must not spend the ceiling on unrelated refactors.

## 11. Future acceptance matrix

This matrix is a technical acceptance contract. No test in it was run in this
docs-only round.

| Gate | Test or evidence | Expected result | Failure class | Before technical acceptance | Before real-data acceptance |
| --- | --- | --- | --- | --- | --- |
| Canonical request hash stability | Repeat serialization and reorder construction | Same SHA-256 | structural | Required | Required |
| Instance hash stability | Replay same request and exact authority | Same instance hash | structural | Required | Required |
| Dual-cutoff leakage prevention | Change forecast and label visibility independently | Future evidence excluded | structural | Required | Required |
| Exact Task 9 binding | Compare persisted run/result/artifact identity | Exact authority only | structural | Required | Required |
| Exact Task 10 binding | Compare replay/model/parameter identity | Exact authority only | structural | Required | Required |
| Exact I7 binding | Compare immutable snapshot identity/hash/cutoff | Exact snapshot only | structural | Required | Required |
| No latest fallback | Remove requested version while newer exists | Blocked, no substitution | structural | Required | Required |
| Missing actual is unknown | Omit visible label row | Exclusion/not-computable, never zero | exclusion/not-computable | Required | Required |
| Future revision exclusion | Add revision after label cutoff | Not selected | exclusion | Required | Required |
| 7/14/21 determinism | Synthetic fixture creates horizon rows | Stable binding rows/hashes | structural | Required | Required |
| Idempotent replay | Repeat same request and evidence | No duplicate final evidence | structural | Required | Required |
| Same request/evidence | Repeat identical authority bundle | Same canonical result | structural | Required | Required |
| Evidence drift rejection | Change one authority hash | Deterministic rejection | structural | Required | Required |
| PostgreSQL persistence | Commit and reload all S2 evidence | Complete persisted evidence | structural | Required | Required |
| Duplicate/concurrent invocation | Independent sessions call same identity | One complete result or replay | structural | Required | Required |
| Transaction rollback | Fail after parent and child staging | No partial final evidence | structural | Required | Required |
| Migration round trip | Upgrade/catalog/downgrade/upgrade | Exact reversible schema | structural | If schema | If schema |
| Synthetic deterministic E2E | Revision, missing day, exclusion, drift fixture | Rows and manifests only | scope/structural | Required | Not sufficient |
| No S3 metric output | Inspect result and persistence payload | No metrics, baseline, or report | scope | Required | Required |
| No real-data claim | Missing approval and source evidence | Blocked, no quality conclusion | governance | Required | Required |

## 12. Synthetic fixture boundary

The future synthetic fixture is engineering evidence only:

```text
SYNTHETIC_FIXTURE_REPOSITORY_OWNED=true
SYNTHETIC_FIXTURE_USES_REAL_BUSINESS_DATA=false
SYNTHETIC_FIXTURE_DETERMINISTIC=true
SYNTHETIC_FIXTURE_HAS_FORECAST_CUTOFF=true
SYNTHETIC_FIXTURE_HAS_INDEPENDENT_LABEL_CUTOFF=true
SYNTHETIC_FIXTURE_HAS_REVISION=true
SYNTHETIC_FIXTURE_HAS_MISSING_DAY=true
SYNTHETIC_FIXTURE_HAS_ORDINARY_EXCLUSION=true
SYNTHETIC_FIXTURE_HAS_AUTHORITY_DRIFT_NEGATIVE_CASE=true
SYNTHETIC_FIXTURE_HAS_7_14_21_BINDING_ROWS=true
SYNTHETIC_FIXTURE_COMPUTES_S3_METRICS=false
```

```text
SYNTHETIC_ENGINEERING_ACCEPTANCE_DOES_NOT_IMPLY=
  BUSINESS_TARGET_EQUIVALENCE
  SOURCE_OWNER_APPROVAL
  EXTERNAL_ATTESTATION
  REAL_DATA_COVERAGE
  FORECAST_QUALITY
  REAL_DATA_BACKTEST_ACCEPTANCE
  RELEASE_ACCEPTANCE
```

The fixture must not use placeholder evidence as real evidence, create a
positive business attestation, or calculate an attestation hash.

## 13. Governance and next gate

This brief is forward-scoped only. It does not delete or rewrite the
historical Q2A-Q2F audit trail. Frozen identity, dual-cutoff, leakage,
missing-day, revision, actual-label, and fail-closed contracts remain valid.
This brief cannot bypass runner technical acceptance or real-data execution
and release gates. Q2G remains paused and no outbound request or source-owner
contact is allowed.

```text
BRIEF_AUTHORING_COMPLETE=true
BRIEF_REVIEW_REQUIRED=true
S2_RUNNER_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
SYNTHETIC_BACKTEST_EXECUTION_AUTHORIZED=false
REAL_DATA_BACKTEST_AUTHORIZED=false
DATA_IMPORT_AUTHORIZED=false
Q2G_A_STATUS=PAUSED
OUTBOUND_REQUEST_AUTHORIZED=false
NEXT_GATE=INDEPENDENT_AUTHORIZATION_BRIEF_REVIEW
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ISSUE102_CLOSE=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## 14. Round status

This round is docs-only. No implementation, test, schema, migration, workflow,
dependency, synthetic execution, real-data execution, database-row
inspection, data import, Q2G contact, Issue mutation, Ready, or Merge action
is performed.

```text
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
SCHEMA_CHANGED=false
MIGRATION_CHANGED=false
WORKFLOW_CHANGED=false
DEPENDENCY_CHANGED=false
BACKTEST_EXECUTED=false
SYNTHETIC_FIXTURE_EXECUTED=false
REAL_DATA_OPENED=false
DATA_IMPORTED=false
Q2G_RESUMED=false
OUTBOUND_CONTACT_PERFORMED=false
ISSUE102_MUTATED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
```
