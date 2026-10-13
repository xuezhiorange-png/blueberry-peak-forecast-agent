# V0.18 S2 — Authorized saved-run discovery and selection handoff

Task: `V0_18_S2_AUTHORIZED_SAVED_RUN_DISCOVERY_AND_HANDOFF_R1`.
Base main: `9b894b66a018c78de11bf01de4cc1daa3408db40`.
Owner explicitly authorizes this backend implementation. This does not authorize
Ready, Merge, deployment, real accounts/grants, production migrations or S3–S6.

## Delivered transport contract

Exactly three new controlled endpoints use the existing local END_USER session:

| Endpoint | Input | Protected result |
| --- | --- | --- |
| GET `/api/v1/business-access/scope` | No query parameters | Only active own organization/entity scopes, FORECAST/QUALITY data types, capabilities, principal grant revision and catalog snapshot |
| GET `/api/v1/business-access/saved-runs` | target_season, hierarchy_level, entity_id, forecast_family, origin_from, origin_to, page_size, cursor | Minimal authorized saved-record headers and next_cursor; no daily quantities, business totals or global count |
| POST `/api/v1/business-access/selection` | forecast_identity, expected_source_result_hash, grant_revision, catalog_snapshot; optional handoff_token when revalidating consumption | Canonically verified identity/source/projection hashes and a 300-second signed handoff; no business quantities |

JSON envelope: `schema_version=V0_18_BUSINESS_ACCESS_R1`, `status=READY|ERROR`,
`data` (null on rejection); errors have a fixed public `code`. All responses are
`Cache-Control: no-store`. Scope and selection reject query parameters; repeated
or unknown list parameters are rejected. Query limit: 8192 bytes; selection body:
131072 bytes. Page size defaults to 20, maximum 100. Existing HTTPS, Secure /
HttpOnly / SameSite cookie, trusted Origin and synchronizer CSRF requirements
remain unchanged; wrong modifying Content-Type retains the existing 415 behavior.

## SQL authority and pagination

The server first reads only effective grants belonging to the authenticated
Principal and a configured trusted organization. ADMIN is not a forecast grant.
Quality grants are independent, including their frozen evidence bindings.
BASE, REGION and COMPANY grants never imply one another. Full saved identity
and expected source hash are matched; unsupported families or inconsistent
bindings fail closed. Neither current registry names nor client role headers
create authority. No future record automatically becomes authorized.

The existing PostgreSQL operational/hierarchical saved-run tables are reused.
Metadata SQL is restricted to physical source-kind/run-ID pairs derived from
these effective exact grants **before** reading saved-record headers. It does
not select daily tables, source request snapshots, business quantities or totals.
Full header identity/hash is validated against each approved binding. The saved
canonical entity label is used, not a reconstructed current registry label.
An authorized missing record returns 404; drift returns 409. Nothing substitutes
another run, rerun, source, entity or season.

For snapshot invalidation, the adapter reads bounded **authorized-only** minimal
headers, not the global forecast catalog. Maximum effective grants is 10,000;
exceeding this resource bound returns 503 rather than silently truncating grants.
The snapshot hashes effective bindings, validity, trusted server directory
configuration and authorized minimal headers. This intentionally invalidates a
cursor/handoff when any record in that approved directory disappears or changes.
It is a metadata integrity digest, not a recalculated forecast result hash.

Page selection itself is a second PostgreSQL query: approved IDs → SQL filters →
keyset predicate → ORDER BY → LIMIT(page_size+1). Python only removes the single
look-ahead row; it does not filter unauthorized rows or sort business records.
The six-column order is:

`origin_date DESC, source_kind ASC, forecast_family ASC, run_id DESC,
entity_id ASC, source_result_hash ASC`.

Identical grants do not duplicate a record. Equal numeric IDs in different
source tables remain separate. Rerun parent IDs are displayed only when that
physical parent is also explicitly authorized. Header completeness is marked
`canonical_verification_required=true`; it is not a claim that daily integrity
was verified by the list endpoint. Short/partial windows are never padded.

## Signed contexts and consumption

`BUSINESS_ACCESS_SIGNING_KEY` is a separate server secret (at least 32 UTF-8
bytes; deployers must generate a cryptographically random secret). Missing or
insufficient configuration returns 503, never an unsigned fallback. HMAC-SHA256
uses a versioned domain separator, canonical UTF-8 JSON and strict unpadded
base64url. The context purpose separates cursor and selection tokens.

Cursor TTL is 900 seconds and maximum encoded length is 2048 bytes. Selection
TTL is 300 seconds. Both bind Principal, session ID, authentication/grant
revisions, effective directory digest and catalog snapshot. Cursors additionally
bind filters/page size and the full keyset; handoffs bind the complete forecast
identity and source hash. Tokens are integrity-protected, **not encrypted** and
never bearer credentials. They contain no cookie token, signing key or MCP key.

A consumer must retain a valid END_USER session, submit the full identity/hash
and current revision/snapshot, and revalidate the handoff. The same selection
POST supports this through optional `handoff_token`; it repeats exact grant
authorization and original Canonical Read. Future internal consumers must use
this complete service/release sequence, not `Signer.verify()` in isolation.
No new endpoint or Dashboard/MCP integration is silently added.

## Canonical read and response release

Selection performs AUTHENTICATE → CAPABILITY/EXACT GRANT → authorized metadata
validation → existing `ForecastIntelligenceReadService.curve()` → protected
response release. The original repositories validate persisted summary, daily
series, source identity/hash and lineage; no new forecasting or ranking math
exists in this package.

Before actual ASGI headers/body, a separate fresh READ COMMITTED transaction
loads the session and takes the existing shared subject-row lock. It checks
account validity, password-change state, role, session, auth/grant revisions,
effective grants and current catalog snapshot. Selection re-runs Canonical Read
and compares the original projection hash; natural grant/session expiry and
token expiry are checked again immediately before sending. S1 revokers take
the same account row exclusively. Revocation committed before this release
gate denies the entire sensitive response; the shared lock spans headers and
body. Already transmitted bytes cannot be withdrawn. Cancellation releases
the transaction/lock; it does not perform business writes.

Errors: 401 invalid session; 403 ungranted resources (existent or nonexistent,
before any sensitive query); 404 authorized missing run; 409 identity/hash/
revision/directory conflict; 422 malformed filters/context/body; 413 body limit;
503 database, trusted authority or signing configuration unavailable. No SQL,
private paths, credentials or raw internal exceptions are returned.

## Evidence, regression and stage boundaries

Tests use fresh disposable loopback PostgreSQL databases with complete Alembic
upgrade and explicit SYNTHETIC identities/canonical saved runs. Fault-injection
tests temporarily disable immutable triggers **only in a generated disposable
database**, restore them and prove corruption is refused; normal API reads have
SQL-observed zero business DML. Real ASGI tests commit revocation before send,
assert null error bodies, and use PostgreSQL NOWAIT to prove lock/cancellation.

The new machine evidence binds exact source bytes and test results. Frozen S1
runtime/D03 evidence retains its original expected hashes: the two affected
historical tests read legitimate historical code from merged PR #717/#718
commits, while current code executes current runtime tests. Frozen Markdown,
JSON and all 260 historical evidence bytes remain current-worktree checked.
No historical expected hash or governance assertion is weakened.

S1 implementation was merged through #717 and simple-admin closure #718. The
current base includes #721's reviewed timestamp-flake correction; main push CI
38425016611 succeeded. Historical S1 `formal_complete=false` snapshots are not
rewritten or presented as new approval. Current explicit Owner S2 authorization
is recorded separately. S2 remains subject to independent review and subsequent
Owner Ready/Merge authorization.

No new tables, migrations or dependencies; no frontend, MCP, read/decision
business-service or frozen model changes. Dashboard business selection is still
not connected (S4); production deployment and real multi-user acceptance remain
NOT_READY. Final exact-head CI is recorded externally against the submitted HEAD
in the Draft PR receipt, not self-referentially inside a changing evidence file.
