#!/usr/bin/env bash
# reset_test_db.sh — tear down the test harness and drop its volume.
#
# Equivalent to `make test-clean`. Safe to run even if the harness is not
# currently up; `docker compose down -v` is idempotent.

set -euo pipefail

cd "$(dirname "$0")/../.."
exec docker compose -f docker-compose.test.yml down -v
