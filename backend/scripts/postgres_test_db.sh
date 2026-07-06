#!/usr/bin/env bash
# postgres_test_db.sh — guard + start helper for Issue #23 Batch 1.
#
# Refuses to run unless the requested profile matches the local test
# profile exactly (DB name blueberry_peak_test, port 55432, APP_ENV=test,
# DATABASE_URL not pointing at dev DB). Fails closed via `exit 1` on any
# mismatch so CI / local cannot accidentally connect to the development
# database.

set -euo pipefail

# ---- guards -----------------------------------------------------------------

DB="${POSTGRES_DB:-blueberry_peak}"
HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-5432}"
ENV="${APP_ENV:-development}"
DB_URL="${DATABASE_URL:-}"

# --- DATABASE_URL check (must come BEFORE the individual env vars since
# DATABASE_URL is the most common dev leak vector). --------------------------
if [[ -n "$DB_URL" ]]; then
    if [[ "$DB_URL" == *"blueberry_peak"* && "$DB_URL" != *"blueberry_peak_test"* ]]; then
        echo "ERROR: DATABASE_URL points at the dev DB (got '$DB_URL')." >&2
        echo "Refusing to start test harness to avoid connecting to development DB." >&2
        exit 1
    fi
    if [[ "$DB_URL" == *"localhost:5432"* ]]; then
        echo "ERROR: DATABASE_URL points at localhost:5432 (dev port)." >&2
        exit 1
    fi
fi

# --- individual env var checks ----------------------------------------------

if [[ "$DB" != "blueberry_peak_test" ]]; then
    echo "ERROR: POSTGRES_DB must be 'blueberry_peak_test' (got '$DB')." >&2
    echo "Refusing to start test harness to avoid connecting to development DB." >&2
    exit 1
fi

if [[ "$PORT" != "55432" ]]; then
    echo "ERROR: POSTGRES_PORT must be '55432' (got '$PORT')." >&2
    echo "Port 5432 is reserved for the development database." >&2
    exit 1
fi

if [[ "$ENV" != "test" ]]; then
    echo "ERROR: APP_ENV must be 'test' (got '$ENV')." >&2
    exit 1
fi

# ---- start (delegated to docker compose) -------------------------------------

cd "$(dirname "$0")/../.."
exec docker compose -f docker-compose.test.yml up -d
