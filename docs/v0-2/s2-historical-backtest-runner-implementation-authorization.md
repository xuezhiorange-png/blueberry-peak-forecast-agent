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
`RollingBacktestDagSnapshot` models. Their reuse and extension are frozen by
the `EXTEND_EXISTING_ROLLING_BACKTEST` architecture; this brief does not
treat them as a complete S2 schema.

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

### 2.5 Architecture decision and disposition

The audited current aggregate already owns rolling execution identity,
node identity, attempts, resolved inputs, availability audits, orchestration
snapshots, and DAG evidence. The future S2 runner therefore extends that
aggregate rather than creating a second historical-backtest aggregate.

```text
ARCHITECTURE_DECISION=EXTEND_EXISTING_ROLLING_BACKTEST
RUN_IDENTITY_OWNER=RollingBacktestRun
NODE_IDENTITY_OWNER=RollingBacktestNode
ATTEMPT_IDENTITY_OWNER=RollingBacktestAttempt
AUTHORITY_IDENTITY_OWNER=RollingBacktestResolvedInput_AND_EXISTING_TASK9_TASK10_ADAPTERS
IDEMPOTENCY_LEDGER_OWNER=RollingBacktestRun
SECOND_RUN_IDENTITY_AGGREGATE=FORBIDDEN
```

The request identity and S2 run state remain owned by
`RollingBacktestRun`. Existing nodes and attempts remain the execution
identity. Existing resolved-input and availability-audit rows remain the
authority and visibility evidence. The only new persistence is the minimum
S2 child evidence that the current aggregate cannot represent: comparison
binding rows and one immutable manifest containing canonical coverage,
exclusion, and authority-reference payloads.

There is no second `historical_backtest` aggregate. This prevents two run
hashes, two attempt ledgers, duplicate orchestration, or split idempotency.
Task 9 and Task 10 authority continues to be loaded through the audited
`core_forecast.repository` and `rolling_backtest.replay_task10_binding` paths,
then recorded through the existing resolved-input evidence and the S2
manifest. No current object is silently re-owned by a new aggregate.

| CURRENT_SYMBOL | CURRENT_PATH | DISPOSITION | FUTURE_OWNER | RATIONALE |
| --- | --- | --- | --- | --- |
| `RollingBacktestRun` | `backend/app/models/rolling_backtest.py` | `EXTEND_EXISTING` | `RollingBacktestRun` | Existing unique run identity owns the S2 request hash, dual cutoffs, visibility mode, and lifecycle. |
| `RollingBacktestNode` | `backend/app/models/rolling_backtest.py` | `EXTEND_EXISTING` | `RollingBacktestNode` | Existing node/as-of/forecast-cutoff identity remains the node owner; S2 binding rows attach to it. |
| `RollingBacktestAttempt` | `backend/app/models/rolling_backtest.py` | `REUSE_AS_IS` | `RollingBacktestAttempt` | Existing attempt fencing, retry, and status semantics must not be duplicated. |
| `RollingBacktestResolvedInput` | `backend/app/models/rolling_backtest.py` | `EXTEND_EXISTING` | `RollingBacktestResolvedInput` | Existing canonical resolved-input evidence is extended only for exact S2 authority references. |
| `RollingBacktestAvailabilityAudit` | `backend/app/models/rolling_backtest.py` | `EXTEND_EXISTING` | `RollingBacktestAvailabilityAudit` | Existing cutoff availability audit owns forecast/authority visibility evidence. |
| `RollingBacktestOrchestrationSnapshot` | `backend/app/models/rolling_backtest.py` | `EXTEND_EXISTING` | `RollingBacktestOrchestrationSnapshot` | Existing orchestration snapshot remains the execution audit owner. |
| `RollingBacktestDagSnapshot` | `backend/app/models/rolling_backtest.py` | `REUSE_AS_IS` | `RollingBacktestDagSnapshot` | Existing DAG identity is sufficient and must not be recreated. |
| `RollingBacktestConfig` | `backend/app/rolling_backtest/schemas.py` | `EXTEND_EXISTING` | `RollingBacktestConfig` | Existing config/hash path is extended with exact S2 cutoff, visibility, and horizon policy. |
| `RollingNodeDefinition` | `backend/app/rolling_backtest/schemas.py` | `EXTEND_EXISTING` | `RollingNodeDefinition` | Existing node definition remains the source of deterministic node/horizon construction. |
| `ResolvedUpstreamSemanticIdentity` | `backend/app/rolling_backtest/schemas.py` | `REUSE_AS_IS` | `RollingBacktestResolvedInput` | Existing semantic identity is reused as the upstream authority identity. |
| `HistoricalAvailableModelIdentity` | `backend/app/rolling_backtest/schemas.py` | `REUSE_AS_IS` | `RollingBacktestResolvedInput` | Existing historical model identity is already versioned and must not be shadowed. |
| `ReplayTrainedModelIdentity` | `backend/app/rolling_backtest/schemas.py` | `REUSE_AS_IS` | `RollingBacktestResolvedInput` | Existing Task 10 replay identity and policy checks remain authoritative. |

The separate historical-backtest aggregate alternative is not selected. If a
later implementation review proposes it, that would require a new
authorization brief explaining ownership, call direction, hash parity, and
idempotency migration before any code is changed.

### 2.6 Request, node, and cutoff cardinality

S2 uses the frozen singular-node model. One request creates exactly one
rolling node; the node inherits the run's label cutoff and carries the same
forecast cutoff. Multiple nodes are not an alternate interpretation of this
brief.

```text
S2_REQUEST_NODE_CARDINALITY=EXACTLY_ONE
ROLLING_BACKTEST_CONFIG_NODE_COUNT_FOR_S2=1
RUN_IDENTITY_OWNER=RollingBacktestRun
NODE_IDENTITY_OWNER=RollingBacktestNode
RUN_FORECAST_CUTOFF_DERIVED_FROM_SINGLE_NODE=true
RUN_FORECAST_CUTOFF_EQUALS_NODE_FORECAST_CUTOFF=true
LABEL_OBSERVATION_CUTOFF_CARDINALITY=ONE_PER_RUN
NODE_LABEL_OBSERVATION_CUTOFF_INHERITS_RUN=true
MULTI_NODE_S2_REQUEST_ALLOWED=false
MULTI_NODE_S2_REQUEST_REJECTION=STRUCTURAL_FAILURE
```

The request hash includes `single_node_identity_hash`,
`forecast_cutoff_at`, `label_observation_cutoff_at_or_null`,
`label_visibility_mode`, versioned business-key scope, sorted requested
horizons, and resolver/mapping/policy versions. There are no two independently
mutable forecast cutoffs.

```text
CANONICAL_FORECAST_CUTOFF_OWNER=RollingBacktestRun.BacktestRequest
ROLLING_NODE_FORECAST_CUTOFF_ROLE=MATERIALIZED_EXECUTION_PROJECTION
RUN_NODE_FORECAST_CUTOFF_EQUALITY_REQUIRED=true
INDEPENDENT_NODE_CUTOFF_MUTATION_ALLOWED=false
CANONICAL_LABEL_CUTOFF_OWNER=RollingBacktestRun.BacktestRequest
NODE_LABEL_CUTOFF_ROLE=INHERITED_BINDING_CONTEXT
```

The request payload and request hash are semantic authority. The node
`forecast_cutoff_at` is a materialized execution projection: node creation,
load, and replay must revalidate equality with the request cutoff. The node
label cutoff is inherited binding context, not a second owner. No cutoff may be
independently updated after request creation.

The future database/service acceptance must enforce:

```text
rolling_backtest_run.backtest_request_hash=UNIQUE
rolling_backtest_run.s2_node_count=1
rolling_backtest_node.forecast_cutoff_at=CANONICAL_REQUEST_CUTOFF
```

The enforcement may combine database constraints and service preflight, but
must be covered by PostgreSQL evidence. A future implementation must prove:

```text
EXACTLY_ONE_NODE_ACCEPTED=true
ZERO_NODE_REJECTED=true
MULTIPLE_NODES_REJECTED=true
RUN_NODE_FORECAST_CUTOFF_MISMATCH_REJECTED=true
RUN_LEVEL_LABEL_CUTOFF_PROPAGATES_TO_NODE_BINDING=true
REQUEST_HASH_CHANGES_WHEN_FORECAST_CUTOFF_CHANGES=true
REQUEST_HASH_CHANGES_WHEN_LABEL_CUTOFF_CHANGES=true
```

### 2.7 S2 compatibility discriminator

The exactly-one-node and dual-cutoff rules are conditional S2 rules. They must
not be retroactively applied to existing legacy rolling-backtest rows.

```text
S2_DISCRIMINATOR_FIELD=s2_contract_version_or_null
S2_CONTRACT_VERSION=v0.2-s2-historical-binding-v1
S2_DISCRIMINATOR_OWNER=RollingBacktestRun

s2_contract_version_or_null IS NULL=LEGACY_NON_S2_ROLLING_BACKTEST_RUN
s2_contract_version_or_null = v0.2-s2-historical-binding-v1=S2_HISTORICAL_BINDING_RUN

ROLLING_BACKTEST_LEGACY_MULTI_NODE_REMAINS_VALID=true
LEGACY_ROWS_RECLASSIFIED_AS_S2=false
LEGACY_ROWS_REQUIRE_S2_BACKFILL=false
S2_EXACTLY_ONE_NODE_CONSTRAINT_IS_CONDITIONAL=true
S2_DUAL_CUTOFF_CONSTRAINTS_ARE_CONDITIONAL=true
S2_REQUIRED_COLUMNS_ARE_CONDITIONAL=true
```

The existing `execution_mode=historical_observed` and
`execution_mode=retrospective_replay` values are not S2 discriminators. They
belong to the existing rolling contract and cannot be treated as the S2
contract version. A null discriminator preserves legacy multi-node behavior;
the exact S2 contract version activates the conditional S2 preflight,
constraints, and acceptance gates.

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

The canonical scope is a versioned list of resolved business keys, not database
numeric identifiers or display names. The field types and invariants are:

```text
CANONICAL_SCOPE_IDENTITY=VERSIONED_BUSINESS_KEY_LISTS
season_business_keys=list[str], sorted unique, non-empty
farm_business_keys=list[str], sorted unique, non-empty
subfarm_business_keys=list[str], sorted unique, non-empty
variety_business_keys=list[str], sorted unique, non-empty
requested_horizons_days=list[int], sorted unique, non-empty
single_node_identity_hash=64_HEX_SHA256
forecast_cutoff_at=RFC3339_DATETIME_WITH_EXPLICIT_UTC
label_observation_cutoff_at_or_null=RFC3339_DATETIME_WITH_EXPLICIT_UTC_OR_NULL
label_visibility_mode=AS_OF_EVALUATION|FINAL_ADJUDICATED
master_identity_resolver_version=non-empty_version_string
resolved_identity_snapshot_hash=64_HEX_SHA256
mapping_policy_version=non-empty_version_string
authority_selection_policy_version=non-empty_version_string

DATABASE_NUMERIC_IDS_ARE_LOOKUP_REFERENCES_ONLY=true
DATABASE_NUMERIC_IDS_INCLUDED_IN_REQUEST_HASH=false
MASTER_IDENTITY_RESOLVER_VERSION_REQUIRED=true
RESOLVED_IDENTITY_SNAPSHOT_HASH_REQUIRED=true
MAPPING_POLICY_VERSION_REQUIRED=true
```

`subfarm_business_keys` is not an alias for plot. Plot grain is not silently
introduced by the request contract; it requires an independently accepted
grain contract and explicit mapping evidence.

```text
ALLOWED_HORIZONS_DAYS=7,14,21
HORIZONS_SORTED_UNIQUE=true
EMPTY_HORIZONS_ALLOWED=false
OTHER_HORIZONS_ALLOWED=false
UNSORTED_OR_DUPLICATE_HORIZONS_REJECTED=true

ALLOWED_LABEL_VISIBILITY_MODES=AS_OF_EVALUATION,FINAL_ADJUDICATED
AS_OF_EVALUATION_REQUIRES_LABEL_OBSERVATION_CUTOFF=true
FINAL_ADJUDICATED_REQUIRES_NULL_LABEL_OBSERVATION_CUTOFF=true
```

Both current I7 visibility modes may be used by S2, but each cutoff invariant
is mandatory. A malformed combination is a structural failure. A request
hash must include the canonical business-key lists, resolver and mapping
versions, resolved identity snapshot hash, sorted horizons, both cutoff
values, visibility mode, and authority policy version. It must not include a
database auto-increment ID, creation time, process host, attempt ID, query
order, or run order.

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

### 8.1 Minimum non-reusable schema allocation

The following allocation is the minimum schema that cannot be represented by
the current rolling objects without losing S2 evidence. The owner remains the
existing rolling aggregate model path; no `historical_backtest.py` aggregate
is introduced.

| OBJECT_NAME | TABLE_OR_EMBEDDED_PAYLOAD | OWNER_MODEL_PATH | PRIMARY_KEY_ROLE | CANONICAL_IDENTITY | UNIQUE_CONSTRAINT | FOREIGN_KEYS | IMMUTABILITY_POLICY | WHY_EXISTING_SCHEMA_IS_INSUFFICIENT |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `BacktestRequest` (`PROPOSED_NEW_SYMBOL`) | Embedded request payload plus explicit columns on `rolling_backtest_run` | `backend/app/models/rolling_backtest.py` | Existing `rolling_backtest_run.id` owns the request/run row | `backtest_request_hash` over versioned business keys, cutoffs, visibility, horizons, and policy versions | Existing `run_signature` plus proposed unique `uq_rolling_backtest_run_backtest_request_hash` | Existing run FKs; authority references are immutable hashes/payloads | Run identity is write-once after creation; drift is conflict | Current run config has no frozen S2 business-key scope, label cutoff/mode invariant, or resolved identity snapshot hash |
| `BacktestRun` (existing object extended) | Existing table `rolling_backtest_run` | `backend/app/models/rolling_backtest.py` | `rolling_backtest_run.id` | Existing run signature plus S2 request/instance hashes | Existing run signature; proposed unique instance hash within the run identity | Existing season and authority FKs | Existing lifecycle integrity; final identity cannot be rewritten | Current run has generic orchestration identity but no S2 instance fields binding I7 and all forecast authority identities |
| `BacktestBindingRow` (`PROPOSED_NEW_SYMBOL`) | New table `rolling_backtest_binding_row` | `backend/app/models/rolling_backtest.py` | Surrogate row ID is lookup-only | `binding_row_hash` over run/node/business grain/horizon/forecast/label authority refs | Proposed `uq_rolling_backtest_binding_row_run_key` on `(rolling_run_id, binding_key_hash)` | `rolling_run_id -> rolling_backtest_run.id`; `rolling_node_id -> rolling_backtest_node.id` | Rows are append-only before manifest seal and immutable after seal | Current node and resolved-input rows do not store comparison-ready forecast/actual values, physical alignment, or 7/14/21 binding hashes |
| `BacktestManifest` (`PROPOSED_NEW_SYMBOL`) | New one-to-one table `rolling_backtest_manifest` | `backend/app/models/rolling_backtest.py` | `rolling_run_id` is the stable one-to-one key | `manifest_hash` over request, instance, authority, binding, coverage, and exclusion hashes | Proposed unique `rolling_run_id` and unique `manifest_hash` | `rolling_run_id -> rolling_backtest_run.id` | Seal once; `BEFORE UPDATE/DELETE` rejects sealed mutation | Current orchestration/DAG snapshots are phase evidence, not an immutable final S2 evidence package |
| `BacktestCoverageManifest` (`PROPOSED_NEW_SYMBOL`) | JSONB payload `coverage_manifest_payload` embedded in `rolling_backtest_manifest` | `backend/app/models/rolling_backtest.py` | Parent `rolling_run_id` | `coverage_manifest_hash` over ordered coverage entries | Hash uniqueness is parent-scoped through the manifest | Parent manifest FK | Covered by parent manifest seal | Separate table would duplicate a manifest ledger; current schema has no deterministic S2 coverage payload/hash |
| `BacktestExclusionManifest` (`PROPOSED_NEW_SYMBOL`) | JSONB payload `exclusion_manifest_payload` embedded in `rolling_backtest_manifest` | `backend/app/models/rolling_backtest.py` | Parent `rolling_run_id` | `exclusion_manifest_hash` over ordered machine-readable exclusions | Hash uniqueness is parent-scoped through the manifest | Parent manifest FK | Covered by parent manifest seal | Separate table would duplicate the manifest ledger; current availability audit cannot represent all S2 binding exclusions |
| `BacktestAuthorityReference` (`PROPOSED_NEW_SYMBOL`) | JSONB payload `authority_reference_payload` embedded in `rolling_backtest_manifest`, sourced from resolved-input rows | `backend/app/models/rolling_backtest.py` | Parent `rolling_run_id` | `authority_reference_hash` over exact Task 9/10, forecast, label, code, data, and policy refs | Hash uniqueness is parent-scoped through the manifest | Parent manifest FK; source rows remain existing FKs where available | Covered by parent manifest seal | Current resolved inputs are node evidence, not a final manifest-bound cross-authority set |
| `BacktestIdempotencyKey` (`PROPOSED_NEW_SYMBOL`) | No new table; `run_signature` and `backtest_request_hash` on `rolling_backtest_run` | `backend/app/models/rolling_backtest.py` | Existing run primary key | Same request hash and immutable evidence must resolve the same run | Existing unique run signature plus proposed request-hash unique constraint | Existing run FKs | Inherited from run identity | A separate ledger would duplicate existing run idempotency and create a second race owner |

### 8.2 Future migration requirements

If a future review approves the new-schema decision, it must extend
`backend/app/models/rolling_backtest.py` and propose one Alembic revision with
parent `0022_finalized_at_lineage_basis_member`. That revision may add only
the two new tables `rolling_backtest_binding_row` and
`rolling_backtest_manifest`, plus the approved S2 columns/constraints on
`rolling_backtest_run`; coverage, exclusions, and authority references remain
JSONB payloads in the manifest. The review must specify upgrade creation,
dependency-safe downgrade, an upgrade/downgrade/upgrade round trip,
PostgreSQL unique/FK/immutable-evidence acceptance, rollback with no partial
evidence, idempotency conflicts, and foreign-key ownership. No future
migration is approved here.

### 8.3 Legacy migration compatibility

Any future migration must preserve existing rolling-backtest rows and apply S2
requirements only when the discriminator is present:

```text
EXISTING_ROLLING_BACKTEST_ROWS_PRESERVED=true
NEW_S2_COLUMNS_NULLABLE_FOR_LEGACY_ROWS=true
S2_NOT_NULL_REQUIREMENTS_CONDITIONAL=true
S2_UNIQUE_CONSTRAINTS_PARTIAL_OR_CONDITIONALLY_ENFORCED=true
LEGACY_RUN_SIGNATURE_UNCHANGED=true
LEGACY_MULTI_NODE_CONFIG_UNCHANGED=true
S2_CONSTRAINT_CONDITION=s2_contract_version_or_null IS NOT NULL
```

No migration may force every historical `rolling_backtest_run` row to have
`s2_node_count=1`, a non-null `backtest_request_hash`, or a non-null
`label_visibility_mode`. Partial unique indexes, checks, and triggers must
use the S2 discriminator condition and must not collide with legacy rows.

## 9. File allocation matrix

The architecture decision makes the candidate path set finite and deduplicated.
Paths marked `REUSE_AS_IS` are audited current owners and are not candidate
changed paths. Paths marked `EXTEND_EXISTING` are already in the candidate
list. Any proposed new test or migration path below is an exact future path,
not an existing module claim.

```text
FUTURE_CANDIDATE_CHANGED_PATHS=
  backend/app/rolling_backtest/schemas.py
  backend/app/rolling_backtest/signatures.py
  backend/app/rolling_backtest/orchestration.py
  backend/app/rolling_backtest/persistence.py
  backend/app/models/rolling_backtest.py
  backend/alembic/versions/0023_historical_backtest_binding.py
  backend/tests/rolling_backtest/test_historical_backtest_contracts.py
  backend/tests/integration/test_rolling_backtest_historical_binding.py
  backend/tests/rolling_backtest/test_historical_backtest_concurrency.py
  backend/tests/test_historical_backtest_alembic.py
  ci-shard-manifest.yml
  .github/workflows/ci.yml
DECLARED_CHANGED_PATH_COUNT=12
FUTURE_CHANGED_FILE_CEILING=12
MATRIX_PATH_COUNT=12
COUNT_CONSISTENT=true
CI_OWNERSHIP_DECISION=EXPLICIT_NEW_TEST_OWNERSHIP
WORKFLOW_CHANGE_REQUIRED_FOR_FUTURE_IMPLEMENTATION=true
CI_SHARD_MANIFEST_CHANGE_REQUIRED_FOR_FUTURE_IMPLEMENTATION=true
```

| Concern | Current canonical path and symbols | Disposition | Future owner/path | Test ownership | Schema impact |
| --- | --- | --- | --- | --- | --- |
| Application contract | `backend/app/rolling_backtest/schemas.py`: `RollingBacktestConfig`, `RollingNodeDefinition` | `EXTEND_EXISTING` | same path; add S2 fields | `backend/tests/rolling_backtest/test_historical_backtest_contracts.py` | run columns/payload |
| Domain identity | `backend/app/rolling_backtest/schemas.py`, `signatures.py`, `config.py` | `EXTEND_EXISTING` | `schemas.py` and `signatures.py`; no identity module split | same contract test | request/instance hashes |
| Canonical hashing | `backend/app/rolling_backtest/canonical.py`: `canonical_json_dumps`, `sha256_payload` | `REUSE_AS_IS` | existing serializer; callers compose S2 payloads | existing canonical tests plus candidate contract test | hash values only |
| Forecast authority adapter | `backend/app/core_forecast/repository.py`: `load_task8_authority`, `load_task9_authority` | `REUSE_AS_IS` | existing repository, called by rolling orchestration | candidate contract and integration tests | authority payload refs |
| Task 10 authority adapter | `backend/app/rolling_backtest/replay_task10_binding.py`: `evaluate_replay_task10_binding` | `REUSE_AS_IS` | existing exact replay binding | candidate integration test | authority payload refs |
| Label snapshot adapter | `backend/app/actual_harvest_labels/service.py`, `persistence.py`: `create_label_snapshot`, idempotency loader | `REUSE_AS_IS` | existing immutable I7 snapshot loader | candidate integration test | label payload refs |
| Runner orchestration | `backend/app/rolling_backtest/orchestration.py`: `OrchestrationStage`, authority outcomes | `EXTEND_EXISTING` | same path; S2 flow remains in rolling aggregate | candidate integration test | run/binding/manifest |
| Persistence | `backend/app/rolling_backtest/persistence.py`: logical-run and attempt persistence | `EXTEND_EXISTING` | same path; add S2 finalization and child writes | candidate integration/PG test | new child tables |
| Model ownership | `backend/app/models/rolling_backtest.py`: all rolling ORM models | `EXTEND_EXISTING` | same path; extend run and add two minimal child models | candidate integration/PG test | new columns/tables |
| Migration | `backend/alembic/versions/0022_finalized_at_lineage_basis_member.py`: current head | `ADD_NEW` | `backend/alembic/versions/0023_historical_backtest_binding.py` (`PROPOSED_NEW_PATH`) | Alembic/PG portion of integration test | only if separately approved |
| Unit/contract/golden tests | `backend/tests/rolling_backtest/test_canonical.py`, `test_identity_parity.py`, `test_persistence_contracts.py` | `EXTEND_EXISTING` | `backend/tests/rolling_backtest/test_historical_backtest_contracts.py` | unit-contract-golden | none |
| PostgreSQL acceptance | `backend/tests/integration/test_rolling_backtest_persistence.py` and actual-harvest PG ownership | `ADD_NEW` | `backend/tests/integration/test_rolling_backtest_historical_binding.py` (`PROPOSED_NEW_PATH`) | postgres-domain | schema acceptance |
| Concurrency acceptance | existing rolling-backtest concurrency ownership | `ADD_NEW` | `backend/tests/rolling_backtest/test_historical_backtest_concurrency.py` (`PROPOSED_NEW_PATH`) | postgres-concurrency | unique/race behavior |
| Synthetic E2E | `backend/tests/integration/test_rolling_backtest_orchestration.py` fixtures | `ADD_NEW` | same candidate integration path, no separate fixture module | postgres-domain/integration | binding/manifest |
| API exposure | no approved S2 public endpoint found | `EXCLUDED` | none; internal evidence only | no public API test | none |

The candidate test paths have explicit CI ownership:

| TEST_PATH | PYTEST_MARKERS | PR_CI_OWNER_JOB | CURRENTLY_EXECUTED_BY_OWNER | REQUIRED_WORKFLOW_COMMAND_CHANGE | REQUIRED_SHARD_MANIFEST_PATH_CHANGE | REQUIRED_MARKERS | CANARY_ONLY |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/tests/rolling_backtest/test_historical_backtest_contracts.py` | `not integration and not postgres and not postgres_concurrency` | `unit-contract-golden` | Yes, repository-wide residual selector | NO | NO | residual marker selector | false |
| `backend/tests/integration/test_rolling_backtest_historical_binding.py` | `integration, postgres` | `postgres-domain-2` | No, future path | YES | YES | `integration`, `postgres` | false |
| `backend/tests/rolling_backtest/test_historical_backtest_concurrency.py` | `postgres_concurrency` | `postgres-concurrency` | No, future path | YES | YES | active `postgres_concurrency`; optional additive `concurrency` | false |
| `backend/tests/test_historical_backtest_alembic.py` | `migration` | `postgres-migration` | No, future path | YES | YES | `migration` | false |

The unit contract path is already executed by the repository-wide residual
selector. The other three paths require explicit additions to the corresponding
workflow command and `ci-shard-manifest.yml` ownership list. The additions are:

```text
WORKFLOW_COMMAND_PATH_ADDITIONS=
  backend/tests/integration/test_rolling_backtest_historical_binding.py
  backend/tests/rolling_backtest/test_historical_backtest_concurrency.py
  backend/tests/test_historical_backtest_alembic.py
WORKFLOW_COMMAND_PATH_ADDITION_COUNT=3
UNIT_CONTRACT_TEST_AUTO_DISCOVERED=true
DUPLICATE_PR_EXECUTION_ALLOWED=false
ALL_TECHNICAL_ACCEPTANCE_TESTS_HAVE_PR_CI_OWNER=true
CANARY_ONLY_TECHNICAL_ACCEPTANCE_TESTS=false
CI_SELECTOR_MODEL_MATCHES_CURRENT_WORKFLOW=true
SINGLE_EXECUTION_CONTRACT_PRESERVED=true
WORKFLOW_SCOPE_LIMIT=ADD_ONLY_THE_THREE_NON_UNIT_PATHS
JOB_COUNT_CHANGE_ALLOWED=false
TRIGGER_CHANGE_ALLOWED=false
DATABASE_ISOLATION_CHANGE_ALLOWED=false
SECURITY_RULE_CHANGE_ALLOWED=false
```

`ci-shard-manifest.yml` and `.github/workflows/ci.yml` must remain synchronized
in the future implementation. No workflow or manifest file is modified in
this docs-only round. No optional path exists outside the twelve-path set.

## 10. Future implementation changed-file ceiling

```text
REVIEW_BASELINE_IMPLEMENTATION_ALLOCATION_READY=false
ARCHITECTURE_RELATIONSHIP_FROZEN=true
CANDIDATE_PATHS_EXPLICIT=true
PATH_COUNT_AND_CEILING_MATHEMATICALLY_EQUAL=true
IMPLEMENTATION_ALLOCATION_READY=true
FUTURE_CHANGED_FILE_CEILING=12
FUTURE_CHANGED_FILES_ARE_PROVISIONAL=true
```

The ceiling is exactly the twelve paths in `FUTURE_CANDIDATE_CHANGED_PATHS`.
It includes the future migration path even though migration remains separately
unauthorized. It includes all candidate test paths and has no hidden optional
file. The future implementation must not touch frontend, model, parameter,
maturity, weather, harvest equation, Q2G, S3 metrics, dependency, or workflow
files, and must obtain a new review before exceeding the ceiling.

## 11. Future acceptance matrix

This matrix is a technical acceptance contract. No test in it was run in this
docs-only round.

| Gate | Test or evidence | Expected result | Failure class | Before technical acceptance | Before real-data acceptance |
| --- | --- | --- | --- | --- | --- |
| Legacy multi-node config remains valid | Load a pre-S2 multi-node config with null discriminator | Existing config validates unchanged | compatibility | Required | Required |
| Legacy multi-node run reloads unchanged | Reload a pre-S2 persisted run | No synthetic S2 fields or node rewrite required | compatibility | Required | Required |
| Legacy row requires no synthetic S2 backfill | Upgrade with legacy rows present | Legacy rows remain valid and unchanged | compatibility | Required if schema | Required if schema |
| Non-S2 null discriminator accepted | Persist/replay a null-discriminator run | Legacy rolling path accepted | compatibility | Required | Required |
| S2 exact contract version required | Use an unknown or missing S2 version on an S2 request | Structural rejection | structural | Required | Required |
| Exactly one node accepted | Submit one S2 node with matching run/node cutoff | Complete binding and manifest | structural | Required | Required |
| Zero node rejected | Submit a request with zero nodes | Structural rejection | structural | Required | Required |
| Multiple nodes rejected | Submit a request with two S2 nodes | Structural rejection; no partial run | structural | Required | Required |
| Run/node forecast cutoff match | Alter node cutoff independently from run request | Deterministic rejection | structural | Required | Required |
| Run label cutoff propagation | Persist one run cutoff and load its node binding | Node binding inherits the run cutoff | structural | Required | Required |
| S2 partial uniqueness avoids legacy collision | Insert legacy and S2 rows with overlapping legacy identities | Legacy row remains valid; S2 uniqueness applies conditionally | compatibility | Required if schema | Required if schema |
| Upgrade preserves legacy rows | Upgrade with pre-existing rolling data | All legacy rows remain reloadable | compatibility | Required if schema | Required if schema |
| Downgrade preserves pre-existing rolling data | Downgrade after S2 objects exist | Pre-existing rolling data remains intact | compatibility | Required if schema | Required if schema |
| Forecast cutoff request-hash sensitivity | Change only `forecast_cutoff_at` | Request hash changes | structural | Required | Required |
| Label cutoff request-hash sensitivity | Change only `label_observation_cutoff_at_or_null` | Request hash changes | structural | Required | Required |
| Business-key canonicalization | Same resolved business keys constructed with different database lookup IDs or input order | Same canonical scope and request hash | structural | Required | Required |
| Numeric ID lookup does not change request hash | Hold business keys constant while changing lookup IDs | Request hash unchanged | structural | Required | Required |
| Identity resolver version drift | Change resolver version or resolved identity snapshot hash | Instance identity changes and old evidence is not replayed | structural | Required | Required |
| Invalid visibility/cutoff combination | Use a non-null label cutoff for `FINAL_ADJUDICATED` or null cutoff for `AS_OF_EVALUATION` | Deterministic rejection | structural | Required | Required |
| Unsorted/duplicate horizons | Submit unsorted or duplicate values outside the allowed set | Reject; no implicit order or duplicate binding rows | structural | Required | Required |
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
