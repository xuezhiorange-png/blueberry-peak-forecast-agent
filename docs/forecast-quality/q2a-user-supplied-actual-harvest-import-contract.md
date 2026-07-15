# Q2A User-Supplied Actual-Harvest Import Contract

Status: docs-only design draft under Issue #102 comment `4976761806`.

## 1. Scope and authority

The future actual-harvest source mode is `FUTURE_USER_SUPPLIED_IMPORT`. The supported channels are API batch submission and spreadsheet upload through CSV or XLSX. This document defines a common canonical staging contract for both channels; it does not implement an importer, persistence model, migration, API, parser, template, or backtest runner.

The current repository still has no ready primary actual-harvest label. Existing Task 9 and Agent quantities are model output. `fact_receipt_daily` and the checked-in receipt workbooks are factory receipt/arrival proxies and remain non-primary. A user-supplied import becomes a label candidate only after the complete semantic, identity, revision, and point-in-time gates in this contract pass.

## 2. Required authority alignment

The design is subordinate to these merged authorities:

- `docs/forecast-quality/q2a-actual-harvest-source-contract.md`: farm-pick event definition, primary-vs-proxy boundary, and source evidence gate.
- `docs/forecast-quality/q2a-data-coverage-audit.md`: aggregate-only evidence boundary and the current receipt proxy facts.
- `docs/forecast-quality/q2a-label-snapshot-and-revision-contract.md`: four-time model, revision winner, and fail-closed lineage rules.
- `docs/forecast-quality/q2a-prediction-label-alignment-decision.md`: independent prediction/label alignment and P50/P80/P90 comparison shape.
- `docs/forecast-quality/slice-q1-data-coverage-audit.md`: current schema facts, dual cutoff, and the prohibition on treating model output or receipt as actual harvest.

The current main merge baseline is `7c7330220c3b26d2e1209cec5da43f3a748c0645`. This design does not alter those authorities.

## 3. Frozen business boundary

`actual harvest` means fruit physically picked from plants during one farm-local harvest business day, measured as an observed quantity in kilograms. The imported value is not a forecast, plan, capacity value, inventory balance, backlog, factory arrival, factory receipt, processing input, estimated yield, or test fixture.

The import batch must carry a versioned `source_semantics_attestation` declaring:

```text
physical_event=FARM_PICK
quantity_basis=OBSERVED_WEIGHT
quantity_unit=KG
missing_record_semantics=UNKNOWN_NOT_ZERO
```

An absent, contradictory, or unhashable attestation prevents `COMMITTED`. A field named `harvest` is not evidence of the physical event.

## 4. Canonical staging model

API, CSV, and XLSX must normalize into the same two logical objects. No channel may define alternate business semantics.

### 4.1 `ActualHarvestImportBatch`

The batch-level contract contains:

```text
import_id
import_channel                 # API | CSV | XLSX
source_system
source_dataset
source_version
external_batch_id
idempotency_key
submitted_at
import_received_at
ingested_at
submitted_by_identity
expected_record_count_or_null
uploaded_record_count
sealed_record_count_or_null
sealed_at_or_null
sealed_by_identity_or_null
seal_status
server_raw_payload_hash_or_null
canonical_batch_hash_or_null
seal_manifest_hash_or_null
source_file_name_or_null
source_file_hash_or_null
raw_payload_hash
schema_version
mapping_policy_version
validation_policy_version
source_semantics_attestation
source_semantics_attestation_hash
status
record_count
valid_record_count
invalid_record_count
committed_record_count
created_at
validated_at_or_null
committed_at_or_null
```

`submitted_by_identity` is an authorized actor reference, not a reason to collect farm-worker names, phone numbers, employee IDs, or other unnecessary personal data. File names are metadata only and must not be used as season or identity authority.

### 4.2 `ActualHarvestImportRecord`

The minimum canonical record is:

```text
external_logical_record_id
external_revision_id
source_system
external_batch_id
harvest_business_date
farm_code
subfarm_or_plot_code
variety_code
actual_harvest_quantity_kg
source_recorded_at
source_recorded_at_authority_status
source_recorded_at_authority_reference_or_null
import_received_at
ingested_at
revision_number
record_status
```

The following are conditional or optional as stated:

```text
supersedes_external_revision_id  # required when revision_number > 1
season_code                      # optional; formal resolver may supply it
farm_timezone                    # optional only when independently authorized
revised_at
finalized_at
source_row_number                # spreadsheet diagnostic only
source_sheet_name                # spreadsheet diagnostic only
source_note                      # no personal data or unbounded raw payload
```

The contract rejects vague aliases such as `date`, `weight`, `location`, `name`, and `status` in the canonical layer. They may be accepted only by a separately versioned input mapping layer and must normalize into the exact canonical names before validation.

## 5. Quantity and date rules

```text
UNIT=KG
QUANTITY_TYPE=DECIMAL
NEGATIVE_QUANTITY=REJECT
EXPLICIT_ZERO_QUANTITY=ALLOWED
MISSING_RECORD_IS_NOT_ZERO=YES
```

The decimal precision must reuse the precision frozen by the existing Q2A authority; this design does not invent a new precision. Decimal parsing is exact, rejects non-finite values, and never uses binary floating-point accumulation.

`harvest_business_date` is a farm-local date. It is not a UTC date and is not generated from any timestamp. A timezone must come from an authorized farm identity mapping or be explicitly supplied and validated. A late entry may have `source_recorded_at` after the harvest business date. The system must never manufacture a missing-day row or interpret a missing row as zero.

## 6. Identity mapping

The target grain is:

```text
SEASON
X FARM
X SUBFARM_OR_PLOT
X VARIETY
X HARVEST_BUSINESS_DATE
```

Uploaders use business codes, not internal database IDs. Exact, versioned mappings are required:

```text
farm_code -> internal farm identity
subfarm_or_plot_code -> internal subfarm/plot identity
variety_code -> internal variety identity
season_code -> internal season identity
```

Mappings are case-sensitive unless a separately versioned normalization policy says otherwise. Fuzzy matching, similarity matching, insertion order, latest/current selection, and automatic creation of unknown identities are forbidden. An unresolved or ambiguous mapping is a record validation error. The mapping result and mapping snapshot hash must be frozen before commit.

If `season_code` is absent, only a formal deterministic season resolver may supply it. A date year, filename, receipt season, or guessed database ID is not a resolver.

## 7. Revision and point-in-time contract

The only record statuses are:

```text
ACTIVE
CORRECTED
VOID
FINALIZED
```

`ACTIVE` is a current non-final terminal record, `CORRECTED` is a superseded historical revision and never a winner, `VOID` is invalid and never a winner, and `FINALIZED` is a final terminal record. The winner is selected from one explicit supersession chain, never by import order, largest revision number, or latest timestamp.

The lineage contract requires `external_logical_record_id`, unique `external_revision_id`, `revision_number`, and `supersedes_external_revision_id` where applicable. `logical_record_key = source_system + external_logical_record_id` and `revision_key = source_system + external_revision_id`. Every revision must point to the preceding concrete revision in its logical lineage; winner selection never depends on import order, time, latest batch, or database ID. Fail closed on duplicate revision numbers, missing predecessors, multiple successors, cycles, multiple visible terminals, multiple finalized terminals, unknown status, corrected records without successors, void selection, or same revision identity with different payload.

The authoritative time fields are:

```text
source_recorded_at
import_received_at
ingested_at
```

`source_recorded_at` is the originating source assertion and must carry `source_recorded_at_authority_status`; `import_received_at` and `ingested_at` are server-generated, immutable timestamps. The authority values are `TRUSTED_SOURCE_TIMESTAMP`, `USER_ASSERTED_UNVERIFIED`, `MISSING`, and `CONFLICTING`. User-entered time, upload time, file metadata, row order, batch order, and `harvest_business_date` cannot establish source visibility.

The four-time ordering is inherited unchanged:

```text
forecast_cutoff_at
< forecast_target_date_or_window_end
<= label_observation_cutoff_at
<= replay_executed_at
```

An as-of snapshot may see only records with `source_recorded_at <= label_observation_cutoff_at` when `source_recorded_at_authority_status=TRUSTED_SOURCE_TIMESTAMP` and with a valid visible revision chain. `import_received_at` and `ingested_at` prove application receipt and persistence only; they cannot masquerade as historical source visibility. A committed source batch is immutable; corrections are new revisions or new batches. Records without trusted source time may remain staging or committed evidence and may participate in final adjudication only after separate final-eligibility gates pass, but they are not historical as-of eligible.

## 8. Canonical-grain aggregation

The target grain remains:

```text
SEASON X FARM X SUBFARM_OR_PLOT X VARIETY X HARVEST_BUSINESS_DATE
```

At a requested visibility cutoff, the contract first selects one valid terminal revision per logical source record. Multiple different logical records may share one canonical grain. Only then are visible terminal revisions grouped by grain and summed with exact Decimal arithmetic. Same canonical grain is not a duplicate.

Contributing revisions are ordered by `source_system`, `external_logical_record_id`, and `external_revision_id`. The immutable aggregation manifest includes `visibility_mode`, `label_observation_cutoff_at_or_null`, ordered contributing revision keys and hashes, `contributing_revision_count`, `exact_decimal_quantity_sum_kg`, `aggregation_policy_version`, and `aggregation_manifest_hash`. API and spreadsheet inputs with identical canonical records must produce identical manifests and hashes.

## 9. Immutable seal and lifecycle

The v1 lifecycle is:

```text
RECEIVED
-> UPLOADING
-> SEALED
-> VALIDATING
-> VALIDATED
-> COMMITTING
-> COMMITTED
```

Allowed batch statuses are:

```text
RECEIVED
UPLOADING
SEALED
PARSING
PARSE_FAILED
VALIDATING
VALIDATION_FAILED
VALIDATED
COMMITTING
COMMITTED
COMMIT_FAILED
CANCELLED
```

`ActualHarvestImportBatch` also carries `expected_record_count_or_null`, `uploaded_record_count`, `sealed_record_count_or_null`, `sealed_at_or_null`, `sealed_by_identity_or_null`, `seal_status`, `server_raw_payload_hash_or_null`, `canonical_batch_hash_or_null`, and `seal_manifest_hash_or_null`. `SEALED` is the sole completeness boundary. Server-generated counts and hashes are authoritative; client assertions are checked and mismatches fail closed. After sealing, records cannot be added, removed, replaced, reordered, or modified. Validation starts only from `SEALED`, binds its result to the seal manifest, and commit rechecks seal, mapping, and validation hashes. Submit and preview do not create an active label. v1 uses full-batch atomic semantics: one invalid row blocks the complete batch, partial commit is forbidden, and commit failure cannot leave a partially effective label. A `COMMITTED` batch and its seal manifest are never edited in place.

The stable fail-closed error set includes:

```text
REVISION_IDENTITY_CONFLICT
REVISION_NUMBER_CONFLICT
REVISION_PREDECESSOR_MISSING
REVISION_MULTIPLE_SUCCESSORS
REVISION_LINEAGE_CYCLE
REVISION_LOGICAL_RECORD_MISMATCH
BATCH_NOT_SEALED
BATCH_ALREADY_SEALED
BATCH_SEAL_HASH_CONFLICT
BATCH_RECORD_COUNT_MISMATCH
BATCH_MUTATION_AFTER_SEAL
BATCH_SEAL_CHANGED
```

## 10. Idempotency and canonical hashes

Both channels use the same fields:

```text
idempotency_key
external_batch_id
canonical_batch_hash
source_file_hash
raw_payload_hash
canonical_record_hash
mapping_snapshot_hash
validation_result_hash
commit_manifest_hash
```

The deterministic rules are:

```text
same idempotency key + same canonical payload = original import result
same idempotency key + different canonical payload = deterministic conflict
same revision_key + same canonical payload = idempotent replay
same revision_key + different canonical payload = revision identity conflict
same logical_record_key + same revision_number + different revision_key = revision number conflict
same revision referenced by multiple successors = multiple successor conflict
```

Hashes include every field affecting business semantics or commit outcome. They exclude database-generated IDs, hostnames, temporary paths, unordered iteration, and nondeterministic timestamps. Raw source batch, normalized record, mapping snapshot, validation manifest, revision lineage, and commit manifest remain immutable provenance.

## 11. Staging versus label snapshot

```text
staging record != primary label snapshot
```

Commit preserves the immutable source batch, normalized records, source row hashes, validation manifest, mapping snapshot, revision lineage, commit manifest, and source artifact hashes. An evaluation label snapshot is generated later from valid committed revisions and the applicable cutoff. A spreadsheet row is never directly treated as the final backtest winner, and a receipt proxy never fills a missing actual-harvest row.

## 12. Future implementation decomposition

The following are design-only future slices; none is authorized by this document:

| Slice | Future scope | Explicit exclusion |
|---|---|---|
| Q2A-I1 | canonical schemas, enums, validation errors | no persistence or migration |
| Q2A-I2 | staging persistence and migration | no label snapshot |
| Q2A-I3 | CSV/XLSX parser and generated template | no business semantics fork |
| Q2A-I4 | API batch lifecycle | no direct active-label write |
| Q2A-I5 | exact identity mapping and revision validation | no fuzzy matching |
| Q2A-I6 | atomic commit and immutable provenance | no partial commit v1 |
| Q2A-I7 | label snapshot and point-in-time visibility | no backtest runner |
| Q2A-I8 | API/CLI integration, tests, Goldens, PostgreSQL acceptance | no Q2B or model changes |

Each future slice requires separate authorization, allowed-file review, migration boundary, acceptance tests, and a statement of whether real imported data is needed.

## 13. Acceptance gates

Future implementation must prove:

```text
API_AND_SPREADSHEET_SHARE_ONE_CANONICAL_SCHEMA
NO_DIRECT_COMMIT_BEFORE_VALIDATION
FULL_BATCH_ATOMIC_COMMIT
NO_PARTIAL_COMMIT_V1
EXACT_IDENTITY_MAPPING_ONLY
MISSING_DAY_NOT_ZERO
NEGATIVE_QUANTITY_REJECTED
EXPLICIT_ZERO_ALLOWED
REVISION_LINEAGE_FAIL_CLOSED
POINT_IN_TIME_VISIBILITY_ENFORCED
IDEMPOTENCY_DETERMINISTIC
SOURCE_AND_BATCH_HASHES_PRESERVED
RECEIPT_PROXY_NOT_ACCEPTED
RAW_SOURCE_PROVENANCE_IMMUTABLE
```

Required future tests include exact replay, repeated import, idempotency conflict, duplicate record, correction, void, finalized record, broken lineage, terminal conflicts, unknown mapping, API/spreadsheet equivalence, missing-day semantics, explicit zero, historical cutoff, and PostgreSQL concurrent commit race. This design round does not add or execute those tests.

## Cross-document P0 fixup invariants

```text
SERVER_GENERATED_IMPORT_RECEIVED_AT
SERVER_GENERATED_INGESTED_AT
TRUSTED_SOURCE_RECORDED_AT_REQUIRED_FOR_HISTORICAL_REPLAY
HISTORICAL_AS_OF_ELIGIBLE=TRUSTED_SOURCE_TIMESTAMP_ONLY
FINAL_ADJUDICATION_ELIGIBLE=SEPARATE_FINAL_GATE
REVISION_SELECTION_BEFORE_GRAIN_AGGREGATION
MULTIPLE_LOGICAL_RECORDS_PER_GRAIN_ALLOWED
EXACT_DECIMAL_SUM
SAME_GRAIN_NOT_DUPLICATE
VALIDATE_FROM=SEALED
COMMIT_FROM=VALIDATED
MUTATION_AFTER_SEAL=FORBIDDEN
```

## 14. Change log

- v1.0 — user-supplied actual-harvest import contract design authorized by Issue #102 comment `4976761806`; no implementation authorized.
- v1.1 — closes PR #105 review `4700895486`: authoritative time provenance, logical/revision identity separation, same-grain aggregation, immutable batch sealing, and PR metadata truth synchronization.

## §X.1 Q2A import contract status

```text
ISSUE102_AUTHORIZATION_COMMENT_ID=4976761806
PR105_FIXUP_REVIEW_ID=4700895486
ACTUAL_HARVEST_SOURCE_MODE=FUTURE_USER_SUPPLIED_IMPORT
SUPPORTED_IMPORT_CHANNELS=API_AND_SPREADSHEET_UPLOAD
Q2A_IMPORT_CONTRACT_DESIGN_STATUS=PENDING_REVIEW
Q2A_IMPORT_IMPLEMENTATION_AUTHORIZED=NO
PRIMARY_ACTUAL_HARVEST_LABEL_READY=NO
Q2B_AUTHORIZED=NO
Q3_AUTHORIZED=NO
MODEL_CHANGE_AUTHORIZED=NO
READY_AUTHORIZED=NO
MERGE_AUTHORIZED=NO
ISSUE102_STATE=OPEN
ISSUE99_STATE=OPEN
TASK013_SLICE_C_C2_STATUS=PAUSED
```
