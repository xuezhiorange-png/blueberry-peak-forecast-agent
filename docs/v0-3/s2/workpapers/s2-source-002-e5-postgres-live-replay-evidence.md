# V0.3-S2 SOURCE_002 E5 Postgres live replay evidence (Lane C operator)

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_E5_POSTGRES_LIVE_REPLAY_EVIDENCE
ARTIFACT_VERSION=s2-source-002-e5-postgres-live-replay-evidence-v1
TASK_ID=V03_S2_SOURCE_002_E5_POSTGRES_LIVE_REPLAY_EVIDENCE_R1
TASK_CLASS=DOCS_ONLY_LIVE_REPLAY_EVIDENCE
AUTHORIZATION_SCOPE=S2_SOURCE_002_E5_POSTGRES_LIVE_REPLAY_EVIDENCE_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUDITED_REPOSITORY_SHA=b315f6e4c30eccac6e5156ade24068ceaaadb647
AUDITED_REPOSITORY_TREE_SHA=f7471111fc8bbf0bffd3c1318714b47d840b9995
AUDITED_REF=origin/main
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
AMENDMENT_VERSION=v0-3-s2-allowlist-migration-ownership-r2
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-e5-postgres-live-replay-evidence.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-source-002-e5-postgres-live-replay-evidence.json
EVIDENCE_JSON_SHA256=07544e1fd9ded3294e649fc98cd41549d26b7364bc55887c7228ffc98b5134bf
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This document records one completed SOURCE_002 E5 live replay executed by Lane
C on Postgres at the audited `main` head. It binds the verbatim operator report
below. It does not accept S2, freeze an official dataset, start S3, or mutate
the frozen contract or development-plan gate registry.

Prior SQLite live replay evidence remains archived separately in
`s2-source-002-e5-live-replay-evidence-v1` (PR #293). This artifact does not
modify or supersede that file pair.

This PR is documentation only.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_XLS_COMMITTED=true
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
POSTGRES_LIVE_PASS_IS_NOT_S2_ACCEPTANCE=true
SQLITE_LIVE_PASS_IS_NOT_OFFICIAL_S2_FREEZE=true
THIS_TASK_IS_NOT_OFFICIAL_S2_FREEZE=true
OFFICIAL_S2_FREEZE_ISSUED=false
SECTION_11_ALL_FALSE=true
~~~

## 1. Live replay operator context

~~~text
LIVE_REPLAY_OPERATOR=LANE_C
LIVE_REPLAY_ENGINE=POSTGRES
POSTGRES_AVAILABLE=true
POSTGRES_START_METHOD=apt_postgresql_16 + pg_ctlcluster 16 main start
POSTGRES_DSN_SANITIZED=postgresql://postgres@localhost:5432/blueberry_peak_test
ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
OBJECT_STATUS=PASS
SOURCE_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
BYTE_COUNT=28668416
COUNT_ORACLES_MATCH_SQLITE=true
~~~

Lane C executed the controlled SOURCE_002 E5 materialization path on Postgres
with Alembic head `a7c3e9f1b2d4`. The frozen Source002 object identity
verified (`OBJECT_STATUS=PASS`). This is operator evidence, not an official S2
freeze package.

## 2. Bound verbatim report (do not recompute)

The following line is the authoritative live replay output for this artifact.
Numbers are bound as observed. Do not extrapolate tonnage or invent additional
counts.

~~~text
SOURCE_002_E5_REPORT e2=233171 e3_grains=33894 e3_kg_equal=true idfl_sql=233171 pit_sql=0 old_winner_sql=0 train_rows=16224 val_rows=8006 test_rows=0 test_window_grains_not_persisted=9664 dataset_identity=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785 rebuild_parity=PASS
~~~

## 3. Frozen arithmetic and boundary checks

~~~text
E2_EXACT_REPLAY=233171
E3_UNIQUE_CANONICAL_GRAINS=33894
E3_KG_EQUAL=true
IDFL_SQL=233171
PIT_SQL=0
OLD_WINNER_SQL=0
TRAIN_ROWS=16224
VAL_ROWS=8006
TEST_ROWS=0
TEST_WINDOW_GRAINS_NOT_PERSISTED=9664
ROW_ARITHMETIC=16224+8006+9664=33894
DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
REBUILD_PARITY=PASS
SOURCE_002_ROW_LEVEL_READ=false
COUNT_ORACLES_MATCH_SQLITE=true
~~~

Semantics:

- `train_rows + val_rows + test_window_grains_not_persisted = 33894` matches
  `e3_grains`. `test_rows=0`; TEST-window grains were not persisted into D row
  tables.
- `pit_sql=0` and `old_winner_sql=0` remain required SOURCE_002 IDFL boundary
  oracles.
- `dataset_identity` matches the archived SQLite live replay evidence
  (`SQLITE_BOUND_DATASET_IDENTITY` below). That equality is an observed fact,
  not an official published S2 freeze hash package.

~~~text
SQLITE_BOUND_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
POSTGRES_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
DATASET_IDENTITY_MATCHES_SQLITE_EVIDENCE=true
~~~

No xls, Drive URL, file id, password, or Source002 bytes were committed to Git
as part of this evidence task.

## 4. What this evidence is and is not

~~~text
LIVE_REPLAY_RECORDED=true
OFFICIAL_S2_FREEZE_ISSUED=false
POSTGRES_LIVE_PASS_IS_NOT_S2_ACCEPTANCE=true
SQLITE_LIVE_PASS_IS_NOT_OFFICIAL_S2_FREEZE=true
THIS_TASK_IS_NOT_OFFICIAL_S2_FREEZE=true
INDEPENDENT_S2_ACCEPTANCE_DECISION_ISSUED=false
~~~

A Postgres operator live run with `rebuild_parity=PASS` is implementation and
operator evidence. It is not contract §11 acceptance. No independent S2
acceptance decision was issued.

## 5. Contract §11 (all remain false)

Each item remains **false** on this evidence alone.

| §11 item | ACCEPTED | Reason on this head |
|---|---|---|
| IMMUTABLE_RAW_REFERENCE_ACCEPTED | **false** | Postgres operator replay; no official freeze record |
| SOURCE_ROW_LINEAGE_ACCEPTED | **false** | no published lineage freeze package |
| CLEANED_DATA_MANIFEST_ACCEPTED | **false** | no official cleaned manifest acceptance |
| QUALITY_REPORT_ACCEPTED | **false** | no official quality report acceptance |
| CORRECTION_LEDGER_ACCEPTED | **false** | no official correction ledger acceptance |
| EXCLUSION_LEDGER_ACCEPTED | **false** | no official exclusion ledger acceptance |
| TIME_VISIBILITY_REPORT_ACCEPTED | **false** | PIT SQL=0 by design; no published report |
| TRAIN_MATERIALIZED_MANIFEST_ACCEPTED | **false** | Postgres operator evidence only |
| VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED | **false** | Postgres operator evidence only |
| TEST_MATERIALIZED_MANIFEST_ACCEPTED | **false** | `test_rows=0`; TEST still sealed |
| FINAL_SPLIT_MANIFEST_ACCEPTED | **false** | no official S2 split freeze record |
| FINAL_DATASET_HASHES_ACCEPTED | **false** | `dataset_identity` not an official published hash package |
| DETERMINISTIC_REBUILD_PARITY_ACCEPTED | **false** | operator Postgres replay; no acceptance decision |

~~~text
S2_ACCEPTANCE_ITEMS_TRUE_COUNT=0
S2_ACCEPTANCE_ITEMS_FALSE_COUNT=13
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
~~~

## 6. Verdict

~~~text
E5_POSTGRES_LIVE_REPLAY_EVIDENCE_STATUS=RECORDED
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
V0_3_S3_AUTHORIZED=false
~~~

This document records Lane C's completed SOURCE_002 E5 Postgres live replay. It
does not authorize Ready-as-acceptance, Merge-as-acceptance, S3, or contract /
development-plan mutation.
