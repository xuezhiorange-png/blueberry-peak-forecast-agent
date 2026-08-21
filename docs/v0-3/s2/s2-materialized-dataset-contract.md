# V0.3-S2 Materialized Dataset Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S2_MATERIALIZED_DATASET_CONTRACT
CONTRACT_VERSION=v0-3-s2-materialized-dataset-contract-v1
TASK_ID=V03_S2_MATERIALIZED_DATASET_CONTRACT_FREEZE_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_RECORD_ID=5364250100
SOURCE_PHASE_AUTHORIZATION_RECORD_ID=5364219190
AUTHORIZATION_SCOPE=S2_P0_CONTRACT_FREEZE_ONLY
SOURCE_PHASE_V0_3_S2_AUTHORIZED=true
V0_3_S2_PHASE_ENTRY_INHERITED=true
BASE_MAIN_SHA=0a13da0738bb8311d200eaae67404e5d7cd99e70
BASE_MAIN_TREE_SHA=b64c2f6375c2a7f2d5b1b6e16320ec746d0bb630
P0_IMPLEMENTATION_PERFORMED=true
CONTRACT_ONLY=true
~~~

This document freezes the shared V0.3-S2 materialized-dataset contract before
any implementation lane begins. It is a governance contract, not an
implementation, migration, data-access grant, or acceptance result.

This task creates only this document. It does not implement ingestion,
cleaning, point-in-time reconstruction, revision selection, materialization,
partition building, metrics, backtests, model training, or S3. It does not
change any S1 authority artifact.

The S2 phase authorization permits separate implementation lanes to prepare
Draft PRs. It does not authorize any lane implementation in this task, and it
does not authorize Ready, Merge, S2 acceptance, or S3.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
DEPENDENCY_MUTATION_AUTHORIZED=false
WORKFLOW_MUTATION_AUTHORIZED=false
S1_AUTHORITY_MUTATION_AUTHORIZED=false

SOURCE_002_READ_AUTHORIZED=false
SOURCE_002_RAW_READ_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=false
TEST_PARTITION_ACCESS_AUTHORIZED=false
EXTERNAL_HOLDOUT_ACCESS_AUTHORIZED=false
METRIC_EXECUTION_AUTHORIZED=false
BACKTEST_AUTHORIZED=false
MODEL_TRAINING_AUTHORIZED=false
MODEL_OR_PARAMETER_CHANGE_AUTHORIZED=false

A_IMPLEMENTATION_AUTHORIZED=false
B_IMPLEMENTATION_AUTHORIZED=false
C_IMPLEMENTATION_AUTHORIZED=false
D_IMPLEMENTATION_AUTHORIZED=false
INDEPENDENT_REVIEW_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
NEXT_SLICE_STARTED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

## 1. Inherited S1 authority

S2 consumes the following accepted S1 authority. These values are inherited
references; this contract does not redefine, supersede, or reopen them.

~~~text
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
SOURCE_COHORT_MANIFEST_SHA256=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca

TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
ACTUAL_LABEL=actual_harvest_quantity_kg
FORECAST_TARGET=model_harvested_marketable_quantity_kg
Q2C_OUTCOME=PROVEN_EXACT
TARGET_TRANSFORMATION=NONE

CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
TIMEZONE=Asia/Shanghai
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false

SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
PARTITION_DATE_FIELD=HARVEST_BUSINESS_DATE

TRAIN=2025-08-05..2026-01-30
TRAIN_PURPOSE=CANDIDATE_FITTING_ONLY

VALIDATION=2026-01-31..2026-03-09
VALIDATION_PURPOSE=CANDIDATE_SELECTION_AND_VALIDATION_ONLY

TEST=2026-03-10..2026-04-16
TEST_PURPOSE=SEALED_FINAL_EVALUATION_ONLY

EXTERNAL_HOLDOUT_FEASIBILITY=REVIEWED_NOT_FEASIBLE
EXTERNAL_HOLDOUT_REQUIRED=false
EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
~~~

The source cohort manifest, target decision, Q2C outcome, canonical grain,
recorded-label boundary, timezone, missing-day semantics, and split policy
remain owned by S1. S2 must bind their exact identity and policy versions into
every materialized manifest. A lane must fail closed if any inherited identity
cannot be resolved or if a proposed implementation attempts to redraw a
partition, replace the target, invent plot support, or reinterpret unknown as
zero.

S1 freezes source-cohort authority and policy references. S2 owns the
versioned cleaned and materialized rowsets only after the relevant lane
contracts have been independently implemented and accepted. No S2 field
changes an S1 canonical gate.

## 2. Scope, invariants, and non-goals

The following are normative invariants for every future S2 implementation:

~~~text
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
MANUAL_CORRECTION_AUDITED=true
SILENT_VALUE_REPLACEMENT=false
SOURCE_ROW_LINEAGE_REQUIRED=true
POINT_IN_TIME_VISIBILITY_REQUIRED=true

RAW_ROW_OVERWRITE_ALLOWED=false
CLEANING_MUTATES_RAW_SOURCE=false

MATERIALIZATION_DETERMINISTIC=true
MATERIALIZATION_REBUILD_REQUIRES_HASH_PARITY=true

SOURCE_LINEAGE_LOSS_ALLOWED=false
UNKNOWN_TO_ZERO_COERCION_ALLOWED=false
LATEST_ROW_FALLBACK_ALLOWED=false
~~~

Raw source objects and source rows are append-only references. A correction,
exclusion, mapping decision, or visibility decision produces a versioned
downstream record and audit trail; it never overwrites raw source bytes or
silently replaces a value. A missing day is an unknown observation and is not
a numeric zero. A latest/current row may not be substituted for a row selected
by the exact point-in-time authority.

This contract does not grant access to Source002, TEST, external holdout data,
or any business dataset. It freezes the information needed to design a
replayable implementation without reading those data.

## 3. Canonical serialization and hash policy

All new S2 semantic identities use the repository's deterministic canonical
JSON family rather than ad-hoc string concatenation. The implementation must
reuse the existing behavior represented by
backend/app/rolling_backtest/canonical.py and its SHA-256 helper, with the
following S2 profile frozen here:

~~~text
S2_CANONICAL_SERIALIZATION_PROFILE=v0-3-s2-materialized-identity-canonical-v1
ENCODING=UTF-8
JSON_OBJECT_KEYS=LEXICOGRAPHICALLY_SORTED
JSON_SEPARATORS=,:
JSON_ASCII_POLICY=REPOSITORY_CANONICAL_JSON_POLICY
JSON_LIST_ORDER=EXPLICIT_AND_DETERMINISTIC
NATIVE_FLOATS=FORBIDDEN_IN_BUSINESS_PAYLOADS
DECIMAL_ENCODING=CANONICAL_DECIMAL_STRING
DATE_ENCODING=ISO_8601_DATE
DATETIME_ENCODING=TIMEZONE_AWARE_UTC_WITH_Z_SUFFIX
SETS=FORBIDDEN
HASH_ALGORITHM=SHA-256
HASH_OUTPUT=LOWERCASE_64_HEX
SELF_REFERENTIAL_HASH_FIELDS=EXCLUDED_FROM_THEIR_OWN_SCOPE
~~~

The canonical payload is an object with string keys. Dictionary keys are sorted
before serialization. Lists are sorted by the identity's declared ordering
key, never by database insertion order. Decimal values use the repository's
canonical decimal representation. Timezone-aware timestamps are normalized to
UTC and serialized with a Z suffix. A naive timestamp, native float business
value, unsupported type, non-finite number, or unordered collection is a
validation error.

The hash scope must be written beside every persisted hash. A replay computes
the same canonical payload from the stored versioned inputs, serializes it
with this profile, hashes its UTF-8 bytes, and compares the lowercase
64-character result. Any mismatch, duplicate identity with different payload,
ambiguous ordering, missing parent lineage, or missing policy version is a
hard failure. No identity hash includes itself.

The three hash classes are distinct:

- SOURCE_ARTIFACT_SHA256 is the digest of the immutable source artifact bytes
  or its governed source-object representation. It identifies source custody;
  it is not a cleaned-rowset or materialized-partition digest.
- CONTENT_SHA256 is the digest of canonical ordered content bytes for a
  dataset, row, partition, or content-bearing artifact. It identifies content;
  it is not the manifest identity.
- MANIFEST_SHA256 is the digest of the canonical manifest control payload,
  excluding the manifest_sha256 field itself and excluding volatile build
  timestamps. It identifies the declared provenance/control record; it is not a
  content digest.

No implementation may use a Git blob SHA, a database surrogate ID, a path,
wall-clock build time, host, process, transaction, or insertion order as a
replacement for one of these semantic hashes.

## 4. Required semantic identities

Every identity below is a separate contract. The owner is the sole authority
for constructing its identity payload. The stable inputs, version fields, and
lineage fields are all required; omitted or ambiguous inputs fail closed.
Each hash is calculated from its stated canonical payload, never from a payload
that includes the hash field itself.

### 4.1 RAW_SOURCE_ARTIFACT_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_A
STABLE_IDENTITY_INPUTS=source_system,source_dataset,source_version,source_snapshot_reference,source_object_identity,source_artifact_sequence
VERSION_FIELDS=source_version,schema_version,mapping_policy_version,source_artifact_identity_version
LINEAGE_FIELDS=source_owner_attestation,cohort_manifest_reference,custody_record_reference,storage_locator_hash
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE
SHA256_SCOPE=SOURCE_ARTIFACT_SHA256 over immutable artifact bytes or governed object digest plus identity metadata
REPLAY=reload metadata and immutable artifact reference; recompute exact source artifact digest
CONFLICT_BEHAVIOR=duplicate identity with different bytes or metadata is a source-integrity conflict
FAIL_CLOSED=reject replacement, correction, materialization, and downstream lineage
~~~

The source snapshot reference is an opaque governed identity, not a private
plaintext path. Artifact bytes may not be updated in place.

### 4.2 RAW_IMPORT_BATCH_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_A
STABLE_IDENTITY_INPUTS=raw_source_artifact_identity,external_batch_id,source_system,source_dataset,raw_payload_hash
VERSION_FIELDS=import_policy_version,schema_version,mapping_policy_version,validation_policy_version
LINEAGE_FIELDS=raw_source_artifact_identity,source_cohort_id,source_row_identity_set,import_request_identity
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE with records sorted by declared source-row key
SHA256_SCOPE=CONTENT_SHA256 over batch business payload and ordered source-row content hashes
REPLAY=rebuild batch payload from immutable source reference and ordered imported rows
CONFLICT_BEHAVIOR=same external batch identity with different payload or policy versions is an idempotency conflict
FAIL_CLOSED=do not insert a second batch and do not overwrite the first batch
~~~

Transport timestamps and host/process metadata are provenance, not stable
batch identity inputs.

### 4.3 SOURCE_ROW_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_A
STABLE_IDENTITY_INPUTS=raw_source_artifact_identity,external_logical_record_id,external_revision_id,revision_number,source_system
VERSION_FIELDS=source_row_identity_version,schema_version,source_version
LINEAGE_FIELDS=raw_import_batch_identity,source_sheet_name,source_row_number,source_column_mapping_snapshot
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE
SHA256_SCOPE=CONTENT_SHA256 over stable source-row identity payload; source artifact bytes remain SOURCE_ARTIFACT_SHA256
REPLAY=reconstruct from immutable batch and the source's declared external identifiers
CONFLICT_BEHAVIOR=same logical identity with different content or revision ordering is a revision conflict
FAIL_CLOSED=retain both immutable candidates, block winner selection, and require Lane C resolution
~~~

A sheet row number is lineage evidence and is never the sole identity. If the
source cannot provide a stable external logical identity, ingestion cannot
silently synthesize one from current row position.

### 4.4 CLEANED_DATASET_VERSION_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_B
STABLE_IDENTITY_INPUTS=source_cohort_id,ordered_raw_import_batch_identities,cleaning_policy_version,quality_policy_version,correction_policy_version,exclusion_policy_version,mapping_registry_hash
VERSION_FIELDS=cleaning_policy_version,quality_policy_version,correction_policy_version,exclusion_policy_version,cleaned_schema_version
LINEAGE_FIELDS=raw_source_artifact_identities,raw_import_batch_identities,source_row_identity_set,quality_report_identity,ledger_identity_set
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE with source rows and policies sorted explicitly
SHA256_SCOPE=CONTENT_SHA256 over cleaned dataset version control payload and ordered cleaned-row content hashes
REPLAY=rebuild from the exact raw lineage, policies, findings, ledgers, and mapping snapshot
CONFLICT_BEHAVIOR=same dataset version identity with different source/policy/content hashes is a version conflict
FAIL_CLOSED=do not expose the version to PIT or materialization
~~~

A cleaned version is immutable. A new policy or ledger decision creates a new
version identity; it does not mutate a prior version.

### 4.5 CLEANED_ROW_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_B
STABLE_IDENTITY_INPUTS=cleaned_dataset_version_identity,source_row_identity,canonical_grain_key,cleaning_projection_version
VERSION_FIELDS=cleaned_row_schema_version,cleaning_policy_version,correction_policy_version,exclusion_policy_version
LINEAGE_FIELDS=source_row_identity,quality_finding_identity_set,correction_ledger_identity_set,exclusion_ledger_identity_set
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE
SHA256_SCOPE=CONTENT_SHA256 over the cleaned row payload excluding volatile audit timestamps
REPLAY=apply the versioned cleaning/correction/exclusion decisions to the source row
CONFLICT_BEHAVIOR=two cleaned rows for one version and grain key or differing lineage is a duplicate/conflict
FAIL_CLOSED=reject dataset version or mark the row unavailable; never select by last-write order
~~~

A cleaned row preserves the source row reference even when a field is corrected
or a row is excluded.

### 4.6 QUALITY_FINDING_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_B
STABLE_IDENTITY_INPUTS=cleaned_dataset_version_identity,source_row_identity,quality_rule_id,observed_field,finding_code
VERSION_FIELDS=quality_policy_version,quality_rule_version,quality_schema_version
LINEAGE_FIELDS=source_row_identity,cleaned_row_identity,rule_definition_hash,validation_run_identity
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE
SHA256_SCOPE=CONTENT_SHA256 over rule, row, field, finding code, normalized observed value identity, and severity
REPLAY=re-run the versioned rule against the same versioned input without reading ungoverned data
CONFLICT_BEHAVIOR=the same finding identity with changed code, severity, or rule hash is a quality conflict
FAIL_CLOSED=block the affected row or dataset until an explicit versioned disposition exists
~~~

Quality findings are evidence, not silent transformations.

### 4.7 CORRECTION_LEDGER_ENTRY_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_B
STABLE_IDENTITY_INPUTS=correction_event_id,cleaned_dataset_version_identity,source_row_identity,field_name,correction_policy_version
VERSION_FIELDS=correction_policy_version,correction_schema_version
LINEAGE_FIELDS=source_row_identity,quality_finding_identity,original_value_digest,corrected_value_digest,manual_actor_or_authority_reference
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE; sensitive values are represented by governed digests where required
SHA256_SCOPE=CONTENT_SHA256 over correction event identity, field, before/after value digests, reason, and policy version
REPLAY=reconstruct the ledger entry and verify the cited source finding and value digests
CONFLICT_BEHAVIOR=duplicate correction event with different before/after digests or reason is an audit conflict
FAIL_CLOSED=reject the correction and keep the source value unchanged
~~~

A correction entry is append-only and auditable. It never authorizes raw-row
overwrite.

### 4.8 EXCLUSION_LEDGER_ENTRY_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_B
STABLE_IDENTITY_INPUTS=exclusion_event_id,cleaned_dataset_version_identity,source_row_identity,exclusion_code,exclusion_policy_version
VERSION_FIELDS=exclusion_policy_version,exclusion_schema_version
LINEAGE_FIELDS=source_row_identity,quality_finding_identity,exclusion_reason_reference,decision_authority_reference
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE
SHA256_SCOPE=CONTENT_SHA256 over exclusion event identity, row identity, code, reason, policy, and disposition
REPLAY=rebuild exclusion decision from the cited row, finding, policy, and authority
CONFLICT_BEHAVIOR=contradictory inclusion/exclusion entries for the same version and row are a policy conflict
FAIL_CLOSED=exclude from downstream materialization until explicitly resolved; never silently include
~~~

Exclusion is a governed decision and is distinct from missing-day semantics.

### 4.9 PIT_VISIBILITY_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_C
STABLE_IDENTITY_INPUTS=source_row_identity,visibility_policy_version,forecast_cutoff_at,source_recorded_at,source_available_at,source_revised_at,source_finalized_at,source_cancelled_at
VERSION_FIELDS=visibility_policy_version,visibility_schema_version,forecast_cutoff_identity_version
LINEAGE_FIELDS=source_row_identity,source_artifact_identity,availability_authority_reference,revision_candidate_set
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE with UTC timestamps and explicit nulls
SHA256_SCOPE=CONTENT_SHA256 over visibility decision and all timestamp/provenance inputs
REPLAY=reconstruct visibility for the exact cutoff and verify SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT for eligible rows
CONFLICT_BEHAVIOR=missing/contradictory timestamps or policy versions make visibility indeterminate
FAIL_CLOSED=do not expose the row to any partition
~~~

The required timestamp vocabulary is explicit:
SOURCE_RECORDED_AT, SOURCE_AVAILABLE_AT, SOURCE_REVISED_AT,
SOURCE_FINALIZED_AT, and SOURCE_CANCELLED_AT. A timestamp that is not known
is null/unknown, not a fabricated default.

### 4.10 REVISION_WINNER_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_C
STABLE_IDENTITY_INPUTS=logical_record_key,forecast_cutoff_at,revision_winner_policy_version,ordered_revision_candidate_identities
VERSION_FIELDS=revision_winner_policy_version,revision_schema_version,visibility_policy_version
LINEAGE_FIELDS=all_revision_candidate_source_row_identities,visibility_identity_set,cancellation/finalization evidence
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE with candidates sorted by the frozen tie-break tuple
SHA256_SCOPE=CONTENT_SHA256 over candidate identities, cutoff, policy, selected winner or explicit no-winner result
REPLAY=reconstruct the candidate set visible at the exact cutoff and apply deterministic tie-breaking
CONFLICT_BEHAVIOR=ties, missing winner evidence, or contradictory finalization/cancellation state are resolution conflicts
FAIL_CLOSED=return no winner and block the row; LATEST_ROW_FALLBACK_ALLOWED=false
~~~

Lane C must preserve source availability at or before the cutoff. A current
database row is not evidence of historical visibility.

### 4.11 MATERIALIZED_DATASET_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_D
STABLE_IDENTITY_INPUTS=dataset_id,dataset_version,source_cohort_id,target_decision,canonical_grain,all_policy_versions,builder_version,ordered_partition_identities
VERSION_FIELDS=dataset_schema_version,raw_policy_version,cleaning_policy_version,correction_policy_version,exclusion_policy_version,visibility_policy_version,revision_winner_policy_version,split_policy_version,builder_version
LINEAGE_FIELDS=source_cohort_manifest_sha256,cleaned_dataset_version_identity,pit_visibility_report_identity,partition_manifest_identity_set
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE with partitions sorted TRAIN,VALIDATION,TEST
SHA256_SCOPE=CONTENT_SHA256 over deterministic dataset identity/control payload and ordered partition content hashes
REPLAY=rebuild the dataset control payload and all accepted partition identities from upstream lane outputs
CONFLICT_BEHAVIOR=duplicate dataset version with changed policy, partition, or content identity is a dataset-version conflict
FAIL_CLOSED=do not label the dataset accepted or expose it to metrics/backtests
~~~

This identity binds the complete provenance chain but does not itself grant
access to rows.

### 4.12 MATERIALIZED_PARTITION_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_D
STABLE_IDENTITY_INPUTS=materialized_dataset_identity,partition_name,partition_start_date,partition_end_date,partition_date_field,split_policy_version
VERSION_FIELDS=materialized_partition_schema_version,split_policy_version,builder_version
LINEAGE_FIELDS=materialized_dataset_identity,ordered_cleaned_row_identities,ordered_pit_visibility_identities,split-membership decision
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE; rows are sorted by canonical grain and declared tie-break fields
SHA256_SCOPE=CONTENT_SHA256 over exact canonical partition bytes, with row_count and byte_count measured from those bytes
REPLAY=rebuild the same partition using the same upstream identities and verify byte-for-byte content parity
CONFLICT_BEHAVIOR=overlap, gap, duplicate grain key, changed boundary, or changed row bytes is a partition conflict
FAIL_CLOSED=reject the full dataset manifest and do not partially publish a partition
~~~

The only frozen partition boundaries are the S1 TRAIN, VALIDATION, and TEST
ranges. The partition identity cannot introduce a second date field or
alternate boundary convention.

### 4.13 MATERIALIZED_DATASET_MANIFEST_IDENTITY

~~~text
AUTHORITY_OWNER=LANE_D
STABLE_IDENTITY_INPUTS=all required manifest fields except manifest_sha256, plus deterministic policy and provenance references
VERSION_FIELDS=dataset_version,all policy versions,manifest_schema_version,builder_version
LINEAGE_FIELDS=source cohort,raw source artifacts,cleaned version,quality report,correction/exclusion ledgers,PIT/revision reports,partition identity
CANONICAL_SERIALIZATION=S2_CANONICAL_SERIALIZATION_PROFILE; object keys sorted and self hash excluded
SHA256_SCOPE=MANIFEST_SHA256 over the canonical manifest control payload; build timestamps are provenance and not identity inputs
REPLAY=recompute manifest hash, content hash, byte count, row count, and every upstream reference
CONFLICT_BEHAVIOR=any hash/count/policy/lineage mismatch or missing required field invalidates the manifest
FAIL_CLOSED=manifest is not accepted and the dataset cannot be consumed downstream
~~~

The manifest is the acceptance boundary for a materialized dataset. It must
never conceal a missing lineage reference behind a successful file write.

## 5. Four implementation lanes

Exactly four implementation lanes are frozen. Each lane has one owner and
one bounded decision surface. No lane may silently absorb another lane's
semantics.

### Lane A: raw ingestion and lineage foundation

~~~text
LANE=A
TASK_ID=V03_S2_A_RAW_INGESTION_LINEAGE_FOUNDATION_R1
OWNER=RAW_SOURCE_AND_LINEAGE_OWNER
OWNS=immutable source reference; source artifact identity; import batch identity; stable source row identity; source/version/hash preservation; ingestion idempotency; raw lineage persistence/query boundary
DOES_NOT_OWN=cleaning policy; correction semantics; exclusion semantics; revision-winner policy; PIT eligibility; final materialized split construction
~~~

Lane A may validate transport and source identity, preserve raw bytes and
metadata, assign or verify stable source identities, and expose append-only
lineage references. It must not alter values, select a revision winner, or
decide partition membership.

### Lane B: cleaning, quality, and correction

~~~text
LANE=B
TASK_ID=V03_S2_B_CLEANING_QUALITY_CORRECTION_R1
OWNER=CLEANING_QUALITY_CORRECTION_OWNER
OWNS=cleaned dataset version; quality findings; correction ledger; exclusion ledger; manual-correction audit; missing/invalid/duplicate/mapping treatment; cleaned-row lineage to source rows
DOES_NOT=mutate raw records; redefine source identity; redefine PIT visibility; define revision winner; define split dates
~~~

Lane B must preserve unknown-day semantics and record any accepted correction
or exclusion as a versioned ledger decision.

### Lane C: PIT visibility and revision winner

~~~text
LANE=C
TASK_ID=V03_S2_C_PIT_VISIBILITY_REVISION_WINNER_R1
OWNER=POINT_IN_TIME_AND_REVISION_OWNER
OWNS=SOURCE_RECORDED_AT; SOURCE_AVAILABLE_AT; SOURCE_REVISED_AT; SOURCE_FINALIZED_AT; SOURCE_CANCELLED_AT; forecast-cutoff eligibility; point-in-time reconstruction; revision winner; cancellation/finalization visibility; deterministic tie-breaking; no-latest-row-fallback semantics
MUST_PRESERVE=SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT for an eligible row
DOES_NOT_OWN=raw mutation; cleaning rules; split dates; model execution; backtest execution
~~~

Lane C returns an explicit no-winner or blocked result when visibility cannot
be reconstructed. It cannot repair upstream lineage or redefine a cleaned
value.

### Lane D: materialized dataset and split freeze

~~~text
LANE=D
TASK_ID=V03_S2_D_MATERIALIZED_DATASET_SPLIT_FREEZE_R1
OWNER=MATERIALIZED_DATASET_AND_SPLIT_OWNER
OWNS=deterministic materialized builder; TRAIN manifest; VALIDATION manifest; TEST manifest; final row counts; byte counts; content hashes; policy-version bindings; split re-acceptance evidence; deterministic rebuild/hash replay
CONSUMES=Lane A source lineage; Lane B cleaned/quality/ledger outputs; Lane C PIT/revision outputs; inherited S1 split and target authority
DOES_NOT_INVENT=source semantics; cleaning semantics; correction semantics; PIT semantics; revision-winner semantics; split boundaries
~~~

Lane D may fail closed when an upstream lane is absent, unmerged, or
main-alignment is not verified. It may not create a substitute upstream
record.

## 6. Parallel development and dependency gates

The following rules apply to separate future Draft PRs:

~~~text
A_B_C_PARALLEL_IMPLEMENTATION_ALLOWED=true
A_B_C_SEPARATE_BRANCH_REQUIRED=true
A_B_C_SEPARATE_DRAFT_PR_REQUIRED=true
A_B_C_FILE_OWNERSHIP_OVERLAP_ALLOWED=false

D_DRAFT_MAY_BEGIN_WHILE_A_B_C_ACTIVE=true
D_READY_REQUIRES_A_B_C_MERGED=true
D_READY_REQUIRES_POST_MERGE_MAIN_ALIGNMENT=true
D_MERGE_REQUIRES_A_B_C_MERGED=true
D_MERGE_REQUIRES_POST_MERGE_MAIN_ALIGNMENT=true

NO_STEP_IMPLIES_THE_NEXT=true
~~~

A Draft is a proposed implementation state only. It does not prove that the
upstream lane is merged, that its exact head was reviewed, or that its
dependencies are satisfied. Lane D may be drafted against this frozen
contract while A, B, or C is active, but D Ready and D Merge are held until
all required upstream lanes are merged and current main is independently
revalidated against the exact dependency graph.

No lane's completion implies another lane's review, Ready, Merge, S2
acceptance, S3 authorization, or data-access authorization.

## 7. Future maximum file allowlists

### 7.1 Allowlist status and current-architecture findings

~~~text
IMPLEMENTATION_ALLOWLIST_READINESS=BLOCKED
ALLOWLIST_MODE=FUTURE_MAXIMUM_CANDIDATE_PATHS_ONLY
IMPLEMENTATION_FILES_CREATED_BY_THIS_TASK=0
CURRENT_ARCHITECTURE_FILE_OWNERSHIP_FROZEN=false
~~~

The current architecture contains cross-layer surfaces rather than a
materialized-dataset package. In particular:

- actual_harvest_import currently combines API, raw import, validation,
  commit, lifecycle, and persistence surfaces;
- actual_harvest_labels is a separate label-snapshot surface with no dedicated
  S2 test directory;
- harvest_state and residual_model contain existing authority, cutoff,
  visibility, manifest, and forecast consumers that are not all S2-owned;
- rolling_backtest contains additional cutoff/availability consumers;
- backend/app/db/base.py, backend/app/models/__init__.py, backend/app/main.py,
  backend/app/api/__init__.py, and shared repositories are integration seams;
- the current Alembic history is a single chain through revision
  0028_quality_child_hash_scope and has no frozen S2 entity/revision ownership;
- no backend/app/materialized_dataset package exists on this baseline.

Therefore the lists below are maximum candidate paths, not permission to edit
them. Existing shared files are deliberately excluded until an explicit
integration-seam decision names one merge owner. A future lane authorization
must resolve the listed questions and re-verify the exact changed-file scope.

No production path is assigned to two lanes in these maximum lists. If a
future implementation needs a shared path, it must be added as
SHARED_INTEGRATION_SEAM with exactly one MERGE_OWNER before implementation.

### 7.2 Lane A maximum allowlists

~~~text
LANE_A_PRODUCTION_ALLOWLIST=
backend/app/actual_harvest_import/api_auth.py
backend/app/actual_harvest_import/api_errors.py
backend/app/actual_harvest_import/api_policy.py
backend/app/actual_harvest_import/api_schemas.py
backend/app/actual_harvest_import/batch_a_contracts.py
backend/app/actual_harvest_import/canonical_hashes.py
backend/app/actual_harvest_import/commit_hashes.py
backend/app/actual_harvest_import/commit_models.py
backend/app/actual_harvest_import/commit_persistence.py
backend/app/actual_harvest_import/commit_service.py
backend/app/actual_harvest_import/enums.py
backend/app/actual_harvest_import/errors.py
backend/app/actual_harvest_import/lifecycle.py
backend/app/actual_harvest_import/lifecycle_persistence.py
backend/app/actual_harvest_import/models.py
backend/app/actual_harvest_import/persistence.py
backend/app/actual_harvest_import/schemas.py
backend/app/actual_harvest_import/spreadsheet_parser.py
backend/app/actual_harvest_import/spreadsheet_policy.py
backend/app/actual_harvest_import/spreadsheet_template.py
backend/app/actual_harvest_import/trial_create.py
backend/app/api/actual_harvest_imports.py

LANE_A_TEST_ALLOWLIST=
backend/tests/actual_harvest_import/conftest.py
backend/tests/actual_harvest_import/alembic_cases.py
backend/tests/actual_harvest_import/postgres_cases.py
backend/tests/actual_harvest_import/test_api_authorization.py
backend/tests/actual_harvest_import/test_api_hashes.py
backend/tests/actual_harvest_import/test_api_limits.py
backend/tests/actual_harvest_import/test_api_routes.py
backend/tests/actual_harvest_import/test_api_schemas.py
backend/tests/actual_harvest_import/test_api_schemas_exports.py
backend/tests/actual_harvest_import/test_architecture.py
backend/tests/actual_harvest_import/test_batch_a_synthetic_contracts.py
backend/tests/actual_harvest_import/test_commit_contract.py
backend/tests/actual_harvest_import/test_csv_parser.py
backend/tests/actual_harvest_import/test_errors.py
backend/tests/actual_harvest_import/test_i4_architecture.py
backend/tests/actual_harvest_import/test_lifecycle.py
backend/tests/actual_harvest_import/test_lifecycle_postgres.py
backend/tests/actual_harvest_import/test_persistence.py
backend/tests/actual_harvest_import/test_spreadsheet_normalization.py
backend/tests/actual_harvest_import/test_spreadsheet_template.py
backend/tests/actual_harvest_import/test_validation.py
backend/tests/actual_harvest_import/test_validation_contract.py
backend/tests/actual_harvest_import/test_xlsx_parser.py

LANE_A_MIGRATION_ALLOWLIST=
backend/alembic/versions/<lane-a-raw-ingestion-lineage-revision>.py

LANE_A_EXCLUSIONS=
backend/app/db/base.py
backend/app/models/__init__.py
backend/app/main.py
backend/alembic/versions/0018_actual_harvest_import_staging.py
backend/alembic/versions/0020_actual_harvest_commit_manifest.py
~~~

The two existing Alembic files in the exclusions are historical authority and
must not be edited by a future lane without a separate migration decision.
The validation module is not in Lane A's production list even though current
imports call it; that cross-layer ownership is one reason readiness remains
blocked.

### 7.3 Lane B maximum allowlists

~~~text
LANE_B_PRODUCTION_ALLOWLIST=
backend/app/actual_harvest_import/validation.py
backend/app/actual_harvest_import/validation_hashes.py
backend/app/actual_harvest_import/validation_models.py
backend/app/actual_harvest_import/validation_service.py
backend/app/actual_harvest_labels/enums.py
backend/app/actual_harvest_labels/hashes.py
backend/app/actual_harvest_labels/models.py
backend/app/actual_harvest_labels/persistence.py
backend/app/actual_harvest_labels/schemas.py
backend/app/actual_harvest_labels/service.py

LANE_B_TEST_ALLOWLIST=
backend/tests/actual_harvest_import/test_validation.py
backend/tests/actual_harvest_import/test_validation_contract.py
backend/tests/actual_harvest_labels/<future-owned-tests>.py

LANE_B_MIGRATION_ALLOWLIST=
backend/alembic/versions/<lane-b-cleaning-quality-correction-revision>.py

LANE_B_EXCLUSIONS=
backend/app/actual_harvest_import/models.py
backend/app/actual_harvest_import/persistence.py
backend/app/actual_harvest_import/commit_service.py
backend/app/actual_harvest_labels/__init__.py
backend/tests/actual_harvest_import/test_i7_label_snapshot.py
~~~

The current validation modules are coupled to the A import path and the
actual_harvest_labels package has no dedicated S2 test ownership. Whether
those seams remain B-owned or become an explicit shared seam must be decided
before B implementation. B cannot alter raw models or persisted raw source.

### 7.4 Lane C maximum allowlists

~~~text
LANE_C_PRODUCTION_ALLOWLIST=
backend/app/harvest_state/authority_canonical.py
backend/app/harvest_state/authority_request_loader.py
backend/app/harvest_state/authority_request_types.py
backend/app/harvest_state/authority_resolution.py
backend/app/harvest_state/authority_resolution_errors.py
backend/app/harvest_state/authority_resolution_types.py
backend/app/harvest_state/authority_schemas.py
backend/app/harvest_state/canonical.py
backend/app/harvest_state/provenance.py
backend/app/residual_model/forecast_cutoff.py
backend/app/residual_model/visibility.py
backend/app/rolling_backtest/availability.py
backend/app/rolling_backtest/resolution.py

LANE_C_TEST_ALLOWLIST=
backend/tests/harvest_state/test_authority_canonical.py
backend/tests/harvest_state/test_authority_resolution.py
backend/tests/harvest_state/test_authority_schemas.py
backend/tests/harvest_state/test_canonical.py
backend/tests/harvest_state/test_provenance.py
backend/tests/residual_model/test_forecast_cutoff.py
backend/tests/residual_model/test_pit_visibility_authority.py
backend/tests/residual_model/test_visibility.py
backend/tests/rolling_backtest/test_cutoff_boundaries.py
backend/tests/rolling_backtest/test_historical_backtest_contracts.py

LANE_C_MIGRATION_ALLOWLIST=
backend/alembic/versions/<lane-c-pit-visibility-revision-winner-revision>.py

LANE_C_EXCLUSIONS=
backend/app/actual_harvest_import/validation.py
backend/app/actual_harvest_labels/persistence.py
backend/app/rolling_backtest/replay_pipeline.py
backend/app/models/harvest_state.py
~~~

The harvest_state and rolling_backtest files above have broader historical
responsibilities than S2. Their exact S2 ownership, compatibility adapters,
and integration seam are unresolved; they are candidate paths only and keep
readiness blocked.

### 7.5 Lane D maximum allowlists

~~~text
LANE_D_PRODUCTION_ALLOWLIST=
backend/app/materialized_dataset/__init__.py
backend/app/materialized_dataset/builder.py
backend/app/materialized_dataset/canonical.py
backend/app/materialized_dataset/hashing.py
backend/app/materialized_dataset/manifest.py
backend/app/materialized_dataset/partitions.py
backend/app/materialized_dataset/schemas.py
backend/app/materialized_dataset/service.py
backend/app/api/materialized_datasets.py

LANE_D_TEST_ALLOWLIST=
backend/tests/materialized_dataset/conftest.py
backend/tests/materialized_dataset/test_builder.py
backend/tests/materialized_dataset/test_canonical.py
backend/tests/materialized_dataset/test_hashing.py
backend/tests/materialized_dataset/test_manifest.py
backend/tests/materialized_dataset/test_partitions.py
backend/tests/materialized_dataset/test_rebuild_parity.py
backend/tests/materialized_dataset/test_data_access_boundaries.py

LANE_D_MIGRATION_ALLOWLIST=
backend/alembic/versions/<lane-d-materialized-dataset-revision>.py

LANE_D_EXCLUSIONS=
backend/app/actual_harvest_import
backend/app/actual_harvest_labels
backend/app/harvest_state
backend/app/residual_model
backend/app/rolling_backtest
backend/app/db/base.py
backend/app/models/__init__.py
backend/app/main.py
~~~

All Lane D paths are future-only on this baseline. The D implementation must
not create a parallel source, cleaning, PIT, revision, or split authority.

### 7.6 Unresolved ownership questions

Readiness remains blocked until all of the following are resolved in a
separately authorized planning or implementation task:

~~~text
UNRESOLVED_PATH_1=backend/app/actual_harvest_import/validation.py and validation_service.py
QUESTION_1=Are validation findings B-owned while import transaction wiring remains A-owned, or is an explicit shared integration seam required?
UNRESOLVED_PATH_2=backend/app/actual_harvest_labels/*
QUESTION_2=Which existing label snapshot responsibilities are reusable for B versus C, and who owns the merge seam?
UNRESOLVED_PATH_3=backend/app/harvest_state/* and backend/app/residual_model/*
QUESTION_3=Which existing forecast authority files can serve S2 PIT without changing non-S2 behavior?
UNRESOLVED_PATH_4=backend/app/rolling_backtest/availability.py and resolution.py
QUESTION_4=Can S2 reuse these cutoff consumers without broadening S2 into backtest implementation?
UNRESOLVED_PATH_5=backend/app/db/base.py and backend/app/models/__init__.py
QUESTION_5=Which lane, if any, owns shared registration changes, and how is one merge owner enforced?
UNRESOLVED_PATH_6=backend/alembic/versions/*
QUESTION_6=Which S2 persistent entities require migration, and what is the dependency order without parallel heads?
UNRESOLVED_PATH_7=backend/app/materialized_dataset/*
QUESTION_7=What exact schema/service/API surface is needed for D after A/B/C contracts are implemented?
IMPLEMENTATION_ALLOWLIST_READINESS=BLOCKED
~~~

No current file is silently declared a shared seam. A future authorization must
record any shared seam as SHARED_INTEGRATION_SEAM, name exactly one merge owner,
and list all consuming lanes before the path is changed.

## 8. Migration strategy

~~~text
MIGRATION_STRATEGY=LANE_OWNED_NON_OVERLAPPING_MIGRATIONS
MIGRATION_CREATION_AUTHORIZED_IN_P0=false
CURRENT_ALEMBIC_HEAD=0028_quality_child_hash_scope
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
SINGLE_ALEMBIC_HEAD_REQUIRED_AFTER_INTEGRATION=true
REVISION_IDS_INVENTED_IN_P0=false
~~~

The current Alembic history is a single chain. P0 creates no migration and
does not edit existing revisions. If persistent entities are required, each
lane may propose only its own future migration path from the allowlist:

- A owns raw source reference, source artifact, import batch, and source-row
  lineage entities.
- B owns cleaned dataset versions, quality findings, correction ledgers, and
  exclusion ledgers.
- C owns PIT visibility and revision-winner decision entities.
- D owns materialized dataset, partition, and manifest entities.

A migration must name its upstream revision dependency, use no overlapping
table/column ownership, preserve append-only behavior, and be independently
validated. No lane may create parallel Alembic heads. If an upstream migration
is not merged on main, every dependent lane remains Draft-only and cannot be
Ready or Merge. No revision ID is frozen or invented by this contract.

If implementation demonstrates that no new schema is required, it must be
recorded as a separately reviewed deviation; it cannot be inferred from this
contract or used to bypass the migration gate.

## 9. Materialized dataset and partition manifest

A future Lane D manifest must contain at least the following fields. A missing
field, null where a required value is not applicable, policy mismatch, or
unreplayable lineage is invalid.

~~~text
dataset_id
dataset_version
partition_name
source_cohort_id
source_cohort_manifest_sha256
target_decision
canonical_grain
partition_date_field
partition_start_date
partition_end_date

raw_policy_version
cleaning_policy_version
correction_policy_version
exclusion_policy_version
visibility_policy_version
revision_winner_policy_version
split_policy_version
builder_version

row_count
byte_count
content_sha256
manifest_sha256

build_started_at
build_completed_at

lineage_complete
quality_gate_status
rebuild_hash_replay_status
~~~

Required field semantics:

- dataset_id and dataset_version are the stable dataset identity and immutable
  version, not a database row ID.
- partition_name is exactly TRAIN, VALIDATION, or TEST. The three names are
  case-sensitive.
- source_cohort_manifest_sha256 must equal the inherited S1 source cohort
  manifest digest.
- target_decision and canonical_grain must equal the inherited S1 values.
- partition_date_field is HARVEST_BUSINESS_DATE. Partition boundaries use the
  inherited Asia/Shanghai business-date interpretation.
- start and end dates use the inherited inclusive ranges and cannot be
  redrawn by D.
- policy versions identify the exact A/B/C/D policy inputs used to build the
  partition.
- row_count is the count of canonical rows in the exact partition bytes.
  Unknown or unavailable counts are not zero.
- byte_count is the count of exact UTF-8 bytes hashed by content_sha256, after
  the declared line-ending and encoding policy is applied.
- content_sha256 is CONTENT_SHA256 over deterministic ordered partition bytes.
- manifest_sha256 is MANIFEST_SHA256 over the canonical manifest control
  payload, excluding itself and volatile build timestamps.
- build timestamps are timezone-aware provenance, not identity substitutes.
- lineage_complete is true only when every materialized row can replay to source,
  cleaning, quality/ledger, PIT, revision, and split decisions.
- quality_gate_status must be a defined accepted status, not an assertion that
  model quality or metrics have been computed.
- rebuild_hash_replay_status must be PASS only after an independent deterministic
  rebuild produces identical content and manifest hashes.

The full provenance chain is:

~~~text
SOURCE_ARTIFACT_SHA256
  -> RAW_IMPORT_BATCH_IDENTITY
  -> SOURCE_ROW_IDENTITY
  -> CLEANED_DATASET_VERSION_IDENTITY
  -> CLEANED_ROW_IDENTITY
  -> QUALITY_FINDING_IDENTITY / CORRECTION_LEDGER_ENTRY_IDENTITY / EXCLUSION_LEDGER_ENTRY_IDENTITY
  -> PIT_VISIBILITY_IDENTITY / REVISION_WINNER_IDENTITY
  -> MATERIALIZED_PARTITION_IDENTITY
  -> MATERIALIZED_DATASET_MANIFEST_IDENTITY
~~~

A manifest may reference identities and hashes but may not embed raw Source002
rows or expose sensitive row-level data.

## 10. Test seal and data-access boundary

Test materialization is a storage/build activity and is not a test outcome,
evaluation result, metric, or model-quality claim.

~~~text
TEST_MATERIALIZATION_IS_NOT_TEST_EVALUATION=true

SOURCE_002_READ=false
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false

TRAIN_ROW_ACCESS=false
VALIDATION_ROW_ACCESS=false
TEST_ROW_ACCESS=false
TEST_MATERIALIZATION_EXECUTED=false

METRIC_EXECUTION=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
~~~

A later explicit authorization is required before controlled real-data
materialization. TEST remains sealed until that authorization. No S2 task may
read TEST rows or external holdout rows merely because the contract names their
manifest fields. No S2 result may claim test performance, quantile coverage,
backtest success, model validation, or production readiness.

## 11. Future S2 acceptance model

The following are minimum requirements for a future S2 acceptance decision.
They are not current facts and are all unperformed at this contract-freeze
stage.

~~~text
REQUIRED_FINAL_S2_ACCEPTANCE=ALL_OF_THE_FOLLOWING

IMMUTABLE_RAW_REFERENCE_ACCEPTED=true
SOURCE_ROW_LINEAGE_ACCEPTED=true
CLEANED_DATA_MANIFEST_ACCEPTED=true
QUALITY_REPORT_ACCEPTED=true
CORRECTION_LEDGER_ACCEPTED=true
EXCLUSION_LEDGER_ACCEPTED=true
TIME_VISIBILITY_REPORT_ACCEPTED=true

TRAIN_MATERIALIZED_MANIFEST_ACCEPTED=true
VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED=true
TEST_MATERIALIZED_MANIFEST_ACCEPTED=true

FINAL_SPLIT_MANIFEST_ACCEPTED=true
FINAL_DATASET_HASHES_ACCEPTED=true
DETERMINISTIC_REBUILD_PARITY_ACCEPTED=true

S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
V0_3_S3_AUTHORIZED=false
~~~

Each acceptance item needs exact-head implementation evidence, independent
review, schema/hash replay where relevant, and a current-main dependency check.
No item is accepted by the existence of a file, a green unrelated workflow, or
a Draft PR.

## 12. Validation and authorization boundary

This contract's own validation is limited to documentation and scope:

~~~text
CONTRACT_SYNTAX=MARKDOWN
CONTRACT_REQUIRED_S1_BINDINGS_PRESENT=true
CONTRACT_REQUIRED_INVARIANTS_PRESENT=true
CONTRACT_REQUIRED_IDENTITY_CONTRACTS=13
CONTRACT_REQUIRED_LANES=4
CONTRACT_REQUIRED_ALLOWLIST_SETS=12
CONTRACT_REQUIRED_MANIFEST_FIELDS_PRESENT=true
CONTRACT_REQUIRED_DATA_BOUNDARIES_PRESENT=true
IMPLEMENTATION_ALLOWLIST_READINESS=BLOCKED
~~~

The contract does not assert that any implementation lane is complete, that a
materialized dataset exists, or that a final S2 acceptance item is true.

~~~text
P0_IMPLEMENTATION_PERFORMED=true
A_IMPLEMENTATION_PERFORMED=false
B_IMPLEMENTATION_PERFORMED=false
C_IMPLEMENTATION_PERFORMED=false
D_IMPLEMENTATION_PERFORMED=false

INDEPENDENT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
V0_3_S3_AUTHORIZED=false
NEXT_SLICE_STARTED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

The only repository mutation for this task is creation of
docs/v0-3/s2/s2-materialized-dataset-contract.md. S1 acceptance records,
reconciliation artifacts, source evidence, production code, tests, schemas,
migrations, workflows, dependencies, and data artifacts remain unchanged.
