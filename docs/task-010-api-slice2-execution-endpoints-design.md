# TASK-010 API Slice 2 — Residual Training / Prediction Execution Endpoints Design Contract

Status: design-only contract / no implementation mutation  
Base commit: `21c45dee49fbfabbbf81b9c471ac7a2fcfe58c9a` (origin/main)  
Branch: `codex/task-010-api-slice2-design-freeze`  
Companion to: `docs/task-010-report-api-contract.md` (PR #73, merged `4e9fa6f3...`) — **read first**.

---

## 1. Purpose and scope

TASK-010 API Slice 2 freezes the **execution** endpoints of the residual-model API
surface. Slice 1 (PR #75, merged `21c45dee...`) already exposed four
**download** endpoints for already-completed runs. Slice 2 freezes the four
endpoints that **create** and **inspect** training / prediction runs.

This document does **NOT**:

- authorize any production code mutation,
- authorize any new test,
- authorize Alembic changes,
- authorize frontend work,
- authorize agent workflow changes,
- authorize background queues / workers / async job tables,
- modify any TASK-009A / TASK-011 / TASK-012 file.

This document freezes **only** the API contract: route paths, request schemas,
response envelopes, idempotency / conflict semantics, error payloads,
transaction boundary, and report-endpoint linkage. A future implementation
slice must satisfy this contract byte-for-byte.

---

## 2. Existing completed boundary

The TASK-010 sequence is partially complete. Slice 2 inherits the following
merged state and may **not** redefine it:

| PR | Merge commit | Slice content |
|---|---|---|
| PR #73 | `4e9fa6f3c945538af3959f93f6ce49ce585e8f6c` | `docs/task-010-report-api-contract.md` — frozen report schema versions, scalar / ZIP / CSV determinism rules, security boundary, future-API placeholder. |
| PR #74 | `7b3c57bdbf5e7edcbacfa81eb0b5a3884044bbf0` | Deterministic report renderers (`render_residual_training_json_report` etc.) + determinism tests. |
| PR #75 | `21c45dee49fbfabbbf81b9c471ac7a2fcfe58c9a` | Residual report download API endpoints — 4 GET routes under `/api/v1/residual-model/`. |

Post-merge verification:

- `origin/main` HEAD = `21c45dee49fbfabbbf81b9c471ac7a2fcfe58c9a` ✓
- Post-merge `main` CI run `28957305606` = `success` (all 9 jobs green,
  including `full-suite-canary`)
- Open PRs = none; Open Issues = none

---

## 3. Route contract (Slice 2 freeze)

Slice 2 adds exactly **four** routes. Slice 1 download routes remain frozen as-is
and are **not redefined here**.

### 3.1 Training execution routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/residual-model/training-runs` | Create + execute a new residual-model training run. |
| `GET` | `/api/v1/residual-model/training-runs/{run_id}` | Inspect an existing training run's status, hashes, warnings, blockers, and report links. |

### 3.2 Prediction execution routes

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/residual-model/prediction-runs` | Create + execute a new residual-model prediction run against an existing training run. |
| `GET` | `/api/v1/residual-model/prediction-runs/{run_id}` | Inspect an existing prediction run's status, hashes, warnings, blockers, and report links. |

### 3.3 Slice 1 download routes (re-affirmed, NOT redefined)

| Method | Path | Source |
|---|---|---|
| `GET` | `/api/v1/residual-model/training-runs/{run_id}/report.json` | PR #75 |
| `GET` | `/api/v1/residual-model/training-runs/{run_id}/report.csv` | PR #75 |
| `GET` | `/api/v1/residual-model/prediction-runs/{run_id}/report.json` | PR #75 |
| `GET` | `/api/v1/residual-model/prediction-runs/{run_id}/report.csv` | PR #75 |

### 3.4 Negative authorization (NOT in Slice 2)

The following are **NOT** frozen here and must not be added by a Slice 2
implementation round:

- raw artifact binary download endpoints,
- raw training dataset export,
- `DELETE` / `PATCH` mutation of training or prediction runs,
- cancellation endpoints,
- re-run / replay endpoints,
- streaming / SSE / WebSocket endpoints,
- bulk creation endpoints.

---

## 4. Request schema contract

### 4.1 `POST /api/v1/residual-model/training-runs` — TrainingRunCreateRequest

The request body MUST be a JSON object with the following frozen fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `manifest_snapshot` | object | **yes** | Snapshot of the training manifest (sample source + feature + cutoff). The API adapter canonicalizes this object before hashing; the request body itself is opaque (caller-supplied). |
| `manifest_snapshot_id` | integer \| null | no | Optional reference to a previously-persisted manifest snapshot. If supplied, the API adapter MUST verify the snapshot exists and **MUST** reject with `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` if it does not. |
| `manifest_rows` | array[object] \| null | no | Optional inline manifest rows. **Slice 2 freeze**: only inline rows are accepted. The API does **NOT** accept an `external_manifest_ref` field in Slice 2. |
| `config` | object | **yes** | Frozen config identity. Hashable via canonical JSON. |
| `forecast_cutoff` | string (ISO-8601 date) | **yes** | Visibility boundary: training data on or before this date is allowed; data after is rejected by the service layer. |
| `source_run_ids` | object | no | Upstream run references for lineage. Each value is an integer run-id. Valid keys: `task9a_run_id`, `harvest_state_run_id`, `production_run_id`. |
| `idempotency_key` | string \| null | no | Caller-supplied UUIDv4 for client-side dedupe. See §7. |

Inline `manifest_rows` MUST be an array of objects matching the existing
training-manifest row schema (see `backend/app/residual_model/manifest.py`).
The API adapter MUST NOT accept raw arrays of scalars, raw CSV strings, or
file-path references.

Validation failure semantics:

- missing required field → HTTP `422` with stable error code
  `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`;
- `forecast_cutoff` not parseable as ISO-8601 → `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`;
- inline `manifest_rows` schema mismatch → `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`;
- `manifest_snapshot_id` non-null but not found → `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`.

### 4.2 `POST /api/v1/residual-model/prediction-runs` — PredictionRunCreateRequest

| Field | Type | Required | Description |
|---|---|---|---|
| `training_run_id` | integer | **yes** | Foreign key to an existing training run. The adapter MUST verify the run exists and reject if not (code `RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND`). |
| `feature_actual_snapshot` | object | **yes** | Frozen actual feature snapshot used as prediction input. Canonicalized before hashing. |
| `supplemental_features` | array[object] \| null | no | Optional rows supplementing the snapshot. Same schema as the snapshot rows. |
| `config` | object | **yes** | Frozen prediction config identity (may differ from training config). |
| `prediction_mode` | string (enum) | **yes** | One of the existing residual-model prediction modes (see `backend/app/residual_model/application.py` and `prediction_features.py`). The API adapter MUST reject unknown modes with `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`. |
| `task9_run_id` | integer \| null | no | Upstream TASK-009A deterministic forecast run used as prediction baseline. |
| `task9_result_hash` | string \| null | no | SHA-256 of the TASK-009A result, hex-encoded. If supplied, MUST match the persisted hash for `task9_run_id`; mismatch → `RESIDUAL_MODEL_EXECUTION_CONFLICT`. |
| `source_run_ids` | object | no | Upstream run references. |
| `idempotency_key` | string \| null | no | See §7. |

`artifact_hash_authority` is **NOT** caller-supplied. The adapter derives it
from the resolved training run's artifact metadata at execution time. Callers
must not supply it.

Validation failure semantics mirror §4.1.

### 4.3 Schema references (existing Pydantic schemas)

Where the codebase already exposes a Pydantic model that matches the request
shape, the future implementation MUST import and reuse it (no shadow
re-definition). Specifically:

- Training manifest row → existing row Pydantic in
  `backend/app/residual_model/manifest.py`.
- Residual prediction feature row → existing schema in
  `backend/app/residual_model/prediction_features.py`.
- Residual training config → existing config Pydantic in
  `backend/app/residual_model/config.py`.

Slice 2 introduces new Pydantic request models (`TrainingRunCreateRequest`,
`PredictionRunCreateRequest`) as **thin adapter wrappers** that compose
the existing schemas. The internal `service` / `persistence` modules are
**not** modified by this contract — only the API adapter layer consumes them.

---

## 5. Response envelope contract

Both `POST` and `GET` endpoints return the same envelope shape per resource.

### 5.1 Training run envelope (`TrainingRunEnvelope`)

| Field | Type | Description |
|---|---|---|
| `run_id` | integer | Database id. |
| `execution_status` | string (enum) | `accepted` \| `running` \| `completed` \| `failed` \| `blocked`. |
| `eligibility_status` | string (enum) | `eligible` \| `ineligible` — derived from the manifest + cutoff gate. |
| `training_signature` | string (hex SHA-256) | Deterministic signature of the training inputs. |
| `config_hash` | string (hex SHA-256) | Canonical hash of `config`. |
| `manifest_hash` | string (hex SHA-256) | Canonical hash of `manifest_snapshot`. |
| `created_at` | string (ISO-8601) | Insertion timestamp. |
| `finished_at` | string (ISO-8601) \| null | Completion timestamp; null while still running. |
| `warnings` | array[object] | Non-fatal advisory messages. Empty array if none. |
| `blockers` | array[object] | Reason the run is ineligible / blocked. Empty array if none. |
| `report_links` | object | Sub-object with two keys: `json` and `csv`. Each value is an absolute path under `/api/v1/residual-model/...` resolved against the current `run_id`. See §10. |

`report_links` shape:

```json
{
  "report_links": {
    "json": "/api/v1/residual-model/training-runs/123/report.json",
    "csv":  "/api/v1/residual-model/training-runs/123/report.csv"
  }
}
```

### 5.2 Prediction run envelope (`PredictionRunEnvelope`)

| Field | Type | Description |
|---|---|---|
| `run_id` | integer | Database id. |
| `execution_status` | string (enum) | `accepted` \| `running` \| `completed` \| `failed` \| `blocked`. |
| `mode` | string | Echo of `prediction_mode` from the request. |
| `prediction_hash` | string (hex SHA-256) | Deterministic signature of the prediction output. |
| `prediction_input_signature` | string (hex SHA-256) | Canonical hash of `(training_run_id, feature_actual_snapshot, supplemental_features, config, task9_result_hash?)`. |
| `config_hash` | string (hex SHA-256) | Canonical hash of `config`. |
| `created_at` | string (ISO-8601) | Insertion timestamp. |
| `completed_at` | string (ISO-8601) \| null | Completion timestamp. |
| `warnings` | array[object] | Non-fatal advisories. |
| `blockers` | array[object] | Reason blocked. |
| `report_links` | object | `json` + `csv` keys, same convention as training. |

### 5.3 HTTP status mapping

| Outcome | HTTP | Body |
|---|---|---|
| `POST` first creation, status `completed` / `blocked` / `failed` | **201 Created** | envelope + `Location` header pointing to the run-specific `GET` route. |
| `POST` replay (idempotent re-submission with matching signature) | **200 OK** | envelope of existing run, **no** `Location` header required. |
| `POST` signature conflict | **409 Conflict** | stable error payload (§8). |
| `GET` existing run | **200 OK** | envelope. |
| `GET` non-existent run | **404 Not Found** | stable error payload. |

A blocked run is a **successful** run record — its envelope is returned at
`201` / `200`, not at `4xx`. Only `failed` (training/prediction raised) maps
to an envelope with `execution_status = "failed"` while still returning
`201` / `200`. Internal exceptions map to `500` (§8).

---

## 6. Synchronous vs asynchronous execution — DECISION

**Decision: synchronous execution adapter. Async is a P0 blocker for Slice 2.**

The Slice 2 `POST` handler MUST execute the residual-model training /
prediction service **inline** within the request lifecycle:

- `POST /training-runs` → calls existing
  `ResidualModelService.train_residual_model(...)` synchronously →
  envelope returned in the response body.
- `POST /prediction-runs` → calls existing
  `ResidualModelService.predict_with_residual_model(...)` synchronously
  → envelope returned in the response body.

The following are **NOT** introduced by Slice 2:

- background task queues (Celery, RQ, Dramatiq, Arq, etc.),
- dedicated worker processes,
- new async job table or status table,
- polling endpoints distinct from `GET .../{run_id}`,
- `202 Accepted` semantics.

Rationale (binding for any future async re-authorization):

1. The existing `ResidualModelService` boundary is already synchronous and
   transaction-bounded. Wrapping it in a queue would duplicate the
   transaction boundary.
2. Async would force a P0 design amendment covering idempotency at the queue
   boundary, retry semantics, dead-letter handling, and observability —
   outside Slice 2's scope.
3. Async would entangle TASK-012 (agent workflow) into Slice 2, which the
   brief explicitly forbids.
4. Synchronous execution is bounded by training/prediction runtime; if a
   future slice determines that runtime is unacceptable, that slice must
   freeze a new design amendment covering queue semantics — NOT mutate
   this contract.

**If a future round determines async is mandatory**, that round MUST:

- mark the round as `BLOCKED_BY_P0`,
- cite this §6 explicitly,
- propose an amendment SHA, and
- receive explicit Charles authorization before any implementation.

---

## 7. Idempotency and conflict semantics

Slice 2 freezes the following idempotency model, building on the existing
`ResidualModelHashConflictError` and signature machinery already used by
`persistence.py`.

### 7.1 Training run POST

| Scenario | HTTP | Response |
|---|---|---|
| First creation with valid inputs | `201 Created` | envelope + `Location: /api/v1/residual-model/training-runs/{run_id}` |
| Replay: same `manifest_snapshot` + same `config` + same `forecast_cutoff` + same `source_run_ids` + same `idempotency_key` (if supplied) → existing run found | `200 OK` | envelope of the existing run |
| Same inputs but different `idempotency_key` → no existing run found | `201 Created` | new envelope (caller signalled a fresh attempt) |
| Same canonical inputs hash (`training_signature`) but a different canonical payload bytes (e.g. reordered keys) | `409 Conflict` | `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| Same `idempotency_key` reused with different canonical payload | `409 Conflict` | `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| Concurrent in-flight POST with matching `idempotency_key` | first wins; second observes existing run and returns `200 OK` | envelope of existing run |

### 7.2 Prediction run POST

| Scenario | HTTP | Response |
|---|---|---|
| First creation with valid inputs | `201 Created` | envelope + `Location` header |
| Replay: same `training_run_id` + same `feature_actual_snapshot` + same `config` + same `prediction_mode` + same `idempotency_key` → existing run | `200 OK` | envelope of existing run |
| Same `prediction_input_signature` but different canonical payload | `409 Conflict` | `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| `task9_result_hash` supplied but doesn't match `task9_run_id`'s persisted hash | `409 Conflict` | `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| `training_run_id` does not exist | `404 Not Found` | `RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND` |

### 7.3 Determinism guarantees

The API adapter MUST canonicalize the request payload (sorted keys, stable
JSON encoding, deterministic decimal rendering) before hashing. Two requests
with byte-different but semantically-identical payloads MUST produce the
same signature and trigger the replay path.

Concurrent duplicate requests MUST be linearized at the database level via
the existing `UNIQUE` constraints on `manifest_hash + config_hash` (training)
and `prediction_input_signature` (prediction). The implementation MUST NOT
adopt an in-process lock or an external coordination layer.

---

## 8. Stable error payloads

All error responses (HTTP 4xx and 5xx) MUST use the frozen envelope:

```json
{
  "error": {
    "code": "...",
    "message": "..."
  }
}
```

Frozen error codes for Slice 2:

| Code | HTTP | When |
|---|---|---|
| `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` | 422 | Request schema validation failure (missing field, wrong type, unknown `prediction_mode`, unparseable `forecast_cutoff`). |
| `RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND` | 404 | `GET /training-runs/{run_id}` or `POST /prediction-runs` with a non-existent `training_run_id`. |
| `RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND` | 404 | `GET /prediction-runs/{run_id}` with a non-existent run. |
| `RESIDUAL_MODEL_EXECUTION_CONFLICT` | 409 | Idempotency / hash / signature conflict (§7). |
| `RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR` | 500 | Loader / repository / service raised `ResidualArtifactIntegrityError`, `ResidualModelPersistenceIntegrityError`, or any other internal integrity exception. |
| `RESIDUAL_MODEL_REPORT_NOT_AVAILABLE` | 404 | `GET` on a run whose execution has not reached a state with downloadable report (e.g. `running` / `failed` before persistence complete). Returns `404` (NOT `409` per §8 second-tied decision). |

The following are **forbidden** in any error response body:

- raw `sqlalchemy` exception text,
- raw `asyncpg` exception text,
- Python tracebacks,
- absolute local file paths,
- raw `artifact_bytes` or any binary blob,
- raw training dataset rows.

The error envelope MUST NOT include a FastAPI-default `detail` field for the
endpoints listed in §3.1 / §3.2. Validation errors raised by Pydantic MUST
be re-wrapped to `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` by the API adapter.

---

## 9. DB transaction boundary

The Slice 2 API adapter delegates **all** persistence and transaction
management to the existing service / persistence layer. The adapter MUST
NOT bypass the service layer to fabricate ORM rows directly.

### 9.1 Training run write

A single successful `POST /training-runs` produces, in **one atomic
transaction owned by `persistence.py`**:

1. INSERT into `residual_model_training_runs` (parent row).
2. INSERT one or more rows into `residual_model_manifest_rows` (manifest snapshot rows).
3. INSERT zero or more rows into `residual_model_artifacts` (artifact blobs + sha256 + meta).

The API adapter MUST NOT split these into separate transactions. If step 2
or step 3 fails, the parent row must roll back. `session.flush()` is NOT a
commit; the boundary is the single `commit()` issued by `persistence.py`
at the end of the service call.

### 9.2 Prediction run write

A single successful `POST /prediction-runs` produces, in **one atomic
transaction owned by `persistence.py`**:

1. INSERT into `residual_prediction_runs` (parent row).
2. INSERT one or more rows into `residual_prediction_rows`.

Same atomicity rule. The API adapter MUST NOT split these.

### 9.3 Read paths

`GET` endpoints MUST NOT mutate state. They may issue `SELECT`s inside an
implicit read-only transaction managed by the dependency-injected session.

### 9.4 Failure paths

- A `failed` envelope implies the service layer persisted a `failed` run
  record. The contract allows this because the persistence boundary
  already commits a partial state representing the failure mode (a
  `failed` row with `error_code` + `error_message`). This is NOT a
  "partial visible state" violation — it is an explicitly-designed
  failure-record contract owned by `persistence.py` and MUST NOT be
  re-implemented in the API adapter.
- A `blocked` envelope implies the service layer persisted a `blocked`
  run record. Same reasoning.
- An internal exception (sqlalchemy / asyncpg / integrity error) MUST
  roll back the transaction. The API adapter catches the exception and
  returns `500 RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR` with a stable
  payload. The DB MUST NOT contain a half-written run.

The API adapter MUST NOT construct ORM objects directly via raw SQL or
constructors; it MUST go through `service.train_residual_model(...)` and
`service.predict_with_residual_model(...)` entry points.

---

## 10. Report endpoint linkage

### 10.1 Required availability

After a successful `POST /training-runs` that returned envelope with
`execution_status` in `{completed, blocked, failed}`, the following MUST
hold:

- `GET /api/v1/residual-model/training-runs/{run_id}/report.json` MUST
  return `200 OK` with the report bytes.
- `GET /api/v1/residual-model/training-runs/{run_id}/report.csv` MUST
  return `200 OK` with the ZIP archive.

After a successful `POST /prediction-runs`:

- `GET .../prediction-runs/{run_id}/report.json` MUST return `200 OK`.
- `GET .../prediction-runs/{run_id}/report.csv` MUST return `200 OK`.

If the run's `execution_status` is `accepted` or `running` (synchronous
adapter means this state should not normally be visible to the caller, but
it is allowed), the report endpoints MUST return
`RESIDUAL_MODEL_REPORT_NOT_AVAILABLE` (`404`) until persistence completes.

### 10.2 `report_links` in envelopes

Both `POST` and `GET` envelopes MUST include `report_links` populated as
per §5.1 / §5.2. The link values are relative paths to be resolved against
the API base URL by the client. They are stable across requests for the
same `run_id`.

### 10.3 Blocked / failed runs and reports

- **blocked run**: report IS downloadable. `execution_status = blocked`,
  but the manifest + (partial) output are persisted; the renderer will
  emit a report with non-empty `blockers`. This is a Slice 1 behavior
  already covered by `render_residual_training_json_report` /
  `render_residual_prediction_json_report`.
- **failed run**: report IS downloadable. `execution_status = failed`,
  the report contains the `error_code` + `error_message`. Same Slice 1
  renderer path.

This freeze re-affirms Slice 1's behavior for blocked / failed runs and
MUST NOT be regressed by the implementation.

---

## 11. Security and governance boundary

The Slice 2 API surface is **read-write**. The following security
constraints are binding:

### 11.1 Negative authorizations (NOT in Slice 2)

- raw artifact binary download endpoints (Slice 2 inspects run metadata;
  binary download is intentionally NOT frozen — see §3.4);
- raw training dataset export;
- arbitrary file-path parameters;
- user-supplied ZIP entry names (Slice 1 already freezes this for ZIP
  outputs; Slice 2 inherits);
- bypassing visibility / authority / cutoff checks in the service layer.

### 11.2 Visibility / authority checks

The API adapter MUST NOT bypass the existing `forecast_cutoff` /
`eligibility` gates enforced by `service.py`. All canonical inputs MUST
flow through the service layer's gating logic. If the service rejects an
input as `ineligible`, the adapter returns a `blocked` envelope (not an
HTTP error).

### 11.3 Allowed files for this design PR

This design PR is restricted to:

- `docs/task-010-api-slice2-execution-endpoints-design.md` (this file).

No other file may be added or modified by this PR.

### 11.4 Forbidden files for this design PR

This design PR must not touch:

- `backend/app/**` (including `backend/app/api/**`,
  `backend/app/residual_model/**`, `backend/app/repositories/**`,
  `backend/app/main.py`),
- `backend/tests/**`,
- `backend/alembic/**`,
- `frontend/**`,
- `.github/workflows/**`,
- dependency files (`pyproject.toml`, `requirements*.txt`, `Makefile`,
  `backend/constraints*.txt`),
- `configs/**`,
- `scripts/**`,
- TASK-009A files,
- TASK-011 files,
- TASK-012 files.

If a README or index file would need updating, STOP and report — do not
modify.

---

## 12. Test matrix for future implementation

A future Slice 2 implementation slice must include tests covering all
cases below. This document freezes the **matrix**; the tests themselves
are not written here.

### 12.1 Happy paths

| Case | Expected |
|---|---|
| `POST /training-runs` valid request → 201 → envelope + `Location` | `execution_status = completed`, `report_links` populated |
| `GET /training-runs/{id}` → 200 → envelope | stable field order, all hashes present |
| `POST /prediction-runs` valid request → 201 → envelope | `execution_status = completed`, `report_links` populated |
| `GET /prediction-runs/{id}` → 200 → envelope | stable field order |
| After `POST /training-runs` → `GET .../report.json` → 200 | JSON bytes match Slice 1 determinism contract |
| After `POST /training-runs` → `GET .../report.csv` → 200 | ZIP archive matches Slice 1 deterministic ZIP contract |
| After `POST /prediction-runs` → `GET .../report.json` → 200 | JSON bytes match Slice 1 |
| After `POST /prediction-runs` → `GET .../report.csv` → 200 | ZIP archive matches Slice 1 |

### 12.2 Idempotency / replay

| Case | Expected |
|---|---|
| Replay `POST /training-runs` with identical canonical inputs | `200 OK` + existing run envelope |
| Replay `POST /prediction-runs` with identical canonical inputs | `200 OK` + existing run envelope |
| Concurrent duplicate `POST /training-runs` | exactly one run row created; both responses return same `run_id` |

### 12.3 Conflict / negative paths

| Case | Expected |
|---|---|
| Same signature, different canonical payload bytes | `409` + `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| Same `idempotency_key`, different payload | `409` + `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| `task9_result_hash` mismatch | `409` + `RESIDUAL_MODEL_EXECUTION_CONFLICT` |
| `GET /training-runs/{nonexistent_id}` | `404` + `RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND` |
| `GET /prediction-runs/{nonexistent_id}` | `404` + `RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND` |
| `POST /prediction-runs` with non-existent `training_run_id` | `404` + `RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND` |
| Invalid request schema (missing required field) | `422` + `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` |
| Unparseable `forecast_cutoff` | `422` + `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` |
| Unknown `prediction_mode` | `422` + `RESIDUAL_MODEL_EXECUTION_INPUT_ERROR` |
| Report endpoint on `running` run | `404` + `RESIDUAL_MODEL_REPORT_NOT_AVAILABLE` |

### 12.4 Integrity / shielding

| Case | Expected |
|---|---|
| Service raises `ResidualArtifactIntegrityError` | `500` + `RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR`, no sqlalchemy/asyncpg/traceback/path/binary leak |
| Service raises `ResidualModelPersistenceIntegrityError` | `500` + same stable payload |
| Service raises unexpected internal exception | `500` + same stable payload |
| Database `commit()` raises mid-transaction | `500` + same stable payload + no partial row visible |

### 12.5 Regression coverage

| Case | Expected |
|---|---|
| Slice 1 11 residual-model API tests | unchanged pass |
| `test_harvest_state_api.py` 21 tests | unchanged pass |
| Slice 1 10 residual-model determinism tests | unchanged pass |

### 12.6 Forbidden test behaviors

Tests MUST NOT:

- insert ORM rows directly via `session.add(...)` outside the production
  service path;
- bypass the service layer to fabricate run records;
- mock the persistence layer's transaction boundary;
- import or test against `backend/app/residual_model/reporting.py`
  directly for API-shape assertions (those tests live in PR #74).

---

## 13. Governance

This PR is **design-only**. It does not authorize:

- implementation,
- tests,
- Alembic changes,
- frontend changes,
- workflow / dependency changes,
- any mutation of TASK-009A / TASK-011 / TASK-012 files,
- issue creation / closure / editing / commenting,
- PR #25 touch (already merged; not open, but historically excluded),
- branch cleanup.

### 13.1 PR state

- Created as **Draft**.
- `Ready` transition requires a separate Charles authorization round.
- `Merge` requires a separate Charles authorization round.
- Post-merge `main` CI must be green before any downstream work.

### 13.2 Sequential slice pattern

Slice 2 follows the same 3-step pattern established by Slice 1:

1. **design freeze PR** ← this document (current round).
2. **golden-case test PR** (future; freezes the test matrix from §12 as
   actual test files; no implementation code).
3. **implementation PR** (future; satisfies §3–§10 byte-for-byte; flips the
   test PR to MERGEABLE + Ready + Merge).

Each round is independently authorized by Charles. No round auto-starts
the next.

### 13.3 Companion documents

- `docs/task-010-report-api-contract.md` — Slice 1 design freeze.
- `docs/task-010-api-slice2-execution-endpoints-design.md` — this
  document.
- Future `docs/task-010-api-slice2-execution-endpoints-tests.md` — test
  matrix frozen as code (separate PR).

---

## 14. Acceptance gates for a future Slice 2 implementation

A future implementation round may proceed only after this design contract
is merged. Minimum acceptance gates for that implementation:

- route paths, request schemas, response envelopes, idempotency
  semantics, error payloads, transaction boundary, and report linkage
  conform to this document byte-for-byte;
- 12 test matrix groups all pass;
- no forbidden file touched;
- PR CI green (9 jobs);
- post-merge `main` CI green;
- no TASK-009A / TASK-011 / TASK-012 mutation;
- no Alembic change (unless a future freeze amendment authorizes one);
- no frontend change;
- no PR #25 touch.

---

## 15. Change log

| Date | Author | Change |
|---|---|---|
| 2026-07-08 | Codex (design freeze round) | Initial freeze. Base commit `21c45dee49fbfabbbf81b9c471ac7a2fcfe58c9a`. |