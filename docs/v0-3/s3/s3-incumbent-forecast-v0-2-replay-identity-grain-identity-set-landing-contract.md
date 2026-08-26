# V0.3-S3-A2 Incumbent Forecast V0.2 Replay-Identity Grain Identity-Set Landing Contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-landing-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING
USER_GATE=可以下一步
CONTRACT_ONLY=true
BASE_MAIN_SHA=85a9b90818454503c9a68347fdf37bc14ff87475
BASE_MAIN_TREE_SHA=6f7b2e05c48abac78eae95f23dc0aed121e4dd3b
BASE_REF=origin/main
PARENT_GRAIN_IDENTITY_SET_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=2cdad6d21013684f5ba9b3fd2ff1126c72a00bc5
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=d6edd4dd5bab631c2b418e817f874aed50b1354338ddcae508996c6e89ee1e8f
GRAIN_IDENTITY_SET_LOADER_R1_EVIDENCE_JSON_SHA256=a09d0b4398abd6feace3157519bac3164ddfef654b738bbb26c4cdf3addb5f4b
P0_CONTRACT_PATH=docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
NO_STEP_IMPLIES_THE_NEXT=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
~~~

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
MATCH_TABLE_NAMES=()
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This document freezes coordinator-reviewed **grain identity-set artifact landing** authority after
identity-set loader R1. Loader R1 is landed;
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=true`. Production
loader has no independently reviewed artifact and returns empty; grain-row-presence default remains 0 rows.
Frozen table `s3_incumbent_forecast_replay_identity` still has `OBJECT_ROW_COUNT_AT_REVIEW=0`. The repository
still has **no** coordinator-reviewed grain identity-set artifact. Parent identity-set contract §§1–9 freeze
**what the set is**; loader R1 freezes fail-closed empty provider. This contract freezes **how a reviewed
artifact lands into the repository** and **when** `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY` may flip —
not landing members today.

This is **not** an implementation grant, **not** landing R1, **not** member landing today, **not** row
INSERT wiring, **not** versioned forecast artifact creation, **not** catalog closeout, **not** catalog
default session wiring, and **not** evidence that S3 is complete.

Honest boundary: landing contract ≠ grant ≠ landing R1 ≠ member landing today ≠ INSERT ≠ versioned artifact
≠ catalog closeout. Loader R1 ≠ landing. No coordinator-reviewed identity-set artifact; production provider
empty; table still 0 rows; `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY` remains `true`. This contract must
not invent, enumerate, or exemplify any `forecast_cutoff_at` / `model_id` / `forecast_quantile` values.
Default `obtain()` without injected session remains `()`. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This contract does not flip `NO_REVIEWED` or `NO_VERSIONED`.

~~~text
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_LAND_IDENTITY_SET_MEMBERS=true
CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WIRE_SESSION_INTO_CATALOG_DEFAULT=true
CONTRACT_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
CONTRACT_MERGE_DOES_NOT_ADD_ALEMBIC=true
CONTRACT_MERGE_DOES_NOT_TOUCH_PYTHON=true
LATER_IDENTITY_SET_LANDING_DOES_NOT_AUTO_FLIP_NO_VERSIONED=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_H7_FIXTURE=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 1. Inherited authority (not reopened)

### 1.1 Parent grain identity-set contract, grant, and loader R1

~~~text
PARENT_GRAIN_IDENTITY_SET_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=2cdad6d21013684f5ba9b3fd2ff1126c72a00bc5
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=d6edd4dd5bab631c2b418e817f874aed50b1354338ddcae508996c6e89ee1e8f
GRAIN_IDENTITY_SET_LOADER_R1_EVIDENCE_JSON_SHA256=a09d0b4398abd6feace3157519bac3164ddfef654b738bbb26c4cdf3addb5f4b
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=true
IDENTITY_SET_LOADER_MODULE_PATH=backend/app/s3_daily_rowset/incumbent_forecast_v0_2_replay_identity_grain_identity_set.py
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_PY_BLOB=eed2ecbcacc2a8173003cba55853a6ef5b5f89c5
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_TESTS_BLOB=bd3f39506815f9e52a9751dd4cd837b3c1182edc
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5e8fe47036766424d1f47308c27f719129cf9c5f
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
~~~

Parent grain identity-set contract §§1–9 remain authoritative and are not rewritten by this landing
contract. Loader R1 wired fail-closed provider that returns empty without a coordinator-reviewed
identity-set artifact. Loader R1 ≠ landing members ≠ INSERT wiring ≠ versioned forecast artifact.

### 1.2 Frozen table and Alembic state

~~~text
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_DOWN_REVISION=a7c3e9f1b2d4
LANE_C_E4B_MIGRATION_REVISION=a7c3e9f1b2d4
ALEMBIC_MIGRATION_PATH=backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
OBJECT_ROW_COUNT_AT_REVIEW=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
~~~

### 1.3 Inherited S2 binding

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
TRAIN_ROW_COUNT=16224
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
VALIDATION_ROW_COUNT=8006
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
REPLAY_SOURCE_CARRIES_NO_KG_OR_TONNES=true
SOURCE_002_ROW_LEVEL_READ=false
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
~~~

## 2. Why this contract is the unique remaining gap

1. Loader R1 is landed:
   `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=true`.
2. Production loader has no independently reviewed artifact → provider returns empty; grain-row-presence
   default remains 0 rows.
3. Frozen table `s3_incumbent_forecast_replay_identity` still has `OBJECT_ROW_COUNT_AT_REVIEW=0`.
4. `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true`. The repository still has no coordinator-reviewed
   grain identity-set artifact.
5. Parent identity-set contract freezes **what the set is**; loader R1 freezes fail-closed empty provider.
   **How** a reviewed artifact lands into the repository and **when** `NO_REVIEWED` may flip are not yet
   frozen as an independent contract.
6. Loader R1 ≠ member landing ≠ INSERT wiring ≠ versioned artifact.
7. `SOURCE_002_ROW_LEVEL_READ=false`; members must not be derived from source-002 row-level reads.
8. This gap is **not**: landing members today; **not** flipping `NO_REVIEWED`; **not** grain-row-presence
   INSERT production wiring; **not** catalog default session; **not** MATCH reclassification; **not** new
   Alembic; **not** flipping `NO_VERSIONED`.

Do not treat loader R1 as artifact landing or member landing.

## 3. Frozen grain identity-set landing authority

### 3.1 Landing definition

~~~text
LANDING_MEANS_COORDINATOR_REVIEWED_HASHABLE_ARTIFACT_IN_REPOSITORY=true
LANDING_ARTIFACT_MEMBER_SHAPE_ONLY=forecast_cutoff_at,model_id,forecast_quantile
LANDING_ARTIFACT_MUST_BE_INDEPENDENTLY_REVIEWED=true
LANDING_ARTIFACT_MUST_BE_HASHABLE=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
~~~

Landing means: a coordinator-reviewed, hashable identity-set artifact exists in the repository containing
**only** grain triples `(forecast_cutoff_at, model_id, forecast_quantile)`. This contract must not invent,
enumerate, or exemplify any member literals. This contract merge does not land such an artifact.

### 3.2 NO_REVIEWED flip rule

~~~text
NO_REVIEWED_FLIP_REQUIRES_NON_EMPTY_REVIEWED_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_FLIP_ONLY_AFTER_ACTUAL_LANDING=true
THIS_CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true
FAIL_CLOSED_WHEN_NO_INDEPENDENTLY_REVIEWED_MEMBERS=true
~~~

`NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY` may become `false` **only** when a non-empty, independently
reviewed artifact is actually in the repository. This contract does not land an artifact; therefore this
contract must not flip `NO_REVIEWED`.

### 3.3 Landing boundaries and later grant/R1 scope

~~~text
LANDING_NOT_EQUAL_INSERT=true
LANDING_NOT_EQUAL_VERSIONED_FORECAST_ARTIFACT=true
LANDING_NOT_EQUAL_CATALOG_CLOSEOUT=true
LATER_IDENTITY_SET_LANDING_DOES_NOT_AUTO_FLIP_NO_VERSIONED=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_H7_FIXTURE_AS_IDENTITY_SET=true
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

Landing ≠ INSERT. Even when an artifact is landed in a later slice, grain-row-presence still requires a
reviewed set plus session to INSERT; this slice does not wire INSERT. Landing ≠ versioned forecast artifact
≠ catalog closeout.

A later landing grant/R1 (separate contract on main, separate grant, separate 「可以实施」) may:

1. Land a coordinator-reviewed non-empty identity-set artifact into the repository **only** when such an
   artifact has been independently reviewed (not invented in this contract).
2. Flip `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY` to `false` **only** after actual non-empty landing.
3. If no independently reviewed members exist at R1 time: fail-closed — do not land, do not flip
   `NO_REVIEWED`; at most flip `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_IMPLEMENTED`
   in a later slice (not authorized here).

A later landing R1 must **not**:

- Invent or enumerate identity-set member values
- Derive members from source-002 row-level reads or H7 fixture as live evidence
- Flip `NO_REVIEWED` without non-empty reviewed artifact in repository
- Auto-flip `NO_VERSIONED` or wire session into catalog default obtain
- INSERT unreviewed sets or add to `MATCH_TABLE_NAMES`
- Add Alembic revisions or rewrite alignment contract §6
- Touch production/test Python forbidden by parent freezes

This contract does not issue an implementation grant and does not authorize landing R1.

Member shape inherits parent identity-set contract §3.1. Forbidden projection families:
kg, tonnes, weight, quantity, forecast_value, daily_curve, harvest_business_date, catalog_cell,
alignment_identity.

## 4. Explicit non-scope (not authorized by this contract)

~~~text
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_LAND_IDENTITY_SET_MEMBERS=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_INVENT_CUTOFF_MODEL_QUANTILE_LISTS=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WIRE_SESSION_INTO_CATALOG_DEFAULT=true
CONTRACT_MERGE_DOES_NOT_FLIP_GRAIN_IDENTITY_SET_IMPLEMENTED=true
CONTRACT_MERGE_DOES_NOT_FLIP_LANDING_IMPLEMENTED=true
CONTRACT_MERGE_DOES_NOT_UNSEAL_TEST=true
CONTRACT_MERGE_DOES_NOT_CLOSE_S3=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_TONNES_OR_KG=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 5. Frozen Python blob audit (byte-identical at contract merge)

~~~text
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_PY_BLOB=eed2ecbcacc2a8173003cba55853a6ef5b5f89c5
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_TESTS_BLOB=bd3f39506815f9e52a9751dd4cd837b3c1182edc
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5e8fe47036766424d1f47308c27f719129cf9c5f
GRAIN_ROW_PRESENCE_TESTS_BLOB=1ab1e712d2816b3445c6dac8adc583dccd4dba61
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
ALEMBIC_E8B2C4D6F1A3_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 6. Forbidden inputs and substitutions

~~~text
FORBIDDEN_INVENT_GRAIN_IDENTITY_SET_MEMBERS=true
FORBIDDEN_INVENT_CUTOFF_MODEL_QUANTILE_EXAMPLES=true
FORBIDDEN_REPOSITORY_SCAN_FOR_SUBSTITUTES=true
FORBIDDEN_RAW_SOURCE_002_PRIMARY_READ=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_H7_FIXTURE_AS_IDENTITY_SET=true
FORBIDDEN_USE_HARVEST_BUSINESS_DATE_AS_FORECAST_CUTOFF=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true
FORBIDDEN_ADD_MEMBERS_JSON_OR_CSV=true
~~~

## 7. TEST seal and exclusion policy

~~~text
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_REMAINS_SEALED=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 8. LLM and deterministic service boundary

LLM agents organize explanation and invoke tools. Grain identity-set landing rules, reviewed artifact
binding, provider behavior, and tonnes must come from deterministic service logic and coordinator-reviewed
artifacts only. LLM must not invent tonnes, identity-set member values, cutoff lists, model identifiers,
quantile literals, or row payloads.

## 9. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_IMPLEMENTATION_AUTHORIZED=false (companion introduced; not flipped)
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_LANDING_IMPLEMENTED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md` §12 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md` §15 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md` §18 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md` §21 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md` §24 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` §27 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §30 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §33 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §36 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §39 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §42 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §45 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §48 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §51 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §53 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §59 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §60 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §64 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §65 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §68 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §76 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~
