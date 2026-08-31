# V0.3-S3-A2 Default catalog live-origin obtain contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-default-catalog-live-origin-obtain-contract-v1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
USER_GATE=可以下一步
CONTRACT_ONLY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
COORDINATOR_RUN=bc-01a05131-6262-7c86-9895-dde762dda347
BASE_MAIN_SHA=3fd69ccc292848e13f091bf731fc9241eb6bd4ec
PARENT_LIVE_CATALOG_ORIGIN_PR=482
PARENT_LIVE_CATALOG_ORIGIN_MERGE=3fd69ccc292848e13f091bf731fc9241eb6bd4ec
CONTRACT_PATH=docs/v0-3/s3/s3-default-catalog-live-origin-obtain-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-origin-obtain-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-default-catalog-live-origin-obtain-contract.json
EVIDENCE_JSON_SHA256=f3f13966dafe41cf13f840eb36aa22ad1910f1b0270508a06d105143ba61b6ae
~~~

#482 is on main. Injected-port catalog is `ARTIFACT_PRODUCED`. Default catalog construction
still returns `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This workpaper records the
contract freeze for a later default catalog live-origin obtain — not the obtain itself.

User declared weather and plans temporarily unavailable. This family does not invent them
and does not claim peak tonnes or completeness PASS.

~~~text
S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_CONTRACT_AUTHORIZED=true
S3_A2_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_DEFAULT_CATALOG_LIVE_ORIGIN_OBTAIN_IMPLEMENTED=false
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
WEATHER_UNAVAILABLE=true
PLANS_UNAVAILABLE=true
FORBIDDEN_INVENT_WEATHER=true
FORBIDDEN_INVENT_PLANS=true
FORBIDDEN_INVENT_TONNES=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_NEW_SQLALCHEMY_API_FAMILY=true
~~~
