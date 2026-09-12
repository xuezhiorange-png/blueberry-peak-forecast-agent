# PR607 main full-suite failure recovery R1

TASK_ID=V0_3_PR607_MAIN_FULL_SUITE_FAILURE_RECOVERY_R1

## Fixed identities and first failure

PR607 head `97377ec0cdb6dc377aef8e06985bbc20c2a0df81` passed run
34618964218 without executing full-suite-canary. Merge
`f3a0804869d459d423b31115ff9aae8a31ab0996` failed run 34620858559,
job 103334182918. Release `043f8f3e4e867b5d5f82437f7f8c9caa1c8d2fc6`
also failed its full suite (run 34622915318, job 103340974640).

The first and only failed pytest node in both original runs was
`backend/tests/forecast_authority/test_retention.py::test_postgres_session_boundary_is_opt_in`.
Its insert references `core_forecast_run_id=1`, but no parent was persisted.
PostgreSQL raises `ForeignKeyViolationError` at constraint
`fk_forecast_authority_capture_core_run_id`; SQLAlchemy wraps this in
`IntegrityError`, then retention wraps it in `ForecastAuthorityConflictError`.
These are one causal chain, not three independent failures. Container shutdown
EOF/open-transaction messages occur after the pytest failure and are not its cause.

Original merge result: 1 failed, 6283 passed, 4 skipped (1358.23s).
Original release result: 1 failed, 6283 passed, 4 skipped (1531.88s).
Complete retrieved job-log SHA-256 values:

- Merge: `78c318309452a5d3c887a2995c72e92a1548597358fc25efd76b946192ff7837`.
- Release: `d246f61df5c4752b64a5577b9a1eb6a5ed9e39c033151d11a7d6f1e0a23fa5e7`.

## Root cause, not a forecast-contract change

The PostgreSQL test reused a synthetic in-memory source's fixed parent ID and
only called table.create(checkfirst=True). On Alembic-migrated PostgreSQL that
does not create the missing Core parent or remove the legitimate migration FK.
The test depended on state it never established. The production FK correctly
rejects the invalid fixture. No evidence here shows a forecast algorithm defect.

The retention test file is byte-identical at PR607 head and release:
SHA-256 `6cce300c4089216fc44ef3f3470ac664715b3994a4b0ec95063b55066d247040`.
Its history predates PR607 (commits f9bb94b / 56043b6). PR607 exposed, rather
than necessarily introduced, this coverage defect. Merge-to-release contains
only PR608 closeout documentation; no code, test, dependency or workflow fix.
No flaky classification is made.

## Exact full-suite reproduction

Reproduction uses GitHub's original isolated job at each pinned SHA, once more
per SHA for diagnosis (attempt 2), not an automatic retry-to-green policy:

```sh
gh run rerun 34620858559 --job 103334182918 --repo xuezhiorange-png/blueberry-peak-forecast-agent
gh run rerun 34622915318 --job 103340974640 --repo xuezhiorange-png/blueberry-peak-forecast-agent
```

Both SHA workflows are identical (SHA-256
`9e8412523f68f4fc1355385e8471e9afb64e323787c12b50b5d24d4828f60973`).
The job checks out its run SHA, uses ubuntu-latest, setup-python 3.12,
postgres:16 service at localhost:55432, upgrades pip and installs:

```sh
pip install --disable-pip-version-check --quiet -c backend/constraints-ci.txt -e ".[dev]"
```

It waits for SELECT 1, derives a per-run/attempt database with the repository's
resolve_isolated_db_name helper, creates that previously nonexistent database,
validates its test identity, and runs:

```sh
alembic -c backend/alembic.ini upgrade head
pytest -q --tb=long --durations=30 --junitxml=reports/test-results/full.xml
```

Environment: APP_ENV=test, POSTGRES_HOST=localhost, POSTGRES_PORT=55432,
POSTGRES_USER=blueberry_app, POSTGRES_DB=ISOLATED_DB_NAME,
DATABASE_URL=the isolated asyncpg service URL, RUN_POSTGRES_INTEGRATION=1.
The workflow's public disposable test password is unchanged. No acceptance or
budget database is used. The seed marker is emitted as PYTEST_CI_SEED or the
run SHA exactly as in the original workflow (not silently a new pytest option).

Supplementary local reproduction uses separate detached worktrees for the two
SHAs, fresh Alembic-migrated databases in a newly initialized test-only PG16.15
cluster on port 55439, and the exact failed node. Both fail on the same FK.
This macOS/Python3.12.13 targeted reproduction is not misrepresented as the
Ubuntu/Python3.12.14 full-suite environment; Actions attempts provide that proof.

## Narrow fix and regression

Only test infrastructure and CI coverage change. The retention test now creates
its own safely named migrated database, persists the existing canonical synthetic
Core fixture and binds capture to its actual parent ID/request hash. It commits,
disposes the connection pool, and verifies hash parity through a fresh connection.
The test-only database is removed afterward, not any pre-existing database.
An additional negative regression proves the FK still rejects a missing parent.
No FK, assertion, production code, frozen metric or sealed TEST data is weakened.

The original positive test fails before the repair and passes afterward; the
negative regression prevents a constraint bypass from masquerading as a repair.

## PR/main parity and required check

Previously `if: github.event_name != 'pull_request'` silently excluded the full
suite from every PR. The PG integration node was excluded by the unit marker
filter and was not selected by the PR directory shards. Removing the canary
event condition runs the identical migrated service, dependency installation and
exhaustive pytest command for every PR, including forecast/scoring/parameter/data
changes. Push/main remains unchanged. No path-based exception or blanket retry
is added. The shard manifest records the intentionally overlapping exhaustive
gate; historical PR55 deduplication constraints are superseded only for this gate.
New workflow tests reject event/step/path exclusions and manifest divergence.

The branch protection API returned HTTP404 `Branch not protected`. No external
settings were modified. Configure required status check **full-suite-canary**
(workflow **CI**) on main; code makes it run but cannot by itself prevent an
administrator from merging a red PR without a required-check rule.

## Release disposition and limits

v0.3.0 remains immutable at its published SHA. Its full-suite validation is not
clean; the demonstrated defect is test infrastructure, not evidence invalidating
the previously recorded Banna empirical forecast. Do not claim release-wide
regression acceptance from PR607 green status. The correction belongs to a
subsequent reviewed patch, v0.3.1, not a moved tag. This task does not publish it.
No new real forecast, S4 evaluation, production data mutation, or TEST access.

Final run results and exact-SHA Actions links are recorded in the PR body. Required
check configuration remains an external follow-up, not an accomplished setting.
