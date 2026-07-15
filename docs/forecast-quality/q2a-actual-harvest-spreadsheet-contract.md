# Q2A Actual-Harvest Spreadsheet Contract

Status: docs-only design draft under Issue #102 comment `4976761806`.

## 1. Purpose and authority

CSV and XLSX are two transport formats for the same `ActualHarvestImportBatch` and `ActualHarvestImportRecord` canonical staging contract. This document defines format, normalization, preview, and rejection rules only. It does not create a CSV/XLSX template, parser, persistence model, migration, API, test, or Golden.

The source must represent observed farm-pick weight, not model output, plan, capacity, inventory, backlog, factory arrival, factory receipt, factory intake, processing input, estimated yield, or fixture data. Existing receipt workbooks remain non-primary proxies.

Authority references:

- `docs/forecast-quality/q2a-user-supplied-actual-harvest-import-contract.md`
- `docs/forecast-quality/q2a-actual-harvest-source-contract.md`
- `docs/forecast-quality/q2a-data-coverage-audit.md`
- `docs/forecast-quality/q2a-label-snapshot-and-revision-contract.md`
- `docs/forecast-quality/q2a-prediction-label-alignment-decision.md`
- `docs/forecast-quality/slice-q1-data-coverage-audit.md`

## 2. Canonical columns

The canonical row columns are exactly:

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

The canonical identity fields are `source_system`, `external_logical_record_id`, and `external_revision_id`. `revision_number` and `supersedes_external_revision_id` are required for revision lineage; `supersedes_external_revision_id` is null only for the initial revision. `source_recorded_at_authority_status` is required and must be one of `TRUSTED_SOURCE_TIMESTAMP`, `USER_ASSERTED_UNVERIFIED`, `MISSING`, or `CONFLICTING`. `import_received_at` and `ingested_at` are server-generated and must not be supplied by CSV/XLSX. `source_row_number` and `source_sheet_name` are diagnostics and do not become business identity.

No alternate channel-specific names such as `date`, `weight`, `location`, `name`, or `status` are canonical. A future parser may map aliases only under an explicit mapping policy version; the normalized result must contain the exact canonical fields before validation.

## 3. CSV contract

CSV input is UTF-8, has exactly one header row, and has one logical record per data row. The header must match the canonical field policy exactly after only the explicitly versioned header normalization allowed by the mapping policy. The parser must reject duplicate canonical headers, missing required headers, unknown headers under a reject policy, and a header that normalizes two source columns to one canonical column.

Empty rows are ignored only when the entire row is empty and the decision is recorded in validation diagnostics. A row containing any value but missing required fields is invalid and blocks the full batch. No invalid row is silently skipped.

## 4. XLSX contract

XLSX input has exactly one canonical data sheet named `actual_harvest`. It has one header row and one logical record per data row. A future implementation must reject a missing canonical sheet, duplicate canonical sheets, duplicate headers, missing required columns, and unknown columns under the frozen policy.

Workbook rules:

- formula cells are rejected in required fields; the parser must not evaluate formulas as source facts;
- merged cells are rejected in the canonical data region;
- hidden rows are not silently omitted and must either be rejected or be explicitly surfaced in validation diagnostics;
- macro or executable content is not accepted by the v1 contract;
- empty rows follow the CSV rule;
- maximum workbook and row limits remain configured policy, not an arbitrary frozen number;
- sheet and row provenance may be retained as diagnostics but not used as business authority.

No template file is created in this round. A future template must be generated from this contract rather than maintained as a second hand-edited field list.

## 5. Date, timezone, and decimal normalization

`harvest_business_date` is a farm-local business date and must not be substituted with a UTC date. `source_recorded_at` is the originating source assertion and is not trusted merely because a user entered it. `import_received_at` and `ingested_at` are server-generated immutable timestamps; CSV/XLSX cannot provide them. Spreadsheet serial dates, text dates, and datetime cells must be normalized only through a versioned policy that rejects ambiguous values. A timezone is valid only when supplied by an authorized mapping or explicitly provided and validated. Upload time, file metadata, row order, and `harvest_business_date` cannot establish historical visibility.

`actual_harvest_quantity_kg` is an exact decimal in kilograms. Negative values reject. Explicit zero is valid and remains zero. A missing row or missing value does not become zero. Decimal parsing must reject non-finite values and avoid binary floating-point accumulation.

## 6. Source semantics attestation

The upload metadata must include a versioned and hashed attestation:

```text
physical_event=FARM_PICK
quantity_basis=OBSERVED_WEIGHT
quantity_unit=KG
missing_record_semantics=UNKNOWN_NOT_ZERO
```

Without the attestation, or when its declared event is receipt/arrival/processing/model/plan/inventory, the batch cannot pass validation or reach `COMMITTED`. The attestation is evidence about the source semantics, not an excuse to promote receipt data.

## 7. Identity and season mapping

Spreadsheet rows use exact business codes:

```text
farm_code
subfarm_or_plot_code
variety_code
season_code
```

The canonical target grain is `SEASON X FARM X SUBFARM_OR_PLOT X VARIETY X HARVEST_BUSINESS_DATE`. Exact mappings are versioned and hashed. Fuzzy matching, case folding without policy, name similarity, automatic identity creation, and latest/current fallback are forbidden. Unknown or ambiguous identity mapping is a row error and blocks full-batch commit.

When `season_code` is absent, only the formal deterministic season resolver may supply it. A filename, date year, receipt season, or spreadsheet sheet name is not season authority.

Each logical source record uses `logical_record_key = source_system + external_logical_record_id`. Each revision uses `revision_key = source_system + external_revision_id`. Initial revisions have `supersedes_external_revision_id = null`; later revisions point to the previous concrete revision in the same logical lineage. Revision numbers increase deterministically within a lineage. The spreadsheet contract rejects missing predecessors, multiple successors, cycles, multiple terminals, logical-record mismatch, and any import-order or latest-row winner shortcut.

The source-time contract is:

```text
source_recorded_at = originating source assertion
import_received_at = server-generated import acceptance time
ingested_at = server-generated immutable normalized-persistence time
```

Only `source_recorded_at_authority_status=TRUSTED_SOURCE_TIMESTAMP` permits `source_recorded_at <= label_observation_cutoff_at` for historical as-of replay. `USER_ASSERTED_UNVERIFIED`, `MISSING`, and `CONFLICTING` are not historical-as-of eligible. They may remain evidence for final adjudication only after separate final eligibility gates. Server receipt/persistence timestamps cannot masquerade as source visibility.

## 8. Validation, aggregation, and preview behavior

The canonical lifecycle is:

```text
RECEIVED
-> UPLOADING
-> SEALED
-> VALIDATING
-> VALIDATED
-> COMMITTING
-> COMMITTED
```

`PARSING` may be an internal spreadsheet transport status, but parse completion must enter `UPLOADING` before the server seal. `SEALED` is the only completeness boundary. The spreadsheet flow is `file accepted -> parse complete -> canonical rows created -> server record count calculated -> authoritative transport/raw/canonical hashes calculated -> SEALED -> validation`.

Validation starts only from `SEALED`; preview is read-only and cannot activate labels. Seal carries `expected_record_count_or_null`, `uploaded_record_count`, `sealed_record_count_or_null`, `sealed_at_or_null`, `sealed_by_identity_or_null`, `seal_status`, `server_raw_payload_hash_or_null`, `canonical_batch_hash_or_null`, and `seal_manifest_hash_or_null`. Client count/hash assertions are checked but never authoritative. After sealing, no record may be added, removed, replaced, reordered, or modified. Parse failures cannot create a partial sealed batch.

Validation must check required fields, exact types, dates, timezone, decimal values, semantic attestation, identity mappings, canonical grain, revision fields, seal manifest, and all batch hashes. Errors identify record index or source row where available, but reports must not include personal data or raw unrestricted rows. The validation result is bound to the seal manifest hash.

The v1 commit rule is full-batch atomic. Any invalid row blocks the complete batch. A committed batch is immutable; corrections create a new revision or batch.

Stable fail-closed errors include:

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

At the requested visibility cutoff, select one valid terminal revision per logical source record before grouping. Multiple different logical records may share the same canonical grain and must be summed with exact Decimal arithmetic. Same canonical grain is not a duplicate. The ordered contributing revisions use `source_system`, `external_logical_record_id`, and `external_revision_id`; the aggregation manifest records the ordered revision keys/hashes, count, exact decimal sum, visibility mode, cutoff, aggregation policy version, and aggregation manifest hash. CSV and XLSX produce equivalent manifests for equivalent canonical records. Row order must not affect the result.

## 9. Hash and idempotency surface

Spreadsheet transport metadata may include `source_file_name` and `source_file_hash`, but the source file name is not business identity. The canonical hashes are:

```text
source_file_hash_or_null
server_raw_payload_hash_or_null
canonical_batch_hash
canonical_record_hash
mapping_snapshot_hash
validation_result_hash
commit_manifest_hash
seal_manifest_hash_or_null
aggregation_manifest_hash
```

Hashes exclude database-generated IDs, temporary paths, hostnames, unordered iteration, and nondeterministic timestamps. Same canonical content must produce byte-identical normalized records regardless of CSV versus XLSX transport. Same idempotency key with different canonical content is a deterministic conflict.

## 10. Forbidden personal data and unsafe content

The canonical sheet must not contain picker names, phone numbers, employee IDs, identity-document numbers, or other unnecessary personal data. Free-text notes must not be used for identity, event semantics, revision winner selection, or hidden source payload. Macro/executable content is outside v1.

## 11. Future implementation slices

Future work may implement the spreadsheet portion under separate authorization:

| Slice | Scope | Not included |
|---|---|---|
| Q2A-I3 | CSV/XLSX parser, normalization, and contract-derived template | no persistence or API |
| Q2A-I5 | exact mapping and revision validation | no fuzzy resolution |
| Q2A-I6 | atomic commit and provenance | no partial commit |
| Q2A-I8 | tests, Goldens, and PostgreSQL acceptance | no Q2B or model change |

No slice is implementation-authorized by this design PR.

## 12. Acceptance gates

Future tests must prove CSV/XLSX canonical equivalence, header failures, formula/merged/hidden-row policy, date and decimal normalization, explicit zero, missing-day-not-zero, exact mapping, revision fail-closed, idempotency, immutable provenance, atomic commit, and concurrent commit behavior. This round does not add or execute tests.

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

- v1.0 — spreadsheet transport contract derived from the shared user-supplied actual-harvest import contract; implementation not authorized.
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
