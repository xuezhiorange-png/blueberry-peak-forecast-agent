# S5 task-owned PostgreSQL SIGTERM cleanup correction R1

TASK_ID=V0_18_S5_SIGTERM_OWNED_POSTGRES_CLEANUP_CORRECTION_R1

Owner authorized test-runner correction only, continuing Draft PR #726 from
`97eb4417344f5950927cd65cf77ea3fdfa6f7d44`. No production code, schema,
forecast mathematics, MCP or Dashboard changes; no Ready/Merge/deploy/S6.

## Root cause and correction

The original runner set `started` only after `pg_ctl start` returned. SIGTERM
raised KeyboardInterrupt before that assignment, leaving an already spawned
postmaster outside cleanup. A second SIGTERM could also interrupt `finally`.

Signal handlers now only record the first cancellation and count subsequent
SIGTERM/SIGINT. Business subprocesses run in their own newly created process
groups: cancellation terminates only that exact group (bounded escalation for
an unresponsive owned business command). PostgreSQL startup is allowed to
settle under pg_ctl's explicit 60-second startup timeout, then cleanup always
inspects the exclusive data directory, regardless of command success.

Before any stop, verify root/data device and inode, owner, non-symlink paths,
PG_VERSION, postmaster.pid data directory/port/socket/listen identity, and the
live postmaster command's exact `-D` directory. PID reuse or directory replacement
fails closed: report cleanup failure, never signal an unverified process.
Listener/socket fields are checked when present; an initial startup PID/directory
is accepted only together with the independently verified live process `-D` path.
Only `pg_ctl -D <verified owned directory> -m fast -t 60 -w stop` stops PostgreSQL.
There is no port-based kill, process-name search/kill or system-wide cleanup.

Cleanup is not cancelled by repeated SIGTERM/SIGINT. It records shutdown status,
postmaster PID, directory identities, absent PID file, pg_ctl stopped state,
closed loopback listener, signal count, final exit code and execution-log SHA256.
The first cancellation exits 143 (SIGTERM) or 130 (SIGINT); cleanup failure takes
precedence as exit 1. A downstream failure keeps its nonzero status. Logs,
data directory, private password and any backup remain preserved, not deleted.

SIGKILL, machine/power loss and malicious same-UID tampering are not claimed to
be recoverable. This is isolated POSIX runner acceptance, not production readiness.

## Deterministic real-process acceptance

`backend/tests/safe_pilot/test_runner_cleanup.py` uses real initdb/pg_ctl/postgres.
A loopback control connection holds startup before its command returns, business
execution, or cleanup. The observer releases explicit barriers; no sleeps or
port/name-based killing are used. Only the downstream pytest command is replaced
by a controlled subprocess, not database creation/status/stop or signal handling.

1. SIGTERM while startup has spawned PostgreSQL but not returned: stop verified
   postmaster, close port, preserve logs, exit 143.
2. SIGTERM during business work and another SIGTERM/SIGINT during held cleanup:
   cancel owned work, finish cleanup, retain first cancellation, exit 143.
3. Another independently running cluster remains usable and is later stopped by
   its own runner; neither its process nor resources are modified by the first.
4. Downstream failure exit 7: stop PostgreSQL, retain failure and log digest.
5. Startup command reports failure after spawning PostgreSQL: cleanup still runs.
6. Reviewed old Git source is run explicitly as an unfixed baseline: observe the
   real leak, then the test fixture stops only that baseline-created cluster.
   This proves reproduction, NOT historical acceptance of the fix.
   The test loader separately records the exact executed Git blob SHA256 in
   `executed-source.json`. The old runner's unchanged source inventory observes
   current worktree files, not that executed historical blob; it is explicitly
   NOT used as baseline execution provenance.
7. Replaced/symlink directory and foreign postmaster identity: refuse stop.
8. A reused PID belonging to the observer cannot be treated as PostgreSQL.

Tests also check actual process state, removed PID file, pg_ctl status 3, closed
port, manifest/log SHA agreement, and fixture teardown state. Private evidence is
retained; only explicitly selected non-secret logs/manifests/XML are published.

## Historical evidence and current-runtime separation

Existing S5 JSON, archives, documents and all older frozen evidence remain byte
identical. The old offline publisher comparison is explicitly evaluated at fixed
reviewed R1 commit `97eb4417344f5950927cd65cf77ea3fdfa6f7d44` for only three evolving
test sources: runner, publisher, original offline contract. Every other original
source, document and artifact still checks current bytes against original hashes.
No old expected hash is changed. Original statements about then-current source
bytes and acceptance remain historical statements, not claims about this fix.

This new correction has separate canonical JSON, current source bindings and
runtime artifacts. Its publisher rejects overwrite and verifies the full-run
manifest's source bytes match the current worktree before publication. New runtime
tests execute current code, never historical code except the named negative repro.

## Reproduction and validation

With Python 3.12 and PostgreSQL tools on PATH:

```sh
pytest -q backend/tests/safe_pilot/test_runner_cleanup.py
python -m backend.tests.safe_pilot.run --output /tmp/SYNTHETIC-NEW-UNUSED-NAME --browser
python -m backend.tests.safe_pilot.cleanup_evidence /tmp/SYNTHETIC-NEW-UNUSED-NAME
pytest -q backend/tests/forecast_intelligence/test_v0_18_s5_safe_pilot_contract.py backend/tests/forecast_intelligence/test_v0_18_s5_cleanup_correction_contract.py
```

The full runner executes current S5/S1/S2/S3 regression and real HTTPS/PostgreSQL
browser acceptance. Commit-time CI is pending by definition; the final PR receipt
must bind the new exact HEAD, completed workflow and actual job/test results.
The prior HEAD's green CI cannot accept this correction. PR remains Draft.

PRODUCTION_READINESS=NOT_READY
S5_FORMAL_COMPLETE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
S6_AUTHORIZED=false
