# Q2A Import Validation, Revision, and Commit Contract

Status: docs-only design draft under Issue #102 comment `4976761806`.

## 1. Scope

This document freezes validation, identity mapping, revision lineage, point-in-time visibility, hash, and atomic commit semantics for the common user-supplied actual-harvest staging model. It does not implement validation, persistence, migration, snapshot building, API, parser, tests, or a backtest runner.

The primary actual-harvest label remains unavailable until a future import passes this contract. Model outputs and factory receipt/arrival remain non-primary.

## 2. Authority alignment

The contract reuses:

- `docs/forecast-quality/q2a-user-supplied-actual-harvest-import-contract.md` for canonical batch/record fields and lifecycle.
- `docs/forecast-quality/q2a-label-snapshot-and-revision-contract.md` for the four-time model and unique terminal revision rule.
- `docs/forecast-quality/q2a-actual-harvest-source-contract.md` for farm-pick semantics and proxy prohibition.
- `docs/forecast-quality/q2a-data-coverage-audit.md` for the current absence of a production actual-harvest source.
- `docs/forecast-quality/q2a-prediction-label-alignment-decision.md` for independent evaluation alignment and P50/P80/P90 prediction quantiles.
- `docs/forecast-quality/slice-q1-data-coverage-audit.md` for Q1 schema and cutoff facts.

## 3. Validation stages

Validation is deterministic and ordered:

```text
transport_parse
-> canonical_field_validation
-> source_semantics_validation
-> quantity_and_date_validation
-> exact_identity_mapping
-> canonical_grain_validation
-> revision_lineage_validation
-> point_in_time_metadata_validation
-> hash_and_idempotency_validation
-> batch_result_validation
```

The first failure is not the only failure: the batch may report all deterministic row errors, but no error may be silently dropped. Preview is read-only. `VALIDATED` requires zero invalid rows and a matching validation result hash.

## 4. Stable error model

Every error has:

```text
error_code
severity
import_id
record_index_or_null
external_record_id_or_null
field_path_or_null
message_template_id
details
```

Required codes:

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
REVISION_LINEAGE_CYCLE
MULTIPLE_TERMINAL_REVISIONS
INVALID_RECORD_STATUS
SOURCE_SEMANTICS_ATTESTATION_MISSING
SOURCE_SEMANTICS_NOT_FARM_PICK
BATCH_NOT_VALIDATED
BATCH_ALREADY_COMMITTED
CANONICAL_HASH_MISMATCH
```

Error details are structured, deterministic, and sanitized. They do not contain raw rows, stack traces, personal data, credentials, or private URLs.

## 5. Semantic validation

The batch attestation must be present, versioned, and hash-bound:

```text
physical_event=FARM_PICK
quantity_basis=OBSERVED_WEIGHT
quantity_unit=KG
missing_record_semantics=UNKNOWN_NOT_ZERO
```

Validation rejects a source declared as factory receipt, arrival, processing input, model output, plan, capacity, inventory, backlog, estimated yield, or fixture. Field names cannot establish semantics. `actual_harvest_quantity_kg` is exact decimal KG; negative rejects, explicit zero is allowed, and missing rows are not zero.

## 6. Exact identity mapping

Mapping must resolve the target grain:

```text
SEASON
X FARM
X SUBFARM_OR_PLOT
X VARIETY
X HARVEST_BUSINESS_DATE
```

The input uses exact business codes and a versioned mapping snapshot:

```text
farm_code -> internal farm identity
subfarm_or_plot_code -> internal subfarm/plot identity
variety_code -> internal variety identity
season_code -> internal season identity
```

Mapping is exact and case-sensitive unless a separately versioned policy says otherwise. Unknown or ambiguous mappings reject. No fuzzy matching, automatic creation, filename mapping, insertion order, latest/current fallback, or date-year derivation is allowed. A missing `season_code` may be resolved only through the formal deterministic season resolver.

The mapping snapshot and its hash are part of the validation and commit evidence. The mapping result cannot change between `VALIDATED` and `COMMITTED`.

## 7. Revision lineage

The status vocabulary and semantics are:

```text
ACTIVE     = current non-final terminal record
CORRECTED  = superseded historical revision; never a winner
VOID       = invalidated record; never a winner
FINALIZED  = final terminal record
```

Each source record identity is scoped by source system and external record identity. Revisions use monotonically declared `revision_number` and `supersedes_external_record_id`. The winner is the unique visible terminal node on one valid explicit chain, or the unique finalized terminal for final adjudication. Import order and largest/latest shortcuts are forbidden.

Fail closed on:

```text
duplicate revision_number
missing predecessor
multiple successors
revision cycle
multiple visible terminals
multiple finalized terminals
unknown status
corrected record without successor
void record selected as winner
same identity and revision with different payload
revision number discontinuity
```

The original source payload, normalized record, revision links, and validation evidence are immutable. A correction is an append-only new revision or batch.

## 8. Point-in-time visibility

The four-time contract is:

```text
forecast_cutoff_at
< forecast_target_date_or_window_end
<= label_observation_cutoff_at
<= replay_executed_at
```

An as-of snapshot may see only records with `recorded_at <= label_observation_cutoff_at` and a valid visible lineage. `revised_at` and `finalized_at` provide additional evidence when present; they never override the visibility cutoff. Future corrections must not leak into historical backtests. A missing date is never generated or treated as zero.

If the source lacks `recorded_at`, revision identity, or terminal status, the import may remain staging evidence but cannot produce an evaluation-ready primary label snapshot.

## 9. Hashes, idempotency, and commit manifest

The contract preserves:

```text
idempotency_key
external_batch_id
raw_payload_hash
canonical_batch_hash
canonical_record_hash
mapping_snapshot_hash
validation_result_hash
commit_manifest_hash
source_file_hash_or_null
source_semantics_attestation_hash
```

Same key and same canonical payload returns the original result. Same key with different payload is a deterministic conflict. Same external record/revision and payload is an idempotent duplicate; same identity/revision with different payload is a conflict.

Canonical hashes exclude database-generated IDs, temporary paths, runtime hosts, unordered mapping iteration, and nondeterministic timestamps. They include every business field and validation/mapping result that can affect commit semantics.

## 10. Full-batch atomic commit

The state transition is:

```text
RECEIVED
-> PARSING
-> VALIDATING
-> VALIDATED
-> COMMITTING
-> COMMITTED
```

Parse or validation failures use the corresponding failure status. Commit is allowed only from `VALIDATED`, with matching input, mapping, validation, and source hashes. v1 is full-batch atomic: any invalid row or concurrency conflict prevents all rows in the batch from becoming effective. Partial commit is forbidden. A failed commit must be safely retryable or fail without partial activation.

The commit manifest records the immutable source batch, normalized records, validation result, mapping snapshot, revision lineage, source artifact/file hashes, and committed record set. `COMMITTED` does not itself mean that an evaluation snapshot has been built.

## 11. Label snapshot boundary

```text
staging record != primary label snapshot
```

The evaluation label snapshot is derived only from committed, valid, visible terminal revisions. It must preserve the cutoff and replay evidence. It must not overwrite source history, delete revisions, use receipt as a fallback, or add missing dates as zero. Prediction-side P50/P80/P90 output remains separate from the point-observation label.

## 12. Concurrency and future acceptance tests

Future implementation must test:

- exact replay and repeated identical import;
- idempotency key conflict;
- duplicate external record and revision conflict;
- correction, void, finalized record, broken lineage, cycles, and multiple terminals;
- unknown and ambiguous identity mapping;
- API/spreadsheet canonical equivalence;
- missing day remains unknown and explicit zero remains zero;
- historical cutoff excludes future revisions;
- PostgreSQL concurrent commit race with no partial batch.

No tests are added by this design-only round.

## 13. Future implementation decomposition

| Slice | Future scope | Explicit exclusion |
|---|---|---|
| Q2A-I1 | schemas, enums, validation errors | no persistence |
| Q2A-I2 | staging persistence and migration | no backtest runner |
| Q2A-I5 | exact mapping and lineage validation | no fuzzy matching |
| Q2A-I6 | atomic commit and provenance | no partial commit |
| Q2A-I7 | cutoff-bound label snapshot | no model change |
| Q2A-I8 | integration tests and PostgreSQL acceptance | no Q2B |

All future slices require separate authorization.

## 14. Change log

- v1.0 — validation, revision, point-in-time, and atomic commit contract derived from the shared user-supplied import design; implementation not authorized.

## §X.1 Q2A import contract status

```text
ISSUE102_AUTHORIZATION_COMMENT_ID=4976761806
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
