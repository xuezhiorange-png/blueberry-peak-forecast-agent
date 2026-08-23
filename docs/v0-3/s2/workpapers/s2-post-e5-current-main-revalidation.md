# V0.3-S2 current-main revalidation after E5 merge

## Artifact identity and exact current-main baseline

~~~text
ARTIFACT_ID=V0_3_S2_POST_E5_CURRENT_MAIN_REVALIDATION
ARTIFACT_VERSION=s2-post-e5-current-main-revalidation-v1
TASK_ID=V03_S2_POST_E5_CURRENT_MAIN_REVALIDATION_R1
TASK_CLASS=DOCS_ONLY_GOVERNANCE_REVALIDATION
AUTHORIZATION_SCOPE=S2_CURRENT_MAIN_REVALIDATION_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUDITED_REPOSITORY_SHA=0529043be60990c166f61c7a89fc3eb8befbebbe
AUDITED_REPOSITORY_TREE_SHA=b596a45eaa8c21d923321c136403b104da756f07
AUDITED_REF=origin/main
PREVIOUS_AUDITED_REPOSITORY_SHA=482cc93e1def598744dba2eae75f869c3d5dbc4f
PREVIOUS_ARTIFACT_VERSION=s2-post-d2-current-main-revalidation-v1
PREVIOUS_REVALIDATION_PR=283
PREVIOUS_REVALIDATION_PR_STATE=MERGED_SUPERSEDED_FOR_CURRENT_MAIN_FACTS
CONTRACT_ID=V0_3_S2_MATERIALIZED_DATASET_CONTRACT
CONTRACT_VERSION=v0-3-s2-materialized-dataset-contract-v1
AMENDMENT_VERSION=v0-3-s2-allowlist-migration-ownership-r2
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-post-e5-current-main-revalidation.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-post-e5-current-main-revalidation.json
EVIDENCE_JSON_SHA256=b7b1f179d43d2add510090acf7f65d45c391ffee9aaaf04701d137595a43e2e1
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This is a read-only exact-head review of current `main` after Lane A/B/C/D1/D2,
SOURCE_002 controlled-materialization docs, E1–E5 implementation merges, and
Lane C E4b SQL persist entered the default branch. It observes implementation
evidence. It does not accept S2, freeze a real dataset, unseal SOURCE_002 for
evaluation, unseal TEST, start S3, or mutate the frozen contract or
development-plan gate registry.

Draft PR [#281](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/281)
and merged post-D2 revalidation [#283](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/283)
are **stale for current-main facts** after E5 merge `0529043`. This artifact
supersedes `s2-post-d2-current-main-revalidation-v1` for the audited SHA below.
Do not treat #281 as current-main authority.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
S1_AUTHORITY_MUTATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_PARTITION_ACCESS_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_ISSUED=false
SLICE_S2_COMPLETE=false
~~~

## 1. What this review is and is not

This review answers one question: after the merged implementation slices through
E5, does current `main` at `0529043` satisfy contract §11 S2 acceptance?

The answer is **no**. Merged code slices, green CI on the E5 branch, filled
allowlists, and a wired controlled-SQL E5 path are not S2 acceptance. Contract
§11 requires exact-head implementation evidence, review, schema/hash replay
where relevant, and a current-main dependency check for every listed item bound
to a frozen live object with published hashes. This coordinator review supplies
the waived-third-party review of the merged code. It does not convert that
review into acceptance.

~~~text
FOURTEEN_IMPLEMENTATION_AND_DOCS_SLICES_MERGED=true
GREEN_CI_DOES_NOT_EQUAL_CONTRACT_PASS=true
DRAFT_DOES_NOT_EQUAL_READY=true
READY_DOES_NOT_EQUAL_MERGE=true
MERGE_DOES_NOT_EQUAL_S2_ACCEPTANCE=true
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
S1_REOPENED=false
~~~

S1 remains accepted and is not reopened. Product 0.2.0 ENGINEERING_TRIAL is
done. Current product stage remains V0.3 BUSINESS_PILOT. S3–S6 are not
started and are not authorized.

## 2. Exact-head merge ancestry

First-parent `origin/main` at the audited SHA. Listed slices are **code or docs
implementation evidence**, not S2 acceptance.

| Order | PR | Merge commit | Slice |
|---|---|---|---|
| 1 | [#277](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/277) | `fedc4ef9147747ee001fbfd44f60c3ee5dd4078c` | Lane A lineage |
| 2 | [#280](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/280) | `77d0f17f52d734c57becd118e1c6d695229b72c0` | Lane B cleaning / quality / ledgers |
| 3 | [#278](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/278) | `bd590e8a3f63d9b0f401b5d0bf119f74214ac4e8` | Lane C PIT / revision winner |
| 4 | [#279](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/279) | `07986a31d4b80a90b1c292404f2940c15b669c19` | Lane D1 materialized freeze logic |
| 5 | [#282](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/282) | `482cc93e1def598744dba2eae75f869c3d5dbc4f` | Lane D2 persist / storage rebuild / API / seams |
| 6 | [#283](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/283) | `496631e2e42142f45683159cf32545386b61ace7` | Post-D2 governance revalidation docs |
| 7 | [#284](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/284) | `b2cbe1d6f1d521127a3edfd443ea7f265acb08a1` | SOURCE_002 controlled materialization authorization |
| 8 | [#285](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/285) | `923c309b7242be02d4bf974f49bcdcd4b7cda444` | Lane A E1/E2 identity + ingest |
| 9 | [#286](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/286) | `06223aee270aec983cd7166545b584b67aae506d` | Lane B E3 cleaning from persisted A |
| 10 | [#287](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/287) | `25e94c369e1695e4a575809999df8af8612005b3` | Canonical-grain kg-sum ledger policy docs |
| 11 | [#288](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/288) | `2101acf9350f7ca170cabadbd2dc18d65cf3c3d2` | Lane C E4 IDFL revision-winner resolve |
| 12 | [#289](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/289) | `741dbde960097ed4606d7d997d898d76baf7f61d` | IDFL label-side winner SQL schema docs |
| 13 | [#290](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/290) | `3f24a25373dbdbe70b262d79b1be545f10a1e0e6` | Lane C E4b IDFL winner SQL persist |
| 14 | [#291](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/pull/291) | `0529043be60990c166f61c7a89fc3eb8befbebbe` | Lane D E5 SOURCE_002 controlled SQL materialization |

E5 (#291) added **no new Alembic revision**. Lane C E4b (#290) added the current
unique head `a7c3e9f1b2d4`.

## 3. Unique Alembic head

~~~text
HEAD=a7c3e9f1b2d4
HEAD_FILE=backend/alembic/versions/a7c3e9f1b2d4_s2_lane_c_idfl_label_side_winner.py
DOWN_REVISION=d4e8f1a2b3c5
CHAIN=
  0028_quality_child_hash_scope
  -> 0029_s2_lane_a_raw_ingestion_lineage
  -> 2af278a20e2a
  -> 8c6aead9f8e9
  -> d4e8f1a2b3c5
  -> a7c3e9f1b2d4
E5_NEW_MIGRATION=false
PARALLEL_HEADS=false
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
~~~

Tables created by merged S2 migrations:

| Lane | Revision | Tables |
|---|---|---|
| A | `0029_s2_lane_a_raw_ingestion_lineage` | `s2_raw_source_artifact`, `s2_raw_import_batch`, `s2_source_row_lineage` |
| B | `2af278a20e2a` | `s2_cleaned_dataset_version`, `s2_cleaned_row`, `s2_quality_finding`, `s2_correction_ledger_entry`, `s2_exclusion_ledger_entry` |
| C | `8c6aead9f8e9` | `s2_pit_visibility_decision`, `s2_revision_winner_decision` |
| C E4b | `a7c3e9f1b2d4` | `s2_idfl_label_side_winner_decision` |
| D | `d4e8f1a2b3c5` | `s2_materialized_dataset`, `s2_materialized_materializable_row`, `s2_materialized_partition` |

Unique-head oracles on current `main` pin `a7c3e9f1b2d4` in
`backend/tests/test_historical_backtest_alembic.py`,
`backend/tests/forecast_quality/test_persistence.py` (head oracles only; the
0028 upgrade/downgrade around 0028-as-intermediate tests is unchanged),
`backend/tests/actual_harvest_import/alembic_cases.py`,
`backend/tests/s2_materialized_dataset/lane_b/conftest.py`,
`backend/tests/s2_materialized_dataset/lane_c/conftest.py`, and
`backend/tests/s2_materialized_dataset/lane_d/conftest.py`.

## 4. Package mode, allowlist, and shared seams

~~~text
S2_MATERIALIZED_DATASET_PACKAGE_MODE=PEP420_NAMESPACE
FORBIDDEN_NAMESPACE_INIT_1=backend/app/s2_materialized_dataset/__init__.py
FORBIDDEN_NAMESPACE_INIT_1_EXISTS=false
FORBIDDEN_NAMESPACE_INIT_2=backend/app/s2_materialized_dataset/shared/__init__.py
FORBIDDEN_NAMESPACE_INIT_2_EXISTS=false
LANE_D_PRODUCTION_ALLOWLIST_PRESENT=17/17
LANE_D_ALLOWLIST_GAPS=()
~~~

Empty test-only package inits remain authorized under
`backend/tests/s2_materialized_dataset/`. No forbidden production namespace
inits were created.

E5 extended only allowlisted Lane D paths (`lane_d/service.py`,
`shared/contracts.py`, repository lazy exports, and Lane D tests). It did not
add a Lane D migration file.

## 5. Frozen counting semantics (do not mix)

~~~text
DECLARED_SOURCE_ROW_COUNT=233171
E2_EXACT_REPLAY=233171
JULY_OPTION_A_EXCLUDED_SOURCE_ROW_COUNT=2
SOURCE_ROWS_IN_SCOPE=233169
ROW_COUNT_RECONCILIATION=233171=233169+2
E3_UNIQUE_CANONICAL_GRAINS=33894
E4_E4B_IDFL_SQL_ROW_COUNT=233171
PIT_SQL_ROW_COUNT=0
OLD_REVISION_WINNER_SQL_ROW_COUNT=0
TEST_PERSISTED_ROW_COUNT=0
SOURCE_002_ROW_LEVEL_READ=false
~~~

Semantics:

- `233171` is the declared / E2 exact-replay source-row count and includes the
  two July Option A lineage rows. Do not call `233171` “产季内”.
- `SOURCE_ROWS_IN_SCOPE=233169` is the in-cohort count (`233171 - 2`).
- `E3_UNIQUE_CANONICAL_GRAINS=33894` is a **grain** count after kg-sum collapse,
  not Lane C winner row count.
- E4/E4b IDFL SQL target and observed boundary oracle is `233171` rows in
  `s2_idfl_label_side_winner_decision`. PIT SQL and legacy revision-winner SQL
  must remain `0` for SOURCE_002.
- TEST persisted `row_count` remains `0`. TEST-window grains must not enter D
  materializable row tables.

## 6. Live object and coordinator environment

Production S2 code binds SOURCE_002 identity constants. This review does **not**
claim a frozen `dataset_identity` on a live object.

Coordinator scan of this recording environment, by size `28668416` and SHA-256
`fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` only:

~~~text
THIS_ENVIRONMENT_SOURCE_002_OBJECT_PRESENT=false
TARGET_SIZE_MATCH_COUNT=0
TARGET_SHA_MATCH_COUNT=0
SOURCE_002_BYTES_READ=false
SOURCE_002_ROW_LEVEL_READ_EXECUTED=false
E5_LIVE_REPORT_STATUS=OBJECT_MISSING
TRAIN_ROWS=NOT_MEASURED
VAL_ROWS=NOT_MEASURED
DATASET_IDENTITY=NOT_MEASURED
REBUILD_PARITY_ON_LIVE_OBJECT=NOT_MEASURED
PLAINTEXT_LOCATOR_RECORDED=false
~~~

`controlled_materialize_source_002_from_environment` on this head returns
`rebuild_parity=OBJECT_MISSING` when the frozen object is absent. No live
`SOURCE_002_E5_REPORT` with measured `train_rows`, `val_rows`, or
`dataset_identity` was produced on this recording head.

`data/raw/2024_2025_receipts.xls`, `data/raw/2025_2026_receipts.xls`, and
Google Sheets xlsx exports are **not** Source002. They must not be substituted.

## 7. Lane implementation evidence on this head

Local coordinator pytest was **not executed** on this recording environment
(`pytest` unavailable). GitHub CI on PR #291 branch head reported success for
static, unit-contract-golden, postgres-*, compose-smoke, and frontend jobs at
review time. Main merge canary `32611467632` was still `in_progress` when this
paper was recorded. Green CI is not S2 acceptance.

### Lanes A/B/C/D1/D2 — merged code slices (unchanged verdict from post-D2)

Implementation PASS for contract §4.1–§4.10 and §7.6 D machinery as code
slices. Residuals from post-D2 remain observed (Fake-port unit tests, GET-only
API, `rebuild_partition_bytes` alias, hash-only storage rebuild compare, etc.).

### SOURCE_002 path — merged code slices (new since post-D2)

| Step | PR | Implementation evidence on `0529043` | Acceptance |
|---|---|---|---|
| Authorization | #284 | controlled materialization grant docs | docs only |
| E1/E2 | #285 | Lane A identity verification + ingest gate | code slice PASS |
| E3 | #286 | Lane B cleaning from persisted A with kg-sum policy | code slice PASS |
| kg-sum policy | #287 | ledger policy docs | docs only |
| E4 | #288 | Lane C IDFL resolve in memory | code slice PASS |
| IDFL schema | #289 | SQL schema / ledger grant docs | docs only |
| E4b | #290 | `s2_idfl_label_side_winner_decision` migration + persist | code slice PASS |
| E5 | #291 | Lane D `build_source_002_upstream_bundle_from_sql`, boundary oracles, controlled materialize | code slice PASS |

E5 consumes persisted SQL from Lane A lineage, Lane B cleaned rows, and Lane C
`s2_idfl_label_side_winner_decision`. It does not require rows in
`s2_pit_visibility_decision` or `s2_revision_winner_decision` for SOURCE_002.
`SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED=true` in
`shared/contracts.py`. Synthetic Fake-port unit tests may remain for non-SOURCE_002
coverage.

## 8. Contract §11 scoring

Each row is scored on this exact head. `IMPLEMENTATION_EVIDENCE` means merged
code and tests exist. `ACCEPTED` remains **false** for every item because no
frozen live object on `0529043` carries published hashes, official freeze
records, or rebuild PASS bound to a governed dataset identity.

| §11 item | Implementation evidence | Independent review of that evidence | Official freeze artifact | ACCEPTED |
|---|---|---|---|---|
| IMMUTABLE_RAW_REFERENCE_ACCEPTED | A tables + E1/E2 SOURCE_002 path | this review | no live-object freeze on `0529043` | **false** |
| SOURCE_ROW_LINEAGE_ACCEPTED | A lineage + E2 replay machinery | this review | OBJECT_MISSING on recording env | **false** |
| CLEANED_DATA_MANIFEST_ACCEPTED | B cleaned version + E3 machinery | this review | no published freeze manifest | **false** |
| QUALITY_REPORT_ACCEPTED | B findings + hashes | this review | no official quality report | **false** |
| CORRECTION_LEDGER_ACCEPTED | B correction ledger + tests | this review | no published freeze record | **false** |
| EXCLUSION_LEDGER_ACCEPTED | B exclusion ledger + July Option A path | this review | no published freeze record | **false** |
| TIME_VISIBILITY_REPORT_ACCEPTED | C PIT/winner/IDFL tables + E4/E4b | this review | PIT SQL=0 by design; no published report | **false** |
| TRAIN_MATERIALIZED_MANIFEST_ACCEPTED | D1/D2/E5 builder + persist | this review | train_rows NOT_MEASURED live | **false** |
| VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED | D1/D2/E5 builder + persist | this review | val_rows NOT_MEASURED live | **false** |
| TEST_MATERIALIZED_MANIFEST_ACCEPTED | synthetic placeholder `row_count=0` | this review | TEST still sealed | **false** |
| FINAL_SPLIT_MANIFEST_ACCEPTED | S1 ranges hardcoded in D | this review | no official S2 split freeze record | **false** |
| FINAL_DATASET_HASHES_ACCEPTED | hash functions + in-test digests | this review | dataset_identity NOT_MEASURED live | **false** |
| DETERMINISTIC_REBUILD_PARITY_ACCEPTED | D2/D5 storage rebuild machinery | this review | rebuild_parity NOT_MEASURED on live object | **false** |

~~~text
REQUIRED_FINAL_S2_ACCEPTANCE=ALL_OF_THE_FOLLOWING
S2_ACCEPTANCE_ITEMS_TRUE_COUNT=0
S2_ACCEPTANCE_ITEMS_FALSE_COUNT=13
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
FINAL_SPLIT_MANIFEST_ACCEPTED=false
FINAL_DATASET_HASHES_ACCEPTED=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
~~~

## 9. Development-plan gates observed, not mutated

`docs/v0-3/development-plan.md` gate rows are **not** edited by this task.
Observed against current `main`, not written back:

| Gate | Observed now | Still required for S2 complete |
|---|---|---|
| `SLICE_S2_COMPLETE` | not satisfied | yes |
| `MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE` | E5 machinery exists; no live freeze | yes |
| `MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED` | S1 ranges in code; no accepted S2 manifest | yes |
| `MODEL_FINAL_DATASET_HASHES_ACCEPTED` | no published hash package on live object | yes |
| `TECH_UNIQUE_ALEMBIC_HEAD` | unique head `a7c3e9f1b2d4` observed | still a later release gate |

## 10. Residuals that do not block this revalidation

- Frozen Source002 object absent on coordinator recording environment.
- No live `dataset_identity`, `train_rows`, or `val_rows` measured on `0529043`.
- E5 live report path returns `OBJECT_MISSING` without governed bytes.
- TEST partition remains `row_count=0` with synthetic placeholder bytes.
- Fake-port unit tests remain alongside the SOURCE_002 SQL path.
- GET-only API; no POST materialize route.
- `rebuild_partition_bytes` remains an alias of `materialize_partition_bytes`.
- Main merge canary was in progress at review time.

## 11. Verdict

~~~text
CURRENT_MAIN_REVALIDATION_STATUS=PASS
LANE_ABCD_IMPLEMENTATION_ON_MAIN=PASS
SOURCE_002_E1_E5_IMPLEMENTATION_ON_MAIN=PASS
PEP420_NAMESPACE=PASS
UNIQUE_ALEMBIC_HEAD=PASS
SOURCE_002_OBJECT_ON_RECORDING_ENV=OBJECT_MISSING
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
NEXT_SLICE_STARTED=false
~~~

Current `main` is an integrated A/B/C/D plus SOURCE_002 E1–E5 implementation
head. It is **not** an accepted S2 freeze.

This document does not authorize S3, Ready-as-acceptance, Merge-as-acceptance,
TEST evaluation, or contract / development-plan mutation. It only records the
post-E5 exact-head facts.
