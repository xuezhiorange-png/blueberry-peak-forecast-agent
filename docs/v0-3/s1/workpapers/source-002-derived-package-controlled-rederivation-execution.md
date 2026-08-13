# Source 002 controlled rederivation execution

## Result

```text
TASK=SOURCE_002_DERIVED_VALUE_PACKAGE_CONTROLLED_REDERIVATION
BASE_MAIN_SHA=86bb514b23ab21e4930d01057ce1d516a9faa616
RESULT=BLOCKED_EXACT_FROZEN_SOURCE_BINDING_UNRESOLVED
```

The controlled rederivation is authorized, but it has not been executed because the exact frozen seven-column Source002 object has not been rebound to accessible bytes.

## What was recovered

The user's File Library does contain the previously uploaded historical workbook:

```text
HISTORICAL_UPSTREAM_WORKBOOK_FOUND=true
HISTORICAL_UPSTREAM_WORKBOOK_TITLE=原果入库汇总表到加工厂_1.xls
HISTORICAL_UPSTREAM_WORKBOOK_FORMAT=.xls
HISTORICAL_UPSTREAM_WORKBOOK_SHEET_COUNT=4
HISTORICAL_UPSTREAM_HEADER=时间,链路,农场,分场,品种,果径,入库公斤数,加工厂
```

This workbook is clearly from the same scan/weigh data family, but it contains an additional `加工厂` field. It is therefore not silently substituted for the frozen Source002 object.

## Frozen Source002 identity

```text
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
SOURCE_ROW_COUNT=233171
SOURCE_FORMAT=CDFV2 Microsoft Excel (.xls)
SOURCE_SHEET_COUNT=4
SOURCE_HEADER=时间,链路,农场,分场,品种,果径,入库公斤数
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
```

The earliest Git evidence records that these identities were machine-generated during a separately authorized read before PR #175, but that prior runtime did not persist the input file name or an accessible byte binding in Git.

## Fail-closed boundary

```text
UPSTREAM_WORKBOOK_USED_AS_EXACT_SOURCE002=false
EXTRA_FACTORY_COLUMN_DROPPED_TO_RECONSTRUCT_SOURCE002=false
EXACT_SOURCE002_BYTES_REBOUND=false
SOURCE002_SHA256_RECOMPUTED=false
ROW_LEVEL_REDERIVATION_PERFORMED=false
IDENTITY_ARRAY_VALUES_REDERIVED=false
V2_PACKAGE_CREATED=false
```

Dropping `加工厂` from the historical workbook would be a reconstruction unless a governed upstream-to-frozen transformation binding is proven. The merged PR #215 contract does not allow that substitution or reconstruction.

## State remains unchanged

```text
READY_FOR_FINAL_FIELD_BINDING_COUNT=4
BLOCKED_FINAL_FIELD_BINDING_COUNT=3
ALL_7_FIELDS_READY=false
SOURCE_AUTHORITY_ACCEPTED=false
CURRENT_CANONICAL_GATE_PASS_COUNT=0
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
```

This PR remains Draft. Independent review, Ready, Merge, final binding, Source Authority acceptance, Remaining06, and V0.3 S2 are not performed by this correction.
