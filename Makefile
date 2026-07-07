# Issue #23 Batch 1 Makefile (one-command contract fix)
#
# Scope: one-command local test environment. NOT for CI (CI workflows
# live in .github/workflows/, out of scope for this Batch 1 PR).
#
# This Makefile guarantees:
# - `make test-pg` works with no env pre-export (uses make-level defaults).
# - `make test-pg POSTGRES_PORT=5432` (or any other dev-DB override) is
#   REJECTED by the guard with rc != 0 and a clear error message.
# - `DATABASE_URL=...dev-db make test-pg` is REJECTED by the guard.

# ---- defaults: ensure plain `make test-pg` works without exporting env ---

APP_ENV ?= test
POSTGRES_HOST ?= localhost
POSTGRES_PORT ?= 55432
POSTGRES_DB ?= blueberry_peak_test
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= postgres
DATABASE_URL ?= postgresql://$(POSTGRES_USER):***@$(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)

# ---- guard (fails closed on dev-DB profile) ----------------------------------
#
# The guard evaluates the EFFECTIVE env (user-overrides + make-defaults)
# so `make test-pg POSTGRES_PORT=5432` is rejected, but plain
# `make test-pg` passes.

GUARD_OK := $(shell APP_ENV='$(APP_ENV)' POSTGRES_HOST='$(POSTGRES_HOST)' POSTGRES_PORT='$(POSTGRES_PORT)' POSTGRES_DB='$(POSTGRES_DB)' DATABASE_URL='$(DATABASE_URL)' python3 -c "import os,sys; db=os.environ.get('POSTGRES_DB',''); host=os.environ.get('POSTGRES_HOST','localhost'); port=os.environ.get('POSTGRES_PORT','5432'); env=os.environ.get('APP_ENV',''); url=os.environ.get('DATABASE_URL',''); bad = (env != 'test') or ('blueberry_peak' in db and '_test' not in db) or (port == '5432' and host == 'localhost') or ('blueberry_peak' in url and '_test' not in url) or ('localhost:5432' in url); sys.exit(1 if bad else 0)" 2>/dev/null && echo 1 || echo 0)

guard:
	@test "$(GUARD_OK)" = "1" || (echo "ERROR: refuse to run with non-test env" && echo "  APP_ENV=$(APP_ENV) POSTGRES_HOST=$(POSTGRES_HOST) POSTGRES_PORT=$(POSTGRES_PORT) POSTGRES_DB=$(POSTGRES_DB) DATABASE_URL=$(DATABASE_URL)" && exit 1)

# ---- one-command targets -----------------------------------------------------
#
# IMPORTANT: `export VAR` only exports variables that are ALREADY SET in
# the shell — make variables are not visible to subshells. We must use
# `export VAR=value` to inject the make-level defaults (or user overrides)
# into the subprocess env. This guarantees `make test-pg` (with no user
# override) is always evaluated against the test profile by both the
# guard and the bash guard inside postgres_test_db.sh.

.PHONY: test-pg
test-pg: guard
	export APP_ENV='$(APP_ENV)' POSTGRES_HOST='$(POSTGRES_HOST)' POSTGRES_PORT='$(POSTGRES_PORT)' POSTGRES_DB='$(POSTGRES_DB)' POSTGRES_USER='$(POSTGRES_USER)' POSTGRES_PASSWORD='$(POSTGRES_PASSWORD)' DATABASE_URL='$(DATABASE_URL)' && bash backend/scripts/postgres_test_db.sh && bash backend/scripts/wait_for_postgres.sh && pytest -m postgres

.PHONY: test-clean
test-clean:
	bash backend/scripts/reset_test_db.sh

.PHONY: test-unit
test-unit:
	export APP_ENV=test && pytest -m "not postgres and not integration"
