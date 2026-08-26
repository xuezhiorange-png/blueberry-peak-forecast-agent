# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain identity-set candidate-source contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02307-c032-7da6-8a02-00d9b3518794
BASE_REF=origin/main
BASE_MAIN_SHA=379b9262ea9008337440f69cac7ffd3c7eff2011
BASE_MAIN_TREE_SHA=4939120eacacd4dc0a0d93c67687a9793927c9f6
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-candidate-source-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 replay-identity grain identity-set
candidate-source** contract freeze after independent-review R1. Independent-review R1 is on main and
fail-closed; `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_INDEPENDENT_REVIEW_IMPLEMENTED=true`.
`INDEPENDENT_REVIEW_IMPLEMENTED=true` ≠ independent review performed. `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY`
remains `true`. Frozen table still has 0 rows. Production loader/provider remains empty. Parent contracts freeze
what the set is, fail-closed provider, landing rules, and independent-review provenance. This contract freezes
**candidate-source** — lawful origins and forbidden origins for a later candidate — not acquiring a candidate
today, not landing members, not flipping `NO_REVIEWED`.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_INDEPENDENT_REVIEW_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Unique gap (after independent-review R1)

1. Independent-review R1 on main; fail-closed without reviewed candidate; `NO_REVIEWED` still true.
2. Table still 0 rows; production provider empty; default obtain() without session remains `()`.
3. Candidate-source — where a later candidate may lawfully originate — not yet frozen.
4. Without this freeze, later slices could treat forbidden origins as candidates.
5. Not acquiring a candidate; not landing members; not flipping `NO_REVIEWED`; not INSERT; not versioned artifact.

## 2. Upstream bindings

~~~text
PARENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97918d6b00e74cd9fe7bec4ff80c3930eb31a640
CURRENT_INDEPENDENT_REVIEW_CONTRACT_GIT_BLOB_SHA=057372ec930c3c5ba78e590dba4bd5eb878ee7fb
INDEPENDENT_REVIEW_CONTRACT_EVIDENCE_JSON_SHA256=1789700197063e663fd507c6dd087a592da90e419d7175b03856b7577e18b9c9
INDEPENDENT_REVIEW_GRANT_EVIDENCE_JSON_SHA256=a280a53e1b7b54a829428d68266008dcff328680d8f58d564b07fe63c0a0d6ab
INDEPENDENT_REVIEW_R1_EVIDENCE_JSON_SHA256=c34afe4056a67ac65b086ae213a9b2d1f6e0fcff4911fd8cc1daeb4a86b87ceb
PARENT_LANDING_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=b134b1a9208ae94f42b2f3ffcf82f5613042f4ed
CURRENT_LANDING_CONTRACT_GIT_BLOB_SHA=01ba9f4a2e773d1a5093f793dbd7a21f004df77e
LANDING_R1_EVIDENCE_JSON_SHA256=49ffb1cd4cc664bd6603908e7435c1576d81a21014539e7d95dcaf58abd865ec
PARENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c8b7ccc0ecd02b6e86dc86752e0fe98a898ebbd6
CURRENT_GRAIN_IDENTITY_SET_CONTRACT_GIT_BLOB_SHA=3fe3af547b50c5dc88ffed16e220b031171ff0c7
GRAIN_IDENTITY_SET_CONTRACT_EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
GRAIN_IDENTITY_SET_LOADER_R1_EVIDENCE_JSON_SHA256=a09d0b4398abd6feace3157519bac3164ddfef654b738bbb26c4cdf3addb5f4b
ALEMBIC_REVISION=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen candidate-source summary

| field | frozen value |
|---|---|
| candidate source | lawful hashable origin of member-shape-only set |
| member shape | per parent grain identity-set contract |
| today | no lawful populated candidate source exists |
| this merge | does not acquire candidate; does not flip NO_REVIEWED |
| boundaries | ≠ independent-review ≠ landing ≠ INSERT ≠ versioned artifact |
| table row count | `0` |
| obtain default | fail-closed `()` |

## 4. Honest boundary

Candidate-source contract ≠ grant ≠ candidate-source R1 ≠ independent-review ≠ landing ≠ members landed ≠
INSERT ≠ versioned artifact ≠ catalog closeout. `INDEPENDENT_REVIEW_IMPLEMENTED=true` ≠ independent review
performed. `LANDING_IMPLEMENTED=true` ≠ members landed. `GRAIN_IDENTITY_SET_IMPLEMENTED=true` ≠ members
landed. `CONTRACT_MERGE_DOES_NOT_ACQUIRE_CANDIDATE=true`. `CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true`.
`CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true`.
`CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true`. Historical pointer snapshots may remain
`INDEPENDENT_REVIEW_IMPLEMENTED=false`.

## 5. Unique flip

Only `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_CONTRACT_AUTHORIZED`
flips `false` → `true` in `docs/v0-3/development-plan.md` §4.4 live state block. Companions introduced as
`false`: `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTATION_AUTHORIZED`,
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CANDIDATE_SOURCE_IMPLEMENTED`.

## 6. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=7586088c647fbcd3bfb0d7158aa13ae2b56cf2a0a59d0fc3311971010e21cfb5
~~~
