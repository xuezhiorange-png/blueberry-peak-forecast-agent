# Full-coverage CI acceleration R1

Task: `BLUEBERRY_CI_FULL_COVERAGE_ACCELERATION_R1`.
Base: `92cc8904e3af211300a88a20720d2c03848c43b8`, main CI `39554253546` success.
PR #745 is not changed. No production, model, dependency, migration, existing
test assertion, marker or frontend E2E fixture is changed.

## Measured serial baseline

| Event / source | Canary job wall time | Golden job wall time | Canary cases / skips |
| --- | ---: | ---: | ---: |
| main push `39554253546` | 2,874 s (47m54s) | Not a main-push job | 10,751 / 5 |
| PR #744 `39548916887` | 2,802 s (46m42s) | 1,138 s (18m58s) | See that run's JUnit |

The main JUnit SHA256 is
`731b22a8f2accae9c2fed6b93f51e07785a0177b81a331beba16f1c08fb5f2f3`.
Golden JUnit SHA256 is
`a6806aaf77e90a8927b5e028289f8129759a73f5ca2d7a7a6b0d64879731525a`.
They are archived Actions outputs, not inferred from existing PASS labels.
The checked-in timing data contains per-file durations, their source run and
artifact identity, collection fingerprint and the five existing skip identities
and reasons. It contains no business data.

## Partition contract

Normal PR, main push, nightly and manual CI execute four independent canary
workers. `scripts/ci/canary_partition.py` is explicitly loaded only for those
workers. Other pytest invocations and the fast-feedback jobs are unchanged.

Files are assigned longest historical duration first to the least-loaded slot,
with deterministic path and slot tie-breakers. Each complete test file stays
together, preserving module/class fixtures and in-file ordering. Pytest's
normal fixture-based collection reordering is allowed; deleting collected items
before partitioning is rejected. Unseen files get a documented conservative
file overhead plus per-node estimate, never zero ownership or an exclusion.

The baseline estimates are 687.726 / 687.725 / 687.725 / 687.725 seconds for
150 / 159 / 160 / 160 files. These are **predictions**, not the claimed result.
The heaviest file is the unchanged rolling-backtest orchestration module
(457.353 seconds); it is not split. Actual runtime and setup/queue overhead
must be measured. Session-wide fixture initialization can repeat across workers.

Every worker retains Python 3.12, PostgreSQL 16, the existing constrained pip
installation and cache, full historical Git objects, safe test profile checks,
`alembic upgrade head`, all original pytest flags, and scoped database cleanup.
Each has a separate service container and a database name derived from run,
attempt and slot. Cleanup re-derives that exact name and rejects an invalid slot;
the pre-existing production/dev database guards remain intact.

No new skip, xfail or retry is added. The plugin partitions by deselection, not
by skip: the four selected sets must exhaust the complete collection once.
The original five skips are checked by exact nodeid and reason. Unexpected
collection skips/errors, new skips, xfails, missing calls and duplicate calls
fail the gate.

## Stable gate and evidence

The historical YAML job ID `full-suite-canary` now describes matrix workers
named `full-suite-canary-shard (0)` through `(3)`. Keeping that ID and its
protected step names also preserves the existing unmodified workflow safety
tests. `full-suite-canary-gate` exposes the original required check name
**full-suite-canary**. No branch-protection settings are changed.

The gate runs with `always()`, requires the entire matrix result to be exactly
`success`, and verifies all four mandatory artifacts. Failure, cancellation,
skipping, missing or duplicate artifacts cannot become success. `fail-fast`
is false so diagnostic evidence from the other slots is retained.

Each proof records the complete pre-partition node catalog, assignments,
selected nodes, setup/call/teardown reports, actual PostgreSQL version and DB
identity, Python and installed dependency fingerprint, checkout/tree, workflow,
lock/constraints and plugin hashes, run/attempt and source head. The aggregator
compares these with each other and its own checked-out source. It also checks
JUnit nodeids/outcomes against the execution reports. The final artifact retains
the historical name `full-suite-canary-results` and a merged `full.xml`, plus
`canary-gate-summary.json`; the serial control is not double-counted.

## One controlled comparison

After local checks, the independent Draft PR runs its normal exact-head CI.
One explicit dispatch on the same final branch, with `compare_serial=true`,
adds a fifth `serial` control to the four workers. It does not omit any normal
worker. All five use the same code, dependency installation, Python/PostgreSQL,
configuration and event environment, with independent databases. The gate then
requires exact per-node serial/parallel outcome equality as well as coverage.
This is an acceptance comparison, not automatic retry or main-result reuse.
Default dispatch, main and PR execution do not pay for a serial control.

Actual comparison evidence is the immutable Actions run/artifacts and PR
receipt tied to the final SHA. Record job start/end, total run elapsed time,
queue/setup overhead, summed runner seconds, counts/skips and PostgreSQL/E2E
outcomes. Compare the normal four-worker critical path with the 25-minute goal.
Do not label the intentionally slower five-worker comparison's total wall time
as the normal production CI wall time.

A post-merge main push cannot be measured before Owner authorizes merge.
The dispatch comparison is a main-mode proxy; label that limitation explicitly
and retain post-merge main validation as pending. More parallel workers may
increase total runner minutes because setup and session fixtures repeat, even
when wall-clock waiting falls. Report the measured trade-off, not estimated
runner-minute savings. No needless baseline rerun or success-result reuse is
enabled.

## Golden overlap

The baseline Golden report has 9,641 actual test cases, all present in Canary,
plus three module-level collection-skip reports. Canary has 1,110 additional
actual cases. Golden's 21 skips versus Canary's five also reflect different
database environments. Therefore Golden is not interchangeable with exhaustive
Canary. Its selector, assertions, job and fast-feedback role remain unchanged.
It will likely become the PR critical path after Canary acceleration; no Golden
parallelization or deduplication is enabled by this PR.

## Local checks and limits

New unit tests exercise deterministic balancing, whole-file ownership, real toy
pytest subprocess collection/execution, serial equality, JUnit merging, and
failure/missing/cancelled/skipped matrix, duplicate/missing calls, environment
drift and skip/xfail rejection. All existing CI parity and dev-DB safety tests
must continue to pass without edits. Local macOS collection is not proof of the
Linux/PostgreSQL 16 full execution set; the real Actions comparison supplies it.

Second-stage reuse remains a separate, **design-only** proposal in
`main-result-reuse-design-r1.md`. No main gate is removed or made conditional.
