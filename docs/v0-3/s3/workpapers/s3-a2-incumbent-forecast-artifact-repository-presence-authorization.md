# V0.3-S3-A2 Incumbent forecast artifact repository-presence implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-a2-incumbent-forecast-artifact-repository-presence-authorization-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTATION_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTATION_GRANT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE
USER_GATE=授权
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a05131-6262-7c86-9895-dde762dda347
IMPLEMENTER_RUN=bc-3cff709a-62df-5195-a207-b108ba7837b4
BASE_REF=origin/main
BASE_MAIN_SHA=7eba6a29eaa0480bfdea139c67a756432198b99f
BASE_MAIN_TREE_SHA=f2ea7a47402eae80ee2de3359da7d005ba638762
PARENT_PR=479
PARENT_PRESENCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md
PARENT_PRESENCE_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=1f6caac8173467a64fe21c6f4b8e4e811a9b84b1
PRESENCE_CONTRACT_WORKPAPER_GIT_BLOB_SHA=21f183270f4d41f8e9b6b5059359f601ddd6d85b
PRESENCE_CONTRACT_EVIDENCE_GIT_BLOB_SHA=36bc2e642958e43ec8fa087010c881df7d2280d4
PRESENCE_CONTRACT_EVIDENCE_JSON_SHA256=14769a5c4d935bbf83c747fb2b44dea3b8a019542980ca63568799137b9f53dd
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-repository-presence-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-repository-presence-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_REVIEWED_SET_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_REPOSITORY_PRESENCE_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_TONNES=true
FORBIDDEN_TREAT_CONTENT_PRODUCER_R1_AS_REPOSITORY_PRESENCE=true
FORBIDDEN_TREAT_LIVE_ACTUALS_R1_AS_VERSIONED_FORECAST_ARTIFACT=true
FORBIDDEN_TREAT_REVIEWED_SET_R1_AS_VERSIONED_ARTIFACT=true
FORBIDDEN_TREAT_THIS_GRANT_AS_VERSIONED_FORECAST_ARTIFACT=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
IMPLEMENTATION_AUTHORIZED_TRUE_DOES_NOT_MEAN_IMPLEMENTED=true
IMPLEMENTATION_AUTHORIZED_TRUE_DOES_NOT_MEAN_ARTIFACT_IN_REPOSITORY=true
THIS_FAMILY_UNIQUE_REMAINING_GAP=_no_versioned_incumbent_forecast_artifact_repository_presence_r1
THIS_FAMILY_UNIQUE_REMAINING_GAP_CLOSED=false
PARENT_UNIQUE_REMAINING_GAP=_no_coordinator_reviewed_grain_identity_set_artifact_in_repository
PARENT_UNIQUE_REMAINING_GAP_CLOSED=false
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_IN_THIS_PR=true
~~~

The user authorized issuance of the S3-A2 **incumbent forecast artifact repository-presence** implementation grant
after repository-presence contract freeze on main (#479). This document records what a **later** repository-presence R1
may do when the user again says 「可以实施」. This PR does not perform repository-presence R1, flip
`DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED`, flip `NO_VERSIONED`, flip `NO_REVIEWED`,
write a forecast artifact, invent member literals, invent tonnes, or authorize production or test code mutation.

This is **repository-presence** implementation authorization only. Parent repository-presence contract §§1–9,
artifact contract, content contract, content producer R1, adapter R1, reviewed-set grant (#477), fail-closed
reviewed-set R1 (#478), and live actuals binding remain authoritative and are not reopened. Do not rewrite alignment
contract §6 (`EmptyS2IdentityAlignmentPort` remains the historical production default; alignment §6 SHA
`2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8`).

Repository-presence contract is on main (#479). No coordinator-reviewed grain identity-set artifact exists in
repository today (`NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true`). No lawful versioned incumbent forecast artifact
exists in repository today (`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true`).
`FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY=true`. Default content producer on empty obtain returns `produce()=None`.
`#476` live TRAIN/VAL actuals / parsed SOURCE_002 grains are NOT a coordinator-reviewed identity set and NOT a versioned
forecast artifact. `FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true` remains even though `SOURCE_002_ROW_LEVEL_READ=true`.
This grant authorizes a **later** repository-presence R1 — not writing an artifact today, not flipping `NO_VERSIONED`,
not flipping `NO_REVIEWED`.

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_REVIEWED_SET_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_REVIEWED_SET_IMPLEMENTED=false
REVIEWED_SET_IMPLEMENTED=false
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE=true
LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true
SOURCE_002_ROW_LEVEL_READ=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
OBJECT_ROW_COUNT_AT_REVIEW=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

Repository-presence grant ≠ repository-presence R1 ≠ writing a forecast artifact ≠ versioned artifact in repository.
`CONTENT_PRODUCER_IMPLEMENTED=true` ≠ versioned artifact in repository. `REPOSITORY_PRESENCE_CONTRACT_AUTHORIZED=true`
≠ artifact in repository. `IMPLEMENTATION_AUTHORIZED=true` ≠ `IMPLEMENTED` ≠ artifact in repository ≠ `NO_VERSIONED`
flipped ≠ `NO_REVIEWED` flipped ≠ catalog bindable ≠ completeness verified ≠ backtest/metrics. No versioned artifact;
default producer `produce()=None` on empty obtain; table still 0 rows. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. Parent unique remaining gap
`_no_coordinator_reviewed_grain_identity_set_artifact_in_repository` remains open. This family unique remaining gap
`_no_versioned_incumbent_forecast_artifact_repository_presence_r1` remains open. This grant does not close S3. Jumping to
repository-presence R1 now is forbidden.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
THIS_FAMILY_UNIQUE_REMAINING_GAP=_no_versioned_incumbent_forecast_artifact_repository_presence_r1
THIS_FAMILY_UNIQUE_REMAINING_GAP_CLOSED=false
PARENT_UNIQUE_REMAINING_GAP=_no_coordinator_reviewed_grain_identity_set_artifact_in_repository
PARENT_UNIQUE_REMAINING_GAP_CLOSED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY=true
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE=true
OBJECT_ROW_COUNT_AT_REVIEW=0
~~~

Per parent repository-presence contract §3.2, `NO_VERSIONED` may become false **only after all** of: (1)
`NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=false`; (2) a coordinator-reviewed grain identity set of member-shape
triples `(forecast_cutoff_at, model_id, forecast_quantile)` exists (not invented); (3) lawful versioned incumbent
forecast artifact content for those grains exists, hashed per parent content contract; (4) independent coordinator
review of the presence package. This grant does not invent, enumerate, or exemplify any member-shape value lists or
member literals. This grant does not change frozen Python bytes.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=479
PARENT_PRESENCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md
PARENT_PRESENCE_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=1f6caac8173467a64fe21c6f4b8e4e811a9b84b1
PRESENCE_CONTRACT_EVIDENCE_JSON_SHA256=14769a5c4d935bbf83c747fb2b44dea3b8a019542980ca63568799137b9f53dd
PARENT_ARTIFACT_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c3f37c7f52e56c4412ea0f79ea595b7b18f1c279
CURRENT_ARTIFACT_CONTRACT_GIT_BLOB_SHA=e6da5f5e57738fc713e41d912aecfc0ee7ff0f7a
ARTIFACT_CONTRACT_EVIDENCE_JSON_SHA256=8e19a623c6739abeb047768ef642281b86ac7f2d73ea35fcff83ae3165f40376
ARTIFACT_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
CURRENT_CONTENT_CONTRACT_GIT_BLOB_SHA=92df34d6578ba8bc6f34cbf4dac6dcc980edc3db
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=9d896a0207eae7a6e9224da316bbab344b1e7274
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
GRAIN_ROW_PRESENCE_R1_EVIDENCE_JSON_SHA256=43771f68f87d550f48b1e0aa9bcaa42304676436fc08df31365c6c5fc0763511
CURRENT_POPULATED_ORIGIN_CONTRACT_GIT_BLOB_SHA=94cb84a9c43287a61ccbf31b1436419a7967fb7f
POPULATED_ORIGIN_CONTRACT_EVIDENCE_JSON_SHA256=5610634d659790380881fa12adf6d955bd8d3f6c497879f0d70b32f32ee24e38
POPULATED_ORIGIN_GRANT_EVIDENCE_JSON_SHA256=b149e1d00d93a28696040557ca555864e0bc3f2c65707fa78d9a6b65940de1eb
POPULATED_ORIGIN_R1_EVIDENCE_JSON_SHA256=f431cbceb91d830adfc332311dfbf052e74599080c22cd2736b1bc2f7e4c5ea4
REVIEWED_SET_GRANT_EVIDENCE_JSON_SHA256=0758848cc46be93c2f23e99c038922210a7a053627d0800feb6c3ad1c5566fe9
REVIEWED_SET_R1_EVIDENCE_JSON_SHA256=e25817dd910c24b14221f40e9b8ce6055830e28103074d97e1d9b8536b483337
REVIEWED_SET_R1_WORKPAPER_GIT_BLOB_SHA=b80eb28ec44da86c83d61998a7f4c57694d4027c
REVIEWED_SET_R1_EVIDENCE_GIT_BLOB_SHA=f94fb6206fd2d5b010e7fd7f0975623800c580a4
LIVE_ATTESTATION_EVIDENCE_JSON_SHA256=b8f0f0196bf517eb74bbed97d6a710fad9e3a16d64d7ecc33e955320b1f1c076
LIVE_ACTUALS_EVIDENCE_JSON_SHA256=06ba994644be39db28498a5b26df04cd7425ca641272f242071732939913480b
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
UNIQUE_ALEMBIC_HEAD=e8b2c4d6f1a3
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
FROZEN_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
~~~

## 3. Inherited S2 and parent contract authority (not reopened)

~~~text
DATASET_ID=source-002
DATASET_VERSION=e5-live-v1
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_PARTITION_DATES=2025-08-05..2026-01-30
VALIDATION_PARTITION_DATES=2026-01-31..2026-03-09
TEST_PARTITION_DATES=2026-03-10..2026-04-16
TRAIN_ROW_COUNT=16224
TRAIN_BYTE_COUNT=9087071
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROW_COUNT=8006
VALIDATION_BYTE_COUNT=4484905
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
TEST_REMAINS_SEALED=true
DEFAULT_MONTH_SCOPE=1-4
FORBIDDEN_VARIETIES=普鲜,普青,普冻,废果
FORBIDDEN_FACTORY_BASON=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
MEMBER_SHAPE_ONLY=per_parent_grain_identity_set_contract_grain_triple
SOURCE_002_ROW_LEVEL_READ=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 4. What this authorization grants

A later repository-presence R1 may, under a separate user 「可以实施」 gate, record a hashable repository-presence
evidence package and flip `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED` from `false` to
`true`, and may flip `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` from `true` to `false` **only after** all
parent contract §3.2 preconditions are met. Per parent contract §3.5, if any precondition fails at R1 time:
fail-closed — do not invent members or tonnes, do not flip `NO_VERSIONED`, do not flip `NO_REVIEWED`; at most flip
`DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED`. Honesty required:
`REPOSITORY_PRESENCE_IMPLEMENTED=true` after fail-closed R1 does **NOT** mean a versioned artifact exists in
repository. Repository-presence R1 is **docs-only**; no production or test code mutation is authorized by this grant.

### 4.1 Allowed changes (future implementation only)

~~~text
REPOSITORY_PRESENCE_R1_IS_DOCS_ONLY=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
FORBIDDEN_ADD_ALEMBIC=true
~~~

Future implementation may:

1. Record a hashable repository-presence package **only** when all parent contract §3.2 preconditions are met (not
   invented in grant or R1 docs).
2. If any precondition fails at R1 time: fail-closed per parent contract §3.5 — do not invent members or tonnes; do not
   flip `NO_VERSIONED`; do not flip `NO_REVIEWED`; at most flip
   `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED`.
3. Must not enumerate member literals; must not promote loader-test-only members; must not derive from source-002, live
   actuals, or H7; must not treat content producer R1, adapter R1, reviewed-set R1, or empty `produce()=None` as
   repository presence.

Repository-presence R1 ≠ content producer R1 ≠ adapter R1 ≠ reviewed-set R1 ≠ live actuals binding ≠ SOURCE_002 harvest
grains ≠ catalog closeout.

The only `NO_VERSIONED` flip permitted by a future repository-presence R1 (when all §3.2 preconditions are met) is:

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true → false
~~~

The companion implementation-status flip permitted (including fail-closed R1) is:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED=false → true
~~~

### 4.2 What future repository-presence R1 must keep false / unchanged when preconditions fail

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
REVIEWED_SET_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_REVIEWED_SET_IMPLEMENTED=false
MATCH_TABLE_NAMES=()
MATCH_TABLE_COUNT=0
AUDIT_TABLE_COUNT=106
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
CONTENT_PRODUCER_ON_EMPTY_OBTAIN_RETURNS_NONE=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
OBJECT_ROW_COUNT_AT_REVIEW=0
FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY=true
~~~

Honesty: even after this grant, without a lawful versioned artifact the repository has no versioned forecast artifact,
default producer `produce()=None` on empty obtain, and `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` stays
`true`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

### 4.3 Forbidden in future implementation

~~~text
FORBIDDEN_INVENT_GRAIN_IDENTITY_SET_MEMBERS=true
FORBIDDEN_INVENT_MEMBER_SHAPE_VALUE_LISTS=true
FORBIDDEN_INVENT_TONNES=true
FORBIDDEN_DERIVE_MEMBERS_FROM_SOURCE_002=true
FORBIDDEN_TREAT_CONTENT_PRODUCER_R1_AS_REPOSITORY_PRESENCE=true
FORBIDDEN_TREAT_LIVE_ACTUALS_R1_AS_VERSIONED_FORECAST_ARTIFACT=true
FORBIDDEN_TREAT_REVIEWED_SET_R1_AS_VERSIONED_ARTIFACT=true
FORBIDDEN_H7_FIXTURE_AS_LIVE_EVIDENCE_OR_CONTENT_IDENTITY=true
FORBIDDEN_PROMOTE_LOADER_TEST_ONLY_MEMBERS=true
FORBIDDEN_FLIP_NO_VERSIONED_WITHOUT_LAWFUL_ARTIFACT=true
FORBIDDEN_FLIP_NO_REVIEWED_WITHOUT_REVIEWED_SET=true
FORBIDDEN_WRITE_SELECT_FROM_JOIN_WHERE=true
FORBIDDEN_NEW_ALEMBIC=true
FORBIDDEN_UNSEAL_TEST=true
FORBIDDEN_REWRITE_ALIGNMENT_CONTRACT_SECTION_6_AUDIT=true
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
FORBIDDEN_TREAT_EMPTY_TABLE_AS_VERSIONED_ARTIFACT=true
FORBIDDEN_TREAT_THIS_GRANT_AS_VERSIONED_FORECAST_ARTIFACT=true
~~~

## 5. Frozen Python blob audit (byte-identical; this grant does not touch)

~~~text
GRAIN_IDENTITY_SET_PY_BLOB=eed2ecbcacc2a8173003cba55853a6ef5b5f89c5
INCUMBENT_FORECAST_ARTIFACT_CONTENT_PY_BLOB=0cc05fff3deff00d279070aa246f241ff3754e89
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
ALEMBIC_E8B2C4D6F1A3_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
TEST_CATALOG_ARTIFACT_PY_BLOB=af59a9f1d291ab32eff23684aca477f0e4a852cd
FORBIDDEN_TOUCH_TEST_CATALOG_ARTIFACT_PY=true
~~~

## 6. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTATION_AUTHORIZED=false → true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED=false (companion introduced; not flipped)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-repository-presence-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-acquisition-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-independent-review-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-landing-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md` pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md` pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md` pointer
- `docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md` pointer
- `docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md` pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §166 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

Unchanged live flags retained:

~~~text
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_REPOSITORY_PRESENCE_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
REVIEWED_SET_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_REVIEWED_SET_IMPLEMENTED=false
FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
SOURCE_002_ROW_LEVEL_READ=true
LIVE_ACCEPTED_S2_TRAIN_VAL_ACTUALS_SOURCE_BOUND=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
~~~

## 7. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=672f9f2159b2b5ad35b451973881e5d543892c33b58ebbf870ea6bf2c36e30a3
~~~

## 8. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_REVIEWED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_REPOSITORY_PRESENCE_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_TONNES=true
AWAITING_COORDINATOR_REVIEW=true
~~~
