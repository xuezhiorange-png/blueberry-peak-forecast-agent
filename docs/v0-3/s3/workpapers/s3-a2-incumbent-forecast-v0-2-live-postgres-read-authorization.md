# V0.3-S3-A2 Incumbent forecast V0.2 live postgres read implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-v0-2-live-postgres-read-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=c980d5e4efa96119ed3ba877915267c527d45029
BASE_MAIN_TREE_SHA=cbdc4fb1785312877301b2de422ae41c46b55cf7
PARENT_PR=360
PARENT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md
PARENT_LIVE_POSTGRES_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c324d03f52a86cbd9a9b354bdcc58e27eb01279a
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_POPULATE_ROWS=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
AUTHORIZATION_MERGE_DOES_NOT_REOPEN_106_ROW_AUDIT=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_ALEMBIC=true
AUTHORIZATION_MERGE_DOES_NOT_TOUCH_PYTHON=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE_IN_GRANT=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_PRODUCTION_INIT_PY=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_IN_THIS_PR=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast V0.2 live postgres read**
implementation grant after the live-read contract freeze on main (#360). This document
records what a **later** deterministic live-read R1 may do when the user again says
「可以实施」. This PR does not implement live postgres read, flip
`LIVE_POSTGRES_READ_IMPLEMENTED`, populate rows, open postgres connections, flip
`NO_VERSIONED`, or authorize production code mutation.

This is **live-read** implementation authorization only. Parent live-read contract §§1–9,
parent bindable-name contract §§1–9, parent postgres-obtain contract §§3.1–3.2, and the
frozen 106-row Alembic audit remain authoritative and are not reopened. Do not rewrite
alignment contract §6 (`EmptyS2IdentityAlignmentPort` remains the historical production
default; alignment §6 SHA `2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8`).

Do not confuse with already-landed postgres-obtain R1 (fail-closed empty obtain). That slice
is done. This grant authorizes a **later** live postgres read of the already-encoded bindable
name `s3_incumbent_forecast_replay_identity`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_LIVE_READ_BINDABLE_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
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

Grant ≠ live-read contract ≠ live-read R1 ≠ versioned forecast artifact. Empty table +
encoded bindable name + unused grant still yields `obtain()=()`. Later live-read of the empty
table still yields `()`. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This grant does not close S3. Jumping to
live-read R1 implementation now is forbidden.

## 1. Unique remaining code gap (this grant does not fill it)

~~~text
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
UNIQUE_REMAINING_GAP=_empty_v0_2_postgres_obtain_second_empty_return_after_non_empty_bindable_names
~~~

After bindable-name R1 (#359), `bindable_table_names()` returns frozen name
`s3_incumbent_forecast_replay_identity`. `IncumbentForecastReplaySource._empty_v0_2_postgres_obtain`
consults non-empty bindable names, then still returns `()`. That second empty return is the
unique remaining code gap for a **later** live-read R1. Default `IncumbentForecastReplaySource.v0_2_postgres_obtain`
still points at that function. Obtain priority remains: harvest-as-cutoff → `()`; explicit
`replay_rows` win; else call `v0_2_postgres_obtain`; missing/unreadable/ambiguous/unauthorized/empty → `()`.

This grant does not change those Python bytes.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=360
PARENT_LIVE_POSTGRES_READ_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md
PARENT_LIVE_POSTGRES_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c324d03f52a86cbd9a9b354bdcc58e27eb01279a
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
PARENT_BINDABLE_NAME_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=402942dd80a14299db263227e60d4a590b786f76
CURRENT_BINDABLE_NAME_CONTRACT_GIT_BLOB_SHA=66302f63110572ee305b0804bd7e467616b3fe51
BINDABLE_NAME_CONTRACT_EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
BINDABLE_NAME_GRANT_EVIDENCE_JSON_SHA256=b745ccdc0a5084368852041337d5409d0c8aad4c93183070a573a35167df604d
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
CURRENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA=5a796011f2418cc4079ad3128cc7a1c7d5513eea
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
CURRENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA=86523cc0c431a80f0cc7b664fb284bb7e4ccf590
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
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
~~~

Evidence JSON self-hashes above are binding references, not whole-file `sha256sum`
values. The parent 106-row Alembic audit (snapshot at `2cfc2c0`) is cited only; not
rewritten by this authorization grant. `s3_incumbent_forecast_replay_identity` exists in
Alembic with 0 rows; `MATCH_TABLE_COUNT` remains `0`.

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
REPLAY_SOURCE_CARRIES_NO_KG_OR_TONNES=true
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

A later deterministic live-read R1 may, under a separate user 「可以实施」 gate,
replace the fail-closed second empty return in `_empty_v0_2_postgres_obtain` with a live read
bound only to frozen table `s3_incumbent_forecast_replay_identity`, per parent live-read
contract §3.3.

### 4.1 Allowed changes (future implementation only)

~~~text
LIMITED_EDIT_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
FUTURE_PATH=backend/app/s3_daily_rowset/incumbent_forecast_replay_source.py
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
OPTIONAL_NEW_TESTS_LIVE_POSTGRES_READ=true
OPTIONAL_UPDATE_TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY=true
OPTIONAL_UPDATE_TEST_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_PY=true
PEP_420_NO_PRODUCTION_INIT_PY_UNDER_S3_DAILY_ROWSET=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BY_DEFAULT=true
FORBIDDEN_ADD_ALEMBIC=true
FORBIDDEN_CREATE_SECOND_TABLE=true
~~~

Future implementation may:

1. Limited-modify `incumbent_forecast_replay_source.py` (blob `9ffb7bdf`) to replace the
   second fail-closed empty return in `_empty_v0_2_postgres_obtain` with a live read bound
   **only** to frozen table `s3_incumbent_forecast_replay_identity`.
2. Project **only** grain columns `forecast_cutoff_at`, `model_id`, `forecast_quantile` into
   `IncumbentForecastArtifactEntry`. No kg/tonnes/weight/quantity/forecast_value/daily_curve/
   harvest_business_date/catalog_cell/alignment_identity.
3. Honor obtain priority: harvest-as-cutoff → `()`; explicit `replay_rows` win; else attempt
   live read; missing/unreadable/ambiguous/unauthorized/empty → `()`.
4. Use existing in-repo session/engine plumbing if present; must not invent DSN, database name,
   or connection strings.
5. Flip `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` to `true` in
   `docs/v0-3/development-plan.md` §4.4 live block.
6. Add tests; optionally update `test_incumbent_forecast_replay_source.py` (blob
   `14a2c27f`) and `test_incumbent_forecast_v0_2_postgres_obtain.py` (blob `8db60cba`) as
   necessary oracles.

The only implementation-status flip permitted by a future live-read R1 is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false → true
~~~

### 4.2 What future live-read R1 must keep false / unchanged

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
MATCH_TABLE_NAMES=()
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
~~~

Honesty: even after a future live-read R1 implements reading, the empty Alembic table still
has 0 rows and default `obtain()` remains `()` until rows exist. Empty-table live-read still
yields `()`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

### 4.3 Forbidden in future implementation

~~~text
FORBIDDEN_ADD_TO_MATCH_TABLE_NAMES=true
FORBIDDEN_REOPEN_OR_RECLASSIFY_106_AUDIT=true
FORBIDDEN_POPULATE_ROWS=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE=true
FORBIDDEN_WRITE_DSN_OR_CONNECTION_STRINGS=true
FORBIDDEN_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_INVENT_SECOND_TABLE_NAME=true
FORBIDDEN_INVENT_CONNECTION_STRINGS=true
FORBIDDEN_INVENT_CUTOFF_LISTS=true
FORBIDDEN_INVENT_TONNES_OR_KG=true
FORBIDDEN_FLIP_NO_VERSIONED=true
FORBIDDEN_FLIP_AVAILABLE_OR_VERIFIED=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TOUCH_S2_IDENTITY_ALIGNMENT_PY=true
FORBIDDEN_TOUCH_FORECAST_ARTIFACT_PY=true
FORBIDDEN_TOUCH_AUTHORITY_PY_BY_DEFAULT=true
IMPLEMENTATION_PR_MAY_NOT_WRITE_LIVE_FORECAST_ARTIFACT_TO_REPOSITORY_WHILE_OBTAIN_EMPTY=true
~~~

## 5. Frozen Python blob audit (byte-identical; this grant does not touch)

~~~text
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=b0dc923ae4a4c06e3f6ccafd38e175d8ac16d3f7
S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY_BLOB=ae3381d2c0b0744a49519370e67005c479120665
FORECAST_ARTIFACT_PY_BLOB=73e65fbe6774ef555f825efc74c9c8eb5f003575
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
ALEMBIC_E8B2C4D6F1A3_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
TEST_S2_IDENTITY_ALIGNMENT_PY_BLOB=9c653823ebca79fdb12d61325fdb4b18e17d0cef
TEST_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=c81c3ebfe565095f17cfa8794d115ea9fab0ca73
TEST_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_PY_BLOB=9fdd22ccadd6990fa2522c8b23a287dc4e87f173
TEST_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_PY_BLOB=929b9fc8a89c1a0b31154cd89b2bd6d4c7cb4a4a
TEST_FORECAST_ARTIFACT_PY_BLOB=2ae0036a46f6f0b2898a8fca3589041b9869c196
TEST_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=11e23e247d6f90e8c7528a073b6e90c709f4a5cc
TEST_INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=14a2c27f97fa50a37902558c9819f07cd3d71411
TEST_INCUMBENT_FORECAST_LIVE_ENVELOPE_PY_BLOB=cf34f76c734388129b7dbf8d4f585bde584fceac
TEST_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_PY_BLOB=10ac671d603b842ece5cb3ae449b1580715ed2b0
TEST_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_PY_BLOB=97b072ca484ce50be6796b88c28b8999d9bde353
TEST_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_PY_BLOB=8db60cba335dd87ac72f7b86469168e15b7efe97
TEST_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=44c80ce1e75f5f89c206090fdaf97502811d64ca
TEST_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_PY_BLOB=e50b387a416cca1db160cecfac872704399b76ed
TEST_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_PY_BLOB=a8265856beb321d443a9da2f4c1970e422fe4162
BOUND_FIXTURE_TEST_INJECTION_PATH_MUST_REMAIN=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md` §10 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md` §13 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md` §16 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` §19 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` §22 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` §25 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` §28 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` §31 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` §34 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` §37 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` §40 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` §43 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §52 pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §68 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §51 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §56 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §57 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §60 pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` §45 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 7. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=ba791a1c2292d36b075cc6bc717d788df9d1efd063193ed5d2290783f4bfbeec
~~~

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
