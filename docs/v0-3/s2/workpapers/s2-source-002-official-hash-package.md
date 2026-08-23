# V0.3-S2 SOURCE_002 official hash package record

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_OFFICIAL_HASH_PACKAGE
ARTIFACT_VERSION=s2-source-002-official-hash-package-v1
TASK_ID=V03_S2_SOURCE_002_OFFICIAL_HASH_PACKAGE_R1
TASK_CLASS=DOCS_ONLY_HASH_PACKAGE
AUTHORIZATION_SCOPE=S2_SOURCE_002_OFFICIAL_HASH_PACKAGE_RECORD_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUDITED_REPOSITORY_SHA=cd682056be1edba970779356d2e5ceb5731c8307
AUDITED_REPOSITORY_TREE_SHA=86e0d12252a43889bee501e7ef0238d78ca04fab
AUDITED_REF=origin/main
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
AMENDMENT_VERSION=v0-3-s2-allowlist-migration-ownership-r2
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-official-hash-package.md
EVIDENCE_JSON_PATH=docs/v0-3/s2/evidence/s2-source-002-official-hash-package.json
NO_STEP_IMPLIES_THE_NEXT=true
~~~

This document records the Lane C Postgres freeze hash dump as an official hash
package. It binds the verbatim dump below. It does **not** accept S2, issue an
official S2 freeze acceptance, start S3, or mutate the frozen contract or
development-plan gate registry.

Prior operator replay evidence remains archived separately:

- SQLite live replay: `s2-source-002-e5-live-replay-evidence-v1` (PR #293)
- Postgres live replay: `s2-source-002-e5-postgres-live-replay-evidence-v1`
  (PR #294)

This artifact does not modify or supersede those file pairs.

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
DO_NOT_INVENT_HASHES_OR_TONNES=true
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
SOURCE_002_OFFICIAL_HASH_PACKAGE_RECORDED=true
OFFICIAL_S2_FREEZE_ISSUED=false
THIS_PACKAGE_IS_NOT_S2_ACCEPTANCE=true
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
SLICE_S2_COMPLETE=false
SECTION_11_ALL_FALSE=true
~~~

`BUILDER_QUALITY_GATE_STATUS=ACCEPTED` in the bound dump is a builder-internal
gate disposition. It must **not** be read as contract
`QUALITY_REPORT_ACCEPTED=true`.

## 1. Bound verbatim freeze hash dump (do not recompute)

The following block is the authoritative official hash package for this
artifact. Hashes and counts are bound as observed. Do not extrapolate tonnage,
invent additional hashes, or commit `content_bytes`.

~~~text
SOURCE_002_FREEZE_HASH_DUMP
AUDITED_REPOSITORY_SHA=cd682056be1edba970779356d2e5ceb5731c8307
ALEMBIC_HEAD=a7c3e9f1b2d4
POSTGRES_DSN_SANITIZED=postgresql://postgres@localhost:5432/blueberry_peak_test
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
LINEAGE_COMPLETE=true
QUALITY_GATE_STATUS=ACCEPTED
REBUILD_PARITY=PASS
TRAIN.row_count=16224
TRAIN.byte_count=9087071
TRAIN.content_sha256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
TRAIN.partition_identity_sha256=55d8e97e73568def2cd368bcf76deeb13de5089361f70b08c8101ea8f745097b
TRAIN.manifest_sha256=9cb126a65311904dc34a0350a5735369aa9988dfe8056138d7e1cd9d093351fd
TRAIN.partition_start_date=2025-08-05
TRAIN.partition_end_date=2026-01-30
TRAIN.rebuild_hash_replay_status=PASS
VALIDATION.row_count=8006
VALIDATION.byte_count=4484905
VALIDATION.content_sha256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
VALIDATION.partition_identity_sha256=006c80ff6bc88ecf7112fd082ab7e27e71655ebd2f00ff105d6110a8473244ba
VALIDATION.manifest_sha256=2b8a69ef6579d616464525c9ceebc141f43dc018272b572b77fe4f3c21bf79d4
VALIDATION.partition_start_date=2026-01-31
VALIDATION.partition_end_date=2026-03-09
VALIDATION.rebuild_hash_replay_status=PASS
TEST.row_count=0
TEST.byte_count=240
TEST.content_sha256=bd3d846a300c70a638bc169a095c3b02cb9e20c2c2aa6a96af0990d85a1fb1bd
TEST.partition_identity_sha256=452ac3ea3c8083678bcc7f929d77f1cb6c2237445a072b0895f60cf6fffca8a3
TEST.manifest_sha256=1507d2bab7edb57421f258ded681955e93559b2e7393a3f784fb3577bdb6aeab
TEST.partition_start_date=2026-03-10
TEST.partition_end_date=2026-04-16
TEST.rebuild_hash_replay_status=PASS
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_SHA256=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
BUILDER_VERSION=v0-3-s2-lane-d-builder-r1
SPLIT_POLICY_VERSION=v0-3-s1-time-ordered-split-policy-v1
RAW_POLICY_VERSION=v0-3-s2-source-002-controlled-import-policy-v1
CLEANING_POLICY_VERSION=v0-3-s2-cleaning-policy-v2+s2-source-002-canonical-grain-kg-sum-v1
CORRECTION_POLICY_VERSION=v0-3-s2-correction-policy-v1
EXCLUSION_POLICY_VERSION=v0-3-s2-exclusion-policy-v1
VISIBILITY_POLICY_VERSION=v0-3-s2-idfl-label-side-visibility-v1
REVISION_WINNER_POLICY_VERSION=v0-3-s2-idfl-revision-winner-v1
~~~

## 2. TEST partition seal

~~~text
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_IS_SEALED_PLACEHOLDER=true
TEST_EVALUATION_AUTHORIZED=false
~~~

`TEST.row_count=0` with `TEST.byte_count=240` binds the sealed TEST placeholder
bytes persisted under the existing GET-without-bytes API policy. This is not
test evaluation, quantile coverage, backtest, or model validation. TEST remains
sealed.

## 3. What this package is and is not

~~~text
SOURCE_002_OFFICIAL_HASH_PACKAGE_RECORDED=true
OFFICIAL_S2_FREEZE_ISSUED=false
THIS_PACKAGE_IS_NOT_S2_ACCEPTANCE=true
HASH_PACKAGE_RECORDED_DOES_NOT_EQUAL_S2_ACCEPTANCE=true
INDEPENDENT_S2_ACCEPTANCE_DECISION_ISSUED=false
~~~

Recording the Postgres freeze hash dump publishes governed partition and dataset
identity hashes for `source-002` / `e5-live-v1`. It does not issue S2
acceptance, complete Slice S2, or authorize S3.

No xls, Drive URL, file id, password, or partition `content_bytes` were
committed to Git as part of this task.

## 4. Contract §11 (all remain false)

Each item remains **false** even though the hash package is now recorded.

| §11 item | ACCEPTED | Reason on this head |
|---|---|---|
| IMMUTABLE_RAW_REFERENCE_ACCEPTED | **false** | hash package recorded; no S2 acceptance decision |
| SOURCE_ROW_LINEAGE_ACCEPTED | **false** | hash package recorded; no acceptance decision |
| CLEANED_DATA_MANIFEST_ACCEPTED | **false** | hash package recorded; no acceptance decision |
| QUALITY_REPORT_ACCEPTED | **false** | builder `QUALITY_GATE_STATUS=ACCEPTED` ≠ contract acceptance |
| CORRECTION_LEDGER_ACCEPTED | **false** | hash package recorded; no acceptance decision |
| EXCLUSION_LEDGER_ACCEPTED | **false** | hash package recorded; no acceptance decision |
| TIME_VISIBILITY_REPORT_ACCEPTED | **false** | hash package recorded; no acceptance decision |
| TRAIN_MATERIALIZED_MANIFEST_ACCEPTED | **false** | hashes recorded; no S2 acceptance decision |
| VALIDATION_MATERIALIZED_MANIFEST_ACCEPTED | **false** | hashes recorded; no S2 acceptance decision |
| TEST_MATERIALIZED_MANIFEST_ACCEPTED | **false** | `TEST.row_count=0`; TEST still sealed |
| FINAL_SPLIT_MANIFEST_ACCEPTED | **false** | split ranges bound in dump; no acceptance decision |
| FINAL_DATASET_HASHES_ACCEPTED | **false** | hash package recorded; no S2 acceptance decision |
| DETERMINISTIC_REBUILD_PARITY_ACCEPTED | **false** | rebuild PASS in dump; no acceptance decision |

~~~text
S2_ACCEPTANCE_ITEMS_TRUE_COUNT=0
S2_ACCEPTANCE_ITEMS_FALSE_COUNT=13
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=false
SLICE_S2_COMPLETE=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
~~~

## 5. Verdict

~~~text
OFFICIAL_HASH_PACKAGE_RECORD_STATUS=RECORDED
S2_ACCEPTANCE_DECISION=NOT_ACCEPTED
V0_3_S3_AUTHORIZED=false
~~~

This document records the SOURCE_002 official hash package. It does not
authorize Ready-as-acceptance, Merge-as-acceptance, S3, or contract /
development-plan mutation.
