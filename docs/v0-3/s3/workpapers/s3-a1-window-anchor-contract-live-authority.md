# V0.3-S3-A1 Window-anchor contract live-authority insert

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A1_WINDOW_ANCHOR_CONTRACT_LIVE_AUTHORITY
ARTIFACT_VERSION=s3-a1-window-anchor-contract-live-authority-v1
TASK_ID=V03_S3_A1_WINDOW_ANCHOR_CONTRACT_LIVE_AUTHORITY_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A1_WINDOW_ANCHOR_CONTRACT_LIVE_AUTHORITY_ONLY
PARALLEL_LANE=S3-A1
SLICE=V0.3-S3
ENGLISH_ID=WINDOW_ANCHOR_CONTRACT_LIVE_AUTHORITY
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=3463336d1539332cb9bb81117ff52cf70e9120e6
BASE_MAIN_TREE_SHA=2ee91907f493faaf0ddf336af2cc0f793a617d26
PARENT_S3_A1_PR=300
PARENT_S3_A1_MERGE=ef3702dd168b2c4e9adff133a2807ec1819dfaa7
PARENT_S3_A1_FREEZE_COMMIT=7900e54b95c93797f665a3fc3dd2451f7c3d2f7a
PARENT_S3_A1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a1-window-anchor.md
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
CURRENT_A1_WORKPAPER_GIT_BLOB_SHA=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a1-window-anchor-contract-live-authority.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a1-window-anchor-contract-live-authority.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

S3-A1 evaluation-window anchor contract froze on main in #300
(`docs/v0-3/s3/workpapers/s3-a1-window-anchor.md`, amendment §5.1/§5.3 patches).
That merge added workpaper and evidence JSON and patched the amendment. It did
**not** insert live authority into `docs/v0-3/development-plan.md` §4.4
(`DEVELOPMENT_PLAN_UNCHANGED=true` at freeze). This workpaper records the unique
remaining gap closure: live registry acknowledgment that the frozen A1 contract
is authorized — not executing a window, not materializing evaluation rows, not
authorizing C0 execution, and not rewriting C0 §5 pending snapshot.

~~~text
S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_BACKTEST_EXECUTION_AUTHORIZED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

`S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED=true` ≠ window executed ≠ evaluation
window materialized ≠ `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` ≠
`S3_C0_PIT_BACKTEST_CONTRACT_AUTHORIZED` live ≠ `S3_C_BACKTEST_EXECUTION_AUTHORIZED`
≠ backtest run ≠ C0 §5 freeze rewritten ≠
`S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS` flipped inside C0 freeze fence ≠
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` flipped ≠ S3-B `VERIFICATION_FAILED`
repaired ≠ coverage computable ≠ model/parameter change allowed. This evidence
JSON is not a backtest package or versioned forecast artifact. Catalog first
blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. A2 identity-set
family remains fail-closed; this insert is not origin / members / artifact
authority.

## 1. Unique gap (after #300 A1 freeze)

1. S3-A1 window-anchor contract frozen on main (#300) with amendment §5.1/§5.3.
2. `development-plan.md` §4.4 live state block had no `S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED`.
3. C0 §5 remains freeze snapshot `S3_A1_EVALUATION_WINDOW_ANCHOR_STATUS=PENDING_NOT_MERGED`.
4. Without this insert, coordinators could treat #300 file presence as live registry authority.
5. This merge does not execute a window, does not flip completeness, does not authorize C0.

## 2. Upstream bindings

~~~text
PARENT_S3_A1_PR=300
PARENT_S3_A1_MERGE=ef3702dd168b2c4e9adff133a2807ec1819dfaa7
PARENT_S3_A1_FREEZE_COMMIT=7900e54b95c93797f665a3fc3dd2451f7c3d2f7a
PARENT_S3_A1_WORKPAPER_GIT_BLOB_SHA_AT_FREEZE=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
CURRENT_A1_WORKPAPER_GIT_BLOB_SHA=3db9c30ccae9ac20805cb3021caa989ebbc7f5e2
A1_EVIDENCE_JSON_SHA256=7d5e915bf1eb8b0d7a4f7f271e7f4d492023391a6860e7debc6e403c8898dc89
PARENT_S3_A_PR=299
PARENT_S3_A_MERGE=fd793de12bfe2df646925d9e7adc1d59c046ecdf
PARENT_S3_A_AMENDMENT_GIT_BLOB_SHA_AT_S3_A_FREEZE=1baf930287598f5df78ac28d49c159b4231c0fc6
PARENT_S3_A1_AMENDMENT_GIT_BLOB_SHA_AT_A1_FREEZE=e1109c30b90464e575700ac3a332b3c46c1bcd40
CURRENT_S3_A_AMENDMENT_GIT_BLOB_SHA=110ab6bb8460b882b8e2a6146f0cecc18971492a
CURRENT_P0_CONTRACT_GIT_BLOB_SHA=a2f78e50b3e183d06bf4bb1fb1adc6ba5bde8b56
PARENT_S3_C0_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=3850b7cc85fa87d2cf7aa1b4fb23c3d756d6295b
CURRENT_S3_C0_CONTRACT_GIT_BLOB_SHA=2a771b84fa099361f099710058022d7de68fd70a
CURRENT_S3_B_CONTRACT_GIT_BLOB_SHA=43c07b3ca032e39b339281acdba4e9ad8219307b
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
~~~

## 3. Honest boundary

A1 freeze (#300) ≠ this live-authority insert ≠ A1 grant ≠ A1 R1 ≠ C0
live-authority ≠ C0 execution. `CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_EXECUTE_WINDOW=true`.
`CONTRACT_LIVE_AUTHORITY_MERGE_DOES_NOT_AUTHORIZE_C0_EXECUTION=true`.
`FORBIDDEN_REWRITE_C0_SECTION_5_PENDING_SNAPSHOT=true`. C0 §5
`PENDING_NOT_MERGED` lines remain the C0 freeze snapshot; §16 pointer records
that A1 contract live authority now exists in development-plan without editing §5.

## 4. Unique flip

Only `S3_A1_WINDOW_ANCHOR_CONTRACT_AUTHORIZED` is inserted as `true` in
`docs/v0-3/development-plan.md` §4.4 live state block (immediately after
`S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true`).

Locations:

- `docs/v0-3/development-plan.md` §4.4 live state block and live-authority pointer
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §94 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live paragraph
- `docs/v0-3/s3/s3-pit-backtest-execution-contract.md` §16 pointer

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=f1d403146dfdd442800d5dfe4520a10717b991cafb1ed4b610af431268deac96
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
AWAITING_COORDINATOR_REVIEW=true
~~~
