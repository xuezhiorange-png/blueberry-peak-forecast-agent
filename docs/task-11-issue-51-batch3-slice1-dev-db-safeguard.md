# Batch 3 Slice 1 — dev-DB safeguard + PostgreSQL identity logging baseline

**Status**: Implementation note for the Slice 1 PR (Draft). The actual
design freeze lives in `docs/task-11-issue-51-batch3-pg-isolation-design.md`
(merged via PR #56).

## What Slice 1 delivers

A reusable, fail-closed dev-DB safeguard and identity-logging
baseline. Pure Python — no DB connection, no subprocess, no
production-code mutation.

### 1. New module — `backend/tests/postgres_test_support.py`

Public surface (frozen for Slice 2–5 to consume):

- `FORBIDDEN_DATABASE_NAMES` — `frozenset` of dev-DB names that must
  never appear in a test profile (`blueberry_peak`, `blueberry_peak_dev`,
  `blueberry_peak_production`, `blueberry_dev`, `blueberry_prod`,
  `postgres`).
- `FORBIDDEN_DATABASE_PORTS` — `frozenset` of forbidden ports
  (`5432` only).
- `PRODUCTION_APP_ENVS` — `frozenset` of APP_ENV values that must
  never appear in a test profile (`production`, `prod`, `live`,
  `staging`, `stage`, `stg`).
- `SAFE_TEST_APP_ENVS` — `frozenset` of APP_ENV values that mark a
  profile as safe-for-test (`test`, `testing`, `ci`).
- `DEFAULT_TEST_DB_NAME` / `DEFAULT_TEST_DB_HOST` / `DEFAULT_TEST_DB_PORT`
  / `DEFAULT_TEST_APP_ENV` — safe defaults the resolver fills in
  when env is empty (one-command contract).
- `PostgresTestIdentity` — frozen dataclass carrying `database_name`,
  `database_host`, `database_port`, `app_env`, `worker_id`,
  `safety_profile_source`, `used_defaults`, plus forward-compat
  fields (`schema_name`, `migration_head`).
- `resolve_postgres_test_identity(env=None, *, worker_id="master")`
  — pure resolver. Marks `used_defaults` for any field that was
  silently defaulted (so the validator can detect dev-DB fallback).
- `validate_postgres_test_identity(identity)` — fail-closed validator.
  Raises `ValueError` on any unsafe profile (forbidden name,
  forbidden port + localhost, production APP_ENV, unknown APP_ENV,
  silent fallback to non-safe default).
- `assert_safe_postgres_test_identity(env=None, *, worker_id="master")`
  — combined wrapper. Independently checks `DATABASE_URL` for dev-DB
  patterns. Returns the resolved identity.
- `format_postgres_test_identity(identity)` — deterministic one-line
  summary. Never includes the `DATABASE_URL` value or any password.

### 2. New tests — `backend/tests/safety/test_dev_db_safeguard_slice1.py`

30 new tests covering:

- Resolver: safe defaults / partial env / worker_id override.
- Validator (rejection): forbidden DB name, dev-DB pattern,
  forbidden port + localhost, each production APP_ENV, unknown
  APP_ENV, silent fallback to non-safe default.
- Validator (acceptance): each safe APP_ENV, safe defaults,
  worker-suffixed test DB.
- DATABASE_URL safety: dev-DB name pattern, dev port, test
  profile URL accepted, empty URL accepted.
- Combined wrapper: full identity return value, worst-case profile.
- Formatter: required fields present, no DATABASE_URL leak, defaults
  marker surfaced.
- Constants self-audit: forbidden sets populated, disjointness
  between production and safe sets, default test DB safe.

### 3. Existing scripts preserved

- `backend/scripts/postgres_test_db.sh` — unchanged. The existing
  bash guard remains the first-line-of-defense; the new Python
  validator is a second-line complement for safety tests and
  future Python-side callers.
- `Makefile` — unchanged. The existing `guard:` target remains
  the one-command-contract guard. Slice 1 does NOT modify the
  Makefile because the existing guard already covers all 5
  rejection cases.
- `docker-compose.test.yml` — unchanged.
- `.github/workflows/ci.yml` — **UNCHANGED** (Slice 1 explicit
  boundary).

## What Slice 1 explicitly does NOT do

| Out of scope | Defer to | Notes |
|--------------|----------|-------|
| CI workflow changes | Batch 2 (Issue #50) | CI still bypasses the guard directly via env vars in `ci.yml`; tracked as a known gap, not closed by this slice. |
| TRUNCATE removal | Slice 5 | `isolate_master_data_tables` autouse fixture stays. The new `postgres_test_support` module is consumed by Slices 2/5 but does not touch the TRUNCATE code path. |
| Transaction / savepoint / rollback fixture refactor | Slice 2 | `db_session` fixtures stay as-is in their 5 duplicate locations. |
| Migration isolated schema/DB | Slice 3 | The validator already accepts worker-suffixed test DB names (`*_test_gw0`) for forward-compat, but no migration tests consume it yet. |
| Concurrency / real-commit isolation | Slice 4 | The validator surfaces `worker_id` so Slice 4 can route per-worker DBs. |
| Marker taxonomy overhaul | Batch 4 (per `docs/task-11-infra-test-environment.md`) | Slice 1 leaves the `postgres` marker mismatch (declared but unused) untouched; this is a Slice 2 concern. |
| Production code changes | never (Slice 1 boundary) | No `backend/app/**` touched. |
| Alembic migration changes | never (Slice 1 boundary) | No `backend/alembic/versions/**` touched. |
| Frontend changes | never (Slice 1 boundary) | No frontend touched. |
| Task 8 / Task 9 / Task 10 production semantics | never (Slice 1 boundary) | None touched. |

## Acceptance gates (per Slice 1 spec)

- **G1**: All new safety tests pass. (`pytest backend/tests/safety/test_dev_db_safeguard_slice1.py`)
- **G2**: Unsafe dev DB name rejected. (`test_validator_rejects_explicit_forbidden_db_name`)
- **G3**: Unsafe dev DB port rejected. (`test_validator_rejects_dev_port_with_localhost`)
- **G4**: Production-like APP_ENV rejected. (`test_validator_rejects_production_app_env`)
- **G5**: Unsafe DATABASE_URL / silent fallback rejected.
  (`test_database_url_with_dev_db_name_is_rejected`,
  `test_database_url_with_dev_port_is_rejected`,
  `test_validator_rejects_silent_fallback_to_dev_defaults`)
- **G6**: Identity logging available via
  `format_postgres_test_identity()` for shell / Makefile / safety
  test consumption. The current Slice 1 PR does NOT wire this into
  `postgres_test_db.sh` (would change shell-script behavior); wiring
  is left as a follow-up so Slice 1 stays additive. The Python
  helper IS the documented entry point.
- **G7**: `make test-pg` (`pytest -m postgres`) still selects 0 tests
  in this slice; marker mismatch is explicitly deferred to Slice 2
  per the Slice 1 boundary.
- **G8**: CI workflow unmodified. Verified by `git diff origin/main`
  showing no `.github/workflows/**` changes.
- **G9**: Production code unmodified. Verified by `git diff origin/main`
  showing no `backend/app/**` changes.
- **G10**: Alembic migrations unmodified. Verified by `git diff origin/main`
  showing no `backend/alembic/versions/**` changes.

## Files changed in Slice 1

- `backend/tests/postgres_test_support.py` — NEW (15,484 bytes).
- `backend/tests/safety/test_dev_db_safeguard_slice1.py` — NEW
  (15,140 bytes, 30 tests).
- `docs/task-11-issue-51-batch3-slice1-dev-db-safeguard.md` — NEW
  (this file).

Total: 3 files changed, 0 files in forbidden paths.

## Open follow-ups for Slices 2–6

- **Slice 2** should call `assert_safe_postgres_test_identity()` at
  the start of the new transaction+savepoint+rollback fixture so
  every test's identity is validated before writes.
- **Slice 3** should pass `worker_id=f"gw{i}"` per `pytest-xdist`
  worker so migration tests route to per-worker DBs.
- **Slice 4** should consume the `format_postgres_test_identity()`
  helper for explicit worker-identity logging at the start of each
  concurrency test.
- **Slice 5** should remove the legacy `_truncate_master_data()`
  function and replace it with calls to the new isolation layer.
- **Slice 6** (Batch 2 handoff) should call the validator from each
  CI job's setup step so CI bypasses the local-env-var guard.
- **Batch 2 (Issue #50)** can re-authorize editing
  `.github/workflows/ci.yml` to call
  `python -c "from backend.tests.postgres_test_support import assert_safe_postgres_test_identity; assert_safe_postgres_test_identity()"`
  in each CI job setup.