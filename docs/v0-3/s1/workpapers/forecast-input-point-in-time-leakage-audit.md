# V0.3-S1 Forecast Input Point-in-Time Leakage Audit

```text
ARTIFACT_ID=V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT
ARTIFACT_VERSION=forecast-input-pit-leakage-audit-v1
AUDITED_REPOSITORY_SHA=b1b1ad4bfc36d27df6ccc07313649931948a1659
TASK_CLASS=S1_FORECAST_RELEVANCE_EVIDENCE_AND_CONTRACT_AUDIT
FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY
SOURCE_002_ACTUAL_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
SOURCE_002_RECENT_ACTUAL_HARVEST_USED_AS_FEATURE=false
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false
AUTHORITATIVE_HISTORICAL_FORECAST_CUTOFF=forecast_effective_cutoff_at / forecast_cutoff_at
CURRENT_RESIDUAL_VISIBILITY_INPUT=as_of_date
CURRENT_RESIDUAL_VISIBILITY_DERIVED_CUTOFF=end-of-day UTC for as_of_date
EXACT_FORECAST_CUTOFF_PROPAGATED_TO_RESIDUAL_VISIBILITY=false
RESIDUAL_VISIBILITY_USES_AS_OF_DATE_END_OF_DAY=true
POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
RESIDUAL_MODEL_EXPLICIT_ID_REQUIRED=true
RESIDUAL_MODEL_LATEST_LOOKUP_FOUND=false
RESIDUAL_MODEL_HISTORICAL_AVAILABILITY_PROVEN=false
RESIDUAL_MODEL_AUTHORITY_AUDIT_STATUS=PARTIAL
POST_CUTOFF_INPUT_REJECTED_SCOPE=EXACT_AUTHORITATIVE_FORECAST_CUTOFF
RESIDUAL_LOCAL_EOD_POST_CUTOFF_REJECTED=true
EXACT_FORECAST_CUTOFF_POST_CUTOFF_REJECTED=false
CORRECTION_R2_APPLIED=true
```

## 1. Scope and boundary

This is a code-and-contract evidence audit of the current forecast-input path.
It does not import data, materialize the actual-label dataset, inspect Source
002 rows, train or optimize a model, run a backtest, or change production
code. The Source 002 IDFL label-side exemption is kept separate from the
forecast-input visibility rule.

The audit was performed from the exact main baseline above. The machine-
readable row-level evidence is in:

`docs/v0-3/s1/evidence/forecast-input-point-in-time-leakage-audit.json`

The required forecast-input predicate is:

```text
KNOWN_AT <= FORECAST_CUTOFF_AT
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

Historical actual feature rows additionally require:

```text
OBSERVATION_DATE < FORECAST_AS_OF_DATE
```

The authoritative historical replay cutoff is the exact
`forecast_effective_cutoff_at` / `forecast_cutoff_at`, not merely the local
`as_of_date`. The current residual visibility API receives only `as_of_date`
and derives an end-of-day UTC cutoff. Therefore a same-day feature with
`source_available_at` after the exact forecast cutoff can be accepted by the
residual end-of-day comparison unless a separate upstream authority rejects
it. This is an open control gap, not an observed real-data leakage event.

For machine-readable consistency, `POST_CUTOFF_INPUT_REJECTED` is reserved for
rejection after the authoritative exact `FORECAST_CUTOFF_AT`. Because that
exact cutoff is not propagated, it is `false` for every used audit row. The
implementation still rejects values after the residual local `as_of_date`
end-of-day cutoff where its visibility checks apply; that local behavior is
recorded separately as `RESIDUAL_LOCAL_EOD_POST_CUTOFF_REJECTED=true` and must
not be interpreted as exact historical cutoff enforcement.

The residual visibility layer continues to fail closed for unknown,
blocklisted, disallowed, missing-required, future-known, future-available,
target-date actual, and future-observation inputs relative to its local
as-of-date end-of-day cutoff. Those local checks do not establish exact
historical cutoff rejection, so the machine-readable exact flag remains
`POST_CUTOFF_INPUT_REJECTED=false` for used rows. Existing tests cover the
representative valid and blocked cases; this audit does not weaken those
tests.

## 2. Current model input inventory

The current residual feature registry, rather than an older document list,
was used to derive the actual feature inventory.

| Source domain | Current features | Current path assessment |
| --- | --- | --- |
| TASK9 | `structural_arrival_p50_kg`, `structural_arrival_p80_kg`, `structural_arrival_p90_kg`, `forecast_horizon_days`, `structural_cumulative_to_as_of_kg` | PARTIAL: Task9 output is explicitly identified and cutoff-bound, but the Task8 upstream availability event is not explicit. |
| ANALYTICS | `actual_receipt_lag_1d_kg`, `actual_receipt_lag_3d_kg`, `actual_receipt_lag_7d_kg`, `actual_receipt_rolling_3d_mean_kg`, `actual_receipt_rolling_7d_mean_kg`, `actual_receipt_cumulative_to_as_of_kg`, `realized_cumulative_residual_to_as_of_kg` | PARTIAL: explicit `AnalyticsBuildRun`, source cutoff, prior observation dates, and fail-closed receipt selection exist, but exact `forecast_cutoff_at` ordering is not enforced because residual visibility uses as-of-date end-of-day. |
| WEATHER | `weather_7d_rainfall`, `weather_7d_gdd` | PARTIAL: generic caller-supplied `FeatureValue` timestamps are checked, but the current path does not require weather-specific observation date or stable source/hash binding. |
| PLANNING | `destination_factory_category` | PARTIAL: generic caller-supplied timestamps are checked, but the current path does not require the as-of plan version/hash selected by the planning service. |
| CALENDAR | `spring_festival_window_flag` | PARTIAL: version and hash are taken from the completed Task9 holiday snapshot, but its residual visibility timestamp is still mapped through as-of-date end-of-day rather than the exact historical forecast cutoff. |

The seven Analytics inputs are factory receipt analytics sourced through
`FactReceiptDaily` and an explicit `AnalyticsBuildRun` snapshot. They are not
the Source 002 actual-label feature path and must not be relabeled as recent
actual harvest input. The build snapshot gives a useful source boundary, but
the current residual path does not prove that boundary is at or before the
exact historical `forecast_cutoff_at`; it only compares it with the
as-of-date end-of-day cutoff.

```text
CURRENT_MODEL_ANALYTICS_FEATURE_PATH=FACTORY_RECEIPT_LAG_ROLLING_AND_CUMULATIVE
FORECAST_INPUT_SOURCE_CLASS_TAXONOMY_GAP=ANALYTICS_FACTORY_RECEIPT
```

`ANALYTICS_FACTORY_RECEIPT` is recorded as a taxonomy gap only. This audit
does not accept it as a canonical S1 source class.

## 3. Input and authority evidence

The JSON artifact contains 22 audited rows. After the exact-cutoff
re-audit, every used row is partial or not used:

```text
AUDITED_INPUT_COUNT=22
PASS_COUNT=0
PARTIAL_COUNT=21
BLOCKED_COUNT=0
NOT_USED_COUNT=1
```

The five Task9-derived features inherit the same partial upstream authority
finding. Task9 validates parameter, weather, and capacity source references
against its request as-of date and records hashes. It also validates Task8
completion, as-of date, model/config/source signatures, artifact hashes, and
row relationships. However, `Task8PredictionSourceRef` carries no explicit
`source_available_at` or equivalent availability event. The residual feature
builder then sets the feature timestamp to the Task9 cutoff. That is a useful
output boundary, but it cannot independently prove that every Task8 upstream
input was available at the timestamped forecast cutoff.

The Analytics path has stronger source snapshot evidence at this layer. The
current code loads an explicit completed build run, derives
`AnalyticsActualSnapshot.source_cutoff`, rejects receipt dates after the build
cutoff, and uses only dates before the forecast as-of date. However, the
current residual visibility contract compares that source cutoff with an
as-of-date end-of-day cutoff, not the exact historical `forecast_cutoff_at`.
A missing build or missing required value is not replaced by a current build
or a numeric fallback, but exact same-day post-cutoff exclusion remains
unproven.

The Calendar path requires a non-empty holiday version and hash in the Task9
completed output. The flag is deterministic from that frozen snapshot and does
not select a current calendar based on runtime date, but its residual
visibility timestamp is still derived from the as-of-date end-of-day cutoff.

The Weather and Planning repository services each contain useful as-of
selection logic. The current residual supplemental path, however, accepts a
generic `FeatureValue` from its caller and does not invoke those source-class
specific selectors. A non-empty `source_version` and arbitrary `source_ref`
are not equivalent to a stable source identity, row/hash binding, and
source-class-specific availability proof.

## 4. Leakage-control findings

### F-001 — Task8 availability authority is incomplete

The Task9 path checks `maturity_forecast_as_of_date <= request.as_of_date` and
many lineage identities, but the Task8 source reference has no explicit
availability event. This leaves a gap between a forecast as-of date and the
required `SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT` proof.

Required minimum implementation evidence: add and persist an upstream
availability authority and enforce it against the persisted forecast cutoff.

### F-002 — Weather supplemental binding is generic

`FeatureValue` requires `known_at`, `source_available_at`, and a non-empty
`source_version`, and the visibility audit rejects future timestamps. The
current Weather path does not require an observation date or a weather-specific
source/version/hash identity. A future observation could therefore be
misrepresented if its observation metadata is omitted by a caller.

Required minimum implementation evidence: make weather feature construction
carry observation date, stable source identity/hash, and source-class-specific
cutoff selection.

### F-003 — Planning supplemental binding is generic

The Planning service can select an effective plan as of a date, but the
residual feature builder currently accepts `destination_factory_category` as a
supplemental value and does not require the selected plan row/version/hash.
Generic timestamps alone do not prove that a post-cutoff plan revision was not
used.

Required minimum implementation evidence: bind the planning feature to the
as-of plan identity/version/hash and reject post-cutoff revisions.

### F-004 — Explicit model identity does not prove historical availability

The residual prediction request carries explicit `model_run_id`, `task9_run_id`,
and optional `feature_analytics_build_run_id`; the current entrypoint loads
these by ID, and no latest model lookup or current analytics-build substitution
was found. However, an explicit `model_run_id` does not prove that the selected
artifact existed and was available at or before the exact historical forecast
cutoff. Structural-only fallback is used when the requested model or feature
visibility is blocked; it is not a latest/current source substitution.

Required minimum implementation evidence: enforce
`MODEL_ARTIFACT_AVAILABLE_AT <= FORECAST_CUTOFF_AT` or an equivalent historical
model authority contract. A future model artifact selected by explicit ID must
be blocked.

### EXACT_FORECAST_CUTOFF_NOT_PROPAGATED_TO_RESIDUAL_VISIBILITY — OPEN

The authoritative historical replay value is
`forecast_effective_cutoff_at` / `forecast_cutoff_at`. The current residual
visibility API receives only `as_of_date` and derives an end-of-day UTC cutoff.
For example, a source available at `2026-03-15T10:00:00Z` could be after an
exact cutoff of `2026-03-15T04:00:00Z` while still passing the residual EOD
comparison. This is a potential leakage-control gap; no real business row was
read and no observed leakage event was established.

Required minimum implementation evidence: propagate the exact forecast cutoff
into residual visibility and reject same-day post-cutoff availability.

### RESIDUAL_MODEL_ARTIFACT_HISTORICAL_AVAILABILITY_NOT_ENFORCED — OPEN

The prediction path requires an explicit `model_run_id` and does not perform a
latest-model lookup, but a model artifact created after the historical
forecast cutoff can still be explicitly selected unless another upstream
authority rejects it.

Required minimum implementation evidence: enforce
`MODEL_ARTIFACT_AVAILABLE_AT <= FORECAST_CUTOFF_AT` or an equivalent historical
model authority contract. Future model-run selection must fail closed.

## 5. Weather forecast path

```text
CURRENT_MODEL_HISTORICAL_WEATHER_FORECAST_FEATURE_PATH_FOUND=false
HISTORICAL_WEATHER_FORECAST_AUDIT_STATUS=NOT_USED
```

Only the current Weather observation feature path was audited. No historical
weather-forecast issue/version feature path is present in the current residual
feature registry and builder, so no unused source class was made into a gate.

## 6. Source 002 boundary

```text
SOURCE_002_USED_AS_FORECAST_INPUT=false
SOURCE_002_REREAD=false
SOURCE_002_ROW_LEVEL_INSPECTION=false
SOURCE_002_RECORD_LIFECYCLE_AUDIT=false
```

Source 002 remains an IDFL historical final actual-label authority candidate,
not a current forecast feature. No Source 002 export, row, record identifier,
or external source system was read in this task.

## 7. Result and minimum gaps

Because current used paths contain PARTIAL evidence, the audit cannot close the
forecast-input PIT control:

```text
FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED_SCOPE=NO_REAL_BUSINESS_ROW_LEVEL_INPUTS_WERE_READ_OR_EXECUTED_IN_THIS_AUDIT; NO_OBSERVED_LEAKAGE_EVENT_WAS_ESTABLISHED
POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
POST_CUTOFF_INPUT_REJECTED_SCOPE=EXACT_AUTHORITATIVE_FORECAST_CUTOFF
POST_CUTOFF_INPUT_REJECTED_USED_ROWS=false
RESIDUAL_LOCAL_EOD_POST_CUTOFF_REJECTED=true
EXACT_FORECAST_CUTOFF_POST_CUTOFF_REJECTED=false
FORECAST_INPUT_PIT_EVIDENCE_READY_FOR_INDEPENDENT_REVIEW=true
DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true
```

`false` for detected leakage means no concrete future-valued feature was
observed in this repository-only audit. It does not mean the control is
closed; the missing authority bindings above remain blockers.

The minimum implementation/evidence gaps are:

1. Add an explicit Task8 source availability authority and enforce it at the
   persisted Task9/forecast cutoff.
2. Propagate the exact `forecast_cutoff_at` into residual feature visibility;
   residual visibility currently uses an `as_of_date` end-of-day cutoff, so
   same-day post-cutoff exclusion is not proven.
3. Enforce historical residual model artifact availability at or before the
   exact `forecast_cutoff_at`; explicit `model_run_id` selection alone does not
   prove historical availability.
4. Require weather observation date and stable weather source/version/hash
   provenance for residual supplemental Weather inputs.
5. Require as-of plan identity/version/hash provenance for residual
   supplemental Planning inputs.
6. Keep `ANALYTICS_FACTORY_RECEIPT` distinct from Source 002 and resolve its
   canonical S1 source-class taxonomy in a separately authorized governance
   step.

No production code, model parameter, database, actual-label dataset, split,
backtest, S1 acceptance record, or S2 state was changed by this audit.

## 8. Non-acceptance boundary

```text
CANONICAL_GATE_STATUS_CHANGED=false
GATE_PASS_COUNT=0
SOURCE_AUTHORITY_ACCEPTED=false
SOURCE_COHORT_ACCEPTED=false
Q2C_ACCEPTED=false
V0_3_S1_COMPLETE=false
V0_3_S1_ACCEPTED=false
V0_3_S2_AUTHORIZED=false
V0_3_S2_STARTED=false
PRODUCTION_CODE_CHANGED=false
MODEL_CHANGED=false
DATABASE_WRITE=false
BACKTEST_STARTED=false
```

The artifact is evidence ready for independent review only. It is not a
forecast-readiness approval or an S1 acceptance decision.

## 9. Validation performed

```text
JSON_PARSE_VALID=true
GIT_DIFF_CHECK=PASS
EXACT_CUTOFF_REAUDIT_STATUS=PASS
AUDIT_ROW_STATUS_SUM=22
POST_CUTOFF_SEMANTICS_RECONCILED=PASS
USED_ROW_EXACT_POST_CUTOFF_REJECTED_FALSE=21
NOT_USED_ROW_SEMANTICS_PRESERVED=true
TARGETED_TEST_STATUS=PASS
RESIDUAL_VISIBILITY_PREDICTION_TRAINING_AND_CORE_FORECAST=90 passed
REGISTRY_MANIFEST_REPLAY_CONTRACT_STATUS_AND_TASK9_AUTHORITY=127 passed
PRODUCTION_CODE_CHANGED=false
MODEL_CHANGED=false
DATABASE_WRITE=false
BACKTEST_STARTED=false
```

The local test environment did not provide a standalone `pytest` executable;
the repository's locked `uv` environment was used instead. The exact-head
CI remains the final branch validation required by this task.
