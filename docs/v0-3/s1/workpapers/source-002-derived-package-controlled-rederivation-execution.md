# Source 002 controlled rederivation execution

## Result

```text
TASK=SOURCE_002_DERIVED_VALUE_PACKAGE_CONTROLLED_REDERIVATION
BASE_MAIN_SHA=86bb514b23ab21e4930d01057ce1d516a9faa616
RESULT=REDERIVATION_PASS_CANDIDATE_PACKAGE_CREATED_CUSTODY_HANDOFF_PENDING
```

The exact frozen Source002 object was rebound and read directly. No similarity-selected workbook or alternate source was used.

## Exact source identity parity

```text
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_SHA256_PARITY=PASS
SOURCE_BYTE_COUNT=28668416
SOURCE_BYTE_COUNT_PARITY=PASS
SOURCE_ROW_COUNT=233171
SOURCE_ROW_COUNT_PARITY=PASS
SOURCE_SHEET_COUNT=4
SOURCE_SHEET_COUNT_PARITY=PASS
SOURCE_SHEET_DATA_ROW_COUNTS=65535,65535,65535,36566
SOURCE_HEADER=时间,链路,农场,分场,品种,果径,入库公斤数
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SCHEMA_PARITY=PASS
```

## Canonical scope parity

```text
RAW_BUSINESS_DATE_START=2025-07-22
RAW_BUSINESS_DATE_END=2026-04-16
UNMAPPED_2025_07_22_ROW_COUNT=2
CANONICAL_SCOPE_ROW_COUNT=233169
CANONICAL_BUSINESS_DATE_START=2025-08-05
CANONICAL_BUSINESS_DATE_END=2026-04-16
CANONICAL_SCOPE_PARITY=PASS
```

The two July rows remain raw-source rows and are excluded from the mapped `2025~2026` canonical S1 scope. No reassignment or zero fill was performed.

## Identity-array rederivation parity

Identity values were read from the exact raw columns, with no normalization, aliasing, spelling correction, merge, null replacement, or silent reassignment. Arrays were deterministically Unicode-lexically sorted and hashed as UTF-8 compact JSON arrays with `ensure_ascii=false`.

```text
FARM_COUNT=84
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
FARMS_PARITY=PASS

SUBFARM_COUNT=192
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
SUBFARMS_PARITY=PASS

VARIETY_COUNT=20
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
VARIETIES_PARITY=PASS
```

Full arrays are not committed to Git.

## V2 candidate package

A new candidate package was materialized outside Git from this exact-source rederivation:

```text
CANDIDATE_PACKAGE_ID=source-002-attestation-derived-values-v2-rederived
CANDIDATE_PACKAGE_STATUS=PARTIAL_DERIVATION_MISSING_DAY_FORMULA_AUTHORITY
CANDIDATE_PACKAGE_SHA256=9220ec20bd9d2fb3e466ad8936382327e045a4ba09df99a0f06d42b0aa5da19f
CANDIDATE_PACKAGE_BYTE_COUNT=9944
RAW_ROWS_IN_PACKAGE=false
FULL_IDENTITY_ARRAYS_IN_GIT=false
```

The package hash is SHA-256 over UTF-8 recursively key-sorted compact canonical JSON excluding the self `package_sha256` field.

## Remaining custody boundary

The rederivation itself passed. The package is not yet usable for final field binding because durable external custody handoff and a durable opaque non-sensitive custody reference have not been completed.

```text
DURABLE_EXTERNAL_CUSTODY_HANDOFF_COMPLETE=false
DURABLE_EXTERNAL_LOCATOR_RECORDED=false
USABLE_FOR_FINAL_FIELD_BINDING=false
STOP_CONDITION=DURABLE_EXTERNAL_CUSTODY_HANDOFF_PENDING
```

The two missing-day fields remain unresolved because no unique missing-day formula/denominator authority has been issued.

## Downstream state unchanged

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

This PR remains Draft. Independent review, Ready, Merge, durable custody completion, final field binding, Source Authority acceptance, Remaining06, and V0.3 S2 remain separate actions.
