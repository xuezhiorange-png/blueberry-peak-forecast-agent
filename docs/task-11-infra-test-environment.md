# Issue #23 Batch 1 — Local Test Environment

## What this provides

A reproducible, isolated local PostgreSQL test harness for the
blueberry backend.

| Setting | Value |
|---|---|
| Database name | `blueberry_peak_test` |
| Port | `55432` (NOT 5432 — that port is reserved for the development DB) |
| `APP_ENV` | `test` |
| Temporary volume | `blueberry_postgres_test_data` (Docker named volume; removed by `make test-clean`) |
| Health check | `pg_isready -U postgres -d blueberry_peak_test` |
| Network | dedicated bridge `blueberry_test_net` |

## Usage

```bash
# Bring up the test harness, wait for healthy, run postgres-tagged tests.
make test-pg

# Tear down the harness and drop its volume.
make test-clean

# Run non-integration unit tests only (no Docker required).
make test-unit
```

The `make test-pg` target runs `docker compose -f docker-compose.test.yml up -d`,
waits up to 60 s for `pg_isready`, then runs `pytest -m postgres` with
`APP_ENV=test POSTGRES_HOST=localhost POSTGRES_PORT=55432 POSTGRES_DB=blueberry_peak_test`.

## Dev-DB safeguard

The harness is **fail closed**. It refuses to start unless every one of
the following is satisfied:

* `APP_ENV=test`
* `POSTGRES_DB=blueberry_peak_test` (not `blueberry_peak` — the dev DB)
* `POSTGRES_PORT=55432` (not `5432` — the dev DB port)

If any condition is wrong, the script exits with a clear error
message and a non-zero status. This is enforced in two layers:

1. **`backend/scripts/postgres_test_db.sh`** — bash-level guard.
2. **`Makefile`** (`guard:` target) — Python guard invoked via
   `$(shell ...)` before any docker compose call.

Both layers reject the dev-DB profile independently, so a bug in one
layer is caught by the other.

## Files added by this PR

| File | Purpose |
|---|---|
| `docker-compose.test.yml` | isolated PostgreSQL test profile |
| `Makefile` | one-command targets (`test-pg` / `test-clean` / `test-unit`) |
| `backend/scripts/postgres_test_db.sh` | bash guard + start helper |
| `backend/scripts/wait_for_postgres.sh` | readiness polling |
| `backend/scripts/reset_test_db.sh` | idempotent teardown + volume drop |
| `backend/tests/safety/test_dev_db_protection.py` | safety tests for the safeguard |
| `docs/task-11-infra-test-environment.md` | this document |
| `pyproject.toml` | minimal pytest marker (`postgres`) — only this section touched |

## What this PR does NOT do (out of scope)

The following are **deferred** to subsequent batches of Issue #23 and
require **separate Charles authorization** before they can be touched:

* CI workflow split (`.github/workflows/postgres-integration.yml`,
  de-duplication of `ci.yml` jobs). → Batch 2.
* Marker taxonomy overhaul (adding the other 11 markers from
  `Issue #23 §4`). → Batch 3.
* Fixture refactor (`backend/tests/factories/` / `assertions/` /
  `db/`). → Batch 3.
* Whole-DB `TRUNCATE` audit and removal. → Batch 4.
* CI diagnostics polish (`--durations=30`, etc.). → Batch 4.
* Migration / concurrency isolation schema. → out of Batch 1.

This PR is **infra-only** (CI workflow / docker compose / makefile /
shell scripts / conftest / pytest config / tests). It does NOT touch
`backend/app/**`, `backend/app/models/**`, `backend/alembic/versions/**`,
or any Task 8/9/10/11 production semantics.
