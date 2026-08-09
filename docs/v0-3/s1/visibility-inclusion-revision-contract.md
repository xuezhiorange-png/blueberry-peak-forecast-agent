# S1 Visibility, Inclusion, and Revision Contract

## Authority and current state

Historical labels must be reconstructed at the requested observation cutoff,
not from the current database state. This document binds to the accepted Q2A/I7
visibility and winner contract and does not implement it.

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
RECORD_STATUS=FINALIZED
AND SOURCE_FINALIZED_AT <= SNAPSHOT_EXECUTED_AT

ACTUAL_LABEL_VISIBILITY_REQUIREMENT=LABEL_MODE_DEPENDENT
AS_OF_LABEL_POINT_IN_TIME_REPLAY_REQUIRED=true
FINAL_ADJUDICATED_FINALIZATION_AUTHORITY_REQUIRED=true
IDFL_LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
```

`ingested_at`, `import_received_at`, `database_committed_at`,
`final_current_value_time`, `harvest_business_date`, and `latest_row_time`
cannot replace the source-system visibility fields.

## Source-class visibility matrix

Every source class must carry or explicitly policy-bind each time field. A
nullable field is allowed only when the source policy proves that the event
cannot occur for that class; null is not an implicit pass.

| source class | visibility domain | SOURCE_RECORDED_AT | SOURCE_AVAILABLE_AT | SOURCE_REVISED_AT | SOURCE_FINALIZED_AT | SOURCE_CANCELLED_AT | FORECAST_CUTOFF_AT | LABEL_OBSERVATION_CUTOFF_AT | availability predicate | revision rule | finalization rule | cancellation or void rule | point-in-time eligibility rule |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ACTUAL_HARVEST_LABEL` | `ACTUAL_LABEL` | mode-dependent: required for AS_OF; not required for IDFL | required by source policy for replay modes; IDFL uses source-object completeness | required or policy-null by mode | required or policy-null by mode | required or policy-null by mode | not applicable to label domain | required for AS_OF only | AS_OF uses `SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT`; FINAL uses finalized terminal; IDFL uses completeness authority | Q2A/I7 lineage winner for replay modes; not applicable for IDFL | `FINALIZED_AT_REQUIRED` for FINAL only | void is never a winner; IDFL has no void winner rule | mode-specific source/object lineage and completeness evidence complete |
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

For `AS_OF_EVALUATION` actual labels, the source-recorded time must be visible
by the label cutoff:

```text
SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT
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
- A source whose historical visibility cannot be reconstructed must remain
  ineligible:

```text
SOURCE_POINT_IN_TIME_ELIGIBLE=false
```

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

An immutable label snapshot must persist, at minimum:

```text
snapshot_request_identity
source_commit_manifest_set
frozen_mapping_manifest
winner_manifest
label_row_set_identity
exclusion_manifest
snapshot_hash
```

The same request and source universe must produce the same identities and
hashes. A different request, source universe, mapping version, or revision
graph must not reuse the previous snapshot identity. Persistence is atomic;
a partial snapshot is invalid.

## Acceptance requirements

```text
S1_ACCEPTANCE_REQUIRES_SOURCE_CLASS_VISIBILITY_MATRIX=true
S1_ACCEPTANCE_REQUIRES_FORECAST_INPUT_CUTOFF_RULE=true
S1_ACCEPTANCE_REQUIRES_LABEL_OBSERVATION_CUTOFF_RULE=true
S1_ACCEPTANCE_REQUIRES_FROZEN_MAPPING_EVIDENCE=true
S1_ACCEPTANCE_REQUIRES_REVISION_GRAPH_VALIDATION=true
S1_ACCEPTANCE_REQUIRES_EXPLICIT_EXCLUSION_MANIFEST=true
S1_ACCEPTANCE_REQUIRES_IMMUTABLE_SNAPSHOT_HASH=true
S1_ACCEPTANCE_REQUIRES_IDEMPOTENT_REPLAY=true
S1_ACCEPTANCE_REQUIRES_NO_CURRENT_STATE_FALLBACK=true
S1_ACCEPTANCE_REQUIRES_LABEL_MODE_DEPENDENT_VISIBILITY_CONTRACT=true
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
