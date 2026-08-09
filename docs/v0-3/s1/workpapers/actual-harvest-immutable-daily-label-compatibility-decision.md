# V0.3-S1 Actual-Harvest Immutable Daily Label Compatibility Decision Preparation

## Decision-preparation identity and boundary

```text
PREPARATION_ID=V0_3_S1_ACTUAL_HARVEST_IMMUTABLE_DAILY_LABEL_COMPATIBILITY_DECISION
BASELINE_MAIN_SHA=d6fcdcdc98e6f74655fa36cdbf0a7a634003c256
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
DOCUMENT_STATUS=DESIGN_ONLY_PREPARED_FOR_INDEPENDENT_REVIEW
DECISION_STATUS=NOT_ACCEPTED

REAL_SOURCE_EXPORT_READ_THIS_TASK=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
SOURCE_002_RE_READ_THIS_TASK=false
EXTERNAL_SOURCE_SYSTEM_ACCESSED_THIS_TASK=false
BACKTEST_STARTED=false
S2_STARTED=false
REPOSITORY_RUNTIME_MUTATION=false
```

This workpaper prepares a compatibility decision for a source class whose
confirmed representation is a daily business aggregate. It does not amend,
replace, or weaken the accepted Q2A/I7 contract, does not issue an attestation,
and does not authorize a backtest or an S2 package.

The authoritative references remain:

- `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`;
- `docs/v0-3/s1/visibility-inclusion-revision-contract.md`;
- `docs/v0-3/s1/source-authority-and-cohort-manifest.md`.

The proposal below is a compatibility candidate only. Any future contract
amendment requires a separately authorized policy change and independent
review.

## 1. Confirmed source-class facts

The following facts are the source-class facts supplied for this decision
preparation. They are recorded as governance input and are not the result of a
new source-file read or an external-system query in this task.

```text
SOURCE_CLASS=ACTUAL_HARVEST_LABEL
SOURCE_SYSTEM=扫码称重系统
SOURCE_DATASET=田间商品果每日采摘净重汇总
SOURCE_RECORD_IDENTITY=CONFIRMED_ABSENT
SOURCE_TIME_BASIS=DAILY_STATISTICS_ONLY
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
EXPORT_LIFECYCLE_SCHEMA_VERSION_SUPPORTED=false

SOURCE_FACT_ABSENCE_PRESERVED=true
NO_SYNTHETIC_LIFECYCLE_AUTHORITY=true
```

These facts describe the source representation. They do not create any
missing lifecycle field. `SOURCE_TIME_BASIS=DAILY_STATISTICS_ONLY` describes
the business statistics grain; it does not establish that the external
source system has no source-recorded timestamp. The current governed label
representation does not expose a trusted `source_recorded_at`, while the
external system capability remains unknown and unestablished. In particular,
no canonical-grain combination, row hash, business date, export time, import
time, database order, or repository-generated value is treated as a
source-system record identity or source-recorded timestamp.

The following distinctions are binding for this preparation:

```text
DAILY_STATISTICS_ONLY != SOURCE_SYSTEM_HAS_NO_SOURCE_RECORDED_AT
SOURCE_002_FIELD_ABSENCE != SOURCE_SYSTEM_CAPABILITY_ABSENCE
CURRENT_EXPORT_DOES_NOT_EXPOSE_SOURCE_RECORDED_AT != SOURCE_SYSTEM_DOES_NOT_STORE_SOURCE_RECORDED_AT
```

## 2. Current compatibility with accepted I7 modes

### 2.1 AS_OF_EVALUATION

The accepted Q2A/I7 contract requires, among other conditions:

```text
source_recorded_at_authority_status=TRUSTED_SOURCE_TIMESTAMP
source_recorded_at IS NOT NULL
source_recorded_at <= label_observation_cutoff_at
```

The current governed source representation has no stable source record
identity and does not expose trusted source-recorded-time evidence. This is
not a determination that the external source system cannot store such a
timestamp. The following values remain forbidden substitutes:
`HARVEST_BUSINESS_DATE`, export time, import time,
`database_committed_at`, database row order, latest row, or any lexical/row
hash ordering.

```text
CURRENT_I7_AS_OF_COMPATIBILITY=false
ACTUAL_LABEL_AS_OF_EVALUATION_SOURCE_CAPABILITY_STATUS=UNSUPPORTED_BY_CURRENT_GOVERNED_SOURCE_REPRESENTATION
ACTUAL_LABEL_AS_OF_EVALUATION_ELIGIBILITY=BLOCKED
```

This is a current-governed-representation compatibility result. It is not a
claim that the external source system has no timestamp capability, that the
business quantity is invalid, or that a future, separately governed label
mode cannot be designed.

### 2.2 FINAL_ADJUDICATED

The accepted Q2A/I7 authority requires a finalized terminal and a non-null
finalization time:

```text
FINAL_ADJUDICATED_REQUIRES_FINALIZED_TERMINAL=true
FINAL_ADJUDICATED_REQUIRES_FINALIZED_AT_NON_NULL=true
FINAL_ADJUDICATED_REQUIRES_FINALIZED_AT_BEFORE_OR_AT_SNAPSHOT_EXECUTION=true
FINAL_ADJUDICATED_FINALIZED_AT_POLICY_NULL_ALLOWED=false
```

The source-class fact is that no independent finalization event and no
`FINALIZED_AT` are present. Therefore this mode is unsupported by the current
source representation and remains fail-closed:

```text
ACTUAL_LABEL_FINAL_ADJUDICATED_SOURCE_CAPABILITY_STATUS=CONFIRMED_UNSUPPORTED_NO_INDEPENDENT_FINALIZATION_EVENT
ACTUAL_LABEL_FINAL_ADJUDICATED_SUPPORTED_BY_SOURCE_CLASS=false
ACTUAL_LABEL_FINAL_ADJUDICATED_ELIGIBILITY=BLOCKED
```

This decision does not introduce a policy-null pass for `FINAL_ADJUDICATED`.

## 3. Source model classification

The source is modeled for this decision as:

```text
SOURCE_MODEL=IMMUTABLE_DAILY_BUSINESS_AGGREGATE
DAILY_AGGREGATE=true
BUSINESS_DATE_BASED=true
POST_CONFIRMATION_MODIFICATION=false
CORRECTION_WORKFLOW_NOT_APPLICABLE=true
VOID_WORKFLOW_NOT_APPLICABLE=true
LATE_ENTRY_NOT_APPLICABLE=true
REVISION_LINEAGE_NOT_PRESENT=true
INDEPENDENT_FINALIZATION_NOT_PRESENT=true
SOURCE_RECORDED_TIMESTAMP_NOT_PRESENT_IN_GOVERNED_LABEL_REPRESENTATION=true
EXTERNAL_SOURCE_SYSTEM_SOURCE_RECORDED_TIMESTAMP_CAPABILITY=UNKNOWN_NOT_ESTABLISHED
STABLE_SOURCE_RECORD_ID_NOT_PRESENT=true
```

This model must not be described as a revisioned event store, a bitemporal
source, or a point-in-time replayable source. “Immutable” here means that the
confirmed business representation is a daily aggregate that is not modified
after confirmation; it does not supply historical visibility timestamps or
lineage that are absent from the source.

## 4. Candidate third mode: `IMMUTABLE_DAILY_FINAL_LABEL`

The following is a candidate mode, not an accepted contract:

```text
CANDIDATE_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL
CANDIDATE_MODE_STATUS=PREPARED_FOR_REVIEW_ONLY
```

The candidate is intended for a source that:

1. represents the label as a final observed business-day quantity;
2. is immutable after business confirmation;
3. has no correction, revision-lineage, void/cancel, or late-entry workflow;
4. the governed label representation does not expose the trusted
   `source_recorded_at` required for historical replay, and no historical
   version replay is available;
5. is evaluated as a final observed daily label rather than as a simulated
   historical label view.

The candidate does not invent a row identity. It would require a governed
source-object/snapshot identity and aggregate evidence sufficient to identify
the source package, while explicitly accepting that stable per-record identity
and label-side lifecycle replay are not available.

### 4.1 Candidate label-side semantics

```text
LABEL_VALUE_AUTHORITY=FINAL_OBSERVED_DAILY_BUSINESS_QUANTITY
LABEL_VISIBILITY_AUTHORITY=NOT_POINT_IN_TIME_REPLAYABLE
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
FORECAST_SIDE_POINT_IN_TIME_AUTHORITY_REQUIRED=true
```

The candidate may support a retrospective comparison of a forecast with the
final observed daily quantity only when the forecast-side evidence remains
point-in-time valid and:

```text
FORECAST_CUTOFF_AT < HARVEST_BUSINESS_DATE
```

That comparison is not an `AS_OF_EVALUATION` replay and is not
`FINAL_ADJUDICATED`. It must be named and reported as a separate evaluation
mode if, and only if, a future contract amendment accepts it.

### 4.2 Candidate prohibitions

Until a separate mode is formally accepted, and even after acceptance unless
the contract explicitly changes these values, the candidate must state:

```text
POINT_IN_TIME_LABEL_REPLAY_SUPPORTED=false
REVISION_WINNER_REPLAY_SUPPORTED=false
HISTORICAL_LABEL_VISIBILITY_RECONSTRUCTION_SUPPORTED=false
SOURCE_RECORDED_AT_CUTOFF_SUPPORTED=false
FINAL_ADJUDICATED_MODE_SUPPORTED=false
```

The candidate cannot be called `AS_OF_EVALUATION` or
`FINAL_ADJUDICATED`. It cannot authorize:

```text
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

Those claims require their own contract, evidence, and review gates.

## 5. Compatibility matrix

The matrix distinguishes the two accepted I7 modes from the proposed third
mode. “Candidate” describes a design property, not a current acceptance.

| dimension | `AS_OF_EVALUATION` | `FINAL_ADJUDICATED` | `IMMUTABLE_DAILY_FINAL_LABEL` candidate |
| --- | --- | --- | --- |
| stable source identity | Required for eligible source evidence; absent here | Required for eligible source evidence; absent here | Source-object/snapshot identity required; stable row identity is not fabricated |
| `source_recorded_at` | Required, trusted, non-null, and cutoff-bound; not exposed by the current governed representation | Required by the selected source/visibility contract; not exposed by the current governed representation | Not a label-side requirement in the candidate; the governed representation does not expose it and external system capability remains unknown |
| `source_available_at` | Source/lifecycle policy must support the visibility chain | Source/lifecycle policy must support the selected committed universe | Not used to make the final label historically visible; remains required for forecast inputs |
| revision identity | Required where revisions exist | Required for lineage winner selection | Not present and not reconstructed |
| lineage | One valid cutoff-visible terminal is required | One eligible finalized terminal is required | No lineage graph; no winner graph claim |
| `finalized_at` | Not a substitute for `source_recorded_at` | Required and non-null; policy-null cannot pass | Not required by the candidate, and never treated as evidence for `FINAL_ADJUDICATED` |
| late entry | Must be represented by source times and policy | Must be represented by source times and policy | Source fact says not applicable; candidate does not create late-entry evidence |
| correction | Must be represented with revision time and parent lineage | Must be represented under finalized winner rules | Source fact says not applicable; no correction lineage is invented |
| void/cancel | Must be represented and excluded from winner selection | Must be represented under final status rules | Source fact says not applicable; no void semantics are invented |
| label observation cutoff | Required and determines historical visibility | Null in the accepted final mode; it does not convert to replay | Not used for label-side visibility; any future contract must name this distinction |
| snapshot execution | Must be later than the selected cutoff | Bounds the required non-null finalization time | Identifies when aggregate evidence was prepared, not when the label became visible |
| winner algorithm | Q2A/I7 cutoff-visible lineage winner | Q2A/I7 finalized terminal winner | No winner algorithm; canonical daily aggregation is not a revision winner |
| historical replayability | Required | Not supplied by final adjudication alone | Explicitly not supported |
| allowed evaluation claim | Historical label state at an authorized cutoff | Finalized terminal under the accepted final rules | Only a future-approved retrospective final-observed-label comparison |
| forbidden evaluation claim | Current-row or latest-row replay | Backdated historical replay from final state | AS-OF replay, revision-winner replay, final-adjudicated eligibility, or leakage-safe model claim without separate review |

## 6. Forecast-side leakage boundary

The candidate mode changes neither the forecast-input contract nor the
forecast cutoff. All forecast inputs must continue to satisfy their applicable
source-class visibility rule, including:

```text
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

for source classes where that predicate is required. A final static label is
not permission to use future forecast inputs:

```text
LABEL_FINAL_STATIC_MODE != FORECAST_INPUT_FUTURE_LEAKAGE_ALLOWED
```

The forecast side must retain its own source identity, availability evidence,
cutoff, snapshot, and provenance. A label observation cutoff cannot make a
forecast input eligible, and a final observed label cannot retroactively prove
that a forecast input was available.

## 7. Decision options

### Option A — separate mode amendment

```text
OPTION_A=AMEND_Q2A_I7_WITH_SEPARATE_IMMUTABLE_DAILY_FINAL_LABEL_MODE
OPTION_A_STATUS=PREPARED_FOR_REVIEW
```

This option would add a separately named third mode with explicit prohibitions
on label-side replay and explicit forecast-side cutoff controls. It must not
rewrite the accepted predicates for `AS_OF_EVALUATION` or
`FINAL_ADJUDICATED`. It would require a versioned contract amendment,
auditability requirements for source-object/snapshot identity and aggregate
evidence, a precise permitted evaluation claim, and independent review before
any evaluation is authorized.

### Option B — keep I7 unchanged and exclude this label authority

```text
OPTION_B=KEEP_Q2A_I7_UNCHANGED_AND_DECLARE_SOURCE_002_INELIGIBLE_FOR_MODEL_EVALUATION_LABEL_AUTHORITY
OPTION_B_STATUS=PREPARED_FOR_REVIEW
```

This option makes no contract change and keeps the current fail-closed result.
It prevents unsupported model-evaluation claims but leaves the forecast
package without a usable label authority for this source class.

### Recommended decision for independent review

```text
RECOMMENDED_OPTION=OPTION_A_CONDITIONAL_SEPARATE_MODE
```

The recommendation is conditional, not an acceptance. Option A better matches
the confirmed immutable daily aggregate without manufacturing lifecycle
fields, while preserving the strongest existing I7 rules and requiring
forecast-side point-in-time provenance. It is preferable only if the separate
mode explicitly limits its claim to retrospective comparison against a final
observed daily quantity and passes independent governance review. Until then,
Option B's fail-closed behavior remains the effective operational state.

## 8. Required future decision controls

Before any future package can use the candidate mode, the decision must settle
at least:

- the formal name, version, and authority owner of the third mode;
- the minimum source-object/snapshot identity and aggregate audit evidence;
- whether business-date completeness and unmapped-date handling are accepted
  for the source class;
- the exact retrospective evaluation claim and its forbidden interpretations;
- how forecast-side source availability and cutoff evidence are independently
  proven;
- whether the resulting metric is allowed to be described as a model-quality
  claim or only as a descriptive retrospective comparison;
- the independent review and acceptance gate for the amended contract.

None of these decisions is made by this preparation document.

## 9. Fail-closed governance state

```text
ACTUAL_LABEL_AS_OF_EVALUATION_ELIGIBILITY=BLOCKED
ACTUAL_LABEL_FINAL_ADJUDICATED_ELIGIBILITY=BLOCKED
S1_VISIBILITY_GATE_CLOSED=false
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
V0_3_S2_AUTHORIZED=false
```

```text
FORMAL_ATTESTATION_CREATED=false
FORMAL_COHORT_MANIFEST_CREATED=false
REAL_DATA_ACCESS_AUTHORIZED=false
REAL_SOURCE_EXPORT_READ=false
REAL_BUSINESS_ROW_LEVEL_DATA_READ=false
```

The candidate mode is not a formal source authority, cohort acceptance,
Q2C decision, S1 acceptance, or S2 authorization.

## 10. Preparation validation checklist

```text
SOURCE_FACT_ABSENCE_PRESERVED=true
NO_SYNTHETIC_LIFECYCLE_AUTHORITY=true
SOURCE_RECORDED_AT_IN_CURRENT_GOVERNED_SOURCE_REPRESENTATION=NOT_PRESENT
CURRENT_GOVERNED_SOURCE_REPRESENTATION_EXPOSES_SOURCE_RECORDED_AT=false
EXTERNAL_SCAN_WEIGH_SYSTEM_SOURCE_RECORDED_AT_CAPABILITY_STATUS=UNKNOWN_NOT_ESTABLISHED
CURRENT_I7_AS_OF_COMPATIBILITY=false
FINAL_ADJUDICATED_FINALIZED_AT_POLICY_NULL_ALLOWED=false
ACTUAL_LABEL_FINAL_ADJUDICATED_SUPPORTED_BY_SOURCE_CLASS=false
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

No `source_recorded_at`, source record ID, `finalized_at`, revision lineage,
or source-system lifecycle schema is created by this document. The next step
is an independent review of this compatibility decision, not a backtest,
external-system access, or S2 implementation.
