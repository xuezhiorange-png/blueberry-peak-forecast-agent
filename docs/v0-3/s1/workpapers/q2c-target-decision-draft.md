# V0.3-S1 Q2C Target Decision Draft

## Workpaper identity and status

```text
WORKPAPER_ID=V0_3_S1_Q2C_TARGET_DECISION_DRAFT
BASE_MAIN_SHA=0d4aa3f6dc90f9014bbcf43aa73e2bb2248d16aa
WORKPAPER_STATUS=DRAFT_ONLY
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
CURRENT_V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
```

This workpaper records only the business information confirmed in the current
planning conversation. It is not a signed source attestation, does not issue a
Q2C decision, and does not close any S1 Gate.

## Draft target and physical meaning

```text
TARGET_PHYSICAL_EVENT=田间商品果完成有效称重
QUANTITY_BASIS=商品果净重
QUANTITY_UNIT=kg
WEIGHING_POINT=田间采摘点
MARKETABILITY_BOUNDARY=仅统计商品果
FIELD_SORTING_RULE=田间剔除的非商品果不计入
PACKHOUSE_SORTING_RULE=加工厂后续分选不追溯调整
REJECTED_FRUIT_RULE=加工厂拒收或退货不追溯调整
FARM_TIMEZONE=Asia/Shanghai
```

The draft target is the field-side marketable-fruit weighing event. Factory
receipt, later packhouse sorting, factory rejection, and returned fruit are not
used to retroactively change this field-side quantity in this draft.

The draft does not assert that the source system has already proven the event,
weighing point, marketability boundary, or post-harvest treatment. Those facts
remain subject to formal source authority and Q2C evidence.

## Canonical evaluation grain

```text
CANONICAL_GRAIN=
SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE

PLOT_SUPPORTED=false
```

The `果径` source dimension is not part of this target grain. It is retained as
a source dimension for the conversion step described below and is aggregated
before the canonical target quantity is formed.

## Season handling draft

```text
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
2024~2025产季约为2024年8月至2025年6月
后续产季按类似跨年度月份范围维护
SEASON_EXACT_DATE_BOUNDARIES=NOT_PROVIDED
```

The season statement is intentionally approximate. This workpaper does not
invent a start day, end day, month-end rule, or any other exact date boundary.

## Q2C closure boundary

The following remain unresolved and prevent a formal Q2C decision:

- formal source authority and attestation;
- exact season date boundaries;
- scale, tare, precision, calibration, decimal, and rounding evidence;
- formal correction, void, late-entry, missing-day, and final-confirmation
  rules;
- source snapshot, schema, attestation, and decision identities or hashes;
- aggregate coverage and data-quality evidence.

```text
CURRENT_Q2C_PHYSICAL_ALIGNMENT_STATUS=BLOCKED
Q2C_DECISION_STATUS=NOT_ISSUED
Q2C_DECISION_HASH=NOT_ISSUED
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
```
