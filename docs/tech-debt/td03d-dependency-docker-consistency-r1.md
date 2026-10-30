# TD-03D — dependency and Docker environment consistency

Task: `BLUEBERRY_TECH_DEBT_TD03D_DEPENDENCY_DOCKER_CONSISTENCY_R1`.
Base: `7eec6fa181307d9b26081322e45caa67d0f73e69`; PR #771 is merged and
main push CI #41049642495 completed successfully at that exact SHA.

## Proven drift

Three fresh, isolated macOS Python 3.12.13 environments were actually installed:

1. `pip install -c backend/constraints-ci.txt -e '.[dev]'` (CI policy).
2. `pip install '.[dev]'` (the old Docker installation policy, reproduced locally,
   **not** a claim that an old Linux image was executed).
3. `uv sync --frozen --extra dev --no-default-groups` in an explicit temporary
   `UV_PROJECT_ENVIRONMENT`; the lockfile was not regenerated.

The unconstrained installation differed from CI on 13 direct dependencies:

| Dependency | CI constrained | Old unconstrained policy | Existing uv.lock install |
| --- | --- | --- | --- |
| `alembic` | 1.18.5 | 1.20.1 | 1.18.4 |
| `asyncpg` | 0.31.0 | 0.32.0 | 0.31.0 |
| `fastapi` | 0.139.0 | 0.162.0 | 0.137.2 |
| `mypy` | 2.1.0 | 2.4.1 | 2.1.0 |
| `numpy` | 2.5.1 | 2.5.4 | 2.4.6 |
| `pydantic` | 2.13.4 | 2.14.2 | 2.13.4 |
| `pydantic-settings` | 2.14.2 | 2.16.2 | 2.14.2 |
| `pytest` | 9.1.1 | 9.2.0 | 9.1.1 |
| `pytest-asyncio` | 1.4.0 | 1.4.1 | 1.4.0 |
| `ruff` | 0.15.20 | 0.17.3 | 0.15.18 |
| `scikit-learn` | 1.9.0 | 1.9.1 | 1.9.0 |
| `sqlalchemy` | 2.0.51 | 2.1.6 | 2.0.51 |
| `uvicorn` | 0.50.2 | 0.54.0 | 0.49.0 |

All 33 selected direct dependencies satisfy pyproject's declared ranges in these
observations. CI constraints actively cover 31. Of the other two, argon2-cffi is
already an exact pyproject pin, while certifi retains its existing lower bound.
The frozen uv environment has five CI-constraint mismatches; certifi also differs
(2026.6.17 versus the observed CI-style 2026.10.23). This PR changes neither pins,
project requirements nor uv.lock. The private installation receipts preserve all
versions, mismatches and input hashes; no business data was used.

## Small changes and their limits

- Docker keeps `python:3.12-slim` and the existing noneditable package install,
  adding `-c backend/constraints-ci.txt`. CI retains its editable source install.
- The existing LightGBM dependency uses OpenMP; the slim image explicitly installs
  its Linux runtime (`libgomp1`). Native imports are exercised without fitting or
  predicting. See the [upstream installation guide](https://lightgbm.readthedocs.io/en/stable/Installation-Guide.html).
- A build-context allowlist sends only pyproject, uv.lock and backend sources;
  root raw data, Git history, frontend, reports and local environment files are
  excluded. No source-data archive is unpacked or copied for this validation.
- The local test profile moves from `postgres:15-alpine` to `postgres:16-alpine`.
  Its history contains only the original Issue #23 harness introduction; current
  contracts/CI document no dedicated PostgreSQL 15 compatibility lane.
- PostgreSQL 16 uses **new** `blueberry_postgres_test_data_v16`, never the old
  `blueberry_postgres_test_data`. No migration/deletion of the old volume occurs.
  Existing dev Compose, database guards, test DB name and port 55432 stay intact.

These are equal installation constraints, **not** a complete transitive lock or
bit-identical environment. Transitives, certifi's range, the mutable Python image
tag, OS packages, interpreter patch, platform and editable/noneditable packaging
remain distinct. Pip does not consume the copied uv.lock. Use the constrained pip
command for the current CI policy; frozen uv is a separate version set. Aligning
that historical lock would require its own reviewed dependency decision.

## Actual Docker / PostgreSQL acceptance

The development host has no Docker CLI/runtime. Local static tests are therefore
not presented as a successful image build. Instead, the **existing** PR-only
`compose-smoke` Linux job performs the real Docker acceptance in the final CI:

```sh
python scripts/ci/check_environment_consistency.py docker \
  --root . --report-dir reports/environment
```

This builds the real backend Dockerfile, verifies every active constraint and
Python 3.12 inside the image, runs `pip check`, and imports FastAPI, SQLAlchemy,
asyncpg, aiosqlite, ecCodes, scikit-learn, LightGBM and CatBoost. The version/import
probe has no network, app server or business database access.

The PostgreSQL probe composes the real test file with a temporary JSON override
that changes **only** generated container/network/volume names. Before creating
anything it verifies the rendered image, DB, port, mount and network identity,
and rejects preexisting resources. It checks the actual server major version,
55432 publishing and owned mount, then sums two synthetic NUMERIC values in a
temporary table. Cleanup removes only that new project and image; it verifies
that preexisting volume names survive and no owned container/network remains.
It never starts, stops, mounts, migrates or deletes a user's existing PG15/16
cluster or volume. A port collision fails rather than commandeering another DB.
If an old local test instance occupies 55432, its owner must stop it separately.

The JSON receipt is uploaded as `environment-consistency`. Failures propagate;
missing receipt is a CI error. Job names, events, selectors, shards and all prior
Compose checks remain, with no skip/xfail, retry or relaxed success condition.
Actual exact-head runtime results are recorded in the PR receipt after CI ends.

## Local checks and retained boundaries

The two new configuration tests first failed on the old Docker/PG15 files. The
focused suite covers missing constraints, version/port/database/volume drift,
metadata-only inspection, malformed resource ownership, rendered unsafe profiles,
preexisting-volume refusal and cleanup on a failed synthetic query. Relevant
existing CI, safety, version, health, isolation and historical-source contracts
run alongside it; full Ruff, format and strict app/research Mypy stay required.

No app/research code, dependency pin, model parameter, scoring denominator,
source authority, TD-03A/03B fixture, frozen evidence, TD-01 XLS untracking,
v0.21.0 tag/release or production database is changed. Draft PR only; no
Ready/Merge/Tag/Release/Deploy or V0.22 authorization is inferred.
