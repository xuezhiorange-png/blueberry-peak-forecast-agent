# Local development Makefile for Issue #23 Batch 1 (PostgreSQL test harness).
#
# Scope: one-command local test environment. NOT for CI (CI workflows
# live in .github/workflows/, out of scope for this Batch 1 PR).

# ---- defaults: ensure plain `make test-pg` works without exporting env ---

APP_ENV ?= test
POSTGRES_HOST ?= localhost
POSTGRES_PORT ?= 55432
POSTGRES_DB ?= blueberry_peak_test
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= ***
DATABASE_URL ?= postgresql://$(POSTGRES_USER):***@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)

# Guard evaluates the make-level defaults so a plain `make test-pg`
# works without exporting anything. Fails closed if the user explicitly
# overrides to a dev-DB profile.
GUARD_OK := $(shell APP_ENV='$(APP_ENV)' POSTGRES_HOST='$(POSTGRES_HOST)' POSTGRES_PORT='$(POSTGRES_PORT)' POSTGRES_DB='$(POSTGRES_DB)' DATABASE_URL='$(DATABASE_URL)' python3 -c "import os,sys; \
    db=os.environ.get('POSTGRES_DB',''); \
    host=os.environ.get('POSTGRES_HOST','localhost'); \
    port=os.environ.get('POSTGRES_PORT','5432'); \
    env=os.environ.get('APP_ENV',''); \
    url=os.environ.get('DATABASE_URL',''); \
    bad = (env != 'test') \
        or ('blueberry_peak' in db and '_test' not in db) \
        or (port == '5432' and host == 'localhost') \
        or ('blueberry_peak' in url and '_test' not in url) \
        or ('localhost:5432' in url); \
    sys.exit(1 if bad else 0)" 2>/dev/null && echo 1 || echo 0)

guard:
	@test "$(GUARD_OK)" = "1" || (echo "ERROR: refuse to run with non-test env (APP_ENV=$$APP_ENV DATABASE_URL=$$DATABASE_URL POSTGRES_HOST=$$POSTGRES_HOST POSTGRES_PORT=$$POSTGRES_PORT POSTGRES_DB=$$POSTGRES_DB)" && exit 1)

# ---- one-command targets -----------------------------------------------------

.PHONY: test-pg
test-pg: guard
	bash backend/scripts/postgres_test_db.sh
	bash backend/scripts/wait_for_postgres.sh
	pytest -m postgres

.PHONY: test-clean
test-clean:
	bash backend/scripts/reset_test_db.sh

.PHONY: test-unit
test-unit:
	APP_ENV=test pytest -m "not postgres and not integration"
