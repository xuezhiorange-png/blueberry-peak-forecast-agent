# V0.3-S3-A2 Default catalog live-bindability and registry availability contract

## Artifact identity

~~~text
ARTIFACT_ID=V0_3_S3_A2_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT
ARTIFACT_VERSION=v0-3-s3-a2-default-catalog-live-bindability-and-registry-availability-contract-v1
TASK_ID=DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_AND_REGISTRY_AVAILABLE_TRANSITION_ONLY
SLICE=V0.3-S3
ENGLISH_ID=DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY
USER_GATE=CONTRACT_AUTHORING_ONLY
CONTRACT_AUTHORING_AUTHORIZED=true
REVIEWER_ROLE=COORDINATOR
BASE_REF=origin/main
BASE_MAIN_SHA=f5809d30e08be6214852143784b7577d1b0bbcc5
BASE_MAIN_TREE_SHA=6415af5372bf8af4d1575f5a6f24283418871efb
PARENT_HANDOFF_R1_PR=527
PARENT_HANDOFF_R1_MERGE=f5809d30e08be6214852143784b7577d1b0bbcc5
PARENT_HANDOFF_R1_EVIDENCE_JSON_SHA256=2dd029a946817e0272a2dc352a4181ad9d0cc64a6d96f5ffad3326450b03b94c
CONTRACT_PATH=docs/v0-3/s3/s3-default-catalog-live-bindability-and-registry-availability-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.json
NO_STEP_IMPLIES_THE_NEXT=true
CONTRACT_ONLY=true
THIS_DRAFT_IS_NOT_READY=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
IMPLEMENTATION_AUTHORIZED=false
R1_AUTHORIZED=false
CLOSEOUT_AUTHORIZED=false
~~~

Handoff R1 #527 is on main. Bare catalog is `ARTIFACT_PRODUCED` with catalog
`00f6bc53…` / 2427 entries and `in_memory_structural_acceptance=true`. Binding
and bindable-repository classifiers remain `NOT_BINDABLE`;
`NO_BINDABLE_CATALOG_IN_REPOSITORY=true`;
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false`. This contract freeze defines the
authority boundary for future live-bindability and registry AVAILABLE transition
without implementing it.

~~~text
LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT_AUTHORIZED=true
LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED=false
REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false
CONTRACT_AUTHORED_ONLY=true
UNIQUE_GAP_SCOPE=DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_AND_REGISTRY_AVAILABLE_TRANSITION_ONLY
UNIQUE_REMAINING_GAP=_no_coordinator_reviewed_authority_to_promote_the_already_produced_structurally_accepted_default_catalog_into_a_live_bindable_catalog_and_available_evaluation_instance_registry
UNIQUE_REMAINING_GAP_CLOSED=false
CURRENT_FIRST_BLOCKER=NO_AUTHORIZED_LIVE_BINDABLE_CATALOG_AND_NO_AVAILABLE_REGISTRY_CLOSEOUT
DO_NOT_DUPLICATE_OLD_FAMILY=true
~~~

## 1. Coordinator summary

1. Catalog **production** (`ARTIFACT_PRODUCED`) is landed via handoff R1.
2. **Structural acceptance** (`in_memory_structural_acceptance=true`) is landed
   in frozen binding but is not live-bindable classification.
3. **Live-bindable authority** is missing: no versioned
   `DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_PACKAGE`.
4. **Registry AVAILABLE closeout** is missing: no coordinator-reviewed closeout
   package and `frozen_binding_classifies_live_bindable=false`.
5. **Completeness PASS** remains a separate blocked family (weather/plans).

## 2. Contract decisions

- Future success binding tokens: `LIVE_BINDABLE` / `LIVE_BINDABLE_CATALOG`.
- Future bound registry status:
  `BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`.
- Repository presence: authority package referring to pinned catalog identity,
  not a new versioned catalog artifact.
- `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY` stays independent.

## 3. Evidence digest

~~~text
EVIDENCE_JSON_SHA256=b7d0df409e0094594bf817f5fd048a2764defeb539a1679082643eed51c14bfc
~~~
