# Blueberry Peak Forecast Agent V0.3 Development Plan

## 1. Document identity and version boundary

This document freezes the V0.3 overall development plan. It is a planning and
governance artifact only. It does not implement V0.3-S1, import real business
data, train or change a model, modify production code, create a migration, or
authorize any implementation step.

```text
VERSION=0.3.0
VERSION_NAME=BUSINESS_FORECAST_PILOT
VERSION_NAME_CN=真实业务预测验证与模型优化版
V0_3_TOTAL_SLICES=6
V0_3_RELEASE_CLASS=BUSINESS_PILOT

PRIMARY_GOAL=使用真实历史数据验证、诊断并优化现有产量预测能力，形成可持续运行、评价和迭代的业务预测闭环

MULTI_FACTORY_ROUTING_IN_SCOPE=false
FACTORY_CAPACITY_OPTIMIZATION_IN_SCOPE=false
AUTOMATIC_PRODUCTION_DISPATCH_IN_SCOPE=false
```

V0.3 is a business pilot and model-validation phase. It is not a claim that
the current model has already passed real-business accuracy validation. The
pilot must produce auditable evidence before any release or expansion claim is
made.

V0.3 does not target cross-factory routing, factory scheduling, transportation
optimization, or automatic production commands. Those subjects are explicitly
out of this version boundary even when they appear as broader product context
elsewhere in the repository.

## 2. Existing capability baseline

### 2.1 V0.1 completed baseline

V0.1 established the deterministic forecast calculation and persistence chain,
including:

- complete-season daily effective-marketable-fruit forecasting;
- P50, P80, and P90 forecast ranges;
- natural maturity quantity;
- harvesting capacity;
- mature inventory;
- mature loss;
- single-day peak;
- strict consecutive-seven-natural-day cumulative peak;
- seasonal cumulative quantity;
- persistence and query;
- deterministic replay;
- PostgreSQL complete-season end-to-end coverage.

The V0.1 baseline is a technical capability baseline. It is not evidence of
real-business accuracy, business representativeness, or formal business
acceptance.

### 2.2 V0.2 completed baseline

V0.2 added the engineering trial loop, including:

- actual-harvest data import;
- CSV and XLSX import;
- validation and atomic commit;
- point-in-time actual labels;
- historical backtesting with future-data leakage protection;
- forecast-quality metrics;
- comparison with one naive baseline;
- browser Forecast page;
- forecast-versus-actual Quality page;
- CSV export;
- PostgreSQL and browser end-to-end acceptance.

```text
V0_2_RELEASE_CLASS=ENGINEERING_TRIAL
REAL_BUSINESS_ACCURACY_VALIDATED=false
REAL_BUSINESS_REPRESENTATIVENESS_VALIDATED=false
FORMAL_BUSINESS_ACCEPTANCE_COMPLETE=false
```

V0.2 proves that the engineering trial product loop can run with a versioned,
deterministic trial input generator and engineering acceptance data. It does
not prove real production forecasting accuracy, business representativeness,
formal data ownership, production-system integration, or commercial
deployment acceptance.

## 3. V0.3 business forecast loop

The V0.3 primary chain is frozen as follows:

```text
真实历史数据
→ 数据质量检查
→ 数据版本冻结
→ 历史时点输入还原
→ 当前模型历史回测
→ 误差指标计算
→ 误差来源诊断
→ 参数校准和有限模型优化
→ 候选模型公平比较
→ 正式模型版本发布
→ 真实产季持续预测
→ 实际结果回收
→ 持续误差评价和业务复盘
```

The completed V0.3 evidence package must be able to prove all of the
following:

1. The data source, physical meaning, unit, time basis, and statistical grain
   are explicit.
2. Historical data has an immutable or otherwise governed version identity and
   a reconstructable time-visibility boundary.
3. Historical backtests use only information available at the forecast cutoff.
4. The current model and a naive baseline are compared on identical labels,
   exclusions, cutoffs, horizons, and evaluation ranges.
5. Every model or parameter change has quantitative evidence and a recorded
   reason.
6. The test set remains sealed while parameters and candidates are selected.
7. The selected candidate passes an independent test or holdout evaluation.
8. A real-season business pilot is completed within a defined operational
   scope.
9. Business use, non-use, interpretation, and acceptance results are recorded.
10. Historical forecasts, source data versions, parameters, features, and
    model artifacts are traceable and reproducible.

## 4. Formal slice boundary

V0.3 has exactly six formal slices. No seventh slice may be introduced under
this plan, and cross-factory routing must not be added to any slice.

```text
V0_3_S1=REAL_BUSINESS_DATA_CONTRACT_AND_ACCEPTANCE_DATASET_FREEZE
V0_3_S2=REAL_HISTORICAL_DATA_INGESTION_AND_QUALITY_GOVERNANCE
V0_3_S3=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
V0_3_S4=PARAMETER_CALIBRATION_MODEL_OPTIMIZATION_AND_SELECTION
V0_3_S5=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
V0_3_S6=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

### 4.1 V0.3-S1 — Real business data contract and acceptance dataset freeze

```text
SLICE=V0.3-S1
ENGLISH_ID=REAL_BUSINESS_DATA_CONTRACT_AND_ACCEPTANCE_DATASET_FREEZE
MODEL_CHANGE_ALLOWED=false
PRODUCTION_MODEL_TRAINING_ALLOWED=false
FORMAL_DATA_IMPORT_AUTHORIZED=false
```

#### Objective

S1 freezes the contract and the evaluation-data identity before production
data is used for model diagnosis. It does not modify the production model,
train a model, or import a formal acceptance dataset.

#### Contract decisions

- Freeze the primary prediction target.
- Freeze the physical meaning, unit, and time basis of every target and input.
- Freeze the source system, source dataset, source version, owner role, and
  revision policy.
- Freeze the historical visibility rule used to reconstruct what was known at
  a forecast cutoff.
- Freeze inclusion, exclusion, missing-day, correction, and cancellation
  rules.
- Freeze training, validation, test, and external-holdout identities.
- Freeze the evaluation metrics and the minimum coverage required for an
  interpretable result.
- Define the dataset manifest, content hash, row-count, byte-count, and
  lineage rules.

#### Primary target and distinct quantities

```text
PRIMARY_TARGET=effective_marketable_quantity_kg
```

The implementation and reports must distinguish these quantities rather than
silently treating them as interchangeable:

```text
actual_harvest_quantity_kg
effective_marketable_quantity_kg
factory_received_quantity_kg
```

The contract must document how field sorting, processing-factory sorting,
rejection, transport loss, storage loss, and any other transformation affect
each quantity.

#### Evaluation grain and split policy

The recommended business grain is:

```text
business_date × farm × subfarm_or_plot × variety × season
```

The dataset must contain explicit and independently identifiable ranges:

```text
TRAIN
VALIDATION
TEST
EXTERNAL_HOLDOUT
```

Splits must use complete time intervals or complete seasons. Randomly splitting
adjacent daily rows is prohibited as the primary evaluation method.

#### S1 acceptance evidence

S1 is accepted only when the contract, source-owner responsibility, visibility
rule, exclusion policy, split manifest, metric definitions, and dataset hash
rules are independently reviewed. S1 acceptance does not authorize S2 data
ingestion or model work.

### 4.2 V0.3-S2 — Real historical data ingestion and quality governance

```text
SLICE=V0.3-S2
ENGLISH_ID=REAL_HISTORICAL_DATA_INGESTION_AND_QUALITY_GOVERNANCE
MODEL_CHANGE_ALLOWED=false
```

#### Objective

S2 connects the approved real historical sources to the governed ingestion and
quality pipeline while preserving raw facts and their lineage. S2 does not
change the forecast model.

#### Minimum data range

The governed source scope must address, where available and approved:

- actual harvest quantity;
- effective marketable quantity or marketable-fruit rate;
- farm, subfarm, plot, and variety identities;
- planted and productive area;
- tree age or planting date;
- expected and actual yield per mu;
- phenology dates;
- weather observations and their publication or availability time;
- picker count and harvesting efficiency;
- mature inventory and loss;
- data-entry time, revision time, cancellation time, and final-confirmation
  state.

#### Governance invariants

```text
RAW_SOURCE_IMMUTABLE=true
CLEANED_DATA_VERSIONED=true
MANUAL_CORRECTION_AUDITED=true
SILENT_VALUE_REPLACEMENT=false
SOURCE_ROW_LINEAGE_REQUIRED=true
POINT_IN_TIME_VISIBILITY_REQUIRED=true
```

Raw source rows must not be overwritten. Cleaning and correction must produce
versioned records with an auditable reason, actor role, timestamp, and source
lineage. Missing data must not be silently converted to zero. A revision is
usable in a historical forecast only when its visibility timestamp satisfies
the historical cutoff rule.

#### S2 acceptance evidence

S2 requires an immutable raw-source reference, a cleaned-data manifest, a
quality report, a correction ledger, a time-visibility report, and reproducible
training/validation/test dataset builds. S2 acceptance does not authorize S3
backtesting until those artifacts are reviewed.

### 4.3 V0.3-S3 — Current model point-in-time backtest and error diagnosis

```text
SLICE=V0.3-S3
ENGLISH_ID=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
MODEL_CHANGE_ALLOWED=false
PARAMETER_CHANGE_ALLOWED=false
```

#### Objective

S3 evaluates the current V0.2 model against the governed real historical data
using strict historical visibility. It produces an error diagnosis and a
quantified candidate-improvement backlog; it does not change the model or
parameters.

#### Backtest rules

- Reconstruct each forecast input from data visible at its historical cutoff.
- Keep the production exclusion and missing-data policies identical across the
  current model and naive baseline.
- Use the frozen training, validation, test, and external-holdout identities.
- Do not use final-season facts, future revisions, or later labels to construct
  a historical input.
- Record every unavailable, excluded, and insufficient-coverage result rather
  than silently filling it.

#### Required horizons and metrics

```text
7_DAY_HORIZON
14_DAY_HORIZON
21_DAY_HORIZON
COMPLETE_SEASON
```

At minimum, report:

- MAE;
- WAPE;
- sMAPE;
- cumulative error;
- single-day peak date error and quantity error;
- consecutive-seven-day peak date error and quantity error;
- seasonal cumulative error;
- P80 coverage;
- P90 coverage;
- interval width;
- difference from the naive baseline.

#### Error attribution matrix

Every material error must be assigned to a known category or explicitly
recorded as residual uncertainty:

```text
TOTAL_QUANTITY_ERROR
MATURITY_TIMING_ERROR
PHENOLOGY_INPUT_ERROR
WEATHER_RESPONSE_ERROR
HARVEST_CAPACITY_ERROR
MARKETABLE_RATE_ERROR
MATURE_INVENTORY_ERROR
MASTER_DATA_ERROR
DATA_QUALITY_ERROR
UNKNOWN_RESIDUAL_ERROR
```

#### S3 acceptance evidence

S3 is accepted only when the point-in-time replay, leakage audit, current-model
metrics, naive-baseline metrics, coverage report, and error-attribution matrix
are reproducible from their manifests. The output is a ranked, evidence-based
candidate list for S4, not an authorization to change the model.

### 4.4 V0.3-S4 — Parameter calibration, model optimization, and candidate selection

```text
SLICE=V0.3-S4
ENGLISH_ID=PARAMETER_CALIBRATION_MODEL_OPTIMIZATION_AND_SELECTION
```

S4 may be authorized only after S3 has been accepted. Before S3 acceptance,
no parameter or model change is in scope.

#### Optimization order

1. Calibrate data and business parameters.
2. Calibrate P80/P90 interval behavior.
3. Apply only finite model changes supported by the S3 diagnosis.

Priority candidates include:

- area;
- yield per mu;
- marketable-fruit rate;
- phenology offset;
- variety parameters;
- weather response;
- harvest efficiency;
- maturity loss;
- initial mature inventory.

Only when parameter calibration is insufficient may the candidate set consider:

- maturity-curve structure;
- variety-stratified models;
- regional-stratified models;
- weather features;
- residual features;
- residual-model retraining.

#### Fair comparison invariants

Every candidate comparison must hold the following constant:

```text
SAME_TRAIN_DATASET=true
SAME_VALIDATION_DATASET=true
SAME_TEST_DATASET=true
SAME_LABELS=true
SAME_EXCLUSION_POLICY=true
SAME_CUTOFF_POLICY=true
SAME_FORECAST_HORIZONS=true
SAME_METRICS=true
```

The test set is sealed. It must not be repeatedly used to tune parameters or
choose candidates. If the test set is opened for a final decision, the event,
reason, and consequence must be recorded and a new independent holdout must be
defined before claiming an unbiased result.

#### Candidate artifact requirements

Each candidate must have:

- dataset hash;
- feature manifest;
- parameter manifest;
- model artifact hash;
- source commit SHA;
- random seed;
- experiment result;
- release manifest;
- rollback plan.

S4 acceptance requires a fair comparison, an independent test result, a
selection rationale, and a reproducible release/rollback manifest.

### 4.5 V0.3-S5 — Business forecast operations, explanation, and continuous evaluation

```text
SLICE=V0.3-S5
ENGLISH_ID=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
```

#### Objective

S5 operates the selected formal model in the pilot workflow and keeps the
forecast-to-actual loop auditable. It addresses explanation and operations,
not cross-factory routing or automatic production control.

#### Required capabilities

The pilot surface must support:

- comparison of the current forecast with the previous forecast;
- comparison of the current model with the previous released model;
- comparison before and after calibration;
- P50/P80/P90 comparison;
- forecast-versus-actual comparison;
- current-model-versus-naive-baseline comparison;
- data-gap and data-quality risk notices;
- model and parameter version display;
- historical forecast query;
- result export;
- business adoption record;
- reason record for manual adjustment.

The service must preserve the immutability of historical forecasts. A new
forecast is an additional versioned result, not an overwrite of the previous
result.

#### Explanation rule

Structured explanations must be derived from actual input differences,
version differences, and result differences. The system must not invent a
weather, maturity, capacity, or data-quality cause that is not present in the
recorded evidence.

#### S5 acceptance evidence

S5 requires operational run records, version comparison evidence, persisted
explanation evidence, data-quality notices, forecast history, export evidence,
and a traceable record of business adoption or non-adoption.

### 4.6 V0.3-S6 — Real-season business pilot and release acceptance

```text
SLICE=V0.3-S6
ENGLISH_ID=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

#### Objective

S6 runs the selected formal model through a real season and records technical,
model, and business acceptance. S6 is the final pilot and acceptance slice,
not an authorization to expand into unrelated operational automation.

#### Minimum pilot scope

```text
FARMS>=2
VARIETIES>=2
FIXED_FORECAST_CADENCE=true
ACTUAL_RESULT_FEEDBACK_COMPLETE=true
```

The actual pilot scope, source-owner authorization, measurement boundary,
security handling, and business acceptance roles must be documented before
real business data is imported. This plan does not itself grant that
authorization.

#### Technical acceptance

Technical acceptance must cover:

- data import;
- forecast execution;
- historical result query;
- data and model traceability;
- deterministic replay;
- PostgreSQL E2E;
- browser E2E;
- full-suite CI;
- a unique Alembic head.

#### Model acceptance

Model acceptance must report:

- daily error;
- seven-day error;
- fourteen-day error;
- twenty-one-day error;
- single-day peak error;
- consecutive-seven-day peak error;
- seasonal cumulative error;
- P80 coverage;
- P90 coverage;
- improvement or regression against the current model;
- improvement or regression against the naive baseline.

#### Business acceptance

Business acceptance must record:

- whether high peaks were identified early enough;
- whether the forecast informed workforce preparation;
- whether it informed packaging preparation;
- whether it informed precooling and processing preparation;
- whether business users understood the forecast;
- whether false positives and false negatives were acceptable;
- whether the forecast was adopted;
- why it was not adopted when it was not used;
- whether the evidence supports a larger pilot.

## 5. Explicit non-scope

The following are outside V0.3. They are not optional enhancements and must
not be smuggled into a formal slice through an implementation backlog:

```text
MULTI_FACTORY_ROUTING
CROSS_FACTORY_ALLOCATION
FACTORY_CAPACITY_OPTIMIZATION
AUTOMATIC_PEAK_SHAVING
VEHICLE_ROUTING
TRANSPORT_SCHEDULING
PRECOOLING_CHAMBER_SCHEDULING
PROCESSING_LINE_SCHEDULING
REAL_TIME_ERP_INTEGRATION
REAL_TIME_IOT_INTEGRATION
AUTOMATIC_PRODUCTION_COMMANDS
COMPLEX_RBAC
APPROVAL_WORKFLOW_PLATFORM
MULTI_AGENT_EXPANSION
LLM_CHAT
COLD_STORAGE_DESIGN_OPTIMIZATION
```

In particular:

```text
MULTI_FACTORY_ROUTING_IN_SCOPE=false
FACTORY_CAPACITY_OPTIMIZATION_IN_SCOPE=false
AUTOMATIC_PRODUCTION_DISPATCH_IN_SCOPE=false
```

V0.3 may record an operational context or a manually supplied capacity
constraint when that is necessary to evaluate the forecast, but it does not
automatically route loads, allocate work across factories, schedule equipment,
or issue production commands.

## 6. Completion gate

The final completion marker is frozen as:

```text
BLUEBERRY_FORECAST_AGENT_V0_3_BUSINESS_FORECAST_PILOT_COMPLETE
```

The marker may be used only when every condition below is true. Listing a
condition here does not assert that it has been satisfied.

```text
V0_3_S1_COMPLETE=true
V0_3_S2_COMPLETE=true
V0_3_S3_COMPLETE=true
V0_3_S4_COMPLETE=true
V0_3_S5_COMPLETE=true
V0_3_S6_COMPLETE=true

REAL_DATA_CONTRACT_ACCEPTED=true
REAL_DATASET_FROZEN=true
DATA_QUALITY_GATE_PASSED=true
POINT_IN_TIME_BACKTEST_PASSED=true
CURRENT_MODEL_BASELINE_COMPLETE=true
ERROR_DIAGNOSIS_COMPLETE=true
SELECTED_MODEL_HOLDOUT_TEST_PASSED=true
MODEL_RELEASE_MANIFEST_COMPLETE=true
BUSINESS_PILOT_COMPLETED=true
BUSINESS_ACCEPTANCE_RECORDED=true
POSTGRESQL_E2E_PASSED=true
BROWSER_E2E_PASSED=true
FULL_SUITE_CI_PASSED=true
UNIQUE_ALEMBIC_HEAD=true
```

No release, production-deployment, or broader-scope claim may use the marker
while any condition is false, unverified, or only inferred from a merged code
change.

## 7. Authorization sequence and dependency gates

The slice dependency order is explicit:

```text
S1_ACCEPTED → S2_MAY_BE_AUTHORIZED
S2_ACCEPTED → S3_MAY_BE_AUTHORIZED
S3_ACCEPTED → S4_MAY_BE_AUTHORIZED
S4_ACCEPTED → S5_MAY_BE_AUTHORIZED
S5_ACCEPTED → S6_MAY_BE_AUTHORIZED
```

The arrows describe a prerequisite for a later authorization; they do not
authorize the later implementation automatically. Every slice requires a
separate scope, evidence, and authorization decision.

```text
NO_STEP_IMPLIES_THE_NEXT=true
OPEN_BACKLOG_DOES_NOT_EXTEND_VERSION_SCOPE=true
PLANNING_DOES_NOT_AUTHORIZE_IMPLEMENTATION=true
```

An open backlog item cannot expand V0.3 beyond the six formal slices. A product
or governance request that is outside this document requires an explicit
version replan before it can be considered.

## 8. Data, privacy, and reproducibility boundaries

Real business data may be used in V0.3 only after a separate authorization has
confirmed the source owner, purpose, approved dataset identity, physical
measurement boundary, historical visibility, access controls, and retention
rules. No real data is added by this planning document.

Every accepted dataset or model result must be reproducible from a stable
manifest. The manifest must identify source version, time boundary, inclusion
and exclusion rules, feature set, parameters, code commit, model artifact, and
random seed where applicable. Sensitive raw rows, credentials, personal data,
and private source URLs must not be committed to the repository.

The trial and pilot evidence must distinguish:

- engineering-flow correctness;
- statistical/model evidence;
- real-business data acceptance;
- business adoption and formal acceptance.

Passing one category does not imply passing another category.

## 9. Current authorization status

This document freezes the plan only. No V0.3 implementation is authorized by
this commit or by its Draft PR.

```text
V0_3_PLAN_FROZEN=true

V0_3_IMPLEMENTATION_AUTHORIZED=false
V0_3_S1_IMPLEMENTATION_AUTHORIZED=false
V0_3_S2_IMPLEMENTATION_AUTHORIZED=false
V0_3_S3_IMPLEMENTATION_AUTHORIZED=false
V0_3_S4_IMPLEMENTATION_AUTHORIZED=false
V0_3_S5_IMPLEMENTATION_AUTHORIZED=false
V0_3_S6_IMPLEMENTATION_AUTHORIZED=false

REAL_DATA_IMPORT_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
FRONTEND_CHANGE_AUTHORIZED=false
MULTI_FACTORY_ROUTING_AUTHORIZED=false
```

The next permitted task is a separately planned and separately authorized:

```text
NEXT_TASK=V0_3_S1
NEXT_TASK_SCOPE=REAL_BUSINESS_DATA_CONTRACT_AND_ACCEPTANCE_DATASET_FREEZE
```

That next task must not be started automatically by this plan, this branch, or
the associated Draft PR.
