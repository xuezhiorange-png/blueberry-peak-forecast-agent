# V0.3-S1 Forecast Input Point-in-Time Leakage Audit

ARTIFACT_ID=V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT
ARTIFACT_VERSION=forecast-input-pit-leakage-audit-v1
TASK_CLASS=DOCS_ONLY_POST_FIX_EVIDENCE_REVALIDATION_CORRECTION_R1
AUDITED_REPOSITORY_SHA=7b6d4e89ed528d0e9153fcfb209da16110a68e32
PREVIOUS_REVIEWED_HEAD_SHA=aa56f85f256eccdb162398c00353d4d2f61e1535
REVALIDATED_PR_189=true
REVALIDATED_PR_190=true
PR_189_MERGE_COMMIT_SHA=3cd720249ddd8e20fab65558c3ee83e57303516e
PR_190_MERGE_COMMIT_SHA=7b6d4e89ed528d0e9153fcfb209da16110a68e32

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

AUDITED_INPUT_COUNT=22
PASS_COUNT=0
PARTIAL_COUNT=21
BLOCKED_COUNT=0
NOT_USED_COUNT=1
PR190_DIRECT_IMPACT_ROW_COUNT=6
PR190_DIRECT_IMPACT_ROWS_PASS=0
TASK9_DERIVED_PASS_COUNT=0
TASK9_UPSTREAM_AUTHORITY_STATUS=PARTIAL
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

The residual builder accepts the caller-supplied `FeatureValue` for these
supplemental inputs. It does not rewrite `known_at` to the forecast cutoff.
The supplied `known_at` and `source_available_at` are normalized and compared
against the exact cutoff by residual visibility. Source-class-specific
observation, identity, version, and hash provenance remain incomplete.

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
| Weather features | 2 | PARTIAL | Caller timestamps are checked against the exact cutoff; weather-specific observation date and stable source/version/hash provenance remain unbound. |
| AUTHORITY.WEATHER_SUPPLEMENTAL_BINDING | 1 | PARTIAL | Caller timestamps are checked against the exact cutoff; weather-specific provenance remains unbound. |
| Planning feature | 1 | PARTIAL | Caller timestamps are checked against the exact cutoff; as-of selected plan identity/version/hash remains unbound. |
| AUTHORITY.PLANNING_SUPPLEMENTAL_BINDING | 1 | PARTIAL | Caller timestamps are checked against the exact cutoff; as-of selected plan provenance remains unbound. |
| AUTHORITY.RESIDUAL_MODEL_REQUEST_AND_ARTIFACT | 1 | PARTIAL | Historical model-artifact availability at or before exact cutoff is not enforced. |
| Historical weather forecast | 1 | NOT_USED | No current registered feature path. |

AUDITED_INPUT_COUNT=22
PASS_COUNT=0
PARTIAL_COUNT=21
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

- F-002 Weather supplemental binding: require weather observation date and
  stable source/version/hash provenance.
- F-003 Planning supplemental binding: require as-of plan identity/version/hash
  provenance.
- F-004 Residual model artifact historical availability: enforce artifact
  availability at or before the exact forecast cutoff.
- ANALYTICS_FACTORY_RECEIPT taxonomy: formally classify and accept the source
  class with its identity and visibility contract.
- ANALYTICS_REALIZED_CUMULATIVE_COMPOSITE_AVAILABILITY: carry
  `AnalyticsBuildRun.source_cutoff` into the composite or enforce an equivalent
  explicit Analytics-build availability predicate at or before the exact
  cutoff.
- TASK9_UPSTREAM_MIXED_AUTHORITY_RECONCILIATION: reconcile the exact-timestamp
  Task8 authority with Task9 local-date and source-class policies before
  promoting Task9-derived rows.

The Task8 availability and exact residual cutoff findings remain closed by
PR #190 and PR #189 respectively.

## 7. Minimum implementation gaps remaining

    1. Enforce historical residual model artifact availability at or before the exact forecast_cutoff_at.
    2. Require weather-specific observation date and stable source/version/hash provenance.
    3. Require planning-specific as-of effective plan identity/version/hash provenance.
    4. Retain ANALYTICS_FACTORY_RECEIPT as an explicit evidence taxonomy gap until S1 source-class governance accepts it.
    5. Carry the authoritative AnalyticsBuildRun.source_cutoff into realized_cumulative_residual_to_as_of_kg or enforce an equivalent explicit Analytics-build availability predicate at or before exact forecast_cutoff_at.
    6. Reconcile Task9 upstream source-class visibility evidence across exact-timestamp Task8 and local-date ParameterSourceRef/availability-registry policies before promoting Task9-derived rows.

## 8. Overall result and acceptance boundary

    FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
    FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
    POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
    IMPLEMENTATION_GAP_FOUND=true
    DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true

`FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false` means this repository-only
revalidation did not observe a concrete future-valued business feature. It does
not mean all forecast-input authority is complete. The open source,
provenance, mixed-policy, model-artifact, and taxonomy gaps keep the audit
blocked.

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
    TARGETED_TEST_RESULT=80 passed
    PRODUCTION_CODE_CHANGED=false
    TEST_CODE_CHANGED=false
    DATABASE_WRITE=false
    BACKTEST_STARTED=false

No current-main code or tests were modified by this correction. No real
historical business backtest was executed.

## 10. Next action

    NEXT_RECOMMENDED_ACTION=RUN_PR191_CORRECTION_R1_INDEPENDENT_REVIEW
