# V0.3-S3-A2 S2 identity alignment harvest source contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-s2-identity-alignment-harvest-source-contract-v1
TASK_ID=V03_S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_R1
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_ONLY
SLICE=V0.3-S3
ENGLISH_ID=S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE
USER_GATE=可以下一步
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=3f411cdcc1c56642ca6c9abc2b4476ace83d8c39
BASE_MAIN_TREE_SHA=6cec0ee6157f3fa994e1ce924f03372fac47f669
CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
~~~

This workpaper records the S3-A2 **S2 identity alignment harvest source** contract
freeze after producer→adapter wiring R1 (#347). Wiring is landed; default
`harvest_rows=()` still yields `produce()`=`None`. This contract freezes the only
permitted future harvest source authority path. It does **not** implement obtain,
issue grants, execute R1, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED`.

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DO_NOT_INVENT_HASHES_OR_TONNES=true
FORBIDDEN_INVENT_SQL_OR_TABLE_NAMES=true
~~~

## 1. Why this contract (unique gap after #347)

1. Wiring R1 landed producer→adapter default chain.
2. Default `harvest_rows=()` → `produce()`=`None` → `evidence=None` → `UNBOUND`.
3. Producer has no harvest source seam like forecast `obtain()`.
4. Catalog default still passes `harvest_rows=default()`; no SOURCE_002 read.
5. Without frozen harvest source rules, later R1 could invent rows or misuse unverified rowset.
6. This contract freezes fail-closed harvest source authority without implementation.

## 2. Upstream bindings (reference only)

~~~text
PARENT_PR=347
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_GRANT_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
WIRING_R1_EVIDENCE_GIT_BLOB_SHA=ffcbff7dedf4da263e30e885fb07881f779d711f
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S2_CONTRACT_GIT_BLOB_SHA=0e974ba408122bc2f8b0ee4108fb1af136ec1099
ALIGNMENT_PROJECTION_VERSION=v0-3-s3-a2-s2-identity-alignment-projection-v1
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IDENTITY_VERSION=v0-3-s3-a2-accepted-s2-identity-alignment-evidence-identity-v1
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PY_BLOB=14e5614c9069b7b50d12bf3caa36305245c2cc39
~~~

## 3. Repository audit (read-only at 3f411cd)

~~~text
Wiring R1: producer.produce() wired into adapter.evidence
Default harvest_rows=() → produce()=None → evidence=None → UNBOUND
Producer accepts tuple[MaterializableRow,...] only
No harvest source seam exists yet
Catalog default harvest_rows=default(); no SOURCE_002 read
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
SOURCE_002_ROW_LEVEL_READ=false
~~~

## 4. Obtain priority summary

| priority | condition | outcome |
|---|---|---|
| 1 | explicit non-empty `harvest_rows` | injection wins |
| 2 | default construction | future optional internal harvest_source; no new port parameters |
| 3 | empty harvest_rows or empty obtain | produce()=None |
| 4 | forbidden default reads | no SOURCE_002 / repo scan / H7 live / unverified rowset |
| 5 | TEST intersection | exclude; empty → () |
| 6 | default catalog | first blocker NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT |
| 7 | forecast ok, alignment empty | NO_S2_IDENTITY_ALIGNMENT |
| 8 | catalog_source_kind | from forecast only |
| 9 | empty result | no live S2 / no versioned alignment facts claim |

## 5. Registry flip manifest

~~~text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=false → true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false (companion; not flipped)
~~~

## 6. Status

~~~text
THIS_DRAFT_IS_NOT_READY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
AWAITING_COORDINATOR_REVIEW=true
~~~
