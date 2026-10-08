#!/usr/bin/env bash

# Reproduce the existing full-suite-canary lifecycle for the dedicated,
# pull-request-only warning evidence job.  The pytest selector and execution
# options remain the canary options; only plugin registration, capture paths,
# and post-processing are added.

set -euo pipefail

ledger_root="reports/warning-ledger"
raw_root="${ledger_root}/raw"
mkdir -p "${raw_root}"
export WARNING_LEDGER_DIR="${raw_root}"

cleanup() {
  set +e
  if [[ -z "${ISOLATED_DB_NAME:-}" ]]; then
    return 0
  fi
  python - <<'PY'
import asyncio
import os

import asyncpg
from backend.tests.migration_isolation_helpers import (
    assert_safe_isolated_db_name,
    resolve_isolated_db_name,
)


async def main() -> None:
    job_name = os.environ.get("ISOLATED_JOB_NAME")
    if job_name != "warning-ledger-evidence":
        print("::warning::unexpected warning-ledger cleanup identity")
        return
    expected_name = resolve_isolated_db_name(
        os.environ["GITHUB_RUN_ID"],
        os.environ["GITHUB_RUN_ATTEMPT"],
        job_name,
    )
    assert_safe_isolated_db_name(expected_name)
    if os.environ.get("ISOLATED_DB_NAME") != expected_name:
        print("::warning::warning-ledger database identity mismatch")
        return
    conn = await asyncpg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ.get("POSTGRES_ADMIN_DB", "blueberry_peak"),
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) "
            "FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            expected_name,
        )
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", expected_name
        )
        if exists:
            await conn.execute(f'DROP DATABASE "{expected_name}"')
            print(f"dropped isolated database {expected_name!r}")
    finally:
        await conn.close()


try:
    asyncio.run(main())
except Exception as exc:  # noqa: BLE001
    print(f"::warning::failed to drop warning-ledger database: {exc}")
PY
}

trap cleanup EXIT

python - <<'PY'
import asyncio
import os
import asyncpg


async def main() -> None:
    last_error = None
    for _ in range(30):
        try:
            conn = await asyncpg.connect(
                host=os.environ["POSTGRES_HOST"],
                port=int(os.environ["POSTGRES_PORT"]),
                database=os.environ["POSTGRES_DB"],
                user=os.environ["POSTGRES_USER"],
                password=os.environ["POSTGRES_PASSWORD"],
            )
            value = await conn.fetchval("SELECT 1")
            await conn.close()
            if value == 1:
                return
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1)
    raise SystemExit(f"PG not ready: {last_error}")


asyncio.run(main())
PY

ISOLATED_DB_NAME="$(python - <<'PY'
import os

from backend.tests.migration_isolation_helpers import (
    assert_safe_isolated_db_name,
    resolve_isolated_db_name,
)

name = resolve_isolated_db_name(
    os.environ["GITHUB_RUN_ID"],
    os.environ["GITHUB_RUN_ATTEMPT"],
    os.environ["ISOLATED_JOB_NAME"],
)
assert_safe_isolated_db_name(name)
print(name)
PY
)"
export ISOLATED_DB_NAME

python - <<'PY'
import asyncio
import os

import asyncpg


async def main() -> None:
    name = os.environ["ISOLATED_DB_NAME"]
    conn = await asyncpg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", name
        )
        if exists:
            raise SystemExit(
                f"isolated database {name!r} already exists; refusing to overwrite"
            )
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


asyncio.run(main())
PY

export POSTGRES_DB="${ISOLATED_DB_NAME}"
export DATABASE_URL="postgresql+asyncpg://blueberry_app:change-me-in-local-env@localhost:55432/${ISOLATED_DB_NAME}"

python - <<'PY'
from backend.tests.db.profile import assert_safe_postgres_test_identity

identity = assert_safe_postgres_test_identity(env=None)
print(
    "validated isolated PostgreSQL test identity: "
    f"database={identity.database_name!r} port={identity.port}"
)
PY

alembic -c backend/alembic.ini upgrade head

set +e
echo "PYTEST_CI_SEED=${PYTEST_CI_SEED:-$GITHUB_SHA}" >> "$GITHUB_STEP_SUMMARY"
pytest -p scripts.ci.warning_ledger.plugin -q --tb=long \
  --durations=30 \
  --junitxml="${ledger_root}/full.xml" \
  > "${ledger_root}/pytest.stdout.log" \
  2> "${ledger_root}/pytest.stderr.log"
pytest_status=$?
cat "${ledger_root}/pytest.stdout.log"
cat "${ledger_root}/pytest.stderr.log" >&2
printf '%s\n' "${pytest_status}" > "${ledger_root}/pytest.exitcode"
set -e

set +e
python scripts/ci/warning_ledger/postprocess.py \
  --raw-dir "${raw_root}" \
  --stdout "${ledger_root}/pytest.stdout.log" \
  --stderr "${ledger_root}/pytest.stderr.log" \
  --junitxml "${ledger_root}/full.xml" \
  --exitcode "${ledger_root}/pytest.exitcode" \
  --output-dir "${ledger_root}/artifacts" \
  --repository "${GITHUB_REPOSITORY}" \
  --base-sha "${BASE_SHA}" \
  --workflow-run-id "${GITHUB_RUN_ID}" \
  --job-id "${GITHUB_JOB}" \
  --pytest-command 'pytest -p scripts.ci.warning_ledger.plugin -q --tb=long --durations=30 --junitxml=reports/warning-ledger/full.xml' \
  --expected-signature-count 13 \
  --expected-passed 3423 \
  --expected-skipped 3
postprocess_status=$?
set -e

if [[ "${pytest_status}" -ne 0 ]]; then
  exit "${pytest_status}"
fi
exit "${postprocess_status}"
