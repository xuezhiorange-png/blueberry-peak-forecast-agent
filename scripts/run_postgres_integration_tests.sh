#!/usr/bin/env bash
# run_postgres_integration_tests.sh — one-command local PostgreSQL test runner
#
# Starts an isolated PostgreSQL container, runs migrations, executes
# integration tests in two groups (transactional + special), and tears down.
#
# Usage:
#   ./scripts/run_postgres_integration_tests.sh
#   ./scripts/run_postgres_integration_tests.sh backend/tests/integration/test_foo.py -vv
set -Eeuo pipefail

COMPOSE_FILE="docker-compose.test.yml"
PROJECT_NAME="blueberry-peak-test"
NETWORK="${PROJECT_NAME}_default"

export APP_ENV=test
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=55432
export POSTGRES_DB=blueberry_peak_test
export POSTGRES_USER=blueberry_test
export POSTGRES_PASSWORD=blueberry-test-only
export RUN_POSTGRES_INTEGRATION=1

EXTRA_PYTEST_ARGS=("$@")

cleanup() {
  echo "::group::Teardown"
  docker compose \
    -f "$COMPOSE_FILE" \
    -p "$PROJECT_NAME" \
    down -v --remove-orphans 2>/dev/null || true
  echo "::endgroup::"
}
trap cleanup EXIT

echo "=== Starting test PostgreSQL ==="
docker compose \
  -f "$COMPOSE_FILE" \
  -p "$PROJECT_NAME" \
  up -d postgres-test

echo "=== Waiting for healthcheck ==="
for i in $(seq 1 60); do
  status=$(docker inspect --format='{{.State.Health.Status}}' \
    "$(docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps -q postgres-test)" 2>/dev/null || echo "starting")
  if [ "$status" = "healthy" ]; then
    echo "PostgreSQL healthy after ${i}s"
    break
  fi
  if [ "$i" -eq 60 ]; then
    echo "ERROR: PostgreSQL did not become healthy"
    docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs postgres-test
    exit 1
  fi
  sleep 1
done

echo "=== Verifying database identity ==="
python3 -c "
import asyncio, os, asyncpg

async def main():
    conn = await asyncpg.connect(
        host=os.environ['POSTGRES_HOST'],
        port=int(os.environ['POSTGRES_PORT']),
        database=os.environ['POSTGRES_DB'],
        user=os.environ['POSTGRES_USER'],
        password=os.environ['POSTGRES_PASSWORD'],
    )
    db = await conn.fetchval('SELECT current_database()')
    await conn.close()
    expected = os.environ['POSTGRES_DB']
    assert db == expected, f'Expected {expected}, got {db}'
    print(f'Database identity verified: {db}')

asyncio.run(main())
"

echo "=== Running Alembic migrations ==="
uv run alembic -c backend/alembic.ini upgrade head

if [ ${#EXTRA_PYTEST_ARGS[@]} -gt 0 ]; then
  echo "=== Running specified tests ==="
  uv run pytest "${EXTRA_PYTEST_ARGS[@]}" -vv --tb=long \
    --timeout=120 --timeout-method=thread
  exit_code=$?
  echo "=== Tests finished with exit code $exit_code ==="
  exit "$exit_code"
fi

echo "=== Running transactional integration tests ==="
uv run pytest \
  -m "integration and not postgres_real_commit and not postgres_migration and not postgres_concurrency" \
  -vv --tb=long \
  --timeout=120 --timeout-method=thread \
  --junitxml=reports/test-results/postgres-transactional.xml

echo "=== Running special integration tests ==="
uv run pytest \
  -m "postgres_real_commit or postgres_migration or postgres_concurrency" \
  -vv --tb=long \
  --timeout=120 --timeout-method=thread \
  --junitxml=reports/test-results/postgres-special.xml

echo "=== All integration tests passed ==="
