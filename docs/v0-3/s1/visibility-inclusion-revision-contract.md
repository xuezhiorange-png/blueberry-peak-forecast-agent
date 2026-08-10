# S1 Visibility, Inclusion, and Revision Contract

## Authority and current state

Actual-label visibility is label-mode dependent. `AS_OF_EVALUATION` reconstructs
historical state at the requested label observation cutoff;
`FINAL_ADJUDICATED` uses its existing finalization authority; and
`IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1` does not claim historical point-in-time
reconstruction, using accepted immutable-source-object completeness and
derivation lineage instead. No mode may use current database state as a
substitute for its accepted authority. This document binds to the accepted
Q2A/I7 visibility and winner contract and does not implement it.

```text
VISIBILITY_AUTHORITY=docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md
CURRENT_SOURCE_POINT_IN_TIME_ELIGIBLE=false
CURRENT_LABEL_SNAPSHOT_CONTRACT_STATUS=BLOCKED
CURRENT_REVISION_WINNER_RULE_STATUS=BLOCKED
CURRENT_INCLUSION_POLICY_STATUS=BLOCKED
LATEST_ROW_FALLBACK_ALLOWED=false
LIVE_MASTER_DATA_REMAPPING_ALLOWED=false
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
RANDOM_ADJACENT_DATE_SPLIT_ALLOWED=false
IDFL_V1_MODE_CONTRACT_ACCEPTED=true
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=true
IDFL_V1_VISIBILITY_MODE_SEMANTICS_ACCEPTED=true
```

The current state is fail-closed because no accepted source authority, cohort,
or time-visibility evidence has been supplied.

## Separate visibility domains

Forecast-input visibility and actual-label visibility are different contracts.
The label cutoff must never be used to prove that a forecast input was visible
when the forecast was made.

```text
FORECAST_INPUT_VISIBILITY_DOMAIN=FORECAST_INPUT
LABEL_VISIBILITY_DOMAIN=ACTUAL_LABEL

FORECAST_INPUT_AVAILABILITY_PREDICATE=
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT

ACTUAL_LABEL_AS_OF_PREDICATE=
SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT

ACTUAL_LABEL_FINAL_ADJUDICATED_PREDICATE=
SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
AND SOURCE_FINALIZED_AT <= SNAPSHOT_EXECUTED_AT

ACTUAL_LABEL_VISIBILITY_REQUIREMENT=LABEL_MODE_DEPENDENT
AS_OF_LABEL_POINT_IN_TIME_REPLAY_REQUIRED=true
FINAL_ADJUDICATED_FINALIZATION_AUTHORITY_REQUIRED=true
IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
```

`ingested_at`, `import_received_at`, `database_committed_at`,
`final_current_value_time`, `harvest_business_date`, and `latest_row_time`
cannot replace the source-system visibility fields.

## Forecast relevance and current IDFL applicability

The forecast-input point-in-time rule applies to source classes that are
actually used as forecast inputs. It must not be widened into a requirement
that the actual-label source expose record-level replay fields when the
selected actual-label mode is IDFL.

```text
SOURCE_002_ACTUAL_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
ACTUAL_LABEL_PURPOSE=HISTORICAL_FINAL_ACTUAL_FOR_FORECAST_EVALUATION
IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
IDFL_RECORD_LEVEL_LIFECYCLE_FIELDS_REQUIRED_FOR_LABEL_ELIGIBILITY=false
IDFL_SOURCE_AVAILABLE_AT_REQUIRED_FOR_LABEL_SIDE=false
FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY
FORECAST_INPUT_SOURCE_CLASS_USAGE_MUST_BE_ESTABLISHED_FROM_MODEL_OR_CONTRACT=true
CURRENT_MODEL_IMPLEMENTATION_FEATURE_SOURCE_DOMAINS=TASK9,ANALYTICS,WEATHER,PLANNING,CALENDAR
CURRENT_MODEL_HISTORICAL_WEATHER_FORECAST_FEATURE_PATH_FOUND=false
```

Record-level lifecycle fields remain required for `AS_OF_EVALUATION` and
`FINAL_ADJUDICATED`, and for a forecast-input class if its accepted contract
actually uses those fields. Their absence from the current Source 002 IDFL
label-side representation is not, by itself, a forecast future-leakage
finding.

## Source-class visibility matrix

Every source class must carry or explicitly policy-bind each time field. A
nullable field is allowed only when the source policy proves that the event
cannot occur for that class; null is not an implicit pass.

| source class | visibility domain | SOURCE_RECORDED_AT | SOURCE_AVAILABLE_AT | SOURCE_REVISED_AT | SOURCE_FINALIZED_AT | SOURCE_CANCELLED_AT | FORECAST_CUTOFF_AT | LABEL_OBSERVATION_CUTOFF_AT | availability predicate | revision rule | finalization rule | cancellation or void rule | point-in-time eligibility rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACTUAL_HARVEST_LABEL` | `ACTUAL_LABEL / REPLAY_LABEL_MODES` | required | required by source policy | required or policy-null | required or policy-null | required or policy-null | not applicable to label domain | required | `SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT`; FINAL additionally requires `SOURCE_FINALIZED_AT <= SNAPSHOT_EXECUTED_AT` | Q2A/I7 lineage winner | `FINALIZED_AT_REQUIRED` for FINAL mode | void is never a winner | source and lineage evidence complete |
| `ACTUAL_HARVEST_LABEL` | `ACTUAL_LABEL / IMMUTABLE_DAILY_FINAL_LABEL` | not required for label mode | source-object completeness authority | policy-defined by source class | not required for IDFL label mode | not required for IDFL label mode | not applicable to label domain | not required for IDFL label mode | `HARVEST_BUSINESS_DATE <= SOURCE_COMPLETE_THROUGH_BUSINESS_DATE` | not applicable; no revision winner | not required for IDFL label mode | not applicable; no void winner | immutable source-object, completeness, derivation-lineage, and target-binding evidence complete |
| `AREA` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | historical source version reconstructable |
| `YIELD_PLAN` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | no post-cutoff plan is eligible |
| `PHENOLOGY` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | late observations are not backdated |
| `WEATHER_OBSERVATION` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | source revision visible only at its availability time | finalization cannot move visibility earlier | cancelled observation excluded | no complete post-period backfill |
| `HISTORICAL_WEATHER_FORECAST` | `FORECAST_INPUT` | required | required | required | policy-defined | policy-defined | required | not applicable to input domain | issued forecast available by cutoff | issued-version identity at cutoff | finalized forecast does not rewrite prior issue | cancelled issue excluded | forecast issue time is authoritative |
| `PICKER_COUNT` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | pre-cutoff version required |
| `HARVEST_EFFICIENCY` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | no post-cutoff aggregate substitution |
| `MARKETABLE_RATE` | `FORECAST_INPUT` | required | required | required or policy-null | policy-defined | policy-defined | required | not applicable to input domain | `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` | cutoff-visible version only | finalized version only when policy requires | cancelled version excluded | post-season aggregate is not eligible pre-cutoff |
| `MANUAL_CORRECTION` | `ACTUAL_LABEL` | required | required | required | policy-defined | policy-defined | not applicable to label domain | required | `SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT` | correction is visible only at its recorded/revised time | final mode requires finalized time | void/correction lineage follows Q2A/I7 | correction evidence and parent lineage complete |
| `CANCELLED_OR_VOIDED_RECORD` | `ACTUAL_LABEL` | required | required | required or policy-null | policy-defined | required | not applicable to label domain | required | `SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT` | cancellation is a lineage event, not latest-row replacement | final mode uses final status boundary | void is excluded and cannot regain winner status | cancellation evidence is reconstructable |

The matrix is a contract of required fields and predicates, not evidence that
any source class is currently eligible.

## Cutoff and source-time rules

For forecast inputs, the source must be available by the forecast cutoff:

```text
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

For replay-mode actual labels, the source-recorded time must be visible by the
label cutoff:

```text
SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
```

The pre-existing `FINAL_ADJUDICATED` replay predicate remains:

```text
SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
AND SOURCE_FINALIZED_AT <= SNAPSHOT_EXECUTED_AT
```

The replay order is:

```text
FORECAST_CUTOFF_AT < FORECAST_TARGET_DATE_OR_WINDOW_END
<= LABEL_OBSERVATION_CUTOFF_AT <= REPLAY_EXECUTED_AT
```

Forecast-input visibility uses the source availability version available at
`FORECAST_CUTOFF_AT`. Label visibility uses the Q2A/I7 source-recorded time and
the selected label mode. `IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1` does not use
label-side point-in-time replay or a label observation cutoff; it requires
accepted source-object completeness and immutable-source derivation lineage.
A label cutoff cannot make a later forecast input eligible.

IDFL_V1 binds temporal eligibility to the accepted forecast-target interval
authority and does not redefine the forecast horizon:

```text
FORECAST_TEMPORAL_ELIGIBILITY_AUTHORITY=
ACCEPTED_FORECAST_TARGET_INTERVAL_CONTRACT
FORECAST_CUTOFF_AT < FORECAST_TARGET_DATE_OR_WINDOW_END
HARVEST_BUSINESS_DATE_TO_FORECAST_TARGET_INTERVAL_MAPPING_REQUIRED=true
FARM_TIMEZONE=Asia/Shanghai
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

An unqualified timestamp-to-business-date predicate is not an IDFL authority.
If a stricter interval-start rule is required, it must come from the accepted
forecast-target contract.

## Visibility modes and revision winners

```text
AS_OF_EVALUATION:
  SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
  visible source batch and mapping manifest are required
  one valid lineage terminal is required

FINAL_ADJUDICATED:
  SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
  SOURCE_FINALIZED_AT <= SNAPSHOT_EXECUTED_AT
  finalized winner under the same lineage and scope rules is required

IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1:
  LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
  SOURCE_RECORDED_AT_REQUIRED_FOR_LABEL_SIDE=false
  LABEL_OBSERVATION_CUTOFF_REQUIRED=false
  REVISION_WINNER_REQUIRED=false
  FINALIZED_AT_REQUIRED=false
  SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED=true
  SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
  IDFL_DOES_NOT_SELECT_Q2C_TARGET=true
  FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
  FORECAST_TEMPORAL_ELIGIBILITY_AUTHORITY=ACCEPTED_FORECAST_TARGET_INTERVAL_CONTRACT
  HARVEST_BUSINESS_DATE_TO_FORECAST_TARGET_INTERVAL_MAPPING_REQUIRED=true
  FARM_TIMEZONE=Asia/Shanghai
  CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
  CURRENT_SOURCE_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
```

`CORRECTED` records are non-terminal and require exactly one valid successor.
`FINALIZED` and `VOID` records cannot have successors. `VOID` is never a
winner. A visible child with an invisible parent, fork, cycle, discontinuity,
missing parent, or multiple visible terminal revisions is a structural failure.
One source family is used per snapshot; source-priority merging and cross-source
aggregation are prohibited.

The authoritative structural reason codes remain:

```text
SOURCE_EVIDENCE_DRIFT
MAPPING_EVIDENCE_MISSING
MAPPING_EVIDENCE_DRIFT
MISSING_SUPERSEDED_PARENT
VISIBLE_CHILD_WITH_INVISIBLE_PARENT
SUPERSESSION_CHAIN_FORK
SUPERSESSION_CHAIN_CYCLE
REVISION_NUMBER_DISCONTINUITY
MULTIPLE_VISIBLE_TERMINAL_REVISIONS
CORRECTED_WITHOUT_SUCCESSOR
FINALIZED_HAS_SUCCESSOR
VOID_HAS_SUCCESSOR
FINALIZED_AT_REQUIRED
SOURCE_SYSTEM_SCOPE_CONFLICT
IDEMPOTENCY_CONFLICT
UNSUPPORTED_LABEL_GRAIN
```

## Special source-class rules

- Post-season final yield cannot enter a pre-season forecast input.
- A late phenology observation cannot enter an earlier cutoff.
- Complete after-the-fact weather observations cannot replace the weather
  forecast version visible at the earlier cutoff.
- A post-season marketable-rate aggregate cannot enter a pre-season input.
- Picker count and harvest efficiency use the version available before the
  forecast cutoff.
- Manual-correction visibility is determined by source revision time and its
  parent lineage.
- Cancellation and void events cannot be hidden by falling back to the latest
  row.
- A source class and label mode that require historical point-in-time
  reconstruction must remain ineligible when that visibility cannot be
  reconstructed:

```text
REPLAY_MODE_SOURCE_POINT_IN_TIME_ELIGIBLE=false
```

This replay-only rule does not make IDFL automatically ineligible solely
because `HISTORICAL_LABEL_VISIBILITY_RECONSTRUCTION_SUPPORTED=false`.

## Inclusion, missing days, and replay identity

Request scope and frozen mapping evidence are checked before visibility,
lineage, and winner eligibility. Missing or excluded data is not silently
imputed as zero. Missing business dates remain unknown under
`UNKNOWN_NOT_ZERO`.

For IDFL_V1, source-object completeness and missing-day semantics are separate
gates. Completeness through a business date does not authorize a no-record to
zero mapping, and the IDFL mode does not select a Q2C target:

```text
SOURCE_OBJECT_COMPLETENESS_AUTHORITY_REQUIRED=true
SOURCE_COMPLETE_THROUGH_BUSINESS_DATE_REQUIRED=true
SOURCE_COMPLETENESS_POLICY_VERSION_REQUIRED=true
SOURCE_COMPLETENESS_EVIDENCE_HASH_REQUIRED=true
SOURCE_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_REQUIRED=true
SOURCE_OBJECT_BOUND_ROW_LINEAGE_IS_SOURCE_SYSTEM_IDENTITY=false
MISSING_DAY_SEMANTICS=UNKNOWN_NOT_ZERO
MISSING_DAY_NUMERIC_IMPUTATION_ALLOWED=false
NO_RECORD_TO_ZERO_MAPPING_STATUS=
BLOCKED_PENDING_SOURCE_COMPLETENESS_EVIDENCE
IDFL_DOES_NOT_SELECT_Q2C_TARGET=true
TARGET_DECISION_REMAINS_SEPARATE=true
LABEL_TARGET_AUTHORITY=Q2C_ACCEPTED_TARGET
IDFL_TARGET_BINDING_STATUS=BLOCKED_PENDING_Q2C_ACCEPTANCE
JULY_AUTOMATIC_SEASON_ASSIGNMENT=false
UNMAPPED_DATE_POLICY=PENDING
UNMAPPED_DATE_AUTO_ASSIGNMENT_ALLOWED=false
```

Snapshot requirements are label-mode dependent. Common snapshot identity is
deterministic and immutable. Replay modes must persist, at minimum:

```text
snapshot_request_identity
source_commit_manifest_set
frozen_mapping_manifest
winner_manifest
label_row_set_identity
exclusion_manifest
snapshot_hash
```

IDFL_V1 instead must persist immutable-source-object bindings and must not
require replay-only winner or revision artifacts:

```text
IDFL_LABEL_SNAPSHOT_REQUIREMENTS=
source_snapshot_reference,
source_object_set_hash,
source_object_identity_hashes,
source_complete_through_business_date,
source_completeness_policy_version,
source_completeness_evidence_hash,
source_row_lineage_manifest_hash,
mapping_policy_version,
visibility_policy_version,
inclusion_policy_version,
aggregation_policy_version,
label_row_set_identity,
exclusion_manifest,
snapshot_hash
IDFL_WINNER_MANIFEST_REQUIRED=false
IDFL_REVISION_GRAPH_REQUIRED=false
IDFL_LABEL_OBSERVATION_CUTOFF_REQUIRED=false
```

The same request and source universe must produce the same identities and
hashes. A different request, source universe, mapping version, or revision
graph must not reuse the previous snapshot identity. Persistence is atomic;
a partial snapshot is invalid.

## Acceptance requirements

```text
S1_ACCEPTANCE_REQUIRES_SOURCE_CLASS_VISIBILITY_MATRIX=true
S1_ACCEPTANCE_REQUIRES_FORECAST_INPUT_CUTOFF_RULE=true
S1_ACCEPTANCE_REQUIRES_FROZEN_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_EXPLICIT_EXCLUSION_MANIFEST=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SNAPSHOT_HASH=true
S1_ACCEPTANCE_REQUIRES_DETERMINISTIC_IDEMPOTENT_SNAPSHOT=true
S1_ACCEPTANCE_REQUIRES_NO_CURRENT_STATE_FALLBACK=true
S1_ACCEPTANCE_REQUIRES_LABEL_MODE_DEPENDENT_VISIBILITY_CONTRACT=true
AS_OF_ACCEPTANCE_REQUIRES_LABEL_OBSERVATION_CUTOFF_RULE=true
REPLAY_MODE_ACCEPTANCE_REQUIRES_REVISION_GRAPH_VALIDATION=true
REPLAY_MODE_ACCEPTANCE_REQUIRES_REVISION_WINNER_AUTHORITY=true
REPLAY_MODE_ACCEPTANCE_REQUIRES_IDEMPOTENT_REPLAY=true
IDFL_ACCEPTANCE_REQUIRES_SOURCE_OBJECT_COMPLETENESS_AUTHORITY=true
IDFL_ACCEPTANCE_REQUIRES_SOURCE_OBJECT_BOUND_ROW_LINEAGE=true
IDFL_ACCEPTANCE_REQUIRES_NO_REVISION_WINNER=true
IDFL_ACCEPTANCE_REQUIRES_IDEMPOTENT_SNAPSHOT=true
IDFL_ACCEPTANCE_REQUIRES_LABEL_OBSERVATION_CUTOFF=false
IDFL_V1_ATOMIC_CROSS_CONTRACT_ACCEPTANCE=true
IDFL_V1_VISIBILITY_MODE_SEMANTICS_ACCEPTED=true
IDFL_FORECAST_TARGET_INTERVAL_BINDING_ACCEPTED=true
```

Until source authority, cohort identity, and visibility evidence are accepted,
the current visibility and winner statuses remain `BLOCKED`.

The IDFL mode contract is accepted as design only. It does not make the
current source eligible:

```text
IDFL_V1_MODE_CONTRACT_ACCEPTED=true
IMMUTABLE_DAILY_FINAL_LABEL_ACCEPTED=true
DESIGN_STATUS=ACCEPTED_DESIGN_NOT_IMPLEMENTED
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY=false
CURRENT_SOURCE_IDFL_V1_ELIGIBILITY_STATUS=BLOCKED_PENDING_SOURCE_SPECIFIC_GATES
ACTUAL_LABEL_VISIBILITY_CLOSED=false
S1_VISIBILITY_GATE_CLOSED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
```
