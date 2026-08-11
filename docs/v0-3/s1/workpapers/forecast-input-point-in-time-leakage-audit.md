# V0.3-S1 Forecast Input Point-in-Time Leakage Audit

ARTIFACT_ID=V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT
ARTIFACT_VERSION=forecast-input-pit-leakage-audit-v1
TASK_CLASS=DOCS_ONLY_POST_FIX_EVIDENCE_REVALIDATION
AUDITED_REPOSITORY_SHA=7b6d4e89ed528d0e9153fcfb209da16110a68e32
REVALIDATED_PR_189=true
REVALIDATED_PR_190=true
PR_189_MERGE_COMMIT_SHA=3cd720249ddd8e20fab65558c3ee83e57303516e
PR_190_MERGE_COMMIT_SHA=7b6d4e89ed528d0e9153fcfb209da16110a68e32
FORECAST_INPUT_POINT_IN_TIME_CONTROL_REQUIRED=true
FUTURE_INPUT_LEAKAGE_ALLOWED=false
FORECAST_INPUT_REQUIREMENT_SCOPE=USED_SOURCE_CLASSES_ONLY
SOURCE_002_ACTUAL_LABEL_MODE=IMMUTABLE_DAILY_FINAL_LABEL / IDFL_V1
SOURCE_002_RECENT_ACTUAL_HARVEST_USED_AS_FEATURE=false
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
TASK8_DAILY_PERSISTED_AVAILABILITY_AUTHORITY_PROVEN=true
TASK8_CALLER_OMISSION_BYPASS_CLOSED=true
TASK8_POST_CUTOFF_DB_ROW_REJECTED=true
TASK8_AVAILABILITY_FINDING_CLOSED=true
EXACT_CUTOFF_FINDING_CLOSED=true
AUDITED_INPUT_COUNT=22
PASS_COUNT=7
PARTIAL_COUNT=14
BLOCKED_COUNT=0
NOT_USED_COUNT=1
FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
IMPLEMENTATION_GAP_FOUND=true
DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true

## 1. Scope and authority

This is a documentation-only current-main revalidation. It absorbs the
merged PR #189 exact-cutoff fix and PR #190 Task8 persisted-availability fix.
It does not modify production code, tests, schemas, databases, models, or
canonical S1 acceptance state. It does not read Source 002 or run a real
business backtest.

The forecast-input visibility predicate for replay is:

    KNOWN_AT <= FORECAST_CUTOFF_AT
    SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT

For replay, FORECAST_CUTOFF_AT is the normalized persisted
HarvestStateRun.forecast_effective_cutoff_at. A legacy UTC end-of-day
compatibility cutoff is available only for non-replay runs without persisted
cutoff metadata. It is not a replay fallback.

## 2. Current-main implementation evidence

### PR #189 — exact residual feature cutoff

Current main contains:

- backend/app/residual_model/forecast_cutoff.py, which resolves the persisted
  exact replay cutoff and fails closed when a replay cutoff is missing;
- backend/app/residual_model/visibility.py, which normalizes the exact cutoff
  and rejects known_at or source_available_at after it;
- backend/app/residual_model/prediction_features.py and
  backend/app/residual_model/training_manifest.py, which pass the resolved
  cutoff into prediction and training visibility audits.

The current tests prove replay exact timestamp resolution, fail-closed replay
when the cutoff is missing, non-replay legacy EOD compatibility, same-day
post-cutoff rejection, equality acceptance, and exact-cutoff use by prediction
and training paths.

The former
EXACT_FORECAST_CUTOFF_NOT_PROPAGATED_TO_RESIDUAL_VISIBILITY finding is closed
by PR #189.

### PR #190 — Task8 persisted availability

Current main contains:

- backend/app/harvest_state/application.py, which sends the exact replay
  requirement and cutoff into the Task8 binder;
- backend/app/harvest_state/authority_request_loader.py, which loads the
  persisted MaturityDailyPredictionModel, uses its created_at as the
  authoritative Task8 daily availability timestamp, rejects caller omission
  in exact replay, rejects caller timestamp mismatches, and rejects a
  persisted daily row after the exact cutoff;
- backend/app/rolling_backtest/replay_pipeline.py, which explicitly passes
  require_persisted_task8_availability=true and node.forecast_cutoff_at.

The current tests prove caller omission injection, timestamp parity,
caller-tamper rejection, post-cutoff rejection, equality acceptance, pinned
authority preservation, and replay dispatch propagation.

The former Task8 availability finding is closed by PR #190.

## 3. Row-level revalidation result

The machine-readable artifact contains exactly 22 rows:

| Input group | Rows | Status | Remaining reason |
| --- | ---: | --- | --- |
| TASK9 structural outputs | 5 | PASS | Persisted Task8 availability and exact cutoff are bound and checked. |
| AUTHORITY.TASK9_UPSTREAM_CHAIN | 1 | PASS | Task8 persisted created_at is bound into trusted Task9 evidence and checked against the exact cutoff. |
| Calendar | 1 | PASS | Versioned/hash-bound Task9 holiday snapshot uses exact residual visibility cutoff. |
| Analytics features | 7 | PARTIAL | Exact cutoff control is present; ANALYTICS_FACTORY_RECEIPT remains an unaccepted S1 source-class taxonomy. |
| AUTHORITY.ANALYTICS_BUILD_RUN_SNAPSHOT | 1 | PARTIAL | Exact source cutoff control is present; source-class taxonomy remains unaccepted. |
| Weather features | 2 | PARTIAL | Weather-specific observation date and stable source/version/hash provenance remain unbound. |
| AUTHORITY.WEATHER_SUPPLEMENTAL_BINDING | 1 | PARTIAL | Weather-specific provenance remains unbound. |
| Planning feature | 1 | PARTIAL | As-of selected plan identity/version/hash remains unbound. |
| AUTHORITY.PLANNING_SUPPLEMENTAL_BINDING | 1 | PARTIAL | As-of selected plan provenance remains unbound. |
| AUTHORITY.RESIDUAL_MODEL_REQUEST_AND_ARTIFACT | 1 | PARTIAL | Historical model-artifact availability at or before exact cutoff is not enforced. |
| Historical weather forecast | 1 | NOT_USED | No current registered feature path. |

AUDITED_INPUT_COUNT=22
PASS_COUNT=7
PARTIAL_COUNT=14
BLOCKED_COUNT=0
NOT_USED_COUNT=1
PR190_DIRECT_IMPACT_ROW_COUNT=6
PR190_DIRECT_IMPACT_ROWS_PASS=6
CALENDAR_ROW_PROMOTED_TO_PASS=true

The six PR #190 direct-impact rows are:

    TASK9.structural_arrival_p50_kg
    TASK9.structural_arrival_p80_kg
    TASK9.structural_arrival_p90_kg
    TASK9.forecast_horizon_days
    TASK9.structural_cumulative_to_as_of_kg
    AUTHORITY.TASK9_UPSTREAM_CHAIN

## 4. Findings

### F-001 — Task8 availability authority

    STATUS=PASS
    CLOSED=true
    CLOSED_BY_PR=190
    CLOSED_BY_MERGE_COMMIT=7b6d4e89ed528d0e9153fcfb209da16110a68e32

Exact replay cannot bypass database authority by omitting caller availability
fields. The trusted path binds MaturityDailyPredictionModel.created_at,
requires duplicate caller evidence to match it, and checks it against the
exact forecast cutoff.

### Exact residual cutoff propagation

    STATUS=CLOSED
    CLOSED=true
    CLOSED_BY_PR=189
    CLOSED_BY_MERGE_COMMIT=3cd720249ddd8e20fab65558c3ee83e57303516e

Replay uses HarvestStateRun.forecast_effective_cutoff_at, and residual
visibility rejects known_at and source_available_at after that timestamp.
Equality remains allowed. Legacy EOD behavior is retained only for the
non-replay compatibility case described above.

### Remaining open findings

The following remain open and are not closed by either merged fix:

- F-002 Weather supplemental binding: require weather observation date and
  stable source/version/hash provenance.
- F-003 Planning supplemental binding: require as-of plan
  identity/version/hash provenance.
- F-004 Residual model artifact historical availability: enforce model
  artifact availability at or before the exact forecast cutoff.
- ANALYTICS_FACTORY_RECEIPT taxonomy: retain as an explicit gap until S1
  source-class governance accepts it.

## 5. Minimum implementation gaps remaining

    1. Enforce historical residual model artifact availability at or before the exact forecast_cutoff_at.
    2. Require weather-specific observation date and stable source/version/hash provenance.
    3. Require planning-specific as-of effective plan identity/version/hash provenance.
    4. Retain ANALYTICS_FACTORY_RECEIPT as an explicit evidence taxonomy gap until S1 source-class governance accepts it.

These four items exactly match minimum_implementation_gaps in the
machine-readable artifact. The former Task8 availability and exact residual
cutoff propagation gaps are not repeated.

## 6. Overall result

    FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=BLOCKED
    FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
    POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=true
    IMPLEMENTATION_GAP_FOUND=true
    DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=true

FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false means this repository-only
revalidation did not observe a concrete future-valued business feature. It
does not mean all forecast-input authority is complete; the four remaining
source/provenance/model/taxonomy gaps keep the audit blocked.

## 7. Source 002 and acceptance boundary

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

## 8. Validation

    JSON_PARSE_VALID=true
    JSON_ROW_STATUS_COUNTS_MATCH=true
    JSON_WORKPAPER_SUMMARY_MATCH=true
    MINIMUM_GAPS_MATCH=true
    CURRENT_MAIN_CODE_REAUDIT=PASS
    TARGETED_TEST_STATUS=PASS
    TARGETED_TEST_RESULT=80 passed
    PRODUCTION_CODE_CHANGED=false
    TEST_CODE_CHANGED=false
    DATABASE_WRITE=false
    BACKTEST_STARTED=false

The targeted current-main test set covered forecast-cutoff resolution,
residual visibility, prediction/training feature paths, Task8 persisted
availability, rolling replay Task8 authority, replay dispatch, and related
provenance. No real historical business backtest was executed.

## 9. Next action

    NEXT_RECOMMENDED_ACTION=RUN_FORECAST_INPUT_PIT_POST_FIX_REVALIDATION_R1_INDEPENDENT_REVIEW
