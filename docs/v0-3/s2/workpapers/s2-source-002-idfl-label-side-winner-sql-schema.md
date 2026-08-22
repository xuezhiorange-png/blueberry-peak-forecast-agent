# V0.3-S2 SOURCE_002 IDFL label-side winner SQL schema and ledger grant

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_IDFL_LABEL_SIDE_WINNER_SQL_SCHEMA
ARTIFACT_VERSION=s2-source-002-idfl-label-side-winner-sql-schema-v1
LEDGER_POLICY_VERSION=s2-source-002-idfl-label-side-winner-sql-v1
TASK_ID=V03_S2_SOURCE_002_IDFL_LABEL_SIDE_WINNER_SQL_SCHEMA_R1
TASK_CLASS=DOCS_ONLY_SCHEMA_LEDGER_GRANT
AUTHORIZATION_SCOPE=S2_SOURCE_002_IDFL_LABEL_SIDE_WINNER_SQL_SCHEMA_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUTHORIZED_AT=2026-08-22T15:05:00Z
RECORDED_AT=2026-08-22T15:10:00Z
AUTHORIZATION_UTTERANCE=授权
AUTHORIZATION_CONTEXT=Coordinator recommended option 2 (new IDFL table; do not make existing cutoff columns nullable). User replied 授权.
BASE_MAIN_SHA=2101acf9350f7ca170cabadbd2dc18d65cf3c3d2
BASE_MAIN_REF=origin/main
E4_MERGED_PR=288
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-idfl-label-side-winner-sql-schema.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-source-002-idfl-label-side-winner-sql-schema.json
EVIDENCE_JSON_SHA256=307b4867d15e0f87c01fdf02c0ea56dc3b898276d13959e683e55de6a039995e
NO_STEP_IMPLIES_THE_NEXT=true
~~~

The user authorized this schema and ledger grant after E4 merged on `main`
(#288). This document records the frozen SQL design for persisting IDFL
label-side revision-winner decisions. It does **not** create a migration,
does not mutate production code, does not accept S2, and does not start Lane
D.

This PR is documentation only. A later implementation PR may follow this
design only after a separate user authorization to implement.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
ALLOWLIST_EXPANSION_IN_THIS_PR=false
LANE_C_IMPLEMENTATION_AUTHORIZED=false
LANE_D_START_AUTHORIZED=false
S2_ACCEPTANCE_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

## 1. What this grant authorizes

This grant authorizes a **future** implementation PR to add one new append-only
SQL table and its Lane C persist path. That future PR is not implied by this
document and requires a separate user utterance equivalent to “可以实施”.

~~~text
FUTURE_IMPLEMENTATION_AUTHORIZED_BY_THIS_GRANT=SCHEMA_AND_LEDGER_DESIGN_ONLY
FUTURE_MIGRATION_AUTHORIZED_BY_THIS_GRANT=false
FUTURE_ALLOWLIST_EXPANSION_AUTHORIZED_BY_THIS_GRANT=false
FUTURE_LANE_D_START_AUTHORIZED_BY_THIS_GRANT=false
~~~

The grant freezes:

1. table name `s2_idfl_label_side_winner_decision` (fixed; no alternate names);
2. column intent, nullability, and CHECK constraints described below;
3. rejection of all nullable-cutoff and fabrication workarounds listed in §2;
4. alignment with merged Lane C IDFL semantics on `main` @ `2101acf`.

## 2. Frozen design decisions (not options)

The following are binding. Implementers must not re-open them.

### 2.1 REJECTED

~~~text
REJECT_NULLABLE_FORECAST_CUTOFF_ON_S2_PIT_VISIBILITY_DECISION=true
REJECT_NULLABLE_FORECAST_CUTOFF_ON_S2_REVISION_WINNER_DECISION=true
REJECT_SENTINEL_OR_PLACEHOLDER_DATETIME_FOR_CUTOFF=true
REJECT_HARVEST_BUSINESS_DATE_AS_SOURCE_AVAILABLE_AT=true
REJECT_HARVEST_BUSINESS_DATE_AS_FORECAST_CUTOFF_AT=true
REJECT_INSERT_IDFL_ROWS_INTO_S2_PIT_VISIBILITY_DECISION=true
REJECT_INSERT_IDFL_ROWS_INTO_S2_REVISION_WINNER_DECISION=true
~~~

Rationale:

- `s2_pit_visibility_decision.forecast_cutoff_at` and
  `s2_revision_winner_decision.forecast_cutoff_at` are `NOT NULL` by design.
  Forecast PIT visibility and replay revision-winner identity require a real
  cutoff timestamp.
- IDFL label-side mode does not carry `ForecastCutoffContext`. Making cutoff
  nullable or fabricating sentinel datetimes would conflate the forecast PIT
  domain with the IDFL label domain.
- `HARVEST_BUSINESS_DATE` is a canonical-grain business date. It must not be
  written into lifecycle timestamps (`source_available_at`) or into a forecast
  cutoff column.
- `s2_revision_winner_decision` identity includes `forecast_cutoff_at`. Inserting
  IDFL rows there would violate that table’s contract even if cutoff were
  nullable.

### 2.2 ACCEPTED

~~~text
ACCEPT_NEW_TABLE_S2_IDFL_LABEL_SIDE_WINNER_DECISION=true
NEW_TABLE_MUST_NOT_HAVE_FORECAST_CUTOFF_AT_COLUMN=true
NEW_ALEMBIC_DOWN_REVISION=d4e8f1a2b3c5
NEW_ALEMBIC_MUST_BECOME_UNIQUE_HEAD=true
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
IMPLEMENTATION_ORDER=TESTS_FIRST_THEN_MIGRATION
~~~

The new migration must chain linearly from the current unique head
`d4e8f1a2b3c5`. It becomes the sole head. No parallel heads.

## 3. Lane C semantic alignment (merged #288)

The new table must persist decisions that match the merged Lane C code on
`main` @ `2101acf`. Do not invent alternate IDFL semantics.

~~~text
REVISION_WINNER_MODE=IDFL_LABEL_SIDE
IDFL_REVISION_WINNER_REQUIRED=false
WINNER_MANIFEST_REQUIRED=false
BLOCKED=false
NO_WINNER_REASON=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE=false
FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL=false
LIFECYCLE_TIMESTAMPS_EXPLICIT_NULL_ALLOWED=true
FORECAST_CUTOFF_CONTEXT_CARRIED=false
CANDIDATE_SHAPE=SINGLETON_PER_SOURCE_ROW
REVISION_WINNER_ALGORITHM=NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE
~~~

Constants and version strings must copy the merged defaults from
`backend/app/s2_materialized_dataset/lane_c/schemas.py` and
`backend/app/s2_materialized_dataset/lane_c/hashes.py`. Do not introduce new
version strings in the implementation PR unless a separate governance change
authorizes them.

| Field / constant | Frozen value on `main` |
|---|---|
| `RevisionWinnerMode` | `IDFL_LABEL_SIDE` |
| `revision_winner_required` | `false` |
| `winner_manifest_required` | `false` |
| `blocked` | `false` |
| `no_winner_reason` | `NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE` |
| `IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED` | `false` |
| `SOURCE_AVAILABLE_AT_REQUIRED_FOR_IDFL_LABEL_SIDE` | `false` |
| `FORECAST_INPUT_VISIBILITY_POLICY_REUSED_FOR_ACTUAL_LABEL` | `false` |
| `visibility_policy_version` | `v0-3-s2-idfl-label-side-visibility-v1` |
| `visibility_schema_version` | `v0-3-s2-idfl-label-side-visibility-schema-v1` |
| `forecast_cutoff_identity_version` | `v0-3-s2-idfl-forecast-cutoff-not-applicable-v1` |
| `revision_winner_policy_version` | `v0-3-s2-idfl-revision-winner-v1` |
| `revision_schema_version` | `v0-3-s2-idfl-revision-schema-v1` |
| `visibility_boundary` | `NOT_POINT_IN_TIME_REPLAYABLE_FOR_IDFL_LABEL_SIDE; SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED; SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED; FORECAST_INPUT_VISIBILITY_DOMAIN_SEPARATE` |
| `IDFL_REVISION_WINNER_HASH_POLICY_VERSION` | `v0-3-s2-idfl-revision-winner-hash-v1` |

Lifecycle timestamps for IDFL decisions are explicitly all `NULL`
(`idfl_null_timestamps()`). That is not missing data to backfill from
`HARVEST_BUSINESS_DATE`.

Identity and hash inputs for IDFL decisions must **not** include
`forecast_cutoff_at`. The forecast PIT domain and IDFL label domain remain
separate.

Each SOURCE_002 source row is a singleton candidate:
`ordered_candidate_identities` is a one-element tuple containing that row’s
`source_row_identity_hash`.

## 4. Proposed table: `s2_idfl_label_side_winner_decision`

Table purpose: append-only SQL ledger of IDFL label-side revision-winner
dispositions, one row per resolved source-row identity. This is **not** a PIT
visibility table and **not** a replay revision-winner table.

### 4.1 Forbidden columns

The following must not appear on this table:

~~~text
FORBIDDEN_COLUMN_FORECAST_CUTOFF_AT=true
FORBIDDEN_COLUMN_ELIGIBLE=true
FORBIDDEN_COLUMN_BLOCK_REASON_PIT_ENUM=true
~~~

`forecast_cutoff_identity_version` is permitted. It is a version string
marking cutoff as not applicable for IDFL. It is not a cutoff timestamp.

### 4.2 Column intent and nullability

| Column | Type intent | Null | Notes |
|---|---|---|---|
| `id` | bigint autoincrement PK | NOT NULL | Surrogate key only |
| `source_row_identity_hash` | text (sha256) | NOT NULL | Lane A/C identity |
| `source_system` | text | NOT NULL | From `SourceRowIdentity` |
| `external_logical_record_id` | text | NOT NULL | From `SourceRowIdentity` |
| `external_revision_id` | text | NOT NULL | From `SourceRowIdentity` |
| `revision_number` | integer | NOT NULL | `>= 1` |
| `raw_source_artifact_identity_hash` | text (sha256) | NOT NULL | From `SourceRowIdentity` |
| `raw_import_batch_identity_hash` | text (sha256) | NOT NULL | From `SourceRowIdentity` |
| `source_recorded_at` | timestamptz | NULL | Explicit NULL for IDFL |
| `source_available_at` | timestamptz | NULL | Explicit NULL for IDFL |
| `source_revised_at` | timestamptz | NULL | Explicit NULL for IDFL |
| `source_finalized_at` | timestamptz | NULL | Explicit NULL for IDFL |
| `source_cancelled_at` | timestamptz | NULL | Explicit NULL for IDFL |
| `visibility_policy_version` | text | NOT NULL | `IdflLabelSideContext` |
| `visibility_schema_version` | text | NOT NULL | `IdflLabelSideContext` |
| `forecast_cutoff_identity_version` | text | NOT NULL | not-applicable version string |
| `revision_winner_policy_version` | text | NOT NULL | `IdflLabelSideContext` |
| `revision_schema_version` | text | NOT NULL | `IdflLabelSideContext` |
| `visibility_boundary` | text | NOT NULL | frozen constant string |
| `mode` | text | NOT NULL | CHECK `= IDFL_LABEL_SIDE` only |
| `revision_winner_required` | boolean | NOT NULL | always `false` for IDFL |
| `winner_manifest_required` | boolean | NOT NULL | always `false` for IDFL |
| `winner_source_row_identity_hash` | text (sha256) | NULL | always NULL on current semantics |
| `winner_source_system` | text | NULL | winner identity bundle |
| `winner_external_logical_record_id` | text | NULL | winner identity bundle |
| `winner_external_revision_id` | text | NULL | winner identity bundle |
| `winner_revision_number` | integer | NULL | winner identity bundle |
| `winner_raw_source_artifact_identity_hash` | text (sha256) | NULL | winner identity bundle |
| `winner_raw_import_batch_identity_hash` | text (sha256) | NULL | winner identity bundle |
| `blocked` | boolean | NOT NULL | always `false` on current semantics |
| `no_winner_reason` | text | NOT NULL | CHECK enum; `NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE` |
| `ordered_candidate_identities_json` | text (JSON array) | NOT NULL | singleton hash list |
| `content_sha256` | text (sha256) | NOT NULL | UNIQUE; `compute_idfl_revision_winner_content_hash` |
| `created_at` | timestamptz | NOT NULL | server default `now()` |

Winner identity columns remain nullable with the same all-or-nothing CHECK
pattern used on `s2_revision_winner_decision`: either all winner fields are
NULL or all are present with valid sha256 and `winner_revision_number >= 1`.
For current IDFL semantics the all-NULL branch is the only legal branch.

### 4.3 CHECK and uniqueness constraints

~~~text
UNIQUE_CONTENT_SHA256=uq_s2_idfl_label_side_winner_decision_content
CHECK_SOURCE_ROW_IDENTITY_HASH=64_LOWERCASE_HEX
CHECK_RAW_SOURCE_ARTIFACT_HASH=64_LOWERCASE_HEX
CHECK_RAW_IMPORT_BATCH_HASH=64_LOWERCASE_HEX
CHECK_CONTENT_SHA256=64_LOWERCASE_HEX
CHECK_REVISION_NUMBER_GTE_1=true
CHECK_MODE_ENUM=IDFL_LABEL_SIDE_ONLY
CHECK_NO_WINNER_REASON_ENUM=REVISION_WINNER_BLOCK_REASON_VALUES
CHECK_WINNER_IDENTITY_ALL_OR_NOTHING=true
CHECK_NO_FORECAST_CUTOFF_COLUMN=true
APPEND_ONLY_IMMUTABILITY_TRIGGER_REQUIRED=true
~~~

`no_winner_reason` CHECK uses the same `RevisionWinnerBlockReason` value set
as `s2_revision_winner_decision`, even though IDFL rows always store
`NOT_APPLICABLE_FOR_IDFL_LABEL_SIDE`.

`content_sha256` must match `compute_idfl_revision_winner_content_hash` on
the merged code path. Do not reuse `compute_revision_winner_content_hash`
(which requires `forecast_cutoff_at` in its payload).

## 5. Ledger and counting semantics

~~~text
LEDGER_POLICY_VERSION=s2-source-002-idfl-label-side-winner-sql-v1
WINNER_ROWS_RESOLVED_COUNTS_IN_MEMORY_AND_SQL=true
WINNER_ROWS_SQL_PERSISTED_COUNTS_SQL_ROWS_ONLY=true
IN_MEMORY_LANE_C_PERSISTENCE_STORE_DOES_NOT_COUNT=true
PIT_ROWS_PERSISTED_MUST_REMAIN_0=true
~~~

- `winner_rows_resolved`: number of IDFL decisions computed (one per identity
  in Lane B `cleaned version.source_row_identity_hashes`; observed length
  `233171`, including July Option A lineage rows; not the in-cohort count
  `233169`).
- `winner_rows_sql_persisted`: `COUNT(*)` from `s2_idfl_label_side_winner_decision`
  only. In-memory `LaneCPersistenceStore` rows do not count.
- `pit_rows_persisted`: must remain `0` for SOURCE_002 IDFL E4/E4b. IDFL does
  not persist PIT visibility rows.

## 6. Observed E4 facts on merged `main` (#288 @ `2101acf`)

These are coordinator-observed facts from the merged E4 implementation. They
are not tonnage and must not be extrapolated.

~~~text
E4_MERGED_PR=288
E4_MERGED_SHA=2101acf9350f7ca170cabadbd2dc18d65cf3c3d2
E4_STATUS=RESOLVED_NOT_SQL_PERSISTED
DECLARED_SOURCE_ROW_COUNT=233171
E2_EXACT_REPLAY=233171
JULY_OPTION_A_EXCLUDED_SOURCE_ROW_COUNT=2
SOURCE_ROWS_IN_SCOPE=233169
E4_WINNER_ROWS_RESOLVED=233171
E4_ITERATES=Lane B cleaned version.source_row_identity_hashes (length 233171, includes July 2 lineage rows)
IN_COHORT_NE_RESOLVED=true
E4B_TARGET_WINNER_ROWS_SQL_PERSISTED=233171
WINNER_ROWS_SQL_PERSISTED=0
E3_UNIQUE_CANONICAL_GRAINS=33894
E3_KG_EQUAL=true
E4_BLOCKED_REASON=PIT_CUTOFF_NOT_APPLICABLE_FOR_IDFL_NO_FABRICATION
PIT_ROWS_PERSISTED=0
PIT_STATUS=NOT_APPLICABLE_NOT_PERSISTED
~~~

E4 resolves IDFL winner decisions in memory but cannot SQL-persist them
because `s2_revision_winner_decision.forecast_cutoff_at` is `NOT NULL` and
IDFL decisions do not carry cutoff context. That is the expected blocked
state until the new table exists.

Frozen counting semantics:

- `DECLARED_SOURCE_ROW_COUNT=233171` and `E2_EXACT_REPLAY=233171` bind the
  full declared source object.
- `JULY_OPTION_A_EXCLUDED_SOURCE_ROW_COUNT=2` and
  `SOURCE_ROWS_IN_SCOPE=233169` (`233171 - 2`) are the in-cohort source-row
  count. Do not call `233171` “产季内”.
- `E4_WINNER_ROWS_RESOLVED=233171` because E4 iterates Lane B
  `cleaned version.source_row_identity_hashes` (length `233171`, including
  the July 2 lineage rows). `IN_COHORT_NE_RESOLVED=true`: resolved winner
  count is not the in-cohort count.
- July Option A rows remain `BUSINESS_EXCLUSION` in Lane B. E4b must not
  shrink SQL persist to `233169` only because of July exclusion. Target
  `E4B_TARGET_WINNER_ROWS_SQL_PERSISTED=233171`, aligned with observed E4
  resolved count.
- Each iterated identity yields exactly one singleton IDFL decision.
- `E3_UNIQUE_CANONICAL_GRAINS=33894` is the distinct canonical-grain count
  after E3 collapse. It is a grain count, not Lane C winner row count. Lane C
  IDFL resolution is per source-row identity, not per canonical grain.

## 7. Future implementation sequence (not authorized here)

### 7.1 E4b — Lane C SQL persist (future PR)

~~~text
E4B_AUTHORIZED_BY_THIS_GRANT=false
E4B_REQUIRES_SEPARATE_USER_IMPLEMENTATION_AUTHORIZATION=true
~~~

When separately authorized, E4b may:

1. add tests first, then Alembic migration with `down_revision=d4e8f1a2b3c5`;
2. add ORM model and persist function on Lane C allowlisted paths only;
3. extend `controlled_persist_source_002_idfl_from_environment` to write
   `s2_idfl_label_side_winner_decision` instead of attempting
   `s2_revision_winner_decision`;
4. target `E4B_TARGET_WINNER_ROWS_SQL_PERSISTED=233171` (aligned with
   observed E4 resolved count; not `233169`) with `pit_rows_persisted=0`.

Allowlist expansion for a new migration file path or new production module
is **not** authorized by this document. A future implementation PR may need a
separate allowlist grant. This document only previews that the new Alembic
file will be a new path off head `d4e8f1a2b3c5`. It does not amend the
frozen contract allowlist.

PEP 420 remains in force. Do not add forbidden production inits:

~~~text
FORBIDDEN_NAMESPACE_INIT_1=backend/app/s2_materialized_dataset/__init__.py
FORBIDDEN_NAMESPACE_INIT_2=backend/app/s2_materialized_dataset/shared/__init__.py
~~~

### 7.2 E5 — Lane D materialization (future PR)

~~~text
E5_AUTHORIZED_BY_THIS_GRANT=false
E5_REQUIRES_E4B_SQL_PERSIST_CONFIRMED=true
~~~

Lane D may be considered only after E4b SQL persist is coordinator-confirmed.
E5 must consume persisted SQL outputs from Lane A, Lane B, Lane C replay
tables, **and** the new IDFL table. Fake ports and in-memory stores are not
acceptable for SOURCE_002 materialization.

### 7.3 S2 acceptance

~~~text
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
~~~

This schema grant does not score contract §11 and does not mutate
`docs/v0-3/development-plan.md` gate rows. No §11 item is PASS because of
this document.

## 8. What this grant does not do

~~~text
DOES_NOT_CREATE_MIGRATION=true
DOES_NOT_MUTATE_S2_PIT_VISIBILITY_DECISION=true
DOES_NOT_MUTATE_S2_REVISION_WINNER_DECISION=true
DOES_NOT_COMMIT_SOURCE_BYTES_OR_LOCATORS=true
DOES_NOT_START_LANE_D=true
DOES_NOT_AUTHORIZE_READY_OR_MERGE_OF_THIS_PR=true
~~~

Contract `docs/v0-3/s2/s2-materialized-dataset-contract.md` remains frozen at
`CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099`. This PR
does not edit it.

This document does not authorize Ready or Merge of this PR unless separately
coordinated and explicitly authorized by the user.
