# V0.3-S3-A2 Accepted S2 identity alignment evidence contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-contract-v1
TASK_ID=V03_S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_ONLY
SLICE=V0.3-S3
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=5b55e2f2323ff79c629aa883d57251bda93d397d
BASE_MAIN_TREE_SHA=953916de3bab04c86239e291c21f68dd053c6f90
CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-accepted-s2-identity-alignment-evidence-contract.json
EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **accepted S2 identity alignment evidence
producer** contract freeze after S2 identity alignment adapter R1 (#323). The
landed `S2IdentityAlignmentAdapter` consumes caller-injected
`VersionedAcceptedS2IdentityAlignmentEvidence` only; default construction remains
fail-closed. This contract defines how a future deterministic producer may
construct that evidence from accepted S2 materialized identities. It does **not**
implement a producer, write live S2 identity facts, produce catalogs, or flip
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE` / `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED`.

~~~text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
DO_NOT_INVENT_HASHES_OR_TONNES=true
~~~

## 1. Upstream bindings (reference only)

~~~text
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
S2_CONTRACT_SHA256=52388e434cf4e0183dbfe2420b4fbcec54fd85934906f4f9a0dfb59e4dd17616
MATERIALIZED_DATASET_IDENTITY_SHA256=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROW_COUNT=16224
VALIDATION_ROW_COUNT=8006
TEST_ROW_COUNT=0
TEST_BYTE_COUNT=240
S2_IDENTITY_ALIGNMENT_CONTRACT_GIT_BLOB_SHA=ed3d16c72c78e8bf7c3c610b6212b7444b95c897
S2_IDENTITY_ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
FORECAST_ARTIFACT_PY_BLOB=f928c6c9fa94e91e33c37edd8e9ab57c6e138480
H7_SUCCESS_FIXTURE_HASH=8e74d6be6bcadc087b2dd7a72dfcb588e849305db598aac5c02a954660f30c18
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
~~~

## 2. Repository audit (read-only at 5b55e2f)

~~~text
S2IdentityAlignmentAdapter default evidence=None → UNBOUND / ()
produce() with forecast only → NO_S2_IDENTITY_ALIGNMENT
catalog_artifact.produce() copies catalog_source_kind from forecast_source_kind
default forecast BOUND_FIXTURE → FIXTURE_ONLY_CATALOG_NOT_BINDABLE may persist
NO_LIVE_S2_IDENTITY_FACTS_IN_REPOSITORY=true
NO_REPOSITORY_SCAN_FOR_EVIDENCE=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 3. Producer contract scope summary

### 3.1 Evidence row and envelope

~~~text
AcceptedS2IdentityEvidenceRow=season,farm,subfarm,variety,harvest_business_date
VersionedAcceptedS2IdentityAlignmentEvidence binds dataset_id,dataset_version,materialized_dataset_identity_sha256,content_identity_sha256,rows
PRODUCER_CARRIES_NO_TONNES=true
PRODUCER_CARRIES_NO_FORECAST_CUTOFF=true
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
CONTENT_IDENTITY_SHA256_MUST_BE_COMPUTED_FROM_REAL_ROWS_IN_FUTURE_IMPL=true
FORBIDDEN_INVENT_CONTENT_IDENTITY_SHA256=true
~~~

### 3.2 Distinction from consumer contract

~~~text
THIS_IS_PRODUCER_CONTRACT=true
S2_IDENTITY_ALIGNMENT_CONTRACT_IS_CONSUMER_CONTRACT=true
ALIGNMENT_CONTRACT_SECTIONS_1_10_NOT_REWRITTEN=true
ADAPTER_R1_ALREADY_LANDED=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
~~~

## 4. What remains forbidden / not authorized

~~~text
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_C_BACKTEST_EXECUTION_AUTHORIZED=false
S3_B_SEMANTICS_VERIFIED_CLAIM_AUTHORIZED=false
TEST_REMAINS_SEALED=true
CURRENT_V0_3_S3_COMPLETE=false
PRODUCTION_IMPLEMENTATION_NOT_AUTHORIZED_BY_THIS_CONTRACT=true
~~~

## 5. Registry flip manifest

~~~text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=false → true
~~~

Locations:

- `docs/v0-3/development-plan.md` §4.4
- `docs/v0-3/s3/s3-daily-rowset-amendment.md` §31 pointer
- `docs/v0-3/s3/s3-s2-identity-alignment-contract.md` §14 pointer
- `docs/v0-3/s3/s3-incumbent-forecast-artifact-contract.md` §15 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-artifact-contract.md` §19 pointer
- `docs/v0-3/s3/s3-evaluation-instance-catalog-binding-contract.md` §20 pointer
- `docs/v0-3/s3/s3-evaluation-instance-registry-contract.md` §23 pointer
- `docs/v0-3/s3/s3-backtest-and-diagnosis-contract.md` §11 live pointer paragraph

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
AWAITING_COORDINATOR_REVIEW=true
~~~
