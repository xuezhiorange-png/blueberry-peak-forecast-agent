# V0.18 S4 — Dashboard authorized business flow

TASK_ID=V0_18_S4_DASHBOARD_AUTHORIZED_BUSINESS_FLOW_R1.
Owner authorizes frontend implementation and isolated synthetic acceptance only.
Base: `08b185b4621bf517846c986841bb5579b6c37b35` (merged S3 PR #724).
Fresh GitHub verification: post-merge push CI `38657747572` completed/success;
latest formal Release remains `v0.17.0`. No parallel S4 PR was open.

## Delivered workflow

The existing five-page React Dashboard now requires actual local authentication:
login → mandatory first password change when required → authorized scope/list →
explicit saved-record selection → signed server handoff → canonical curve
verification → the same Overview, Forecast, Attribution, Capacity and Quality.
There is no automatic latest, new primary navigation, administrator console,
model execution or client calculation of authoritative business quantities.

`SessionGate` restores only `/auth/me`, never a previous forecast selection.
It shows a server-authenticated Principal identifier and role, not a client actor.
Login/change-password use the real endpoints; a rotated session is checked again
with me. Password inputs are not retained after success, stored or logged. Session
credentials remain exclusively in the Secure/HttpOnly/SameSite Cookie. Logout
unmounts all business content before its network round trip; if the server cannot
confirm logout, the user is warned rather than told that server revocation succeeded.

All POSTs, including capacity simulation/comparison, first acquire the actual
synchronizer CSRF token. Token acquisition and its associated write are serialized
because the server rotates that token; concurrent POSTs cannot invalidate each
other's token. The browser supplies Origin naturally. No fabricated actor, Origin,
Cookie or MCP secret is used by production JavaScript. Requests are same-origin,
no-store, nonredirecting and allowlisted, with existing response schemas, size
bounds and safe fixed error messages.

## Authorized discovery and selection

The selector reads only the real S2 scope and saved-runs endpoints. It shows the
authorized entity labels, hierarchy, season, forecast type, origin, saved time and
completeness. Ordinary users never type run/hash/baseline/policy identity fields.
Filters only narrow the server-authorized set. Editing a filter cancels work,
discards the previous page/cursor, and requires an explicit query. Next-page uses
only the server-issued cursor with the same filters; no global count or browser
sorting, aggregation or permission inference is added.

Selection submits the exact server-listed ForecastIdentity, source hash, grant
revision and catalog snapshot. The complete identity/hash in the handoff must
match that selected row. The actual S1 curve is then read and its identity,
source hash and projection hash verified before one atomic context commit.
Only READY/PARTIAL nonempty canonical curves can commit. Deleted, corrupted or
conflicting records never fall back to another run/rerun/season/entity.

The signed handoff stays in memory, is not bearer authorization and is never put
in a URL or storage. The context expires conservatively 300 seconds after the
selection started; expiry removes the selection, curves, drafts, costs, results
and rankings and requires a new explicit selection. Each subsequent HTTP read
still independently authenticates and authorizes on the server. This UI does not
replace server revocation or the S1/S2 response-release gates.

## Isolation and recovery

AbortController, request-boundary revisions, selector generations, resource keys
and scenario input revisions prevent old work from replacing newer state. A
cancelled request cannot clear a new request's busy state or commit after dialog
close/unmount/StrictMode cleanup. Closing normally preserves the previous valid
forecast and selected date. A 401 physically unmounts the complete authenticated
tree, aborts its requests and returns to login. A protected forecast permission
rejection or authority conflict clears affected business context and remounts
its children, eliminating old curves, costs, drafts and rankings. The selector
opener receives focus after conflict recovery. Failures do not leak server details.

Quality is independently authorized: a missing Quality grant does not fabricate
metrics or revoke an otherwise valid forecast grant. Historical M1 identity stays
EXPOSED_OOT/2025–2026/BASE_COHORT_AGGREGATE. Current-season actuals are not read,
imported or scored. Unbound Upper80/90, attribution and child contributions remain
NOT_AVAILABLE, with no POINT fallback, synthetic factors or contribution math.

An active tab checks me every 60 seconds and on focus; every actual request still
has immediate server checks. **No push revocation exists**: an idle page cannot
know about a remote change before a response, focus check or poll. Already viewed
or transmitted bytes cannot be withdrawn. This is not a claim of instantaneous
remote DOM erasure, deployment approval or production multi-user acceptance.

## Verification and provenance

New unit tests cover physical clearing, projection mismatch, filter/cursor reset,
late authentication, strict identities, cancellation, close/Escape/native close,
previous context preservation and StrictMode. Existing business response, Decimal,
hash, eight-state, chart/table, stale scenario and five-page tests remain.

`business_pg.py` is a test-only loopback HTTPS server serving the built frontend
and the **actual production S1/S2 application**. It creates a UUID-named isolated
PostgreSQL database, upgrades current Alembic, inserts literal synthetic canonical
saved runs, accounts and exact grants, and drops that generated database on exit.
It exercises real browser Cookie/CSRF/Origin, forced password change, BASE/REGION/
COMPANY records, DIRECT and WORKFORCE simulation/comparison, server ranking,
revocation and closed-dialog late responses. The read phase forbids business DML.
Its fixed synthetic control endpoints and literal passwords are never imported
or mounted by the production application. Self-signed loopback TLS is accepted
only by the test browser; production certificate provisioning is not validated.

The older SQLite S5/S6 presentation/parity harness receives an explicitly
test-only authentication/list adapter so its unchanged canonical services,
HTTP/MCP payload comparisons and cancellation assertions can still run against
the new business UI. That adapter **is not authentication or grant acceptance**;
only the PostgreSQL/real-auth tests provide those new runtime assertions.
Legacy Trial remains on its existing isolated test application. No production
backend, MCP runtime, schema, migration, dependency or CI workflow was changed.

Screenshots have unique spec/case/project/viewport source paths and SHA256 in the
new evidence. Six viewports cover all five pages. Layout tests assert document
scrollWidth ≤ innerWidth, not hidden overflow. Keyboard/dialog/date controls,
large-text and reduced-motion regressions remain. Chromium narrow viewport is
not iOS Safari, a soft keyboard, or a screen reader; all three remain unvalidated.

Historical SHA256 assertions use reviewed immutable Git bytes for legitimately
revised source files, not new expected digests. All 260 frozen history files and
old S4 design materials remain byte-identical. The V0.17 frontend/test snapshot
is independently checked at PR #716's immutable commit `320f2046…`; S1 runtime
test source uses its merged S1 snapshot, and S3 source-helper/test pins use this
S4 base. Current code continues to execute current runtime regressions separately.

## Governance and limitations

S4_FORMAL_COMPLETE=false; PRODUCTION_READINESS=NOT_READY. There are no real users,
grants, current actuals, deployment, model experiments or production migrations.
Real bootstrap/admin/organization provisioning and operational certificate/network
isolation remain Owner-controlled production dependencies. S5 is not started.
Committed evidence records local tests; final exact-head CI and Draft PR identity
are reported externally after commit, avoiding a self-referential evidence hash.
Ready/Merge/Deploy/Tag/Release remain unauthorized. STOP after Draft PR and CI.
