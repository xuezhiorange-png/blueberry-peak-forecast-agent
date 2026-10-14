# V0.18 S3 — MCP service-account safety R1

TASK_ID=V0_18_S3_MCP_SERVICE_ACCOUNT_SAFETY_R1

Base main: `3410dd4426618a7a4b29c08cbf58aaef20196939`. Owner separately
authorized S3 implementation, SERVICE_ACCOUNT_ONLY, EXACT_RUN_GRANTS and
INDEPENDENT_QUALITY_GRANTS with isolated PostgreSQL/SDK acceptance. This is
implementation evidence, not independent review, formal completion or deployment.

## Baseline and unchanged authorities

Fresh fetch matched the requested main; PR #723 is merged at this commit. Its
post-merge push CI #38578960598 completed/success: four executed jobs succeeded,
eight workflow jobs skipped by existing event rules. Latest release remains
v0.17.0. No parallel S3 PR was found. S1 and S2 historical governance snapshots
remain untouched. GitHub #723 currently exposes no separate review record;
we do not invent one or backfill formal stage approvals into historical evidence.

The existing eight names, order, descriptions, input/output schemas, annotations,
Decimal strings and result/projection/engine/comparison hashes are unchanged.
The registry still advertises its frozen V0.17 business contract. S3 adds a
policy-aware transport, not new business calculation. HTTP uses actual local
END_USER sessions and independent SQL grants; MCP uses its own SERVICE_ACCOUNT.
An MCP key does not become a browser login or final-user delegation.

## Operational entry and trusted policy authority

The S3 operational factory is
`backend.app.mcp.forecast_intelligence_http:create_service_account_app`.
It serves only POST `/mcp/forecast-intelligence`, never the legacy MCP/Trial or
business-discovery routers. It requires `FORECAST_INTELLIGENCE_MCP_POLICY_FILE`
to reference an absolute path in an operator-owned mode-0700 directory, with
mode-0600 regular policy and stable sidecar lock files. Missing, malformed,
expired, symlinked or insecure policy fails closed (503); unsupported POSIX
locking platforms fail closed. No production configuration or credentials were
created. TLS, exact trusted Host and optional exact Origin are mandatory.
Duplicate credential headers fail authentication. No proxy identity header is
trusted. All transport responses are no-store.

The historical `create_forecast_intelligence_app(config=...)` explicit immutable
composition and `create_server(account=...)` are retained for V0.17 compatibility
harnesses only. They are **not** the S3 operational entry and do not have mutable
policy revocation guarantees. S3 acceptance must not be applied to those modes.
The old static `FORECAST_INTELLIGENCE_MCP_CONFIG` environment variable is not an
operational fallback. Safe pilot must use the dedicated S3 factory and prohibit
alternative/legacy entry points by deployment and network controls; actual
deployment/network isolation remains unvalidated.

`PolicyDocument` contains a positive monotonically published revision, an
explicit timezone-aware `valid_until`, and the existing strict MCPServiceConfig.
That validity bounds **all** accounts and exact grants in the document; publish
the earliest expiry of any included authorization and renew deliberately.
Account disable lists it in `disabled_principals` (including the last account),
or removes it while other registered accounts remain; revoke removes its grant/capability;
rotation replaces its credential. Missing permissions/grants, duplicate keys,
cross-principal grants and wildcard identities are rejected by existing schemas.
There is no automatic future-run or hierarchy grant inheritance. Quality grants
are independent; the canonical Quality reader still checks frozen evidence hashes.

`FilePolicy.publish()` is a trusted operator composition API, not an HTTP/MCP
tool, account-management API or permission for a client to publish policy. It
validates the private directory/lock, requires a strictly newer revision, writes
complete private JSON to an exclusive temporary file, fsyncs it, atomically
replaces the policy, and fsyncs the directory under an exclusive flock. Raw keys
exist only in that private authority file; no key is recorded in public evidence.
SecretStr's default redacted serialization is not used to publish credentials.
Do not edit/replace lock files or policy files outside this protocol. Same OS user,
filesystem and clock are trusted administration boundaries, not adversarial users.

## Admission, revocation and release linearization

Every HTTP request reads current policy under a shared interprocess lock, then
authenticates its sole credential and validates HTTPS/Host/Origin. The SDK tool
dispatcher checks capability, request schema, current policy revision/digest and
exact run or Quality grant **before** entering the canonical business service.
Unknown client actor/user/source-system fields cannot grant authority. Resource
identity and the expected source hash are pinned by the existing grant facade;
the existing reader/decision service verifies canonical integrity. Unauthorized
calls do not create a business database session or execute simulation.

The policy digest binds the complete exact configuration, not merely a supplied
revision counter. A policy change conservatively invalidates every in-flight
request admitted against that document, even if a different account changed.
The dispatcher rechecks after computation. All SDK messages are buffered subject
to the existing 2 MiB limit; **no protected ASGI bytes are sent at this stage**.

Immediately before actual ASGI release, the transport takes a shared flock,
reloads/validates expiry and exact digest, then holds that lock through actual
response sends. Revocation/rotation publication takes the same exclusive lock.
If publication commits first, the old response is discarded and a fixed,
redacted 503 is sent, without any old business payload/hash. If release wins,
publication cannot commit until that response completes or cancels. This is the
linearization boundary; already-sent bytes cannot be withdrawn. Business work
admitted before revocation may already have read data; it cannot release its
result after a prior successful revocation commit. New requests do not use a
cached snapshot. Expiry is evaluated at admission and the release gate.

Existing actual-body limit (256 KiB), argument limit (128 KiB), execution deadline
(30 s) and response limit remain unchanged. Nonblocking shared-lock acquisition
has a 2 s deadline and is cancellable. Cancellation and send failure close the
descriptor and release its lock. After response start, errors do not send a second
HTTP start or substitute a false successful payload. There is no business action
persistence. Slow response release can delay publication until release/cancel or
the execution deadline; operators must not confuse publication start with commit.

The SDK's JSON-response handler does not itself monitor post-body disconnects.
S3 therefore gives a separate task sole ownership of post-body ASGI receive;
disconnect cancels the SDK task group and running service work before response
release. The replay stream cannot race that monitor for disconnect messages.
An explicit post-body disconnect test proves service cleanup and zero ASGI sends.

**Proved scope:** independent POSIX processes sharing the same local filesystem
and stable lock inode. **Not proved/supported:** multiple hosts, containers with
different filesystems, NFS/distributed locking, Windows, hostile same-UID writers,
production credential provisioning or production network isolation. No distributed
revocation claim is made. Those require a separately authorized authority design;
no new tables, migrations or dependencies were added here.

## Runtime acceptance and compatibility

Tests use disposable PostgreSQL, synthetic saved runs, actual local-auth login,
real canonical readers and real MCP SDK ClientSession over HTTP. BASE, REGION and
COMPANY independently exercise all eight tool results. Complete structured JSON
and text JSON are compared to authenticated HTTP responses, including every hash,
Decimal, status and unavailable reason. DIRECT/WORKFORCE and POINT/Upper80/Upper90
simulation/comparison are compared. Unbound bounds and attribution remain
NOT_AVAILABLE; historical Quality is still M1 EXPOSED_OOT, not current accuracy.

A real loopback TLS uvicorn server with a generated synthetic certificate also
exercises SDK initialization, exact eight-tool discovery and canonical PostgreSQL
curve bytes. Its certificate is explicitly trusted by the client, not verify=false.
The listener is closed after the test. No real weather, harvest, user or grant is
read/created. Fixture seeding occurs before read acceptance, using existing
deterministic synthetic generators only; no production forecast is executed.

Independent child processes revoke grants, rotate credentials, remove accounts
and expire policy while a real canonical read is suspended. Actual ASGI captures
prove no sensitive body is sent. Another test blocks actual ASGI send, proves the
publisher cannot commit, cancels the request and proves the writer then commits.
Two concurrent accounts cannot access each other's exact runs; Quality remains
independent. Deleted/corrupted isolated records return canonical errors, not data.
Permission/identity denials use zero-session/zero-execution sentinels and SQL
observations. Timeout/cancellation and retry recovery are exercised.

Existing S1/S2 and V0.17 MCP suites remain current-runtime regressions. Historical
evidence continues to check unchanged expected SHA256 at reviewed fixed commits
for legitimately revised code/test bytes; frozen documents remain checked from
current worktree bytes. Both MCP transport historical digests were independently
verified against PR #716 commit `320f2046e3105b1b55da9cb037892571110b584a` (seven
evidence bindings each). The S1 test helper pin uses merged S1 commit
`e9812e82067dceae444ff0707ceeb2f560c1018e`; S2 revised test-source pins use this
task's merged S2 base. No expected digest or frozen file was recomputed/overwritten.

## Governance STOP

Only new S3 runtime/test/evidence and necessary historical test-source adapters
are changed. No S1/S2 authentication/calculation, MCP tool schemas, old MCP runtime,
Dashboard, dependencies, database schema, migration or CI workflow changes.

SERVICE_ACCOUNT_EXACT_GRANT_SAFETY_ACCEPTANCE is isolated local-filesystem runtime
acceptance, never final-user OAuth or production acceptance. S3_FORMAL_COMPLETE=false,
END_USER_DELEGATION=false, PRODUCTION_READINESS=NOT_READY. New exact-head CI remains
an external post-commit gate; the committed JSON cannot recursively bind its own
future HEAD/CI. The final PR receipt must independently report that run and jobs.

Ready/Merge, production database operations, real accounts/grants, Deploy,
Tag/Release and S4 are not authorized. Stop at Draft PR plus full exact-head CI.
