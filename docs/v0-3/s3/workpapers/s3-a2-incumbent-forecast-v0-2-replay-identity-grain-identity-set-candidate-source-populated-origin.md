# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain identity-set candidate-source populated-origin contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=02588eb53b82b86f1be8af8700f8c658b6925bae
BASE_MAIN_TREE_SHA=16bb3af530f4f17d5e4c2fdc6388607626f17447
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-populated-origin.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 replay-identity grain identity-set candidate-source
populated-origin** contract freeze after acquisition fail-closed R1 on main. Parent acquisition contract freezes **how** a
later slice may bind a real lawful populated origin into a hashable acquisition evidence package.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTED=true`.
Acquisition R1 closed the HOW process fail-closed without a lawful populated origin. Acquisition R1 evidence is **not** a
populated-origin attestation package. This contract freezes **what** constitutes a lawful populated origin for later
acquisition — not attesting one today, not landing members, not flipping `NO_REVIEWED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Unique gap (after acquisition R1)

1. Candidate-source contract on main freezes WHERE; acquisition contract on main freezes HOW; acquisition R1 fail-closed on main.
2. `ACQUISITION_IMPLEMENTED=true` ≠ lawful populated origin exists ≠ acquisition performed.
3. Acquisition R1 evidence ≠ populated-origin package.
4. Table still 0 rows; production provider empty; default obtain() without session remains `()`.
5. Populated origin — WHAT attestation makes a lawful origin populated — not yet frozen.
6. Without this freeze, later slices could treat acquisition R1 as populated-origin or invent members.
7. Not attesting populated origin; not landing members; not flipping `NO_REVIEWED`; not INSERT; not versioned artifact.

## 2. Upstream bindings

~~~text
PARENT_ACQUISITION_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=fbef3a7686f32bda7d9c24a90b7f65629bf81921
CURRENT_ACQUISITION_CONTRACT_GIT_BLOB_SHA=33ea663bd786e89051f9afc44022e0f5293643da
ACQUISITION_CONTRACT_EVIDENCE_JSON_SHA256=5b01beeb76a3d8735872a89147620bc19090793c9dea1867c721ad8ae1f74d27
ACQUISITION_GRANT_EVIDENCE_JSON_SHA256=31253fb3b4b18025728557b7060ca5ebb8363dc80bc274fe64dc3bab5ff43dea
ACQUISITION_R1_EVIDENCE_JSON_SHA256=2fa6a2b4568bb189d125095c29980a02579372b8eec8e17ae6470b0d708c0677
PARENT_CANDIDATE_SOURCE_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=202aeb5198e61e504cab053ad781437663b8ea06
CURRENT_CANDIDATE_SOURCE_CONTRACT_GIT_BLOB_SHA=92dd0e6a765c2791c087c613536c0d88197c8254
CANDIDATE_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=7586088c647fbcd3bfb0d7158aa13ae2b56cf2a0a59d0fc3311971010e21cfb5
CANDIDATE_SOURCE_GRANT_EVIDENCE_JSON_SHA256=1e8ca33ea4a1502983311c360d0ac7fecdfa05f861d9346cecb5e39f17a58378
CANDIDATE_SOURCE_R1_EVIDENCE_JSON_SHA256=6cc3c4dd7276e3f82bd19957e806ac130e8538ef70168e0d2395b61252cb343f
PARENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97918d6b00e74cd9fe7bec4ff80c3930eb31a640
CURRENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA=b95b7713b49eb35fed00ed985e3db0ef721f2e34
INDEPENDENT_REVIEW_R1_EVIDENCE_JSON_SHA256=c34afe4056a67ac65b086ae213a9b2d1f6e0fcff4911fd8cc1daeb4a86b87ceb
PARENT_LANDING_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b134b1a9208ae94f42b2f3ffcf82f5613042f4ed
CURRENT_LANDING_CONTRACT_GIT_BLOB_SHA=2ee2494206f605295b3b4bf739bb95c300c7dac4
LANDING_R1_EVIDENCE_JSON_SHA256=49ffb1cd4cc664bd6603908e7435c1576d81a21014539e7d95dcaf58abd865ec
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=b066824e74789323edd025774131563f98d08f75
GRAIN_IDENTITY_SET_LOADER_R1_EVIDENCE_JSON_SHA256=a09d0b4398abd6feace3157519bac3164ddfef654b738bbb26c4cdf3addb5f4b
GRAIN_ROW_PRESENCE_R1_EVIDENCE_JSON_SHA256=43771f68f87d550f48b1e0aa9bcaa42304676436fc08df31365c6c5fc0763511
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
ALEMBIC_REVISION=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen populated-origin summary

| field | frozen value |
|---|---|
| populated origin | lawful non-empty member-shape provenance outside contract docs |
| member shape | per parent grain identity-set contract |
| today | no lawful populated origin exists |
| acquisition R1 | fail-closed process closure only; not populated-origin package |
| this merge | does not attest populated origin; does not flip NO_REVIEWED |
| boundaries | ≠ candidate-source WHERE ≠ CS R1 ≠ acquisition ≠ acquisition R1 |
| table row count | `0` |
| obtain default | fail-closed `()` |

## 4. Honest boundary

Populated-origin contract ≠ grant ≠ populated-origin R1 ≠ acquisition contract ≠ acquisition R1 ≠ candidate-source WHERE
contract ≠ candidate-source R1 ≠ independent-review ≠ landing ≠ members landed ≠ INSERT ≠ versioned artifact ≠ catalog
closeout. `ACQUISITION_IMPLEMENTED=true` ≠ lawful populated origin exists ≠ acquisition performed.
`CANDIDATE_SOURCE_IMPLEMENTED=true` ≠ lawful populated origin exists. `INDEPENDENT_REVIEW_IMPLEMENTED=true` ≠ independent
review performed. `LANDING_IMPLEMENTED=true` ≠ members landed. `CONTRACT_MERGE_DOES_NOT_ACQUIRE_CANDIDATE=true`.
`CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true`.
`CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true`. Historical pointer snapshots may remain
`CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT_AUTHORIZED=false`.

## 5. Unique flip

Only `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_CONTRACT_AUTHORIZED` flips `false` → `true` in `docs/v0-3/development-plan.md` §4.4 live state block.
Companions introduced as `false`: `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_IMPLEMENTATION_AUTHORIZED`, `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_POPULATED_ORIGIN_IMPLEMENTED`.

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=5610634d659790380881fa12adf6d955bd8d3f6c497879f0d70b32f32ee24e38
~~~
