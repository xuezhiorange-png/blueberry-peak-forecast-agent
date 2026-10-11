# S1 Runtime R2: migration compatibility resolved; regression ingress adaptation blocked

TASK_ID=V0_18_S1_ALEMBIC_HEAD_COMPATIBILITY_AND_RUNTIME_RESUME_R2

Base: `320f2046e3105b1b55da9cb037892571110b584a`. Branch:
`task/v0.18-s1-local-auth-runtime-r1`. No commit, push or PR has been made.
Latest verified formal release is v0.17.0. No parallel S1 Runtime PR was found.

## Migration correction

The current head is `d7766e57d4c8`, with direct parent
`0040_hierarchical_forecast`. `backend/tests/alembic_head.py` uses Alembic's
ScriptDirectory to assert exactly one nonempty head and 0040 ancestry. It rejects
a deliberately forked synthetic graph and accepts a future linear synthetic head.

Only current-head assertions were adapted in these files:

| File | Old assertion | New assertion | Historical semantics retained |
| --- | --- | --- | --- |
| backend/tests/test_historical_backtest_alembic.py | Database head equals 0040 twice | Database head equals verified unique script head | Legacy columns, inserted row and exact downgrade target unchanged |
| backend/tests/forecast_quality/test_persistence.py | Database head equals 0040 four times | Database head equals verified unique script head | Data, checks, triggers and prohibited downgrade assertions unchanged |
| backend/tests/s2_materialized_dataset/lane_b/conftest.py | Script heads equal fixed 0040 | Verified unique head with 0040 ancestry | Lane B revision and parent identities unchanged |
| backend/tests/s2_materialized_dataset/lane_d/conftest.py | Script heads equal fixed 0040 | Verified unique head with 0040 ancestry | Lane D revision and parent identities unchanged |
| backend/tests/actual_harvest_import/alembic_cases.py | Script heads equal fixed 0040 | Verified unique head with 0040 ancestry | All historical migration identities unchanged |
| backend/tests/s3_daily_rowset/test_incumbent_forecast_replay_identity_persistence_schema.py | Script heads equal fixed 0040 | Verified unique head with 0040 ancestry | Replay identity migration revision and parent unchanged |

The existing isolated live round-trip test already discovers its head dynamically
and was not edited. The S1 historical evidence's observed head 0040 remains unchanged.

PostgreSQL 15.18 was run on a dedicated loopback cluster, with only synthetic
databases. A fresh database passed the historical backtest upgrade/downgrade/upgrade
test. Forecast Quality persistence passed 32 tests. Reusing an earlier test database
produced a duplicate synthetic run_signature failure; a fresh database passed
without changing the original insertion or its uniqueness constraint.

## Runtime work and actual verification

The original uncommitted runtime work was preserved and extended: authentication
tables, additive migration, Argon2id, server sessions, CSRF, bounded management
APIs, exact grants, controlled HTTP ingress and a fresh ASGI response release gate.
Additional database guards protect immutable account identity, nondecreasing
revisions, append-only audit and typed exact-resource bindings.

Actual local results:

- New local-auth tests: 39 passed, including real PostgreSQL and ASGI tests.
- Historical hash and V0.18 contracts: 137 passed.
- Lane B/D and replay identity regression: 106 passed.
- Frontend unit: 122 passed after minimal historical-source hash adaptation.
- Dashboard/cross-surface/selector browser regression: 64 passed, desktop and mobile
  Chromium, using this worktree's Python and an independent frontend port.
- Frontend typecheck, lint, format and build passed.
- Backend Ruff, format and mypy passed (573 application files).
- Full non-PostgreSQL backend regression stopped after 3 failures: 5246 passed,
  20 skipped, 813 deselected. Two failures are the known missing local libomp
  dependency; the third is the legacy MCP production-entrypoint mismatch below.

These results are NOT a complete A01–A20 security verdict. Coverage still requires
completion and a successful exact-head CI. Real administrator/steward/publisher
approval remains D03=PENDING. No real account, grant or production migration occurred.

## New scope blocker: legacy regression transport

The controlled production export intentionally denies old Trial/MCP business paths.
`.github/workflows/ci.yml` starts `backend.app.main:app` for Frontend E2E, waits on
`/health/ready`, then runs legacy Trial creation/import tests. The controlled
allowlist currently denies those paths, including that readiness path. Likewise,
`backend/tests/mcp/test_v0_12_research.py::test_loopback_tcp_http_and_stdio_parity`
uses the shared live backend helper and expects the old MCP endpoint to return 200;
the controlled production entrypoint returns 403. The focused failure was reproduced.

Do NOT add a production authentication exemption, fallback actor, test-environment
authentication bypass, or weaken these assertions. A narrowly authorized test-only
adaptation is required: legacy regression must explicitly start a separate legacy
factory/trust-domain fixture, while current controlled production rejection remains
independently tested. This needs the Frontend E2E startup step and legacy MCP live
test helper adapted. Current CI authorization permits historical-object acquisition,
not changing that startup contract. Those startup files/steps were not modified.

One additional historical hash conflict was found in the frontend governance test.
Only its two legitimately changed HTTP adapter pins now read fixed PR #716 Git bytes;
expected hashes, frozen documents and screenshot bindings remain unchanged.
Frontend-unit receives historical objects through fetch-depth 0. No Dashboard runtime
code was changed. Actual CI object availability remains unverified until a PR run.

Initial browser attempts used system Python without uvicorn and an already-running
foreign frontend on port 4173. Those attempts were not accepted as product failures
or passes. This worktree was rerun with its own Python and port 45173: 64 passed.
The foreign frontend/backend processes were not stopped or modified.

## Governance and preservation

260 tracked V0.16–V0.18 historical document/evidence files were byte-compared with
the base Git commit: zero changes. Runtime resume R1 blocked report and JSON remain
intact. New browser artifacts and the isolated PostgreSQL test log/JUnit are preserved.
No historical expected hash was changed; current runtime testing uses current code.

RESULT=BLOCKED
PR_STATE=NOT_CREATED
EXACT_HEAD_CI=NOT_EXECUTED
S1_FORMAL_COMPLETE=false
PRODUCTION_READINESS=NOT_READY
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
STOP=true
