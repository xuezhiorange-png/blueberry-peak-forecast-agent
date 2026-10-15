# V0.18 S6 — isolated business and security acceptance R1

TASK_ID=V0_18_S6_BUSINESS_AND_SECURITY_ACCEPTANCE_R1. Owner authorized tests,
test-only composition, evidence, push, Draft PR and exact-head CI. No production
fix, deployment, Ready/Merge, release or Version Closeout is authorized.

## Baseline and audit chain

Fresh fetch verified main `fc0b88cf222567e4821a9d11589331f6a7963e04`, merged S5
PR #726, main CI #38703671252 attempt 2 completed/success. Latest formal release
is v0.17.0. A new independent worktree protects all earlier worktrees/untracked
files. S1 #717/#718, S2 #723, S3 #724, S4 #725 and S5 #726 merge/CI facts are
queried again into the new machine evidence. Historical false authorization and
formal-completion fields remain their original snapshots, not rewritten.

## Reproduction and ownership

With the locked Python 3.12 environment, native PostgreSQL tools, OpenSSL and
locked frontend dependencies on PATH, from the repository root:

```sh
python -m backend.tests.acceptance_s6.run --output /tmp/SYNTHETIC-s6-NEW --browser
```

The output directory must not exist. `--s6-only` is a focused diagnostic mode,
not full regression acceptance. The default composes all existing S5 runtime
tests, S1 local_auth, S2 business_access, S3 policy/PostgreSQL and new S6 cases.
The browser command executes both the existing real-auth business-flow spec and
the new S6 spec. No previous S5 result is inherited as a current test result.

The S6 wrapper changes test command selection only. The exact immutable S5 runner
still creates the private SCRAM cluster, records device/inode/data directory,
handles repeated SIGTERM/SIGINT, cancels only its owned business process group,
settles pg_ctl startup, verifies the postmaster and stops only its own directory.
Every run records PostgreSQL PID absence, closed listener, shutdown exit, logs
and source hashes. Private keys/passwords/dumps and complete private PG data are
retained locally, never published. SIGKILL/power-loss recovery is not claimed.

## Same authority, four observations

The new TLS matrix uses literal SYNTHETIC saved runs seeded through the actual
canonical repositories. BASE, REGION and COMPANY have independent exact grants.
The real production HTTP App and independent operational MCP App share the same
disposable PostgreSQL factory. Actual MCP ClientSession initialization, discovery
and calls are used; all eight tool schemas are compared with current definitions.
Every business response is compared as full structured JSON against the direct
canonical read/decision service, including raw Decimal strings and all hashes.
Text JSON must equal structuredContent. Display rounding does not weaken this
payload comparison. Literal expected totals are numeric fixture assertions only.

The browser harness extends, rather than replaces, S4's actual PG/HTTPS harness.
It starts an independent TLS MCP App over **the browser's same database**. Fixed
test-only observation endpoints call actual canonical services and MCP SDK; the
browser compares its actual protected HTTP response with those observations and
then asserts the corresponding DOM values. No page.route/mock payload, fabricated
actor, second authentication system, or browser business calculation is used.
The extension is never imported/mounted by production.

The original two bases retain their complete 15-day fixtures. An additional base
has a literal two-day business window, inserted before the existing business DML guard. Missing
dates and H7/H15 summaries stay absent. No model training/inference experiment or
actual harvest access occurs. Forecast source/model identity is not M1 Ridge
historical Quality identity. POINT is not proven P50; unavailable planning bounds
are not calibrated quantiles or POINT fallback; attribution is not causal.

**Metric boundary:** the current frozen HTTP/MCP/Dashboard contracts expose
D1..D7 cumulative quantity, D1..D15 cumulative quantity and the saved daily peak.
They do not expose a maximum-over-all-contiguous-seven-day-window metric. S6
verifies the existing prefix semantics, never relabels H7 as a rolling peak and
does not invent a new authority field. Four-surface rolling-seven-day-maximum
acceptance is NOT_VALIDATED / SOURCE_CAPABILITY_UNAVAILABLE, not an accuracy PASS.

## Business/security coverage

| Requirement | Current execution / observation |
| --- | --- |
| Login, first change, Cookie/CSRF, logout/account switch | Existing real-auth browser cases rerun; S1 tests rerun |
| Scope, filters, pagination, signed selection, cursor/handoff expiry/isolation | S2 runtime suite rerun; new S6 full-identity TLS selection |
| BASE/REGION/COMPANY, season/family/run/hash, independent Quality, ADMIN | New TLS denials and parity; S1/S2/S3 regression; browser exact selection |
| Zero sensitive work | SQL observer + Quality evidence-read boundary + original simulation observer, with a real allowed-work positive control |
| In-flight END_USER revocation | New real TLS canonical-read barrier, committed account/grant revocation, actual response contains no sensitive body |
| MCP rotation/disable/revoke/concurrency/timeout/cancel | Current S3 cases and S5 actual two-worker POSIX/TLS cases rerun |
| Legacy denial, Host/Origin/CSRF/misconfiguration | Actual production entry via S5 TLS cases rerun; no legacy-test fallback |
| PostgreSQL fault/recovery, source/catalog drift | S1/S2/S3 actual database/source cases rerun |
| Backup/restore/reapproval and rollback | Fresh actual pg_dump/pg_restore/hash/quarantine and same-compatible-version stop/revoke/restart tests rerun |
| DIRECT/WORKFORCE, bounds unavailable, server comparison | New complete TLS payload matrix; browser sends its actual inputs to SDK/canonical observer |
| Input/revision/logout clearing | Real browser stale ranking, revoked session, selection cancel/reopen/late response and account switch |
| Logs | Existing runtime caplog secret checks + new TLS secret checks + runner log scan; publisher excludes all credentials/dumps |

Zero-work counters distinguish authorization metadata queries from sensitive
forecast SQL. The Quality observer wraps the actual synchronous fixed-file read
boundary and delegates unchanged; zero boundary entries prove zero file reads.
Its positive control performs a real authorized Quality read. Simulation likewise
delegates to the original function, and SQL observations do not replace results.
An HTTP 403 without these observations is not zero-read evidence.

Request/release locks are tested at actual ASGI send and real TLS boundaries.
Revocation committed before the release gate prevents sensitive output. Bytes
already sent cannot be withdrawn, and remote idle DOM clearing still depends on
the existing focus/poll/request behavior, not an invented push notification.

Local opaque sessions and service-account keys have no JWT issuer/audience input;
those OIDC checks are NOT_APPLICABLE to this route, not reported as tested OAuth.
MCP remains SERVICE_ACCOUNT_ONLY, with exact run and independent Quality grants.
Cross-host/NFS/Windows revocation remains NOT_VALIDATED.

## Browser states, accessibility and provenance

The new spec covers five pages at six specified viewports in both Chromium
projects. Narrow Chromium is not iOS. The state matrix distinguishes real
READY/EMPTY/PARTIAL/NOT_AVAILABLE/NO_CURRENT_ACTUAL and runtime failures from
component-only state coverage. No fictional READY attribution/upper authority is
manufactured merely to fill a matrix. Unit state tests are not real browser proof.
Any requested browser-state cell without a real source stays NOT_VALIDATED in
the matrix; S6 does not silently turn partial coverage into a full product PASS.

Checks include exact daily values, source hashes, server simulation/ranking,
H1/H3/H7/H15 date prefixes, focus return, reduced-motion preference, 200% base
font sizing, auxiliary data table and scrollWidth <= innerWidth. Existing
close/Escape/native-close/late-response and forced-password-change cases rerun.
Real iOS Safari, soft keyboard and screen-reader acceptance remain NOT_VALIDATED.

New screenshots are explicit Playwright attachments. The publisher keys them by
spec, complete case title, project, viewport-bearing attachment name and result
index; duplicate provenance/destination is rejected before writing. Files are
created exclusively, never recursively flattened by desktop/mobile filename.
Each SHA256 binds the exact current-run raw path and test result. The existing
spec's screenshots are not silently relabelled as fresh S6-spec captures.

## Development failures, final evidence and governance

An initial diagnostic run retained four new-test failures: three numeric literal
string-format mismatches (980 versus the canonical 980.000000), and one invalid
empty service-account fixture rejected by the real policy schema. Test inputs
were corrected; full JSON/hash equality and production rules were not weakened.
Initial runs are diagnostic, not final source-version acceptance. Their owned
clusters were verified stopped and their logs remain local.

Machine evidence binds the successful final-source run, source/artifact SHA256,
fresh JUnit properties, browser comparisons/screenshots, cleanup and limitations.
Static checks and full CI remain distinct evidence levels. The committed evidence
cannot hash its own future Git commit; final HEAD, CI run/attempt/jobs/Canary are
bound by the post-commit exact-head receipt, not fabricated in advance.

All V0.16–V0.18 historical docs/evidence remain byte-identical. Production code,
math, database schema, MCP/Dashboard runtime, dependencies and CI workflow are
unchanged. No real account/grant, production DB, deployment or current actuals.
Open frontend dependency advisories from S5 remain open, not erased by green CI.
RPO/RTO/retention/operations ownership, actual credentials/catalog/HTTPS/network,
real devices and deployment approval remain production prerequisites.

PRODUCTION_READINESS=NOT_READY. S6_FORMAL_COMPLETE=false. Ready/Merge/Deploy/
Tag/Release/Version Closeout are not authorized. STOP after Draft PR/exact-head CI
or a reproducible production-defect blocker; independent review remains external.
