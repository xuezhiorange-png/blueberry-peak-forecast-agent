# V0.3-S2 SOURCE_002 E5 live replay evidence (Lane C operator)

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_E5_LIVE_REPLAY_EVIDENCE
ARTIFACT_VERSION=s2-source-002-e5-live-replay-evidence-v1
TASK_ID=V03_S2_SOURCE_002_E5_LIVE_REPLAY_EVIDENCE_R1
TASK_CLASS=DOCS_ONLY_LIVE_REPLAY_EVIDENCE
AUTHORIZATION_SCOPE=S2_SOURCE_002_E5_LIVE_REPLAY_EVIDENCE_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUDITED_REPOSITORY_SHA=c6e3cd3578f1d17a9bc2764a6157fcf36094e95e
AUDITED_REPOSITORY_TREE_SHA=037618384ce512d743e1aad8cc8493f9c62e7315
AUDITED_REF=origin/main
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
AMENDMENT_VERSION=v0-3-s2-allowlist-migration-ownership-r2
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-e5-live-replay-evidence.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-source-002-e5-live-replay-evidence.json
EVIDENCE_JSON_SHA256=9da4ed3d7a277ec632354d4dded2571e7c44efb3a385349bbdb79bf2d8eae076
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This document records one completed SOURCE_002 E5 live replay executed by Lane
C on the audited `main` head. It binds the verbatim operator report below. It
does not accept S2, freeze an official dataset, start S3, or mutate the frozen
contract or development-plan gate registry.

This PR is documentation only.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_XLS_COMMITTED=true
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
SQLITE_LIVE_PASS_IS_NOT_OFFICIAL_S2_FREEZE=true
~~~

## 1. Live replay operator context

~~~text
LIVE_REPLAY_OPERATOR=LANE_C
LIVE_REPLAY_ENGINE=SQLITE
POSTGRES_AVAILABLE=false
ALEMBIC_HEAD=a7c3e9f1b2d4
PARALLEL_ALEMBIC_HEADS_ALLOWED=false
~~~

Lane C executed the controlled SOURCE_002 E5 materialization path on SQLite
with Alembic head `a7c3e9f1b2d4`. Postgres was not available on the recording
environment. This is operator evidence, not an official S2 freeze package.

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
~~~

Semantics:

- `train_rows + val_rows + test_window_grains_not_persisted = 33894` matches
  `e3_grains`. `test_rows=0`; TEST-window grains were not persisted into D row
  tables.
- `pit_sql=0` and `old_winner_sql=0` remain required SOURCE_002 IDFL boundary
  oracles.
- `dataset_identity` is bound from the live SQLite run. It is **not** an
  official published S2 freeze hash package.

No xls, Drive URL, file id, or Source002 bytes were committed to Git as part
of this evidence task.

## 4. What this evidence is and is not

~~~text
LIVE_REPLAY_RECORDED=true
OFFICIAL_S2_FREEZE_ISSUED=false
POSTGRES_REPLAY_EXECUTED=false
INDEPENDENT_S2_ACCEPTANCE_DECISION_ISSUED=false
SQLITE_LIVE_PASS_IS_NOT_OFFICIAL_S2_FREEZE=true
~~~

A single SQLite live run with `rebuild_parity=PASS` is implementation and
operator evidence. It is not contract §11 acceptance. Postgres replay was not
executed. No independent S2 acceptance decision was issued.

## 5. Contract §11 (all remain false)

Each item remains **false** on this evidence alone.

| §11 item | ACCEPTED | Reason on this head |
|---|---|---|
| IMMUTABLE_RAW_REFERENCE_ACCEPTED | **false** | single SQLite operator run; no official freeze record |
| SOURCE_ROW_LINEAGE_ACCEPTED | **false** | no published lineage freeze package |
| CLEANED_DATA_MANIFEST_ACCEPTED | **false** | no official cleaned manifest acceptance |
| QUALITY_REPORT_ACCEPTED | **false** | no official quality report acceptance |
| CORRECTION_LEDGER_ACCEPTED | **false** | no official correction ledger acceptance |
| EXCLUSION_LEDGER_ACCEPTED | **false** | no official exclusion ledger acceptance |
| TIME_VISIBILITY_REPORT_ACCEPTED | **false** | PIT SQL=0 by design; no published report |
| TRAIN_MATERIALIZED_MANIFEST_ACCEPTED | **false** | SQLite live evidence only |
| VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED | **false** | SQLite live evidence only |
| TEST_MATERIALIZED_MANIFEST_ACCEPTED | **false** | `test_rows=0`; TEST still sealed |
| FINAL_SPLIT_MANIFEST_ACCEPTED | **false** | no official S2 split freeze record |
| FINAL_DATASET_HASHES_ACCEPTED | **false** | `dataset_identity` not an official published hash package |
| DETERMINISTIC_REBUILD_PARITY_ACCEPTED | **false** | SQLite-only; Postgres not run; no acceptance decision |

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
E5_LIVE_REPLAY_EVIDENCE_STATUS=RECORDED
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
V0_3_S3_AUTHORIZED=false
~~~

This document records Lane C's completed SOURCE_002 E5 SQLite live replay. It
does not authorize Ready-as-acceptance, Merge-as-acceptance, S3, or contract /
development-plan mutation.
