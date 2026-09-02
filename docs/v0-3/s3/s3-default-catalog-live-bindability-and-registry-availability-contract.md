# V0.3-S3-A2 Default catalog live-bindability and registry availability contract

## Contract identity and phase boundary

~~~text
CONTRACT_ID=V0_3_S3_A2_DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT
CONTRACT_VERSION=v0-3-s3-a2-default-catalog-live-bindability-and-registry-availability-contract-v1
TASK_ID=DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT
TASK_CLASS=CONTRACT_DEFINITION_ONLY
AUTHORIZATION_SCOPE=DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_AND_REGISTRY_AVAILABLE_TRANSITION_ONLY
SLICE=V0.3-S3
ENGLISH_ID=DEFAULT_CATALOG_LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY
USER_GATE=可以
INTERPRETED_GATE=CONTRACT_AUTHORING_ONLY
CONTRACT_AUTHORING_AUTHORIZED=true
USER_GATE_AUDIT_CORRECTED=true
CONTRACT_ONLY=true
BASE_MAIN_SHA=f5809d30e08be6214852143784b7577d1b0bbcc5
BASE_MAIN_TREE_SHA=6415af5372bf8af4d1575f5a6f24283418871efb
BASE_REF=origin/main
PARENT_HANDOFF_R1_PR=527
PARENT_HANDOFF_R1_MERGE=f5809d30e08be6214852143784b7577d1b0bbcc5
PARENT_HANDOFF_R1_EVIDENCE_JSON_SHA256=2dd029a946817e0272a2dc352a4181ad9d0cc64a6d96f5ffad3326450b03b94c
PARENT_HANDOFF_CONTRACT_PATH=docs/v0-3/s3/s3-default-catalog-forecast-port-envelope-handoff-contract.md
PARENT_BINDABLE_REPOSITORY_CONTRACT_PATH=docs/v0-3/s3/s3-default-catalog-bindable-repository-contract.md
PARENT_REGISTRY_AVAILABLE_CLOSEOUT_CONTRACT_PATH=docs/v0-3/s3/s3-evaluation-instance-registry-available-closeout-contract.md
REVIEWER_ROLE=COORDINATOR
NO_STEP_IMPLIES_THE_NEXT=true
THIS_PR_IS_NOT_A_GRANT=true
THIS_PR_IS_NOT_R1=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
GRANT_REQUIRES_SEPARATE_USER_GATE_授权=true
~~~

~~~text
LIVE_BINDABILITY_AND_REGISTRY_AVAILABILITY_CONTRACT_AUTHORIZED=true
LIVE_BINDABILITY_IMPLEMENTATION_AUTHORIZED=false
REGISTRY_AVAILABILITY_IMPLEMENTATION_AUTHORIZED=false
CONTRACT_AUTHORED_ONLY=true
DETERMINISTIC_DEFAULT_CATALOG_FORECAST_PORT_ENVELOPE_HANDOFF_IMPLEMENTED=true
DETERMINISTIC_DEFAULT_CATALOG_BINDABLE_REPOSITORY_IMPLEMENTED=true
DETERMINISTIC_EVALUATION_INSTANCE_REGISTRY_AVAILABLE_CLOSEOUT_IMPLEMENTED=true
BARE_DEFAULT_CATALOG_REASON=ARTIFACT_PRODUCED
CATALOG_PRODUCED=true
IN_MEMORY_STRUCTURAL_ACCEPTANCE=true
FROZEN_BINDING_CLASSIFICATION=NOT_BINDABLE
FROZEN_BINDING_REASON_CODE=NOT_BINDABLE
FROZEN_BINDING_IN_MEMORY_STRUCTURAL_ACCEPTANCE=true
FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false
BINDING_CLASSIFICATION=NOT_BINDABLE
BINDING_REASON_CODE=NOT_BINDABLE
DEFAULT_CATALOG_BINDABLE_REPOSITORY_REASON_CODE=NOT_BINDABLE
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
REGISTRY_SOURCE_STATUS=NOT_MATERIALIZED_OR_NOT_BOUND
COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS=false
FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false
AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
S3_A2_COMPLETENESS_PASS_AUTHORIZED=false
CURRENT_V0_3_S3_COMPLETE=false
V0_3_S4_AUTHORIZED=false
TEST_REMAINS_SEALED=true
WEATHER_UNAVAILABLE=true
PLANS_UNAVAILABLE=true
WEATHER_AND_PLANS_DEFERRED_TO_NEXT_VERSION=true
WEATHER_AND_PLANS_BLOCK_COMPLETENESS_PASS=true
CURRENT_P50_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P80_SEMANTICS_STATUS=VERIFICATION_FAILED
CURRENT_P90_SEMANTICS_STATUS=VERIFICATION_FAILED
S3_B_COVERAGE_EXECUTION_AUTHORIZED=false
FORBIDDEN_INVENT_TONNES=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
CLOSEOUT_AUTHORIZED=false
~~~

Handoff R1 merge #527 is on main. Bare default catalog production is
`ARTIFACT_PRODUCED` with content identity `06f45beb…` (three rows) and catalog
identity `00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af`
(2427 entries). Frozen binding records `in_memory_structural_acceptance=true`
while `binding_classification=NOT_BINDABLE`. Landed bindable-repository and
AVAILABLE-closeout classifiers intentionally preserve
`no_bindable_catalog_in_repository=true` and
`evaluation_instance_registry_available=false`.

This contract freezes the **narrow authority boundary** for a future legally
authorized transition from produced + structurally accepted catalog toward
`LIVE_BINDABLE_CATALOG=true` and `EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`.
It is **not** an implementation grant, **not** R1, **not** completeness PASS,
**not** a rename of `NOT_BINDABLE` without authority, and **not** a duplicate of
the landed `DEFAULT_CATALOG_BINDABLE_REPOSITORY` implementation family.

~~~text
UNIQUE_GAP_SCOPE=DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_AND_REGISTRY_AVAILABLE_TRANSITION_ONLY
UNIQUE_REMAINING_GAP=_no_coordinator_reviewed_authority_to_promote_the_already_produced_structurally_accepted_default_catalog_into_a_live_bindable_catalog_and_available_evaluation_instance_registry
UNIQUE_REMAINING_GAP_CLOSED=false
CURRENT_FIRST_BLOCKER=NO_AUTHORIZED_LIVE_BINDABLE_CATALOG_AND_NO_AVAILABLE_REGISTRY_CLOSEOUT
OLD_BINDABLE_REPOSITORY_FAMILY_IS_NOT_THE_NEW_IMPLEMENTATION_TARGET=true
OLD_BINDABLE_REPOSITORY_FAMILY_REMAINS_FROZEN=true
OLD_AVAILABLE_CLOSEOUT_FAMILY_REMAINS_HISTORICAL_INPUT=true
DO_NOT_DUPLICATE_OLD_FAMILY=true
CANONICAL_LIVE_BINDABILITY_AUTHORITY_PATH=SEPARATE_DETERMINISTIC_AUTHORITY_CLASSIFIER
CANONICAL_OPTION=SEPARATE_AUTHORITY_CLASSIFIER
BINDING_PY_REMAINS_FROZEN=true
REGISTRY_CORE_REMAINS_FROZEN_AT_CONTRACT_STAGE=true
DIRECT_BINDING_PY_LIVE_BINDABLE_EXTENSION_IS_NOT_CANONICAL=true
FROZEN_BINDING_MUST_NOT_BE_RENAMED_LIVE_BINDABLE=true
AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION_REQUIRED=true
FUTURE_AUTHORITY_CLASSIFICATION_SUCCESS=LIVE_BINDABLE
FUTURE_AUTHORITY_REASON_CODE_SUCCESS=LIVE_BINDABLE_CATALOG
FUTURE_REGISTRY_SOURCE_STATUS=BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_BINDABILITY=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REGISTRY_AVAILABILITY=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE=true
CONTRACT_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
CONTRACT_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_CATALOG_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_BINDING=true
CONTRACT_MERGE_DOES_NOT_REWRITE_FROZEN_REGISTRY=true
CONTRACT_MERGE_DOES_NOT_REWRITE_BINDABLE_REPOSITORY_CLASSIFIER=true
CONTRACT_MERGE_DOES_NOT_REWRITE_AVAILABLE_CLOSEOUT_CLASSIFIER=true
CONTRACT_MERGE_DOES_NOT_REWRITE_HANDOFF_MODULE=true
FORBIDDEN_RENAME_NOT_BINDABLE_TO_BINDABLE_WITHOUT_AUTHORITY=true
FORBIDDEN_FLIP_AVAILABLE_BY_BOOLEAN_ONLY=true
FORBIDDEN_TREAT_IN_MEMORY_CATALOG_AS_REPOSITORY_PERSISTENCE=true
FORBIDDEN_INVENT_VERSIONED_ARTIFACT=true
FORBIDDEN_INVENT_REGISTRY_IDENTITY=true
FORBIDDEN_USE_H7_FIXTURE_HASH=true
FORBIDDEN_USE_TEST_PARTITION=true
FORBIDDEN_SOURCE_002_REVIEW_MEMBER_REDERIVATION=true
FORBIDDEN_HARVEST_DATE_AS_FORECAST_CUTOFF=true
FORBIDDEN_GLOBAL_STATE_INSTALL=true
FORBIDDEN_COMPLETENESS_PASS=true
FORBIDDEN_QUANTILE_MODEL_CHANGE=true
FORBIDDEN_BACKTEST_EXECUTION=true
FORBIDDEN_METRIC_EXECUTION=true
FORBIDDEN_ERROR_ATTRIBUTION_EXECUTION=true
FORBIDDEN_V0_3_S4=true
~~~

## 1. Terminology — not synonyms

The following states must remain distinct in all future implementation and
review:

| State | Current live value | Meaning |
| --- | --- | --- |
| Catalog production | `BARE_DEFAULT_CATALOG_REASON=ARTIFACT_PRODUCED` | Deterministic in-memory catalog artifact produced via handoff-enabled bare default path |
| In-memory structural binding acceptance | `IN_MEMORY_STRUCTURAL_ACCEPTANCE=true` | Frozen `EvaluationInstanceCatalogBindingService` passes all five structural requirements for live `V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` catalog |
| Live-bindable authority | **missing** | Explicit versioned coordinator-reviewed authority to classify catalog as live-bindable and flip repository bindability |
| Registry AVAILABLE closeout | `COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS=false` | Coordinator-reviewed evidence that AVAILABLE preconditions are met |
| S3 daily-rowset completeness PASS | `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false` | Separate curve/weather/plan gated family; not implied by catalog production or structural acceptance |

~~~text
CATALOG_PRODUCTION_IS_NOT_STRUCTURAL_ACCEPTANCE=true
STRUCTURAL_ACCEPTANCE_IS_NOT_LIVE_BINDABLE_AUTHORITY=true
LIVE_BINDABLE_AUTHORITY_IS_NOT_REGISTRY_AVAILABLE_CLOSEOUT=true
REGISTRY_AVAILABLE_CLOSEOUT_IS_NOT_COMPLETENESS_PASS=true
IN_MEMORY_CATALOG_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT=true
~~~

## 2. Inherited landed facts (not reopened)

~~~text
CONTENT_IDENTITY_SHA256=06f45beb0c42be0ecf2750dede6783ca5f9a1e363d85ef3e26b0faccf14353f5
CONTENT_ROW_COUNT=3
CATALOG_IDENTITY_SHA256=00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af
CATALOG_ENTRY_COUNT=2427
REVIEWED_GRAIN_IDENTITY_SET_IDENTITY_SHA256=76b97d1feee4ad388200dc6d774b50afaefa5137e41a367b2e6c65b685f5bdb3
DECLARED_CATALOG_SOURCE_KIND=V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
ACTUALS_AUTHORITY=V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
FORECASTS_AUTHORITY=V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
HARVEST_BUSINESS_DATE_IS_NOT_FORECAST_CUTOFF=true
DEFAULT_GLOBAL_REVIEWED_SET_LOADER_REMAINS_EMPTY=true
DEFAULT_SESSION_PROVIDER_LEFT_UNSET=true
CATALOG_ARTIFACT_PY_BLOB=8196cb7dca33df8708f78789bd2eb9e8243b8354
FORECAST_ARTIFACT_PY_BLOB=49938d7107728987439a0a751a1273b73e0022e7
BINDING_PY_BLOB=0a335f682a923bcd73908b58cd70cd49c9ab0117
REGISTRY_PY_BLOB=ca16d518ab18136059cd08bcf4b247774d750bb5
BINDABLE_REPOSITORY_PY_BLOB=98948a405e4865a573f1b2332d128af3aaaccfd3
AVAILABLE_CLOSEOUT_PY_BLOB=cafca50d5c4ff4e416747644f7446a7ea24caee9
HANDOFF_PY_BLOB=a057802f598aada08e26aed35fb4ad76b4f8c4ce
~~~

Frozen `EvaluationInstanceCatalogBindingService.validate()` on live catalog with
all structural requirements PASS still returns
`BindingClassification.NOT_BINDABLE` with
`BindingReasonCode.NOT_BINDABLE` and
`in_memory_structural_acceptance=true`. Frozen
`EvaluationInstanceRegistryService._registry_source_status()` always returns
`NOT_MATERIALIZED_OR_NOT_BOUND` even when the catalog has 2427 entries.
`DefaultCatalogBindableRepositoryClassifier` maps `ARTIFACT_PRODUCED` to
`BindableRepositoryReasonCode.NOT_BINDABLE` and preserves
`no_bindable_catalog_in_repository=true`.
`EvaluationInstanceRegistryAvailableCloseoutClassifier` records
`AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET` with
`frozen_binding_classifies_live_bindable=false`.

## 3. A. Live-bindable authority gap

After catalog identity `00f6bc53…`, entry count 2427, and
`in_memory_structural_acceptance=true`, frozen binding still returns
`NOT_BINDABLE` with `FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false`. The
missing element is **explicit versioned live-bindable authority** on a **new
authority layer**, not additional catalog bytes and not a rename inside frozen
`binding.py`.

~~~text
CANONICAL_LIVE_BINDABILITY_AUTHORITY_PATH=SEPARATE_DETERMINISTIC_AUTHORITY_CLASSIFIER
CANONICAL_OPTION=SEPARATE_AUTHORITY_CLASSIFIER
BINDING_PY_REMAINS_FROZEN=true
REGISTRY_CORE_REMAINS_FROZEN_AT_CONTRACT_STAGE=true
DIRECT_BINDING_PY_LIVE_BINDABLE_EXTENSION_IS_NOT_CANONICAL=true
FROZEN_BINDING_MUST_NOT_BE_RENAMED_LIVE_BINDABLE=true
FORBIDDEN_RENAME_NOT_BINDABLE_TO_BINDABLE_WITHOUT_AUTHORITY=true
LIVE_BINDABLE_CLASSIFICATION_REQUIRES_AUTHORITY_PACKAGE=true
AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION_REQUIRED=true
FUTURE_AUTHORITY_CLASSIFICATION_SUCCESS=LIVE_BINDABLE
FUTURE_AUTHORITY_REASON_CODE_SUCCESS=LIVE_BINDABLE_CATALOG
~~~

### 3.1 Canonical future authority module (not created in this Contract PR)

A future separately authorized R1 may create:

~~~text
FUTURE_AUTHORITY_MODULE=backend/app/s3_daily_rowset/s3_a2_default_catalog_live_bindability_and_registry_availability.py
FUTURE_AUTHORITY_CLASSIFIER=DefaultCatalogLiveBindabilityAndRegistryAvailabilityClassifier
~~~

The authority classifier must consume **only**:

1. the already-landed bare-default catalog production result;
2. the already-landed frozen binding result (`classification=NOT_BINDABLE`,
   `reason=NOT_BINDABLE`, `in_memory_structural_acceptance=true`);
3. a versioned coordinator-reviewed
   `DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_PACKAGE`;
4. when evaluating registry AVAILABLE, a versioned coordinator-reviewed
   `DEFAULT_CATALOG_REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE`.

It must not fabricate new catalog rows, forecast rows, alignment rows, or
registry identity. Extending frozen `EvaluationInstanceCatalogBindingService`
to emit `LIVE_BINDABLE` (Option A / direct `binding.py` extension) is
**explicitly non-canonical** for this family.

### 3.2 Legal transition condition (future implementation)

A future grant (user 「授权」) plus R1 (user 「可以实施」) may flip live-bindability
only when **all** hold:

1. Bare-default catalog reason remains `ARTIFACT_PRODUCED`.
2. Catalog identity is exactly
   `00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af`.
3. Catalog entry count is exactly 2427.
4. Frozen binding result remains
   `classification=NOT_BINDABLE`, `reason=NOT_BINDABLE`,
   `in_memory_structural_acceptance=true`,
   `FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false`.
5. Versioned `DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_PACKAGE` exists,
   validates, pins the same catalog identity, and records coordinator review.
6. The **authority classifier** (not frozen binding) returns
   `AUTHORITY_CLASSIFICATION=LIVE_BINDABLE` with
   `AUTHORITY_REASON_CODE=LIVE_BINDABLE_CATALOG`.

Structural acceptance is an input precondition. It is **not** itself
live-bindability. Frozen binding must not flip to live-bindable while
`binding.py` remains frozen.

### 3.3 Authority package minimum semantics

`DEFAULT_CATALOG_LIVE_BINDABLE_AUTHORITY_PACKAGE` must pin at minimum:

~~~text
artifact_or_package_version
catalog_identity_sha256
catalog_entry_count
dataset_identity
actuals_authority
forecasts_authority
catalog_source_kind
reviewer_role
authority_evidence_digest_sha256
train_and_validation_only_rule
test_sealed_rule
harvest_date_not_forecast_cutoff_rule
~~~

This Contract PR does not invent future package bytes. No fake implementation
package may be created solely to satisfy fence tests.

## 4. B. Registry source status transition

Current frozen behavior must not be silently rewritten. Today:

~~~text
REGISTRY_SOURCE_STATUS_UNBOUND=NOT_MATERIALIZED_OR_NOT_BOUND
CatalogSourceKind.UNBOUND=NOT_MATERIALIZED_OR_NOT_BOUND
~~~

Future legal bound status token introduced by this contract:

~~~text
REGISTRY_SOURCE_STATUS_BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF=BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
~~~

Semantics (authority layer only): `AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION=true`;
catalog identity is non-null and pinned; registry snapshot identity equals
catalog identity; in-scope cells are non-empty; TRAIN/VALIDATION only; TEST
sealed; actuals and forecasts authorities remain pinned. Current frozen
`registry.py` does **not** emit this token today.

Transition rule:

~~~text
REGISTRY_SOURCE_STATUS:
  NOT_MATERIALIZED_OR_NOT_BOUND
  → BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
FUTURE_REGISTRY_SOURCE_STATUS=BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF
~~~

Only after authority-layer live-bindable classification is proven (§3). Flipping
`evaluation_instance_registry_available` or `no_bindable_catalog_in_repository`
without this bound status transition is forbidden.

## 5. C. AVAILABLE closeout evidence

`COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS=true` requires **all**:

1. Versioned `DEFAULT_CATALOG_REGISTRY_AVAILABLE_CLOSEOUT_PACKAGE` exists and
   validates.
2. `AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION=true` on the **authority layer** —
   not `FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=true`. Frozen binding remains
   `NOT_BINDABLE` while `binding.py` is frozen.
3. `AUTHORITY_CLASSIFICATION=LIVE_BINDABLE` and
   `AUTHORITY_REASON_CODE=LIVE_BINDABLE_CATALOG`.
4. `no_bindable_catalog_in_repository=false` after versioned live-bindable
   authority package validates and authority classifier returns `LIVE_BINDABLE`.
5. `registry_source_status=BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF`.
6. `registry_snapshot_identity_matches_bound_catalog_identity=true`.
7. Catalog identity remains
   `00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af`; entry
   count remains 2427.
8. All repository authority evidence validates.

Then and only then may a future authorized implementation produce
`COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS=true` and
`EVALUATION_INSTANCE_REGISTRY_AVAILABLE=true`.

~~~text
FORBIDDEN_FUTURE_PREDICATE=FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=true
REQUIRED_FUTURE_PREDICATE=AUTHORIZED_LIVE_BINDABLE_CLASSIFICATION=true
~~~

Historical landed classifier truth is unchanged:
`FROZEN_BINDING_CLASSIFIES_LIVE_BINDABLE=false`,
`COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS=false`,
`AVAILABLE_CLOSEOUT_PRECONDITIONS_NOT_MET=true`. The future authority family
supersedes the missing live-bindable authority predicate; it does not claim the
old frozen classifier historically returned `LIVE_BINDABLE`.

## 6. D. Repository presence decision

~~~text
IN_MEMORY_CATALOG_ARTIFACT_PRODUCED_IS_NOT_VERSIONED_REPOSITORY_ARTIFACT=true
LIVE_BINDABILITY_REQUIRES_VERSIONED_CATALOG_ARTIFACT_IN_REPOSITORY=false
LIVE_BINDABILITY_REQUIRES_VERSIONED_BINDING_AUTHORITY_PACKAGE=true
BINDABLE_CATALOG_REPOSITORY_PRESENCE_MAY_BE_SATISFIED_BY_VERSIONED_BINDING_AUTHORITY_PACKAGE_REFERENCING_PINNED_CATALOG=true
DUPLICATE_SERIALIZED_CATALOG_ARTIFACT_NOT_REQUIRED=true
~~~

Future live-bindability does **not** require persisting a duplicate versioned
catalog artifact in the repository. It requires a **separately versioned
binding/registry authority package** that refers to the already deterministic
catalog identity `00f6bc53…`. `NO_BINDABLE_CATALOG_IN_REPOSITORY=true→false`
may occur only after the versioned live-bindable authority package exists,
validates, and the authority classifier returns `LIVE_BINDABLE`. That flip
must not mean the in-memory catalog was silently reclassified as a persisted
catalog artifact. Producing or inventing a new versioned catalog artifact file
solely to flip bindability is forbidden.

## 7. E. Forecast repository presence independence

~~~text
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
FORECAST_HANDOFF_IMPLEMENTED=true
NO_VERSIONED_IS_INDEPENDENT_COMPANION_STATE=true
NO_VERSIONED_IS_NOT_LIVE_BINDABILITY_PREREQUISITE=true
~~~

Handoff R1 proves bare default catalog production without a versioned incumbent
forecast artifact in the repository. Live-bindability must not couple to flipping
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY`. Successful forecast
handoff does not imply versioned forecast repository presence and does not
imply live-bindability.

## 8. Future state transitions (defined only — not executed in this PR)

| Field | Current | Future legal value | Gate |
| --- | --- | --- | --- |
| `NO_BINDABLE_CATALOG_IN_REPOSITORY` | `true` | `false` | Versioned authority package + authority classifier `LIVE_BINDABLE` |
| `EVALUATION_INSTANCE_REGISTRY_AVAILABLE` | `false` | `true` | All AVAILABLE-closeout preconditions (§5) |
| `REGISTRY_SOURCE_STATUS` | `NOT_MATERIALIZED_OR_NOT_BOUND` | `BOUND_V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` | Authority-layer live-bindable classification proven |
| `COORDINATOR_REVIEWED_AVAILABLE_CLOSEOUT_EXISTS` | `false` | `true` | Coordinator-reviewed closeout package + §5 |
| `CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED` | `false` | unchanged by this family | Separate completeness PASS authorization |
| `S3_A2_COMPLETENESS_PASS_AUTHORIZED` | `false` | unchanged by this family | Separate user gate |

This contract PR keeps all current live values in the left column.

## 9. Acceptance criteria for future implementation

~~~text
ACCEPTANCE_1=bare_default_catalog_production_remains_ARTIFACT_PRODUCED
ACCEPTANCE_2=catalog_identity_remains_00f6bc532dfd97f2d625fc1347bf2a7663299fda206bd472df4c2c32c54ab5af
ACCEPTANCE_3=catalog_entry_count_remains_2427
ACCEPTANCE_4=in_memory_structural_acceptance_remains_true
ACCEPTANCE_5=live_bindable_authority_is_explicit_and_versioned
ACCEPTANCE_6=authority_classification_has_a_legally_defined_live_bindable_success_state
ACCEPTANCE_7=authority_reason_code_has_a_legally_defined_success_semantics
ACCEPTANCE_8=no_bindable_catalog_in_repository_can_flip_only_after_the_required_authority_exists
ACCEPTANCE_9=registry_source_status_changes_only_after_live_binding_authority_is_proven
ACCEPTANCE_10=evaluation_instance_registry_available_can_flip_to_true_only_after_all_registry_available_closeout_preconditions_pass
ACCEPTANCE_11=registry_snapshot_identity_matches_the_bound_catalog_identity
ACCEPTANCE_12=actuals_authority_remains_V0_3_S2_SOURCE_002_E5_LIVE_V1_TRAIN_AND_VALIDATION
ACCEPTANCE_13=forecasts_authority_remains_V0_2_CURRENT_INCUMBENT_MODEL_AT_HISTORICAL_CUTOFF
ACCEPTANCE_14=TRAIN_and_VALIDATION_only_TEST_remains_sealed
ACCEPTANCE_15=no_forbidden_catalog_source_kind_is_accepted
ACCEPTANCE_16=harvest_business_date_is_not_used_as_forecast_cutoff
ACCEPTANCE_17=no_global_reviewed_set_loader_is_installed
ACCEPTANCE_18=no_default_session_provider_is_left_installed
ACCEPTANCE_19=no_tonnes_weather_or_plans_are_invented
ACCEPTANCE_20=current_s3_daily_rowset_completeness_verified_remains_false
ACCEPTANCE_21=s3_a2_completeness_pass_authorized_remains_false
~~~

## 10. Frozen production modules (contract merge must not touch)

~~~text
backend/app/s3_daily_rowset/forecast_artifact.py
backend/app/s3_daily_rowset/s3_a2_default_catalog_forecast_port_envelope_handoff.py
backend/app/s3_daily_rowset/catalog_artifact.py
backend/app/s3_daily_rowset/accepted_s2_identity_alignment_evidence.py
backend/app/s3_daily_rowset/s3_a2_default_catalog_bindable_repository.py
backend/app/s3_daily_rowset/s3_a2_evaluation_instance_registry_available_closeout.py
backend/app/s3_daily_rowset/binding.py
backend/app/s3_daily_rowset/registry.py
~~~

## 11. Contract package paths

~~~text
CONTRACT_PATH=docs/v0-3/s3/s3-default-catalog-live-bindability-and-registry-availability-contract.md
WORKPAPER_PATH=docs/v0-3/s3/workpapers/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.md
EVIDENCE_JSON_PATH=docs/v0-3/s3/evidence/s3-a2-default-catalog-live-bindability-and-registry-availability-contract.json
NEXT_GATE=CONTRACT_REVIEW
STOP_AFTER_CONTRACT_AUTHORING=true
~~~
