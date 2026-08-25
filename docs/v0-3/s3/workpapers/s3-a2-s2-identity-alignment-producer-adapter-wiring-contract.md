# V0.3-S3-A2 S2 identity alignment producer→adapter wiring contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-s2-identity-alignment-producer-adapter-wiring-contract-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=79fa9bf3ec7ab4c532e55f58aefcfb0f09ef4191
BASE_MAIN_TREE_SHA=15760ff16d1120aa120849ec866758105902779f
CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **S2 identity alignment producer→adapter wiring**
contract freeze after postgres obtain R1 (#344). Adapter and evidence producer
services are landed; default catalog factory returns `S2IdentityAlignmentAdapter(evidence=None)`
without calling the producer. This contract freezes fail-closed wiring authority only.
It does **not** implement wiring, issue grants, execute R1, or flip
`NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
~~~

## 1. Why this contract (unique gap after #344)

1. `S2IdentityAlignmentAdapter` landed; default `evidence=None` → `UNBOUND`.
2. `AcceptedS2IdentityAlignmentEvidenceProducer` landed; default `harvest_rows=()` → `produce()`=`None`.
3. `catalog_artifact.py` returns adapter but does not wire producer→evidence.
4. Catalog `produce()` checks forecast first; default blocker `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
5. `catalog_source_kind` copied from forecast, not alignment; default `BOUND_FIXTURE`.
6. Alignment contract §6 6a9fde9 audit snapshot not rewritten; `79fa9bf` default is `Adapter(evidence=None)`.
7. Forecast wiring and postgres obtain explicitly excluded alignment wiring.
8. This contract freezes producer→adapter default wiring rules without implementation.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=344
PARENT_ALIGNMENT_CONTRACT_GIT_BLOB_SHA=7568a608b891d4b98b9aaf7f6857a28eb90bb123
PARENT_EVIDENCE_PRODUCER_CONTRACT_GIT_BLOB_SHA=22f49d7a78bad1a9332040e9f890daa22ef4b1e3
PARENT_CATALOG_ARTIFACT_CONTRACT_GIT_BLOB_SHA=9caa94290d17ac594c0619fe4f442b7050d3615e
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
EVIDENCE_PRODUCER_AUTH_EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
POSTGRES_OBTAIN_GRANT_EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
CATALOG_ARTIFACT_PY_BLOB=968e841527b696d17364ddae11693fadb49462b8
S2_IDENTITY_ALIGNMENT_PY_BLOB=b899e52dbd8752b30395441389ad93fc98d9dbf7
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
~~~

## 3. Repository audit (read-only at 79fa9bf)

~~~text
Adapter landed: default evidence=None → aligned_identities=() → UNBOUND
Producer landed: default harvest_rows=() → produce()=None
catalog_artifact._default_s2_identity_alignment_port() → S2IdentityAlignmentAdapter() without producer call
Catalog produce() forecast-first; default blocker=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
catalog_source_kind from forecast; default declared kind=BOUND_FIXTURE
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
POSTGRES_OBTAIN_R1 did not wire alignment
~~~

## 4. Wiring priority summary

| priority | condition | outcome |
|---|---|---|
| 1 | explicit `alignment_port` | injection wins |
| 2 | default construction | lazy producer→adapter wiring allowed; no new port parameters |
| 3 | empty producer output | `evidence=None` |
| 4 | forbidden default reads | no SOURCE_002 / repo scan / H7 live evidence |
| 5 | default catalog | first blocker `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT` |
| 6 | forecast ok, alignment empty | `NO_S2_IDENTITY_ALIGNMENT` |
| 7 | catalog_source_kind | from forecast only |
| 8 | wiring | does not flip `NO_LIVE_S2` |
| 9 | empty result | no versioned alignment facts claim |

## 5. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false (companion; not flipped)
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
