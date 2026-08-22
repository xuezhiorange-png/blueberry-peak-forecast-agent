# V0.3-S2 SOURCE_002 E4b IDFL winner SQL implementation

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S2_SOURCE_002_E4B_IDFL_WINNER_SQL_IMPLEMENTATION
TASK_CLASS=LANE_C_E4B_IMPLEMENTATION
BASE_MAIN_SHA=741dbde960097ed4606d7d997d898d76baf7f61d
SCHEMA_WORKPAPER=docs/v0-3/s2/workpapers/s2-source-002-idfl-label-side-winner-sql-schema.md
~~~

## Migration

~~~text
NEW_REVISION=a7c3e9f1b2d4
DOWN_REVISION=d4e8f1a2b3c5
UNIQUE_ALEMBIC_HEAD=a7c3e9f1b2d4
NEW_TABLE=s2_idfl_label_side_winner_decision
~~~

## PR scope

- Lane C allowlist: persistence, schemas, hashes, revision_winner, visibility, `__init__`
- Lane C tests: conftest, test_revision_winner, test_visibility, test_cutoff
- One Alembic migration: `backend/alembic/versions/a7c3e9f1b2d4_s2_lane_c_idfl_label_side_winner.py`
- Unique-head oracle pins only (lane_b/lane_d conftest, alembic_cases, historical_backtest, forecast_quality)

## Explicit non-goals

~~~text
LANE_D_START_AUTHORIZED=false
S2_ACCEPTANCE_AUTHORIZED=false
CONTRACT_MUTATED=false
ALLOWLIST_BODY_MUTATED=false
~~~
