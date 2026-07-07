#!/usr/bin/env bash
# wait_for_postgres.sh — poll for test PostgreSQL readiness.
#
# Polls `pg_isready` against the local test profile (port 55432, db
# blueberry_peak_test) up to 60 seconds. Exits 0 on healthy, 1 on timeout.

set -euo pipefail

HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-55432}"
USER="${POSTGRES_USER:-postgres}"
DB="${POSTGRES_DB:-blueberry_peak_test}"
TIMEOUT="${TIMEOUT:-60}"

START=$(date +%s)
DEADLINE=$((START + TIMEOUT))

while true; do
    if pg_isready -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" >/dev/null 2>&1; then
        echo "postgres-test: ready (host=$HOST port=$PORT db=$DB)"
        exit 0
    fi
    NOW=$(date +%s)
    if [[ "$NOW" -ge "$DEADLINE" ]]; then
        echo "ERROR: postgres-test not ready after ${TIMEOUT}s" >&2
        exit 1
    fi
    sleep 1
done
