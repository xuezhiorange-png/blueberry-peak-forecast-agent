# V0.3-S1 Immutable Daily Final Label Contract Amendment Candidate

## 1. Candidate identity and authority boundary

```text
CANDIDATE_ID=V0_3_S1_IMMUTABLE_DAILY_FINAL_LABEL_CONTRACT_AMENDMENT_CANDIDATE
BASELINE_MAIN_SHA=9a69a0a6e38ab36ddf48e7911d703519be6b8fdb
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
CANDIDATE_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
CANDIDATE_LABEL_MODE_VERSION=IDFL_V1_CANDIDATE
DOCUMENT_STATUS=CONTRACT_AMENDMENT_CANDIDATE_FOR_INDEPENDENT_REVIEW
DECISION_STATUS=NOT_ACCEPTED
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=false
```

This document prepares a versioned third label mode for independent review. It does not amend any accepted contract by itself. The current governing documents remain authoritative until a later, separately authorized cross-contract acceptance package changes them:

- `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`;
- `docs/v0-3/s1/visibility-inclusion-revision-contract.md`;
- `docs/v0-3/s1/source-authority-and-cohort-manifest.md`.

This candidate is derived from the merged compatibility preparation:

- `docs/v0-3/s1/workpapers/actual-harvest-immutable-daily-label-compatibility-decision.md`.

```text
EXISTING_AS_OF_EVALUATION_SEMANTICS_CHANGED=false
EXISTING_FINAL_ADJUDICATED_SEMANTICS_CHANGED=false
ACCEPTED_I7_CHANGED_THIS_TASK=false
VISIBILITY_CONTRACT_CHANGED_THIS_TASK=false
SOURCE_AUTHORITY_CONTRACT_CHANGED_THIS_TASK=false
BACKTEST_AUTHORIZED=false
V0_3_S2_AUTHORIZED=false
REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
```

## 2. Problem statement

The current governed actual-harvest representation is an immutable daily business aggregate rather than a revisioned, point-in-time replayable event source.

Confirmed source-representation facts are:

```text
SOURCE_MODEL=IMMUTABLE_DAILY_BUSINESS_AGGREGATE
SOURCE_TIME_BASIS=DAILY_STATISTICS_ONLY
SOURCE_RECORD_IDENTITY=CONFIRMED_ABSENT
SOURCE_RECORDED_AT_IN_CURRENT_GOVERNED_SOURCE_REPRESENTATION=NOT_PRESENT
CURRENT_GOVERNED_SOURCE_REPRESENTATION_EXPOSES_SOURCE_RECORDED_AT=false
EXTERNAL_SCAN_WEIGH_SYSTEM_SOURCE_RECORDED_AT_CAPABILITY_STATUS=UNKNOWN_NOT_ESTABLISHED
SOURCE_AVAILABLE_AT=CONFIRMED_ABSENT
POST_CONFIRMATION_MODIFICATION_RULE=NO_MODIFICATION
CORRECTION_SCENARIO=NOT_APPLICABLE
REVISION_LINEAGE=NOT_PRESENT
VOID_OR_CANCELLATION_SCENARIO=NOT_APPLICABLE
SOURCE_CLASS_HAS_INDEPENDENT_FINALIZATION_EVENT=false
FINALIZED_AT=NOT_PRESENT
LATE_ENTRY_SCENARIO=NOT_APPLICABLE
EXPORT_LIFECYCLE_FIELDS_SUPPORTED=false
```

Therefore the source does not satisfy the current accepted `AS_OF_EVALUATION` or `FINAL_ADJUDICATED` label modes.

```text
CURRENT_I7_AS_OF_COMPATIBILITY=false
ACTUAL_LABEL_AS_OF_EVALUATION_ELIGIBILITY=BLOCKED
ACTUAL_LABEL_FINAL_ADJUDICATED_SUPPORTED_BY_SOURCE_CLASS=false
ACTUAL_LABEL_FINAL_ADJUDICATED_ELIGIBILITY=BLOCKED
```

The candidate must solve that representation mismatch without manufacturing source lifecycle facts.

## 3. Non-negotiable epistemic rules

```text
SOURCE_FACT_ABSENCE_PRESERVED=true
NO_SYNTHETIC_LIFECYCLE_AUTHORITY=true
```

The candidate must never infer or synthesize:

```text
CANONICAL_GRAIN_HASH_AS_SOURCE_RECORD_ID=false
ROW_HASH_AS_SOURCE_RECORD_ID=false
HARVEST_BUSINESS_DATE_AS_SOURCE_RECORDED_AT=false
EXPORT_TIME_AS_SOURCE_RECORDED_AT=false
IMPORT_TIME_AS_SOURCE_RECORDED_AT=false
DATABASE_COMMIT_TIME_AS_SOURCE_RECORDED_AT=false
SNAPSHOT_EXECUTED_AT_AS_LABEL_VISIBILITY_TIME=false
BUSINESS_IMMUTABILITY_AS_REVISION_HISTORY=false
SCAN_COMPLETION_AS_FINALIZED_AT=false
```

The following distinctions remain binding:

```text
DAILY_STATISTICS_ONLY != SOURCE_SYSTEM_HAS_NO_SOURCE_RECORDED_AT
CURRENT_GOVERNED_REPRESENTATION_DOES_NOT_EXPOSE_SOURCE_RECORDED_AT != EXTERNAL_SOURCE_SYSTEM_CONFIRMED_ABSENT
NO_BUSINESS_CORRECTION_SCENARIO != PROVEN_ADMINISTRATIVE_MUTATION_IMPOSSIBLE
FINAL_OBSERVED_LABEL != HISTORICAL_LABEL_REPLAY
```

## 4. Proposed third mode

The proposed mode is:

```text
LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
LABEL_MODE_VERSION=IDFL_V1_CANDIDATE
LABEL_VALUE_AUTHORITY=FINAL_OBSERVED_DAILY_BUSINESS_QUANTITY
LABEL_VISIBILITY_AUTHORITY=NOT_POINT_IN_TIME_REPLAYABLE
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
LABEL_OBSERVATION_CUTOFF_REQUIRED=false
REVISION_WINNER_REQUIRED=false
FINALIZED_AT_REQUIRED=false
SOURCE_RECORDED_AT_REQUIRED_FOR_LABEL_SIDE=false
STABLE_ROW_LEVEL_SOURCE_ID_REQUIRED=false
FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
```

This mode is a retrospective final-observed-label mode. It is not a historical label state reconstruction mode.

It must not be named, aliased, or reported as:

```text
AS_OF_EVALUATION
FINAL_ADJUDICATED
POINT_IN_TIME_LABEL_REPLAY
REVISION_WINNER_REPLAY
```

## 5. Applicability predicate

A source class may be considered for `IMMUTABLE_DAILY_FINAL_LABEL` only when an accepted source policy binds all of the following:

```text
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
DAILY_BUSINESS_AGGREGATE=true
FINAL_OBSERVED_BUSINESS_QUANTITY=true
POST_CONFIRMATION_VALUE_IMMUTABLE_BY_GOVERNED_BUSINESS_RULE=true
CORRECTION_WORKFLOW_NOT_APPLICABLE_BY_GOVERNED_POLICY=true
VOID_OR_CANCELLATION_WORKFLOW_NOT_APPLICABLE_BY_GOVERNED_POLICY=true
LATE_ENTRY_NOT_APPLICABLE_BY_GOVERNED_POLICY=true
HISTORICAL_LABEL_REPLAY_NOT_AVAILABLE=true
```

These policy bindings describe the governed representation. They must not be rewritten as claims about undocumented administrator, backend, or vendor capabilities.

If a later accepted source version introduces revisions, corrections, late entry, or historical lifecycle visibility, that source version requires a new compatibility decision. It must not silently inherit `IDFL_V1` eligibility.

## 6. Canonical label grain and quantity semantics

The candidate preserves the canonical actual-harvest grain:

```text
CANONICAL_LABEL_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

The candidate label quantity is the governed final observed daily business quantity at that grain.

For the current source representation, fruit-size is a source aggregation dimension and is aggregated before the canonical target grain.

```text
QUANTITY_UNIT=kg
QUANTITY_ARITHMETIC=EXACT_DECIMAL
SILENT_FLOAT_ROUNDING_ALLOWED=false
EXPLICIT_ZERO_PRESERVED=true
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
```

No-record-to-zero conversion remains forbidden unless a separate formal source-completeness rule is accepted.

```text
NO_RECORD_TO_ZERO_MAPPING_STATUS=BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
```

## 7. Required source-object and aggregate audit authority

Because the mode does not use stable row-level source identity or revision winners, it must bind immutable source-package authority at the object/snapshot and aggregate levels.

A future accepted `IDFL_V1` label snapshot must bind at least:

```text
source_system
source_dataset
source_version
schema_version
schema_hash
source_snapshot_reference
source_object_identity_hashes
source_owner_role
attestation_version
attestation_hash
coverage_scope
mapping_policy_version
visibility_policy_version
inclusion_policy_version
split_policy_version
custody_record_hash
label_mode_version
aggregate_policy_version
source_object_set_hash
canonical_label_row_set_hash
coverage_manifest_hash
exclusion_manifest_hash
label_snapshot_hash
```

Identity rules:

```text
HASH_ALGORITHM=SHA-256
CANONICALIZATION=VERSIONED_CANONICAL_JSON_WITH_DECIMAL_STRINGS
REAL_DATA_ALLOWED_IN_GIT=false
OPAQUE_NON_SENSITIVE_SOURCE_REFERENCE_REQUIRED=true
DATABASE_ID_AS_CANONICAL_IDENTITY=false
STORAGE_PATH_AS_CANONICAL_IDENTITY=false
PRIVATE_URL_AS_CANONICAL_IDENTITY=false
```

A source-object identity hash proves which immutable source package was evaluated. It does not become a source record ID and does not create revision lineage.

## 8. Aggregate construction order

The candidate processing order is distinct from I7 revision-first aggregation:

```text
governed immutable source object set
-> accepted source scope and inclusion policy
-> accepted season/date mapping
-> canonical identity mapping
-> source-dimension aggregation
-> canonical daily label grouping
-> exact Decimal SUM
-> deterministic coverage and exclusion manifest
-> immutable final-observed label snapshot
```

There is no revision terminal selection step.

```text
REVISION_WINNER_ALGORITHM=NOT_APPLICABLE
LATEST_ROW_FALLBACK_ALLOWED=false
LARGEST_REVISION_FALLBACK_ALLOWED=false
DATABASE_ROW_ORDER_AUTHORITY=false
```

If the source representation contains duplicate or conflicting records that cannot be deterministically explained by the accepted source policy, snapshot creation must fail closed. The candidate must not silently select a winner.

## 9. Business-date and coverage requirements

The label snapshot request must bind an explicit business-date scope and accepted season resolver.

```text
FARM_TIMEZONE=Asia/Shanghai
BUSINESS_DATE_REQUIRED=true
SEASON_RESOLVER_VERSION_REQUIRED=true
UNMAPPED_DATE_POLICY_REQUIRED=true
COVERAGE_SCOPE_REQUIRED=true
KNOWN_EXCLUSIONS_REQUIRED=true
```

Current known source evidence includes an unresolved July date outside the currently confirmed automatic season assignment. This candidate does not resolve that date.

```text
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
UNMAPPED_DATE_AUTO_ASSIGNMENT_ALLOWED=false
```

An accepted mode may exclude unresolved dates only through an explicit, versioned exclusion policy and manifest. Silent deletion or assignment is forbidden.

## 10. Forecast-side point-in-time boundary

The candidate changes label-side replay requirements only. It does not weaken forecast-input point-in-time authority.

```text
FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

Every forecast-input source class must continue to satisfy its accepted visibility rule, including where applicable:

```text
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

The evaluation ordering for this candidate is:

```text
FORECAST_CUTOFF_AT < HARVEST_BUSINESS_DATE
```

and all forecast features used by the evaluated forecast must be proven available at or before `FORECAST_CUTOFF_AT` under their own source-class contracts.

A final observed label cannot retroactively make a forecast input historically eligible.

## 11. Permitted and forbidden evaluation claims

Acceptance of the label mode alone must not authorize a backtest or a model-quality claim.

```text
LABEL_MODE_ACCEPTANCE_IMPLIES_BACKTEST_AUTHORIZATION=false
LABEL_MODE_ACCEPTANCE_IMPLIES_MODEL_QUALITY_CLAIM=false
```

If all downstream gates are separately accepted, `IDFL_V1` may be eligible to support a qualified retrospective evaluation claim:

```text
FUTURE_QUALIFIED_EVALUATION_CLAIM=
MODEL_ERROR_AGAINST_FINAL_OBSERVED_DAILY_HARVEST_QUANTITY_ON_GOVERNED_RETROSPECTIVE_COHORT

LABEL_MODE_CAN_SUPPORT_QUALIFIED_RETROSPECTIVE_MODEL_EVALUATION=true
```

Such a future claim must explicitly disclose:

```text
LABEL_SIDE_HISTORICAL_REPLAY_NOT_SUPPORTED=true
LABEL_SIDE_REVISION_REPLAY_NOT_SUPPORTED=true
LABEL_SIDE_SOURCE_RECORDED_AT_CUTOFF_NOT_USED=true
FORECAST_SIDE_POINT_IN_TIME_EVIDENCE_REQUIRED=true
COHORT_SCOPE_QUALIFICATION_REQUIRED=true
```

Forbidden claims include:

```text
HISTORICAL_LABEL_STATE_RECONSTRUCTED=false
AS_OF_LABEL_ACCURACY_CLAIM_ALLOWED=false
FINAL_ADJUDICATED_ACCURACY_CLAIM_ALLOWED=false
REVISION_WINNER_ACCURACY_CLAIM_ALLOWED=false
GLOBAL_MODEL_ACCURACY_FROM_NARROW_COHORT_ALLOWED=false
```

Current state remains:

```text
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

## 12. Required downstream gates before any model evaluation

Even after a future acceptance of `IDFL_V1`, model evaluation remains blocked until all applicable gates are separately accepted, including at least:

```text
SOURCE_AUTHORITY_ACCEPTED=true
SOURCE_COHORT_ACCEPTED=true
Q2C_ACCEPTED=true
FORMAL_MISSING_DAY_RULE_ACCEPTED=true
UNMAPPED_DATE_POLICY_ACCEPTED=true
INCLUSION_POLICY_ACCEPTED=true
CUSTODY_RECORD_ACCEPTED=true
SPLIT_POLICY_ACCEPTED=true
METRIC_CONTRACT_ACCEPTED=true
MINIMUM_COVERAGE_THRESHOLD_ACCEPTED=true
DATA_QUALITY_THRESHOLDS_ACCEPTED=true
HOLDOUT_FEASIBILITY_ACCEPTED_OR_FORMALLY_NOT_APPLICABLE=true
FORECAST_INPUT_VISIBILITY_ACCEPTED=true
INDEPENDENT_REVIEW_ACCEPTED=true
```

This candidate closes none of those gates by itself.

## 13. Proposed I7 contract delta

A future acceptance package would add a third label mode without changing the existing predicates for `AS_OF_EVALUATION` or `FINAL_ADJUDICATED`.

Proposed I7 delta:

```text
SUPPORTED_LABEL_MODES=
AS_OF_EVALUATION,
FINAL_ADJUDICATED,
IMMUTABLE_DAILY_FINAL_LABEL

AS_OF_EVALUATION_SEMANTICS_UNCHANGED=true
FINAL_ADJUDICATED_SEMANTICS_UNCHANGED=true
```

For `IMMUTABLE_DAILY_FINAL_LABEL` only:

```text
label_observation_cutoff_at=NULL_NOT_APPLICABLE
source_recorded_at_cutoff_predicate=NOT_APPLICABLE
revision_winner_selection=NOT_APPLICABLE
finalized_terminal_selection=NOT_APPLICABLE
source_object_snapshot_authority=REQUIRED
canonical_final_daily_aggregation=REQUIRED
coverage_and_exclusion_manifest=REQUIRED
```

The mode must use its own request identity and policy-version namespace so it cannot collide with an AS-OF or FINAL snapshot identity.

## 14. Proposed S1 visibility contract delta

The current visibility contract treats all actual labels as point-in-time label sources. A future acceptance package must change that from one universal label predicate to a mode-specific label authority matrix.

Proposed structure:

| label mode | label-side historical visibility | `SOURCE_RECORDED_AT` | `LABEL_OBSERVATION_CUTOFF_AT` | revision winner | finalization | forecast-side cutoff |
| --- | --- | --- | --- | --- | --- | --- |
| `AS_OF_EVALUATION` | required | required | required | required | status-specific | unchanged |
| `FINAL_ADJUDICATED` | final terminal authority | source/contract required | null under accepted final rules | required | required | unchanged |
| `IMMUTABLE_DAILY_FINAL_LABEL` | not replayable | not required for label side | not applicable | not applicable | not applicable | fully required |

This exception is label-mode-specific. It must not relax the point-in-time requirements of `AREA`, `YIELD_PLAN`, `PHENOLOGY`, `WEATHER_OBSERVATION`, `HISTORICAL_WEATHER_FORECAST`, `PICKER_COUNT`, `HARVEST_EFFICIENCY`, `MARKETABLE_RATE`, or any future forecast-input source class.

## 15. Proposed source-authority/cohort contract delta

The current source-authority contract assumes row-level revision identity and global point-in-time visibility. A future acceptance package must make those requirements source-model and label-mode aware without weakening source authority, custody, hashing, or coverage requirements.

For `IDFL_V1`, the accepted source authority would bind a no-revision aggregate policy identity such as:

```text
REVISION_POLICY_IDENTITY=IMMUTABLE_DAILY_AGGREGATE_NO_REVISION_V1
REVISION_POLICY_VERSION=IDFL_NO_REVISION_V1
ROW_LEVEL_REVISION_IDENTITY_REQUIRED=false
ROW_LEVEL_SUPERSEDED_PARENT_REQUIRED=false
ROW_LEVEL_SOURCE_RECORDED_AT_REQUIRED_FOR_LABEL_MODE=false
SOURCE_OBJECT_IMMUTABILITY_REQUIRED=true
SOURCE_OBJECT_IDENTITY_HASHES_REQUIRED=true
WITHDRAWAL_AND_VOID_POLICY_AT_SOURCE_OBJECT_LEVEL_REQUIRED=true
```

The global rule:

```text
POINT_IN_TIME_VISIBILITY_REQUIRED=true
```

would need to become mode-aware, for example:

```text
POINT_IN_TIME_VISIBILITY_REQUIREMENT_IS_SOURCE_CLASS_AND_MODE_SPECIFIC=true
FORECAST_INPUT_POINT_IN_TIME_VISIBILITY_REQUIRED=true
AS_OF_LABEL_POINT_IN_TIME_VISIBILITY_REQUIRED=true
IMMUTABLE_DAILY_FINAL_LABEL_POINT_IN_TIME_REPLAY_REQUIRED=false
```

This change must not permit a source object to be silently replaced, mutated, withdrawn, or reinterpreted in place.

## 16. Withdrawal and replacement behavior

`IDFL_V1` has no row-level void winner semantics, but source-package withdrawal remains governed.

```text
SOURCE_OBJECT_WITHDRAWAL_SUPPORTED_BY_GOVERNANCE=true
WITHDRAWN_SOURCE_OBJECT_CAN_BE_SILENTLY_DELETED=false
WITHDRAWN_SOURCE_OBJECT_CAN_BE_REWRITTEN_IN_PLACE=false
REPLACEMENT_SOURCE_REQUIRES_NEW_IDENTITY=true
REPLACEMENT_SOURCE_REQUIRES_NEW_HASHES=true
DOWNSTREAM_INVALIDATION_REQUIRED=true
```

A withdrawal or replacement must propagate to the cohort identity, any materialized S2 dataset, split manifest, label snapshot, evaluation run, and acceptance evidence according to versioned policy.

## 17. Determinism and snapshot identity candidate

A future accepted snapshot must be reproducible for the same canonical request and immutable source-object universe.

Required candidate identities include:

```text
label_mode_version
label_snapshot_request_identity_hash
source_object_set_hash
mapping_snapshot_hash
canonical_label_row_set_hash
coverage_manifest_hash
exclusion_manifest_hash
label_snapshot_hash
```

`snapshot_executed_at` may be persisted as audit metadata but must not be used to fabricate label visibility or alter deterministic canonical hashes unless a future accepted contract explicitly defines otherwise.

```text
SNAPSHOT_EXECUTED_AT_IS_LABEL_VISIBILITY_AUTHORITY=false
SAME_REQUEST_AND_SAME_SOURCE_OBJECT_UNIVERSE_REPRODUCES_SAME_HASHES=true
```

## 18. Acceptance-test candidate

A future implementation/acceptance package for this mode must test at least:

- exact canonical grain construction;
- fruit-size/source-dimension aggregation before canonical label grouping;
- exact Decimal summation;
- explicit zero versus missing day;
- rejection of implicit missing-to-zero conversion;
- deterministic handling of unresolved/unmapped business dates;
- single source-system/source-family enforcement;
- immutable source-object identity binding;
- source-object replacement produces a new identity and hashes;
- input-order independence;
- stable canonical label hashes for the same source-object universe;
- no row-level source ID fabrication;
- no `source_recorded_at` fabrication;
- no revision-winner execution in this mode;
- no `finalized_at` policy-null substitution for `FINAL_ADJUDICATED`;
- forecast-side future leakage rejection;
- evaluation claim is labeled as retrospective final-observed-label evaluation;
- no AS-OF, final-adjudicated, or historical replay claim;
- scope/coverage qualification is present in any model-quality report;
- source withdrawal invalidates downstream unfinished evaluation artifacts.

SQLite-only evidence must not substitute for PostgreSQL evidence where persistence behavior is part of acceptance.

## 19. Cross-contract atomic acceptance requirement

The candidate cannot be accepted by editing only one governing document.

```text
CROSS_CONTRACT_ACCEPTANCE_ATOMIC=true
```

A future acceptance package must synchronize at least:

```text
Q2A_I7_LABEL_CONTRACT_DELTA_ACCEPTED
S1_VISIBILITY_CONTRACT_DELTA_ACCEPTED
S1_SOURCE_AUTHORITY_CONTRACT_DELTA_ACCEPTED
IDFL_V1_ACCEPTANCE_RECORD_CREATED
```

Partial acceptance is forbidden:

```text
I7_ONLY_ACCEPTANCE_ALLOWED=false
VISIBILITY_ONLY_ACCEPTANCE_ALLOWED=false
SOURCE_AUTHORITY_ONLY_ACCEPTANCE_ALLOWED=false
```

If any required delta fails independent review, the effective state remains the current fail-closed state.

## 20. Acceptance decision candidate

Recommended future decision:

```text
RECOMMENDED_ACCEPTANCE_DECISION=ACCEPT_AS_SEPARATE_V1_MODE_PENDING_CROSS_CONTRACT_AMENDMENT_AND_INDEPENDENT_REVIEW
```

Rationale:

1. it matches the actual immutable daily aggregate representation without manufacturing lifecycle fields;
2. it preserves the stronger accepted AS-OF and FINAL modes unchanged;
3. it keeps forecast-input point-in-time requirements intact;
4. it creates auditable source-object and aggregate identities instead of fake row-level lifecycle identities;
5. it allows a precisely qualified retrospective model evaluation path after all other S1/S2 gates are separately accepted;
6. it preserves fail-closed missing-day, unmapped-date, scope, custody, and withdrawal controls.

Current decision remains:

```text
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=false
IDFL_V1_ACCEPTANCE_STATUS=PENDING_INDEPENDENT_REVIEW
```

## 21. Current governance state

This candidate does not close any current S1 gate.

```text
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
FORMAL_REVISION_POLICY_ACCEPTED=false
VISIBILITY_POLICY_ACCEPTED=false
FORMAL_MISSING_DAY_RULE_ACCEPTED=false
UNMAPPED_DATE_POLICY_ACCEPTED=false
S1_VISIBILITY_GATE_CLOSED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
```

## 22. Required next step

The next step after this candidate is independent review of the complete cross-contract semantics, not acceptance and not implementation.

```text
NEXT_ALLOWED_ACTION=RUN_INDEPENDENT_REVIEW_OF_IDFL_V1_CROSS_CONTRACT_AMENDMENT_CANDIDATE
```

Until that review passes and a separate acceptance package is explicitly authorized:

```text
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
```
