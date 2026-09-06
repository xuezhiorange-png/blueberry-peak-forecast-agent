# V0.3-S3 Farm-total Baseline Live Execution (R1)

> Scope: authorized live execution evidence only — no scoring, no TEST access
> Task: `V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_R1`
> Parent authorization: PR #567 merge `090f282ab44e9aee836fc561a429200640b10633`

## Machine-readable header

```text
TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_LIVE_EXECUTION_R1
BASE_MAIN_SHA=090f282ab44e9aee836fc561a429200640b10633

PARENT_AUTHORIZATION_PR=567
PARENT_AUTHORIZATION_MERGE_SHA=090f282ab44e9aee836fc561a429200640b10633
PARENT_EVALUATION_PACKAGE_PR=566
PARENT_EVALUATION_PACKAGE_MERGE_SHA=80b05d5c033f19d0ded3dc7c983a08f00f50d662

USER_EXECUTION_GATE=可以执行

EXECUTION_MAIN_SHA=090f282ab44e9aee836fc561a429200640b10633
RUNNER_COMMIT_SHA=bfd6d08aecb7c34ce12dbc2fc198f2a00dbcd6c9

LIVE_DATABASE_ATTESTATION_PRECHECK=PASS
LIVE_DATABASE_DATASET_ID=source-002
LIVE_DATABASE_DATASET_VERSION=e5-live-v1
LIVE_DATABASE_MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
PREVIOUS_EMPTY_ISOLATED_DB_REUSED=false
RUNNER_CHANGED_AFTER_BLOCKER=false

LIVE_BASELINE_EXECUTION_PERFORMED=true
LIVE_TRAIN_EXECUTION_PERFORMED=true
OFFICIAL_TRAIN_BYTE_READ_PERFORMED=true
OFFICIAL_VALIDATION_BYTE_READ_PERFORMED=true
LIVE_VALIDATION_TARGET_PROJECTION_PERFORMED=true
VALIDATION_BASELINE_MATERIALIZED=true

LIVE_REPLAY_REQUIRED=true
LIVE_REPLAY_COUNT=2
LIVE_REPLAY_STATUS=PASS
REPLAY_IDENTITY_MATCH_RESULT=PASS

VALIDATION_BASELINE_SCORED=false
VALIDATION_SCORING=false
S3_C_BACKTEST_EXECUTION=false
S3_METRIC_EXECUTION=false

TEST_EVALUATION_ACCESS=false
TEST_PAYLOAD_RETURNED=false
TEST_REMAINS_SEALED=true

MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false

AUTHORITY_DIR_SOURCE=/tmp/v03-farm-total-authority
AUTHORITY_PACKAGE_REGENERATION_PERFORMED=false

READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

## 1. Execution summary

Live execution used the frozen runner at commit `bfd6d08aecb7c34ce12dbc2fc198f2a00dbcd6c9`
against `origin/main` `090f282ab44e9aee836fc561a429200640b10633`.

The controlled authority directory supplied reviewed farm-total authority packages.
Official SOURCE-002 TRAIN and VALIDATION bytes were obtained through the governed
live obtain seam. Farm-total data-plane materialization and baseline evaluation package
construction completed in memory with `verify_official_hashes=True`.

Two identical live runs were executed and replay identities matched.

## 2. Repository identity

| Field | Value |
| --- | --- |
| Execution main SHA | `090f282ab44e9aee836fc561a429200640b10633` |
| Runner commit SHA | `bfd6d08aecb7c34ce12dbc2fc198f2a00dbcd6c9` |
| Runner path | `scripts/run_v03_farm_total_baseline_evaluation_package.py` |

## 3. SOURCE-002 authority

| Field | Value |
| --- | --- |
| Dataset ID | `source-002` |
| Dataset version | `e5-live-v1` |
| Materialized dataset identity SHA256 | `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785` |
| Official train content SHA256 | `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2` |
| Official validation content SHA256 | `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06` |
| Train source row count | 16224 |
| Validation source row count | 8006 |
| Test remains sealed | true |

## 4. Authority bundle

| Field | Value |
| --- | --- |
| Farm group mapping set SHA256 | `eb013e3e638074945d182c89433096716e771b934855bc0139b9f20ca76c8677` |
| Farm area authority set SHA256 | `339d2adebe1b3db6fece4726934191b86dc311be26c481e9d6dc333b4cae1d3f` |
| Authority mapping package file SHA256 | `a349f48da71095fffb4a71dc7cbe92d81e04add62c8475601cc4c0eaaf4f56df` |
| Authority area package file SHA256 | `c26eb6ebc5bdbd537a0ccec3fe48388b6432cc685ada0763f7b7d765a28f4757` |

## 5. Farm-total data plane

| Field | Value |
| --- | --- |
| Train farm-total row count | 2663 |
| Validation farm-total row count | 1033 |
| Train farm group count | 31 |
| Validation farm group count | 31 |
| Train farm-total dataset SHA256 | `08aa2116d700ce00531943fcb00e7ed9b9353ed7821012359838ec027ef7a0e1` |
| Validation farm-total dataset SHA256 | `351a401fccfeb42758401583ee88a86fb85e9917ca5f3997c62ac3b36f81cac0` |
| Area double count count | 0 |
| Source farm double map count | 0 |
| Source actual double count | 0 |
| Validation used as training input | false |

## 6. Baseline evaluation package diagnostics

| Field | Value |
| --- | --- |
| Package schema version | `v0-3-s3-farm-total-baseline-evaluation-package-v1` |
| Target count | 1033 |
| Emitted point count | 1033 |
| Blocked target count | 0 |
| Ready target count | 1033 |
| Insufficient train support target count | 0 |
| Unseen group target count | 0 |

## 7. Hash identities

| Field | Value |
| --- | --- |
| Estimator state SHA256 | `daf4a0565d910ef0da70f3de1adcbf6507b60c2c77c784d4c2412a416da755c3` |
| Target identity set SHA256 | `9f268fa082e4dc6e1c83ed47fc32a4b6b202f07e38773d9b5a5967c0c9bfe427` |
| Baseline point set SHA256 | `5869bbde1c3717c2ee5469976a6cea368c4e5c538063b893c383f244aeaee0a5` |
| Target outcome set SHA256 | `169033291c46884c587275888b1e6fb83e740b240a74c5a063c4b36291f64d94` |
| Prediction identity SHA256 | `2608b407dc00361cf2cd73e8469ce569591cdb6eacc033e16578d7e1561dbf44` |
| Package SHA256 | `f1098fd3ff2559bda9ff311788496bdbbcb6000c335743f2028ffe558e291c37` |

## 8. Replay

```text
LIVE_REPLAY_COUNT=2
LIVE_REPLAY_STATUS=PASS
REPLAY_IDENTITY_MATCH_RESULT=PASS
```

Both live runs emitted `EXECUTION_STATUS=PASS` with identical replay identity fields.

## 9. Boundaries preserved

```text
VALIDATION_BASELINE_SCORED=false
VALIDATION_SCORING=false
S3_C_BACKTEST_EXECUTION=false
S3_METRIC_EXECUTION=false
TEST_EVALUATION_ACCESS=false
TEST_PAYLOAD_RETURNED=false
TEST_REMAINS_SEALED=true
MODEL_CHANGE=false
PARAMETER_CHANGE=false
MIGRATION_CHANGE=false
SCHEMA_CHANGE=false
V0_3_S4_AUTHORIZED=false
BASELINE_P80_STATUS=NOT_COMPUTABLE
BASELINE_P90_STATUS=NOT_COMPUTABLE
```

No real kg values, per-target baseline points, validation actuals, raw rows, or TEST
bytes are recorded in this workpaper.
