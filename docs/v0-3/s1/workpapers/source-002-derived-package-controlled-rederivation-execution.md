# Source 002 controlled reconstruction verification

## Result

```text
TASK=SOURCE_002_RECOVERED_UPSTREAM_TO_FROZEN_CONTROLLED_RECONSTRUCTION_AND_BINDING
BASE_MAIN_SHA=86bb514b23ab21e4930d01057ce1d516a9faa616
RESULT=PARTIAL_RECONSTRUCTION_VERIFICATION_BLOCKED_FULL_ROWSET_ACCESS
```

This gate was separately authorized after the upstream workbook was recovered from the user's prior uploads.

## Recovered upstream

```text
WORKBOOK_FOUND=true
WORKBOOK_TITLE=原果入库汇总表到加工厂_1.xls
OBSERVED_SHEET_COUNT=4
OBSERVED_FIELDS=时间,链路,农场,分场,品种,果径,入库公斤数,加工厂
LAST_BUSINESS_DATE_2026_04_16_OBSERVED=true
```

The recovered workbook is the historical scan/weigh data family used by the project. Its business schema contains the seven frozen Source002 fields plus `加工厂`.

## Authorized deterministic projection

```text
PROJECTION=DROP_FACTORY_COLUMN_ONLY
DROP_FIELD=加工厂
RETAIN_FIELDS_IN_ORDER=时间,链路,农场,分场,品种,果径,入库公斤数
VALUE_NORMALIZATION_ALLOWED=false
ROW_REORDERING_ALLOWED=false
SHEET_REORDERING_ALLOWED=false
```

The projected field schema exactly matches the frozen Source002 field schema.

## Verified parity

```text
SHEET_COUNT_PARITY=PASS
PROJECTED_SCHEMA_PARITY=PASS
LAST_BUSINESS_DATE_PARITY=PASS
```

## Parity not yet computable from the available File Library execution surface

The File Library exposes searchable/parsed workbook content, but it does not expose the complete rowset or original workbook bytes to the deterministic execution runtime used in this task. Therefore the following values are not reported as passing:

```text
SOURCE_ROW_COUNT_PARITY=NOT_VERIFIED
CANONICAL_SCOPE_ROW_COUNT_PARITY=NOT_VERIFIED
UNMAPPED_2025_07_22_TWO_ROW_PARITY=NOT_VERIFIED
FARM_84_AND_ARRAY_HASH_PARITY=NOT_VERIFIED
SUBFARM_192_AND_ARRAY_HASH_PARITY=NOT_VERIFIED
VARIETY_20_AND_ARRAY_HASH_PARITY=NOT_VERIFIED
FIRST_RAW_DATE_2025_07_22_PARITY=NOT_VERIFIED
CANONICAL_START_DATE_2025_08_05_PARITY=NOT_VERIFIED
FULL_SEMANTIC_RECONSTRUCTION_PARITY=BLOCKED
```

No failed parity is inferred from an unverified item.

## Historical binary identity boundary

The historical seven-column Source002 object remains identified by its governed SHA-256 and byte count. A newly serialized reconstruction is not expected to recreate those historical workbook bytes, so historical binary SHA equality is not used as proof that a newly serialized workbook is the original object. This task seeks semantic reconstruction parity against the previously governed row count, dates, canonical scope, and identity-array hashes.

## Package and downstream state

```text
FULL_PROJECTED_DATASET_MATERIALIZED=false
V2_PACKAGE_CREATED=false
READY_FOR_FINAL_FIELD_BINDING_COUNT=4
BLOCKED_FINAL_FIELD_BINDING_COUNT=3
SOURCE_AUTHORITY_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

The PR remains Draft. Independent review, Ready, Merge, final binding, Source Authority acceptance, Remaining06, and V0.3 S2 remain separate actions.
