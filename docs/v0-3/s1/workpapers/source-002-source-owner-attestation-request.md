# Source 002 Source-Owner Attestation Request

## Purpose and boundary

```text
WORKPAPER_ID=V0_3_S1_SOURCE_002_SOURCE_OWNER_ATTESTATION_REQUEST
WORKPAPER_STATUS=READINESS_REQUEST_ONLY_NOT_ATTESTATION
TARGET_GATE_ID=S1-SOURCE-AUTHORITY
AUDITED_MAIN_SHA=ca3cbd936d50466ae1a35390fe2717e930df367d
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_OWNER_ATTESTATION_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
S1_SOURCE_AUTHORITY_CANONICAL_GATE_PASS=false
```

This form records the exact information that must be confirmed or supplied
before a final `business-source-attestation.json` can be issued. It is not an
attestation, does not identify a person, and does not change any canonical S1
gate.

The current repository contains aggregate, non-sensitive Source 002 evidence
only. It does not contain the actual farm, subfarm, or variety arrays, and this
task does not authorize reading the raw source or deriving row-level dates.

## Schema inventory and recomputed readiness

The canonical schema is
`docs/v0-3/s1/schemas/business-source-attestation.schema.json`.

```text
SCHEMA_REQUIRED_TOP_LEVEL_FIELD_COUNT=36
SCHEMA_REQUIRED_NESTED_FIELD_COUNT=26
SCHEMA_REQUIRED_LEAF_COUNT=57
SCHEMA_REQUIRED_PATH_COUNT_INCLUDING_OBJECT_CONTAINERS=62
LEAF_COUNT_DEFINITION=31 primitive required top-level scalar/array fields plus 26 nested leaves; five nested object containers are counted separately

CLASS_A_GOVERNED_VALUE_PRESENT_COUNT=2
CLASS_B_GOVERNED_VALUE_PRESENT_REQUIRES_SOURCE_OWNER_ATTESTATION_COUNT=37
CLASS_C_SOURCE_OWNER_VALUE_MISSING_COUNT=6
CLASS_D_SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED_COUNT=9
CLASS_E_LATER_GATE_VALUE_NOT_REQUIRED_FOR_SOURCE_AUTHORITY_COUNT=3
CLASS_F_NOT_SCHEMA_REQUIRED_COUNT=6

GOVERNED_VALUE_PRESENT_COUNT=39
SOURCE_OWNER_ATTESTATION_REQUIRED_COUNT=52
SOURCE_OWNER_VALUE_MISSING_COUNT=6
SOURCE_DATA_DERIVATION_REQUIRED_COUNT=9
UNRESOLVED_REQUIRED_FIELD_COUNT=15
DEFERRED_REQUIRED_FIELD_COUNT=3

FINAL_ATTESTATION_SCHEMA_READY=false
FINAL_ATTESTATION_ISSUANCE_READY=false
CANONICAL_GATE_CLOSURE_ELIGIBLE=false
```

The readiness artifact contains the complete 57-leaf matrix, including each
schema path, current value, evidence source, authority role, repository-proof
flag, owner-confirmation flag, source-object access flag, legal-population
flag, classification, and rationale:

`docs/v0-3/s1/evidence/source-002-attestation-issuance-readiness.json`

## A. Fixed values requiring source-owner confirmation

Please confirm that the following existing governed values describe the source
object and its use. Confirmation must be made by the role
`农场数据负责人`; no personal identity is requested in this repository.

### Source identity

```text
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_VERSION=scan-weight-export:v0_3_s1:002
SCHEMA_VERSION=observed-source-schema-v1
SCHEMA_HASH=919e63c4d3b4d00b304a045f63bfb050d4eb9abec3b0a318186b7ca2e7276867
SOURCE_SNAPSHOT_REFERENCE=snapshot:v0_3_s1:002
SOURCE_OWNER_ROLE=农场数据负责人
SOURCE_SHA256=fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a
SOURCE_ROW_COUNT=233171
SOURCE_BYTE_COUNT=28668416
```

### Recorded-label and time semantics

```text
PHYSICAL_EVENT=HARVEST
WEIGHING_POINT_AND_RELATION_TO_PICK=VALID_FIELD_SCAN_WEIGH_RECORD at 田间采收点; first valid governed scan-and-weigh record for the harvest business event
QUANTITY_BASIS=RECORDED_MARKETABLE_NET_WEIGHT
QUANTITY_UNIT=KG
ALL_PICKED_OR_MARKETABLE=MARKETABLE_ONLY
MEASUREMENT_METHOD=VALID_FIELD_SCAN_WEIGH_RECORD
FIELD_SORTING_RULE=田间剔除的非商品果不计入
PACKHOUSE_SORTING_RULE=加工厂后续分选不追溯调整
REJECTED_FRUIT_RULE=加工厂拒收或退货不追溯调整
FARM_TIMEZONE=Asia/Shanghai
LOCAL_DAY_BOUNDARY=LOCAL_CALENDAR_DAY_00_00_ASIA_SHANGHAI
MISSING_DAY_RULE=UNKNOWN_NOT_ZERO
```

### Scope and fixed policy references

```text
MAPPED_SEASONS=[2025~2026]
KNOWN_EXCLUSIONS=[NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE]
KNOWN_SCOPE_BOUNDARIES=[
  JULY_RETAINED_RAW_EXCLUDED_FROM_CANONICAL_S1_COHORT,
  NO_KNOWN_BUSINESS_EXCLUSIONS_AT_S1_SOURCE_SCOPE,
  S2_TECHNICAL_AND_DATA_QUALITY_EXCLUSIONS_SEPARATE
]
FARM_COUNT=84
SUBFARM_COUNT=192
VARIETY_COUNT=20
SOURCE_COHORT_IDENTITY_PACKAGE_SHA256=6f07bc878935060f57a2ef24318d6d3b17e27c7f096885f813ac80bed6ac9d10
FARMS_ARRAY_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARMS_ARRAY_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETIES_ARRAY_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
```

The counts and hashes do not substitute for the required arrays. The final
attestation cannot be populated with arrays reconstructed from those values.

## B. Missing values requiring source-owner input

Each item below is intentionally marked as `SOURCE_OWNER_INPUT_REQUIRED`.
No value is supplied by this workpaper.

```text
ATTESTATION_VERSION=SOURCE_OWNER_INPUT_REQUIRED
ATTESTATION_EFFECTIVE_AT=SOURCE_OWNER_INPUT_REQUIRED
ATTESTATION_STATUS=SOURCE_OWNER_INPUT_REQUIRED
```

`ATTESTATION_STATUS` may become `ATTESTED` only as part of an actual owner
attestation event. `ATTESTATION_EFFECTIVE_AT` must be the attestation event
time, not the applicability start date.

The following policy-status leaves also require an explicit concrete value or
confirmation:

```text
WITHDRAWAL_STATUS_RULE=SOURCE_OWNER_INPUT_REQUIRED
VOID_STATUS_RULE=SOURCE_OWNER_INPUT_REQUIRED
ATTESTATION_HASH=SOURCE_OWNER_INPUT_REQUIRED
```

`ATTESTATION_HASH` must be computed by the final issuance process over the
truthful final payload. It must not be guessed or copied from another artifact.
The existing policy identities remain available for confirmation:

```text
REVISION_POLICY_VERSION=source-002-idfl-revision-policy-v1
WITHDRAWAL_POLICY_VERSION=source-002-withdrawal-policy-v1
VOID_PROPAGATION_POLICY_VERSION=source-002-void-propagation-policy-v1
REPLACEMENT_SOURCE_REQUIRES_NEW_IDENTITY=true
REPLACEMENT_SOURCE_REQUIRES_NEW_SHA256=true
DOWNSTREAM_WITHDRAWAL_PROPAGATION_REQUIRED=true
```

## C. Fields requiring source-data derivation

The following required values cannot be answered from governance text alone.
They are marked `SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED`; this task
does not read Source 002 raw data, row-level data, or a production database.

```text
COVERAGE_SCOPE_FARMS=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
COVERAGE_SCOPE_SUBFARMS=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
COVERAGE_SCOPE_VARIETIES=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
COVERAGE_SCOPE_BUSINESS_DATE_START=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
COVERAGE_SCOPE_BUSINESS_DATE_END=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
FIRST_HARVEST_BUSINESS_DATE=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
LAST_HARVEST_BUSINESS_DATE=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
MISSING_DAY_COUNT=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
MISSING_DATA_PROPORTION=SOURCE_DATA_DERIVATION_REQUIRED_NOT_AUTHORIZED
```

The stored values `84`, `192`, `20`, the three identity digests, and the
package digest are aggregate preparation evidence only. They do not authorize
identity-array generation. The observed maximum date is not a complete-through
watermark.

## D. Fixed-snapshot and completeness declaration

The source currently uses the following fail-closed description:

```text
SOURCE_002_COMPLETENESS_MODE=FIXED_SNAPSHOT_WITHOUT_ISSUED_COMPLETE_THROUGH_WATERMARK
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE=NOT_ISSUED
COMPLETENESS_DECLARATION_OWNER_ROLE=农场数据负责人
COMPLETENESS_DECLARATION_ISSUED=false
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
```

`产季结束核对` remains a reported business process, not a formally issued
declaration event. No observed maximum date is promoted to a watermark, and no
missing-day value is converted to zero. A final owner attestation must either
preserve this fixed-snapshot boundary in a schema-valid manner or supply an
explicitly authorized completeness/date value.

## E. Revision, withdrawal, and replacement policy

The current approved direction is:

- post-confirmation row revision is disabled for the immutable daily final-label
  boundary;
- post-confirmation row void is disabled as a silent mutation;
- replacement requires a new source identity and a new SHA-256;
- withdrawal and void propagation must reach downstream cohort, split,
  snapshot, and acceptance evidence;
- `source-002-idfl-revision-policy-v1`,
  `source-002-withdrawal-policy-v1`, and
  `source-002-void-propagation-policy-v1` are existing policy identities.

The concrete `WITHDRAWAL_STATUS_RULE` and `VOID_STATUS_RULE` remain
`SOURCE_OWNER_INPUT_REQUIRED`. The owner request must not invent a status
vocabulary or claim source-system void capability.

The schema-required `late_entry_rule`,
`revision_policy.winner_and_lineage_rule`, and `visibility_boundary` are
classified as `LATER_GATE_VALUE_NOT_REQUIRED_FOR_SOURCE_AUTHORITY` for the
current Source 002 IDFL label-side scope. They remain visible in the readiness
matrix and must be resolved by the later applicable replay/forecast-input
authority if that mode uses them.

## F. Scope and effective-time boundary

The current approved applicability inputs are:

```text
EFFECTIVE_FROM=2024-08-01T00:00:00+08:00
EFFECTIVE_TO_OR_OPEN_ENDED=OPEN_ENDED
AUTHORITY_TIMEZONE=Asia/Shanghai
MAPPED_SEASONS=[2025~2026]
JULY_UNMAPPED_DATE=2025-07-22
JULY_UNMAPPED_ROW_COUNT=2
JULY_RAW_ROWS_RETAINED=true
JULY_CANONICAL_COHORT_ASSIGNED=false
JULY_AUTO_SEASON_ASSIGNMENT=false
```

The source owner must confirm the applicability boundary in the final
attestation. The July disposition remains a governed boundary and is not a
license to generate identity arrays or to silently assign a season.

## G. Final attestation issuance statement

The source owner may issue a final attestation only after the required fields
are truthfully complete, including the concrete scope arrays and authorized
coverage/date derivations. The issuance process must then create the final
payload, set the actual attestation status, compute its canonical SHA-256, and
record the attestation event time.

Until that event occurs:

```text
FORMAL_BUSINESS_SOURCE_ATTESTATION_CREATED=false
SOURCE_OWNER_ATTESTATION_ISSUED=false
SOURCE_AUTHORITY_ACCEPTED=false
S1_SOURCE_AUTHORITY_CANONICAL_GATE_PASS=false
```

This request is not permission to read Source 002, not a source-owner
signature, and not a canonical S1 acceptance decision.

## Data-safety and governance boundary

```text
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
PRODUCTION_DATABASE_READ=false
S1_REMAINING_05_AUTHORIZED=false
S1_REMAINING_06_AUTHORIZED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
NEXT_RECOMMENDED_ACTION=OBTAIN_EXPLICIT_SOURCE_OWNER_ATTESTATION_AND_AUTHORIZED_MISSING_SCOPE_VALUES
```
