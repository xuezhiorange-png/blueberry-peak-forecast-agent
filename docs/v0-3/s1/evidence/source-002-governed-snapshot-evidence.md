# V0.3-S1 Source 002 Governed Snapshot Evidence

## Evidence identity and boundary

```text
EVIDENCE_RECORD_ID=V0_3_S1_SOURCE_002_GOVERNED_SNAPSHOT_EVIDENCE
EVIDENCE_RECORD_STATUS=PREPARATION_ONLY_PENDING_FORMAL_ATTESTATION
BASELINE_MAIN_SHA=431a88fb4b542264fcf60d95a840202cc578f394
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
HASH_ALGORITHM=SHA-256
RAW_SOURCE_IMMUTABLE=true
REAL_DATA_ALLOWED_IN_GIT=false
```

This record is a non-row-level preparation artifact. It records aggregate and
identity evidence already generated during the separately authorized read of
Source 002. This task did not reopen, copy, parse, or recalculate the source
file. It does not create a business attestation, source cohort manifest, or
source authority acceptance.

```text
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
REAL_SOURCE_EXPORT_READ_PERFORMED=true
REAL_BUSINESS_ROW_LEVEL_DATA_READ_PERFORMED=true
REAL_BUSINESS_ROW_LEVEL_DATA_IMPORTED=false
DATABASE_WRITE=false
```

## Source and schema identity

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_EFFECTIVE_SEASON=2024~2025产季起
SPREADSHEET_IS_INDEPENDENT_SOURCE=false
SPREADSHEET_ROLE=扫码系统导出、汇总或整理副本

SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_BYTE_COUNT=28668416
FILE_FORMAT=CDFV2 Microsoft Excel (.xls)
SHEET_COUNT=4
SOURCE_ROW_COUNT=233171

OBSERVED_SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_SHA256=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
ACTUAL_HEADER_SCHEMA=时间,链路,农场,分场,品种,果径,入库公斤数
EXPECTED_FIELD_COUNT=7
OBSERVED_EXPECTED_FIELD_COUNT=7
MISSING_EXPECTED_FIELDS=[]
```

The hashes are source-object and observed-schema identities. They are not an
attestation hash, cohort manifest hash, or acceptance record hash.

## Canonical-grain and field support

```text
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
HARVEST_BUSINESS_DATE_SUPPORTED=true
FARM_SUPPORTED=true
SUBFARM_SUPPORTED=true
VARIETY_SUPPORTED=true
CHAIN_PROVENANCE_SUPPORTED=true
FRUIT_SIZE_SOURCE_AGGREGATION_SUPPORTED=true
CAN_SUPPORT_CANONICAL_GRAIN=true
```

The source `果径` dimension is retained as a source dimension and is not part
of the canonical grain. `链路` remains provenance and is not part of the
canonical grain.

## Aggregate coverage evidence

The season rule is the current draft business calendar: August 1 through June
30, inclusive; July is not automatically assigned.

```text
FIRST_HARVEST_BUSINESS_DATE=2025-07-22
LAST_HARVEST_BUSINESS_DATE=2026-04-16

MAPPED_COVERAGE_SEASON_COUNT=1
MAPPED_SEASON_IDENTITIES=[2025~2026]

COVERAGE_FARM_COUNT=84
COVERAGE_SUBFARM_COUNT=192
COVERAGE_VARIETY_COUNT=20
MAPPED_CANONICAL_GROUP_COUNT=529

UNMAPPED_ROW_COUNT=2
UNMAPPED_DISTINCT_DATE_COUNT=1
UNMAPPED_FIRST_DATE=2025-07-22
UNMAPPED_LAST_DATE=2025-07-22
UNMAPPED_CANONICAL_GROUP_COUNT=2

JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
JULY_POLICY_RESOLVED=false
UNMAPPED_DATE_POLICY=PENDING
```

The two July rows remain unmapped. They are not deleted, assigned to the
previous or next season, converted to zero, or counted as a formal season
identity. `UNMAPPED_CANONICAL_GROUP_COUNT` is a descriptive count of distinct
farm/subfarm/variety combinations among those July rows; it is not a formal
`SEASON × FARM × SUBFARM × VARIETY` season-group count.

```text
DESCRIPTIVE_CALENDAR_GAP_COUNT=31455
CANONICAL_MISSING_DAY_METADATA_STATUS=DESCRIPTIVE_ONLY_NOT_FORMAL_MISSINGNESS_EVIDENCE
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
NO_RECORD_TO_ZERO_MAPPING_STATUS=BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
FORMAL_MISSING_DAY_RULE_STATUS=PENDING
```

The descriptive calendar-gap value is not a formal missing-day count, data
error count, business no-harvest count, or zero-fill instruction.

## Coverage-scope preparation boundary

The following is a preparation-only aggregate view. It is not the formal
`coverage_scope` authority object because the current schema requires concrete
season, farm, subfarm, and variety identity arrays, while this package does
not commit row-derived entity lists.

```text
COVERAGE_SCOPE_CANDIDATE_STATUS=PREPARATION_ONLY_PARTIAL
COVERAGE_SCOPE_MAPPED_SEASONS=[2025~2026]
COVERAGE_SCOPE_OBSERVED_BUSINESS_DATE_START=2025-07-22
COVERAGE_SCOPE_OBSERVED_BUSINESS_DATE_END=2026-04-16
COVERAGE_SCOPE_FARM_COUNT=84
COVERAGE_SCOPE_SUBFARM_COUNT=192
COVERAGE_SCOPE_VARIETY_COUNT=20
COVERAGE_SCOPE_KNOWN_BOUNDARIES=
  SOURCE_002_ONLY,
  JULY_2025-07-22_UNMAPPED_2_ROWS_1_DISTINCT_DATE,
  COUNTS_ARE_AGGREGATE_ONLY,
  FORMAL_ENTITY_IDENTITY_ARRAYS_NOT_ISSUED
COVERAGE_SCOPE_ENTITY_ID_LISTS=BLOCKED_PENDING_APPROVED_MAPPING_EVIDENCE
```

No farm, subfarm, or variety name list is included. A later authorized
mapping/custody step must decide whether formal scope identity arrays may be
retained as governed non-sensitive identifiers.

## Quantity precision evidence

```text
QUANTITY_UNIT=kg
BUSINESS_CONFIRMED_SOURCE_QUANTITY_PRECISION=0.001 kg
SOURCE_QUANTITY_PRECISION=0.001 kg
SOURCE_QUANTITY_PRECISION_STATUS=BUSINESS_CONFIRMED_AND_SOURCE_002_OBSERVED
SOURCE_QUANTITY_PRECISION_GAP=false
SOURCE_QUANTITY_DECIMAL_PLACES=3
SOURCE_QUANTITY_INTEGER_ROUNDING=false
SOURCE_QUANTITY_ROUNDING_RULE=保留三位小数，不取整
WEIGHT_MAX_OBSERVED_DECIMAL_PLACES=3
WEIGHT_MORE_THAN_3_DECIMAL_ROW_COUNT=0
WEIGHT_PRECISION_CONTRACT_GAP=false
SCALE_DEVICE_PRECISION=NOT_PROVIDED
SCALE_DEVICE_PRECISION_BUSINESS_RULE_STATUS=NOT_CONFIRMED
SCALE_DEVICE_PRECISION_FORMAL_EVIDENCE_STATUS=PENDING
SCALE_VERIFICATION_STATUS=BUSINESS_CONFIRMED
SCALE_VERIFICATION_STATEMENT=称重设备均已检定
```

The `0.001 kg` value is the accepted Source 002 business/source quantity
representation result. It records the exported quantity's three-decimal
representation and does not by itself establish scale resolution, minimum
division, device precision, calibration precision, a calibration certificate,
or a formal measurement authority record. The separate device-precision
evidence remains pending.

## Authority, custody, and Git boundary

```text
SOURCE_AUTHORITY_STATUS=NOT_ISSUED
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
FORMAL_CUSTODY_RECORD_STATUS=BLOCKED
FORMAL_ATTESTATION_HASH=NOT_ISSUED
FORMAL_COHORT_MANIFEST_HASH=NOT_ISSUED

SOURCE_SNAPSHOT_REFERENCE_IS_OPAQUE=true
PRIVATE_LOCATOR_COMMITTED_TO_GIT=false
RAW_SOURCE_FILE_COMMITTED_TO_GIT=false
RAW_ROWS_COMMITTED_TO_GIT=false
ROW_LEVEL_DERIVED_DATA_COMMITTED_TO_GIT=false
PERSONAL_IDENTITY_COMMITTED_TO_GIT=false
CREDENTIALS_COMMITTED_TO_GIT=false
```

The snapshot reference is an opaque governed identity only. No local path,
private URL, bucket path, credential, personal identity, raw workbook, raw
row, or row-level extract is part of this record.

## Preparation result and governance state

```text
SOURCE_002_SCHEMA_VALIDATION_ACCEPTABLE=true
SOURCE_002_COVERAGE_METADATA_USABLE_FOR_PREPARATION=true
SOURCE_002_FORMAL_ATTESTATION_READY=false
SOURCE_002_FORMAL_COHORT_READY=false

Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S1_ACCEPTANCE_STATUS=BLOCKED
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

This preparation evidence may support the next formalization review; it does
not close source authority, cohort freeze, Q2C, visibility, revision, custody,
quality, holdout, or independent-review gates.

## Next package boundary

The next package is scoped only to the actual-harvest label lifecycle produced
by the scan-and-weigh source. It does not claim that the full S1 visibility
gate is closed; that gate also covers the other contract-defined source
classes.

```text
ACTUAL_LABEL_LIFECYCLE_NEXT_PACKAGE_SCOPE_DEFINED=true
NEXT_PACKAGE=V0_3_S1_ACTUAL_HARVEST_LABEL_RECORD_LIFECYCLE_AND_POINT_IN_TIME_AUTHORITY_FREEZE
ACTUAL_LABEL_VISIBILITY_CLOSED=false
S1_VISIBILITY_GATE_CLOSED=false
S1_VISIBILITY_FULL_CLOSURE_NOT_CLAIMED=true
```

The actual-label package may advance source record identity, recorded and
available time, revision/lineage, finalization, cancellation, late-entry, and
winner compatibility evidence. It does not authorize lifecycle implementation
or any new source read.
