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
FastAPI dependency overrides. Every operation checks actor identity, source
system, API channel, and the operation permission. No wildcard or fallback
scope is accepted.

The ASGI middleware limits actual-harvest JSON write bodies to 5,242,880 bytes
while receiving chunks, not only through `Content-Length`. Append pages contain
1-500 records. Preview uses a versioned keyset token, defaults to 50 records,
and caps pages at 100. Responses use a stable envelope and never expose SQL
identifiers, credentials, raw request bodies, or tracebacks.

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
never deletes records or seal evidence. Sealed records are immutable.

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

Local validation completed on the isolated worktree:

- `uv lock --check` passed.
- Ruff check and format check passed for the I4 application and test paths.
- `uv run mypy app` passed.
- I4 targeted tests passed (`24 passed`).
- Full actual-harvest suite passed (`180 passed, 1 skipped`).
- Core forecast and S1 regression passed (`154 passed`).
- Agent regression passed (`359 passed`).
- Alembic/API regressions passed (`8 passed` across the targeted commands).
- `uv run alembic -c backend/alembic.ini heads` returned the single head
  `0018_actual_harvest_import_staging`.
- Local PostgreSQL was not run because no isolated PostgreSQL profile was
  available; the marked PostgreSQL lifecycle test is guarded by
  `RUN_POSTGRES_INTEGRATION=1` and is assigned to `postgres-domain-1`.

The exact-head PR CI and artifact evidence are recorded in the Draft PR body
after push. No PostgreSQL pass is claimed locally.
