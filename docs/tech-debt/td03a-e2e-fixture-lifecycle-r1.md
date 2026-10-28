# TD-03A — owned E2E fixture lifecycle diagnostics

Task: `BLUEBERRY_TECH_DEBT_TD03A_E2E_FIXTURE_LIFECYCLE_R1`.
Base: `b7cd75c3022271cb6f25f91b3feddad02e1f1d36`.

## Incident status

`ROOT_CAUSE_NOT_PROVEN`. This delivery supplies diagnostics and failure preservation,
not a proven transport/lifecycle workaround. No timeout increase, audit retry,
ignored exception, business assertion change or permission change is introduced.

[Attempt 1](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40656452366/attempts/1)
reported 208 passing tests plus a worker-fixture authority GET `socket hang up`.
[Attempt 2](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40656452366/attempts/2)
passed on the identical SHA. The original log archive remains preserved, SHA256
`98d53a459c9d79bd21b2e1e44fc08beca874c9e8e364d8e491a701fc60693a08`.
Neither original attempt published the authority child's exit receipt/stderr or
a correlated request/cleanup timeline. The error output timestamp is not proof
of the request start time. Early exit, route/disposal races and HTTP connection
behavior therefore remain hypotheses, not established causes.

An unchanged local baseline ran the six selector cases three times, without
retries: 16 passed and two failed before READY with the existing 30-second setup
deadline. This is a different symptom, not reproduction of the teardown socket
failure. Those startup failures and their process/port release checks are retained.
An instrumented selector run subsequently passed all 18 cases; it does not prove
the intermittent fault is fixed. The main CI for the TD-02 merge was observed
cancelled, not successful; the PR must report its own exact-head CI separately.

## What is recorded

`startOwnedServer` keeps the same OS-owned socket, PID/nonce validation, shutdown
signals and deadlines. Every caller receives a separate append-only JSONL journal
under `frontend/test-results/owned-server-diagnostics/`. Existing E2E artifact
upload already includes that directory; no workflow change is necessary.

Records include worker/child PID, nonce, bound port, sequence, parent observation
UTC/elapsed time, BOUND/READY, ASGI lifespan, HTTP begin/end/disconnect/error,
received/sent signals, child exit/stdio-close and the final cleanup receipt.
ASGI events retain their own emission UTC separately from parent receipt UTC.
An ASGI return is not claimed to be a TCP-flush or client-completion timestamp.

The selector's thin worker helper adds request-context/use/route-cleanup/disposal
phases and a UUID-only test correlation header. State and final authority audit
requests are never retried. The existing bounded startup readiness poll is
unchanged. `SYNTHETIC == true` and `read_dml_count == 0` assertions remain required;
primary and cleanup failures are both returned, using AggregateError when needed.
Other existing business spec files keep their original bytes and gain the shared
child/ASGI journal through their existing owned-server calls.

No request query, body, authorization header or arbitrary exception message enters
the journal. Source paths are reduced to repository-relative code frames. stderr
has a full-stream hash/byte count, an 8 KiB buffer and a <=4 KiB safe summary:
only fixed lifecycle lines/code locations are readable; other lines are hashed.
Recent in-memory events are limited to 256; high-volume ASGI records are capped
after 4096 events, with a dropped-event counter in the diagnostic snapshot.
Lifecycle/failure records continue. Journals use mode 0600 in a 0700 directory.
Journal I/O or ownership-protocol failures remain visible failures after cleanup.

## Validation and limits

The diagnostic/lifecycle tests use real owned Python subprocesses and loopback
HTTP: clean/idempotent stop, abnormal child exit, interrupted/in-flight requests,
independent listeners, stderr redaction, and retained body/audit/cleanup failures.
Intentional SIGKILL and cancellation are **fault injection**, not incident
reproduction. Python tests verify ASGI messages/responses and the original error
are forwarded unchanged while their contents stay out of telemetry.

The original 208 business cases are retained. Fourteen diagnostic cases are
additive. Final local full E2E: 222 passed, zero failed/skipped/flaky. Frontend
unit: 223 passed. Python focused/history contracts: 21 passed. Full Ruff/Format
and Mypy, frontend lint/format/typecheck and the changed E2E TypeScript check
passed. Across local instrumented runs, all 162 owned child PIDs and ports were
released and had close/cleanup receipts. These successes do not prove the original
intermittent fault is repaired. The selector business test-call AST is unchanged; only its worker/page
fixture bookkeeping moves. Original historical-source bindings, hashes and
evidence are not rewritten. Run the focused suite in the isolated test runtime:

```sh
cd frontend
APP_ENV=test DASHBOARD_TEST_PYTHON=/absolute/isolated/python \
  npm run test:e2e -- owned-server-diagnostics.spec.ts owned-server-lifecycle.spec.ts --workers=1
```

Full browser acceptance uses the existing CI synthetic seed/XLSX programs, a
dedicated PostgreSQL 16 database and the existing guarded synthetic legacy test
entry, a freshly seeded database, and UTC browser/runtime timezone matching the
CI runner. The first local full run retained 212 passes and 10 Forecast/Quality
failures: the local browser submitted a cutoff eight hours before the frozen
synthetic authority. A UTC follow-up restored forecast creation; reusing prior
import rows also caused duplicate synthetic import failures. These are separately
retained local setup issues, not reproduction of the original teardown fault.
No business source, assertion, timeout or CI setting was changed to address them.
The test runtime must not connect to a production database. Final full-suite and
exact-head CI results are reported in the PR, not prefilled here. Repeated selector validation
is a finite test experiment, never a CI retry-until-green policy.

This observes failures; it does not guarantee telemetry survives an OS-level
worker SIGKILL or prove historical process timing that was never recorded.
Root cause and permanent remediation remain open until a correlated failure is
observed and reproduced. No forecast algorithm, real data, Tag/Release, model
promotion, production deployment, TD-03B or V0.22 work is included.
