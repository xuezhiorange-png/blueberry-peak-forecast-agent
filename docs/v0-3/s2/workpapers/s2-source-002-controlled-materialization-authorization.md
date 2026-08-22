# V0.3-S2 SOURCE_002 controlled materialization authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_CONTROLLED_MATERIALIZATION_AUTHORIZATION
ARTIFACT_VERSION=s2-source-002-controlled-materialization-authorization-v1
TASK_ID=V03_S2_SOURCE_002_CONTROLLED_MATERIALIZATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S2_SOURCE_002_CONTROLLED_MATERIALIZATION_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUTHORIZED_AT=2026-08-22T04:48:00Z
RECORDED_AT=2026-08-22T04:51:26Z
AUTHORIZATION_UTTERANCE=授权
BASE_MAIN_SHA=496631e2e42142f45683159cf32545386b61ace7
BASE_MAIN_TREE_SHA=df50d720a7ec000fd802585dcc8ef423fc1d1527
PREVIOUS_REVALIDATION_PR=283
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-controlled-materialization-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-source-002-controlled-materialization-authorization.json
EVIDENCE_JSON_SHA256=c02211b1c047607ce795e0719f7d605ea5e2643b7218c1a5f998c603380cb991
NO_STEP_IMPLIES_THE_NEXT=true
~~~

The user authorized SOURCE_002 controlled materialization after the post-D2
revalidation. This document records that grant. It does not ingest Source002,
does not freeze a dataset, does not accept S2, and does not start S3.

This PR is documentation only.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
S1_AUTHORITY_MUTATION_AUTHORIZED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
GIT_COMMIT_OF_SOURCE_BYTES_OR_LOCATORS_AUTHORIZED=false
~~~

## 1. What is authorized

A later implementation sequence may, after exact object-identity verification,
read the frozen Source002 object and run A → B → C → D to persist an
immutable raw reference, lineage, cleaned rows, quality/ledgers, PIT/revision
winners, and TRAIN/VALIDATION/TEST materialized partitions.

~~~text
SOURCE_002_READ_AUTHORIZED=true
SOURCE_002_RAW_READ_AUTHORIZED=true
SOURCE_002_ROW_LEVEL_READ_AUTHORIZED=true
SOURCE_002_MUTATION_AUTHORIZED=false

BUILDER_TRAIN_PARTITION_BUILD_AUTHORIZED=true
BUILDER_VALIDATION_PARTITION_BUILD_AUTHORIZED=true
BUILDER_TEST_PARTITION_STORAGE_MATERIALIZATION_AUTHORIZED=true
TEST_MATERIALIZATION_IS_NOT_TEST_EVALUATION=true
TEST_EVALUATION_AUTHORIZED=false
TEST_API_CONTENT_BYTES_AUTHORIZED=false

METRIC_EXECUTION_AUTHORIZED=false
BACKTEST_AUTHORIZED=false
MODEL_TRAINING_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_AUTHORIZED=false
SLICE_S2_COMPLETE=false
~~~

TEST materialization is storage/build of the TEST partition (hashes, counts,
and stored `content_bytes` under the existing GET-without-bytes API). It is
not test evaluation, quantile coverage, backtest, or model validation.

Missing-day semantics remain `UNKNOWN_NOT_ZERO`. Absent days must not be
coerced to numeric zero.

The frozen S2 contract file is **not** rewritten. Freeze-time flags in that
file remain historical. This authorization is a separate grant.

## 2. Required Source002 identity

Implementation must fail closed unless the opened object matches all of:

~~~text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
BYTE_COUNT=28668416
DECLARED_SOURCE_ROW_COUNT=233171
OBSERVED_SCHEMA_VERSION=observed-source-schema-v1
OBSERVED_SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_SHA256=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
~~~

`data/raw/2024_2025_receipts.xls` and `data/raw/2025_2026_receipts.xls` are
**not** Source002. They must not be substituted.

No plaintext storage locator, Drive file ID, credential, workbook, or row
dump may be committed to Git. Logs must not record whole sensitive rows.

## 3. Access readiness on the recording environment

Coordinator scan of this cloud workspace, by size `28668416` and SHA-256
`fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` only:

~~~text
THIS_ENVIRONMENT_SOURCE_002_OBJECT_PRESENT=false
TARGET_SIZE_MATCH_COUNT=0
TARGET_SHA_MATCH_COUNT=0
SOURCE_002_BYTES_READ=false
SOURCE_002_ROW_LEVEL_READ_EXECUTED=false
PLAINTEXT_LOCATOR_RECORDED=false
~~~

Therefore ingest is **not** executable on this recording head. The grant is
real. The bytes are not here.

## 4. Implementation sequence after bytes are present

Lanes remain sequential. Parallel A/B/C/D PRs that assume Fake ports are not
this work.

| Step | Owner | Allowed paths | Stop if |
|---|---|---|---|
| E1 | implementing agent | docs-only readiness note optional | object missing or identity mismatch |
| E2 | Lane A | Lane A production/test/migration allowlists only | cannot ingest via existing allowlisted import/mapping without new files |
| E3 | Lane B | Lane B allowlists only | A facts not persisted |
| E4 | Lane C | Lane C allowlists only | A/B facts not persisted |
| E5 | Lane D | Lane D allowlists + D-owned seams | cannot consume persisted A/B/C; Fake ports remain as tests only |

`ALLOWLIST_PATH_NOT_LISTED_REQUIRES_BLOCK=true`. A needed new production path
is a stop, not a silent contract amendment.

D must consume persisted A/B/C outputs, not `FakeLaneA/B/C`, for the
SOURCE_002 dataset. Synthetic Fake tests may remain for unit coverage.

Unique Alembic head stays linear. No parallel heads.
`PARALLEL_ALEMBIC_HEADS_ALLOWED=false`. Do not create forbidden production
inits `backend/app/s2_materialized_dataset/__init__.py` or
`backend/app/s2_materialized_dataset/shared/__init__.py`.

## 5. What this grant does not do

~~~text
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
FINAL_SPLIT_MANIFEST_ACCEPTED=false
FINAL_DATASET_HASHES_ACCEPTED=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
NEXT_SLICE_STARTED=false
~~~

A later exact-head review is still required before any §11 item is scored
true. Green CI is not acceptance. This authorization is not a freeze record.

## 6. Next action

1. Provide the frozen Source002 object to an implementation environment
   through a governed out-of-band channel (not Git).
2. Run E1 identity verification.
3. If and only if identity matches, start E2 Lane A ingest as a Draft PR.
4. Do not start S3.
