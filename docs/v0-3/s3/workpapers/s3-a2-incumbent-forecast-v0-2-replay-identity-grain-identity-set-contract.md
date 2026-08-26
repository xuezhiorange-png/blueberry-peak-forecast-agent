# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain identity-set contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=ddb054a8578fb2592609d25dd37c14cfb4ee1744
BASE_MAIN_TREE_SHA=3566161370d2977a577b57969e043fde6f0c5359
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-identity-set-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 replay-identity grain identity-set**
contract freeze after grain-row-presence R1. Grain-row-presence R1 is landed;
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true`.
Frozen table `s3_incumbent_forecast_replay_identity` still has 0 rows. The repository still has
**no** coordinator-reviewed grain identity-set artifact. This contract freezes **what a reviewed
identity-set is and how it is reviewed** — not landing members today, not loader R1, not versioned
artifact.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Unique gap (after grain-row-presence R1)

1. Grain-row-presence R1 landed; table still 0 rows.
2. R1 implemented fail-closed INSERT-if-reviewed-set-else-0-rows only.
3. Grain-row-presence R1 ≠ identity-set; no reviewed artifact in repository.
4. Default provider without reviewed artifact must be empty; grain-row-presence remains 0 rows.
5. Identity-set member shape and review rules not yet frozen as independent contract.
6. Not member landing; not flipping `NO_REVIEWED`; not catalog session wiring; not MATCH; not Alembic.

## 2. Upstream bindings

~~~text
PARENT_GRAIN_ROW_PRESENCE_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=636f2fa960dc8f8b5e58024ca7415a74d0f89a1d
CURRENT_GRAIN_ROW_PRESENCE_CONTRACT_GIT_BLOB_SHA=5210ef2ebf5abb63e558a49653ab26e3b9a517d1
GRAIN_ROW_PRESENCE_R1_EVIDENCE_JSON_SHA256=43771f68f87d550f48b1e0aa9bcaa42304676436fc08df31365c6c5fc0763511
GRAIN_ROW_PRESENCE_GRANT_EVIDENCE_JSON_SHA256=bbdc217b10d5b54081321a069b88929ba56973397f23487ee32bfdfd174533c1
INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_PY_BLOB=5e8fe47036766424d1f47308c27f719129cf9c5f
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
ALEMBIC_REVISION=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen grain identity-set summary

| field | frozen value |
|---|---|
| member shape | `(forecast_cutoff_at, model_id, forecast_quantile)` |
| reviewed artifact in repo | none (must not invent) |
| default provider | fail-closed empty |
| table row count | `0` |
| obtain default | fail-closed `()` |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTATION_AUTHORIZED=false (companion)
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_IDENTITY_SET_IMPLEMENTED=false (companion)
~~~

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=26be24a9a6d7d09be0b1cbf8a52ca415f2e25728736179baf2d06003de150f34
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_LAND_IDENTITY_SET_MEMBERS=true
CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_REVIEWED_GRAIN_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AWAITING_COORDINATOR_REVIEW=true
~~~

Honesty: grain identity-set contract ≠ grant ≠ R1 ≠ loader landing ≠ INSERT ≠ member landing ≠
versioned artifact ≠ catalog closeout. Grain-row-presence R1 ≠ identity-set. Empty table still
0 rows. `NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY` remains `true`. Catalog first blocker
remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
