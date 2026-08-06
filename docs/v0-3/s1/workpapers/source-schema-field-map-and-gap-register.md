# V0.3-S1 Source Schema Field Map and Gap Register

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_SOURCE_SCHEMA_FIELD_MAP_AND_GAP_REGISTER
BASE_MAIN_SHA=0d4aa3f6dc90f9014bbcf43aa73e2bb2248d16aa
WORKPAPER_STATUS=DRAFT_ONLY
CURRENT_SOURCE_AUTHORITY_BINDING_STATUS=BLOCKED
CURRENT_SOURCE_COHORT_FREEZE_STATUS=BLOCKED
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This map describes the intended source-to-target roles from the confirmed
business information. It does not read or include source rows and does not
issue a source schema, source snapshot, cohort manifest, or Q2C result.

## Confirmed source field map

| Source field | Confirmed business meaning | Draft target or handling role | Grain treatment |
| --- | --- | --- | --- |
| 时间 | 采摘日期 | `HARVEST_BUSINESS_DATE` candidate | Enters the canonical date dimension after season matching. |
| 链路 | 旗舰公司名称 | Source provenance and traceability | Does not enter the canonical target grain. |
| 农场 | 农场 | `FARM` | Enters the canonical grain. |
| 分场 | 分场 | `SUBFARM` | Enters the canonical grain. |
| 品种 | 品种 | `VARIETY` | Enters the canonical grain. |
| 果径 | 来源维度 | Source dimension for aggregation | Does not enter the canonical target grain. |
| 入库公斤数 | 田间扫码称重形成的商品果净重 | `QUANTITY_BASIS=商品果净重`, unit `kg` | Aggregated before the canonical target quantity is formed. |

The source label `入库公斤数` is mapped according to the confirmed business
meaning above; this workpaper does not infer any additional warehouse or
factory event from the label.

## Conversion draft

```text
1. 按采摘日期匹配产季
2. 同一产季、农场、分场、品种、采摘日期下，对各果径公斤数求和
3. 链路仅用于旗舰公司来源追溯，不进入目标粒度
```

The resulting draft grain is:

```text
SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

The season rule is intentionally limited to the confirmed precision:

```text
2024~2025产季约为2024年8月至2025年6月
后续产季按类似跨年度月份范围维护
SEASON_EXACT_DATE_BOUNDARIES=NOT_PROVIDED
```

No exact start day, end day, or month-end default is introduced.

## Evidence gap register

| Gap or decision field | Current draft state | Required later evidence |
| --- | --- | --- |
| `SOURCE_VERSION` | `NOT_PROVIDED` | Governed source version identity. |
| `SOURCE_SNAPSHOT_REFERENCE` | `NOT_ISSUED` | Immutable, non-sensitive snapshot identity. |
| `SCHEMA_VERSION` | `NOT_PROVIDED` | Source schema version. |
| `SCHEMA_HASH` | `NOT_ISSUED` | Non-sensitive schema hash. |
| `ATTESTATION_VERSION` | `NOT_PROVIDED` | Versioned source attestation. |
| `ATTESTATION_EFFECTIVE_AT` | `NOT_PROVIDED` | Attestation effective timestamp. |
| `ATTESTATION_HASH` | `NOT_ISSUED` | Hash of the governed attestation. |
| `TARE_POLICY` | `NOT_PROVIDED` | Tare handling rule. |
| `SCALE_PRECISION` | `NOT_PROVIDED` | Scale precision evidence. |
| `SCALE_CALIBRATION_AUTHORITY` | `NOT_PROVIDED` | Calibration authority evidence. |
| `DECIMAL_PRECISION_AND_ROUNDING` | `NOT_PROVIDED` | Decimal and rounding rule. |
| `LATE_ENTRY_RULE` | `NOT_PROVIDED` | Late-entry and visibility rule. |
| `MISSING_DAY_RULE_EVIDENCE` | `NOT_PROVIDED` | Evidence for missing-day semantics. |
| `CORRECTION_RULE` | `NOT_PROVIDED` | Formal correction rule. |
| `VOID_RULE` | `NOT_PROVIDED` | Formal void rule. |
| `FINAL_CONFIRMATION_RULE` | `NOT_PROVIDED` | Final confirmation rule. |
| `REVISION_POLICY_VERSION` | `NOT_PROVIDED` | Versioned revision policy. |
| `WITHDRAWAL_POLICY_VERSION` | `NOT_PROVIDED` | Versioned withdrawal policy. |
| `VOID_PROPAGATION_POLICY_VERSION` | `NOT_PROVIDED` | Versioned void propagation policy. |
| `SEASON_EXACT_DATE_BOUNDARIES` | `NOT_PROVIDED` | Exact cross-year season boundaries. |
| `COVERAGE_SEASON_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_FARM_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_SUBFARM_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `COVERAGE_VARIETY_COUNT` | `NOT_PROVIDED` | Aggregate coverage statistic. |
| `FIRST_HARVEST_BUSINESS_DATE` | `NOT_PROVIDED` | Aggregate coverage boundary. |
| `LAST_HARVEST_BUSINESS_DATE` | `NOT_PROVIDED` | Aggregate coverage boundary. |
| `SOURCE_ROW_COUNT` | `NOT_PROVIDED` | Declared source metadata only; not S2 accepted row count. |
| `MISSING_DAY_COUNT` | `NOT_PROVIDED` | Aggregate quality statistic. |
| `MISSING_DATA_PROPORTION` | `NOT_PROVIDED` | Aggregate quality statistic. |

The following identities are deliberately not issued or calculated:

```text
Q2C_DECISION_HASH=NOT_ISSUED
SCHEMA_HASH=NOT_ISSUED
SOURCE_SNAPSHOT_HASH=NOT_ISSUED
ATTESTATION_HASH=NOT_ISSUED
```

## Current boundary and authorization

```text
BUSINESS_REPORTED_ERROR_SCENARIO=NOT_OBSERVED
BUSINESS_REPORTED_DUPLICATE_SCENARIO=CONTROLLED_BY_QR_WORKFLOW
FORMAL_CORRECTION_POLICY=NOT_PROVIDED
FORMAL_VOID_POLICY=NOT_PROVIDED

REAL_BUSINESS_ROW_LEVEL_DATA_READ=false
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_DATA_ACCESSED=false
PRODUCTION_DATABASE_ACCESSED=false
LOCAL_BUSINESS_DATABASE_ACCESSED=false
```

The business-reported statements are not formal correction or void evidence.
This gap register does not authorize S1 acceptance, S2, TEST, external holdout,
or any production change.
