# V0.3-S1 Forecast Input Point-in-Time Leakage Audit

ARTIFACT_ID=V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT
ARTIFACT_VERSION=forecast-input-pit-leakage-audit-v1
TASK_CLASS=DOCS_ONLY_POST_PR194_WEATHER_REVALIDATION
AUDITED_REPOSITORY_SHA=9dc4992e76453ce5bc6c03b65d8aab72ccd169ef
PREVIOUS_REVIEWED_HEAD_SHA=aa56f85f256eccdb162398c00353d4d2f61e1535
REVALIDATED_PR_189=true
REVALIDATED_PR_190=true
PR_189_MERGE_COMMIT_SHA=3cd720249ddd8e20fab65558c3ee83e57303516e
PR_190_MERGE_COMMIT_SHA=7b6d4e89ed528d0e9153fcfb209da16110a68e32
PR_192_MERGE_COMMIT_SHA=768d4f8391504eb907277611fdf99589518c0edf
REVALIDATED_PR_192=true
REVALIDATED_PR_194=true
PR_194_MERGE_COMMIT_SHA=9dc4992e76453ce5bc6c03b65d8aab72ccd169ef

FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY
SOURCE_002_USED_AS_FORECAST_INPUT=false
SOURCE_002_REREAD=false
LABEL_SIDE_POINT_IN_TIME_REPLAY_REQUIRED=false

AUTHORITATIVE_HISTORICAL_FORECAST_CUTOFF=HarvestStateRun.forecast_effective_cutoff_at / exact forecast_cutoff_at
CURRENT_RESIDUAL_VISIBILITY_INPUT=persisted exact forecast cutoff for replay; legacy non-replay EOD compatibility only when persisted cutoff is absent
CURRENT_RESIDUAL_VISIBILITY_DERIVED_CUTOFF=normalized forecast_effective_cutoff_at for replay; legacy UTC EOD only for non-replay runs without persisted cutoff
EXACT_FORECAST_CUTOFF_PROPAGATED_TO_RESIDUAL_VISIBILITY=true
RESIDUAL_VISIBILITY_USES_AS_OF_DATE_END_OF_DAY=false
REPLAY_EOD_FALLBACK_ALLOWED=false
LEGACY_NON_REPLAY_EOD_COMPATIBILITY=true
RESIDUAL_FEATURE_VISIBILITY_EXACT_CUTOFF_POST_CUTOFF_REJECTED=true
EXACT_FORECAST_CUTOFF_POST_CUTOFF_REJECTED_AUDIT_WIDE=false

TASK8_DAILY_PERSISTED_AVAILABILITY_AUTHORITY_PROVEN=true
TASK8_CALLER_OMISSION_BYPASS_CLOSED=true
TASK8_POST_CUTOFF_DB_ROW_REJECTED=true
TASK8_AVAILABILITY_FINDING_CLOSED=true
EXACT_CUTOFF_FINDING_CLOSED=true

WEATHER_EXPLICIT_RUN_ID_REQUIRED=true
WEATHER_LATEST_OR_CURRENT_RUN_FALLBACK_ALLOWED=false
WEATHER_PERSISTED_RUN_RELOADED=true
WEATHER_RUN_STATUS_COMPLETED_REQUIRED=true
WEATHER_OBSERVATION_DATE_REQUIRED=true
WEATHER_OBSERVATION_DATE_BOUND_TO_PERSISTED_RUN=true
WEATHER_SOURCE_SIGNATURE_BOUND=true
WEATHER_FEATURE_VERSION_BOUND=true
WEATHER_CONFIG_HASH_BOUND=true
WEATHER_MAPPING_VERSION_BOUND=true
WEATHER_SOURCE_VERSION_BOUND=true
CROSS_RUN_WEATHER_PROVENANCE_TAMPER_BLOCKED=true
WEATHER_AUTHORITY_TRAINING_ENFORCED=true
WEATHER_AUTHORITY_PREDICTION_ENFORCED=true
SHARED_WEATHER_AUTHORITY_VALIDATOR=true
WEATHER_KNOWN_AT_EXACT_CUTOFF_CHECK_PRESERVED=true
WEATHER_SOURCE_AVAILABLE_AT_EXACT_CUTOFF_CHECK_PRESERVED=true
WEATHER_CUTOFF_EQUALITY_ALLOWED=true

AUDITED_INPUT_COUNT=22
PASS_COUNT=4
PARTIAL_COUNT=17
BLOCKED_COUNT=0
NOT_USED_COUNT=1
PR190_DIRECT_IMPACT_ROW_COUNT=6
PR190_DIRECT_IMPACT_ROWS_PASS=0
TASK9_DERIVED_PASS_COUNT=0
TASK9_UPSTREAM_AUTHORITY_STATUS=PARTIAL
RESIDUAL_MODEL_AUTHORITY_ROW_PROMOTED_TO_PASS=true
RESIDUAL_MODEL_AUTHORITY_AUDIT_STATUS=PASS
RESIDUAL_MODEL_HISTORICAL_AVAILABILITY_PROVEN=true
CALENDAR_ROW_PROMOTED_TO_PASS=false
CALENDAR_STATUS=PARTIAL

FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
IMPLEMENTATION_GAP_FOUND=true
DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true

## 1. Scope and authority

This is a documentation-only current-main revalidation correction. It absorbs
the merged PR #189 exact-cutoff fix and PR #190 Task8 persisted-availability
fix. It changes neither production code nor tests, schemas, databases, models,
nor canonical S1 acceptance state. It does not read Source 002 or run a real
business backtest.

The residual FeatureValue-level replay predicate remains:

    KNOWN_AT <= FORECAST_CUTOFF_AT
    SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT

For replay, FORECAST_CUTOFF_AT is the normalized persisted
HarvestStateRun.forecast_effective_cutoff_at. A legacy UTC end-of-day
compatibility cutoff is available only for non-replay runs without persisted
cutoff metadata. It is not a replay fallback.

The predicate above is scoped to the residual FeatureValue and Task8 controls;
it is not an assertion that every nested Task9 source authority uses an exact
timestamp. The row-level audit therefore records mixed authority semantics and
does not promote an end-to-end Task9 chain without complete proof.

## 2. Current-main implementation evidence

### PR #189 — exact residual feature cutoff

Current main contains:

- `backend/app/residual_model/forecast_cutoff.py`, which resolves the
  persisted exact replay cutoff and fails closed when a replay cutoff is
  missing;
- `backend/app/residual_model/visibility.py`, which normalizes the exact
  cutoff and rejects `known_at` or `source_available_at` after it;
- `backend/app/residual_model/prediction_features.py` and
  `backend/app/residual_model/training_manifest.py`, which pass the resolved
  cutoff into prediction and training visibility audits.

The former exact-cutoff propagation finding remains closed by PR #189. This
proves the scoped residual FeatureValue control, not every upstream source
authority used to construct a Task9 result.

### PR #190 — Task8 persisted availability

Current main contains:

- `backend/app/harvest_state/application.py`, which sends the exact replay
  requirement and cutoff into the Task8 binder;
- `backend/app/harvest_state/authority_request_loader.py`, which loads the
  persisted `MaturityDailyPredictionModel`, uses its `created_at` as the
  authoritative Task8 daily availability timestamp, rejects caller omission
  in exact replay, rejects caller timestamp mismatches, and rejects a
  persisted daily row after the exact cutoff;
- `backend/app/rolling_backtest/replay_pipeline.py`, which explicitly passes
  `require_persisted_task8_availability=true` and the node cutoff.

The former Task8 availability finding remains closed by PR #190. It does not
by itself prove all nested Task9 parameter, weather, capacity, or calendar
source authorities.

### PR #192 — residual model replay-trained persisted authority

Current main contains the merged PR #192 replay-trained authority chain. The
prediction-time gate in `backend/app/residual_model/application.py` reloads the
persisted `ResidualModelTrainingRun`, requires a persisted replay Task9 run, and
checks that the persisted Task12 context matches the persisted typed attempt,
Task9 identity/result, and exact `forecast_cutoff_at`. It then requires:

- `training_cutoff_at <= forecast_cutoff_at` with timezone-aware timestamps;
- `training_manifest_hash` and `task10_manifest_hash` equal the persisted
  training run manifest hash;
- `model_config_hash` and `task10_config_hash` equal the persisted training run
  config hash;
- the persisted manifest row count to match the training run;
- every persisted training observation and label availability date to be at or
  before the persisted training cutoff;
- a recomputed manifest hash and recomputed Task12 training dataset hash to
  match persisted authority.

The shared `replay_training_authority.py` helpers reconstruct manifest rows and
the canonical dataset identity from persisted state. The replay producer in
`replay_trained_service.py` binds the Task12 context and result identity to the
persisted Task10 training manifest/config and artifact metadata rather than
caller-only projection values. This is a valid replay-trained authority path:
the replay artifact may be created after the forecast cutoff only when the
persisted training and label authority is historical and the exact cutoff
checks pass; it is not a generic future-artifact exemption.

The current-main regression set passed 91 tests across prediction application,
replay-trained slice E1/E3, and forecast-cutoff/visibility paths. This closes
the residual model authority row without promoting any Task9-derived row.

### PR #194 — Weather supplemental persisted authority

Current main contains the merged PR #194 Weather correction at
`9dc4992e76453ce5bc6c03b65d8aab72ccd169ef`. The shared
`backend/app/residual_model/weather_authority.py` binder is invoked by both
`training_manifest.py` and `prediction_features.py`; the training and
prediction paths therefore use one persisted Weather authority validator.

For `weather_7d_rainfall` and `weather_7d_gdd`, the binder requires an explicit
`weather_feature_run_id` and reloads that exact persisted `WeatherFeatureRun`.
There is no latest/current/implicit run fallback, and the persisted run must be
`completed`. It requires `FeatureValue.observation_date`, requires it to equal
the persisted `feature_date`, and requires both persisted `as_of_date` and
`feature_date` to be no later than the Task9 `as_of_date`.

The binder enforces parity for the persisted SHA-256 `source_signature`,
`feature_version`, `config_hash`, `mapping_version`, and
`weather_source_version`. It rejects missing/unknown/non-completed run IDs,
observation-date omission or mismatch, metadata mismatch, and cross-run
provenance mixing. The exact caller `known_at` and `source_available_at`
cutoff checks remain in residual visibility, including the inclusive equality
boundary. `WeatherFeatureRun.finished_at` is not treated as the historical
business availability timestamp for replay; the replay evidence is the
persisted run identity/provenance plus historical feature/as-of dates and the
existing caller visibility timestamps.

The current-main targeted revalidation passed 60 tests across the Weather
authority binder, training and prediction paths, exact-cutoff visibility, and
related residual authority regressions. These facts support promotion of the
two Weather feature rows and the Weather authority row only; they do not
promote Planning, Analytics, Calendar, or Task9-derived rows.

## 3. Authority semantics reconciled against current main

### Task8 daily prediction

`MaturityDailyPredictionModel.created_at <= exact forecast_cutoff_at` is the
authoritative Task8 daily rule. The persisted row identity, caller parity,
replay cutoff, and equality boundary are covered by the merged PR #190 path.

### Rolling availability registry

`backend/app/rolling_backtest/availability.py` defines source-specific rules.
The registry includes exact timestamp rules, exact timestamp plus observation
date rules, and explicit `LOCAL_AVAILABLE_DATE` / local-date-with-observation
rules. These policies must not be flattened into one universal timestamp
predicate.

### Task9 nested source references

`backend/app/harvest_state/schemas.py` defines `ParameterSourceRef.available_at`
and `as_of_date` as dates. `backend/app/harvest_state/service.py` validates
these references with date-level predicates such as
`available_at <= as_of_date`. The Task9 request therefore contains a mixed
authority chain: Task8 has an exact persisted timestamp, while nested
parameter, weather, capacity, and holiday references retain their own
date-level source policy. The current audit does not establish a complete
end-to-end reconciliation of those policies, so Task9-derived rows remain
PARTIAL.

### Supplemental Weather and Planning FeatureValue inputs

For Weather, the residual builder accepts the feature value and then binds it
through the shared persisted Weather authority validator. It does not use
`WeatherFeatureRun.finished_at` as historical business availability. The
supplied `known_at` and `source_available_at` are still normalized and
compared against the exact cutoff by residual visibility, while the persisted
run identity/provenance and observation-date parity are independently required.

Planning remains caller-supplied at this point: its as-of plan
identity/version/hash provenance is still incomplete and remains a separate
open gap.

### Residual model request and artifact

The residual model authority row is now PASS for the current merged
implementation. Non-replay prediction keeps the direct persisted timestamp
checks: `ResidualModelTrainingRun.finished_at` and each persisted artifact's
`created_at` must be at or before the exact forecast cutoff. Replay-trained
prediction uses the explicit persisted replay authority path instead of
silently applying a post-cutoff artifact as a generic fallback.

That replay path reloads the persisted Task12 training run and its manifest
rows, validates Task12 input-snapshot/typed-attempt parity, binds both Task12
and Task10 manifest/config identities to the persisted training run, verifies
training and label availability against a training cutoff no later than the
exact forecast cutoff, and recomputes both manifest and training-dataset
hashes. The producer and prediction-time validator use the same canonical
manifest/dataset identity helpers. Therefore the authority is persisted and
reproducible rather than caller-provided, while valid replay execution remains
available.

### Analytics realized cumulative composite

`realized_cumulative_residual_to_as_of_kg` consumes AnalyticsBuildRun-derived
actual cumulative data and Task9 structural cumulative data. In current main,
the composite `FeatureValue.source_available_at` is stamped to the forecast
cutoff, while the authoritative `AnalyticsBuildRun.source_cutoff` is not
carried into the composite or independently checked against the cutoff.
Generic residual visibility therefore cannot prove historical Analytics-build
availability for this feature.

## 4. Row-level revalidation result

The machine-readable artifact contains exactly 22 rows:

| Input group | Rows | Status | Remaining reason |
| --- | ---: | --- | --- |
| TASK9 structural outputs | 5 | PARTIAL | Task8 exact availability and residual exact cutoff are present, but nested Task9 source refs retain date-level policies and the complete mixed upstream chain is not reconciled. |
| AUTHORITY.TASK9_UPSTREAM_CHAIN | 1 | PARTIAL | Task8 uses exact `created_at`, while Task9 parameter/weather/capacity refs use `available_at <= as_of_date`; one universal exact-timestamp predicate is not proven. |
| Calendar | 1 | PARTIAL | Version/hash binding exists, but the upstream holiday authority remains a date-level Task9 source reference whose mixed-policy integration is not fully proven. |
| Analytics features | 7 | PARTIAL | Generic source-cutoff checks exist for ordinary Analytics features; the source-class taxonomy remains unaccepted and the realized cumulative composite has a separate source-cutoff binding gap. |
| AUTHORITY.ANALYTICS_BUILD_RUN_SNAPSHOT | 1 | PARTIAL | Analytics source cutoff is available for the ordinary snapshot path, but source-class taxonomy remains unaccepted. |
| Weather features | 2 | PASS | Explicit completed persisted WeatherFeatureRun identity, observation-date parity, source/version/hash provenance, cross-run protection, and exact caller timestamp visibility are all covered by merged PR #194 and current-main tests. |
| AUTHORITY.WEATHER_SUPPLEMENTAL_BINDING | 1 | PASS | Shared persisted Weather authority binding is enforced in training and prediction; omission, mismatch, non-completed, unknown, and cross-run cases fail closed. |
| Planning feature | 1 | PARTIAL | Caller timestamps are checked against the exact cutoff; as-of selected plan identity/version/hash remains unbound. |
| AUTHORITY.PLANNING_SUPPLEMENTAL_BINDING | 1 | PARTIAL | Caller timestamps are checked against the exact cutoff; as-of selected plan provenance remains unbound. |
| AUTHORITY.RESIDUAL_MODEL_REQUEST_AND_ARTIFACT | 1 | PASS | Persisted non-replay training/artifact timestamps and replay-trained Task12 training/label authority are checked against the exact forecast cutoff. |
| Historical weather forecast | 1 | NOT_USED | No current registered feature path. |

AUDITED_INPUT_COUNT=22
PASS_COUNT=4
PARTIAL_COUNT=17
BLOCKED_COUNT=0
NOT_USED_COUNT=1
PR190_DIRECT_IMPACT_ROW_COUNT=6
PR190_DIRECT_IMPACT_ROWS_PASS=0
TASK9_DERIVED_PASS_COUNT=0
CALENDAR_ROW_PROMOTED_TO_PASS=false

The six PR #190 direct-impact rows remain explicitly identified, but none is
promoted to PASS because the broader Task9 upstream authority chain is not
fully proven in this audit:

    TASK9.structural_arrival_p50_kg
    TASK9.structural_arrival_p80_kg
    TASK9.structural_arrival_p90_kg
    TASK9.forecast_horizon_days
    TASK9.structural_cumulative_to_as_of_kg
    AUTHORITY.TASK9_UPSTREAM_CHAIN

The residual model authority row is independent of that mixed Task9-derived
chain and is promoted to PASS based on the merged PR #192 persisted replay
authority evidence above.

The two Weather feature rows and `AUTHORITY.WEATHER_SUPPLEMENTAL_BINDING` are
independent of the mixed Task9-derived chain and are promoted to PASS based on
the merged PR #194 persisted Weather authority evidence above.

## 5. Correction findings

### P1-1 — Supplemental timestamps

For Weather and Planning, the evidence now records:

    KNOWN_AT_FIELD_OR_RULE=
    caller-supplied FeatureValue.known_at; normalized and compared against
    exact forecast_cutoff_at by residual visibility

    SOURCE_AVAILABLE_AT_FIELD_OR_RULE=
    caller-supplied FeatureValue.source_available_at; normalized and compared
    against exact forecast_cutoff_at; source-class-specific provenance remains
    incomplete

`POST_CUTOFF_INPUT_REJECTED=true` remains a scoped statement that a supplied
timestamp after the exact cutoff is rejected. It is not a claim that the
source-class provenance is complete.

### P1-2 — Analytics composite availability

The realized cumulative composite remains PARTIAL. Its current
`FeatureValue.source_available_at=forecast_cutoff_at` does not prove:

    AnalyticsBuildRun.source_cutoff <= exact forecast_cutoff_at

Accordingly its row-level post-cutoff fields are false, and the gap is kept
separate from the `ANALYTICS_FACTORY_RECEIPT` taxonomy gap.

### P1-3 — Task9 upstream chain and Calendar

The evidence no longer describes all Task9 upstream sources with a single
`known_at <= exact cutoff AND source_available_at <= exact cutoff` predicate.
It explicitly records:

- exact `MaturityDailyPredictionModel.created_at` authority for Task8;
- exact timestamp rules and local-date rules from the rolling availability
  registry; and
- date-level `ParameterSourceRef.available_at <= as_of_date` validation inside
  Task9.

Because the complete mixed-policy chain is not proven as one end-to-end
authority, `AUTHORITY.TASK9_UPSTREAM_CHAIN`, the five Task9-derived rows, and
the Calendar row remain PARTIAL.

## 6. Findings remaining open

- F-003 Planning supplemental binding: require as-of plan identity/version/hash
  provenance.
- ANALYTICS_FACTORY_RECEIPT taxonomy: formally classify and accept the source
  class with its identity and visibility contract.
- ANALYTICS_REALIZED_CUMULATIVE_COMPOSITE_AVAILABILITY: carry
  `AnalyticsBuildRun.source_cutoff` into the composite or enforce an equivalent
  explicit Analytics-build availability predicate at or before the exact
  cutoff.
- TASK9_UPSTREAM_MIXED_AUTHORITY_RECONCILIATION: reconcile the exact-timestamp
  Task8 authority with Task9 local-date and source-class policies before
  promoting Task9-derived rows.

F-002 Weather supplemental binding is closed by merged PR #194. The Task8
availability and exact residual cutoff findings remain closed by PR #190 and
PR #189 respectively.

## 7. Minimum implementation gaps remaining

MINIMUM_IMPLEMENTATION_GAP_COUNT=4

    1. Require planning-specific as-of effective plan identity/version/hash provenance.
    2. Retain ANALYTICS_FACTORY_RECEIPT as an explicit evidence taxonomy gap until S1 source-class governance accepts it.
    3. Carry the authoritative AnalyticsBuildRun.source_cutoff into realized_cumulative_residual_to_as_of_kg or enforce an equivalent explicit Analytics-build availability predicate at or before exact forecast_cutoff_at.
    4. Reconcile Task9 upstream source-class visibility evidence across exact-timestamp Task8 and local-date ParameterSourceRef/availability-registry policies before promoting Task9-derived rows.

## 8. Overall result and acceptance boundary

    FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
    FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
    POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
    IMPLEMENTATION_GAP_FOUND=true
    DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true

`FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false` means this repository-only
revalidation did not observe a concrete future-valued business feature. It does
not mean all forecast-input authority is complete. The open source,
provenance, mixed-policy, Analytics taxonomy, and Analytics composite gaps
keep the audit blocked.

    SOURCE_002_USED_AS_FORECAST_INPUT=false
    SOURCE_002_REREAD=false
    REAL_SOURCE_EXPORT_READ_THIS_TASK=false
    REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false
    DATABASE_WRITE=false
    BACKTEST_EXECUTED=false
    MODEL_CHANGED=false
    MODEL_TRAINING_EXECUTED=false

    CANONICAL_GATE_STATUS_CHANGED=false
    GATE_PASS_COUNT=0
    SOURCE_AUTHORITY_ACCEPTED=false
    SOURCE_COHORT_ACCEPTED=false
    Q2C_ACCEPTED=false
    V0_3_S1_COMPLETE=false
    V0_3_S1_ACCEPTED=false
    V0_3_S2_AUTHORIZED=false
    V0_3_S2_STARTED=false

This artifact is prepared for independent review only. It is not forecast
readiness approval, S1 acceptance, or S2 authorization.

## 9. Validation

    JSON_PARSE_VALID=true
    JSON_ROW_COUNT=22
    JSON_ROW_STATUS_COUNTS_MATCH=true
    JSON_WORKPAPER_SUMMARY_MATCH=true
    MINIMUM_GAPS_MATCH=true
    TASK8_CLOSED_STATUS_MATCH=true
    EXACT_CUTOFF_CLOSED_STATUS_MATCH=true
    SUPPLEMENTAL_TIMESTAMP_SEMANTICS_MATCH_CODE=true
    REALIZED_CUMULATIVE_ANALYTICS_AVAILABILITY_MATCH_CODE=true
    TASK9_UPSTREAM_POLICY_SEMANTICS_MATCH_CODE=true
    CURRENT_MAIN_CODE_REAUDIT=PASS
    TARGETED_TEST_STATUS=PASS
    TARGETED_TEST_RESULT=60 passed
    PR192_REVALIDATION=PASS
    PR194_REVALIDATION=PASS
    PRODUCTION_CODE_CHANGED=false
    TEST_CODE_CHANGED=false
    DATABASE_WRITE=false
    BACKTEST_STARTED=false

No current-main code or tests were modified by this correction. No real
historical business backtest was executed.

## 10. Next action

    NEXT_RECOMMENDED_ACTION=RUN_POST_PR194_WEATHER_PIT_REVALIDATION_INDEPENDENT_REVIEW
