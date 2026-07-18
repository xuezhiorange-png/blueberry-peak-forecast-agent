# Q2A Actual-Harvest API Contract

Status: docs-only logical API design under Issue #102 comment `4976761806`.

## 1. Purpose and non-implementation boundary

This document defines logical endpoints for a future user-supplied actual-harvest import. It is not an OpenAPI file and does not implement HTTP routes, authentication, persistence, migrations, parsers, or label snapshots.

API requests and spreadsheet uploads share the canonical `ActualHarvestImportBatch` and `ActualHarvestImportRecord` contract from `q2a-user-supplied-actual-harvest-import-contract.md`. The API must not create an active label before validation and atomic commit.

Authority references:

- `docs/forecast-quality/q2a-user-supplied-actual-harvest-import-contract.md`
- `docs/forecast-quality/q2a-actual-harvest-source-contract.md`
- `docs/forecast-quality/q2a-label-snapshot-and-revision-contract.md`
- `docs/forecast-quality/q2a-prediction-label-alignment-decision.md`
- `docs/forecast-quality/slice-q1-data-coverage-audit.md`
- `backend/app/models/harvest_state.py`, `backend/app/models/analytics.py`, and `backend/app/agent/schemas.py` were read for current-main facts only.

## 2. Logical endpoints

The future logical endpoints are:

```text
POST /actual-harvest/imports
POST /actual-harvest/imports/{import_id}/records
POST /actual-harvest/imports/{import_id}/seal
POST /actual-harvest/imports/{import_id}/validate
GET  /actual-harvest/imports/{import_id}
GET  /actual-harvest/imports/{import_id}/preview
GET  /actual-harvest/imports/{import_id}/errors
POST /actual-harvest/imports/{import_id}/commit
POST /actual-harvest/imports/{import_id}/cancel
```

These are design names only. No endpoint is implemented or exposed by this PR.

## 3. Request contracts

### 3.1 Create import

`POST /actual-harvest/imports` creates a staging batch. Its logical request includes:

```text
import_channel                 # API
source_system
source_dataset
source_version
external_batch_id
idempotency_key
submitted_by_identity
source_semantics_attestation
schema_version
mapping_policy_version
validation_policy_version
raw_payload_hash
client_expected_record_count_or_null
client_raw_payload_hash_or_null
```

The response identifies the staging `import_id`, canonical schema version, initial status, and deterministic batch metadata. It does not claim that any label is active.

The server-owned seal fields are:

```text
expected_record_count_or_null
uploaded_record_count
sealed_record_count_or_null
sealed_at_or_null
sealed_by_identity_or_null
seal_status
server_raw_payload_hash_or_null
canonical_batch_hash_or_null
seal_manifest_hash_or_null
```

`import_received_at` and `ingested_at` are also server-generated immutable timestamps. They are returned as provenance and are never accepted as client fields.

### 3.2 Add records

`POST /actual-harvest/imports/{import_id}/records` accepts canonical records or a bounded canonical record page only while the batch is `UPLOADING`. Every record uses the exact field names in the shared contract, including `external_logical_record_id`, `external_revision_id`, `source_recorded_at`, `source_recorded_at_authority_status`, `revision_number`, and `supersedes_external_revision_id`. The endpoint must reject records added after sealing or to a terminal/cancelled batch and must not silently overwrite an existing source revision.

The canonical record payload inventory is:

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
supersedes_external_revision_id
season_code
farm_timezone
revised_at
finalized_at
source_row_number
source_sheet_name
source_note
```

### 3.3 Validate and preview

`POST /actual-harvest/imports/{import_id}/seal` is the only transition from `UPLOADING` to `SEALED`. The server computes authoritative record count, raw/canonical hashes, and a seal manifest hash. Client count/hash values are assertions only; mismatch fails closed. `POST .../validate` runs the deterministic parse/semantic/schema/mapping/revision validation contract only from `SEALED`, and binds the result to the seal manifest hash. `GET .../preview` returns counts and canonical validation results from staging only. Neither endpoint activates a label. A validation result is immutable for its input hash; a changed payload requires a new seal and validation result.

### 3.4 Commit and cancel

`POST .../commit` is allowed only from `VALIDATED`, with matching seal, mapping, validation, and aggregation hashes. v1 commit is full-batch atomic; any invalid row or hash mismatch fails the whole operation. `POST .../cancel` is allowed before commit and never deletes committed source history. Race outcomes for append/seal, seal/validate, validate/commit, commit/commit, and cancel/commit fail closed.

## 4. Response envelope

Every response uses a typed logical envelope:

```text
request_id
status
data_or_null
errors
warnings
pagination_or_null
canonical_hashes
provenance
```

`data` for an import includes `import_id`, batch status, counts, schema/mapping/validation versions, and source artifact hashes. It must not include unrestricted raw rows by default. Preview and errors use bounded pagination.

The response must distinguish `VALIDATED` from `COMMITTED`. `COMMITTED` means the batch passed the atomic commit contract, not that a historical evaluation snapshot has already been generated.

## 5. State and transition rules

Allowed states:

```text
RECEIVED
UPLOADING
SEALED
VALIDATING
VALIDATION_FAILED
VALIDATED
COMMITTING
COMMITTED
PARSE_FAILED
COMMIT_FAILED
CANCELLED
```

The valid lifecycle is `RECEIVED -> UPLOADING -> SEALED -> VALIDATING -> VALIDATED -> COMMITTING -> COMMITTED`, with deterministic failure or cancellation transitions. `PARSING` may be an internal spreadsheet transport state, but parse completion must enter `UPLOADING` before sealing. No request may transition directly from submit to `COMMITTED`. A failed commit must not leave a partially active label. `SEALED` is the sole completeness boundary and is immutable.

## 6. Idempotency and conflicts

The API uses `idempotency_key` and `external_batch_id` with the canonical hashes:

```text
raw_payload_hash
server_raw_payload_hash_or_null
canonical_batch_hash
canonical_record_hash
mapping_snapshot_hash
validation_result_hash
commit_manifest_hash
seal_manifest_hash_or_null
aggregation_manifest_hash
```

Rules:

```text
same idempotency key + same canonical payload = original result
same idempotency key + different canonical payload = IDEMPOTENCY_KEY_CONFLICT
same external record + same revision + same payload = idempotent duplicate
same external record + same revision + different payload = REVISION_NUMBER_CONFLICT
```

The API must return the original result for an exact replay without adding a second effective record. Hashes exclude runtime hostnames, temporary paths, database IDs, and unordered iteration.

## 7. Authorization boundary

The future endpoint requires an authorized user identity and a source semantics attestation. Authorization must cover source-system scope, allowed farm/season scope, upload size policy, preview visibility, validation visibility, and commit permission. `submitted_by_identity` is an audit identity and must not become an unnecessary personal-data field in the imported record.

No API caller may bypass exact identity mapping, source semantics, revision validation, point-in-time rules, or the full-batch atomic gate. No endpoint may accept receipt/arrival as a primary actual-harvest label.

## 8. Errors and pagination

The machine-readable error shape is:

```text
error_code
severity
import_id
record_index_or_null
external_logical_record_id_or_null
external_revision_id_or_null
field_path_or_null
message_template_id
details
```

The minimum stable codes are:

```text
REQUIRED_FIELD_MISSING
UNKNOWN_FIELD
INVALID_DATE
INVALID_DATETIME
INVALID_TIMEZONE
INVALID_DECIMAL
NEGATIVE_QUANTITY
IDENTITY_MAPPING_NOT_FOUND
IDENTITY_MAPPING_AMBIGUOUS
DUPLICATE_RECORD
IDEMPOTENCY_KEY_CONFLICT
REVISION_NUMBER_CONFLICT
REVISION_PREDECESSOR_MISSING
REVISION_IDENTITY_CONFLICT
REVISION_MULTIPLE_SUCCESSORS
REVISION_LINEAGE_CYCLE
REVISION_LOGICAL_RECORD_MISMATCH
MULTIPLE_TERMINAL_REVISIONS
INVALID_RECORD_STATUS
SOURCE_SEMANTICS_ATTESTATION_MISSING
SOURCE_SEMANTICS_NOT_FARM_PICK
BATCH_NOT_VALIDATED
BATCH_ALREADY_COMMITTED
CANONICAL_HASH_MISMATCH
BATCH_NOT_SEALED
BATCH_ALREADY_SEALED
BATCH_SEAL_HASH_CONFLICT
BATCH_RECORD_COUNT_MISMATCH
BATCH_MUTATION_AFTER_SEAL
BATCH_SEAL_CHANGED
```

`details` is structured and sanitized. It never contains a traceback, credentials, private URLs, or unrestricted raw business rows. Error and preview endpoints must use deterministic bounded pagination with an explicit page-size policy; the maximum raw payload and page sizes remain configured policy rather than arbitrary values frozen here.

## 9. Cutoff and label boundary

The API only creates staging and committed source artifacts. Evaluation labels are generated later from committed, valid revisions and an as-of cutoff:

```text
forecast_cutoff_at
< forecast_target_date_or_window_end
<= label_observation_cutoff_at
<= replay_executed_at
```

An evaluation snapshot sees only valid terminal revisions with `source_recorded_at <= label_observation_cutoff_at` when `source_recorded_at_authority_status=TRUSTED_SOURCE_TIMESTAMP`. `import_received_at` and `ingested_at` are server-generated provenance and cannot establish historical source visibility. Records with `USER_ASSERTED_UNVERIFIED`, `MISSING`, or `CONFLICTING` source time are not historical-as-of eligible; they may enter final adjudication only after separate final-eligibility gates. The API never uses a future correction to rewrite a historical snapshot, never fills missing dates with zero, and never treats a raw uploaded row as the final winner without lineage validation.

## 10. Revision-first grain aggregation

The target label grain remains `SEASON X FARM X SUBFARM_OR_PLOT X VARIETY X HARVEST_BUSINESS_DATE`. At the requested visibility cutoff, the API selects one valid terminal revision per `logical_record_key` before grouping. Multiple different logical records may share one canonical grain; same grain is not a duplicate. The API then computes an exact Decimal sum and persists an ordered contributing-revision manifest.

The manifest orders revision keys by `source_system`, `external_logical_record_id`, and `external_revision_id`, and includes the visibility mode, cutoff, ordered revision keys and hashes, count, exact decimal sum, aggregation policy version, and `aggregation_manifest_hash`. Equivalent canonical API and spreadsheet records must produce identical aggregation manifests and hashes. No first-row, last-row, max-value, latest-import, or database-ID shortcut is allowed.

## 11. Future implementation decomposition

| Slice | Future API scope | Explicit exclusion |
|---|---|---|
| Q2A-I4 | batch creation, records, get, preview, seal, cancel | no validation or active-label write |
| Q2A-I5 | validate, errors, exact mapping, lineage, preview validation summary, cancel extension | no commit, winner, aggregation, or label snapshot |
| Q2A-I6 | atomic commit and immutable provenance | no partial commit v1 |
| Q2A-I7 | label snapshot and cutoff visibility | no backtest runner |
| Q2A-I8 | API integration, tests, Goldens, PostgreSQL acceptance | no Q2B or model changes |

Every slice requires separate authorization and a migration/acceptance boundary. This document authorizes no implementation slice.

## 12. Acceptance gates

Future tests must cover exact replay, idempotency conflicts, duplicate revisions, correction, void, finalization, broken lineage, unknown mapping, cutoff visibility, bounded error pagination, API/spreadsheet canonical equivalence, atomic commit, and PostgreSQL concurrent commit races. Tests are not added by this PR.

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

## 13. Change log

- v1.0 — logical API contract derived from the shared user-supplied actual-harvest import contract; implementation not authorized.
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
