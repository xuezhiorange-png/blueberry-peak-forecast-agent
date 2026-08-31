# V0.3-S3-A2 live catalog origin execution

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_LIVE_CATALOG_ORIGIN_EXECUTION
ARTIFACT_VERSION=s3-a2-live-catalog-origin-execution
TASK_CLASS=IMPLEMENTATION
USER_GATE=那你搞啊
COORDINATOR_RUN=bc-01a05131-6262-7c86-9895-dde762dda347
IMPLEMENTER_RUN=bc-01a05131-6262-7c86-9895-dde762dda347
BASE_MAIN_SHA=fde7acec586e83eafd99b755f3049d9e3e4a074c
PARENT_PRESENCE_R1_PR=481
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_A_NEW_CONTRACT=true
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-live-catalog-origin-execution.json
EVIDENCE_JSON_SHA256=36a64657db1e437e90999d0d9446368942faf9c07e68da52f2890ba297e1fcea
~~~

User ordered execution against the already-loaded SOURCE_002 receipts (`那你搞啊`). This workpaper records that run. It is not a new contract, not a grant, not completeness PASS, and not a coordinator-reviewed identity-set file.

Forecast grains come from frozen rolling-backtest calendar policy, not from harvest dates. 2026 default nodes are all illegal because at least one horizon window intersects TEST. Origin falls back to the last legal cutoff before TEST (`VALIDATION_END` minus max horizon) at Asia/Shanghai midnight, crossed with `V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF` and P50/P80/P90. That is 3 identity grains. No tonnes.

## Live result

~~~text
LIVE_EXECUTION_REASON_CODE=ARTIFACT_PRODUCED
CATALOG_REASON_CODE=ARTIFACT_PRODUCED
ORIGIN_ENTRY_COUNT=3
TABLE_ROW_COUNT=3
ALIGNED_IDENTITY_COUNT=809
CATALOG_ENTRY_COUNT=2427
PARSED_TRAIN_ROW_COUNT=16224
PARSED_VALIDATION_ROW_COUNT=8006
PARSED_TOTAL_ROW_COUNT=24230
TEST_ROW_COUNT=0
TEST_REMAINS_SEALED=true
USES_HARVEST_DATE_AS_FORECAST_CUTOFF=false
DECLARED_CATALOG_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
ALIGNMENT_SOURCE_KIND=SOURCE_002_E5_LIVE_V1_TRAIN_VALIDATION_ALIGNMENT
CATALOG_IDENTITY_SHA256=00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af
FORECAST_ARTIFACT_CONTENT_IDENTITY_SHA256=06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=CONTRACT_STILL_BOUND_BLOCKED
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
DEFAULT_HARVEST_OBTAIN_EMPTY=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
DEFAULT_SESSION_PROVIDER_LEFT_UNSET=true
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_TONNES_INVENTED=true
~~~

Injected-port catalog production succeeded. Default harvest `obtain()` remains empty and default catalog construction remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` because this execution does not wire a session into the production default path. Completeness stays blocked: there is still no point-in-time daily curve at cutoff, and weather / plans / maturity / residual tables are empty. Do not invent tonnes.

Frozen blobs unchanged: `test_catalog_artifact.py` `af59a9f1d291ab32eff23684aca477f0e4a852cd`; `catalog_artifact.py` `8196cb7dca33df8708f78789bd2eb9e8243b8354`; grain-identity-set `eed2ecbcacc2a8173003cba55853a6ef5b5f89c5`; content producer `0cc05fff3deff00d279070aa246f241ff3754e89`; Alembic `e8b2c4d6f1a3` `1e0864ebef1d947d4c9466d71efaa759d44c7ad7`. Alignment §6 SHA unchanged.
