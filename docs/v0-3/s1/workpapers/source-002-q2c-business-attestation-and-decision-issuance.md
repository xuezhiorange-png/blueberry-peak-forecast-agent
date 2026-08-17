# Source002 Q2C Business Attestation and Decision Issuance

## Issuance identity

```text
TASK_ID=SOURCE_002_Q2C_BUSINESS_ATTESTATION_AND_DECISION_ISSUANCE
BASE_MAIN_SHA=99b98e6cd2fced364fe3b9db816e562bae9f8771
ARTIFACT_STATUS=ISSUED_FOR_INDEPENDENT_REVIEW
BUSINESS_OWNER_ROLE=business_data_owner_role
BUSINESS_OWNER_CONFIRMATION_EVENT=EXPLICIT_Q2C_TARGET_BOUNDARY_CONFIRMATION
BUSINESS_OWNER_CONFIRMATION_AT=2026-08-17T11:53:00+08:00
BUSINESS_OWNER_CONFIRMATION_TIMEZONE=Asia/Shanghai
NO_STEP_IMPLIES_THE_NEXT=true
```

This docs-only package issues a versioned Q2C business-source attestation and
a final Q2C decision record. It does not perform independent review, canonical
Q2C acceptance, Ready, Merge, implementation, or any downstream gate action.

## Explicit business owner confirmation

The confirmation event is preserved as the authority for the Q2C boundary:

```text
V0.3 的业务预测目标物理事件为田间采收点首次有效扫码称重。
目标数量为田间已经判定为商品果的净重，单位 KG。
田间剔除的非商品果不进入该目标数量。
加工厂后续分选、拒收、退货不追溯调整该田间目标数量。
该目标不重构扫码称重前的运输、存储或其他理论损耗。
时间口径为农场本地 HARVEST_BUSINESS_DATE，时区 Asia/Shanghai。
统计粒度为 SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE，PLOT 不属于当前 canonical grain。
model_harvested_marketable_quantity_kg 的业务目标含义绑定到上述同一田间商品果采收/称重边界，而不是加工厂收货、后续分选或 post-harvest retained quantity。
TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY。
同意基于已经治理并接受的 Source002 Source Authority 与 Source Cohort，签发版本化 business-source attestation，并形成独立 Q2C decision record。
```

The event creates no new source fact. It binds existing governed Source002
values and the accepted Source Authority and Source Cohort identities.

## Source provenance and attestation projection

```text
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_OWNER_ATTESTATION_VERSION=source-002-final-source-owner-attestation-v1
SOURCE_OWNER_ATTESTATION_HASH=2c7bd156da2eb3d7c2cb5906e23cb3d380f709b43e39e1c6a6ce38f5587971e1
SOURCE_COHORT_ACCEPTED=true
SOURCE_COHORT_MANIFEST_VERSION=source-002-final-source-cohort-manifest-v1
SOURCE_COHORT_ID=source-002-s1-cohort-v1
SOURCE_COHORT_MANIFEST_HASH=27ddb9a77d9ce7d4b0579d0648c23b5ade7d6a090626b695e5b41827e714fcca
FARMS_COUNT=84
FARMS_SHA256=2daf09d38efb41bada5a1b493974c569e64b63abdd322e5ab4dacc206edb0381
SUBFARMS_COUNT=192
SUBFARMS_SHA256=921a56006d1a75f683c62c8a930e913fc39cabf2dcffec88b16549ed95945e13
VARIETIES_COUNT=20
VARIETIES_SHA256=fe6274775796193318fa3ad504ba8cc4e2196b8c58dd8f795cec80cc22c26209
BUSINESS_SOURCE_ATTESTATION_VERSION=source-002-q2c-business-source-attestation-v1
BUSINESS_SOURCE_ATTESTATION_HASH=09a1ccc02036d353ab1fb8cd7a25edcdc0458a736fec510cd1c3711f51137be2
BUSINESS_SOURCE_ATTESTATION_HASH_REPLAY=PASS
```

The Q2C business-source attestation is a projection of the accepted final
Source Owner Attestation. Except for its Q2C attestation version, the Q2C
effective time, and its own attestation hash, every schema value—including
the 84/192/20 concrete arrays and their order—is preserved exactly.

## Target decision

```text
TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
FORECAST_TARGET=model_harvested_marketable_quantity_kg
ACTUAL_LABEL=actual_harvest_quantity_kg
Q2C_OUTCOME=PROVEN_EXACT
TARGET_TRANSFORMATION=NONE
TRANSFORMATION_REQUIRED=false
TRANSFORMATION_AUTHORITY_USED=false
VERSIONED_Q2C_TRANSFORMATION_SELECTED=false
PHYSICAL_EQUIVALENCE_ASSUMED=false
PHYSICAL_EQUIVALENCE_BUSINESS_AUTHORIZED=true
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
```

`effective_marketable_quantity_kg` is not selected because the owner
confirmation binds the forecast target to the recorded field marketable net
weight at the first valid field scan-weigh event. Factory-received, arrival,
post-harvest-retained, natural-maturity, and other downstream quantities are
not silently substituted.

## Six-dimension Q2C result

| Dimension | Actual side | Forecast side | Result |
| --- | --- | --- | --- |
| PHYSICAL_EVENT | HARVEST at first valid governed field scan-weigh event | `model_harvested_marketable_quantity_kg` uses the same governed harvest boundary | PROVEN_EXACT |
| QUANTITY_AND_MARKETABILITY_BOUNDARY | Recorded marketable net weight in KG; field non-marketable fruit excluded | Same field-marketable net-weight boundary | PROVEN_EXACT |
| SORTING_BOUNDARY | Field exclusion applies before recorded quantity; later packhouse/factory sorting does not retroactively adjust the label | Same boundary | PROVEN_EXACT |
| POST_HARVEST_BOUNDARY | Recorded field scan-weigh boundary; later transport, receipt, rejection, return, and retention do not retroactively adjust the target | Same boundary | PROVEN_EXACT |
| TIME_BASIS | HARVEST_BUSINESS_DATE, Asia/Shanghai | Same farm-local harvest business date | PROVEN_EXACT |
| CANONICAL_GRAIN | SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE; plot_supported=false | Same canonical grain | PROVEN_EXACT |

```text
Q2C_DIMENSION_COUNT=6
Q2C_PROVEN_EXACT_DIMENSION_COUNT=6
Q2C_UNRESOLVED_DIMENSION_COUNT=0
```

## Hash contracts and validation

Business-source attestation hash:

```text
HASH_CONTRACT_VERSION=source-002-final-attestation-hash-contract-v1
HASH_CONTRACT_SHA256=c17e94b4dea7a833d03a884de3e7953db034e70fbba69856c508827c07470a39
HASH_SCOPE=FULL_ISSUED_SCHEMA_VALID_FINAL_ATTESTATION_OBJECT_EXCLUDING_ONLY_attestation_hash
CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
BUSINESS_SOURCE_ATTESTATION_HASH=09a1ccc02036d353ab1fb8cd7a25edcdc0458a736fec510cd1c3711f51137be2
BUSINESS_SOURCE_ATTESTATION_HASH_REPLAY=PASS
```

Q2C decision hash:

```text
DECISION_HASH_ALGORITHM=SHA-256
DECISION_HASH_SCOPE=FULL_ISSUED_FINAL_Q2C_DECISION_OBJECT_EXCLUDING_ONLY_decision_record_sha256
DECISION_HASH_CANONICALIZATION=UTF8_JSON_SORT_KEYS_RECURSIVELY_COMPACT_SEPARATORS_ENSURE_ASCII_FALSE
Q2C_DECISION_HASH=c7feccd6791b6e9879f82c034552e53d5cc96922314cffa4d21fe5ee1e5d0e18
Q2C_DECISION_HASH_REPLAY=PASS
```

Validation is materialized as completed evidence:

```text
JSON_SYNTAX=PASS
BUSINESS_SOURCE_ATTESTATION_SCHEMA_VALIDATION=PASS
BUSINESS_SOURCE_ATTESTATION_REQUIRED_TOP_LEVEL_FIELD_COUNT=36
BUSINESS_SOURCE_ATTESTATION_MISSING_REQUIRED_FIELD_COUNT=0
BUSINESS_SOURCE_ATTESTATION_SOURCE_VALUE_PARITY=PASS
BUSINESS_SOURCE_ATTESTATION_ARRAY_ORDER_PARITY=PASS
Q2C_DIMENSION_RECONCILIATION=PASS
CANONICAL_GATE_STATUS_MUTATION_COUNT=0
CANONICAL_GATE_BLOCK_REASON_MUTATION_COUNT=0
SOURCE_002_RAW_READ=false
SOURCE_002_ROW_LEVEL_READ=false
REAL_BUSINESS_DATA_READ=false
TEST_DATA_ACCESSED=false
EXTERNAL_HOLDOUT_ACCESSED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MIGRATION_CREATED=false
MODEL_CHANGED=false
```

## Issued-but-not-accepted state

```text
FORMAL_Q2C_DECISION_ISSUED=true
POSITIVE_Q2C_OUTCOME_ISSUED=true
Q2C_DECISION_STATUS=ISSUED_PENDING_INDEPENDENT_REVIEW
Q2C_ACCEPTED=false
INDEPENDENT_REVIEW_STATUS=NOT_STARTED
CANONICAL_Q2C_GATE_STATUS=BLOCKED
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
CURRENT_CANONICAL_GATE_PASS_COUNT=4
CURRENT_CANONICAL_GATE_BLOCKED_COUNT=13
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
INDEPENDENT_REVIEW_PERFORMED=false
READY_PERFORMED=false
MERGE_PERFORMED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

Issuance is not canonical acceptance. The next independent review is a
separate authorized step and is not performed by this task.
