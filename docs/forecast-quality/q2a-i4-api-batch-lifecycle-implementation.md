# Q2A-I4 actual-harvest API batch lifecycle

## Boundary

Q2A-I4 adds the API application boundary over the existing I1-I3 actual-harvest
staging schema. The exact implementation base is
`e23466e8b92c5a96fdb7fecf84be3b29b7d35850`. The development branch is
`codex/issue-102-q2a-i4-api-batch-lifecycle` and its isolated worktree is
`/Users/charles/Documents/blueberry-peak-forecast-agent-q2a-i4`.

The six implemented operations are:

- `POST /api/v1/actual-harvest/imports`
- `POST /api/v1/actual-harvest/imports/{import_id}/records`
- `GET /api/v1/actual-harvest/imports/{import_id}`
- `GET /api/v1/actual-harvest/imports/{import_id}/preview`
- `POST /api/v1/actual-harvest/imports/{import_id}/seal`
- `POST /api/v1/actual-harvest/imports/{import_id}/cancel`

Validation, errors, commit, spreadsheet orchestration, identity mapping,
season resolution, revision winner selection, labels, backtests, and forecast
changes are not implemented by I4.

## Authorization and limits

The default actor dependency fails closed with
`ACTUAL_HARVEST_AUTHORIZATION_UNAVAILABLE`. Tests inject an exact actor through
FastAPI dependency overrides. I4 freezes `BATCH_OWNER` authorization:

```text
AUTHORIZATION_POLICY=BATCH_OWNER
BATCH_OWNER_AUTHORIZATION=true
SOURCE_DOMAIN_SHARED_ADMIN=false
```

Create requires the actor identity to equal `submitted_by_identity`. Get,
preview, append, seal, and cancel require the same identity as the persisted
batch owner, exact source-system and API-channel scope, and the operation
permission. Same-source non-owners receive the same 404 as an unknown batch;
missing operation permission remains a 403. No wildcard, alias, trim fallback,
or cross-actor administration is accepted.

The ASGI middleware limits only these POST paths: the create route and
`/{import_id}/records`, `/{import_id}/seal`, and `/{import_id}/cancel` under
`/api/v1/actual-harvest/imports/`. It limits JSON write bodies to 5,242,880
bytes while receiving chunks, not only through `Content-Length`. Append pages
contain 1-500 records. Preview uses a versioned keyset token, defaults to 50
records, and caps pages at 100. Responses use a stable envelope and never
expose SQL identifiers, credentials, raw request bodies, or tracebacks.

Seal and cancel use the `EMPTY_JSON_BODY` contract: callers must send `{}` with
`Content-Type: application/json`; extra fields are rejected with
`API_REQUEST_INVALID`, missing or unsupported content types are rejected before
route handling, and an empty JSON body is a sanitized 422 validation error.

## State and transactions

The I4 state matrix is:

```text
RECEIVED -> UPLOADING
UPLOADING + UNSEALED -> UPLOADING + UNSEALED
UPLOADING + UNSEALED -> SEALED + SEALED
RECEIVED | UPLOADING | SEALED | CANCELLED -> CANCELLED
```

The application boundary owns the transaction. Lifecycle persistence does not
commit, rollback, or close the session. Mutation paths lock the batch row with
`SELECT ... FOR UPDATE` before checking status or changing records. An append
page is all-or-nothing; counts are updated in the same transaction. Sealing
recomputes the authoritative record count and all seal metadata. Cancellation
never deletes records or seal evidence. Records cannot be appended, modified,
or deleted after sealing, while the batch may intentionally transition from
`SEALED` to `CANCELLED`.

```text
NO_POST_SEAL_RECORD_MUTATION=true
SEALED_BATCH_MAY_TRANSITION_TO_CANCELLED=true
CANCEL_PRESERVES_SEAL_EVIDENCE=true
```

## Idempotency and hashes

The API uses the existing database unique constraints for
`source_system + idempotency_key` and `source_system + external_batch_id`.
Insert races are recovered through a nested savepoint and a full canonical
payload comparison. Equal create payloads replay the original batch; different
payloads return a deterministic conflict. Equal complete append pages replay;
different revision content conflicts. No I5 revision-chain or winner logic is
performed.

Hash policy versions are:

- `actual-harvest-api-transport-hash-v1`
- `actual-harvest-canonical-batch-hash-v1`
- `actual-harvest-seal-manifest-v1`

Canonical JSON is UTF-8, key sorted, enum stable, timezone-aware, and exact
Decimal based. Record hashes include all client business fields, including
`source_note`, and exclude database IDs, server timestamps, and spreadsheet
provenance. The server raw payload hash is a reconstructed canonical API
transport manifest, not a byte-for-byte HTTP hash. Canonical batch and seal
manifest hashes sort records by source system, logical record ID, revision
number, and revision ID; append page boundaries and insertion order therefore
do not change their input order.

## Preview semantics

Preview returns canonical staging records only. It explicitly reports
`validation_status=NOT_RUN` and `active_label_created=false`. It does not map
identity, resolve seasons, select revision winners, create labels, or claim
that records are validated.

## Database and exclusions

No migration, table, column, index, ORM shape, or repository transaction
semantics were added. The Alembic head remains
`0018_actual_harvest_import_staging`.

The persisted facts remain staging facts:

```text
STAGING_RECORD_IS_NOT_ACTIVE_LABEL
SEALED_IS_NOT_VALIDATED
SEALED_IS_NOT_COMMITTED
CANCELLED_DATA_IS_NOT_DELETED
NO_PRIMARY_LABEL_CREATED
```

Q2A-I5 through I8, Q2B, Q3, Issue #102/#99 changes, branch cleanup, and
worktree cleanup remain outside this slice.

## Validation record

The remaining acceptance-gap regressions are explicit rather than inferred from
empty-batch behavior:

```text
POSTGRES_SEAL_CANCEL_NONEMPTY_RECORD_PRESERVATION=true
POSTGRES_SEAL_EVIDENCE_EXACT_EQUALITY=true
CANONICAL_KEYSET_ORDER_EXACTLY_ASSERTED=true
PAGINATION_NO_DUPLICATE=true
PAGINATION_NO_OMISSION=true
```

The PostgreSQL seal-versus-cancel race starts with one persisted canonical
record, snapshots its business fields and both counters, and verifies that the
record remains unchanged. If seal wins, the cancelled batch's six seal
evidence fields exactly equal the seal result; if cancel wins, the seal is
rejected and all seal evidence remains null. The API pagination regression
appends three records in non-canonical order and walks `page_size=1` until the
final token is null, asserting sorted canonical keys with no duplicate or
omitted record.

Local validation completed on the isolated worktree:

- `uv lock --check` passed.
- Ruff check and format check passed for the I4 application and test paths.
- `uv run mypy app` passed.
- I4 targeted tests passed (`46 passed`).
- Full actual-harvest suite passed (`202 passed, 5 skipped`); the five skips
  are the PostgreSQL lifecycle tests because Docker is unavailable locally.
- Core forecast and S1 regression passed (`154 passed`).
- Agent regression passed (`359 passed`).
- Existing API/lifespan regressions passed (`22 passed`), and the existing
  Alembic regressions passed (`7 passed`). The specifically named source,
  forecast-quality Q1, and V0.1 S1 contract test files are not present in this
  checkout, so no result is claimed for those absent paths.
- `uv run alembic -c backend/alembic.ini heads` returned the single head
  `0018_actual_harvest_import_staging`.
- Local PostgreSQL was not run because no isolated PostgreSQL profile was
  available; the PostgreSQL lifecycle tests are guarded by
  `RUN_POSTGRES_INTEGRATION=1` and are assigned to `postgres-domain-1`.

Exact-head PR CI for the acceptance-gap commit:

- Run `29635373454`, Head `bebcb84a4c2ac2b1b2aa274dad244b8a88ca4146`,
  completed/success.
- All eight PR jobs passed; `full-suite-canary` was skipped by PR design.
- JUnit aggregate: `3251 total / 3226 passed / 0 failures / 0 errors /
  25 skipped`.
- `postgres-domain-1`: `286 total / 286 passed / 0 failures / 0 errors /
  0 skipped`; all five `test_postgres_i4_*` lifecycle tests were collected
  and passed, including the non-empty seal-versus-cancel test.
- Artifacts, all bound to the exact Head and unexpired:
  - `8426988495` `postgres-domain-2-results`
    `sha256:a96815eeb5fc887a0eca0938a015deb08302c4ec13b5d0aa845a4aeb42fbe33c`
  - `8426948946` `postgres-domain-1-results`
    `sha256:1be2334ea766735170163d87e2917231ffaf2d68bc82ccb3ce60e9b8c15f14cd`
  - `8426940590` `unit-contract-golden-results`
    `sha256:f51f2c280d088e946ad53a2dc944efd573fd3863bf69f980becf0a6c79c0ad1e`
  - `8426927130` `postgres-task11-results`
    `sha256:371f19146070d5e175be3695173d766db64c17b5ca11d8be313981d0c9ec665b`
  - `8426918836` `postgres-migration-results`
    `sha256:53457fdc9fde5dd6bf2d6a590c8305f1becf4000fe3f64a69c75d02fb67eb14b`
  - `8426918030` `postgres-concurrency-results`
    `sha256:5e89f07d0d7133802cb77a80cf073f02046ec3c62db0378532f36db7128d8be8`

No PostgreSQL pass is claimed locally; the PostgreSQL acceptance evidence is
from this exact-head CI run.
