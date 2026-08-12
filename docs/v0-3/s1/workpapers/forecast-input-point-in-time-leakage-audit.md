# V0.3-S1 Forecast Input Point-in-Time Leakage Audit

ARTIFACT_ID=V0_3_S1_FORECAST_INPUT_POINT_IN_TIME_LEAKAGE_AUDIT
ARTIFACT_VERSION=forecast-input-pit-leakage-audit-v2
TASK_CLASS=DOCS_ONLY_POST_TASK4_PIT_EXACT_MAIN_REVALIDATION
AUDITED_REPOSITORY_SHA=ed35995886c4494fc87b4a46687169d88b794851

TASK4_IMPLEMENTATION_PR=200
TASK4_REVIEWED_HEAD_SHA=0fc56fd225bc02d7fefec9b982057cdbe2dbce4b
TASK4_MERGE_SHA=ed35995886c4494fc87b4a46687169d88b794851
TASK4_EXACT_HEAD_CI_RUN_ID=31570670068
TASK4_EXACT_HEAD_REVIEW_ID=4913808367

This is an independent, docs-only revalidation of the merged PR #200
implementation. The PR exact-head CI validates the implementation head; this
workpaper audits the merged `main` commit shown above.

## 1. Scope and authority

The audit covers the same 22 registered forecast-input rows as the prior PIT
artifact. It rechecks current-main production code and tests after PR #200 and
does not change production code, tests, schema, databases, model artifacts, or
canonical S1 acceptance state.

The source-class-aware visibility contract is:

- exact-timestamp sources, including Task8 daily prediction, use
  `known_at <= exact forecast_cutoff_at` and
  `source_available_at <= exact forecast_cutoff_at`;
- Task9 `PARAMETER_SOURCE` and `INITIAL_INVENTORY_SNAPSHOT` use their explicit
  local available-date authority `available_at <= as_of_date`;
- Analytics features use the persisted `AnalyticsBuildRun`-derived
  `source_cutoff`, which is then checked against the exact forecast cutoff;
- no universal timestamp is claimed for every upstream source.

EXACT_FORECAST_CUTOFF_POST_CUTOFF_REJECTED=true
This is a source-class-aware result: exact-timestamp authorities use
<= exact forecast_cutoff_at, while Task9 local-date authorities use
available_at <= as_of_date; it is not a universal timestamp policy for
every source.

`SOURCE_002_RAW_READ=false`, `SOURCE_002_ROW_LEVEL_READ=false`,
`REAL_BUSINESS_DATA_READ=false`, `PRODUCTION_DATABASE_REAL_DATA_READ=false`,
`EXTERNAL_HOLDOUT_ACCESS=false`, `MODEL_TRAINING_EXECUTED=false`, and
`BACKTEST_EXECUTED=false`.

The current canonical S1 runtime remains unchanged:

    S1_VISIBILITY_CANONICAL_GATE_PASS=false
    CURRENT_CANONICAL_GATE_PASS_COUNT=0
    CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
    CANONICAL_GATE_STATUS_CHANGED=false
    AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
    V0_3_S1_COMPLETE=false
    V0_3_S1_ACCEPTED=false
    V0_3_S2_AUTHORIZED=false

PIT evidence support is not canonical S1 gate acceptance, and this workpaper
does not authorize S1-REMAINING-05, S1-REMAINING-06, or S2.

## 2. Current-main implementation evidence

### Planning supplemental authority

`backend/app/residual_model/planning_authority.py` is used by both
`training_manifest.py` and `prediction_features.py`. It reloads the explicit
`FarmSeasonVarietyPlan`, checks persisted `plan_id`, `plan_version`,
`plan_row_hash`, farm/subfarm/season/variety scope, and selects exactly one
row whose `available_at` and effective interval contain the Task9 as-of date.
Missing, unknown, mismatched, later, or multiply-effective plans fail closed.

The persisted plan does not contain `destination_factory_category`. The
caller-provided category remains the business value; only the persisted plan
identity and as-of provenance are authoritative. The closed PIT finding is
the identity/version/hash provenance contract, not a claim that the plan row
itself supplies the category.

### Analytics source-class and composite authority

`ANALYTICS_FACTORY_RECEIPT` is an explicit enum and feature source class, and
`forecast-input-pit-visibility-policy-v1` defines its persisted authority and
disallows latest/current fallback. `analytics_authority.py` is called from
both training and prediction. It reloads the explicit `AnalyticsBuildRun` and
binds `analytics_build_run_id`, `aggregation_version`, `config_hash`,
`source_max_raw_id`, and the persisted build-derived `source_cutoff`.

The binder applies to `realized_cumulative_residual_to_as_of_kg` as well as
the ordinary Analytics receipt features. A source cutoff before or equal to
the exact forecast cutoff is allowed; a later source cutoff is rejected by
the existing residual visibility predicate. The composite no longer inherits
the forecast cutoff as a substitute for its Analytics build availability.

This source-class binding is complete for this PIT evidence domain. It does
not set `SOURCE_AUTHORITY_ACCEPTED=true` and does not mutate the canonical S1
acceptance record.

### Task9 mixed authority and deterministic evidence

`task9_mixed_authority.py` preserves the legitimate split:

    TASK8_DAILY_PREDICTION=EXACT_TIMESTAMP_AUTHORITY
    PARAMETER_SOURCE=LOCAL_AVAILABLE_DATE_AUTHORITY
    INITIAL_INVENTORY_SNAPSHOT=LOCAL_AVAILABLE_DATE_AUTHORITY

Replay Task8 availability is required and is checked against the exact
forecast cutoff; equality is allowed. Local-date references must match the
Task9 as-of date and cannot be later than it. Unclassified source-reference
types fail closed. The validator produces
`v0-3-s1-task9-mixed-visibility-v1` evidence containing the Task9 run ID,
result hash, exact cutoff, as-of date, classified references, and a
repository canonical evidence hash. That evidence fragment is bound to all
five Task9-derived residual features and the Task9-derived calendar feature
in both training and prediction.

No local-date source is converted to a fabricated midnight timestamp.

### Previously closed authorities

The merged PR #190 Task8 persisted `MaturityDailyPredictionModel.created_at`
authority and the merged PR #192 residual model replay-trained authority
remain intact. The merged PR #194 Weather persisted `WeatherFeatureRun`
authority remains intact. No latest/current fallback was reintroduced.

## 3. Row-level revalidation result

The population remains exactly 22 rows. Every used row is independently
supported by current-main code and the targeted tests below; the historical
weather forecast row remains `NOT_USED`.

| Input ID | Status | Current-main authority evidence | Remaining blocker |
| --- | --- | --- | --- |
| `TASK9.structural_arrival_p50_kg` | PASS | Task9 mixed evidence; Task8 exact timestamp; residual cutoff | None |
| `TASK9.structural_arrival_p80_kg` | PASS | Task9 mixed evidence; Task8 exact timestamp; residual cutoff | None |
| `TASK9.structural_arrival_p90_kg` | PASS | Task9 mixed evidence; Task8 exact timestamp; residual cutoff | None |
| `TASK9.forecast_horizon_days` | PASS | Task9 mixed evidence; Task8 exact timestamp; residual cutoff | None |
| `TASK9.structural_cumulative_to_as_of_kg` | PASS | Task9 mixed evidence; Task8 exact timestamp; residual cutoff | None |
| `ANALYTICS.actual_receipt_lag_1d_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.actual_receipt_lag_3d_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.actual_receipt_lag_7d_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.actual_receipt_rolling_3d_mean_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.actual_receipt_rolling_7d_mean_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.actual_receipt_cumulative_to_as_of_kg` | PASS | Persisted AnalyticsBuildRun source class and source cutoff | None |
| `ANALYTICS.realized_cumulative_residual_to_as_of_kg` | PASS | Shared Analytics binder carries persisted source cutoff in training and prediction | None |
| `WEATHER.weather_7d_rainfall` | PASS | PR #194 persisted WeatherFeatureRun authority retained | None |
| `WEATHER.weather_7d_gdd` | PASS | PR #194 persisted WeatherFeatureRun authority retained | None |
| `PLANNING.destination_factory_category` | PASS | Explicit effective persisted plan identity/version/hash/scope binding | None |
| `CALENDAR.spring_festival_window_flag` | PASS | Versioned Task9 holiday snapshot plus classified local-date authority | None |
| `AUTHORITY.TASK9_UPSTREAM_CHAIN` | PASS | Exact Task8 and local-date Task9 policies are explicitly classified and hashed | None |
| `AUTHORITY.ANALYTICS_BUILD_RUN_SNAPSHOT` | PASS | Explicit `ANALYTICS_FACTORY_RECEIPT` class and persisted build identity | None |
| `AUTHORITY.WEATHER_SUPPLEMENTAL_BINDING` | PASS | Shared persisted Weather binder in training and prediction | None |
| `AUTHORITY.PLANNING_SUPPLEMENTAL_BINDING` | PASS | Shared persisted Planning binder in training and prediction | None |
| `AUTHORITY.RESIDUAL_MODEL_REQUEST_AND_ARTIFACT` | PASS | PR #192 persisted model/replay-trained authority retained | None |
| `NOT_USED.HISTORICAL_WEATHER_FORECAST` | NOT_USED | No current registered feature path | Not applicable |

Summary:

    AUDITED_INPUT_COUNT=22
    PASS_COUNT=21
    PARTIAL_COUNT=0
    BLOCKED_COUNT=0
    NOT_USED_COUNT=1
    PASS_COUNT + PARTIAL_COUNT + BLOCKED_COUNT + NOT_USED_COUNT = 22

    GAP01_PLANNING_REVALIDATION=PASS
    GAP02_ANALYTICS_TAXONOMY_REVALIDATION=PASS
    GAP03_ANALYTICS_COMPOSITE_REVALIDATION=PASS
    GAP04_TASK9_MIXED_AUTHORITY_REVALIDATION=PASS
    MINIMUM_IMPLEMENTATION_GAP_COUNT=0

`PR190_DIRECT_IMPACT_ROW_COUNT=6` and
`PR190_DIRECT_IMPACT_ROWS_PASS=6`. `TASK9_DERIVED_PASS_COUNT=6` covers the
five Task9 structural rows and the Task9-derived calendar row;
`AUTHORITY.TASK9_UPSTREAM_CHAIN` is independently PASS.

## 4. Closed finding registry

The current-main finding registry now records these closed findings:

- F-001 Task8 persisted availability — closed by PR #190.
- F-002 Weather supplemental persisted authority — closed by PR #194.
- F-003 Planning supplemental identity/version/hash provenance — closed by
  PR #200.
- F-004 Residual model artifact historical availability — closed by PR #192.
- EXACT_FORECAST_CUTOFF_NOT_PROPAGATED_TO_RESIDUAL_VISIBILITY — closed by
  PR #189.
- RESIDUAL_MODEL_ARTIFACT_HISTORICAL_AVAILABILITY_NOT_ENFORCED — closed by
  PR #192.
- ANALYTICS_FACTORY_RECEIPT_TAXONOMY — closed for this PIT evidence domain by
  PR #200; this is not canonical S1 source-authority acceptance.
- ANALYTICS_REALIZED_CUMULATIVE_COMPOSITE_AVAILABILITY — closed by PR #200.
- TASK9_UPSTREAM_MIXED_AUTHORITY_RECONCILIATION — closed by PR #200.

    OPEN_FINDINGS=NONE
    CLOSED_FINDING_COUNT=9
    MINIMUM_IMPLEMENTATION_GAP_COUNT=0

## 5. Overall PIT result and acceptance boundary

    FORECAST_INPUT_PIT_LEAKAGE_AUDIT_RESULT=PASS
    PIT_REVALIDATION_RESULT=PASS
    PIT_REVALIDATION_SUPPORTS_S1_VISIBILITY=true
    FORECAST_INPUT_FUTURE_LEAKAGE_DETECTED=false
    POTENTIAL_LEAKAGE_CONTROL_GAP_FOUND=false
    IMPLEMENTATION_GAP_FOUND=false
    DIRECT_FORECAST_READINESS_BLOCKER_EVIDENCED=false

The PASS result means all 21 used registered inputs have a current-main
source-class-aware visibility and provenance control. It does not mean every
source has an exact timestamp, and it does not issue any business or
canonical S1 acceptance.

    SOURCE_AUTHORITY_ACCEPTED=false
    SOURCE_COHORT_ACCEPTED=false
    Q2C_ACCEPTED=false
    S1_VISIBILITY_CANONICAL_GATE_PASS=false
    CURRENT_CANONICAL_GATE_PASS_COUNT=0
    CURRENT_CANONICAL_GATE_BLOCKED_COUNT=17
    CANONICAL_GATE_STATUS_CHANGED=false
    AUTHORITATIVE_ACCEPTANCE_RECORD_CHANGED=false
    V0_3_S1_COMPLETE=false
    V0_3_S1_ACCEPTED=false
    V0_3_S2_AUTHORIZED=false
    V0_3_S2_STARTED=false

## 6. Validation

    JSON_SYNTAX=PASS
    JSON_WORKPAPER_CONSISTENCY=PASS
    JSON_ROW_COUNT=22
    JSON_ROW_STATUS_COUNTS_MATCH=true
    CURRENT_MAIN_CODE_REAUDIT=PASS
    TARGETED_PIT_TESTS=PASS (15 passed)
    PLANNING_AUTHORITY_TESTS=PASS
    TASK9_TASK8_AUTHORITY_TESTS=PASS
    WEATHER_AUTHORITY_TESTS=PASS
    TARGETED_TEST_RESULT=78 passed
    POSTGRES_TARGETED_TESTS=SKIPPED_ENVIRONMENT (pg_isready unavailable locally)
    PRODUCTION_CODE_CHANGED=false
    TEST_CODE_CHANGED=false
    DATABASE_SCHEMA_CHANGED=false
    DATABASE_WRITE=false
    BACKTEST_STARTED=false
    MODEL_TRAINING_EXECUTED=false
    SOURCE_002_REREAD=false
    REAL_SOURCE_EXPORT_READ_THIS_TASK=false
    REAL_BUSINESS_ROW_LEVEL_DATA_READ_THIS_TASK=false

No files outside the two authorized evidence/workpaper files are changed by
this task. PostgreSQL targeted tests were not reported as passing because the
local environment has no available `pg_isready` command/PostgreSQL service;
the merged implementation is revalidated from current-main code and the
available targeted tests only.

## 7. Next action

    NEXT_RECOMMENDED_ACTION=RUN_EXACT_HEAD_INDEPENDENT_REVIEW_OF_POST_TASK4_PIT_REVALIDATION_PR
    S1_REMAINING_04_COMPLETE=false
    S1_REMAINING_05_AUTHORIZED=false
    S1_REMAINING_06_AUTHORIZED=false
    READY_PERFORMED=false
    MERGE_PERFORMED=false
    NO_STEP_IMPLIES_THE_NEXT=true
