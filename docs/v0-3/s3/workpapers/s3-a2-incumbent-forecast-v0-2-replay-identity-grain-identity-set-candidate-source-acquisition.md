# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain identity-set candidate-source acquisition contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-acquisition-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=b1efd86302b180071ac5f4ffc81195c85be423ed
BASE_MAIN_TREE_SHA=de0e7da569b625454aeb3ec4e7dbd3a8800b1393
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-acquisition-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-acquisition.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-acquisition.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 replay-identity grain identity-set candidate-source
acquisition** contract freeze after candidate-source fail-closed R1 (#377). Parent candidate-source contract freezes
**where** a later candidate may lawfully originate. Candidate-source R1 closed the WHERE process fail-closed without a
lawful populated source. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTED=true`.
`CANDIDATE_SOURCE_IMPLEMENTED=true` ≠ lawful populated candidate source exists. Candidate-source R1 evidence is **not**
a populated-source acquisition package. This contract freezes **how** a later slice may bind a real lawful populated
origin into a hashable acquisition evidence package — not acquiring a candidate today, not landing members, not flipping
`NO_REVIEWED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Unique gap (after candidate-source R1)

1. Candidate-source contract on main freezes WHERE; candidate-source R1 fail-closed on main; `NO_REVIEWED` still true.
2. `CANDIDATE_SOURCE_IMPLEMENTED=true` ≠ lawful populated source exists ≠ acquisition performed.
3. Candidate-source R1 evidence ≠ acquisition package.
4. Table still 0 rows; production provider empty; default obtain() without session remains `()`.
5. Acquisition — HOW to bind a lawful populated origin into a hashable package — not yet frozen.
6. Without this freeze, later slices could treat CS R1 as acquisition or invent members.
7. Not acquiring a candidate; not landing members; not flipping `NO_REVIEWED`; not INSERT; not versioned artifact.

## 2. Upstream bindings

~~~text
PARENT_CANDIDATE_SOURCE_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=202aeb5198e61e504cab053ad781437663b8ea06
CURRENT_CANDIDATE_SOURCE_CONTRACT_GIT_BLOB_SHA=3d6b21b83a08594c87523ee93352951bd4f72e91
CANDIDATE_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=7586088c647fbcd3bfb0d7158aa13ae2b56cf2a0a59d0fc3311971010e21cfb5
CANDIDATE_SOURCE_GRANT_EVIDENCE_JSON_SHA256=1e8ca33ea4a1502983311c360d0ac7fecdfa05f861d9346cecb5e39f17a58378
CANDIDATE_SOURCE_R1_EVIDENCE_JSON_SHA256=6cc3c4dd7276e3f82bd19957e806ac130e8538ef70168e0d2395b61252cb343f
PARENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97918d6b00e74cd9fe7bec4ff80c3930eb31a640
CURRENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA=aceed790b390f9d63d7de33302bca7dd90e9fd71
INDEPENDENT_REVIEW_R1_EVIDENCE_JSON_SHA256=c34afe4056a67ac65b086ae213a9b2d1f6e0fcff4911fd8cc1daeb4a86b87ceb
PARENT_LANDING_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b134b1a9208ae94f42b2f3ffcf82f5613042f4ed
CURRENT_LANDING_CONTRACT_GIT_BLOB_SHA=cc98db6d5beb9dc3896e00cb5d01edaae2ad8078
LANDING_R1_EVIDENCE_JSON_SHA256=49ffb1cd4cc664bd6603908e7435c1576d81a21014539e7d95dcaf58abd865ec
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=9ee5b5234f7e1c912b3f8e420ffc3771b33940dc
GRAIN_IDENTITY_SET_LOADER_R1_EVIDENCE_JSON_SHA256=a09d0b4398abd6feace3157519bac3164ddfef654b738bbb26c4cdf3addb5f4b
GRAIN_ROW_PRESENCE_R1_EVIDENCE_JSON_SHA256=43771f68f87d550f48b1e0aa9bcaa42304676436fc08df31365c6c5fc0763511
ALIGNMENT_SECTION_6_SHA256=2eaf3719b1cb2e7097c6ded457098a0563b46c0965eabf38d60327b1a6b2a7a8
ALEMBIC_REVISION=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen acquisition summary

| field | frozen value |
|---|---|
| acquisition | bind lawful populated origin into hashable evidence package |
| member shape | per parent grain identity-set contract |
| today | no lawful populated candidate source exists |
| CS R1 | fail-closed process closure only; not acquisition package |
| this merge | does not acquire candidate; does not flip NO_REVIEWED |
| boundaries | ≠ candidate-source WHERE ≠ CS R1 ≠ independent-review ≠ landing |
| table row count | `0` |
| obtain default | fail-closed `()` |

## 4. Honest boundary

Acquisition contract ≠ grant ≠ acquisition R1 ≠ candidate-source WHERE contract ≠ candidate-source R1 ≠
independent-review ≠ landing ≠ members landed ≠ INSERT ≠ versioned artifact ≠ catalog closeout.
`CANDIDATE_SOURCE_IMPLEMENTED=true` ≠ lawful populated source exists ≠ acquisition performed.
`INDEPENDENT_REVIEW_IMPLEMENTED=true` ≠ independent review performed. `LANDING_IMPLEMENTED=true` ≠ members landed.
`CONTRACT_MERGE_DOES_NOT_ACQUIRE_CANDIDATE=true`. `CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true`.
`CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true`. Historical pointer snapshots may remain
`CANDIDATE_SOURCE_ACQUISITION_CONTRACT_AUTHORIZED=false`.

## 5. Unique flip

Only `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_CONTRACT_AUTHORIZED`
flips `false` → `true` in `docs/v0-3/development-plan.md` §4.4 live state block. Companions introduced as `false`:
`S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTATION_AUTHORIZED`,
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_ACQUISITION_IMPLEMENTED`.

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=5b01beeb76a3d8735872a89147620bc19090793c9dea1867c721ad8ae1f74d27
~~~
