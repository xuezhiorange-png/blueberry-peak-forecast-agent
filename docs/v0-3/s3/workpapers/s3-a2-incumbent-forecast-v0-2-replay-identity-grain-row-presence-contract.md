# V0.3-S3-A2 Incumbent forecast V0.2 replay-identity grain row presence contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract-v1
TASK_ID=V03_S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
COORDINATOR_RUN=bc-01a02a06-2694-7db3-bffe-cbcc33b2c1a2
BASE_REF=origin/main
BASE_MAIN_SHA=c50e902e02333e91160697c65d282056f4512e18
BASE_MAIN_TREE_SHA=f5e9fec58da51822b9131206f41903d7b8f10996
CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
THIS_DRAFT_IS_NOT_READY=true
~~~

This workpaper records the S3-A2 **incumbent forecast V0.2 replay-identity grain row presence**
contract freeze after live-read R1. Live-read R1 is landed;
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true`. Frozen table
`s3_incumbent_forecast_replay_identity` still has 0 rows. This contract freezes **how grain rows
may later exist** — not INSERT today, not identity-set invention, not versioned artifact.

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
OBJECT_ROW_COUNT_AT_REVIEW=0
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Unique gap (after live-read R1)

1. Live-read R1 landed; table still 0 rows.
2. Default `obtain()` without session remains `()`; session read of empty table remains `()`.
3. Content producer on empty obtain returns `None`; catalog blocker `NO_VERSIONED`.
4. `EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true` but grain row presence rules not yet frozen.
5. No coordinator-reviewed identity-set in repository.
6. Not catalog session wiring; not MATCH; not Alembic; not `NO_VERSIONED` flip.

## 2. Upstream bindings

~~~text
PARENT_LIVE_POSTGRES_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=2a5225f1a7b1fde3abb7c353fa5be3a9e545a61c
LIVE_POSTGRES_READ_R1_EVIDENCE_JSON_SHA256=8b56f82fe1dd9871dfb7f02ef3b9f768f265020f7f62b4078fb9b7feb1187763
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
ALEMBIC_REVISION=e8b2c4d6f1a3
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
~~~

## 3. Frozen grain row presence summary

| field | frozen value |
|---|---|
| table | `s3_incumbent_forecast_replay_identity` |
| grain | `DISTINCT(forecast_cutoff_at,model_id,forecast_quantile)` |
| row count at review | `0` |
| identity-set in repo | none (must not invent) |
| obtain default | fail-closed `()` |

## 4. Registry flip manifest

~~~text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=false → true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=false (companion)
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=false (companion)
~~~

## 5. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=1e7204dc716dd1e65de4b0248ebe4de01638cb31628b0cb10db8e1fdf5aba833
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AWAITING_COORDINATOR_REVIEW=true
~~~

Honesty: grain row presence contract ≠ grant ≠ R1 ≠ INSERT ≠ identity-set invention ≠
versioned artifact ≠ catalog closeout. Empty table still 0 rows. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
