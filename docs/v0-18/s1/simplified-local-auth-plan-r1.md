# V0.18 S1 Simplified Local Authentication Plan (R1)

## Decision summary

The Owner has selected a simpler first-release direction: administrator-provisioned local username/password accounts, two application roles, explicit server-enforced data grants, and revocable server-side sessions. This document records that new direction as an additive planning decision. It does not replace the historical OIDC recommendation, amend the frozen V0.18 S0 scope, or authorize S1 implementation.

**SCOPE_AMENDMENT_REQUIRED=true before production S1 implementation.** The amendment status is `PENDING_OWNER_DECISION`. The prior S0 and S1-preflight records remain unchanged. Their OIDC-based identity recommendation and pending decisions are historical evidence, not silently rewritten.

The main compatibility issue is that the frozen design assumes a trusted issuer/subject identity and principally exact saved-run grants. The simplified product flow additionally needs a stable local principal and independently revocable BASE, REGION, COMPANY, and Quality entitlements. Owner must approve a narrow, append-only S0 scope addendum before implementation. No runtime behavior is changed here.

| State | Value |
|---|---|
| Owner direction | `SIMPLIFIED_LOCAL_AUTH` |
| S0 formal completion | `true` (historical live governance) |
| S1 preflight formal completion | `true` (historical live governance) |
| S1 production implementation authorized | `false` |
| Production code / migration changed | `false` |
| OIDC / Keycloak implementation | paused; not part of this plan |
| MCP end-user delegation | paused; MCP remains service-account-only |

## What changed, and what did not

The earlier S1 preflight compared enterprise OIDC and a self-hostable OIDC provider and recommended OIDC conditionally, while marking the actual provider, client registration, and enterprise deployment prerequisites unverified. That remains the accurate record of the earlier review. The Owner now directs that the first implementation use local accounts rather than waiting for an unverified enterprise identity provider.

The new plan does not claim local passwords are already implemented, that any account exists, or that the application is production-ready. It retains the security invariants from S0: server-derived identity, default deny, authorization before protected business reads, exact forecast identity and source-hash verification, separate Quality authority, revocation, and no resource-existence disclosure to unauthorized callers.

## Existing architecture and adaptation assessment

| Existing component | Current meaning | Proposed adaptation / boundary |
|---|---|---|
| `TrialActorDep` and `get_actual_harvest_actor` | Server-configured coarse actor; not an authenticated end user and not a per-resource ACL | Keep as legacy compatibility only until separately adapted or network-restricted. Never map its shared actor name to a local user. |
| S1/S2 HTTP read and decision APIs | Use existing trial actor permissions such as `may_read_forecast` / `may_read_quality`; these do not prove resource-level authorization | Add a future authenticated-principal dependency and shared authorization facade before repository access. Preserve response/business contracts; deny before forecast/quality reads and simulation. |
| S3 `ServiceAccount`, exact `RunGrant`, `QualityGrant` | Server-owned MCP identity with explicit grants | Retain for MCP. Do not treat it as a human identity or broaden it into user delegation. Preserve all eight tool names and business payloads. |
| V0.17 Dashboard HTTP client | Browser calls APIs; no local login/session/BFF contract exists | Future Dashboard sends same-origin session cookies through a narrowly scoped BFF/reverse-proxy boundary; no password, service secret, or bearer secret in browser storage. |
| Forecast saved-run selection | Requires full `ForecastIdentity` and source result hash; normal authorized discovery is absent | Future discovery must first establish principal/capability/scope, then list only authorized records and bind cursor/handoff to authorization version. No global `latest` or unauthenticated LIST. |
| Database and dependencies | Existing application persistence exists, but no local account/session/grant runtime or password-hashing dependency was found | S1 may propose additive schema and dependency only after explicit amendment/implementation approval. This task creates neither. |

The intended authorization order for future protected operations is: authenticate local account and resolve active principal → check capability and scope grant → canonical saved-run identity/hash verification → read/project business data or execute a permitted simulation. A denial must not query the protected forecast/quality repository. Generic not-found/forbidden behavior must not reveal whether an unauthorized run exists.

## Proposed identity, account, and role contract

### Accounts and stable principal

* No public self-registration. An authorized administrator provisions, disables, and resets named accounts.
* Each account maps to a server-created, immutable, non-recycled `principal_id` (opaque random identifier). Username is a login/display attribute, never the authorization key. Renaming a username does not change the principal.
* A login session resolves the account to this principal server-side. The client cannot submit or override `principal_id`, role, organization, actor, or `source_system` to obtain authority.
* Disabled accounts cannot authenticate; disabling, password reset, logout, or material grant revocation invalidates relevant sessions. Deleted identities must not cause historical grants to attach to a newly created account.
* `END_USER` accounts and `SERVICE_ACCOUNT` principals are separate identity classes and credential stores. No shared human login or default account.

### Roles versus data grants

Exactly two human roles are in scope:

* `ADMIN`: account/role/grant administration capabilities. `ADMIN` alone does not grant forecast or historical Quality access.
* `BUSINESS_USER`: ordinary business use, limited to explicitly granted capabilities and resources.

Authentication role and data access are separate checks. Even an administrator must receive explicit forecast or Quality grants before reading those data. A future break-glass process, if desired, requires separate Owner approval and auditable controls; it is not implicit in `ADMIN`.

### Password and session safeguards

* Store only a salted adaptive password hash produced by a maintained password-hashing implementation; never plaintext, reversible encryption, or a fast general-purpose hash.
* Proposed algorithm: Argon2id. Use at least the current OWASP baseline (19 MiB memory, 2 iterations, parallelism 1), then benchmark and record an approved deployment-specific cost. The repository currently has no identified password-hashing library; selecting and adding one is future S1 work and needs dependency review.
* Generic login failure response, bounded login attempts/rate controls, password reset through an administrator-controlled process, and forced password change after a reset. Reset delivery, recovery identity checks, and rate limits remain Owner decisions.
* Use an opaque, high-entropy server-side session identifier; store only a verifier/digest server-side. Rotate on authentication and privilege changes. Enforce server-side idle and absolute expiry, logout invalidation, account disable/reset invalidation, and grant-revocation invalidation.
* Browser cookie candidate: `__Host-` prefixed, `Secure`, `HttpOnly`, `SameSite=Lax` (or stricter if UX permits), `Path=/`, no `Domain`. Require HTTPS in deployment. SameSite is defense-in-depth, not a substitute for CSRF protection; use a synchronizer token and Origin validation for state-changing requests.
* Do not put session identifiers, passwords, or secrets in URLs, localStorage, browser logs, or error messages. No credential values belong in evidence or test fixtures.

Algorithm and cookie values above are a proposed implementation contract, not deployed configuration. Session lifetimes, lockout thresholds, password length policy, reset ceremony, and operational ownership remain pending.

## Proposed resource authorization contract

### Grant identity and non-inheritance

The server is the only authority that creates or revokes grants. Every decision uses a stable `principal_id`, capability, explicit scope, grant revision, and active/revoked status. Organization membership and BASE/REGION/COMPANY identifiers must come from an Owner-approved authoritative organization/entity source; display names and client-provided strings are not authority.

Forecast scope is explicit and non-inheriting:

* `BASE`: exact base entity grant.
* `REGION`: exact region entity grant.
* `COMPANY`: explicit company-level grant.

A BASE grant does not imply its REGION or COMPANY aggregate, and a REGION grant does not imply COMPANY. No wildcard or “all current/future children” grant by default. Any future parent-to-child expansion requires an explicit, reviewable policy decision and separately tested semantics.

For a concrete saved forecast, bind the access check and canonical read to the full identity: `source_kind`, `forecast_family`, `run_id`, `hierarchy_level`, `entity_id`, `target_season`, `origin_date`, `baseline_id`, `policy_version`, and `source_result_hash` (plus any required authority fields). A scope grant authorizes only the matching level/entity; the saved-run identity and hash must still match canonical persisted authority before returning data. A hash proves integrity/binding, not user authorization.

Historical Quality is a separate capability and grant. Forecast access never implies Quality access. Quality grants bind the approved evidence set/scope and version/hash, not a guessed current-season actual source.

### Administration, revocation, and discovery

* Grant writes are attributable to a named active administrator and recorded with actor, subject, scope, capability, reason, time, revision, and revocation event. No client-side grant creation.
* A grant has an explicit version/revision. Revocation invalidates server-side sessions or authorization caches as required; opaque cursors and saved-context handoffs bind to principal and authorization revision and become unusable after relevant revocation.
* BASE, REGION, and COMPANY grants are administered as distinct scopes. Grant approver, organization-boundary source, dual-control requirements (especially company scope), audit retention, and bootstrap administrator ownership remain Owner decisions.
* Record discovery must apply authorization before selecting/paginating business records. Cursors are opaque, signed or server-held, scoped to principal + grant revision + query, and must not permit scope changes. Unauthorized and nonexistent identities should have indistinguishable externally observable disclosure where feasible.
* The API must not silently select the newest run, combine different runs, use current registry state to rewrite historical hierarchy, or use a run's creator/base label as permission evidence.

## HTTP, Dashboard, legacy routes, and MCP compatibility

### HTTP and Dashboard

Future HTTP requests use an authenticated local `END_USER` principal, then the shared capability/resource authorization decision, then existing canonical S1/S2 services. S1 read and S2 simulation business calculations remain unchanged. Shared authorization must be testable at the application/service boundary so that HTTP, Dashboard-backed HTTP, and any other human-facing surface cannot disagree.

The Dashboard remains the five V0.17 pages. Future login and authorized record discovery are an access-flow adaptation only. The browser never decides grants and cannot turn an entered `ForecastIdentity` into permission. Advanced identity verification remains subject to the same server-side authorization. No login screen or frontend runtime is created in this task.

Existing Trial and legacy MCP paths are a bypass risk until assessed. Before a user-facing pilot, each route must either be adapted to equivalent authorization without changing its frozen business contract, or be blocked from the pilot network/trust zone. No claim of current route isolation is made.

### MCP

For the first release, MCP remains `SERVICE_ACCOUNT` + server-owned credential + exact `RunGrant` / independent `QualityGrant`. It has no end-user OAuth delegation and no identity forwarding from a client parameter. The eight existing tool names, schemas, computation, and business response semantics remain unchanged. A service account’s exact scope is not evidence that a human end user has that scope.

If an external assistant later needs per-human attribution, that is a separate protocol and Owner decision. Until then, MCP must be described as a separately authorized machine integration, not user-delegated access.

## Recommended stage plan (planning only)

Stage numbers and V0.18 S0–S6 identity are preserved. This replan does not skip gates or authorize any stage.

| Stage | Goal and deliverables | Dependencies / authority | Acceptance boundary |
|---|---|---|---|
| S0 (complete, historical) | Freeze business-usability scope and stage plan | Existing merged S0 evidence | Preserve its original bytes; any auth model change is an append-only scope amendment. |
| S1 | Local accounts, secure password verification, server sessions, two roles, stable principal mapping, shared resource/Quality grants, admin lifecycle and security tests | Owner approves S0 addendum; names bootstrap/admin and org authority; separately authorizes schema/dependency/runtime code. Use synthetic fixtures only. | Auth before reads; disabled/revoked access fails closed; no role-based implicit data access; BASE/REGION/COMPANY non-inheritance; Quality independent; no existence leak; service-account identity remains separate. |
| S2 | Authorized saved-run discovery, filtering, stable pagination, full identity/hash handoff | S1 formally complete; explicit S2 authorization; canonical saved-run repository | Only authorized records listed; cursor/handoff bound to principal/grant revision; no global latest; page boundaries deterministic; source identity revalidated at read. |
| S3 | Keep MCP service-account model and validate the new shared boundary without end-user delegation | S1; explicit S3 authorization; grant compatibility review | Eight tools unchanged; exact service-account grants; no human identity inference; unauthorized reads are zero. |
| S4 | Add Dashboard sign-in and normal authorized record-selection flow | S1 and S2; explicit S4 authorization; frontend scope approval | Five-page IA preserved; browser cannot self-authorize; expiry/revocation and errors recover clearly; no change to forecast math. |
| S5 | Isolated synthetic-data safe-pilot/security acceptance, route isolation, backup/restore and rollback rehearsal | S1–S4; isolated environment, credential custody and test plan approved; explicit S5 authorization | Synthetic-only; no production database/actual; prove principal/scope isolation, audit, recovery, old-route block/adaptation, and no write side effects beyond approved auth/admin operations. |
| S6 | Integrated product/security/business acceptance and closeout evidence | S0–S5 complete; explicit S6 authorization and independent review | Cross-surface authority parity, permission matrix, failure/revocation, accessibility and governance all pass; production readiness remains a separate Owner gate. |

No new prediction model, refit, training, tuning, scoring, calibration, current-season actual access, or production deployment is included in this plan.

## Scope conflicts, amendment, and blockers

The existing S0 and S1-preflight evidence must not be edited. Before S1 production work, request a formal additive amendment that:

1. Records local administrator-provisioned accounts as the selected identity route while preserving the old OIDC comparison as historical evidence.
2. Defines opaque local `principal_id` as the authenticated identity mapping (rather than asserting an unavailable OIDC issuer/subject for local accounts).
3. Extends the resource grant plan to support explicit user scope grants for BASE/REGION/COMPANY while retaining exact full saved-run identity/hash verification and separate Quality grants.
4. Makes clear that database schema/migration, password-hashing dependency, cookie/session configuration, admin bootstrap and production deployment each require their own implementation authorization/acceptance.

**Blocking prerequisites for S1 implementation:** approved amendment; designated account/grant administrator and bootstrap procedure; authoritative organization/entity identifiers and assignment owner; persistence/schema decision; password library/version and parameter approval; cookie/CSRF/HTTPS deployment settings; session/reset/rate policy; audit and backup/recovery ownership; legacy Trial/MCP route isolation plan. No local account runtime exists in the inspected baseline.

### Owner decisions still pending

1. Approve or reject the additive S0 amendment described above.
2. Name the accountable initial administrator, grant approver, organization/entity data steward, and break-glass owner (or explicitly reject break-glass).
3. Approve whether auth/session/grant state uses the existing application database with an additive migration; define backup, retention, and recovery responsibility.
4. Approve the maintained Argon2id package and deployment parameters after dependency and performance review.
5. Set username normalization/uniqueness, password policy, reset verification/delivery, login throttling, lock duration, and session idle/absolute expiry.
6. Decide company-scope grant approval and whether high-impact grants need dual control; define audit retention.
7. Decide whether old Trial and legacy MCP routes will be adapted or network-restricted before pilot, and name the enforcement owner.
8. Confirm that MCP remains service-account-only for the first release; user delegation is out of scope.

## Security references

The password/session/CSRF proposals follow current OWASP Cheat Sheet guidance; these links support the security design only and do not imply implementation or certification:

* [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
* [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
* [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

## Governance snapshot for this proposal

```text
OWNER_AUTH_DIRECTION=SIMPLIFIED_LOCAL_AUTH
S0_ORIGINAL_SCOPE_PRESERVED=true
HISTORICAL_EVIDENCE_UNCHANGED=true
SCOPE_AMENDMENT_REQUIRED=true
S1_PRODUCTION_IMPLEMENTATION_AUTHORIZED=false
LOCAL_AUTH_RUNTIME_IMPLEMENTED=false
DATABASE_MIGRATION_CREATED=false
MODEL_OR_FORECAST_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
DEPLOY_AUTHORIZED=false
TAG_AUTHORIZED=false
RELEASE_AUTHORIZED=false
```

This is a design proposal and compatibility review, not a release, implementation approval, security certification, or production readiness statement.
