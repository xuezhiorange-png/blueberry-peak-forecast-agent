# V0.3-S2 SOURCE_002 canonical-grain kilogram sum ledger policy

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY
ARTIFACT_VERSION=s2-source-002-canonical-grain-kg-sum-v1
TASK_ID=V03_S2_SOURCE_002_CANONICAL_GRAIN_KG_SUM_LEDGER_POLICY_R1
TASK_CLASS=DOCS_ONLY_LEDGER_POLICY_ISSUANCE
AUTHORIZATION_SCOPE=S2_SOURCE_002_CANONICAL_GRAIN_KG_SUM_ONLY
REVIEWER_ROLE=COORDINATOR
USER_WAIVED_THIRD_PARTY_REVIEW=true
COORDINATOR_REVIEW_COUNTS=true
AUTHORIZED_AT=2026-08-22T12:17:00Z
RECORDED_AT=2026-08-22T12:20:00Z
AUTHORIZATION_UTTERANCE=2  链路只是为了业务区分
OPTION_SELECTED=2
BASE_MAIN_SHA=923c309b7242be02d4bf974f49bcdcd4b7cda444
CONTRACT_PATH=docs/v0-3/s2/s2-materialized-dataset-contract.md
CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
WORKPAPER_PATH=docs/v0-3/s2/workpapers/s2-source-002-canonical-grain-kg-sum-ledger-policy.md
NO_STEP_IMPLIES_THE_NEXT=true
~~~

The user selected option 2 after E3 fail-closed on 32,474 canonical-grain
collision groups. This document records that ledger policy. It does not
implement cleaning, does not freeze a dataset, does not accept S2, and does
not start S3.

This PR is documentation only.

~~~text
PRODUCTION_CODE_MUTATION_AUTHORIZED=false
TEST_CODE_MUTATION_AUTHORIZED=false
MIGRATION_CREATION_AUTHORIZED=false
CONTRACT_MUTATION_AUTHORIZED=false
DEVELOPMENT_PLAN_MUTATION_AUTHORIZED=false
S1_AUTHORITY_MUTATION_AUTHORIZED=false
ALLOWLIST_EXPANSION_AUTHORIZED=false
GIT_COMMIT_OF_SOURCE_BYTES_OR_LOCATORS_AUTHORIZED=false
V0_3_S3_AUTHORIZED=false
S2_ACCEPTANCE_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
LANE_C_START_AUTHORIZED=false
LANE_D_START_AUTHORIZED=false
~~~

## 1. What is authorized

SOURCE_002 source rows that share the inherited S1 canonical grain may be
collapsed by **Decimal kilogram sum** of non-excluded contributor rows.

~~~text
CANONICAL_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
TARGET_TRANSFORMATION=NONE
THIS_IS_NOT_A_TARGET_TRANSFORMATION=true
QUANTITY_COLLAPSE_REQUIRES_EXPLICIT_LEDGER_POLICY=true
QUANTITY_COLLAPSE_AUTHORIZED=true
LEDGER_POLICY_VERSION=s2-source-002-canonical-grain-kg-sum-v1
OPERATOR=DECIMAL_SUM
QUANTITY_UNIT=kg
SOURCE_QUANTITY_DECIMAL_PLACES=3
FLOAT_SUM_FORBIDDEN=true

COLLAPSE_DIMENSION_LINK=链路
LINK_ROLE=BUSINESS_DISTINCTION_AND_PROVENANCE_ONLY
LINK_ENTERS_CANONICAL_GRAIN=false

COLLAPSE_DIMENSION_FRUIT_SIZE=果径
FRUIT_SIZE_ROLE=SOURCE_DIMENSION_FOR_AGGREGATION
FRUIT_SIZE_ENTERS_CANONICAL_GRAIN=false

MIN_HASH_SURVIVOR_DROP_FORBIDDEN=true
SILENT_ROW_DROP_FORBIDDEN=true
LANE_C_WINNER_NOT_USED_FOR_THIS_COLLAPSE=true
~~~

`TARGET_TRANSFORMATION=NONE` remains. The operator does not change the
observed marketable net weight. It only stops treating `链路` and `果径` as
ledger keys. That matches the already accepted S1 field map: `链路` is
flagship-company provenance; `果径` is a source dimension for aggregation.

One cleaned row per canonical grain. The unique grain constraint on
`s2_cleaned_row` already requires this. Contributor source-row identities
must remain reconstructable (sorted contributor hashes in the cleaned-row
content hash). A singleton grain keeps the original source-row identity
hash. A collapsed grain uses a 64-hex digest of the sorted contributor
identity hashes, not a min-hash pointer that drops kilograms.

## 2. Quantity rules

~~~text
EXPLICIT_ZERO_KG_IS_KNOWN=true
EXPLICIT_ZERO_KG_INCLUDED_IN_SUM=true
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
ABSENT_DAYS_NOT_IMPUTED_AND_NOT_IN_SUM=true
JULY_2025_07_22_OPTION_A_EXCLUDED_FROM_COHORT_SUM=true
JULY_EXCLUDED_SOURCE_ROW_COUNT=2
MIXED_KNOWN_AND_UNKNOWN_IN_ONE_GRAIN=FAIL_CLOSED
NEGATIVE_KG=FAIL_CLOSED
~~~

July Option A rows stay in Lane A raw facts. They receive `BUSINESS_EXCLUSION`
ledger entries and must not enter the in-cohort kilogram sum. They must not
be season-auto-assigned.

## 3. What this grant does not do

It does not authorize Ready or merge of PR #286. It does not start Lane C or
Lane D. It does not score contract §11. It does not expand allowlists or add
Alembic revisions. It does not permit committing Source002 bytes or locators.

Lane B may implement this policy on the existing E3 Draft after this grant,
using only Lane B allowlisted paths.

## 4. Expected live shape (not a tonnage)

E2 remains `DECLARED_SOURCE_ROW_COUNT=233171`. In-cohort source rows remain
`233169` (`233171 - 2`). After this collapse, cleaned non-excluded **grain**
count is the number of distinct canonical grains among those 233169 rows.
That count is **not** 233169 and must be measured, not assumed.

Kilogram totals must be Decimal sums of contributor cells. Do not invent
tonnes in docs or logs.
