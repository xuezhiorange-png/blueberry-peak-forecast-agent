# TASK-012 Slice E — API / CLI Exposure Design Amendment

> **Status:** DESIGN ONLY — freezes only when this amendment is merged.
>
> **No implementation is authorized by this document.** This amendment does not modify production code, tests, migrations, API routes, CLI behavior, workflows, dependencies, or frontend code.
>
> **Required sequence:** design freeze → Slice E1 contract tests → Slice E2 application service + CLI → Slice E3 HTTP API. Each implementation slice requires separate authorization and a separate PR.

---

## 0. Authority and baseline

Repository: `xuezhiorange-png/blueberry-peak-forecast-agent`

Frozen baseline for this amendment:

- base branch: `main`;
- base SHA: `7a37effc7c4eb7504167343de771aa78b9f56a73`;
- PR #86: TASK-012 Slice D, merged;
- TASK-012 Slices A-D: landed on `main`;
- Slice D contract distribution: 4 `ACTIVE_SLICE_A`, 2 `ACTIVE_SLICE_B`, 3 `ACTIVE_SLICE_C`, 3 `ACTIVE_SLICE_D`, 0 `OBLIGATION_PLACEHOLDER`;
- post-merge CI evidence: run `29098236081`, with `full-suite-canary` completed / success and policy-skipped non-canary jobs.

Primary authority:

- `docs/task-012-replay-trained-model-design.md`;
- §5.4 upstream replay binding;
- §6 identity model;
- §7 training manifest contract;
- §8 selection and reuse policy;
- §9 blocker taxonomy;
- §10 audit and observability;
- §11 test contract;
- §12 Slice E boundary;
- §14 stop conditions.

Consumed implementation modules already on `main`:

- `backend/app/rolling_backtest/replay_trained_identity.py`;
- `backend/app/rolling_backtest/replay_trained_filtering.py`;
- `backend/app/rolling_backtest/replay_trained_prediction.py`;
- `backend/app/rolling_backtest/replay_task10_binding.py`;
- existing Task 10 residual-model service and persistence modules.

This amendment opens only the Slice E service, CLI, and API surfaces. It does not redefine Slices A-D.

---

## 1. Problem statement

Slices A-D established contract tests, deterministic training-manifest and artifact identities, cutoff filtering, exact Task 9 replay binding, prediction identity verification, and comparison-run separation.

The production replay policy remains intentionally closed in the pre-Slice-E binding path. Existing Slice C/D helpers must not be exposed directly as if they were a complete production execution path.

Slice E therefore requires an explicit application-service boundary that:

1. accepts an explicit `replay_trained_model` request;
2. resolves no implicit current/latest/most-recent state;
3. validates all replay, cutoff, Task 9, manifest, config, and artifact identities;
4. delegates training and prediction to the existing Task 10 residual-model services without changing their algorithms;
5. persists or returns only identities that can be reproduced and audited;
6. exposes the same semantic operation through CLI and HTTP adapters;
7. keeps the historical model path unchanged.

An API or CLI adapter that merely calls Slice D validation helpers without performing the full authorized service orchestration is incomplete and must not be presented as replay-trained prediction execution.

---

## 2. Amendment scope

### 2.1 In scope

This amendment freezes contracts for:

- a TASK-012 replay-trained application service;
- an explicit runtime policy gate limited to that service;
- a deterministic request and response schema;
- exact replay attempt, replay node, cutoff, Task 9, manifest, model-config, artifact, and prediction bindings;
- reuse of existing Task 10 training and prediction algorithms;
- CLI exposure through the existing rolling-backtest CLI module;
- HTTP exposure through a thin FastAPI adapter;
- deterministic error and blocker payloads;
- idempotency and conflict behavior;
- audit identity requirements;
- Slice E contract-test requirements;
- implementation slicing and allowed-file boundaries.

### 2.2 Out of scope

The following remain forbidden unless a later amendment explicitly opens them:

- Task 8 natural-maturity semantic changes;
- Task 9 harvest-capacity, mature-inventory, backlog, holiday-release, or factory-arrival semantic changes;
- Task 10 model algorithm, feature definition, eligibility, quantile projection, or fallback semantic changes;
- historically-available-model behavior changes;
- current/latest/most-recent implicit selection;
- wall-clock authority in canonical identities;
- cross-run artifact promotion;
- cross-attempt or cross-node substitution;
- new database migrations or Alembic revisions;
- frontend work;
- workflow or dependency changes;
- branch cleanup;
- issue closing;
- automatic Ready or merge transitions.

---

## 3. Mandatory implementation sequence

### 3.1 Slice E1 — contract tests only

Allowed:

- tests defining the service, CLI, and HTTP contracts in this amendment;
- fixtures containing explicit replay identities and deterministic payloads;
- tests proving the gate remains closed outside the new explicit service path.

Forbidden:

- production implementation;
- route registration;
- CLI command implementation;
- migration or persistence changes.

### 3.2 Slice E2 — application service and CLI

Allowed:

- the application-service implementation;
- the new CLI subcommand;
- deterministic CLI serialization;
- reuse of existing Task 10 service and persistence functions;
- focused additions to shared schemas only when no database schema change is required.

Forbidden:

- HTTP API routes;
- migration changes;
- frontend work;
- Task 8/9/10 semantic changes.

### 3.3 Slice E3 — HTTP API

Allowed only after E1 and E2 are merged and their post-merge main CI is successful.

Allowed:

- a thin FastAPI adapter;
- request/response transport schemas;
- stable status-code and error-envelope behavior;
- route registration;
- API contract and integration tests.

Forbidden:

- business logic in the route module;
- direct model fitting or prediction in the route module;
- duplicate validation that can drift from the application service;
- migration or frontend work.

---

## 4. Application-service contract

### 4.1 Module

Binding implementation path for Slice E2:

`backend/app/rolling_backtest/replay_trained_service.py`

The service is the only new production boundary authorized to open `replay_trained_model` execution. Existing historically-available replay behavior must remain unchanged.

### 4.2 Public operation

The implementation must expose an async operation equivalent to:

```python
async def execute_replay_trained_prediction(
    session: AsyncSession,
    *,
    request: ReplayTrainedExecutionRequest,
) -> ReplayTrainedExecutionResult:
    ...
```

The exact Python type layout may be refined during E1, but the semantic fields below are binding.

### 4.3 Required request identity

`ReplayTrainedExecutionRequest` must contain explicit values for:

- `model_policy`, exactly `"replay_trained_model"`;
- `task12_policy_version`;
- `replay_attempt_id`;
- `replay_node_id`;
- `scenario_id`;
- `forecast_cutoff_at`;
- `training_cutoff_at`;
- `allowed_training_season_ids`;
- canonical training-manifest content;
- canonical model-config content;
- deterministic seed or seed-derivation identity;
- exact Task 8 identity when Task 8 features are consumed;
- exact `task9_run_id`;
- exact `task9_result_hash`;
- replay provenance, including replay code version;
- prediction input rows or their exact frozen source identity;
- an explicit idempotency key;
- an explicit caller/request identity for audit.

No required identity may be inferred from wall-clock time or selected through latest-row behavior.

### 4.4 Required execution order

The service must perform the following semantic sequence:

1. require the explicit `replay_trained_model` policy;
2. validate timezone-aware cutoffs and `training_cutoff_at <= forecast_cutoff_at`;
3. validate feature, label, and artifact visibility at the training cutoff;
4. apply deterministic training-row and label-availability filtering;
5. reject an empty filtered training set with a structured blocker;
6. build the canonical training manifest and identity hashes;
7. delegate training to the existing Task 10 residual-model training service without modifying its algorithm;
8. persist or load the exact training/artifact identity through existing integrity loaders;
9. verify JSON-side and manifest-side artifact identities;
10. load and verify the exact replay-produced Task 9 binding;
11. delegate prediction to the existing Task 10 residual-model prediction service without modifying its algorithm;
12. bind the prediction to the exact replay attempt, node, artifact, Task 9 run, and Task 9 result hash;
13. emit `model_policy = "replay_trained_model"` in the prediction identity;
14. produce a deterministic audit payload and result identity;
15. return the same semantic result for an identical idempotent replay request.

Skipping any step or replacing it with an implicit selection is forbidden.

### 4.5 Runtime gate rule

The runtime gate is opened only for requests entering the new Slice E service and satisfying every contract in §4.3-§4.4.

The implementation must not globally change the historical replay validator to accept replay-trained requests without the full Slice E request context.

Acceptable implementation patterns include:

- an additive policy validator dedicated to Slice E; or
- a narrowly scoped explicit gate parameter that cannot default to enabled.

The default and all pre-Slice-E call paths must remain closed to `replay_trained_model`.

---

## 5. Persistence and schema preflight

Slice E does not authorize a migration.

Before E1 is converted into E2 implementation, the implementation round must prove that existing persistence can represent and reload, without loss:

- `model_policy`;
- replay attempt and node identity;
- forecast and training cutoffs;
- training manifest hash;
- training dataset hash;
- model config hash;
- model artifact hash;
- model code and policy versions;
- exact Task 9 run id and result hash;
- prediction hash and prediction run identity;
- idempotency identity;
- audit identity.

If any required field cannot be persisted or reconstructed through existing canonical payload/artifact storage, implementation must stop with:

`TASK012_SLICE_E_SCHEMA_GAP_REQUIRES_SEPARATE_AMENDMENT`

No field may be silently dropped, placed only in logs, or reconstructed from current state.

---

## 6. CLI contract

### 6.1 Entry point

Existing module:

`python -m backend.app.rolling_backtest.cli`

New subcommand:

`replay-trained-predict`

### 6.2 Flag grammar

```text
python -m backend.app.rolling_backtest.cli replay-trained-predict \
  --request-json <absolute-path> \
  --output-json <absolute-path> \
  [--overwrite <never|missing|always>] \
  [--quiet]
```

The request file must contain the complete §4.3 request identity. The CLI must not accept convenience flags that select current/latest runs.

### 6.3 CLI behavior

- parse the request as UTF-8 JSON;
- reject duplicate keys;
- validate through the same application-service request schema used by the API;
- call the Slice E service exactly once;
- write canonical UTF-8 JSON with sorted keys and deterministic separators;
- never write a partial success file;
- use atomic write/rename behavior;
- treat an existing byte-identical result according to the overwrite policy;
- never merge results from separate replay attempts.

### 6.4 Exit codes

- `0`: success or byte-identical idempotent replay;
- `2`: request-contract or policy error;
- `3`: structured TASK-012 blocker;
- `4`: IO failure;
- `5`: idempotency, hash, or existing-path conflict;
- `64`: CLI usage error.

The CLI must emit a deterministic JSON error/blocker envelope to stdout and a concise diagnostic to stderr.

---

## 7. HTTP API contract

### 7.1 Adapter module

Preferred additive module:

`backend/app/api/rolling_backtest_replay_trained.py`

The module must be registered through the existing API router composition mechanism. It must not place Task 12 business logic in `main.py` or an unrelated Task 10 adapter.

### 7.2 Endpoints

#### Execute

`POST /api/v1/rolling-backtest/replay-trained-predictions`

Behavior:

- `201 Created`: first successful execution;
- `200 OK`: exact idempotent replay of the same request and canonical payload;
- `404 Not Found`: an explicitly named replay, Task 8, Task 9, training, artifact, or prediction identity does not exist;
- `409 Conflict`: idempotency, hash, identity, or cross-run substitution conflict;
- `422 Unprocessable Entity`: invalid request schema, cutoff, policy, or visibility contract;
- `500 Internal Server Error`: integrity failure with a stable non-leaking envelope.

#### Retrieve

`GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}`

Retrieval must load an exact persisted identity. It must not select the latest prediction for an attempt, node, scenario, or policy.

### 7.3 Stable error envelope

```json
{
  "error": {
    "code": "TASK012_STABLE_CODE",
    "message": "Stable public message.",
    "blocker": null,
    "identity": {}
  }
}
```

The adapter must not expose tracebacks, SQL text, driver errors, local filesystem paths, environment variables, model binary bytes, or secrets.

### 7.4 Required public codes

At minimum:

- `TASK012_REPLAY_TRAINED_INPUT_INVALID`;
- `TASK012_REPLAY_TRAINED_NOT_FOUND`;
- `TASK012_REPLAY_TRAINED_CONFLICT`;
- `TASK012_REPLAY_TRAINED_BLOCKED`;
- `TASK012_REPLAY_TRAINED_INTEGRITY_ERROR`.

Internal blocker codes from the TASK-012 taxonomy must remain available inside the structured blocker payload.

---

## 8. Idempotency and conflict contract

An execution is idempotent only when all canonical request fields and all derived identities match exactly.

The following must produce conflict, never silent reuse:

- same idempotency key with different canonical request payload;
- same replay attempt with a different replay node identity;
- same artifact hash with different manifest/config content;
- same prediction identity with a different Task 9 run or result hash;
- same request with a different policy version, code version, seed, or cutoff;
- historical and replay-trained policies attempting to share a prediction identity.

The implementation must reuse existing persistence conflict semantics when they preserve these distinctions. It must not collapse TASK-012 conflicts into a generic success response.

---

## 9. Audit contract

Every successful, blocked, or rejected Slice E attempt must produce or return an audit identity containing:

- request identity and idempotency key;
- requested and accepted policy;
- replay attempt, node, scenario, and cutoff identities;
- training manifest, dataset, config, and artifact hashes;
- exact Task 8 and Task 9 identities when present;
- prediction run id and prediction hash when produced;
- blocker code and deterministic payload when blocked;
- no-leakage validation summary;
- deterministic serialization version;
- code and policy versions.

Runtime timestamps may be included as non-authoritative metadata but must not affect canonical hashes.

---

## 10. Contract-test requirements

Slice E1 must add tests covering at least:

1. pre-Slice-E call paths still reject `replay_trained_model`;
2. the explicit Slice E service accepts only `replay_trained_model`;
3. missing or implicit policy is rejected;
4. post-cutoff features or labels are rejected or excluded according to the frozen contract;
5. empty filtered training data returns the canonical blocker;
6. exact Task 9 run id and result hash are required;
7. cross-attempt, cross-node, and cross-run substitutions are rejected;
8. JSON/manifest artifact mismatch is rejected;
9. identical requests produce the same canonical identities;
10. idempotent re-execution returns the same semantic result;
11. same idempotency key with different payload conflicts;
12. replay-trained output carries `model_policy = "replay_trained_model"`;
13. historical and replay-trained comparison outputs remain separate;
14. CLI rejects relative request/output paths;
15. CLI output is byte-identical for identical requests;
16. API first execution is 201 and exact replay is 200;
17. API stable 404/409/422/500 envelopes do not leak internals;
18. GET requires an exact prediction run id;
19. no API or CLI code uses latest/current/most-recent selection;
20. existing historically-available replay tests remain unchanged and green.

Tests must not fabricate a successful business result by bypassing the real service boundary.

---

## 11. Allowed-file boundaries

### E1 contract tests

Expected files are limited to new or focused test modules and deterministic fixtures under:

- `backend/tests/rolling_backtest/`;
- `backend/tests/` for HTTP adapter contracts when required;
- `backend/tests/fixtures/` when a fixture location already exists.

No production files may change.

### E2 service + CLI

Expected production files are limited to:

- `backend/app/rolling_backtest/replay_trained_service.py`;
- `backend/app/rolling_backtest/cli.py`;
- narrowly required rolling-backtest schema/export modules;
- existing Task 10 service/persistence adapters only when an additive call boundary is required and semantics remain unchanged.

### E3 HTTP API

Expected production files are limited to:

- `backend/app/api/rolling_backtest_replay_trained.py`;
- the minimal router-registration file;
- transport-only schemas when required.

Any need to touch models, migrations, Task 8/9 algorithms, Task 10 model algorithms, workflow files, dependencies, or frontend code is a stop condition.

---

## 12. Stop conditions

Implementation must stop and return to design when:

1. existing persistence cannot losslessly reload the required TASK-012 identity;
2. a database migration is required;
3. the service would need post-cutoff features or labels;
4. a deterministic training or artifact hash cannot be reproduced;
5. current/latest/most-recent fallback is needed;
6. historically-available-model behavior would change;
7. Task 8, Task 9, or Task 10 algorithm semantics would change;
8. the API or CLI would need to fabricate missing business state;
9. cross-run artifact reuse is required;
10. the adapter cannot delegate to one shared application-service contract;
11. a request cannot be bound to an exact replay attempt, node, Task 9 result, artifact, and prediction identity.

---

## 13. Acceptance and governance

This amendment is complete only when its docs-only PR is merged and its exact merge commit has a successful `main` push CI.

After design freeze:

- E1 requires separate implementation authorization;
- E1 must be contract-tests only;
- E2 requires separate authorization after E1 is merged and green;
- E3 requires separate authorization after E2 is merged and green;
- no implementation PR may become Ready or merge without separate authorization.

Required status before this amendment merges:

```text
TASK012_SLICE_E_API_CLI_AMENDMENT_DRAFT
IMPLEMENTATION_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```

Final design position:

Slice E may expose replay-trained prediction only through an explicit, deterministic, auditable application-service boundary. CLI and HTTP are thin adapters over that service. No adapter may infer current state, bypass exact identity checks, silently fall back to a historical model, or present validation-only helpers as completed model execution.
