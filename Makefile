# Local development Makefile for Issue #23 Batch 1 (PostgreSQL test harness).
#
# Scope: one-command local test environment. NOT for CI (CI workflows
# live in .github/workflows/, out of scope for this Batch 1 PR).

# ---- guard rails (refuse to run with dev-DB env) -----------------------------

GUARD_OK := $(shell python3 -c "import os,sys;     db=os.environ.get('DATABASE_URL','');     host=os.environ.get('POSTGRES_HOST','localhost');     port=os.environ.get('POSTGRES_PORT','5432');     env=os.environ.get('APP_ENV','');     bad=(env!='test') or ('blueberry_peak' in db and '_test' not in db) or (host=='localhost' and port=='5432');     sys.exit(1 if bad else 0)" 2>/dev/null && echo 1 || echo 0)

guard:
	@test "$(GUARD_OK)" = "1" || (echo "ERROR: refuse to run test-pg with non-test env (APP_ENV=$$APP_ENV DATABASE_URL=$$DATABASE_URL POSTGRES_HOST=$$POSTGRES_HOST POSTGRES_PORT=$$POSTGRES_PORT)" && exit 1)

# ---- one-command targets -----------------------------------------------------

.PHONY: test-pg
test-pg: guard
	APP_ENV=test docker compose -f docker-compose.test.yml up -d
	bash backend/scripts/wait_for_postgres.sh
	APP_ENV=test POSTGRES_HOST=localhost POSTGRES_PORT=55432 POSTGRES_DB=blueberry_peak_test POSTGRES_USER=postgres POSTGRES_PASSWORD=postgres \
	  pytest -m postgres

.PHONY: test-clean
test-clean:
	docker compose -f docker-compose.test.yml down -v

.PHONY: test-unit
test-unit:
	APP_ENV=test pytest -m "not postgres and not integration"
