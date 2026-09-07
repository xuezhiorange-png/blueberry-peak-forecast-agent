# V0.3-S3 Farm-total Baseline VALIDATION Scoring R1

Scope: controlled SOURCE-002 recovery, R4 Farm-total authority binding, and
authorized aggregate VALIDATION scoring only. This workpaper records the two
successful deterministic live replays. It does not contain raw workbook rows,
TRAIN rows, VALIDATION rows, TEST bytes, per-target actuals, predictions, or
errors.

## Machine-readable execution header

    TASK_ID=V0_3_S3_FARM_TOTAL_BASELINE_VALIDATION_SCORING_R1_SOURCE_002_RECOVERY
    PR_NUMBER=570
    BASE_MAIN_SHA=ea716e91ced56ddeb29856fb52828a33871bee0e
    EXECUTION_MAIN_SHA=ea716e91ced56ddeb29856fb52828a33871bee0e
    SCORING_RUNNER_COMMIT_SHA=d89cfc0e7f27a06a5f16ed854eac59ab0b684c86
    EXECUTION_STATUS=PASS

    AUTHORITY_LINEAGE=R4_REISSUED_DURABLE
    AUTHORITY_RECOVERY_MODE=R4_REISSUANCE
    AUTHORITY_PACKAGE_RECOVERY_PERFORMED=true
    AUTHORITY_PACKAGE_RECOVERY_STATUS=PASS
    AUTHORITY_PACKAGE_RECOVERY_IDENTITY=NEW_R4_NOT_BYTE_IDENTICAL
    AUTHORITY_PACKAGE_SEMANTIC_EQUIVALENCE_TO_R1=NOT_ESTABLISHED
    R4_IS_BYTE_IDENTICAL_TO_R1=false
    R4_NEW_AUTHORITY_IDENTITY=true
    R4_AUTHORITY_DURABLY_COMMITTED=true
    HISTORICAL_MAPPING_SEMANTIC_PARITY=NOT_REPRODUCED
    HISTORICAL_AUTHORITY_MAY_NOT_BE_IMPERSONATED=true
    LOST_R1_AUTHORITY_FILES_RECOVERED=false

    SOURCE_002_RAW_OBJECT_RECOVERED=true
    SOURCE_002_RAW_OBJECT_IDENTITY=PASS
    SOURCE_002_RAW_OBJECT_FILE_NAME=原果入库汇总表.xls
    SOURCE_002_RAW_OBJECT_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
    SOURCE_002_RAW_OBJECT_BYTE_COUNT=28668416
    SOURCE_002_REBUILD_PARITY=PASS
    SOURCE_002_DATABASE_RECOVERY_MODE=ISOLATED_LOCAL_POSTGRES_FROM_FROZEN_RAW_SOURCE

    TEST_REMAINS_SEALED=true
    TEST_EVALUATION=false
    BASELINE_VS_INCUMBENT_COMPARISON_EXECUTED=false
    S3_C_BACKTEST_EXECUTION=false
    S3_METRIC_EXECUTION=false
    MODEL_CHANGE=false
    PARAMETER_CHANGE=false
    MIGRATION_CHANGE=false
    SCHEMA_CHANGE=false
    V0_3_S4_AUTHORIZED=false
    READY_AUTHORIZED=false
    MERGE_AUTHORIZED=false
    NO_STEP_IMPLIES_THE_NEXT=true

## 1. SOURCE-002 raw-object recovery

The public-read Drive object was downloaded as the original binary XLS object,
without Google Sheets export or conversion. The exact byte count and SHA-256
matched the required frozen source identity before the object was passed to the
existing controlled S2 path.

| Field | Value |
| --- | --- |
| Source system | 扫码称重系统 |
| Source dataset | 田间商品果每日采摘净重汇总 |
| Source version | scan-weight-export:v0_3_s1:002 |
| Snapshot reference | snapshot:v0_3_s1:002 |
| File name | 原果入库汇总表.xls |
| Byte count | 28668416 |
| SHA-256 | fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a |
| Source row count | 233171 |
| Sheet count | 4 |
| Raw object identity | PASS |

## 2. Existing S2 controlled rebuild

The exact verified XLS was consumed by the repository’s existing controlled
SOURCE-002 import, cleaning, IDFL winner, and Lane D materialization functions.
No alternate transformation or TEST reader was introduced. The database was a
task-isolated local PostgreSQL instance, and current repository migrations were
applied without downgrading them.

| Required oracle | Observed result |
| --- | ---: |
| E2 exact replay rows | 233171 |
| E3 unique canonical grains | 33894 |
| IDFL SQL rows | 233171 |
| PIT SQL rows | 0 |
| Old revision-winner SQL rows | 0 |
| TRAIN rows | 16224 |
| VALIDATION rows | 8006 |
| TEST materialized rows | 0 |
| TEST-window grains not persisted | 9664 |
| E3 kg reconciliation | PASS |
| Lane D storage rebuild parity | PASS |

The required arithmetic closure also held:

    16224 + 8006 + 9664 = 33894

The resulting materialized dataset identity was:

    f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785

Official partition identities were:

    TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
    TRAIN_BYTE_COUNT=9087071
    VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
    VALIDATION_BYTE_COUNT=4484905

## 3. R4 authority lineage

The committed authority files are new R4 reissuance outputs. They are not
claimed to be byte-identical to the lost R1 files, and the historical mapping
semantic parity oracle was not reproduced. Historical identities are retained
only as traceability references; they are not used as R4 identities.

### Prior-area source boundary

| Field | Value |
| --- | --- |
| Workbook title | 光筑25产季加工布局规划方案.xlsx |
| Workbook SHA-256 | 4d2ab255886e302236fa7490b0beb9a339d3896ef2f417e9164ef888090bafb6 |
| Worksheet | 25产季产量预测汇总表 |
| Authorized area rows | 2:640 |
| Source area total | 24832.51138059892957 |

| R4 authority gate | Value |
| --- | ---: |
| High-confidence groups | 34 |
| Eligible groups | 31 |
| Excluded groups | 双龙营, 新哨, 盘龙 |
| Excluded group count | 3 |
| Eligible proxy area mu | 21719.09138059892957 |

| Authority identity | SHA-256 |
| --- | --- |
| R4 mapping set | ea107c4944358644a51f515e7cc664ad0e3f14da64feeaed99a8c96e5ace2c14 |
| R4 area set | cc719508405246d458d2abace7a9714892835cf26c56c26959e00f1860787301 |
| R4 mapping package file | 9522e86d86d88e9f7ae4825498f66961a81518cfbd46cb9d2253e68a449d8a47 |
| R4 area package file | 02fe4b00e35589578fa7fd7a7cc6550bf34c9bfb6cb4a8926770878bce2a66df |
| Historical mapping set, traceability only | eb013e3e638074945d182c89433096716e771b934855bc0139b9f20ca76c8677 |
| Historical area set, traceability only | 339d2adebe1b3db6fece4726934191b86dc311be26c481e9d6dc333b4cae1d3f |

## 4. R4 Farm-total data-plane and package identities

The R4 authority was loaded from the two committed files under
docs/v0-3/s3/authority. The governed Farm-total data-plane function was then
called with the verified official TRAIN and VALIDATION partition bytes and
official-hash verification enabled.

| Identity | R4 SHA-256 |
| --- | --- |
| TRAIN Farm-total dataset | 923181239c73857997c706cc3aed999252a0ea65e4a290c465900dc028bbe6bd |
| VALIDATION Farm-total dataset | 30a613c258e01fdce3f301065c78ad5db13db001e3d2ceac5592dd4e4aa9929b |
| Estimator state | 30717b4e1aab1ca5c471d2c67579b75d3bd369c61bf7e9404015b6d133669318 |
| Target identity set | 190489c16317e41053c2e5c3a8c0d39084872c01fb166adb6d527ced26cb20b6 |
| Baseline point set | 7452ce44af196e185b48375b51f00ca8f13c4984e514f6750c60d13221d12554 |
| Target outcome set | 2ffc78e647bc66ddbd88f15e7f67543d0cdac1952d006097064ec46b6d36f136 |
| Prediction identity | e482c8b1b7c3bc229a6974793d511572ed3d6435878e12a4fdc1c729abe9de99 |
| Baseline evaluation package | ed9a36c9b1a5eb9932a219e5aea7f2dd446cb1d9d17ff9e49ef0ce9fff05d3b2 |

The historical R1 package SHA-256
f1098fd3ff2559bda9ff311788496bdbbcb6000c335743f2028ffe558e291c37 was not
used as an R4 execution input. R4 package hash parity with that historical
package is false.

## 5. Authorized VALIDATION scoring

The frozen runner at commit d89cfc0e7f27a06a5f16ed854eac59ab0b684c86 used the
existing live SOURCE-002 obtain seam. Only MAE, WAPE, and sMAPE were computed.
The R4 score package contained 1,032 targets, all READY and comparable.

| Diagnostic | Value |
| --- | ---: |
| Target count | 1032 |
| Comparable target count | 1032 |
| Ready target count | 1032 |
| Blocked target count | 0 |
| Insufficient TRAIN support | 0 |
| Unseen group targets | 0 |
| Negative VALIDATION actual count | 0 |

| Metric | Value | Status | Reason |
| --- | ---: | --- | --- |
| MAE | 3114.774317 | COMPUTED | NONE |
| WAPE | 0.481956 | COMPUTED | NONE |
| sMAPE | 0.595950 | COMPUTED | NONE |

Scoring identities:

    SCORING_TARGET_ACTUAL_SET_SHA256=d34ab2b126854baaf330ddaa0faaca05b4a1fcf16672d8f5b11705e2787e7e77
    SCORING_INPUT_SHA256=7558fae7092c80dcc3ff075e197175e5818054c105ccdf53591514f888f19916
    METRIC_RESULT_SET_SHA256=95136cf25aeddc97e7f4dd4f82d4c95dd2fae842c0f44396fea0e3f23229ee03
    SCORE_PACKAGE_SHA256=4476af59a1cdd4ceed5d572f918b542c70decf489313bdcf937ab232a595d251

The scorer-local actual domain remained in force:

    VALIDATION_ACTUAL_FINITE_DECIMAL_REQUIRED=true
    VALIDATION_ACTUAL_NONNEGATIVE_PRECONDITION_REQUIRED=true
    NEGATIVE_VALIDATION_ACTUAL_BLOCKER=NEGATIVE_VALIDATION_ACTUAL
    NEGATIVE_VALIDATION_ACTUAL_ACTION=STRUCTURAL_FAIL_CLOSED
    NEGATIVE_VALIDATION_ACTUAL_IS_NOT_ZERO=true
    UPSTREAM_NONNEGATIVE_GUARANTEE_CLAIMED=false

WAPE remained:

    WAPE=sum(absolute_error_i) / sum(actual_i)

## 6. Deterministic replay

Two runs used the identical runner commit, committed R4 authority directory,
execution-main SHA, database binding, and command. Both returned
EXECUTION_STATUS=PASS, VALIDATION_BASELINE_SCORED=true, and
TEST_REMAINS_SEALED=true.

    LIVE_SCORING_REPLAY_COUNT=2
    LIVE_SCORING_REPLAY_STATUS=PASS

The complete sanitized aggregate JSON payloads were byte-identical. Their
external temporary payload SHA-256 was:

    7447baa8045ea10bdc936f997c68351f690e61494619d47515c6b75c433419dd

No raw XLS, database dump, TEST bytes, raw source rows, or per-target values
were committed.

## 7. Boundary and handoff statements

    VALIDATION_BASELINE_SCORED=true
    FARM_TOTAL_BASELINE_MAE_EXECUTED=true
    FARM_TOTAL_BASELINE_WAPE_EXECUTED=true
    FARM_TOTAL_BASELINE_SMAPE_EXECUTED=true
    FARM_TOTAL_BASELINE_MAPE_EXECUTED=false
    FARM_TOTAL_BASELINE_BIAS_EXECUTED=false
    FARM_TOTAL_BASELINE_COVERAGE_EXECUTED=false
    BASELINE_VS_INCUMBENT_COMPARISON_EXECUTED=false
    S3_C_BACKTEST_EXECUTION=false
    S3_METRIC_EXECUTION=false
    TEST_EVALUATION=false
    TEST_REMAINS_SEALED=true
    TEST_PAYLOAD_RETURNED=false
    MODEL_CHANGE=false
    PARAMETER_CHANGE=false
    MIGRATION_CHANGE=false
    SCHEMA_CHANGE=false
    V0_3_S4_AUTHORIZED=false
    NEXT_AGENT_REQUIRES_CLOUD_TMP_AUTHORITY=false
    NEXT_AGENT_REQUIRES_CURSOR_HISTORY=false
    NEXT_AGENT_REQUIRES_RECONSTRUCTION=false
    R4_AUTHORITY_AVAILABLE_FROM_GIT=true
    R4_AUTHORITY_SOURCE_WORKBOOK_BOUND_BY_SHA256=true
    READY_AUTHORIZED=false
    MERGE_AUTHORIZED=false
    NO_STEP_IMPLIES_THE_NEXT=true
