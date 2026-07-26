# V0.2-S3 Round B Persistence Authorization Freeze

## Authorization status

```text
DOCUMENT_STATUS=PROPOSED_AWAITING_INDEPENDENT_REVIEW
BASE_SHA=aded38e2bec3877018168be0bceb955ed394e425
ROUND_A_MERGE_SHA=aded38e2bec3877018168be0bceb955ed394e425
ROUND_A_ACCEPTANCE_REVIEW_ID=4782025495
ROUND_B_AUTHORIZATION_DOCUMENT_COMPLETE=true
ROUND_B_IMPLEMENTATION_AUTHORIZED=false
ROUND_B_SCHEMA_CHANGE_AUTHORIZED=false
ROUND_B_MIGRATION_CHANGE_AUTHORIZED=false
ROUND_B_PRODUCTION_CODE_CHANGE_AUTHORIZED=false
ROUND_B_TEST_CHANGE_AUTHORIZED=false
REAL_DATA_OPENED=false
REAL_DATA_BACKTEST_AUTHORIZED=false
ISSUE102_CLOSE_AUTHORIZED=false
ROUND_C_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This document freezes a future implementation boundary only. The current
round creates no ORM model, migration, production code, test, API, or real
data result. A Draft PR, review approval, Ready state, or merge of this
document does not authorize Round B implementation automatically. Charles
must issue a separate implementation authorization after independent review.

## 1. Round B scope

Round B is limited to the two frozen requirements below:

```text
ROUND_B_REQUIREMENTS=S3R-19,S3R-20
S3R-19=FORECAST_QUALITY_PERSISTENCE
S3R-20=IDEMPOTENT_PERSISTENCE
ROUND_B_TABLE_COUNT=6
ROUND_B_DOMAIN_ARITHMETIC=false
ROUND_B_HTTP_API=false
ROUND_B_REAL_DATA=false
```

The future implementation may persist only these six logical records:

| Logical record | Persistence purpose | Round B rule |
|---|---|---|
| `QualityEvaluationRun` | One complete S3 evaluation identity and lifecycle row | Owns the evaluation transaction and all child records. |
| `QualityMetricResult` | Persisted daily metric result values and audit envelope | Stores Round A `DailyMetricResult` semantics; it does not recalculate metrics. |
| `QualityBreakdownResult` | Persisted six-axis breakdown-cell result | Stores the existing breakdown payload and status/reason evidence. |
| `NaiveBaselineRun` | Persisted single prior-season point-baseline result | Stores Round A baseline request, source snapshot, result, and canonical identity. |
| `ModelBaselineComparison` | Persistence row for a future model-vs-baseline comparison identity | Table structure only. No new comparison arithmetic is allowed in Round B. |
| `QualityEvaluationManifest` | Immutable complete-result seal and child-set evidence | Must be inserted last and seals the result set. |

The following are explicitly excluded:

```text
COMPLETE_WINDOW_CUMULATIVE_METRICS=false
SINGLE_DAY_PEAK=false
SUSTAINED_7DAY_PEAK=false
QUANTILE_COVERAGE=false
PINBALL_LOSS=false
PREDICTION_INTERVALS=false
MODEL_COMPARISON_CALCULATION=false
HTTP_API=false
FRONTEND=false
REAL_DATA_BACKTEST=false
MODEL_MODIFICATION=false
ISSUE102_CLOSURE=false
ROUND_C_AUTHORIZED=false
```

`ModelBaselineComparison` may contain identities, references, status, and
blocked/not-computable evidence required to persist its future contract. It
must not contain or compute a new delta, loss, coverage, interval, or other
comparison arithmetic in this round.

## 2. Exact future implementation paths

The following is the complete future Round B candidate set. The paths are
not changed by this authorization-document PR.

```text
IMPLEMENTATION_PATH_COUNT=6
CREATE_PATH_COUNT=5
MODIFY_PATH_COUNT=1
HIDDEN_OPTIONAL_PATH_COUNT=0
```

| Action | Repository-relative path | Owner responsibility | Why required | Test owner |
|---|---|---|---|---|
| `CREATE` | `backend/app/models/forecast_quality.py` | Define the six SQLAlchemy models, constraints, immutable/seal metadata, and relationships. | No current model owns the S3 quality persistence tables. Existing `rolling_backtest` and `baseline_backtest` models have different aggregate identities and payload contracts. | `backend/tests/forecast_quality/test_persistence.py` |
| `MODIFY` | `backend/app/models/__init__.py` | Register only the six new model classes in the existing model metadata/export surface. | The current model registry must import the new models for Alembic metadata; no unrelated registration or semantic change is authorized. | `backend/tests/forecast_quality/test_persistence.py` |
| `CREATE` | `backend/app/forecast_quality/persistence.py` | Implement the internal caller-owned transaction API, canonical identity checks, complete-set write, replay classification, and conflict translation. | No current persistence module owns Round A quality results or S3R-20 replay behavior. | `backend/tests/forecast_quality/test_persistence.py`, `backend/tests/forecast_quality/test_idempotency.py` |
| `CREATE` | `backend/alembic/versions/0024_s3_forecast_quality_persistence.py` | Create and downgrade only the six Round B tables, constraints, indexes, and immutable/seal enforcement. | The current Alembic head is `0023_historical_backtest_binding`; a new single child revision is required. | `backend/tests/forecast_quality/test_persistence.py` |
| `CREATE` | `backend/tests/forecast_quality/test_persistence.py` | Test schema, migration, complete writes, foreign keys, constraints, immutable rows, and PostgreSQL behavior. | S3R-19 requires migration and persistence acceptance evidence. | N/A |
| `CREATE` | `backend/tests/forecast_quality/test_idempotency.py` | Test exact replay, conflicting replay, partial-result rejection, rollback, and concurrent races. | S3R-20 requires idempotency and concurrency evidence. | N/A |

No additional path is authorized. In particular, the future implementation
must not modify `backend/app/forecast_quality/*.py`, create a parallel
`repository.py` or `application.py`, modify an API route, change CI, add a
real-data fixture, or reuse an unrelated test module merely to reduce the
candidate count.

`backend/app/models/forecast_quality.py` is intentionally separate from
`backend/app/models/baseline_backtest.py`. The existing baseline-backtest
tables use evaluation schemes, factory/season numeric foreign keys, and a
different historical backtest identity. They cannot represent the Round A
S2 manifest identity, metric envelope, six-axis cell identity, source
snapshot visibility, or all-or-nothing manifest seal without redefining the
existing domain. The future model file must not alter those existing tables.

## 3. Persistence ownership and source semantics

Round B persists the already merged Round A domain objects and canonical
payloads. It does not create a second metric or baseline vocabulary.

| Persisted concern | Existing Round A source | Round B treatment |
|---|---|---|
| S2 evaluation identity | `S3EvaluationInput.s2_run_identity`, `s2_manifest_identity`, `s2_binding_row_set_hash`, policy versions | Reuse the values and recompute the request/result hashes from canonical bytes. |
| Daily metrics | `DailyMetricResult` 21-field audit envelope and `canonical_hash` | Store the exact semantic fields and canonical payload; no recalculation or rounding change. |
| Breakdown | `BreakdownSpec` six-axis identity and `calculate_breakdown_cells()` payload | Store the normalized cell identity and result payload; no new axis or threshold. |
| Naive baseline | `BaselineRequest`, `BaselineSourceSnapshot`, `BaselineResult`, and Round A baseline canonical payload | Store exact source/visibility identities; no latest snapshot fallback and no P80/P90 fabrication. |
| Comparison | Existing model identity plus persisted baseline identity and a future comparison-policy identity | Store references and status only; comparison arithmetic remains out of scope. |
| Manifest | Round A canonical root payload, child canonical hashes, coverage/exclusion evidence | Recompute and seal a deterministic child-set manifest; insertion order is not identity. |

All persisted authority is derived from these validated objects. A caller
may provide an expected hash for assertion, but a caller-supplied final JSON
payload or arbitrary hash is not accepted as authority.

## 4. Six-table schema freeze

### 4.1 Common column and identity policy

Each table has an independent database lookup primary key and an immutable
canonical payload. The following rules apply to every table:

```text
PRIMARY_KEY=database_generated_bigint_lookup_only
SCHEMA_VERSION=required_text
CANONICAL_HASH=required_lowercase_sha256_text
CANONICAL_PAYLOAD=required_jsonb
CREATED_AT=required_timestamptz_server_default_now_not_canonical
COMPLETED_AT=required_for_finalized_result_rows_not_canonical
DECIMAL_STORAGE=NUMERIC_WITH_FIXED_SCALE_6
DECIMAL_CANONICAL_EMISSION=FIXED_SIX_TEXT_ROUND_HALF_EVEN
DATABASE_NUMERIC_IDS_IN_CANONICAL_HASH=false
INSERTION_TIMESTAMPS_IN_CANONICAL_HASH=false
WORKER_OR_HOST_IDENTITY_IN_CANONICAL_HASH=false
DATABASE_ROW_ORDER_IN_CANONICAL_HASH=false
```

The database primary key, foreign-key columns, `created_at`,
`completed_at`, `sealed_at`, and operational status columns are lookup or
lifecycle metadata. They are never inputs to a Round A/Round B canonical
hash. Every JSONB payload must be produced by the existing canonical JSON
serializer before persistence; native `datetime`, `date`, `Decimal`, Enum,
tuple, or arbitrary object values must not be passed directly to JSONB.

### 4.2 `quality_evaluation_run`

```text
TABLE=quality_evaluation_run
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=none
SEMANTIC_IDENTITY=evaluation_request_hash
CANONICAL_IDENTITY=round_b_schema_version + S2 identities + policy versions + request scope
CANONICAL_HASH=canonical_hash
JSONB_PAYLOAD=canonical_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL for COMPLETE rows
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `schema_version` | `TEXT`, non-null | Round B persistence schema version. |
| `evaluation_request_hash` | `TEXT`, non-null, unique | Canonical semantic request identity. |
| `s2_run_identity` | `TEXT`, non-null | Exact S2 run identity from `S3EvaluationInput`. |
| `s2_manifest_identity` | `TEXT`, non-null | Exact S2 manifest identity from `S3EvaluationInput`. |
| `s2_binding_row_set_hash` | `TEXT`, non-null | Exact S2 binding row-set identity from `S3EvaluationInput`. |
| `metric_policy_version` | `TEXT`, non-null | Round A `FrozenVersion` value. |
| `baseline_policy_version` | `TEXT`, non-null | Round A `FrozenVersion` value. |
| `status` | `TEXT`, non-null | Lifecycle status validated by the future persistence layer. |
| `canonical_payload` | `JSONB`, non-null | Canonical run payload. |
| `canonical_hash` | `TEXT`, non-null, unique | Hash of `canonical_payload`. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp, excluded from identity. |
| `completed_at` | `TIMESTAMPTZ`, nullable until complete | Lifecycle timestamp, excluded from identity. |

### 4.3 `quality_metric_result`

```text
TABLE=quality_metric_result
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=quality_evaluation_run_id -> quality_evaluation_run.id ON DELETE RESTRICT
SEMANTIC_IDENTITY=quality_evaluation_run_id + metric_result_key_hash
CANONICAL_IDENTITY=DailyMetricResult audit envelope + metric name + normalized breakdown identity
CANONICAL_HASH=canonical_hash
JSONB_PAYLOAD=canonical_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL for accepted rows
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `quality_evaluation_run_id` | `BIGINT`, non-null FK | Owning run. |
| `schema_version` | `TEXT`, non-null | Persistence schema version. |
| `metric_result_key_hash` | `TEXT`, non-null | Hash of metric name, quantile, horizon, and normalized six-axis breakdown identity. |
| `metric_name` | `TEXT`, non-null | Existing Round A metric name; no new metric names. |
| `metric_status` | `TEXT`, non-null | Existing `MetricStatus` value. |
| `reason_code` | `TEXT`, non-null | Existing public reason-code value. |
| `metric_value` | `NUMERIC(20,6)`, nullable | Round A final metric value; null follows existing not-computable semantics. |
| `numerator` | `NUMERIC(20,6)`, nullable | Existing audit numerator. |
| `denominator` | `NUMERIC(20,6)`, nullable | Existing audit denominator. |
| `breakdown_identity` | `JSONB`, non-null | Normalized six-axis identity. |
| `canonical_payload` | `JSONB`, non-null | Full `DailyMetricResult` canonical payload plus metric key. |
| `canonical_hash` | `TEXT`, non-null | Hash of the full canonical payload. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp. |
| `completed_at` | `TIMESTAMPTZ`, non-null | Persistence completion timestamp, not identity. |

The 21-field `DailyMetricResult` envelope remains the semantic owner. The
relational columns are query projections and must not create a second
meaning for counters, mask policy, coverage, or MAPE reasons.

### 4.4 `quality_breakdown_result`

```text
TABLE=quality_breakdown_result
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=quality_evaluation_run_id -> quality_evaluation_run.id ON DELETE RESTRICT
SEMANTIC_IDENTITY=quality_evaluation_run_id + breakdown_key_hash
CANONICAL_IDENTITY=BreakdownSpec six-axis identity + complete cell result payload
CANONICAL_HASH=canonical_hash
JSONB_PAYLOAD=canonical_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL for accepted rows
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `quality_evaluation_run_id` | `BIGINT`, non-null FK | Owning run. |
| `schema_version` | `TEXT`, non-null | Persistence schema version. |
| `breakdown_key_hash` | `TEXT`, non-null | Hash of the normalized six-axis `BreakdownSpec` identity. |
| `breakdown_identity` | `JSONB`, non-null | Six axes in deterministic order. |
| `metric_status` | `TEXT`, non-null | Existing status, including insufficient-sample behavior. |
| `reason_code` | `TEXT`, non-null | Existing reason code. |
| `s2_comparable_row_count` | `BIGINT`, non-null | Existing cell counter. |
| `s2_excluded_row_count` | `BIGINT`, non-null | Existing cell counter. |
| `s2_not_computable_row_count` | `BIGINT`, non-null | Existing cell counter. |
| `coverage_ratio` | `NUMERIC(20,6)`, nullable by Round A rules | Existing coverage value. |
| `metric_values` | `JSONB`, non-null | Existing per-cell metric values. |
| `canonical_payload` | `JSONB`, non-null | Full canonical cell payload. |
| `canonical_hash` | `TEXT`, non-null | Hash of the full canonical payload. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp. |
| `completed_at` | `TIMESTAMPTZ`, non-null | Persistence completion timestamp. |

No `minimum_sample_size` column or caller-configurable threshold is
authorized. The Round A owner remains the fixed threshold and status/reason
contract.

### 4.5 `naive_baseline_run`

```text
TABLE=naive_baseline_run
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=quality_evaluation_run_id -> quality_evaluation_run.id ON DELETE RESTRICT
SEMANTIC_IDENTITY=quality_evaluation_run_id + baseline_request_hash
CANONICAL_IDENTITY=BaselineRequest + BaselineSourceSnapshot + BaselineResult canonical identities
CANONICAL_HASH=canonical_hash
JSONB_PAYLOAD=canonical_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL for accepted rows
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `quality_evaluation_run_id` | `BIGINT`, non-null FK | Owning run. |
| `schema_version` | `TEXT`, non-null | Persistence schema version. |
| `baseline_request_hash` | `TEXT`, non-null | Canonical `BaselineRequest` identity. |
| `baseline_result_hash` | `TEXT`, non-null | Exact `BaselineResult.canonical_hash`. |
| `baseline_source_snapshot_identity` | `TEXT`, non-null | Exact snapshot identity. |
| `baseline_source_snapshot_hash` | `TEXT`, non-null | Exact snapshot hash. |
| `baseline_source_row_set_hash` | `TEXT`, non-null | Exact visible source row-set hash. |
| `visibility_manifest_hash` | `TEXT`, non-null | Exact cutoff visibility manifest. |
| `baseline_policy_version` | `TEXT`, non-null | Frozen baseline policy. |
| `metric_status` | `TEXT`, non-null | Existing baseline status. |
| `reason_code` | `TEXT`, non-null | Existing baseline reason. |
| `canonical_payload` | `JSONB`, non-null | Baseline canonical payload. |
| `canonical_hash` | `TEXT`, non-null | Hash of the persisted baseline payload. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp. |
| `completed_at` | `TIMESTAMPTZ`, non-null | Persistence completion timestamp. |

The source snapshot and visibility fields are exact projections of the
Round A source object. They must never be populated from a latest snapshot,
arrival timestamp, receipt, model output, or a caller-only string.

### 4.6 `model_baseline_comparison`

```text
TABLE=model_baseline_comparison
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=quality_evaluation_run_id -> quality_evaluation_run.id ON DELETE RESTRICT;
             naive_baseline_run_id -> naive_baseline_run.id ON DELETE RESTRICT
SEMANTIC_IDENTITY=quality_evaluation_run_id + model_identity + naive_baseline_run_id + comparison_key_hash
CANONICAL_IDENTITY=model identity + baseline run identity + comparison policy identity
CANONICAL_HASH=canonical_hash
JSONB_PAYLOAD=canonical_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL for accepted rows
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `quality_evaluation_run_id` | `BIGINT`, non-null FK | Owning evaluation. |
| `naive_baseline_run_id` | `BIGINT`, non-null FK | Persisted baseline identity. |
| `schema_version` | `TEXT`, non-null | Persistence schema version. |
| `comparison_key_hash` | `TEXT`, non-null | Deterministic identity for the future comparison row. |
| `model_identity` | `JSONB`, non-null | Existing model identity only. |
| `comparison_policy_version` | `TEXT`, non-null | Policy identity, not arithmetic. |
| `comparison_status` | `TEXT`, non-null | Persisted status such as blocked/not-computable as defined by the future contract. |
| `reason_code` | `TEXT`, non-null | Existing reason-code vocabulary where applicable. |
| `canonical_payload` | `JSONB`, non-null | Identity and status evidence only. |
| `canonical_hash` | `TEXT`, non-null | Hash of the persisted comparison identity/status payload. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp. |
| `completed_at` | `TIMESTAMPTZ`, non-null | Persistence completion timestamp. |

No comparison delta or arithmetic result column is authorized by Round B.

### 4.7 `quality_evaluation_manifest`

```text
TABLE=quality_evaluation_manifest
PRIMARY_KEY=id BIGINT GENERATED BY DEFAULT AS IDENTITY
FOREIGN_KEYS=quality_evaluation_run_id -> quality_evaluation_run.id ON DELETE RESTRICT
SEMANTIC_IDENTITY=quality_evaluation_run_id + evaluation_instance_hash
CANONICAL_IDENTITY=run identity + sorted complete child canonical-hash sets + manifest schema
CANONICAL_HASH=manifest_hash
JSONB_PAYLOAD=manifest_payload
CREATED_AT=created_at TIMESTAMPTZ NOT NULL DEFAULT now()
COMPLETED_AT=completed_at TIMESTAMPTZ NOT NULL when sealed
SEALED_AT=sealed_at TIMESTAMPTZ NOT NULL when sealed
```

Required columns:

| Column | Type/nullability | Meaning |
|---|---|---|
| `id` | `BIGINT`, non-null PK | Database lookup identity only. |
| `quality_evaluation_run_id` | `BIGINT`, non-null FK, unique | Exactly one manifest per evaluation run. |
| `schema_version` | `TEXT`, non-null | Manifest schema version. |
| `evaluation_request_hash` | `TEXT`, non-null | Must equal the owning run request hash. |
| `evaluation_instance_hash` | `TEXT`, non-null | Hash of the complete validated result instance. |
| `metric_result_set_hash` | `TEXT`, non-null | Hash of sorted metric-result canonical hashes. |
| `breakdown_result_set_hash` | `TEXT`, non-null | Hash of sorted breakdown-result canonical hashes. |
| `baseline_result_set_hash` | `TEXT`, non-null | Hash of sorted baseline-result canonical hashes. |
| `comparison_result_set_hash` | `TEXT`, non-null | Hash of sorted comparison-row canonical hashes, including an explicit empty-set value when none is authorized. |
| `manifest_payload` | `JSONB`, non-null | Complete immutable manifest and authority evidence. |
| `manifest_hash` | `TEXT`, non-null, unique | Hash of `manifest_payload`. |
| `created_at` | `TIMESTAMPTZ`, non-null | Lifecycle timestamp. |
| `completed_at` | `TIMESTAMPTZ`, non-null when sealed | Seal completion timestamp. |
| `sealed_at` | `TIMESTAMPTZ`, non-null when sealed | Immutable seal timestamp, excluded from identity. |

The manifest is inserted last. Its child-set hashes must match the rows
already validated in the same caller-owned transaction. A manifest cannot be
updated, deleted, or resealed.

## 5. Identity and canonical hash matrix

| Record | Semantic identity inputs | Canonical payload source | Required exclusions |
|---|---|---|---|
| `QualityEvaluationRun` | `S3EvaluationInput` S2 identities, policy versions, schema version, and the deterministic evaluation request scope | Existing Round A S2 identity fields and canonical JSON policy | DB IDs, timestamps, worker/host, row order, connection data |
| `QualityMetricResult` | Owning evaluation semantic identity, metric name, P50 point metric identity, horizon, and normalized six-axis breakdown | Exact `DailyMetricResult` 21-field envelope plus its existing canonical payload/hash | Any re-rounded or recomputed value; DB IDs and lifecycle fields |
| `QualityBreakdownResult` | Owning evaluation identity plus normalized `BreakdownSpec` six-axis identity | Existing breakdown cell payload and deterministic cell identity | Caller-selected threshold, DB IDs, row order |
| `NaiveBaselineRun` | `BaselineRequest` identity plus exact visible `BaselineSourceSnapshot` identity | `BaselineRequest`, `BaselineSourceSnapshot`, `BaselineResult`, and existing canonical baseline payload | Latest fallback, arrival/receipt proxy, DB IDs, timestamps |
| `ModelBaselineComparison` | Model identity, persisted baseline identity, comparison policy identity | Identity/status payload only | All comparison arithmetic and DB IDs |
| `QualityEvaluationManifest` | Owning request identity plus complete sorted child canonical-hash sets | Full manifest evidence and Round A root canonical payload | Child insertion order, DB IDs, timestamps, worker/host |

Canonical hash requirements:

```text
HASH_ALGORITHM=SHA256
HASH_INPUT=CANONICAL_JSON_BYTES
HASH_FIELD_ORDER=DETERMINISTIC
HASH_TIME_ENCODING=EXPLICIT_UTC_IF_A_DOMAIN_TIME_IS_ALREADY_IN_CONTRACT
HASH_NULL_POLICY=EXPLICIT_JSON_NULL
HASH_DECIMAL_POLICY=FIXED_SIX_TEXT_ROUND_HALF_EVEN
DATABASE_NUMERIC_IDS_INCLUDED=false
INSERTION_TIMESTAMPS_INCLUDED=false
WORKER_HOST_IDENTITIES_INCLUDED=false
DATABASE_ROW_ORDER_INCLUDED=false
```

The persistence layer must recompute the canonical bytes and compare them
with any supplied expected hash. A matching database row is valid only when
the stored payload re-hashes to the stored hash and all child ownership and
set hashes are valid.

## 6. Constraint and immutability matrix

| Object | Unique constraints | Check constraints | Foreign keys | Immutability/seal rule |
|---|---|---|---|---|
| `quality_evaluation_run` | `evaluation_request_hash`; `canonical_hash` | Lowercase 64-character SHA-256 hashes; required schema/policy fields; final status requires `completed_at` | None | No update/delete after a child exists; a completed run is immutable. |
| `quality_metric_result` | `(quality_evaluation_run_id, metric_result_key_hash)`; `canonical_hash` | Hash format; non-negative counters; `metric_status`/`reason_code` validated against Round A values; coverage/nullability follows Round A | Run, `ON DELETE RESTRICT` | Insert only before manifest seal; no update/delete after insert. |
| `quality_breakdown_result` | `(quality_evaluation_run_id, breakdown_key_hash)`; `canonical_hash` | Exactly six normalized axes; counter closure; coverage/nullability follows Round A | Run, `ON DELETE RESTRICT` | Insert only before manifest seal; no update/delete after insert. |
| `naive_baseline_run` | `(quality_evaluation_run_id, baseline_request_hash)`; `(quality_evaluation_run_id, baseline_result_hash)` | Snapshot identities and visibility cutoff required; point-only P80/P90 states must remain Round A semantics | Run, `ON DELETE RESTRICT` | Insert only before manifest seal; no update/delete after insert. |
| `model_baseline_comparison` | `(quality_evaluation_run_id, comparison_key_hash)`; `canonical_hash` | Model/baseline identities required; no arithmetic fields authorized | Run and baseline run, `ON DELETE RESTRICT` | Insert only before manifest seal; no update/delete after insert. |
| `quality_evaluation_manifest` | One per `quality_evaluation_run_id`; `manifest_hash` | Request hash and all child-set hashes must match; `sealed_at` required for complete status | Run, `ON DELETE RESTRICT` | Manifest update/delete forbidden; child insert after seal forbidden. |

The future migration must enforce immutability with PostgreSQL-safe database
rules, such as deterministic trigger functions plus the manifest seal check,
or an equivalent atomic mechanism. Application-only checks are insufficient
for the concurrency acceptance. The final write order is fixed:

```text
1. validate all Round A objects and recompute all canonical identities
2. insert or resolve QualityEvaluationRun
3. insert all metric, breakdown, baseline, and comparison children
4. verify the exact expected child sets and foreign-key ownership
5. insert and seal QualityEvaluationManifest last
```

Any child insert after a manifest exists for the run must fail. Duplicate
semantic keys with different evidence are drift conflicts, not a second
valid row. A complete result cannot be deleted to make a conflicting replay
look new.

## 7. Internal persistence API

The future API is an internal Python API in
`backend/app/forecast_quality/persistence.py`; it is not an HTTP route and
must not be exposed publicly.

```python
def persist_quality_evaluation(
    session: Session,
    *,
    evaluation_input: S3EvaluationInput,
    metric_results: Sequence[DailyMetricResult],
    breakdown_results: Sequence[Mapping[str, object]],
    baseline_requests: Sequence[BaselineRequest],
    baseline_snapshots: Sequence[BaselineSourceSnapshot],
    baseline_results: Sequence[BaselineResult],
    comparison_records: Sequence[Mapping[str, object]],
    manifest_payload: Mapping[str, object],
) -> PersistedQualityEvaluation:
    ...
```

The exact future implementation contract is:

| API concern | Frozen behavior |
|---|---|
| `session` | A caller-owned SQLAlchemy `Session`; the function does not create a session. |
| Transaction | `CALLER_OWNED_TRANSACTION=true`; the function never calls `commit()`, `rollback()`, or changes transaction boundaries. A nested savepoint may be used to resolve a PostgreSQL unique-key race. |
| Input objects | Existing Round A dataclasses for S2 input, daily result, baseline request, source snapshot, and baseline result; breakdown and comparison mappings must be schema-validated before write. |
| Return | Internal `PersistedQualityEvaluation` containing lookup references and validated canonical hashes; DB IDs are operational return values only. |
| New result | Recompute all canonical payloads and hashes, validate the complete expected set, write all six logical records in one caller transaction, and insert the manifest last. |
| Exact replay | Same semantic identity, same canonical hash, and complete child set. Return existing records with `new_write_count=0`; do not touch timestamps or issue a second insert. |
| Conflicting replay | Same semantic identity with a different canonical hash. Raise an internal persistence conflict with `CONFLICTING_REPLAY_REJECTED`; never overwrite or append a second logical result. |
| Partial existing result | Any required child or manifest is missing, extra, orphaned, or hash-invalid. Raise a partial-result error with `PARTIAL_METRIC_PERSISTENCE_FORBIDDEN`; do not repair silently. |
| Database errors | Translate unique/FK/check/immutability errors to internal persistence errors with the original database exception chained. A serialization or connection failure remains a failed caller transaction. |
| Concurrent identical writes | The winner completes the set. The loser handles the unique-key race in a savepoint, reloads the winner, validates every hash and child set, and returns exact replay with zero logical writes. |
| Concurrent conflicting writes | Exactly one transaction may succeed for one semantic key; the other must fail closed as conflicting replay after reload. Evidence drift must never be treated as idempotent replay. |
| Partial failure | Any exception before manifest seal leaves zero committed Round B rows when the caller rolls back; no partial result is acceptable. |

Required machine contract:

```text
CALLER_OWNED_TRANSACTION=true
IMMUTABLE_RESULT=true
EXACT_REPLAY_ZERO_WRITE=true
CONFLICTING_REPLAY_REJECTED=true
PARTIAL_METRIC_PERSISTENCE_FORBIDDEN=true
MANIFEST_INSERTED_LAST=true
CHILD_INSERT_AFTER_MANIFEST_FORBIDDEN=true
```

## 8. PostgreSQL acceptance matrix

PostgreSQL is the final authority. SQLite may be used for fast local
feedback only and cannot replace PostgreSQL evidence.

| Gate | Required evidence | Expected result |
|---|---|---|
| Alembic upgrade | Upgrade from `0023_historical_backtest_binding` to head | One head; all six tables and constraints exist. |
| Alembic round trip | Upgrade, downgrade, upgrade in an isolated PostgreSQL database | Original pre-0024 objects preserved; only 0024 objects are removed and recreated. |
| New complete write | Persist a deterministic Round A synthetic result set | One run, all required children, one final manifest; no orphan rows. |
| Exact replay | Invoke the same request and identical evidence twice | Existing complete result returned; logical write count is zero; row counts and timestamps unchanged. |
| Conflicting replay | Same semantic request with one changed canonical input/hash | `CONFLICTING_REPLAY_REJECTED`; no second result and no overwrite. |
| Partial result | Seed or simulate a missing child/manifest and replay | `PARTIAL_METRIC_PERSISTENCE_FORBIDDEN`; no silent repair or acceptance. |
| Transaction rollback | Fail validation or constraint before manifest seal and roll back caller transaction | Zero committed rows for that attempt across all six tables. |
| Concurrent identical writes | Two PostgreSQL transactions persist the same request/evidence | One logical complete result; one winner and one exact replay; no duplicate children or manifests. |
| Concurrent conflicting writes | Two transactions use one semantic request with different canonical evidence | One success and one conflict; no evidence drift accepted as replay. |
| Foreign keys and uniques | Delete/duplicate/orphan and duplicate hash probes | Every FK, semantic unique key, hash unique key, and manifest seal rule rejects invalid state. |
| Immutability | Update/delete result and manifest rows; insert a child after seal | Every mutation is rejected by database enforcement. |

The two future test modules must own this matrix. They must use
repository-owned deterministic synthetic fixtures only; no business database,
real harvest data, real-data backtest, or outbound contact is authorized.

## 9. Migration freeze

```text
CURRENT_ALEMBIC_HEAD=0023_historical_backtest_binding
REVISION=0024_s3_forecast_quality_persistence
DOWN_REVISION=0023_historical_backtest_binding
ALEMBIC_HEAD_COUNT_AFTER=1
SECOND_HEAD_ALLOWED=false
HISTORICAL_MIGRATION_MODIFICATION_ALLOWED=false
```

The future migration must:

- declare exactly one `down_revision` of `0023_historical_backtest_binding`;
- create exactly the six Round B tables and their named indexes, unique/check constraints, foreign keys, and immutable/seal enforcement;
- use deterministic object names and PostgreSQL-compatible JSONB/partial enforcement where required;
- preserve every pre-existing table and row;
- make no change to `0023_historical_backtest_binding` or any earlier migration;
- downgrade only objects created by `0024_s3_forecast_quality_persistence`;
- pass upgrade -> downgrade -> upgrade round-trip acceptance with one head.

No migration is created in this authorization-document round.

## 10. Stop conditions and governance

The future implementation must stop without expanding scope if any condition
below occurs:

```text
ROUND_A_DOMAIN_SEMANTICS_MUST_CHANGE=false
COMPARISON_ARITHMETIC_REQUIRED=false
COMPLETE_WINDOW_OR_PEAK_REQUIRED=false
HTTP_API_REQUIRED=false
REAL_DATA_REQUIRED=false
CI_CHANGE_REQUIRED=false
SEMANTIC_IDENTITY_UNRESOLVED=false
SIX_TABLE_RELATIONSHIP_UNRESOLVED=false
SEVENTH_TABLE_REQUIRED=false
```

If any of those values becomes true during implementation, the implementation
authorization is insufficient and must stop for a separately reviewed scope
decision. A Draft PR or successful CI cannot authorize the next round.

```text
CURRENT_ROUND_FILES_CREATED=1
CURRENT_ROUND_PRODUCTION_CODE_CHANGED=false
CURRENT_ROUND_ORM_CREATED=false
CURRENT_ROUND_MIGRATION_CREATED=false
CURRENT_ROUND_TEST_CHANGED=false
CURRENT_ROUND_REAL_DATA_OPENED=false
CURRENT_ROUND_ISSUE102_MUTATED=false
ROUND_B_IMPLEMENTATION_AUTHORIZED=false
ROUND_C_AUTHORIZED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
STOPPED_AWAITING_INDEPENDENT_REVIEW=true
NO_STEP_IMPLIES_THE_NEXT=true
```
