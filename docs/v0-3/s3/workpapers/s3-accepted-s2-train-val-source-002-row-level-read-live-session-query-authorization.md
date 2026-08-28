# V0.3-S3-A2 Accepted S2 TRAIN/VALIDATION SOURCE_002 row-level-read live-session-query implementation authorization

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZATION
ARTIFACT_VERSION=s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-authorization-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_AUTHORIZATION_R1
TASK_CLASS=DOCS_ONLY_AUTHORIZATION_ISSUANCE
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_GRANT_ONLY
PARALLEL_LANE=S3-A2-ACCEPTED-S2-SOURCE-002-ROW-LEVEL-READ-LIVE-SESSION-QUERY
SLICE=V0.3-S3
ENGLISH_ID=ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY
USER_GATE=可以实施
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=e29137b93fc091983ae3c9a5b875a1981a56d30b
BASE_MAIN_TREE_SHA=741515dd8f3fd5f366ac017c6863908e842a1ed6
PARENT_CONTRACT_PR=422
PARENT_CONTRACT_MERGE=ef4b3bc589aa256255541b9e006c76aba4d01d0e
PARENT_LIVE_AUTHORITY_PR=423
PARENT_LIVE_AUTHORITY_MERGE=e29137b93fc091983ae3c9a5b875a1981a56d30b
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=77cd5e885eb8f8a670beee8eac530681c2488096d4dc1d5112c8b8066e2cb8a4
LIVE_AUTHORITY_WORKPAPER=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-contract-live-authority.md
LIVE_AUTHORITY_WORKPAPER_GIT_BLOB_SHA=26bf595e0eb8e238b4428cb7dd7e6c346f5d5e8a
LIVE_AUTHORITY_EVIDENCE_GIT_BLOB_SHA=88a00238acfbe9c872c5c6dc61b6367439fdc28b
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-authorization.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-authorization.json
GRANT_ONLY=true
NO_STEP_IMPLIES_THE_NEXT=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
THIS_PR_IS_NOT_R1=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_FLIP_PARENT_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_MAKE_THE_BOUND_SESSION_QUERYABLE=true
GRANT_MERGE_DOES_NOT_OBTAIN_CONTENT_BYTES=true
GRANT_MERGE_DOES_NOT_BIND_A_LIVE_SESSION=true
GRANT_MERGE_DOES_NOT_ATTEST_OFFICIAL_HASHES_FROM_A_LIVE_READ=true
GRANT_MERGE_DOES_NOT_TOUCH_PYTHON=true
THIS_FAMILY_IS_THE_BOUND_LIVE_SESSION_QUERYABLE_SLICE=true
THIS_FAMILY_IS_NOT_THE_DETERMINISTIC_READER_ATTESTATION_SLICE=true
THIS_FAMILY_IS_NOT_THE_LIVE_SESSION_WIRING_SLICE=true
THIS_FAMILY_IS_NOT_THE_LIVE_OBTAIN_SLICE_FOR_TRAIN_VAL_CONTENT_BYTES=true
THIS_FAMILY_MUST_NOT_UNIQUELY_FLIP_SOURCE_002_ROW_LEVEL_READ=true
PARENT_FAMILY_HOLDS_UNIQUE_LIVE_FLIP_OF_SOURCE_002_ROW_LEVEL_READ=true
THIS_FAMILY_MUST_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED=true
THIS_FAMILY_MUST_NOT_CLOSE_LIVE_OBTAIN_UNIQUE_REMAINING_GAP=true
LIVE_SESSION_FAMILY_UNIQUE_REMAINING_GAP_CLOSED=true
LIVE_OBTAIN_FAMILY_IS_NOT_CLOSED=true
THIS_FAMILY_DOCS_ONLY_STAGES_MUST_NOT_FLIP_SOURCE_002_ROW_LEVEL_READ=true
THIS_GRANT_DOES_NOT_AUTHORIZE_A_DOCS_ONLY_IMPLEMENTED_FLIP_AS_SUBSTITUTE_FOR_A_QUERYABLE_SESSION=true
LATER_R1_THAT_MAKES_SESSION_QUERYABLE_MUST_NOT_UNIQUELY_FLIP_SOURCE_002_ROW_LEVEL_READ=true
LATER_R1_MUST_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED=true
FORBIDDEN_REWRITE_LIVE_SESSION_QUERY_FREEZE_IDENTITY=true
FORBIDDEN_REWRITE_LIVE_SESSION_QUERY_FREEZE_FENCE=true
FORBIDDEN_REWRITE_LIVE_SESSION_FREEZE_IDENTITY=true
FORBIDDEN_REWRITE_LIVE_OBTAIN_FREEZE_IDENTITY=true
FORBIDDEN_REWRITE_SOURCE_002_ROW_LEVEL_READ_FREEZE=true
FORBIDDEN_AUTHORIZE_S3_B_COVERAGE=true
FORBIDDEN_AUTHORIZE_S4=true
~~~

The user authorized issuance of the S3-A2 **accepted S2 TRAIN/VALIDATION
SOURCE_002 row-level-read live-session-query** implementation grant after live
contract authority merged on main (#423). This document records what a
**later** implementation R1 of this live-session-query family may do when the
user again says 「可以实施」. This PR does not make the bound session
synchronously queryable, does not obtain TRAIN/VAL `content_bytes`, does not
attest official hashes from a live read, does not flip
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED`,
does not flip parent `IMPLEMENTED`, does not flip live-obtain `IMPLEMENTED`,
does not flip `SOURCE_002_ROW_LEVEL_READ`, does not land identity-set members,
and does not authorize production or test code mutation.

This is **live-session-query implementation** authorization only. Parent freeze
(#422), live contract authority (#423), live-obtain family (#418–#421),
live-session family (#414–#417), parent SOURCE_002 family (#410–#413),
kg-read family (#406–#409), origin family (#402–#405), populated-origin closed
family, C0 §5 pending snapshot, P0, S3-B family, and A2 identity-set family
remain authoritative and are not reopened.

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED=false
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_IMPLEMENTED=false
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
DO_NOT_INVENT_HASHES_OR_TONNES=true
THIS_FAMILY_IS_THE_BOUND_LIVE_SESSION_QUERYABLE_SLICE=true
THIS_FAMILY_IS_NOT_THE_DETERMINISTIC_READER_ATTESTATION_SLICE=true
THIS_FAMILY_IS_NOT_THE_LIVE_SESSION_WIRING_SLICE=true
THIS_FAMILY_IS_NOT_THE_LIVE_OBTAIN_SLICE_FOR_TRAIN_VAL_CONTENT_BYTES=true
THIS_FAMILY_MUST_NOT_UNIQUELY_FLIP_SOURCE_002_ROW_LEVEL_READ=true
PARENT_FAMILY_HOLDS_UNIQUE_LIVE_FLIP_OF_SOURCE_002_ROW_LEVEL_READ=true
THIS_FAMILY_MUST_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED=true
THIS_FAMILY_MUST_NOT_CLOSE_LIVE_OBTAIN_UNIQUE_REMAINING_GAP=true
LIVE_SESSION_FAMILY_UNIQUE_REMAINING_GAP_CLOSED=true
LIVE_OBTAIN_FAMILY_IS_NOT_CLOSED=true
LIVE_SESSION_PROVIDER_BOUND=true
DEFAULT_SESSION_PROVIDER_UNSET=false
BOUND_LIVE_SESSION_IS_SYNCHRONOUSLY_QUERYABLE=false
ACCEPTED_S2_TRAIN_VAL_CONTENT_BYTES_OBTAINED_FROM_BOUND_LIVE_SESSION=false
OFFICIAL_HASHES_ATTESTED_FROM_A_LIVE_READ=false
LIVE_OBTAIN_THROUGH_BOUND_SESSION_REASON_CODE=FAIL_CLOSED_SESSION_UNREADABLE
QUERYABLE_BOUND_SESSION_IS_NOT_SOURCE_002_ROW_LEVEL_READ=true
QUERYABLE_BOUND_SESSION_IS_NOT_CONTENT_BYTES_OBTAINED=true
~~~

`S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=true` ≠
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED` ≠
bound session synchronously queryable ≠ TRAIN/VAL `content_bytes` obtained ≠
`SOURCE_002_ROW_LEVEL_READ` ≠ parent
`DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED` ≠
live-obtain `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_IMPLEMENTED`.
`#422` / `#423` contract-file fence
`S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=false`
remains historical freeze snapshot; live authority is
`docs/v0-3/development-plan.md` §4.4.
This grant does not authorize a docs-only `IMPLEMENTED` flip as a substitute
for a queryable session. Unique live flip of `SOURCE_002_ROW_LEVEL_READ`
remains reserved for the parent SOURCE_002 family (#410–#413). Catalog first
blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.

## 1. Unique remaining gap (this grant does not fill it)

~~~text
UNIQUE_REMAINING_GAP=_bound_live_session_is_not_synchronously_queryable
PARENT_UNIQUE_REMAINING_GAP=_deterministic_reader_has_not_attested_train_val_official_content_hashes_from_a_live_read
LIVE_OBTAIN_UNIQUE_REMAINING_GAP=_accepted_s2_train_val_content_bytes_not_obtained_from_the_bound_live_session
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED=false
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false
SOURCE_002_ROW_LEVEL_READ=false
LIVE_SESSION_PROVIDER_BOUND=true
BOUND_LIVE_SESSION_IS_SYNCHRONOUSLY_QUERYABLE=false
ACCEPTED_S2_TRAIN_VAL_CONTENT_BYTES_OBTAINED_FROM_BOUND_LIVE_SESSION=false
~~~

Live-session-query freeze (#422) and live contract authority (#423) are on main.
The live-session family unique remaining gap is closed. Live-obtain unique
remaining gap stays open. The bound live session is not synchronously
queryable. This grant authorizes a **later** implementation R1 of this family to
make it queryable — it does not perform that work today.

## 2. Upstream bindings

~~~text
PARENT_CONTRACT_PR=422
PARENT_CONTRACT_MERGE=ef4b3bc589aa256255541b9e006c76aba4d01d0e
PARENT_LIVE_AUTHORITY_PR=423
PARENT_LIVE_AUTHORITY_MERGE=e29137b93fc091983ae3c9a5b875a1981a56d30b
LIVE_AUTHORITY_EVIDENCE_JSON_SHA256=77cd5e885eb8f8a670beee8eac530681c2488096d4dc1d5112c8b8066e2cb8a4
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a04ded1314bd4e01059127b5588d5866eb82b994
CURRENT_S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_CONTRACT_GIT_BLOB_SHA=e4f6066eb786a75499b40a85edbdb62290f73be3
S3_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_FREEZE_EVIDENCE_JSON_SHA256=e54c25da7fafe65ff65625f4bd92dd1315d84c7989aad900ba01741157f4d618
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=a06a0b5987aa4bc9ad3b5f42a40922efc9e42484
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=3dc5c0c3d94c583dfee3c2c057ec936112d1af8d
CURRENT_DEVELOPMENT_PLAN_GIT_BLOB_SHA_AT_BASE=ed60ff770eef56d46efa6e60c9ca6a131593dd8b
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

Historical pointer snapshots retain their own `CURRENT_*` at insert time and
must not be refreshed by this grant.

## 3. Frozen subsequent R1 procedure (execution not authorized in this grant)

The following checklist is frozen for a future separately authorized
implementation R1 pass of this family. This grant does not execute it.

### 3.1 Procedure steps

1. Re-bind each referenced git blob SHA on then-current `origin/main`.
2. Confirm freeze workpaper blob is still
   `75d0e493a886cdebafe084124137a496be726066` and freeze evidence content SHA256
   is still `e54c25da7fafe65ff65625f4bd92dd1315d84c7989aad900ba01741157f4d618`;
   live-authority evidence SHA256 is still
   `77cd5e885eb8f8a670beee8eac530681c2488096d4dc1d5112c8b8066e2cb8a4`.
3. Confirm live-session-query contract file fence still contains
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=false`
   (historical freeze snapshot; R1 must not rewrite freeze fence).
4. Confirm contract top identity block `BASE_MAIN_SHA` is still
   `c572e69569b6e170d60b5f1949f903b846332cac` and historical `CURRENT_*`
   snapshots are not refreshed.
5. Confirm live §4.4 has
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_CONTRACT_AUTHORIZED=true`
   and
   `S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=true`.
6. Confirm copied official hashes still match S2 acceptance package (reference
   only, do not recompute); TEST remains sealed. Bound live session is already
   in place (`LIVE_SESSION_PROVIDER_BOUND=true`) and is not synchronously
   queryable. This grant does not make it queryable.
7. Confirm populated-origin freeze `FAIL_CLOSED_NO_LAWFUL_POPULATED_ORIGIN_TODAY`
   is not rewritten; C0 §5 `PENDING_NOT_MERGED` is not rewritten; parent SOURCE_002
   freeze is not rewritten; live-session freeze identity `e9f0fbb8…` and
   live-obtain freeze identity `915b6255…` are not rewritten.
8. Must not invent hashes/tonnes/DSN/`create_engine`, unseal TEST, uniquely
   flip `SOURCE_002_ROW_LEVEL_READ` / parent `IMPLEMENTED` / live-obtain
   `IMPLEMENTED` / `NO_VERSIONED`, touch Python in this grant, or treat H7
   fixture `8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18`
   as live evidence.
9. Later R1 of **this** family may make the bound live session synchronously
   queryable. A queryable session is not content_bytes obtained and is not
   `SOURCE_002_ROW_LEVEL_READ`. Unique live flip of `SOURCE_002_ROW_LEVEL_READ`
   remains reserved for the parent SOURCE_002 family (#410–#413). This grant
   does not execute that R1. A later docs-only R1, if issued, must not claim
   the session is queryable and must not uniquely flip
   `SOURCE_002_ROW_LEVEL_READ`. This grant leaves
   `DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED=false`,
   live-obtain `IMPLEMENTED=false`, parent `IMPLEMENTED=false`, and
   `SOURCE_002_ROW_LEVEL_READ=false`.

### 3.2 Honest boundary

Live-session-query freeze (#422) ≠ live-authority (#423) ≠ this grant ≠
queryable-session R1 ≠ content_bytes obtained ≠ `SOURCE_002_ROW_LEVEL_READ`.
`GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true`.
`GRANT_MERGE_DOES_NOT_MAKE_THE_BOUND_SESSION_QUERYABLE=true`.
`THIS_FAMILY_IS_THE_BOUND_LIVE_SESSION_QUERYABLE_SLICE=true`.
`THIS_FAMILY_MUST_NOT_UNIQUELY_FLIP_SOURCE_002_ROW_LEVEL_READ=true`.
`THIS_FAMILY_MUST_NOT_FLIP_LIVE_OBTAIN_IMPLEMENTED=true`.
`THIS_GRANT_DOES_NOT_AUTHORIZE_A_DOCS_ONLY_IMPLEMENTED_FLIP_AS_SUBSTITUTE_FOR_A_QUERYABLE_SESSION=true`.

## 4. Six-file manifest

| # | path |
|---|------|
| 1 | `docs/v0-3/development-plan.md` |
| 2 | `docs/v0-3/s3/s3-daily-rowset-amendment.md` |
| 3 | `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` |
| 4 | `docs/v0-3/s3/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-contract.md` |
| 5 | `docs/v0-3/s3/workpapers/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-authorization.md` |
| 6 | `docs/v0-3/s3/evidence/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-authorization.json` |

No seventh file. No Python, Alembic, tests, or edits to C0, S3-D, metric, S3-B,
populated-origin, origin contract, kg-read contract, parent SOURCE_002
row-level-read contract, live-session contract, or live-obtain contract.
Family contract top identity block from #422 remains unchanged; only §14
appended.

## 5. Unique flip

~~~text
S3_A2_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTATION_AUTHORIZED=false → true
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_SESSION_QUERY_IMPLEMENTED=false (companion unchanged)
SOURCE_002_ROW_LEVEL_READ=false (unchanged)
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_IMPLEMENTED=false (parent unchanged)
DETERMINISTIC_ACCEPTED_S2_TRAIN_VAL_SOURCE_002_ROW_LEVEL_READ_LIVE_OBTAIN_IMPLEMENTED=false (live-obtain unchanged)
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and authorization pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §123 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` Live paragraph immediately before ## 12
- `docs/v0-3/s3/s3-accepted-s2-train-val-source-002-row-level-read-live-session-query-contract.md` §14 pointer

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=dbe5acf890743e4ed51405f498e556677171cb63eb238e09fdd80013cec8ce98
~~~

## 7. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
GRANT_MERGE_DOES_NOT_FLIP_IMPLEMENTED=true
GRANT_MERGE_DOES_NOT_MAKE_THE_BOUND_SESSION_QUERYABLE=true
AWAITING_COORDINATOR_REVIEW=true
~~~
