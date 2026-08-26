# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain identity-set implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=041292854627001544e7198d0a309bbfe39c179d
BASE_MAIN_TREE_SHA=b2ef1a3406e7a7e36c84268097f8ec19b9118dda
PARENT_PR=366
PARENT_GRAIN_IDENTITY_SET_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
AUTHORIZATION_MERGE_DOES_NOT_LAND_IDENTITY_SET_MEMBERS=true
AUTHORIZATION_MERGE_DOES_NOT_POPULATE_ROWS=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_CUTOFF_MODEL_QUANTILE_LISTS=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_GRAIN_IDENTITY_SET_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_SESSION_INTO_CATALOG_DEFAULT=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
AUTHORIZATION_MERGE_DOES_NOT_REOPEN_106_ROW_AUDIT=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_ALEMBIC=true
AUTHORIZATION_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_GRANT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_IN_THIS_PR=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast V0.2 replay-identity grain identity-set**
implementation grant after the grain identity-set contract freeze on main (#366). This document
records what a **later** deterministic grain identity-set loader/provider R1 may do when the user
again says 「可以实施」. This PR does not implement loader/provider, flip
`GRAIN_IDENTITY_SET_IMPLEMENTED`, land identity-set members, INSERT rows, invent member literals,
flip `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY`, flip `NO_VERSIONED`, or authorize production
code mutation.

This is **grain-identity-set** implementation authorization only. Parent grain identity-set contract
§§1–9, parent grain-row-presence R1, and the frozen 106-row Alembic audit remain authoritative
and are not reopened. Do not rewrite alignment contract §6 (`EmptyS2IdentityAlignmentPort` remains the
historical production default; alignment §6 SHA `2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8`).

Grain-row-presence R1 is landed; frozen table `s3_incumbent_forecast_replay_identity` still has 0 rows.
This grant authorizes a **later** fail-closed loader/provider R1 per parent contract §3.3 — not member
landing, not INSERT, not grain-row-presence wiring.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

Grant ≠ grain identity-set contract ≠ loader R1 ≠ member landing ≠ INSERT ≠ versioned artifact ≠
catalog closeout. Grain-row-presence R1 ≠ identity-set. No reviewed identity-set artifact exists;
default provider remains empty. Empty table still 0 rows. Default `obtain()` without session still
`()`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This grant does not
close S3. Jumping to identity-set loader R1 now is forbidden.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5e8fe47036766424d1f47308c27f719129cf9c5f
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
UNIQUE_REMAINING_GAP=_no_reviewed_grain_identity_set_artifact_without_fail_closed_loader_provider
OBJECT_ROW_COUNT_AT_REVIEW=0
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
~~~

Grain-row-presence R1 is landed. Frozen table `s3_incumbent_forecast_replay_identity` still has 0 rows.
No coordinator-reviewed grain identity-set artifact exists in repository. This grant does not invent,
enumerate, or exemplify any `forecast_cutoff_at` / `model_id` / `forecast_quantile` member literals.
This grant does not change those Python bytes.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=366
PARENT_GRAIN_IDENTITY_SET_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
GRAIN_ROW_PRESENCE_R1_EVIDENCE_JSON_SHA256=43771f68f87d550f48b1e0aa9bcaa42304676436fc08df31365c6c5fc0763511
GRAIN_ROW_PRESENCE_CONTRACT_EVIDENCE_JSON_SHA256=1e7204dc716dd1e65de4b0248ebe4de01638cb31628b0cb10db8e1fdf5aba833
GRAIN_ROW_PRESENCE_GRANT_EVIDENCE_JSON_SHA256=bbdc217b10d5b54081321a069b88929ba56973397f23487ee32bfdfd174533c1
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_DOWN_REVISION=a7c3e9f1b2d4
LANE_C_E4B_MIGRATION_REVISION=a7c3e9f1b2d4
ALEMBIC_MIGRATION_PATH=backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
~~~

## 3. Inherited S2 and parent contract authority (not reopened)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
REPLAY_SOURCE_GRAIN=DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)
CONTENT_IDENTITY_VERSION=v0-3-s3-a2-incumbent-forecast-artifact-content-identity-v1
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
PEP_420_NAMESPACE=true
PRODUCTION_INIT_PY_FORBIDDEN=true
SOURCE_002_ROW_LEVEL_READ=false
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
~~~

## 4. What this authorization grants

A later deterministic grain identity-set loader/provider R1 may, under a separate user 「可以实施」 gate,
implement fail-closed loader/provider per parent contract §3.3.

### 4.1 Allowed changes (future implementation only)

~~~text
OPTIONAL_LIMITED_PRODUCTION_CODE_GRAIN_IDENTITY_SET_LOADER=true
OPTIONAL_NEW_TESTS_GRAIN_IDENTITY_SET_LOADER=true
PEP_420_NO_PRODUCTION_INIT_PY_UNDER_S3_DAILY_ROWSET=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_ADD_ALEMBIC=true
~~~

Future implementation may:

1. Implement a fail-closed loader/provider that returns a coordinator-reviewed identity-set **only**
   when a separately reviewed artifact exists (not invented in grant or R1 docs).
2. Return **only** grain triple members `forecast_cutoff_at`, `model_id`, `forecast_quantile`.
3. If no independently reviewed artifact exists at R1 time: fail-closed, provider returns empty set.
4. Flip `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED` to
   `true` in `docs/v0-3/development-plan.md` §4.4 live block. `IMPLEMENTED=true` ≠ members landed ≠
   versioned artifact ≠ catalog closeout.
5. Add tests asserting: no reviewed artifact → provider empty; grain-row-presence remains 0 rows;
   default obtain without session → `()`.

Loader R1 ≠ landing members into repository ≠ INSERT ≠ versioned artifact.

The only implementation-status flip permitted by a future loader R1 is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=false → true
~~~

### 4.2 What future loader R1 must keep false / unchanged

~~~text
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
MATCH_TABLE_NAMES=()
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
OBJECT_ROW_COUNT_AT_REVIEW=0
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
~~~

Honesty: even after a future loader R1 implements fail-closed wiring, without a reviewed artifact
the provider remains empty, table remains 0 rows, and `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY`
stays `true`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

### 4.3 Forbidden in future implementation

~~~text
FORBIDDEN_LAND_IDENTITY_SET_MEMBERS=true
FORBIDDEN_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
FORBIDDEN_INSERT_UNREVIEWED_SET=true
FORBIDDEN_INVENT_CUTOFF_MODEL_QUANTILE_LISTS=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true
FORBIDDEN_H7_FIXTURE_AS_IDENTITY_SET=true
FORBIDDEN_ADD_TO_MATCH_TABLE_NAMES=true
FORBIDDEN_REOPEN_OR_RECLASSIFY_106_AUDIT=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_WIRE_SESSION_INTO_CATALOG_DEFAULT_OBTAIN=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 5. Frozen Python blob audit (byte-identical; this grant does not touch)

~~~text
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5e8fe47036766424d1f47308c27f719129cf9c5f
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
ALEMBIC_E8B2C4D6F1A3_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5695249691ddda49b7682455eb3ec8ca5b365890
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md` §16 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md` §19 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md` §22 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` §25 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §28 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §31 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §34 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §37 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §40 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §43 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §46 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §49 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §51 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §57 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §58 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §62 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §63 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §66 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §74 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=false
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 7. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=d6edd4dd5bab631c2b418e817f874aed50b1354338ddcae508996c6e89ee1e8f
~~~

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_LAND_IDENTITY_SET_MEMBERS=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_GRAIN_IDENTITY_SET_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
