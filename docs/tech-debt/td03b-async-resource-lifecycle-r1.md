# TD-03B — synthetic async SQLite resource ownership

Task: `BLUEBERRY_TECH_DEBT_TD03B_ASYNC_RESOURCE_CLEANUP_R1`.
Owner scope is implementation and one Draft PR, without Ready/Merge/Deploy.
Base main is `50394cc13b0c2204ad76abdb8219e1ea9d3b8d29`; PR #769 is merged and
[its main push CI](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40736325995)
succeeded. No TD-03A support code is changed.

## Warning baseline

[PR #769 Golden job](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40676457191/job/122776024767),
head `27efc8ccfb5a648e673fa68b5bf26e748e4beec2`, reported 10,430 passed, 21 skipped,
1,033 deselected and 407 warnings. The archived full log SHA256 is
`5b588418e9f4ba14c6f8b2c770597e450abe7b36ad43bd9b4c3039acbf49fbc3`.
[The baseline ledger](td03b-warning-baseline-r1.json) preserves all 118 warning
message groups, their reported test/module identities, counts and the target
stack. The original full log and unabridged warning summary are also retained
outside Git. Module-grouped warning counts do not reveal individual nodeids;
those identities are not invented.

| Warning category | Occurrences |
| --- | ---: |
| PydanticDeprecatedSince20 (`json_encoders`) | 276 |
| UserWarning (101 serializer warnings, 3 duplicate Operation IDs) | 104 |
| PytestWarning (sync functions marked asyncio) | 15 |
| DeprecationWarning (DB shims / SQLite datetime adapter) | 7 |
| StarletteDeprecationWarning | 3 |
| PytestAssertRewriteWarning | 1 |
| PytestUnhandledThreadExceptionWarning | 1 |
| Total | 407 |

The target warning is attributed to
`test_synthetic_sqlite_aiosqlite_queryable_is_not_official_live_async_session_run_sync_query`.
Its worker stack calls aiosqlite `core.py:66` and then `core.py:75`, both attempting
`future.get_loop().call_soon_threadsafe(...)` on a closed loop. Pytest attribution
alone does not prove which earlier allocation owned a delayed finalizer.

## Proven test resource defect and reproduction limits

The old synthetic maker returns an engine-backed factory without an engine
owner. Querying uses the frozen public probe's `asyncio.run`; session exit rolls
back/checks the connection into `StaticPool` but does not dispose that pool.
An instrumented invocation of the actual synthetic test measured:

- Session close completed once.
- Query loop was already closed when the public call returned.
- Engine dispose count was zero.
- One pooled SQLite connection and its aiosqlite worker remained alive.

The same ownership defect was demonstrated in nine related synthetic makers:
nine newly added exit regressions failed against the old helpers. Their teardown
rescued only their own synthetic leaked engines **after** the failed assertions;
the failures were not converted to success.

A controlled experiment then invoked the real aiosqlite finalizer for the observed
unclosed connection with the already-closed query loop installed as the current
loop. It reproduced the same chained `RuntimeError: Event loop is closed` frames;
the original thread exception handler was retained. This is controlled
finalization, not a claim that a standalone pytest run naturally reproduced the
historical scheduling. An unchanged standalone target module passed 13 tests
without that warning. The ownership leak and closed-loop failure mechanism are
proven; the historical thread's allocation timing was not recorded.

Runtime pins were unchanged: SQLAlchemy 2.0.51 and aiosqlite 0.22.1. Local checks
used Python 3.12.13; the baseline CI used 3.12.15. Exact-head CI independently
validates the committed change on the existing Python 3.12 runner.

## Minimal fixture correction

`owned_sqlite_session_maker` is test-only and still returns the standard
`async_sessionmaker` with an `AsyncSession` subclass. Each session context owns
its own in-memory engine. Synthetic schema/data setup occurs during that
context's entry, and session close always awaits its owned engine's dispose.
Setup failure, body failure, query failure and cancellation retain normal
exception/fail-closed behavior. An externally supplied bind is refused, so this
fixture cannot dispose a borrowed application engine.

The default SQLite `StaticPool` policy, dependency pins and application public
probe remain unchanged. No event-loop policy patch, global warning suppression,
forced garbage collection, pool replacement or application DB change is used.
Existing application/pytest timeouts are unchanged. The test's one-second join
is a bounded check on captured worker handles;
an old worker still alive at that bound makes the test fail.

The three dataset makers seed the same synthetic tables/rows within the owning
query loop. The existing seed routines, 130 business test functions and every
frozen `*_BLOB` constant remain unchanged. Their test files acquire new Git blobs
for the authorized helper edits; historical objects and their expected IDs are
not rewritten. No real SOURCE_002 file, private dataset or production DB is read.
This does not certify production-wide cross-loop engine use.

## Initial local acceptance

The new lifecycle suite has 15 cases: the nine original synthetic paths, body
failure, task cancellation, failed setup, fail-closed query failure, two separate
query loops and rejection of an external bind. All pass. The lifecycle cases check actual connection closure, worker exit, pool
checkin/close and same-loop disposal; the external-bind case checks that no
owned engine or connection is created.

Three independent isolated repetitions each passed 145 tests with zero failures,
errors or skips. `PytestUnhandledThreadExceptionWarning` was elevated to an error
for these checks. The primary-query trace on each repetition recorded:

`ENGINE_CREATE -> CONNECT -> CHECKOUT -> SESSION_CLOSE_BEGIN -> CHECKIN -> SESSION_CLOSE_END -> DISPOSE_BEGIN -> CLOSE -> DISPOSE_END`

All had one dispose on the connection's query loop, a closed connection, no live
owned worker and no thread exception after return. No forced GC was used.
Ten existing PostgreSQL contracts passed on a task-owned PostgreSQL 16 instance,
including persistence, immutable readback, rollback, fail-closed half-state and
health/session isolation. That instance was stopped and its port released.

Local harness failures are retained separately: a bound/non-listening guard
socket caused SYN waiting and an interrupted run; the corrected loopback guard
accepts and immediately closes without reading any payload. A broad regression
also exposed missing `pytest` on nested subprocess PATH. Runtime setup was
corrected without changing assertions or timeouts. Neither is reported as an
aiosqlite fix or included in the three completed repetitions.

The initial complete local S3 rowset regression passed 1,484 tests with one
existing skip and two unchanged SQLite datetime adapter warnings. That head
added 15 lifecycle cases and retained the original tests/skip rules. Those local
results preceded the first CI and did not establish a suite-wide warning fix.

## Initial CI exposed additional test owners

The first PR head, `ea2e80f9c662eb54903d45225e049674a1a1fc3a`, completed
[CI 40801427102](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40801427102)
with all 16 jobs successful. It **did not pass this task's target-warning gate**:
Golden reported 10,445 passed, 21 skipped, 1,033 deselected and 408 warnings,
including two aiosqlite worker exceptions attributed to
`test_s3_a2_completeness_pass_closeout_contract.py`.
The reporting location is not treated as the allocation owner. These logs and
the earlier successful local results remain preserved.

Three further exit regressions demonstrated live workers after the real synthetic
live-actuals, live-catalog and direct-connection entrypoints returned. All three
failed before their fixture correction. The two session factories now use the
same owned-session helper; the direct connection has a test-only AsyncConnection
whose close awaits its engine's disposal. It remains a real AsyncEngine and uses
the standard SQLite async dialect and StaticPool, with no application changes.

Catalog contracts also require landed synthetic rows to survive successive
public calls. An intermediate fresh-memory-per-session correction closed all
workers but failed seven unchanged catalog assertions. That failed run is
retained. For these two data-retaining factories, a pytest-owned temporary SQLite
file now preserves the synthetic rows. Each session still creates/connects/uses/
disposes a different engine within its own query loop. The test storage owner
unlinks only files it created, on normal or exceptional exit. No existing file
path is accepted or discovered; seed tables and rows are unchanged.

The final lifecycle suite has 22 cases, including retained-state round trips
across two loops, storage cleanup after exceptions, and connection failure/
cancellation. Nested inspectors can checkout the same StaticPool record more
than once: one catalog trace had 17 closed checkout proxies although checkin
event counts were not one-to-one. Every actual proxy is therefore checked for
invalidated/cleared state, in addition to physical driver closure, worker exit,
same-loop disposal and close/dispose ordering. No business assertion was removed.

All 158 existing test functions in the changed test modules retain their exact
assertion ASTs, and all 360 original module constants retain their values. Only
one business test's resource-construction call changed; its public call and
assertions did not. The production files, dependency pins and CI criteria remain
unchanged. Final complete-suite repetitions and the new exact-head CI are recorded
in the evidence ledger/PR receipt rather than inferred from the first green CI.

The corrected implementation passed three independent complete S3 repetitions:
1,491 passed, one existing skip and two datetime warnings on each repetition.
Each process traced 61 opened synthetic SQLite engines/workers, with zero live
workers after the suite, every connection closed, and matching query/dispose
loops. Thread exception warnings were errors. Original/red/intermediate logs
remain retained. Ruff, format and Mypy checks apply to the final code; its CI
result is reported separately from these local measurements.

The first CI's Canary also retained separate asyncpg warnings: SAWarning 12,
`Connection._cancel` RuntimeWarning 60 (baseline 56), and unraisable warnings 3
(baseline 1). The cause of that count variation is not proven. These signatures
already occur in the old Canary; they are not claimed fixed or suppressed by
this SQLite-fixture change.

## Other warning work remains separate

No objective of WARNINGS=0 is introduced. The other 406 baseline occurrences are
classified, not silenced or automatically corrected. Possible TD-03B follow-ups,
requiring their own scope, are:

1. Review the 15 sync/async marker mismatches.
2. Plan compatibility-aware migration of deprecated Pydantic encoders; retain
   deliberately invalid serializer fixtures and their diagnostic intent.
3. Review DB shim imports and SQLite datetime adapter deprecations.
4. Review duplicate OpenAPI Operation IDs independently of business/auth API
   compatibility, plus Starlette status-alias deprecations.
5. Review pytest plugin import/rewrite ordering.

TD-03C, TD-03D and V0.22 are not started. Forecast math, production APIs, historical
source authority and frozen hashes are outside this change.
