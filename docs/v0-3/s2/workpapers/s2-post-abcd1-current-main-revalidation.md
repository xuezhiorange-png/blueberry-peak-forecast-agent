# V0.3-S2 current-main revalidation after A/B/C/D1 merge

## Artifact identity and exact current-main baseline

~~~text
ARTIFACT_ID=V0_3_S2_POST_ABCD1_CURRENT_MAIN_REVALIDATION
ARTIFACT_VERSION=s2-post-abcd1-current-main-revalidation-v1
TASK_ID=V03_S2_POST_D1_CURRENT_MAIN_REVALIDATION_R1
TASK_CLASS=DOCS_ONLY_GOVERNANCE_REVALIDATION
AUTHORIZATION_SCOPE=S2_CURRENT_MAIN_REVALIDATION_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUDITED_REPOSITORY_SHA=07986a31d4b80a90b1c292404f2940c15b669c19
AUDITED_REPOSITORY_TREE_SHA=524cddddbeb592b3dbae3412a029fea7f4e0ad5e
AUDITED_REF=origin/main
CONTRACT_ID=V0_3_S2_MATERIALIZED_DATASET_CONTRACT
CONTRACT_VERSION=v0-3-s2-materialized-dataset-contract-v1
AMENDMENT_VERSION=v0-3-s2-allowlist-migration-ownership-r2
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-post-abcd1-current-main-revalidation.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-post-abcd1-current-main-revalidation.json
EVIDENCE_JSON_SHA256=f72b8d315f6aadbb4b4d25f0a50f5172cd1a168952946db0f08668d19d89be68
UNIQUE_ALEMBIC_HEAD=8c6aead9f8e9
UNIQUE_ALEMBIC_HEAD_COUNT=1
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This is a read-only exact-head review of current `main` after Lane A, B, C,
and D1 entered the default branch. It observes implementation evidence. It
does not accept S2, freeze a real dataset, authorize D2, unseal SOURCE_002,
unseal TEST, or start S3.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
S1_AUTHORITY_MUTATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
SOURCE_002_READ_AUTHORIZED=false
SOURCE_002_RAW_READ_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=false
TEST_PARTITION_ACCESS_AUTHORIZED=false
D2_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_ISSUED=false
SLICE_S2_COMPLETE=false
~~~

## 1. What this review is and is not

This review answers one question: after four implementation merges, does
current `main` at `07986a3` satisfy contract §11 S2 acceptance?

The answer is **no**. Merged Draft-origin PRs, green or in-progress CI, and
the existence of allowlisted files are not S2 acceptance. Contract §11
requires exact-head implementation evidence, independent review, schema/hash
replay where relevant, and a current-main dependency check for every listed
item. This coordinator review supplies the independent review of the merged
code. It does not convert that review into acceptance.

~~~text
FOUR_LANE_PRS_MERGED=true
GREEN_CI_DOES_NOT_EQUAL_CONTRACT_PASS=true
DRAFT_DOES_NOT_EQUAL_READY=true
READY_DOES_NOT_EQUAL_MERGE=true
MERGE_DOES_NOT_EQUAL_S2_ACCEPTANCE=true
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
~~~

## 2. Exact-head merge ancestry

First-parent `origin/main` at the audited SHA:

| Order | PR | Merge commit | Title |
|---|---|---|---|
| 1 | [#277](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/277) | `fedc4ef9147747ee001fbfd44f60c3ee5dd4078c` | Lane A raw ingestion lineage |
| 2 | [#280](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/280) | `77d0f17f52d734c57becd118e1c6d695229b72c0` | Lane B cleaning / quality / ledgers |
| 3 | [#278](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/278) | `bd590e8a3f63d9b0f401b5d0bf119f74214ac4e8` | Lane C PIT / revision winner |
| 4 | [#279](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/279) | `07986a31d4b80a90b1c292404f2940c15b669c19` | Lane D1 materialized freeze logic |

Merge order on `main` is A → B → C → D1. That matches
`MIGRATION_INTEGRATION_ORDER=A->B->C->D`. D1 added no migration, so the
unique Alembic head remains Lane C.

## 3. Unique Alembic head

Alembic `ScriptDirectory.get_heads()` on the audited tree returns exactly
one head:

~~~text
HEAD=8c6aead9f8e9
HEAD_FILE=backend/alembic/versions/8c6aead9f8e9_s2_lane_c_pit_visibility_revision_winner.py
CHAIN=
  0028_quality_child_hash_scope
  -> 0029_s2_lane_a_raw_ingestion_lineage
  -> 2af278a20e2a
  -> 8c6aead9f8e9
LANE_D_MIGRATION_PRESENT=false
PARALLEL_HEADS=false
~~~

Tables created by the merged S2 migrations:

| Lane | Revision | Tables |
|---|---|---|
| A | `0029_s2_lane_a_raw_ingestion_lineage` | `s2_raw_source_artifact`, `s2_raw_import_batch`, `s2_source_row_lineage` |
| B | `2af278a20e2a` | `s2_cleaned_dataset_version`, `s2_cleaned_row`, `s2_quality_finding`, `s2_correction_ledger_entry`, `s2_exclusion_ledger_entry` |
| C | `8c6aead9f8e9` | `s2_pit_visibility_decision`, `s2_revision_winner_decision` |
| D1 | none | none |

Unique-head oracles on current `main` pin `8c6aead9f8e9`:

- `backend/tests/test_historical_backtest_alembic.py`
- `backend/tests/forecast_quality/test_persistence.py` (head oracles only; 0028 upgrade/downgrade around the 0028-as-intermediate tests is unchanged)
- `backend/tests/actual_harvest_import/alembic_cases.py` (`get_heads()` plus A→B→C chain)
- `backend/tests/s2_materialized_dataset/lane_c/conftest.py`

Lane B's live migration test now asserts B `revision` and `down_revision`
only. The unused helper
`assert_lane_b_alembic_head_and_revision_contract` in
`backend/tests/s2_materialized_dataset/lane_b/conftest.py` still claims
unique head `2af278a20e2a`. It is not called. That is a residual landmine,
not a current unique-head failure.

## 4. Package mode, allowlist, and shared seams

~~~text
S2_MATERIALIZED_DATASET_PACKAGE_MODE=PEP420_NAMESPACE
FORBIDDEN_NAMESPACE_INIT_1=backend/app/s2_materialized_dataset/__init__.py
FORBIDDEN_NAMESPACE_INIT_1_EXISTS=false
FORBIDDEN_NAMESPACE_INIT_2=backend/app/s2_materialized_dataset/shared/__init__.py
FORBIDDEN_NAMESPACE_INIT_2_EXISTS=false
~~~

Empty test-only package inits exist and remain authorized:

- `backend/tests/s2_materialized_dataset/__init__.py`
- `backend/tests/s2_materialized_dataset/shared/__init__.py`
- `backend/tests/s2_materialized_dataset/lane_d/__init__.py`

Lane D production allowlist versus the audited tree:

| Allowlisted path | On `main` | S2-wired |
|---|---|---|
| `lane_d/{__init__,builder,canonical,hashing,manifest,partitions,schemas}.py` | present | yes (in-package) |
| `shared/{contracts,registration}.py` | present | in-memory registration only |
| `lane_d/service.py` | **missing** | no |
| `api/materialized_datasets.py` | **missing** | no |
| Lane D migration | **missing** | no |
| Shared seams 1–5 and 7 (`db/base.py`, `models/__init__.py`, `main.py`, `api/__init__.py`, `repositories/__init__.py`, `actual_harvest_import/__init__.py`) | files exist | **no S2 import or registration** |

Seam 6 (`shared/contracts.py`) is present and is the in-package contract
module. It is not registered through application startup.

A/B/C production and test allowlisted paths that are not placeholders are
present. D1 did not create extra production modules outside the D allowlist
after folding `identity.py` / `materialize.py` / `quality.py` / `replay.py`
into the listed files.

## 5. Data-access seals

Production S2 code on this head does not read Source002 bytes. Cohort
identity strings and the inherited S1 manifest digest are bound as
constants.

~~~text
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_SHA256=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
S1_MANIFEST_DIGEST_MATCHES_INHERITED_CONTRACT=true
SOURCE_002_ROW_LEVEL_READ=false
TRAIN_ROW_ACCESS=false
VALIDATION_ROW_ACCESS=false
TEST_ROW_ACCESS=false
TEST_MATERIALIZATION_EXECUTED=false
METRIC_EXECUTION=false
BACKTEST_EXECUTED=false
MODEL_TRAINING_EXECUTED=false
~~~

Lane D TEST partition bytes are a synthetic control payload containing
`s2_test_partition_synthetic=true` and `row_count=0`. That preserves the
TEST seal. It is not an accepted TEST materialization.

## 6. Lane implementation evidence on this head

Local coordinator command on the audited tree:

~~~text
PYTHONPATH=. pytest backend/tests/s2_materialized_dataset -q
RESULT=105 passed
~~~

This is local exact-head evidence. It is not official CI and is not S2
acceptance.

GitHub CI observed at review time for `07986a3`:

| Merge | Run | Status at review time |
|---|---|---|
| A #277 | `32487245768` | success |
| B #280 | `32492732797` | success |
| C #278 | `32496963867` | in_progress |
| D #279 | `32497207605` | in_progress |

Green CI, if it later completes, still does not accept S2.

### Lane A — merged, implementation PASS for §4.1–4.3 code slice

Owns immutable source artifact, import batch, and source-row lineage
projections plus tables listed above. Tests cover identity, batch
idempotency, and source-row lineage. Non-blocking leftovers from the A
review remain: unused `SourceRowRevisionConflict` naming and batch
CONTENT_SHA256 scoped to ordered row-content hashes.

### Lane B — merged, implementation PASS for §4.4–4.8 code slice

Owns cleaned dataset version, cleaned rows, quality findings, and
correction/exclusion ledgers. Quantity columns are `NUMERIC`. Append-only
triggers exist. Tests cover `UNKNOWN_NOT_ZERO`, grain conflict fail-closed,
and contradictory exclusion fail-closed. Duplicate identical exclusion
events still fail as contradictory rather than dedupe; that remains
non-blocking for this revalidation.

### Lane C — merged, implementation PASS for §4.9–4.10 code slice

Owns PIT visibility and revision-winner decisions. Naive
`forecast_cutoff_at` is rejected (no UTC coercion). Cancelled-at-or-before
cutoff is not eligible. Duplicate `external_revision_id` fails closed.
Ordinary `source_revised_at > source_available_at` is allowed.

### Lane D1 — merged, freeze-logic PASS; persistence/API/seams NOT_PERFORMED

D1 implements deterministic TRAIN/VALIDATION/TEST partition specs from S1
split authority, canonical NDJSON bytes, content/manifest/identity hashes,
quality-gate evaluation (lineage + replay + frozen boundaries + cohort
digest), and fail-closed build when upstream lineage is incomplete.

D1 does **not** implement D persistence, D API, D migration, or shared-seam
registration. Builds consume `FakeLaneA` / `FakeLaneB` / `FakeLaneC`, not
persisted A/B/C outputs.

`rebuild_partition_bytes` is an alias of `materialize_partition_bytes`.
Replay therefore calls the same function twice in one process. That is
deterministic same-function parity, not an independent rebuild from stored
versioned inputs.

`QualityGateStatus.ACCEPTED` in D1 is a builder-internal gate. It is not
`QUALITY_REPORT_ACCEPTED` and not S2 acceptance.

`MaterializableRow.actual_harvest_quantity_kg` is a required `Decimal`.
Unknown days must remain absent from materializable rows. They must not
later be coerced to zero when D is wired to B.

## 7. Contract §11 scoring

Each row is scored on this exact head. `IMPLEMENTATION_EVIDENCE` means
merged code and tests exist. `ACCEPTED` remains false for every item.

| §11 item | Implementation evidence | Independent review of that evidence | Official freeze artifact | ACCEPTED |
|---|---|---|---|---|
| IMMUTABLE_RAW_REFERENCE_ACCEPTED | A tables + identity tests | this review | no SOURCE_002 raw ref freeze | **false** |
| SOURCE_ROW_LINEAGE_ACCEPTED | A lineage table + tests | this review | synthetic only | **false** |
| CLEANED_DATA_MANIFEST_ACCEPTED | B cleaned version + hashes | this review | synthetic only | **false** |
| QUALITY_REPORT_ACCEPTED | B findings + hashes | this review | no official quality report | **false** |
| CORRECTION_LEDGER_ACCEPTED | B correction ledger + tests | this review | synthetic only | **false** |
| EXCLUSION_LEDGER_ACCEPTED | B exclusion ledger + tests | this review | synthetic only | **false** |
| TIME_VISIBILITY_REPORT_ACCEPTED | C PIT/winner tables + tests | this review | synthetic only | **false** |
| TRAIN_MATERIALIZED_MANIFEST_ACCEPTED | D1 builder + tests | this review | fake upstream, not persisted | **false** |
| VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED | D1 builder + tests | this review | fake upstream, not persisted | **false** |
| TEST_MATERIALIZED_MANIFEST_ACCEPTED | synthetic placeholder, row_count=0 | this review | TEST still sealed | **false** |
| FINAL_SPLIT_MANIFEST_ACCEPTED | S1 ranges hardcoded in D1 | this review | no official split freeze record | **false** |
| FINAL_DATASET_HASHES_ACCEPTED | hash functions + in-test digests | this review | no published hash set | **false** |
| DETERMINISTIC_REBUILD_PARITY_ACCEPTED | same-function replay in tests | this review | not independent stored-input replay | **false** |

~~~text
REQUIRED_FINAL_S2_ACCEPTANCE=ALL_OF_THE_FOLLOWING
S2_ACCEPTANCE_ITEMS_TRUE_COUNT=0
S2_ACCEPTANCE_ITEMS_FALSE_COUNT=13
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
V0_3_S3_AUTHORIZED=false
~~~

## 8. Development-plan gates observed, not mutated

`docs/v0-3/development-plan.md` still records these rows as `BLOCKED` /
`NOT_YET_EXECUTED` / `PENDING_INDEPENDENT_REVIEW`. This revalidation does
not change that file.

Observed against current `main`, not written back:

| Gate | Observed now | Still required for S2 complete |
|---|---|---|
| `SLICE_S2_COMPLETE` | not satisfied | yes |
| `MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE` | D1 logic only; no freeze record | yes |
| `MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED` | S1 ranges in code; no accepted manifest | yes |
| `MODEL_FINAL_DATASET_HASHES_ACCEPTED` | no published hash package | yes |
| `TECH_UNIQUE_ALEMBIC_HEAD` | unique head `8c6aead9f8e9` observed | still a later release gate |

`MATERIALIZED_DATASET_FREEZE_COMPLETE` is **not** true. Freeze machinery
exists. A frozen real or governed dataset identity does not.

## 9. Residuals that do not block this revalidation

- Unused Lane B unique-head helper still pins `2af278a20e2a`.
- Identical duplicate exclusion events fail as contradictory rather than
  dedupe.
- Lane C persist path can store naive timestamps on the blocked
  `NAIVE_TIMESTAMP` path.
- D1 `rebuild_partition_bytes` is not a second builder.
- D `MaterializableRow` requires `Decimal` quantity; unknown-day wiring is
  not yet an integration contract.
- C/D merge CI was still in progress at review time.

## 10. Verdict

~~~text
CURRENT_MAIN_REVALIDATION_STATUS=PASS
LANE_A_IMPLEMENTATION_ON_MAIN=PASS
LANE_B_IMPLEMENTATION_ON_MAIN=PASS
LANE_C_IMPLEMENTATION_ON_MAIN=PASS
LANE_D1_FREEZE_LOGIC_ON_MAIN=PASS
LANE_D_PERSISTENCE_API_SEAMS=NOT_PERFORMED
PEP420_NAMESPACE=PASS
UNIQUE_ALEMBIC_HEAD=PASS
SOURCE_002_SEAL=HOLD
TEST_SEAL=HOLD
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
FINAL_SPLIT_MANIFEST_ACCEPTED=false
FINAL_DATASET_HASHES_ACCEPTED=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
D2_AUTHORIZED=false
NEXT_SLICE_STARTED=false
~~~

Current `main` is an integrated A/B/C/D1 implementation head. It is not an
accepted S2 freeze.

## 11. Recommended next authorization

Do not start S3. Do not unseal SOURCE_002. Do not treat D1 synthetic
`QualityGateStatus.ACCEPTED` as a freeze record.

The remaining S2 implementation gap on this head is **D2**, still inside S2:

1. Lane D migration (`down_revision=8c6aead9f8e9`).
2. `backend/app/s2_materialized_dataset/lane_d/service.py`.
3. `backend/app/api/materialized_datasets.py`.
4. Shared-seam registration by Lane D only.
5. Persist and replay from stored A/B/C outputs using synthetic ports or
   synthetic fixtures. Still no SOURCE_002 read. Still no TEST row access.
   Still no S3.

After D2, a later explicit authorization is still required before controlled
real-data materialization. Only after an official freeze record with
TRAIN/VALIDATION/TEST hashes and independent review can §11 items be scored
true. S3 remains a separate authorization after that.

This document does not authorize D2. It only records that D2 is the next
legal implementation slice if more S2 code is authorized.
