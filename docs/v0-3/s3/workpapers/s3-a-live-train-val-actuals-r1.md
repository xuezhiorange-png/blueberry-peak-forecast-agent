# V0.3-S3-A live accepted S2 TRAIN/VAL actuals binding R1

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A_LIVE_TRAIN_VAL_ACTUALS_R1
ARTIFACT_VERSION=s3-a-live-train-val-actuals-r1-v1
TASK_ID=V03_S3_A_LIVE_TRAIN_VAL_ACTUALS_R1
TASK_CLASS=IMPLEMENTATION
AUTHORIZATION_SCOPE=S3_A_ROWSET_MATERIALIZATION_IMPLEMENTATION_ONLY
SLICE=V0.3-S3
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a05131-6262-7c86-9895-dde762dda347
STACKED_BASE_BRANCH=cursor/s3-a2-source-002-live-attestation-a347
STACKED_BASE_HEAD_SHA=3a3d85f4f27cfaaf32d9ae83ef4c94870e0a81f6
BASE_MAIN_SHA=2e2a554d252b31a91f98e2db33a6266f8d41cf17
GRANT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a-rowset-materialization-authorization.md
GRANT_WORKPAPER_GIT_BLOB_SHA=dbd0291b93e707eb2208494d32fa889eca3551a1
GRANT_EVIDENCE_JSON_SHA256=df66d59383d3bdf76e7db6fdc32b21b2f41237ef3072f8a1ac76205ddc4d6239
MATERIALIZER_R1_EVIDENCE_JSON_SHA256=4eefdfbaee5be91c594d5f0203270ce52a42ec71538659c5484d436a3eb7e65c
PARENT_LIVE_ATTESTATION_PR=475
PARENT_LIVE_ATTESTATION_EVIDENCE_JSON_SHA256=b8f0f0196bf517eb74bbed97d6a710fad9e3a16d64d7ecc33e955320b1f1c076
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a-live-train-val-actuals-r1.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a-live-train-val-actuals-r1.json
EVIDENCE_JSON_SHA256=72a5d63f3b5be6b1140d5849f6038777bd79e1dc9ca0ce4013c79cd006ee07ec
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
IMPLEMENTATION_R1=true
EXECUTION_CLAIM_R1_IS_DOCS_ONLY=false
THIS_FAMILY_UNIQUE_REMAINING_GAP_CLOSED=true
UNIQUE_REMAINING_GAP=_none
~~~

This workpaper records implementation R1 binding accepted S2 TRAIN+VALIDATION
partition bytes from a live read into the landed S3-A daily rowset materializer
actuals port per grant `s3-a-rowset-materialization-authorization.md` (blob
`dbd0291b93e707eb2208494d32fa889eca3551a1`). Parent live attestation (#475) already
attested official TRAIN+VAL content hashes via `AsyncSessionMaker.run_sync`; this R1
parses attested bytes into `MaterializableRow` and binds `InMemoryS2ActualsSource`
for `DailyRowsetMaterializerService`. This R1 uniquely flips
`LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true` in live §4.4. It does not flip
`CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`, does not flip `SOURCE_002_ROW_LEVEL_READ`,
does not land a coordinator-reviewed grain identity set, does not produce a versioned
forecast artifact, and does not authorize backtest/metrics.

~~~text
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=true
LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true
SOURCE_002_ROW_LEVEL_READ=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

`LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true` ≠ completeness verified ≠
members landed ≠ `NO_REVIEWED` flipped ≠ versioned forecast artifact produced ≠
catalog bindable ≠ backtest/attribution/metrics computed. Parsed partition grains
are not a coordinator-reviewed identity set. Using already-configured
`AsyncSessionMaker.run_sync` here is S3-A actuals binding, not landing run-sync-obtain
(#474 freeze only; no grant). No `content_bytes`, kilogram values, or member lists are
recorded in evidence.

## 1. Delivered

- `parse_partition_bytes` inverse of `build_partition_bytes` in
  `backend/app/s2_materialized_dataset/lane_d/canonical.py`
- `backend/app/s3_daily_rowset/live_accepted_s2_train_val_actuals_source.py`
- `build_daily_rowset_materializer_with_live_actuals` wiring in `service.py`
- Tests under `backend/tests/s2_materialized_dataset/lane_d/test_canonical.py` and
  `backend/tests/s3_daily_rowset/test_live_accepted_s2_train_val_actuals_source.py`

## 2. Official hash bindings (copy only)

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN.row_count=16224
TRAIN.byte_count=9087071
TRAIN.content_sha256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION.row_count=8006
VALIDATION.byte_count=4484905
VALIDATION.content_sha256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TEST.row_count=0
TEST_REMAINS_SEALED=true
~~~

## 3. Unique flip

~~~text
UNIQUE_REMAINING_GAP_BEFORE=_no_live_accepted_s2_train_val_actuals_source_bound_into_the_landed_daily_rowset_materializer
UNIQUE_REMAINING_GAP_AFTER=_none
LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=false_to_true
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=already_true_not_reclaimed
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=remains_false
~~~
