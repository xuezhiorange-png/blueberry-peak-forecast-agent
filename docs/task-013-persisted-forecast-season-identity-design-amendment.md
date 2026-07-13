# TASK-013 Persisted Forecast-Season Identity Design Amendment

Status: Draft PR design fixup; implementation and migration are not authorized.

## §1 Context and current blocker

At reviewed PR #96 head `8de1d371e54a044c63e9f4bbb3fbb72b8dfa0864`,
the PostgreSQL production-wiring path correctly fails closed with:

```text
AUTHORITY_SCOPE_MISMATCH
reason=PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE
```

Production TASK-009 does not persist a hash-bound forecast-season identity on
`HarvestStateRun`. TASK-013 therefore cannot prove that a Task 9 candidate has
the same season as the normalized request. CI success proves the capability
gate is stable; it does not complete Slice B.

This amendment defines the source, persistence, versioning, selector,
historical compatibility, and future test contracts. It authorizes no code,
test, ORM, fixture, migration, Ready, or Merge action. The document is already
published in independent Draft PR #97.

## §2 Frozen terminology and existing authority surfaces

### §2.1 Frozen terms and field types

The following fields have distinct meanings and MUST NOT be aliases:

| Field | Type | Meaning | Authority use |
|---|---|---|---|
| `requested_forecast_season` | `int \| str \| null` | Caller token, such as `2026` or a season code | Input only; never a database identity |
| `effective_forecast_season_id` | positive `int` | Resolved `dim_season.id` | TASK-013 selector authority |
| `effective_forecast_season_code` | non-empty `str` after successful normalization | Resolved `Season.code` disclosure | Required hash-bound disclosure; never selector authority |
| `HarvestStateRun.forecast_season_id` | nullable ORM `int`, FK to `dim_season.id` | Persisted TASK-009 season authority | Normal selector authority for eligible v2 rows |

`effective_forecast_season` is retired as an authority-bearing field because it
has previously represented a year-like token. A future implementation may keep
it temporarily as a deprecated caller-token disclosure, but it MUST NOT carry
or imply a database ID and MUST NOT be read by selectors.

### §2.2 TASK-008 season surface

`Season` is the source object:

```text
dim_season.id          BIGINT primary key
dim_season.code        TEXT unique
dim_season.start_date  DATE
dim_season.end_date    DATE
```

`Season.id` is opaque. It is not a year and MUST NOT be derived from a date or
parsed from `Season.code`.

`MaturityForecastRequest` carries `season_id`, but `MaturityForecastRun` has no
direct season column. Its persisted season lineage is:

```text
MaturityForecastRun.plan_id
  -> FarmSeasonVarietyPlan.id
  -> FarmSeasonVarietyPlan.season_id
  -> Season.id
```

`MaturityForecastRun.input_snapshot` stores `plan_id`, `plan_version`, and
`plan_row_hash`, not a direct season ID. This lineage is suitable for audit and
v2 rematerialization candidate identification. It is not the normal Task 9
selector authority.

Forecast season is a forecast/business-request scope. It is not a
`MaturityModelRun` training identity because one model run may cover multiple
seasons.

### §2.3 TASK-009 season surface

The current `Task9ARequest` contains neither `season_id` nor
`forecast_season`. The gap begins at the Task 9 request contract; it is not
merely a field dropped while constructing `input_snapshot`.

Task 9 historical-authority input tables contain `season_id`, but those source
rows do not automatically bind the resulting `HarvestStateRun`. The run must
record, hash, persist, and reload-validate its own season identity.

Current `HarvestStateRun` persists Task 8 lineage, date scope, destination,
canonical snapshots, child-row counts, hashes, and schema versions. It has no
direct season authority.

### §2.4 TASK-010 season surface

`ResidualModelPredictionRun` binds exact `task9_run_id` and
`task9_result_hash`, along with its prediction signature and hashes. Task 10
does not need a duplicate season field. New Task 9 v2 identity changes flow
transitively through the Task 9 result hash into Task 10 prediction identity.

### §2.5 TASK-013 current gap

The current `effective_forecast_season` is an integer policy result and may be
derived from `effective_as_of_date.year`. It is not a `Season.id`. The current
selector probes non-production `input_snapshot["forecast_season"]`; production
Task 9 never writes that key. Both default and explicit override paths already
share one scope validator, which remains the required enforcement shape.

Source-investigation answers:

1. Task 9 request does not currently carry the identity.
2. Task 8 lineage can prove some historical candidates but is indirect.
3. No direct persisted Task 9 season identity exists today.
4. Adding the identity to canonical Task 9 v2 output changes result and
   canonical payload hashes.
5. Task 9 input, output, and result-hash contracts require explicit v2
   versions.

## §3 Non-negotiable anti-guessing constraints

- `Season.id` MUST NOT be assumed equal to a year.
- `Season.code` MUST NOT be parsed into a database ID.
- No season identity may be inferred from `as_of_date.year`, forecast dates,
  prediction dates, timestamps, row IDs, insertion order, or current/latest
  data.
- A caller token is not authority until a formal resolver returns exactly one
  existing `Season.id`.
- Default and explicit override Task 9 selectors MUST run the same season,
  schema, hash, and canonical-mirror checks.
- Existing v1 canonical output and hashes MUST NOT be modified in place.
- Plan/Task 8 lineage can identify rematerialization candidates only; it cannot
  make a v1 row selector-eligible.
- Resolution failure stops before the Task 9 selector.

## §4 Option A — dedicated persisted column

The normal selector authority is:

```text
harvest_state_run.forecast_season_id BIGINT NULL
  REFERENCES dim_season(id) ON DELETE RESTRICT
```

It is physically nullable for historical v1 compatibility. Every new Task 9
v2 completed or blocked write MUST have a non-null positive value.

Recommended portable scope index:

```text
ix_harvest_state_run_forecast_season_scope
  (forecast_season_id, status, destination_factory_id,
   as_of_date, forecast_end_date)
```

Benefits:

- real FK-backed `Season.id`;
- efficient PostgreSQL and SQLite filtering;
- typed equality without JSON extraction or Task 8 joins;
- self-contained Task 9 authority;
- direct disclosure in the TASK-013 Task 9 authority envelope.

Costs:

- Task 9 request/output/hash/ORM/persistence/reload changes;
- Task 13 normalized request and selector changes;
- a separately authorized migration;
- explicit v1 compatibility handling.

## §5 Option B — canonical hash mirror

Task 9 v2 canonical input snapshot contains:

```json
{
  "input_snapshot_schema_version": "task9a-input-snapshot-v2",
  "forecast_season_identity": {
    "season_id": 123,
    "season_code": "2026",
    "start_date": "2026-01-01",
    "end_date": "2026-04-30",
    "season_record_hash": "4ab22bae36fb53732b501957b90426e1cdc041e6923c85bf1052d8d576f22a3c"
  }
}
```

Task 9 v2 canonical output also contains required top-level:

```json
{
  "forecast_season_id": 123
}
```

These values bind season identity into `result_hash` and
`canonical_payload_hash` and support load-time consistency checks. They are not
the normal database selector surface because JSON alone has no FK, weaker type
enforcement, dialect-specific indexing, and a higher malformed-shape risk.

The authoritative equality chain is:

```text
HarvestStateRun.forecast_season_id
== canonical_output.forecast_season_id
== canonical_output.input_snapshot.forecast_season_identity.season_id
== ForecastSeasonIdentitySnapshot.season_id
```

`season_code` is required, non-empty hash-bound evidence in Task 9 v2. It MUST
NOT participate in selector equality, replace `forecast_season_id`, or be
parsed to derive a database ID.

## §6 Option C — historical lineage only

The historical evidence path is:

```text
HarvestStateRun.maturity_forecast_run_id
  -> MaturityForecastRun.plan_id
  -> FarmSeasonVarietyPlan.season_id
  -> Season.id
```

All Task 8 daily source refs and all season-scoped Task 9 authority inputs must
agree before a v1 row can be proposed for rematerialization. The lineage MAY:

- support audit reports;
- identify deterministic v2 rematerialization candidates;
- provide the proposed `forecast_season_id` to a new Task 9 v2 request after
  explicit validation.

It MUST NOT:

- populate a selector-eligible v1 authority;
- rewrite v1 canonical output or hashes;
- replace the dedicated v2 FK during normal selection;
- permit a join-time season fallback when the FK is missing.

Optional predecessor/supersedes lineage between v1 and v2 runs is a future
candidate only. It is not part of the authorized implementation scope.

## §7 Decision matrix

| Criterion | Option A: FK column | Option B: canonical mirror | Option C: lineage |
|---|---|---|---|
| Normal selector authority | Yes, unique authority | No | No |
| Hash-bound | Via required Option B mirror | Yes | No for v1 |
| FK/type integrity | Strong | Application validation | Indirect joins |
| Query/index portability | Strong | Weak/medium | Complex |
| Task 9 self-contained | Yes | Partial | No |
| Historical audit | Explicitly disclosed | v1 missing | Strong evidence source |
| Frozen role | Database authority | Hash/audit mirror | Audit/rematerialization only |

Final definition:

- Option A is the only normal selector authority.
- Option B is required for hash binding and load-time consistency.
- Option C is restricted to historical audit and v2 rematerialization proposal.

## §8 Season resolution policy

### §8.1 Resolver output

The Task 9 business identity is an immutable domain-owned value object:

```text
ForecastSeasonIdentitySnapshot
  season_id: positive int
  season_code: non-empty str
  start_date: date
  end_date: date
  season_record_hash: lowercase 64-character SHA-256 hex
```

Ownership is frozen to the TASK-009 harvest-state domain contract. The future
implementation belongs in `backend.app.harvest_state.schemas` or an equivalent
neutral master-data/domain module, never `backend.app.agent`. It contains no
TASK-013 resolver policy fields.

After successful normalization, the TASK-013 resolver returns an Agent-owned
wrapper:

```text
ResolvedForecastSeasonIdentity
  season_snapshot: ForecastSeasonIdentitySnapshot
  season_resolution_policy_version: non-empty str
  season_resolution_policy_config_hash: lowercase 64-character SHA-256 hex
```

This wrapper is owned by TASK-013 Agent normalization/resolver contract and
belongs in `backend.app.agent.schemas`. TASK-013 may depend on the TASK-009 or
neutral `ForecastSeasonIdentitySnapshot`; `backend.app.harvest_state` MUST NOT
import `backend.app.agent`. TASK-009 knows nothing about TASK-013 resolver
policy and MUST NOT import Agent schemas, enums, services, or adapters.

TASK-013 maps `season_snapshot.season_id` to
`effective_forecast_season_id` and `season_snapshot.season_code` to required
`effective_forecast_season_code`. It records the original
`requested_forecast_season` token separately. Before successful normalization,
including blocker-envelope construction, these effective fields may be absent;
a successful `NormalizedAgentRequest` MUST contain both. The resolver does not
return an overloaded `effective_forecast_season` authority.

### §8.2 Resolver policy identity

The v1 policy version is frozen as:

```text
season_resolution_policy_version = task13-season-resolution-policy-v1
```

`season_resolution_policy_config_hash` is the repository-standard canonical
JSON SHA-256 of exactly this payload:

```json
{
  "schema_version": "task13-season-resolution-policy-config-v1",
  "explicit_token_resolution": "exact_season_code",
  "integer_token_canonicalization": "base10_text",
  "string_token_normalization": "none",
  "empty_token_policy": "reject",
  "no_token_resolution": "inclusive_effective_as_of_date_range",
  "required_match_cardinality": 1,
  "date_range_start_operator": "less_than_or_equal",
  "date_range_end_operator": "greater_than_or_equal",
  "geographic_scope": "global",
  "availability_filter": "none",
  "season_id_derivation": "forbidden",
  "date_year_derivation": "forbidden"
}
```

Object keys are sorted by the existing canonical JSON rules before hashing.
Implementations MUST NOT add unfrozen fields. Database row counts, query order,
and current/latest state MUST NOT enter this hash. V1 defines no whole-table
`dim_season` calendar hash. The exact canonical payload hashes to:

```text
7452669a4cc8723010b2276dbab714d6c218401d44f4aa948768524400ffe708
```

`season_record_hash` identifies the selected row snapshot, not the resolver
rules. It is the canonical JSON SHA-256 of exactly:

```json
{
  "schema_version": "season-record-v1",
  "season_id": 123,
  "season_code": "2026",
  "start_date": "2026-01-01",
  "end_date": "2026-04-30"
}
```

`season_id` is a positive integer; `season_code` is required, non-empty, and
preserved without normalization; dates use ISO `YYYY-MM-DD`; and `end_date`
MUST be on or after `start_date`. The output is lowercase 64-character SHA-256
hex. The example hashes to:

```text
4ab22bae36fb53732b501957b90426e1cdc041e6923c85bf1052d8d576f22a3c
```

The policy hash identifies deterministic resolver rules. The record hash
identifies the exact Season row snapshot selected for this request. A single
ambiguous `season_calendar_config_hash` is not part of this contract.

### §8.3 Explicit token resolution

When `requested_forecast_season` is supplied:

1. An integer token such as `2026` is canonically represented as the text
   token `"2026"`; it is not treated as `Season.id=2026`.
2. A string token is compared as an exact `Season.code` after validating that
   it is non-empty. No case folding, date parsing, year extraction, or fuzzy
   matching is permitted.
3. Query `dim_season` for exact `Season.code == canonical_token`.
4. Exactly one row must match.
5. Return that row's `Season.id` and `Season.code`.

Therefore `requested_forecast_season=2026` resolves only a Season whose exact
code is `"2026"`. It does not resolve a code such as `"2025-2026"` unless the
caller explicitly supplies that code.

Outcomes:

| Condition | Existing blocker | Stable reason |
|---|---|---|
| No exact code match | `INPUT_INVALID_SEASON` | `SEASON_TOKEN_NOT_FOUND` |
| More than one exact match | `INPUT_INVALID_SEASON` | `SEASON_TOKEN_AMBIGUOUS` |
| Invalid/empty token | `INPUT_INVALID_SEASON` | `SEASON_TOKEN_INVALID` |
| Season query failure | `UPSTREAM_READ_FAILURE` | `SEASON_REGISTRY_READ_FAILED` |

The unique `Season.code` database constraint should make ambiguity impossible
in a valid store, but the resolver remains fail-closed if corrupt or joined
data produces multiple rows.

### §8.4 No-token formal date-range resolution

When the caller supplies no token, formal resolution by
`effective_as_of_date` is allowed only through this query:

```text
Season.start_date <= effective_as_of_date
AND Season.end_date >= effective_as_of_date
```

Exactly one row must match. This is a query of the authoritative Season
calendar, not `effective_as_of_date.year` inference.

| Condition | Existing blocker | Stable reason |
|---|---|---|
| No covering Season | `INPUT_INVALID_SEASON` | `SEASON_DATE_RANGE_NOT_FOUND` |
| Multiple covering Seasons | `INPUT_INVALID_SEASON` | `SEASON_DATE_RANGE_AMBIGUOUS` |
| Season query failure | `UPSTREAM_READ_FAILURE` | `SEASON_REGISTRY_READ_FAILED` |

Resolution failure terminates normalization. TASK-009 selection MUST NOT run.

### §8.5 Availability, validity, and scope

Current `dim_season` has `start_date` and `end_date`; it does not have
`available_at`, `valid_from`, or `valid_to`. The v2 resolver MUST NOT invent
those fields or reuse unrelated timestamps. If season availability/versioning
is later required, it needs a separate source-definition amendment and schema
authorization.

Current `Season` is global and has no farm, region, or country scope. The v2
resolver therefore applies no geographic filter. A future scoped season
calendar requires a separate contract and cannot be inferred from location.

## §9 Task 9 v2 persistence and hash contract

### §9.1 Request and output fields

The application boundary order is frozen as:

```text
requested_forecast_season
-> TASK-013 formal season resolver
-> load exactly one Season row
-> construct ForecastSeasonIdentitySnapshot
-> construct ResolvedForecastSeasonIdentity
-> TASK-013 stores resolver-policy provenance
-> construct Task9ARequest v2 using season_snapshot only
-> execute deterministic Task 9 model
-> construct canonical Task 9 v2 output
-> calculate Task 9 v2 result_hash
-> save_harvest_state_output()
-> reload and integrity validation
-> TASK-013 composes Agent authority/provenance envelope
```

Future `Task9ARequest` v2 requires only the domain-owned value object:

```text
forecast_season_identity: ForecastSeasonIdentitySnapshot
```

`season_id` is the database authority. `season_code`, dates, and record hash are
required hash-bound business snapshots. Task 9 execution validates that all
selected season-scoped authorities agree with the ID before numerical
execution. Its numerical algorithm MUST NOT access the database or derive
`season_id` from dates, years, or code.

TASK-013 constructs `ResolvedForecastSeasonIdentity`, stores its resolver-policy
provenance, and passes only `resolved.season_snapshot` to Task 9. Independent
Task 9 API, CLI, replay, and test callers must also provide a valid
`ForecastSeasonIdentitySnapshot`; they do not require an Agent runtime or
resolver object. Task 9 persistence MUST NOT accept or store
`season_resolution_policy_version` or
`season_resolution_policy_config_hash` without a future independent ownership
amendment.

Both completed and blocked Task 9 v2 outputs require:

```text
forecast_season_id: positive integer
input_snapshot.input_snapshot_schema_version = task9a-input-snapshot-v2
input_snapshot.forecast_season_identity = ForecastSeasonIdentitySnapshot
```

A season-resolution failure occurs before Task 9 and therefore creates no Task
9 v2 run. A later Task 9 business blocker may be persisted as blocked, but its
resolved request season remains mandatory.

### §9.2 Save contract

`save_harvest_state_output()` must:

1. validate v2 output/result-hash version coupling;
2. require a positive top-level `forecast_season_id` and a complete business
   snapshot whose `season_code` is non-empty;
3. require the authoritative equality chain:

   ```text
   HarvestStateRun.forecast_season_id
   == canonical_output.forecast_season_id
   == canonical_output.input_snapshot.forecast_season_identity.season_id
   == ForecastSeasonIdentitySnapshot.season_id
   ```

4. load the FK target and verify `Season.id`, `Season.code`,
   `Season.start_date`, and `Season.end_date` equal the business snapshot;
5. recompute and verify `season_record_hash` from the snapshot;
6. write the already hash-bound ID to `HarvestStateRun.forecast_season_id`;
7. reject ORM/canonical/domain-snapshot conflicts;
8. preserve idempotency using the v2 result hash.

Persistence MUST NOT first resolve season, fill `season_code`, change dates, or
alter `season_record_hash` after `result_hash` has been calculated. It neither
receives nor validates Agent-owned resolver-policy provenance.

### §9.3 Load contract

`load_harvest_state_output_by_id()` must:

- continue to read and validate v1 rows under v1 rules;
- for v2, require the expected output and result-hash versions;
- require a non-null valid ORM FK;
- validate ORM, top-level canonical, nested snapshot, and domain-snapshot ID
  equality;
- validate required `season_code`, dates, and record hash;
- validate canonical payload hash and result hash under v2 rules;
- fail closed on missing, malformed, dangling, or conflicting identity.

If the current `dim_season` row later differs from the historical canonical
snapshot, loading MUST fail closed with
`AUTHORITY_IDENTITY_MALFORMED` and stable reason
`PERSISTED_FORECAST_SEASON_REGISTRY_DRIFT`. This applies to any mismatch in
`Season.id`, `Season.code`, `Season.start_date`, `Season.end_date`, or the
recomputed `season_record_hash`.

Registry drift MUST NOT rewrite historical canonical output, recalculate or
overwrite historical result/canonical-payload hashes, replace the historical
snapshot with the current row, or be downgraded to a warning. Neither implicit
selection nor explicit override may use the row, and Task 10 MUST NOT build on
that authority. Disclosure-only or historical-snapshot-authoritative behavior
requires a future independent amendment.

### §9.4 Field-level hash surface

The v2 result-hash payload is the canonical Task 9 output excluding only its
`result_hash` field and including:

```text
result_hash_schema_version = task9a-result-hash-v2
output_schema_version = task9a-output-v2
forecast_season_id
input_snapshot.input_snapshot_schema_version
input_snapshot.forecast_season_identity.season_id
input_snapshot.forecast_season_identity.season_code
input_snapshot.forecast_season_identity.start_date
input_snapshot.forecast_season_identity.end_date
input_snapshot.forecast_season_identity.season_record_hash
all existing v1 result-hash fields
```

The canonical payload hash covers the complete stored v2 canonical output,
including the same season fields. The ORM column is a query surface and is not
separately appended to the hash; equality to the canonical mirror is mandatory
at save and load.

TASK-013 resolver policy version and config hash are intentionally absent from
both Task 9 hashes and canonical output. Therefore:

```text
same Task 9 business inputs
+ same ForecastSeasonIdentitySnapshot
+ different TASK-013 resolver-policy version or config hash
= same Task 9 result_hash

same Task 9 result
+ different TASK-013 resolver-policy provenance
= different TASK-013 canonical request/output hash
```

The season value is request scope, not algorithm configuration. It does not
become a direct Task 9 config-hash field. The config hash will nevertheless
change when `output_schema_version` changes because the existing config-hash
surface includes that version.

## §10 Task 9 v2 schema/version matrix

| Surface | Exact v2 value | Decision and field effect |
|---|---|---|
| Input snapshot | `task9a-input-snapshot-v2` | Upgrade; binds only the required `ForecastSeasonIdentitySnapshot` |
| `output_schema_version` | `task9a-output-v2` | Upgrade; required top-level `forecast_season_id` and domain-owned canonical season snapshot change output shape |
| `result_hash_schema_version` | `task9a-result-hash-v2` | Upgrade; season ID, code, dates, and record hash enter the Task 9 result-hash surface |
| `resolved_parameter_snapshot_schema_version` | `task9a-resolved-parameters-v1` | Unchanged; season is request scope, not a resolved parameter |
| `source_ref_schema_version` | `task9a-source-ref-v1` | Unchanged; existing source-reference meanings do not change |
| `stable_cohort_key_schema_version` | `task9a-cohort-key-v1` | Unchanged; cohort-key semantics do not change |

Version coupling rules:

- `task9a-output-v2` requires `task9a-result-hash-v2` and
  `task9a-input-snapshot-v2`.
- A v2 result-hash row cannot carry v1 output shape.
- A v1 row cannot become v2 through column backfill.
- Missing or empty `season_code`, incomplete dates, or invalid season hashes
  make a v2 output invalid.
- TASK-013 policy provenance is excluded from all Task 9 schema versions and
  hashes. Agent canonical-hash changes are owned by the TASK-013 contract.
- A resolver-policy upgrade does not automatically require a Task 9
  result-hash schema upgrade. Only a business season-snapshot shape change or
  Task 9 hash-semantics change requires a new Task 9 version.
- Selector eligibility requires v2 output version, v2 result-hash version,
  valid FK, matching canonical mirrors, valid hashes, completed status, and an
  exact request season-ID match.
- Resolved-parameter, source-ref, and stable-cohort-key versions remain v1 and
  are still disclosed and validated.

## §11 TASK-013 selector and blocker contract

Both default and explicit override paths compare:

```text
NormalizedAgentRequest.effective_forecast_season_id: int
==
HarvestStateRun.forecast_season_id: int
```

Eligibility evaluation order:

1. base scope/status/date/destination checks;
2. Task 9 output/result-hash schema version checks;
3. ORM season FK presence and validity;
4. canonical top-level and snapshot season mirror validation;
5. persisted ID versus requested effective ID equality;
6. existing variety and Task 8/Task 10 lineage checks;
7. deterministic conflict disclosure if multiple candidates remain.

| Condition | Blocker | Stable reason |
|---|---|---|
| No related Task 9 row | `TASK9_AUTHORITY_NOT_FOUND` | Existing behavior |
| v1 or null season binding | `AUTHORITY_SCOPE_MISMATCH` | `PERSISTED_FORECAST_SEASON_IDENTITY_UNAVAILABLE` |
| Unsupported Task 9 schema versions | `AUTHORITY_SCOPE_MISMATCH` | `TASK9_SEASON_IDENTITY_SCHEMA_UNSUPPORTED` |
| Malformed/non-positive/dangling FK | `AUTHORITY_IDENTITY_MALFORMED` | `PERSISTED_FORECAST_SEASON_IDENTITY_MALFORMED` |
| ORM/canonical mirror conflict | `AUTHORITY_IDENTITY_MALFORMED` | `PERSISTED_FORECAST_SEASON_IDENTITY_CONFLICT` |
| Current Season registry row differs from hash-bound v2 snapshot | `AUTHORITY_IDENTITY_MALFORMED` | `PERSISTED_FORECAST_SEASON_REGISTRY_DRIFT` |
| Valid persisted ID differs from request | `AUTHORITY_SCOPE_MISMATCH` | `FORECAST_SEASON_ID_MISMATCH` |
| Multiple fully eligible candidates | `AUTHORITY_CONFLICT` | Existing full candidate disclosure |
| Registry or authority read error | `UPSTREAM_READ_FAILURE` | Stable field-specific details |

An explicit `TASK9_HARVEST_STATE_RUN` override MUST NOT bypass any check. A Task
8 override must still equal the Task 8 identity frozen by the selected Task 9
run. No season mismatch, missing binding, or cross-run substitution is allowed.
Registry drift cannot be bypassed and the row cannot enter a Task 10 authority
chain.

At TASK-013 composition, the Agent additionally validates:

```text
ResolvedForecastSeasonIdentity.season_snapshot
== Task9ARequest.forecast_season_identity
== selected Task9Authority canonical season snapshot
```

Selector equality itself remains ID-only. `season_code`, dates, and record hash
are integrity fields, not additional selector keys.

## §12 Historical v1 eligibility

| Operation | Historical v1 row |
|---|---|
| Canonical load and audit | Allowed under v1 integrity rules |
| Ordinary implicit Task 9 selector | Ineligible |
| Explicit Task 9 authority override | Still ineligible |
| Date/year-based backfill | Forbidden |
| In-place canonical output/hash update | Forbidden |
| Lineage audit | Allowed |
| Rematerialization proposal generation | Allowed when proof is complete |
| Normal authority eligibility | Only through a newly executed v2 run |

A rematerialization proposal is provable only when:

1. persisted Task 8 forecast lineage exists;
2. forecast plan and Season exist;
3. all Task 8 daily source refs agree on one season ID;
4. all season-scoped Task 9 input authorities agree;
5. no canonical or mirrored lineage value conflicts.

Rematerialization MUST execute Task 9 v2 and create:

- a new `HarvestStateRun.id`;
- a new `result_hash` under `task9a-result-hash-v2`;
- a new `canonical_payload_hash`;
- a required `forecast_season_id` and canonical mirror.

No v1 row is upgraded in place. Optional predecessor/supersedes fields are a
future design candidate only and are not added by this amendment.

## §13 Migration design constraints

The migration revision identifier is deliberately not reserved here. It MUST
be chosen only after implementation authorization and inspection of the then
current `main` Alembic head.

Required future migration operations:

1. Add nullable `harvest_state_run.forecast_season_id` using the repository's
   PostgreSQL/SQLite-compatible integer type.
2. Add FK to `dim_season.id` with `ON DELETE RESTRICT`.
3. Preserve `NULL` for historical v1 rows.
4. Add `CHECK (forecast_season_id IS NULL OR forecast_season_id > 0)`.
5. Add a version-aware check equivalent to:

   ```text
   result_hash_schema_version != 'task9a-result-hash-v2'
   OR forecast_season_id IS NOT NULL
   ```

6. Couple v2 output and result-hash versions through application validation and,
   where portable, a database check.
7. Add the portable selector scope index defined in §4.
8. Perform no date/year/plan-derived eligibility backfill.
9. Modify no historical canonical output, `result_hash`, or
   `canonical_payload_hash`.

Both completed and blocked v2 writes require `forecast_season_id`. A request
that cannot resolve season does not create a Task 9 v2 run.

PostgreSQL migration requirements:

- apply FK/check/index against an isolated migrated database;
- verify existing v1 row counts and hashes before and after upgrade;
- prove v2 null/dangling FK rejection;
- run upgrade/downgrade round trip.

SQLite migration requirements:

- use Alembic batch-table recreation if required for FK/check alteration;
- preserve all v1 data and hashes exactly;
- enforce foreign keys in the test connection;
- verify parity with PostgreSQL eligibility behavior.

Downgrade requirements:

- preflight for any v2 row or non-null season identity;
- refuse operational downgrade when v2 data exists unless explicit destructive
  data-loss authorization is supplied;
- when safe, drop index, checks, FK, and column without rewriting v1 rows;
- document that dropping the column destroys v2 selector capability even
  though canonical v2 payloads still contain the mirror.

## §14 TASK-013 contract changes

`NormalizedAgentRequest` adds required:

```text
effective_forecast_season_id: positive integer
effective_forecast_season_code: non-empty string
```

Both are required after successful normalization. They may be absent only
before normalization succeeds or in the preceding blocker envelope. Code is
disclosure and hash-bound evidence; selector equality uses only the ID.

Provenance must disclose:

```text
requested_forecast_season
effective_forecast_season_id
effective_forecast_season_code
season_resolution_policy_version
season_resolution_policy_config_hash
season_record_hash
```

`effective_forecast_season_id` and code come from
`ResolvedForecastSeasonIdentity.season_snapshot`. `season_record_hash` belongs
to the business snapshot. Policy version/config hash belong exclusively to
TASK-013 resolver provenance. The Agent canonical request/output hash includes
all disclosed resolver provenance; Task 9 canonical output and result hash do
not include policy version/config hash.

Consequently, changing only resolver-policy provenance preserves Task 9
business identity and `result_hash` but changes the TASK-013 canonical hash.
Selector equality remains season-ID-only. Code, dates, and record hash support
Task 9 integrity validation and do not become selector equality fields.

`Task9Authority` adds `forecast_season_id`. The Agent canonical request and
output shapes therefore change, and so do canonical request/output hashes.
Byte-stability fixtures and the production-wiring Golden must be regenerated
from production wiring rather than manually edited.

The PostgreSQL orchestration acceptance test must use:

- a real Season row and formal resolver;
- real Task 9 v2 execution and public persistence/reload;
- the real v2 selector;
- exact Task 8 -> Task 9 -> Task 10 authority lineage;
- non-empty daily curve and peak output.

Tests MUST NOT inject `input_snapshot["forecast_season"]` or any other
test-only field to imitate production persistence.

## §15 TASK-009 / TASK-010 / TASK-013 implementation order

1. Review and merge this design amendment independently.
2. Implement the neutral/TASK-009-owned `ForecastSeasonIdentitySnapshot`.
3. Implement Task 9 v2 request/output/canonical/result-hash contract.
4. Implement `HarvestStateRun.forecast_season_id` ORM and the separately
   authorized migration.
5. Implement Task 9 v2 save/load/integrity/migration tests.
6. Implement the TASK-013-owned `ResolvedForecastSeasonIdentity` and formal
   resolver.
7. Implement TASK-013 normalized request, policy provenance, and Agent hash.
8. Implement TASK-013 v2 selector default/override eligibility.
9. Implement registry-drift fail-closed behavior.
10. Verify Task 10 signature/hash lineage.
11. Update PR #96 PostgreSQL production-wiring fixture.
12. Replace the stub Golden with the production-wiring Golden.
13. Obtain exact-head CI success.
14. Obtain separate Charles authorization for Ready and Merge.

Steps 2 through 5 require no Agent import or Agent implementation. They depend
only on the frozen Task 9 business-snapshot contract.

PR #96 MUST remain Draft until every predecessor above is complete and separately
reviewed. Green CI before those contracts exist does not close Slice B.

## §16 Future test matrix

These tests are required for future implementation but are not implemented in
this design round:

### Dependency ownership

- `backend.app.harvest_state` imports no `backend.app.agent` module;
- `ForecastSeasonIdentitySnapshot` constructs and validates without Agent
  runtime;
- independent Task 9 execution requires no TASK-013 resolver object;
- the Agent resolver constructs `ResolvedForecastSeasonIdentity` and passes
  only `season_snapshot` to Task 9.

### Season resolver

- requested integer token `2026` exactly resolves `Season.code == "2026"`;
- requested string code exactly resolves one Season;
- requested token with no match returns `SEASON_TOKEN_NOT_FOUND`;
- ambiguous exact match returns `SEASON_TOKEN_AMBIGUOUS`;
- invalid token returns `SEASON_TOKEN_INVALID`;
- no requested token resolves exactly one formal date-range Season;
- no covering date-range Season returns `SEASON_DATE_RANGE_NOT_FOUND`;
- overlapping date-range Seasons return `SEASON_DATE_RANGE_AMBIGUOUS`;
- season registry read failure returns `UPSTREAM_READ_FAILURE`;
- policy config hash matches the exact §8.2 Golden;
- selected season record hash matches the exact §8.2 Golden;
- identical Season snapshots produce identical record hashes;
- changing season code or either date changes the record hash;
- regression test proves no `as_of_date.year` derivation occurs.

### Task 9 v2 schema, persistence, and migration

- completed v2 output requires forecast season;
- blocked v2 output requires forecast season;
- complete `ForecastSeasonIdentitySnapshot` exists before Task 9 result-hash
  generation;
- persistence cannot supply or alter season code after hash generation;
- missing season code is rejected;
- empty season code is rejected;
- v2 ORM, canonical, and domain-snapshot identities match;
- ORM/top-level canonical mismatch fails closed;
- top-level/nested snapshot mismatch fails closed;
- v2 missing or dangling FK fails closed;
- v2 result hash is deterministic and season-sensitive;
- canonical payload and result hashes include ID, code, dates, and record hash;
- Task 9 v2 save/load PostgreSQL round trip;
- Task 9 v2 save/load SQLite round trip;
- PostgreSQL and SQLite migration round trips preserve v1 hashes;
- v2 version coupling rejects mixed v1/v2 surfaces;
- current registry-row drift never rewrites historical output or hashes.

### Hash boundary

- identical business snapshot with different policy version produces the same
  Task 9 result hash;
- identical business snapshot with different policy config hash produces the
  same Task 9 result hash;
- either policy provenance change produces a different TASK-013 canonical
  hash;
- changing season ID, code, start date, end date, or record hash changes the
  Task 9 result hash;
- Task 9 canonical output contains no resolver policy version/config hash;
- Agent provenance contains resolver policy version/config hash.

### Registry drift

- season-ID drift returns `AUTHORITY_IDENTITY_MALFORMED` with reason
  `PERSISTED_FORECAST_SEASON_REGISTRY_DRIFT`;
- code drift returns `AUTHORITY_IDENTITY_MALFORMED` with reason
  `PERSISTED_FORECAST_SEASON_REGISTRY_DRIFT`;
- start-date drift returns the same blocker/reason;
- end-date drift returns the same blocker/reason;
- record-hash mismatch returns the same blocker/reason;
- drift does not modify historical canonical output or hashes;
- implicit selector cannot select a drift row;
- explicit override cannot bypass drift;
- a drift row cannot enter the Task 10 authority chain.

### Historical v1 and rematerialization

- v1 canonical audit remains readable;
- v1 implicit selector is ineligible;
- v1 explicit override remains ineligible;
- v1 missing season returns the frozen unavailable reason;
- lineage audit identifies only fully consistent candidates;
- inconsistent Task 8/plan/input lineage produces no proposal;
- v2 rematerialization creates new run ID, result hash, and canonical payload
  hash without modifying v1.

### TASK-013 and TASK-010 integration

- matching v2 persisted season selects exactly;
- season code differences do not participate in selector equality;
- mismatched v2 season fails with `FORECAST_SEASON_ID_MISMATCH`;
- multiple same-season authorities return full `AUTHORITY_CONFLICT`;
- multiple different-season authorities filter by exact season ID;
- matching explicit override succeeds;
- mismatched explicit override fails;
- SQLite/PostgreSQL selector parity;
- Task 10 input signature and prediction hash change when Task 9 v2 run/hash
  changes;
- Task 10 preserves exact Task 9 run/hash lineage without duplicate season;
- repeated TASK-013 execution produces byte-identical canonical output;
- production Golden includes non-null Task 8/9/10 authorities,
  `effective_forecast_season_id`, non-empty daily curve, peak, provenance,
  blockers, and output hash;
- PostgreSQL orchestration uses real resolver, real Task 9 v2 persistence, and
  real selector with no test-only snapshot injection.

## §17 Explicit non-actions and authorization gates

This design document has been committed, its design branch has been pushed,
and independent Draft PR #97 has been created. The PR remains documentation
only. This fixup does not:

- modify Python, ORM, tests, fixtures, workflows, or PR #96;
- create an Alembic migration or reserve a migration number;
- implement a resolver or selector;
- inject `input_snapshot["forecast_season"]`;
- modify historical v1 output or hashes;
- mark Ready, merge, enable auto-merge, or modify PR #96;
- start Slice C/D/E or TASK-014+;
- claim Slice B completion.

Implementation, migration, PR #96 or PR #97 Ready, and Merge all require
separate explicit authorization.

```text
TASK013_PERSISTED_SEASON_IDENTITY_OWNERSHIP_FIXUP_COMPLETED
TASK9_BUSINESS_SEASON_SNAPSHOT_OWNERSHIP_FROZEN
TASK13_RESOLVER_PROVENANCE_OWNERSHIP_FROZEN
TASK9_AGENT_REVERSE_DEPENDENCY_FORBIDDEN
TASK9_RESULT_HASH_POLICY_DECOUPLING_FROZEN
REGISTRY_DRIFT_FAIL_CLOSED_FROZEN
DESIGN_DOCUMENT_COMMITTED_AND_PUSHED
AMENDMENT_DRAFT_PR_CREATED
IMPLEMENTATION_NOT_AUTHORIZED
MIGRATION_NOT_AUTHORIZED
PR96_KEEP_DRAFT
PR97_KEEP_DRAFT
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```
