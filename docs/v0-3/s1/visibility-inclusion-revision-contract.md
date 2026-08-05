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
| `ACTUAL_HARVEST_LABEL` | `ACTUAL_LABEL` | required | required by source policy | required or policy-null | required or policy-null | required or policy-null | not applicable to label domain | required | `SOURCE_RECORDED_AT <= LABEL_OBSERVATION_CUTOFF_AT` | Q2A/I7 lineage winner | `FINALIZED_AT_REQUIRED` for final mode | void is never a winner | source and lineage evidence complete |
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

For actual labels, the source-recorded time must be visible by the label cutoff:

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
the selected label mode. A label cutoff cannot make a later forecast input
eligible.

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
```

Until source authority, cohort identity, and visibility evidence are accepted,
the current visibility and winner statuses remain `BLOCKED`.
