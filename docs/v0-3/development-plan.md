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

### Machine-readable field semantics

Every machine-readable field in this plan is interpreted in exactly one of the
following namespaces:

```text
MACHINE_READABLE_FIELD_SEMANTICS_VERSION=v0.3-plan-r4-v1
CURRENT_FIELD_NAMESPACE=CURRENT_<STATE_NAME>
FUTURE_ACCEPTANCE_REQUIREMENT_NAMESPACE=<SLICE>_ACCEPTANCE_REQUIRES_<CONDITION>
SCHEMA_INVARIANT_NAMESPACE=<INVARIANT_NAME>
CONDITIONAL_EXAMPLE_NAMESPACE=WHEN_<CONDITION>
UNPREFIXED_UNEXECUTED_COMPLETION_TRUE_FORBIDDEN=true
```

`CURRENT_` fields are the only current-state assertions. Fields beginning with
`*_ACCEPTANCE_REQUIRES_*` are requirements for a future acceptance decision;
they do not assert that the requirement has passed. Schema invariants describe
rules that must remain true and do not prove slice completion. A
`WHEN_<CONDITION>:` block is a conditional example that becomes applicable only
after the condition and its independent authorization are satisfied. An
unprefixed `..._COMPLETE=true` or `..._FROZEN=true` field is never used to
claim completion of future work.

The following are schema-audit invariants, not acceptance results. Source-field
names in this plan are invariants describing a future artifact schema; they do
not assert that the source artifact currently exists or has passed review.

```text
CURRENT_STATE_FIELDS_NAMESPACED=true
SOURCE_SCHEMA_FIELDS_ARE_INVARIANTS_NOT_CURRENT_ACCEPTANCE_RESULTS=true
UNCLASSIFIED_MACHINE_READABLE_FIELD_COUNT=0
AMBIGUOUS_FALSE_STATE_COUNT=0
NAKED_FUTURE_COMPLETE_TRUE_COUNT=0
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
CURRENT_REAL_BUSINESS_ACCURACY_VALIDATED=false
CURRENT_REAL_BUSINESS_REPRESENTATIVENESS_VALIDATED=false
CURRENT_FORMAL_BUSINESS_ACCEPTANCE_COMPLETE=false
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
→ 锁定候选模型
→ 独立测试
→ 批准试点模型版本
→ 建立试点运行能力
→ 真实产季业务试点
→ 业务试点验收
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
V0_3_S1=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
V0_3_S2=REAL_HISTORICAL_DATA_INGESTION_GOVERNANCE_AND_MATERIALIZED_DATASET_FREEZE
V0_3_S3=CURRENT_MODEL_POINT_IN_TIME_BACKTEST_AND_ERROR_DIAGNOSIS
V0_3_S4=PARAMETER_CALIBRATION_MODEL_OPTIMIZATION_AND_SELECTION
V0_3_S5=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
V0_3_S6=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

### 4.1 V0.3-S1 — Real business data contract and source cohort freeze

```text
SLICE=V0.3-S1
ENGLISH_ID=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
MODEL_CHANGE_ALLOWED=false
PRODUCTION_MODEL_TRAINING_ALLOWED=false
FORMAL_DATA_IMPORT_AUTHORIZED=false
```

#### Objective

S1 freezes the contract and the source-cohort identity before production data is
used for model diagnosis. It does not modify the production model, train a
model, or import a formal acceptance dataset. S1 does not claim that the final
cleaned row-level dataset has already been frozen.

#### Contract decisions

- Freeze the target-decision rule and defer the final physical target decision
  until the Q2C acceptance described below.
- Freeze the physical meaning, unit, and time basis of every target and input.
- Freeze the source system, source dataset, source version, owner role, and
  revision policy.
- Freeze the historical visibility rule used to reconstruct what was known at
  a forecast cutoff.
- Freeze inclusion, exclusion, missing-day, correction, and cancellation
  rules.
- Freeze the source file/table cohort and the split-construction policy. The
  final materialized row-level split identities are accepted only after S2
  cleaning and lineage reconciliation.
- Freeze the evaluation metrics and the minimum coverage required for an
  interpretable result.
- Freeze data-quality gates, data custody and access boundaries, and the
  source-cohort manifest, source-level version identity, and hash rules.

#### Primary target and distinct quantities

```text
PRIMARY_TARGET_STATUS=UNRESOLVED_PENDING_V0_3_S1_Q2C_ACCEPTANCE

CURRENT_OBSERVED_LABEL=actual_harvest_quantity_kg
CURRENT_OBSERVED_LABEL_PHYSICAL_BOUNDARY=FARM_PICK
CURRENT_OBSERVED_LABEL_MEASUREMENT=OBSERVED_WEIGHT
CURRENT_OBSERVED_LABEL_UNIT=KG

CURRENT_CORE_FORECAST_OUTPUT=effective_marketable_quantity_kg

PHYSICAL_EQUIVALENCE_ASSUMED=false
SILENT_TARGET_SUBSTITUTION_ALLOWED=false
```

The implementation and reports must distinguish these quantities rather than
silently treating them as interchangeable:

```text
actual_harvest_quantity_kg
effective_marketable_quantity_kg
factory_received_quantity_kg
```

The current Actual Harvest label and the Core Forecast effective marketable
quantity are not automatically equivalent. V0.3 must not directly evaluate
`effective_marketable_quantity_kg` with `actual_harvest_quantity_kg` until the
physical boundary is accepted. Field sorting, processing-factory sorting,
rejection, transport loss, storage loss, and every other transformation must be
explicitly documented rather than silently inferred.

S1 must select and independently accept exactly one target path:

```text
TARGET_DECISION=OBSERVED_FARM_PICK_QUANTITY
```

or:

```text
TARGET_DECISION=VERSIONED_Q2C_TRANSFORMATION
```

The observed FARM_PICK path must explain how the existing forecast output is
aligned to the same physical boundary. A Q2C transformation path must freeze
the input and output quantities, field and factory sorting, rejection,
transport and storage loss, marketable-rate policy, date basis, grain, source,
version, availability time, manifest, hash, owner role, and scope. Until one
path is accepted:

```text
PHYSICALLY_ALIGNED_BACKTEST_ALLOWED=false
MODEL_QUALITY_CLAIM_ALLOWED=false
```

#### Evaluation grain and split policy

The canonical evaluation grain is:

```text
CANONICAL_EVALUATION_GRAIN=SEASON × FARM × SUBFARM × VARIETY × HARVEST_BUSINESS_DATE
PLOT_SUPPORTED=false
```

`SUBFARM` and `PLOT` are not interchangeable alternatives. Plot-level support
is outside the default V0.3 contract. A future plot contract requires separate
identity, aggregation, label, and compatibility rules and separate
authorization.

The required dataset split policy is:

```text
REQUIRED_DATASET_SPLITS=TRAIN,VALIDATION,TEST
EXTERNAL_HOLDOUT_POLICY=CONDITIONAL_ON_S1_FEASIBILITY_GATE
```

Splits must use complete time intervals or complete seasons. Randomly splitting
adjacent daily rows is prohibited as the primary evaluation method.

S1 must assess complete-season count, farm and variety coverage, time span,
data completeness, point-in-time reconstructability, and canonical-grain
coverage before deciding whether an external holdout is feasible. If an
independent TEST cannot be constructed, independent model-release evaluation
and pilot approval are not allowed.

#### S1 acceptance evidence

S1 is accepted only when the target decision rule, contract, source-owner
responsibility, visibility rule, exclusion policy, split policy, metric
definitions, minimum coverage, data-custody boundary, and source-cohort hash
rules are independently reviewed. S1 acceptance does not authorize S2 data
ingestion or model work.

```text
CURRENT_S1_FINAL_CLEAN_ROWSET_FROZEN=false
CURRENT_S1_MATERIALIZED_DATASET_HASH_AVAILABLE=false
```

### 4.2 V0.3-S2 — Real historical data ingestion, governance, and materialized dataset freeze

```text
SLICE=V0.3-S2
ENGLISH_ID=REAL_HISTORICAL_DATA_INGESTION_GOVERNANCE_AND_MATERIALIZED_DATASET_FREEZE
MODEL_CHANGE_ALLOWED=false
```

#### Objective

S2 connects the approved real historical sources to the governed ingestion and
quality pipeline while preserving raw facts and their lineage. S2 materializes
the final datasets only after cleaning, correction, exclusion, and visibility
decisions. S2 does not change the forecast model.

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

#### S2 responsibilities and acceptance evidence

S2 requires an immutable raw-source reference, a cleaned-data manifest, a
quality report, a correction ledger, a time-visibility report, reproducible
TRAIN/VALIDATION/TEST dataset builds, and a conditional EXTERNAL_HOLDOUT build
when S1 found it feasible. It must also record final row count, byte count,
content hashes, and the exclusion/correction lineage for every materialized
dataset.

S2 must complete final split re-acceptance after materialization. S2 acceptance
does not authorize S3 backtesting until those artifacts are reviewed and the
following independent gate is accepted:

```text
S2_ACCEPTANCE_REQUIRES_MATERIALIZED_DATASET_FREEZE_COMPLETE=true
S2_ACCEPTANCE_REQUIRES_FINAL_SPLIT_MANIFEST_ACCEPTED=true
S2_ACCEPTANCE_REQUIRES_FINAL_DATASET_HASHES_ACCEPTED=true
S2_ACCEPTANCE_MAY_AUTHORIZE_S3_BACKTEST=true
```

The final S2 gate is not an implementation authorization for S3.

### 4.3 Historical time-visibility and winner contract

V0.3 adopts the existing Q2A/I7 and Q2C visibility semantics. It must not
compress all source timing into one generic `available_at` field.

```text
FORECAST_CUTOFF_AT
LABEL_OBSERVATION_CUTOFF_AT
SNAPSHOT_EXECUTED_AT
SOURCE_RECORDED_AT
SOURCE_AVAILABLE_AT
SOURCE_REVISED_AT
SOURCE_FINALIZED_AT
SOURCE_CANCELLED_AT
```

Forecast inputs may be used only when:

```text
SOURCE_AVAILABLE_AT <= FORECAST_CUTOFF_AT
```

Actual labels must follow the existing I7/Q2C committed-state, finalized-state,
cancellation, revision-winner, terminal-lineage, deterministic tie-break, and
no-latest-row-fallback rules. Forecast-input visibility and label-observation
visibility are separate boundaries and must not be substituted for one another.

S1 must define source-specific rules for actual harvest labels, area, yield
plans, phenology, weather observations, historical weather forecasts, picker
count, harvesting efficiency, marketable rate, manual corrections, and canceled
or voided records. In particular:

- a post-season final yield may not enter a pre-season forecast input;
- a retrospectively entered phenology value may not enter an earlier forecast;
- complete post-event weather observations may not replace the weather
  forecast visible at the historical cutoff;
- post-season marketable-rate aggregates may not enter pre-season inputs;
- final test labels may use final values, but test inputs may not use future
  final values.

Any source whose historical visibility cannot be reconstructed must be marked:

```text
SOURCE_POINT_IN_TIME_ELIGIBLE=false
```

That source must be excluded from the historical input or make the relevant
backtest instance `BLOCKED`.

### 4.4 V0.3-S3 — Current model point-in-time backtest and error diagnosis

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
parameters. S3 must remain blocked until the Q2C target path and S2 materialized
dataset gate are accepted.

#### Current S3 computability and quantile state

The current S3 authority is not treated as evidence that the V0.3 acceptance
requirements have already passed. Its exact current states are:

```text
CURRENT_S3_DAILY_ROWSET_CONTRACT_STATUS=NOT_AVAILABLE_FROM_CURRENT_S2_BINDING
CURRENT_S3_DAILY_ROWSET_AMENDMENT_COMPLETE=true
S3_A_ROWSET_MATERIALIZATION_AUTHORIZED=true
S3_A_COMPLETENESS_VERIFICATION_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_REGISTRY_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_REGISTRY_IMPLEMENTATION_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_BINDING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_EVALUATION_INSTANCE_CATALOG_ARTIFACT_PRODUCTION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
TEST_REMAINS_SEALED=true
S3_A2_S2_IDENTITY_ALIGNMENT_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
COMPLETENESS_VERIFICATION_STATUS=NOT_PERFORMED
DETERMINISTIC_DAILY_ROWSET_SERVICE_IMPLEMENTED=true
DETERMINISTIC_COMPLETENESS_VERIFICATION_SERVICE_IMPLEMENTED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_BINDING_SERVICE_IMPLEMENTED=true
DETERMINISTIC_EVALUATION_INSTANCE_CATALOG_ARTIFACT_SERVICE_IMPLEMENTED=true
CURRENT_P50_SEMANTICS_VERIFIED=false
CURRENT_P80_SEMANTICS_VERIFIED=false
CURRENT_P90_SEMANTICS_VERIFIED=false
CURRENT_P50_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P90_SEMANTICS_STATUS=NOT_VERIFIED
CURRENT_P80_COVERAGE_COMPUTABLE=false
CURRENT_P90_COVERAGE_COMPUTABLE=false
CURRENT_BASELINE_P80_COMPUTABLE=false
CURRENT_BASELINE_P90_COMPUTABLE=false
CURRENT_UNVERIFIED_QUANTILE_STATUS=NOT_VERIFIED
CURRENT_UNCOMPUTABLE_METRIC_STATUS=NOT_COMPUTABLE
CURRENT_S3_DAILY_ROWSET_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
CURRENT_QUANTILE_REASON_CODE=QUANTILE_SEMANTICS_NOT_VERIFIED
CURRENT_BASELINE_QUANTILE_REASON_CODE=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
SOURCE_002_ROW_LEVEL_READ=false
```

The future S3 acceptance gates are prerequisites, not current completion
claims:

```text
S3_ACCEPTANCE_REQUIRES_DAILY_ROWSET_AMENDMENT_COMPLETE=true
S3_ACCEPTANCE_REQUIRES_DAILY_ROWSET_COMPLETENESS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P50_SEMANTICS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P80_SEMANTICS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P90_SEMANTICS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P80_COVERAGE_P50_P80_P90_SEMANTICS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P90_COVERAGE_P50_P80_P90_SEMANTICS_VERIFIED=true
S3_ACCEPTANCE_REQUIRES_P80_COVERAGE_VALID_DENOMINATOR=true
S3_ACCEPTANCE_REQUIRES_P90_COVERAGE_VALID_DENOMINATOR=true
S3_ACCEPTANCE_REQUIRES_QUANTILE_SEMANTICS_VERIFICATION=true
S3_ACCEPTANCE_REQUIRES_BASELINE_QUANTILE_BOUNDARY=true
CURRENT_P80_COVERAGE_RELEASE_ELIGIBLE=false
CURRENT_P90_COVERAGE_RELEASE_ELIGIBLE=false
CURRENT_BASELINE_P80_COMPARISON_RELEASE_ELIGIBLE=false
CURRENT_BASELINE_P90_COMPARISON_RELEASE_ELIGIBLE=false
CURRENT_QUANTILE_CALIBRATION_ACCEPTANCE_ELIGIBLE=false
```

The current S3 result must fail closed: `NOT_VERIFIED` is not `PASS`,
`NOT_COMPUTABLE` is not zero, and a missing daily row is not silently filled.
No coverage pass, baseline-quantile superiority claim, or quantile-calibration
pass may be published before the corresponding authority gates pass.

The following computability mapping is bound to the named S3 sections and
formal reason codes. Coverage is not computable unless all three quantile
semantics, the Q2C physical alignment decision, exact actual/forecast pairing,
and a valid coverage denominator are accepted. A complete daily row set is not
a coverage prerequisite because the formal S3 contract permits coverage over
valid paired sparse binding rows. The mapping distinguishes an upper quantile
spread from a prediction-interval width: `P80-P50` and `P90-P50` are upper
spreads, so no lower-bound reason is valid for either field.

```text
COVERAGE_REQUIRES_COMPLETE_DAILY_ROW_SET=false
PEAK_AND_COMPLETE_HORIZON_METRICS_MAY_REQUIRE_COMPLETE_DAILY_ROW_SET=true
P80_COVERAGE_DAILY_ROWSET_PREREQUISITE_OCCURRENCES=0
P90_COVERAGE_DAILY_ROWSET_PREREQUISITE_OCCURRENCES=0
```

```text
metric_id=P80_COVERAGE
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;Q2C_PHYSICAL_ALIGNMENT_ACCEPTED=true;ACTUAL_FORECAST_PAIRING_ACCEPTED=true;VALID_COVERAGE_DENOMINATOR_AVAILABLE=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§10_and_§11.3
release_eligible=false

metric_id=P90_COVERAGE
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;Q2C_PHYSICAL_ALIGNMENT_ACCEPTED=true;ACTUAL_FORECAST_PAIRING_ACCEPTED=true;VALID_COVERAGE_DENOMINATOR_AVAILABLE=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§10_and_§11.3
release_eligible=false

metric_id=P80_UPPER_QUANTILE_SPREAD
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§10
release_eligible=false

metric_id=P90_UPPER_QUANTILE_SPREAD
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§10
release_eligible=false

metric_id=BASELINE_P80
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_COMPUTABLE
computability_prerequisites=BASELINE_QUANTILE_DISTRIBUTION_DEFINED
unverified_status=NOT_COMPUTABLE
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§15_and_§16.4
release_eligible=false

metric_id=BASELINE_P90
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_COMPUTABLE
computability_prerequisites=BASELINE_QUANTILE_DISTRIBUTION_DEFINED
unverified_status=NOT_COMPUTABLE
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§15_and_§16.4
release_eligible=false

metric_id=QUANTILE_CALIBRATION
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=P50_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P80_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;P90_SEMANTICS_STATUS=VERIFIED_TRUE_UPPER_QUANTILE;VALID_COVERAGE_DENOMINATORS=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=QUANTILE_SEMANTICS_NOT_VERIFIED
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§10_and_§10.1
release_eligible=false

metric_id=SINGLE_DAY_PEAK
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=COMPLETE_DAILY_ROW_SET_AVAILABLE=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§2_and_§9.1
release_eligible=false

metric_id=SUSTAINED_7DAY_PEAK
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=COMPLETE_DAILY_ROW_SET_AVAILABLE=true;COMPLETE_7DAY_WINDOW_AVAILABLE=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§2_and_§9.2
release_eligible=false

metric_id=ROLLING_COMPARISON
current_computability=NOT_COMPUTABLE
current_semantics_status=NOT_VERIFIED
computability_prerequisites=COMPLETE_DAILY_ROW_SET_AVAILABLE=true;COMPARISON_GROUP_READINESS=true
unverified_status=NOT_VERIFIED
not_computable_status=NOT_COMPUTABLE
authoritative_reason_code=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
reason_code_status=VERIFIED_FORMAL_S3_CONTRACT
authority_path=docs/forecast-quality/s3-quality-metrics-contract.md
authority_section=§2_and_§16.5
release_eligible=false
```

The upper-spread definitions are explicit and do not request a lower quantile:

```text
P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
P90_UPPER_QUANTILE_SPREAD_IS_PREDICTION_INTERVAL_WIDTH=false
P80_UPPER_QUANTILE_SPREAD_REASON_CODE_STATUS=VERIFIED_FORMAL_S3_CONTRACT
P90_UPPER_QUANTILE_SPREAD_REASON_CODE_STATUS=VERIFIED_FORMAL_S3_CONTRACT
LOWER_QUANTILE_BOUND_REQUIRED=false
AUTHORITY_REASON_CODES_VERIFIED=true
UNRESOLVED_REASON_CODE_COUNT=0
```

The S3 contract uses `NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE` only for a
prediction-interval-width result. It is not a valid status or reason for either
upper spread. The formal upper-spread fail-closed reason before quantile
semantics verification is `QUANTILE_SEMANTICS_NOT_VERIFIED`.

The sustained-seven-day metric has two ordered, mutually exclusive blockers:

```text
SUSTAINED_7DAY_STAGE_ORDER=ROWSET_AVAILABILITY_THEN_WINDOW_AVAILABILITY
SUSTAINED_7DAY_STAGE_2_ALLOWED_ONLY_AFTER_STAGE_1_PASS=true
SUSTAINED_7DAY_STAGE_REASONS_MUTUALLY_EXCLUSIVE=true
WHEN_COMPLETE_DAILY_ROW_SET_UNAVAILABLE:
SUSTAINED_7DAY_PEAK_STATUS=NOT_COMPUTABLE
SUSTAINED_7DAY_PEAK_REASON_CODE=COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING
WHEN_COMPLETE_DAILY_ROW_SET_AVAILABLE_BUT_NO_COMPLETE_7DAY_WINDOW:
SUSTAINED_7DAY_PEAK_STATUS=NOT_COMPUTABLE
SUSTAINED_7DAY_PEAK_REASON_CODE=NO_COMPLETE_7DAY_WINDOW
```

The second condition is evaluated only after the first condition has passed; a
missing row set is never relabeled as a missing seven-day window.

#### Backtest rules

- Reconstruct each forecast input from data visible at its historical cutoff.
- Keep the production exclusion and missing-data policies identical across the
  current model and naive baseline.
- Use the final S2-accepted TRAIN, VALIDATION, and TEST identities. Use an
  EXTERNAL_HOLDOUT only when S1 declared it feasible and S2 materialized it.
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

At minimum, report the versioned metric contract described below. Generic
metric names are not accepted as result identifiers:

- `daily_mae`;
- `daily_wape`;
- `daily_smape`;
- `cumulative_signed_error_kg`;
- `cumulative_absolute_error_kg`;
- `cumulative_signed_relative_error`;
- `cumulative_absolute_relative_error`;
- `single_day_peak_date_signed_error_days_q`;
- `single_day_peak_date_absolute_error_days_q`;
- `single_day_peak_quantity_signed_error_kg_q`;
- `single_day_peak_quantity_absolute_error_kg_q`;
- `sustained_7day_start_date_signed_error_days_q`;
- `sustained_7day_start_date_absolute_error_days_q`;
- `sustained_7day_quantity_signed_error_kg_q`;
- `sustained_7day_quantity_absolute_error_kg_q`;
- `P80_COVERAGE` and `P90_COVERAGE`;
- `P80_UPPER_QUANTILE_SPREAD` and `P90_UPPER_QUANTILE_SPREAD`;
- the explicitly versioned naive-baseline comparison fields.

#### Error attribution matrix

Error attribution has two layers and is not a strict causal decomposition.
Multiple candidate causes are allowed, and unexplained residuals must remain
visible.

```text
QUANTITY_LEVEL_ERROR
MATURITY_TIMING_ERROR
SINGLE_DAY_PEAK_ERROR
SEVEN_DAY_PEAK_ERROR
SEASON_CUMULATIVE_QUANTITY_ERROR
QUANTILE_CALIBRATION_ERROR
```

```text
PHENOLOGY_INPUT
WEATHER_RESPONSE
HARVEST_CAPACITY
MARKETABLE_RATE
MATURE_INVENTORY
MASTER_DATA
DATA_QUALITY
UNKNOWN_RESIDUAL

MULTI_LABEL_ATTRIBUTION=true
```

Each attribution records `attribution_id`, `error_instance_id`,
`error_dimension`, `candidate_cause`, `attribution_method`,
`evidence_reference`, `counterfactual_run_id`, `estimated_contribution_status`,
`estimated_contribution`, `not_computable_reason`, `confidence_class`,
`reviewer`, and `reviewed_at`. Permitted methods are
`RULE_BASED_DIAGNOSIS`, `SOURCE_CORRECTION_COMPARISON`,
`COUNTERFACTUAL_RERUN`, `ABLATION_EXPERIMENT`, and
`MANUAL_EXPERT_REVIEW`. Manual review is auditable but cannot alone authorize a
model change.

The contribution fields are fail-closed:

```text
estimated_contribution_status=COMPUTED|NOT_COMPUTABLE
```

```text
estimated_contribution_status=COMPUTED
→ estimated_contribution has a value
→ not_computable_reason is empty

estimated_contribution_status=NOT_COMPUTABLE
→ estimated_contribution is empty
→ not_computable_reason is non-empty
```

The value zero is never used to mean that a contribution could not be
computed. Multiple labels may describe one error instance and may overlap:

```text
MULTI_LABEL_CONTRIBUTIONS_MUTUALLY_EXCLUSIVE=false
MULTI_LABEL_CONTRIBUTIONS_MAY_OVERLAP=true
MULTI_LABEL_CONTRIBUTIONS_SUM_TO_100_PERCENT_REQUIRED=false
MULTI_LABEL_CONTRIBUTIONS_CAUSAL_DECOMPOSITION=false
```

Each contribution is a local estimate under its recorded method. Contributions
are not summed or normalized to 100 percent, a `NOT_COMPUTABLE` contribution
does not remove the diagnostic label, and manual review cannot fabricate a
numeric contribution.

#### Attribution measure contract

An attribution method does not define a universal unit. Every contribution
record must bind its value to a measure contract before a numeric value can be
used:

```text
contribution_measure_id
contribution_unit
contribution_value_domain
contribution_sign_policy
contribution_precision
contribution_rounding_phase
contribution_comparison_scope
contribution_method_contract_version
estimated_contribution_status
estimated_contribution
not_computable_reason
```

Each `contribution_measure_id` must also freeze `measure_name`,
`physical_meaning`, `unit`, `value_domain`, `sign_policy`, `precision`,
`rounding_phase`, `zero_meaning`, `comparison_scope`, and
`supported_attribution_methods`. A method contract may use `kg`, `percentage
point`, `dimensionless ratio`, `signed metric delta`, or `absolute metric delta`
only when that unit is explicitly registered for the measure. The contract must
state whether negative values are allowed, what positive and negative signs
mean, whether a ratio is `[0,1]` or percentage points, and when Decimal
rounding occurs. Zero means a computed zero; it never means unavailable.

Until those fields are frozen, the result is fail-closed:

```text
ATTRIBUTION_MEASURE_CONTRACT_REQUIRED=true
ATTRIBUTION_CONTRIBUTION_VALUE_REQUIRED_ONLY_WHEN_STATUS_COMPUTED=true
ATTRIBUTION_NOT_COMPUTABLE_REASON_REQUIRED_WHEN_STATUS_NOT_COMPUTABLE=true
```

Cross-method and cross-measure arithmetic is prohibited. Contributions may be
compared only when all of `contribution_measure_id`, `contribution_unit`,
`contribution_sign_policy`, `contribution_method_contract_version`, and
`contribution_comparison_scope` match; even then they are not automatically
summed:

```text
CROSS_METHOD_CONTRIBUTION_COMPARISON_ALLOWED=false
CROSS_MEASURE_CONTRIBUTION_COMPARISON_ALLOWED=false
CROSS_UNIT_CONTRIBUTION_COMPARISON_ALLOWED=false
CROSS_METHOD_CONTRIBUTION_SUMMATION_ALLOWED=false
```

#### S3 acceptance evidence

S3 is accepted only when the point-in-time replay, leakage audit, current-model
metrics, naive-baseline metrics, coverage report, and error-attribution matrix
are reproducible from their manifests. The output is a ranked, evidence-based
candidate list for S4, not an authorization to change the model.

#### S2 identity alignment implementation authorization amendment R1 pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTH_AMENDMENT_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-authorization-amendment-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTH_AMENDMENT_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-authorization-amendment-r1.json
EVIDENCE_JSON_SHA256=c4d26633413dcde42b989684c1eb372443f5598c210d6a920dc51e50bc4093a4
ORIGINAL_AUTH_EVIDENCE_JSON_SHA256=1d1b213e6a31e899ce777440f1f1dce63be66006520e417775cdb330d335221d
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=false
BOUND_FIXTURE_IS_NOT_LIVE_ALIGNMENT_AUTHORITY=true
TEST_ONLY_EXPLICIT_INJECTION_BOUND_FIXTURE_PATH_PRESERVED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
NO_STATE_FLIPS=true
AMENDMENT_ONLY=true
AMENDMENT_MERGE_DOES_NOT_IMPLEMENT_ALIGNMENT_ADAPTER=true
AMENDMENT_MERGE_DOES_NOT_FLIP_LIVE_FLAGS=true
```

Live `S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED` semantics are amended
by this R1 package only within the test-only structural `BOUND_FIXTURE` scope
described in the amendment workpaper. The original authorization workpaper and
evidence JSON are not rewritten. This pointer does not flip live flags, implement
an adapter, produce catalogs, or authorize backtest execution.

#### S2 identity alignment adapter R1 pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_ADAPTER_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-adapter-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-adapter-r1.json
EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_IMPLEMENTATION_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_IMPLEMENTED=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
```

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED` is maintained in
this §4.4 block and the adapter R1 package above. Default construction remains
fail-closed without injected alignment evidence; this does not write live S2
alignment facts into the repository or flip AVAILABLE/VERIFIED closeout flags.

#### Accepted S2 identity alignment evidence producer contract pointer

```text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_PATH=docs/v0-3/s3/s3-accepted-s2-identity-alignment-evidence-contract.md
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-contract.md
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-accepted-s2-identity-alignment-evidence-contract.json
EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_CONTRACT_AUTHORIZED` is
maintained in this §4.4 block and the producer contract package above. This
contract defines how a future deterministic producer may construct
`VersionedAcceptedS2IdentityAlignmentEvidence`; it does not implement a producer,
write live S2 identity facts, produce catalogs, or authorize backtest execution.

#### Accepted S2 identity alignment evidence producer implementation authorization pointer

```text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-authorization.md
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-accepted-s2-identity-alignment-evidence-authorization.json
EVIDENCE_JSON_SHA256=7a9fb4be04a165cb83cda2c09585b54624401cc9c004c5e48c49496913dce52e
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_EVIDENCE_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 block and the implementation authorization package above.
This grant records what a later deterministic evidence producer may do; it does not
implement a producer, write live S2 identity facts, produce catalogs, or authorize
backtest execution.

#### Accepted S2 identity alignment evidence producer R1 pointer

```text
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-accepted-s2-identity-alignment-evidence-producer-r1.md
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-accepted-s2-identity-alignment-evidence-producer-r1.json
EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
S3_A2_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_IMPLEMENTATION_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_S2_ALIGNMENT_FACTS=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
```

Live `DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED` is
maintained in this §4.4 block and the producer R1 package above. Default construction
remains fail-closed without injected harvest grain; this does not write live S2
alignment facts into the repository or flip AVAILABLE/VERIFIED closeout flags.

#### Incumbent forecast artifact content producer contract pointer

```text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-artifact-content-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-contract.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-contract.json
EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED` is maintained in
this §4.4 block and the content producer contract package above. This contract defines
how a future deterministic producer may construct `VersionedIncumbentForecastArtifact`
for injection into `IncumbentForecastArtifactAdapter`; it does not implement a
producer, write live forecast artifacts, produce catalogs, or authorize backtest
execution.

#### Incumbent forecast artifact content producer implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-authorization.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-authorization.json
EVIDENCE_JSON_SHA256=29a486d5fa04542404c6629509ee65ebdf3931c30cf758db643faf93cfd35a38
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_CONTENT_PRODUCER=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 block and the implementation authorization package above.
This grant records what a later deterministic content producer may do; it does not
implement a producer, write live forecast artifacts, produce catalogs, or authorize
backtest execution.


#### Incumbent forecast artifact content producer R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-artifact-content-producer-r1.md
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-artifact-content-producer-r1.json
EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_ARTIFACT_CONTENT_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED` is
maintained in this §4.4 block and the content producer R1 package above. Default
construction remains fail-closed without injected replay rows; this does not write
live forecast artifacts into the repository or flip AVAILABLE/VERIFIED closeout flags.

#### Incumbent forecast replay source contract pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-source-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-contract.json
EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED` is maintained in
this §4.4 block and the replay source contract package above. This contract defines
how a future deterministic replay source may obtain injectable rows for the landed
`IncumbentForecastArtifactContentProducer`; it does not implement a replay source,
wire producer/adapter defaults, write live forecast artifacts, or authorize backtest
execution.

#### Incumbent forecast replay source implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-authorization.md
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-authorization.json
EVIDENCE_JSON_SHA256=601e06ac1d679d7fb165a481cc01c27dd01fdd68e5a0d9699098c214ba88c890
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_REPLAY_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 block and the implementation authorization package above.
This grant records what a later deterministic replay source R1 may do; it does not
implement a replay source, wire producer/adapter defaults, write live forecast
artifacts, or authorize backtest execution.


#### Incumbent forecast replay source R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-source-r1.md
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-source-r1.json
EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED` is
maintained in this §4.4 block and the replay source R1 package above. Default
construction remains fail-closed without injected replay rows; this does not write
live forecast artifacts into the repository or flip AVAILABLE/VERIFIED closeout flags.

#### Incumbent forecast live source kind contract pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-source-kind-contract.md
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-contract.md
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-source-kind-contract.json
EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED` is maintained in
this §4.4 block and the live source kind contract package above. This contract
freezes when live forecast `catalog_source_kind` may be claimed and which kinds
must never impersonate it; it does not implement code, modify `registry.py`, write
live forecast artifacts, or authorize backtest execution.

#### Incumbent forecast live source kind implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-authorization.md
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-source-kind-authorization.json
EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=false
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_SOURCE_KIND=true
AUTHORIZATION_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 block and the implementation authorization package above.
This grant records what a later deterministic live source kind R1 may do; it does
not implement code, land enum members, write live forecast artifacts, or authorize
backtest execution.

#### Incumbent forecast live source kind R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-source-kind-r1.md
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-source-kind-r1.json
EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a
LIVE_SOURCE_KIND_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
IMPLEMENTATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_MERGE_DOES_NOT_MODIFY_FORBIDDEN_OR_ALIGNMENT_SETS=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED` is
maintained in this §4.4 live state block and the live source kind R1 package above.
R1 lands `CatalogSourceKind.V0_2_CURRENT_INCUMBENT_AT_HISTORICAL_CUTOFF` only; it
does not wire producer/adapter defaults, write live forecast artifacts into the
repository, or flip AVAILABLE/VERIFIED closeout flags. Historical grant/contract
pointer snapshots may remain `false`.

#### Incumbent forecast live envelope contract pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-live-envelope-contract.md
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-contract.md
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-envelope-contract.json
EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
LIVE_SOURCE_KIND_R1_EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_ENVELOPE_ASSIGNMENT=true
CONTRACT_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
CONTRACT_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the live envelope contract package above. This
contract freezes deterministic `catalog_source_kind` envelope assignment on produced
forecast artifacts; it does not implement assignment logic, wire obtain→produce→adapter,
write live forecast artifacts, or authorize backtest execution.

#### Incumbent forecast live envelope implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-authorization.md
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-envelope-authorization.json
EVIDENCE_JSON_SHA256=86d6937c11783d1c95aa6da5de281b749c1272092b452383f2bc27b1c33544b5
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
LIVE_SOURCE_KIND_CONTRACT_EVIDENCE_JSON_SHA256=2d0cce5d0c0f89c136014a2abbd01d67ef0004786c63050115d55a2dc0519ee1
LIVE_SOURCE_KIND_R1_EVIDENCE_JSON_SHA256=3a7a1f4f74074630c4eedb658ca361db579e16b1f7e4630f51b04266fa963a7a
LIVE_SOURCE_KIND_AUTH_EVIDENCE_JSON_SHA256=759644330a0063560f11e53a74a92b03dbb6221ab6c58f523a74462dc145fa9e
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
CONTENT_CONTRACT_EVIDENCE_JSON_SHA256=6294f2028509f2b1021741ac7aea3f20efdcbe07669b87a1782d18c0a5ca9eae
CONTENT_PRODUCER_R1_EVIDENCE_JSON_SHA256=d159c010b4f527972e7554789e85808ae48e11941499c6f597f124fd471ff228
FORECAST_ADAPTER_R1_EVIDENCE_JSON_SHA256=31bb6d24cf4c398eeea86c18d2dece16b9e0ab6f704e9ab229eac5a363d296a0
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_ENVELOPE_ASSIGNMENT=true
AUTHORIZATION_MERGE_DOES_NOT_MODIFY_REGISTRY_PY_ENUM=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the implementation authorization package
above. This grant records what a later deterministic live envelope R1 may do; it
does not implement envelope assignment, wire obtain→produce→adapter, write live
forecast artifacts, or flip AVAILABLE/VERIFIED closeout flags. Historical
contract pointer snapshots may remain `false` for
`DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED`.

#### Incumbent forecast live envelope R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-live-envelope-r1.md
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-live-envelope-r1.json
EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
LIVE_ENVELOPE_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=86d6937c11783d1c95aa6da5de281b749c1272092b452383f2bc27b1c33544b5
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTATION_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
IMPLEMENTATION_MERGE_DOES_NOT_WIRE_PRODUCER_OR_ADAPTER=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED` is
maintained in this §4.4 live state block and the live envelope R1 package above.
R1 implements parent contract §3 envelope assignment via
`declared_catalog_source_kind` only; it does not wire obtain→produce→adapter
defaults or flip AVAILABLE/VERIFIED closeout flags. Historical grant/contract
pointer snapshots may remain `false`.

#### Incumbent forecast fail-closed wiring contract pointer

```text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-fail-closed-wiring-contract.md
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-contract.md
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-fail-closed-wiring-contract.json
EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_SOURCE_KIND_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_SOURCE_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_CONTENT_PRODUCER_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_ARTIFACT_SERVICE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
```

Live `S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the fail-closed wiring contract package above. This
contract freezes deterministic obtain→produce→adapter default-chain behavior; it does
not implement wiring, authorize V0.2 obtain, or flip `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED`.

#### Incumbent forecast fail-closed wiring implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-authorization.md
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-fail-closed-wiring-authorization.json
EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
LIVE_ENVELOPE_CONTRACT_EVIDENCE_JSON_SHA256=9b67eabc5ae01f5e834dda4d8321208198a4bef3ad3e1d5f6a3bdf2fe5ed27d4
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the fail-closed wiring implementation
authorization package above. This grant records what a later deterministic wiring R1
may do when the user again says 「可以实施」; it does not implement wiring, authorize
V0.2 obtain, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED` remains `false`
until a separate implementation R1.

#### Incumbent forecast fail-closed wiring R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-fail-closed-wiring-r1.md
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-fail-closed-wiring-r1.json
EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=84c4491daefa59f74d875f7b311612efbead4143688b5582c499981fe82210e0
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_CONTRACT_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED` is
maintained in this §4.4 live state block and the fail-closed wiring R1 package above.
R1 wires obtain→produce→adapter defaults while empty obtain remains fail-closed;
it does not implement V0.2 postgres obtain, wire alignment producer→adapter, or flip
AVAILABLE/VERIFIED closeout flags. Historical grant/contract pointer snapshots may
remain `false`.

#### Incumbent forecast V0.2 postgres obtain contract pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-postgres-obtain-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-contract.json
EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_LIVE_ENVELOPE_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the V0.2 postgres obtain contract package above. This
contract freezes empty-default obtain authority from named V0.2 point-in-time replay;
it does not implement postgres reading, invent SQL or table names, or flip
`NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.

#### Incumbent forecast V0.2 postgres obtain implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-authorization.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-authorization.json
EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
FAIL_CLOSED_WIRING_CONTRACT_EVIDENCE_JSON_SHA256=2ea44667836957fa736828cbd4ae123c5d2144a43918939ab4d494f4cbcaf1ff
LIVE_ENVELOPE_R1_EVIDENCE_JSON_SHA256=164b2396091dc5b2daf790f09c92e9ebf628c6e577a37acdc6e4dc0c88b3e601
REPLAY_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=59e452eedc6b8db82063d11ccaf7af177447074c7ad68565b31a6d86d5d4b457
REPLAY_SOURCE_R1_EVIDENCE_JSON_SHA256=59a198c38c0c1e8e17a718bb5623943c4035b4b9b582e2216b922d526b508929
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_FAIL_CLOSED_WIRING_IMPLEMENTED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_V0_2_POSTGRES_OBTAIN=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_FORECAST_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the V0.2 postgres obtain implementation
authorization package above. This grant records what a later deterministic obtain R1
may do when the user again says 「可以实施」; it does not implement postgres reading,
invent SQL or table names, or flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` remains `false`
until a separate implementation R1.

#### Incumbent forecast V0.2 postgres obtain R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.md
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-postgres-obtain-r1.json
EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=6b3655921acd896f0570e0c01fbcb5a85478018c8c968bb84c26a02567253bdd
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_CONTRACT_AUTHORIZED=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_WIRE_ALIGNMENT=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED` is
maintained in this §4.4 live state block and the V0.2 postgres obtain R1 package above.
R1 lands the empty-default fail-closed postgres obtain path; repository contracts
contain no frozen SQL or table names so default `obtain()` remains `()`. It does not
flip `NO_VERSIONED` / `AVAILABLE` / `VERIFIED` or wire alignment producer→adapter.
Historical grant/contract pointer snapshots may remain `false`.

#### S2 identity alignment producer→adapter wiring contract pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-producer-adapter-wiring-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-contract.json
EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
PARENT_ALIGNMENT_CONTRACT_GIT_BLOB_SHA=7568a608b891d4b98b9aaf7f6857a28eb90bb123
PARENT_EVIDENCE_PRODUCER_CONTRACT_GIT_BLOB_SHA=22f49d7a78bad1a9332040e9f890daa22ef4b1e3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the producer→adapter wiring contract package above. This
contract freezes fail-closed default wiring authority; it does not implement wiring,
invent harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` remains `false`.



#### S2 identity alignment producer→adapter wiring implementation authorization pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-authorization.json
EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
PARENT_CONTRACT_GIT_BLOB_SHA=4ffe45d030e00029b5053165eec8646be591420a
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_SERVICE_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_WIRING=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the producer→adapter wiring implementation
authorization package above. This grant records what a later deterministic wiring R1
may do when the user again says 「可以实施」; it does not implement wiring, invent
harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` remains `false`
until a separate implementation R1.

#### S2 identity alignment producer→adapter wiring R1 pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-producer-adapter-wiring-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-producer-adapter-wiring-r1.json
EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
WIRING_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_CONTRACT_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED` is
maintained in this §4.4 live state block and the producer→adapter wiring R1 package above.
R1 wires default `AcceptedS2IdentityAlignmentEvidenceProducer.produce()` into
`S2IdentityAlignmentAdapter.evidence`; default `harvest_rows=()` still yields
`evidence=None`. It does not flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED` or read SOURCE_002 row-level harvest. Historical grant/contract pointer
snapshots may remain `false`.

#### S2 identity alignment harvest source contract pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_PATH=docs/v0-3/s3/s3-s2-identity-alignment-harvest-source-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-contract.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-contract.json
EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the harvest source contract package above. This contract
freezes fail-closed harvest source authority; it does not implement obtain, invent harvest
rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` / `VERIFIED`.
`DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` remains `false`.

#### S2 identity alignment harvest source implementation authorization pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-authorization.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-authorization.json
EVIDENCE_JSON_SHA256=bad95719d0f2af0481093251707643ec6aa69fc299770d27e7a52e3703d24c64
PARENT_HARVEST_CONTRACT_GIT_BLOB_SHA=2372c05e1e37d3c552dab0259a24bd8e9c461c91
PARENT_HARVEST_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
PARENT_WIRING_CONTRACT_GIT_BLOB_SHA=71d723a00f722efe04f238276ce4e4cddb193f13
WIRING_CONTRACT_EVIDENCE_JSON_SHA256=89e4a35e68d70d942df0c795953573828618d62ac3caddc78dba5609608ec36a
WIRING_GRANT_EVIDENCE_JSON_SHA256=7a4a758259f3e5a54ef01ac623f822fc3bafb2a04c0031d040e8fb2332506f6f
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
PARENT_PRODUCER_CONTRACT_GIT_BLOB_SHA=65c5ea7916ef15d777ff2053015f99e56ea4268a
EVIDENCE_PRODUCER_CONTRACT_EVIDENCE_JSON_SHA256=2bdb9a578592dadd8cf9d15a8071d46f9983e7bb973159d0c3b6ec21b5725add
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=false
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_PRODUCER_ADAPTER_WIRING_IMPLEMENTED=true
DETERMINISTIC_ACCEPTED_S2_IDENTITY_ALIGNMENT_EVIDENCE_PRODUCER_IMPLEMENTED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_HARVEST_SOURCE=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_HARVEST_ROWS_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_PRODUCE_FROM_NONE=true
AUTHORIZATION_MERGE_DOES_NOT_WRITE_LIVE_ALIGNMENT_ARTIFACT=true
AUTHORIZATION_MERGE_DOES_NOT_PRODUCE_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_BIND_CATALOG=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_CATALOG_SOURCE_KIND_PROVENANCE=true
AUTHORIZATION_MERGE_DOES_NOT_REWIRE_PRODUCER_ADAPTER_WIRING=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the harvest source implementation
authorization package above. This grant records what a later deterministic harvest
source R1 may do when the user again says 「可以实施」; it does not implement obtain,
invent harvest rows or SQL, or flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED`. `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` remains
`false` until a separate implementation R1.


#### S2 identity alignment harvest source R1 pointer

```text
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-s2-identity-alignment-harvest-source-r1.md
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-s2-identity-alignment-harvest-source-r1.json
EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
HARVEST_SOURCE_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=bad95719d0f2af0481093251707643ec6aa69fc299770d27e7a52e3703d24c64
HARVEST_SOURCE_CONTRACT_EVIDENCE_JSON_SHA256=92da3bc9ffab3cb90c825292e8c53f79b1ce5d6abc2ff0ccbedda8b31ba6cb3a
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTATION_AUTHORIZED=true
S3_A2_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_CONTRACT_AUTHORIZED=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_LIVE_S2=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED` is
maintained in this §4.4 live state block and the harvest source R1 package above.
R1 adds in-memory `S2IdentityAlignmentHarvestSource.obtain()` and producer
`harvest_source` fallback; default `harvest_rows=()` and default `obtain()=()` still
yield `produce()=None`. It does not flip `NO_LIVE_S2` / `NO_VERSIONED` / `AVAILABLE` /
`VERIFIED` or read SOURCE_002 row-level harvest. Historical grant/contract pointer
snapshots may remain `false`.

#### Incumbent forecast V0.2/S3 SQL table-name authority contract pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-sql-table-authority-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-sql-table-authority-contract.json
EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
HARVEST_SOURCE_R1_EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_INVENT_SQL_OR_TABLE_NAMES=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED` is
maintained in this §4.4 live state block and the SQL table-name authority contract
package above. This contract freezes a read-only Alembic audit at `2cfc2c0`: zero
`MATCH` table names for replay grain `DISTINCT(forecast_cutoff_at, model_id,
forecast_quantile)`; default obtain remains fail-closed `()`. It does not implement
live postgres read, invent SQL or table names, or flip `NO_VERSIONED` / `NO_LIVE_S2` /
`AVAILABLE` / `VERIFIED`. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED`
remains `false`.

#### Incumbent forecast V0.2/S3 SQL table-name authority implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-authorization.md
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-sql-table-authority-authorization.json
EVIDENCE_JSON_SHA256=8262b9350f59db13ecf67e87734ca6dc9caf58f8c4689c64a331a36b551f1cfd
PARENT_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c2b17ac92b33ca4b8211710aee5de3ebd559249e
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
FAIL_CLOSED_WIRING_R1_EVIDENCE_JSON_SHA256=875480dd04970eedf597a766d702fea1eeeda27512984ca51a725eace0014f0e
HARVEST_SOURCE_R1_EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
EVIDENCE_PRODUCER_R1_EVIDENCE_JSON_SHA256=b563f3372e72736f09c750485d24e176ed36448ca8f4ce033ffdbebd51d35ac3
ALIGNMENT_ADAPTER_R1_EVIDENCE_JSON_SHA256=9813dec98c43edd2e66ac0ce04a27bd6dbe4edb06ba9eb9105736d3d30c547f9
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
DETERMINISTIC_S2_IDENTITY_ALIGNMENT_HARVEST_SOURCE_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_SQL_TABLE_AUTHORITY=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_INVENT_SQL_OR_TABLE_NAMES=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the SQL table-name authority implementation
authorization package above. This grant records what a later deterministic R1 may do
when the user again says 「可以实施」: encode the frozen empty bindable-name set as
in-memory authority while default obtain remains `()`. It does not implement live postgres
read, invent SQL or table names, or flip `NO_VERSIONED` / `NO_LIVE_S2` / `AVAILABLE` /
`VERIFIED`. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`
until separate implementation R1.


#### Incumbent forecast V0.2/S3 SQL table-name authority R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-sql-table-authority-r1.md
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-sql-table-authority-r1.json
EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=8262b9350f59db13ecf67e87734ca6dc9caf58f8c4689c64a331a36b551f1cfd
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
HARVEST_SOURCE_R1_EVIDENCE_JSON_SHA256=bef3cedecf7498064f9929e7c40b863ed8ad028d0cf0e9f30e7b547bc7af408e
WIRING_R1_EVIDENCE_JSON_SHA256=1349db0e8ef64f99250ae965b99fbba52d817f682201286852dccaa3df20c579
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_POSTGRES_OBTAIN_IMPLEMENTED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_REGISTRY_AVAILABLE=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_COMPLETENESS_VERIFIED=true
IMPLEMENTATION_MERGE_DOES_NOT_SOURCE_002_ROW_LEVEL_READ=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED` is
maintained in this §4.4 live state block and the SQL table-name authority R1 package above.
R1 encodes the frozen empty bindable-name set in memory and consults it from default
postgres obtain; default `obtain()` remains `()` without postgres I/O. It does not flip
live postgres read, invent SQL or table names, or flip `NO_VERSIONED` / `NO_LIVE_S2` /
`AVAILABLE` / `VERIFIED`. Historical grant/contract pointer snapshots may remain `false`.

#### Incumbent forecast replay-identity persistence schema contract pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-persistence-schema-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-contract.json
EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
PARENT_SQL_TABLE_AUTHORITY_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=97c15064445d0ff4776884234994f0a10f6537d5
SQL_TABLE_AUTHORITY_CONTRACT_EVIDENCE_JSON_SHA256=99e4bb4853b6020404a86221c470936fce27f26bb6373fbe81167ffaeac6e260
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
PARENT_POSTGRES_OBTAIN_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c02ae702995c38f33ca73c3af26e8fdb33cc8e04
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
POSTGRES_OBTAIN_R1_EVIDENCE_JSON_SHA256=66c992c6ef6a085f8856afdc0456fb727d1dc31d32152ca7006b4c33aaff6c10
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
CONTRACT_MERGE_DOES_NOT_ADD_ALEMBIC=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2_SQL_TABLE_NAME=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED` is
maintained in this §4.4 live state block and the replay-identity persistence schema
contract package above. This contract freezes future object `s3_incumbent_forecast_replay_identity`;
the object does not exist in Alembic today. It does not implement live postgres read, add
Alembic, or flip `NO_VERSIONED`. `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED`
and `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.

#### Incumbent forecast replay-identity persistence schema implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-authorization.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-authorization.json
EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
PARENT_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=cb7dbac6c1f2c0e1a9c23a69f1ad6a684da40e75
PARENT_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=false
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_SCHEMA=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_ALEMBIC=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2_SQL_TABLE_NAME=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the implementation authorization package above.
This grant records what a later deterministic schema R1 may do when the user again says
「可以实施」: create the frozen empty table `s3_incumbent_forecast_replay_identity` via one
linear Alembic revision. This PR does not add Alembic, write SQL, populate rows, or flip
`NO_VERSIONED` / `NO_BINDABLE_V0_2` / `LIVE_POSTGRES_READ`. Authorization merge does not
close S3. `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED`
and `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.
A later schema R1 flips only `SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`.

#### Incumbent forecast replay-identity persistence schema R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-persistence-schema-r1.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-persistence-schema-r1.json
EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
SCHEMA_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=f58fa58c9f3e815c2a987903d1ec4f2ef6818008cba966c57b1b9ccfafdf6e01
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_FUTURE_OBJECT_NAME=s3_incumbent_forecast_replay_identity
FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_DOWN_REVISION=a7c3e9f1b2d4
ALEMBIC_MIGRATION_PATH=backend/alembic/versions/e8b2c4d6f1a3_s3_incumbent_forecast_replay_identity.py
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
UPGRADE_ROW_COUNT=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
EMPTY_TABLE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
IMPLEMENTATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
IMPLEMENTATION_MERGE_DOES_NOT_POPULATE_UPGRADE_ROWS=true
SCHEMA_R1_FLIPS_ONLY_SCHEMA_IMPLEMENTED=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED` is
maintained in this §4.4 live state block and the schema R1 package above. R1 creates the
frozen empty Alembic table `s3_incumbent_forecast_replay_identity` with 0 upgrade rows. Empty
table ≠ versioned incumbent forecast artifact. Empty table ≠ bindable V0.2 SQL table name.
Empty table ≠ live postgres read. Default `obtain()` remains `()`. This R1 flips only
`SCHEMA_IMPLEMENTED`, not `LIVE_POSTGRES_READ`. Historical grant/contract pointer snapshots
may remain `false` for `FROZEN_FUTURE_OBJECT_EXISTS_IN_ALEMBIC`.

#### Incumbent forecast replay-identity bindable name contract pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-replay-identity-bindable-name-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-contract.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-bindable-name-contract.json
EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
PARENT_PERSISTENCE_SCHEMA_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=a7cf5abfed864fb95ab2f870c422a0f7caaf97fd
SCHEMA_CONTRACT_EVIDENCE_JSON_SHA256=b0c2553f3a561bf8c46b39f015a604f31f9c6a9c5d682a060ad5eff0dfbfb806
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED` is
maintained in this §4.4 live state block and the bindable-name contract package above.
This contract freezes coordinator-reviewed bindable name `s3_incumbent_forecast_replay_identity`
for the now-existing empty Alembic table (0 rows at review). Table existence ≠ bindable
implementation. This contract does not implement live postgres read, populate rows, flip
`NO_BINDABLE_V0_2`, flip `NO_VERSIONED`, or change default `obtain()`. Authorization merge
does not close S3. `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED`
and `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.
A later bindable-name R1 flips only `BINDABLE_NAME_IMPLEMENTED` (and `NO_BINDABLE_V0_2`),
not `LIVE_POSTGRES_READ`.

#### Incumbent forecast replay-identity bindable name implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-authorization.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-bindable-name-authorization.json
EVIDENCE_JSON_SHA256=b745ccdc0a5084368852041337d5409d0c8aad4c93183070a573a35167df604d
PARENT_BINDABLE_NAME_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=402942dd80a14299db263227e60d4a590b786f76
BINDABLE_NAME_CONTRACT_EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=true
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
OBJECT_ROW_COUNT_AT_REVIEW=0
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_BINDABLE_NAME_ENCODING=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_POPULATE_ROWS=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_BINDABLE_V0_2=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_BINDABLE_NAME_IMPLEMENTED=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED` is
maintained in this §4.4 live state block and the implementation authorization package above.
This grant records what a later deterministic bindable-name R1 may do when the user again says
「可以实施」: record frozen name `s3_incumbent_forecast_replay_identity` in deterministic code.
Grant ≠ bindable-name encoding ≠ live postgres read ≠ versioned forecast artifact. Empty table
+ reviewed name + unused grant still yields `obtain()=()`. Later live-read of the empty table
still yields `()`. This PR does not encode bindable names, populate rows, flip `NO_BINDABLE_V0_2`,
flip `NO_VERSIONED`, or implement live postgres read. Authorization merge does not close S3.
`DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` and
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remain `false`.
A later bindable-name R1 flips only `BINDABLE_NAME_IMPLEMENTED` (and `NO_BINDABLE_V0_2`), not
`LIVE_POSTGRES_READ`. Jumping to live-read now is forbidden.

#### Incumbent forecast replay-identity bindable name R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-replay-identity-bindable-name-r1.md
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-replay-identity-bindable-name-r1.json
EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
BINDABLE_NAME_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=b745ccdc0a5084368852041337d5409d0c8aad4c93183070a573a35167df604d
BINDABLE_NAME_CONTRACT_EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
SCHEMA_R1_EVIDENCE_JSON_SHA256=921df3fd317213eeaf44fe594e72650ac7dea84d8499ca915c5f627fe60e3599
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_CONTRACT_AUTHORIZED=true
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_PERSISTENCE_SCHEMA_IMPLEMENTED=true
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_BINDABLE_REPLAY_IDENTITY_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
OBJECT_ROW_COUNT_AT_REVIEW=0
AUTHORITY_MODULE_PATH=backend/app/s3_daily_rowset/incumbent_forecast_v0_2_sql_table_authority.py
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB_UNCHANGED=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
BINDABLE_NAME_R1_FLIPS_ONLY_BINDABLE_NAME_AND_NO_BINDABLE_V0_2=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED` and
`NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY` are maintained in this §4.4 live state block
and the bindable-name R1 package above. R1 encodes frozen name
`s3_incumbent_forecast_replay_identity` in deterministic authority code only. Encoding the name
≠ live postgres read ≠ versioned forecast artifact. Empty table still has 0 rows. Default
`obtain()` remains `()`. This R1 flips only `BINDABLE_NAME_IMPLEMENTED` and `NO_BINDABLE_V0_2`,
not `LIVE_POSTGRES_READ`. Historical grant/contract pointer snapshots may remain
`NO_BINDABLE_V0_2=true`.

#### Incumbent forecast V0.2 live postgres read contract pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-live-postgres-read-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-contract.json
EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
BINDABLE_NAME_CONTRACT_EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=false
LIVE_POSTGRES_READ_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_LIVE_READ_BINDABLE_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
OBJECT_ROW_COUNT_AT_REVIEW=0
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY_OBTAIN=true
CONTRACT_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
CONTRACT_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ_IMPLEMENTED=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the live postgres read contract package above. After
bindable-name R1 (#359) encoded frozen name `s3_incumbent_forecast_replay_identity`,
`bindable_table_names()` is non-empty yet `_empty_v0_2_postgres_obtain` still returns `()`.
This contract freezes live-read authority for that encoded name only. Live-read contract ≠
live-read grant ≠ live-read R1 ≠ versioned forecast artifact. Empty table + encoded bindable
name + unused live-read contract still yields `obtain()=()`. Later live-read of the empty
table still yields `()`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`.
This contract does not implement live-read, populate rows, flip `NO_VERSIONED`, or close S3.
`DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` remains `false`.
Historical grant/contract pointer snapshots may remain `NO_BINDABLE_V0_2=true`.
Jumping to live-read implementation now is forbidden.

#### Incumbent forecast V0.2 live postgres read implementation authorization pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTH_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-authorization.md
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTH_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-authorization.json
EVIDENCE_JSON_SHA256=ba791a1c2292d36b075cc6bc717d788df9d1efd063193ed5d2290783f4bfbeec
PARENT_LIVE_POSTGRES_READ_CONTRACT_GIT_BLOB_SHA_AT_FREEZE=c324d03f52a86cbd9a9b354bdcc58e27eb01279a
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
BINDABLE_NAME_CONTRACT_EVIDENCE_JSON_SHA256=34827903ef67de35958cd0e967b1b008ccde1ed90803bc81a4c1fdc6d1467f14
V0_2_POSTGRES_OBTAIN_CONTRACT_EVIDENCE_JSON_SHA256=a6ff0d53db223d6ec1258b38378d62c6ecb8a37fe908458a5a734efe7e203b49
SQL_TABLE_AUTHORITY_R1_EVIDENCE_JSON_SHA256=aad30ef4b0f6b16cbdab8aab4571f231e46758b138ab636d7b20208c55a39218
LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
LIVE_POSTGRES_READ_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
S3_PRODUCTION_CODE_MUTATION_AUTHORIZED=false
S3_TEST_CODE_MUTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_REPLAY_IDENTITY_BINDABLE_NAME_IMPLEMENTED=true
NO_BINDABLE_V0_2=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_LIVE_READ_BINDABLE_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
OBJECT_ROW_COUNT_AT_REVIEW=0
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=9ffb7bdf9beb1d897b8a1752f06de9250011cf15
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_IS_NOT_LIVE_POSTGRES_READ=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY_OBTAIN=true
AUTHORIZATION_MERGE_DOES_NOT_IMPLEMENT_LIVE_POSTGRES_READ=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_LIVE_POSTGRES_READ_IMPLEMENTED=true
AUTHORIZATION_MERGE_DOES_NOT_POPULATE_ROWS=true
AUTHORIZATION_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
AUTHORIZATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
AUTHORIZATION_MERGE_DOES_NOT_REOPEN_106_ROW_AUDIT=true
AUTHORIZATION_MERGE_DOES_NOT_ADD_ALEMBIC=true
AUTHORIZATION_MERGE_DOES_NOT_TOUCH_PYTHON=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED` is maintained in
this §4.4 live state block and the implementation authorization package above. After
bindable-name R1 (#359) encoded frozen name `s3_incumbent_forecast_replay_identity`,
`bindable_table_names()` is non-empty yet `_empty_v0_2_postgres_obtain` still returns `()`.
This grant records what a later deterministic live-read R1 may do when the user again says
「可以实施」. Grant ≠ live-read contract ≠ live-read R1 ≠ versioned forecast artifact.
Empty table + encoded bindable name + unused grant still yields `obtain()=()`. Later live-read
of the empty table still yields `()`. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This grant does not implement live-read, populate
rows, flip `NO_VERSIONED`, or close S3. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED`
remains `false`. Historical grant/contract pointer snapshots may remain `NO_BINDABLE_V0_2=true`.
Jumping to live-read R1 implementation now is forbidden.

#### Incumbent forecast V0.2 live postgres read R1 pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_R1_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-live-postgres-read-r1.md
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_R1_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-live-postgres-read-r1.json
EVIDENCE_JSON_SHA256=8b56f82fe1dd9871dfb7f02ef3b9f768f265020f7f62b4078fb9b7feb1187763
LIVE_POSTGRES_READ_IMPLEMENTATION_AUTH_EVIDENCE_JSON_SHA256=ba791a1c2292d36b075cc6bc717d788df9d1efd063193ed5d2290783f4bfbeec
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
BINDABLE_NAME_R1_EVIDENCE_JSON_SHA256=121d677c6645f87162a0108649f73aec1e825f1901148170d55179f9aa17543d
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_LIVE_READ_BINDABLE_TABLE_NAME=s3_incumbent_forecast_replay_identity
OBJECT_ROW_COUNT_AT_REVIEW=0
LIVE_READ_MODULE_PATH=backend/app/s3_daily_rowset/incumbent_forecast_v0_2_live_postgres_read.py
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB_UNCHANGED=ac840d2e46836427baaec3e46b0d111eda4adf74
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
LATER_LIVE_READ_OF_EMPTY_TABLE_STILL_YIELDS_EMPTY=true
IMPLEMENTATION_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
IMPLEMENTATION_MERGE_DOES_NOT_POPULATE_ROWS=true
LIVE_READ_R1_FLIPS_ONLY_LIVE_POSTGRES_READ_IMPLEMENTED=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED` is maintained in this
§4.4 live state block and the live-read R1 package above. R1 wires live read of frozen table
`s3_incumbent_forecast_replay_identity` via injected session only. Live-read R1 ≠ row population ≠
versioned forecast artifact. Empty table still has 0 rows. Default obtain() without session remains
`()`. Catalog first blocker remains `NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. Historical
grant/contract pointer snapshots may remain `LIVE_POSTGRES_READ_IMPLEMENTED=false`.



#### Incumbent forecast V0.2 replay-identity grain row presence contract pointer

```text
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_PATH=docs/v0-3/s3/s3-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_WORKPAPER=docs/v0-3/s3/workpapers/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.md
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_EVIDENCE_JSON=docs/v0-3/s3/evidence/s3-a2-incumbent-forecast-v0-2-replay-identity-grain-row-presence-contract.json
EVIDENCE_JSON_SHA256=1e7204dc716dd1e65de4b0248ebe4de01638cb31628b0cb10db8e1fdf5aba833
LIVE_POSTGRES_READ_R1_EVIDENCE_JSON_SHA256=8b56f82fe1dd9871dfb7f02ef3b9f768f265020f7f62b4078fb9b7feb1187763
LIVE_POSTGRES_READ_CONTRACT_EVIDENCE_JSON_SHA256=3009c0ed24d35dadcb717d31e62767662ed36a6f7b238d36e2360854ab51b58d
GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=true
GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=false
GRAIN_ROW_PRESENCE_IMPLEMENTED=false
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTATION_AUTHORIZED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED=false
DETERMINISTIC_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_IMPLEMENTATION_AUTHORIZED=true
S3_A2_INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_CONTRACT_AUTHORIZED=true
NO_BINDABLE_V0_2=true
NO_BINDABLE_V0_2_SQL_TABLE_NAME_IN_REPOSITORY=false
DEFAULT_OBTAIN_REMAINS_FAIL_CLOSED_EMPTY=true
FROZEN_GRAIN_ROW_PRESENCE_TABLE_NAME=s3_incumbent_forecast_replay_identity
FROZEN_BINDABLE_OBJECT_EXISTS_IN_ALEMBIC=true
ALEMBIC_REVISION=e8b2c4d6f1a3
ALEMBIC_MIGRATION_BLOB=1e0864ebef1d947d4c9466d71efaa759d44c7ad7
OBJECT_ROW_COUNT_AT_REVIEW=0
NO_REVIEWED_GRAIN_IDENTITY_SET_IN_REPOSITORY=true
INCUMBENT_FORECAST_REPLAY_SOURCE_PY_BLOB=fb12e03ba7770518b16efa7495dce0a2f1f68f18
INCUMBENT_FORECAST_V0_2_LIVE_POSTGRES_READ_PY_BLOB=6ab7bc81f513b76f7d412d6b0c44b4f1ce9d21dc
INCUMBENT_FORECAST_V0_2_SQL_TABLE_AUTHORITY_PY_BLOB=ac840d2e46836427baaec3e46b0d111eda4adf74
AUDIT_TABLE_COUNT=106
MATCH_TABLE_COUNT=0
MATCH_TABLE_NAMES=()
NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT_IN_REPOSITORY=true
NO_LIVE_S2_IDENTITY_ALIGNMENT_ADAPTER_IN_REPOSITORY=true
NO_BINDABLE_CATALOG_IN_REPOSITORY=true
EVALUATION_INSTANCE_REGISTRY_AVAILABLE=false
CURRENT_S3_DAILY_ROWSET_COMPLETENESS_VERIFIED=false
SOURCE_002_ROW_LEVEL_READ=false
TEST_REMAINS_SEALED=true
DEFAULT_CATALOG_FIRST_BLOCKER=NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT
EMPTY_TABLE_IS_NOT_VERSIONED_ARTIFACT=true
EMPTY_TABLE_STILL_ZERO_ROWS_AT_REVIEW=true
CONTRACT_MERGE_DOES_NOT_POPULATE_ROWS=true
CONTRACT_MERGE_DOES_NOT_INVENT_IDENTITY_SET=true
CONTRACT_MERGE_DOES_NOT_INVENT_CUTOFF_MODEL_QUANTILE_LISTS=true
CONTRACT_MERGE_DOES_NOT_FLIP_NO_VERSIONED=true
CONTRACT_MERGE_DOES_NOT_CHANGE_DEFAULT_OBTAIN_FROM_EMPTY=true
CONTRACT_MERGE_DOES_NOT_WIRE_SESSION_INTO_CATALOG_DEFAULT=true
CONTRACT_MERGE_DOES_NOT_ADD_TO_MATCH_TABLE_NAMES=true
CONTRACT_MERGE_DOES_NOT_ISSUE_IMPLEMENTATION_GRANT=true
IMPLEMENTATION_REQUIRES_SEPARATE_USER_GATE_可以实施=true
LIVE_FLAG_AUTHORITY=docs/v0-3/development-plan.md §4.4 live state block
```

Live `S3_A2_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_CONTRACT_AUTHORIZED` is maintained in
this §4.4 live state block and the grain row presence contract package above. After live-read R1,
frozen table `s3_incumbent_forecast_replay_identity` still has 0 rows. This contract freezes how grain
rows may later exist. Grain row presence contract ≠ grant ≠ R1 ≠ INSERT ≠ identity-set invention ≠
versioned artifact ≠ catalog closeout. No coordinator-reviewed grain identity-set exists in repository.
Default `obtain()` without session remains `()`. Catalog first blocker remains
`NO_VERSIONED_INCUMBENT_FORECAST_ARTIFACT`. This contract does not populate rows, flip `NO_VERSIONED`,
or close S3. `DETERMINISTIC_INCUMBENT_FORECAST_V0_2_REPLAY_IDENTITY_GRAIN_ROW_PRESENCE_IMPLEMENTED`
remains `false`. Historical pointer snapshots may remain `LIVE_POSTGRES_READ_IMPLEMENTED=false` or
`NO_BINDABLE_V0_2=true`. Jumping to row-population implementation now is forbidden.


### 4.5 V0.3 metric contract and threshold boundary

```text
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
V0_3_METRIC_CONTRACT_STATUS=PENDING_S1_ACCEPTANCE
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1
```

V0.3 continues to reference the formal V0.2 metric semantics. A changed
formula, mask, aggregation rule, or zero policy requires a separately versioned
contract; a metric name alone is not a definition. The contract must freeze the
following machine-readable fields before any TEST access:

```text
canonical_metric_id
formula_authority
eligible_mask
missing_day_policy
zero_denominator_policy
small_denominator_policy
double_zero_policy
decimal_precision
rounding_phase
aggregation_order
weighting_policy
minimum_sample_count
minimum_coverage_ratio
grouping_grain
date_error_sign_policy
peak_tie_break_policy
seven_day_window_date_basis
horizon_aggregation_policy
not_computable_policy
```

The current authority binds `daily_mae`, `daily_wape`, and `daily_smape` to
the P50 metric mask, uses exact Decimal arithmetic, applies final-boundary
`ROUND_HALF_EVEN`, reports WAPE denominator-zero as `NOT_COMPUTABLE`, treats
the sMAPE double-zero row as zero, and does not add an epsilon to an exact
denominator. It also binds the calculation grain, deduplication, farm-after-
subfarm aggregation order, unweighted arithmetic means, minimum comparable
rows, and the continuous-calendar-day seven-day window. V0.3 must preserve
those semantics unless a new contract version is independently accepted.

```text
MINIMUM_SAMPLE_COUNT=10
MINIMUM_COVERAGE_RATIO=UNRESOLVED_PENDING_V0_3_S1_METRIC_CONTRACT
MINIMUM_COVERAGE_RATIO_STATUS=UNRESOLVED_PENDING_V0_3_S1_METRIC_CONTRACT
GROUPING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_TARGET_DATE_X_FORECAST_CUTOFF_X_MODEL_IDENTITY_X_FORECAST_QUANTILE
REPORTING_GRAIN=SEASON_X_FARM_X_SUBFARM_X_VARIETY_X_HARVEST_BUSINESS_DATE
WEIGHTING_POLICY=UNWEIGHTED_ARITHMETIC_MEAN_AND_WAPE_ACTUAL_DENOMINATOR
SMALL_DENOMINATOR_POLICY=NO_EPSILON_EXACT_AUTHORITY_DENOMINATOR
MISSING_DAY_POLICY=REJECT_INCOMPLETE_WINDOW_AND_UNKNOWN_NOT_ZERO
DATE_ERROR_SIGN_POLICY=SIGNED_AND_ABSOLUTE_FIELDS_BOTH_REQUIRED
PEAK_TIE_BREAK_POLICY=EARLIEST_DATE_AND_EARLIEST_START_DATE
SEVEN_DAY_WINDOW_DATE_BASIS=CONTINUOUS_CALENDAR_DAYS_REJECT_INCOMPLETE_WINDOW
HORIZON_AGGREGATION_POLICY=REQUESTED_HORIZON_AND_EVALUATION_WINDOW_MUST_NOT_BE_CONFUSED
GENERIC_CUMULATIVE_ERROR_TERM_ALLOWED=false
GENERIC_SEASONAL_CUMULATIVE_ERROR_TERM_ALLOWED=false
GENERIC_PEAK_DATE_ERROR_TERM_ALLOWED=false
GENERIC_CUMULATIVE_ERROR_OCCURRENCES=0
GENERIC_SEASONAL_CUMULATIVE_ERROR_OCCURRENCES=0
```

The V0.3 metric gate uses `PASS`, `FAIL`, and `NOT_COMPUTABLE`: `PASS` means
the metric contract and required evidence are satisfied, `FAIL` means a
required contract or result check failed, and `NOT_COMPUTABLE` means the
authoritative denominator, complete window, or physical-alignment prerequisite
is unavailable. Metric-cell statuses remain those of the S3 authority,
including `COMPUTED`, `COMPARED`, `NOT_COMPUTABLE`, `NOT_VERIFIED`, and
`INSUFFICIENT_SAMPLE`.

Unless a future contract adds lower quantiles, `interval width` must not be
used as an ambiguous two-sided interval term. The current upper-quantile
semantics are:

```text
P80_UPPER_QUANTILE_SPREAD=P80-P50
P90_UPPER_QUANTILE_SPREAD=P90-P50
P80_COVERAGE=actual_target <= forecast_P80
P90_COVERAGE=actual_target <= forecast_P90
```

Coverage is meaningful only after Q2C physical alignment. S1 freezes the metric
definitions, threshold owner, threshold-setting process, and minimum coverage.
S3 derives baseline evidence only from TRAIN and VALIDATION. Before TEST is
opened, the following acceptance requirements apply; the `CURRENT_` values
below deliberately remain false until the evidence is accepted:

```text
CURRENT_MODEL_ACCEPTANCE_THRESHOLD_FREEZE_COMPLETE=false
CURRENT_METRIC_CONTRACT_FROZEN_BEFORE_TEST=false
CURRENT_THRESHOLDS_FROZEN_BEFORE_TEST=false
CURRENT_METRIC_SEMANTICS_CHANGE_AFTER_TEST_ACCESS=false

S3_ACCEPTANCE_REQUIRES_MODEL_ACCEPTANCE_THRESHOLD_FREEZE_COMPLETE=true
S3_ACCEPTANCE_REQUIRES_METRIC_CONTRACT_FROZEN_BEFORE_TEST=true
S3_ACCEPTANCE_REQUIRES_THRESHOLDS_FROZEN_BEFORE_TEST=true
```

Thresholds may use business requirements, TRAIN results, and VALIDATION results,
but may not be adjusted after TEST inspection. Any formula, mask, weight,
threshold, or aggregation change after TEST access requires a new metric
contract version, invalidates the old TEST conclusion, requires a new
independent authorization, and may not reuse the old TEST pass result.

### 4.6 V0.3-S4 — Parameter calibration, model optimization, and candidate selection

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

#### Validation experiment budget and candidate-selection protocol

Before any candidate experiment is executed, S4 must freeze one experiment
plan. The values below are a finite planning boundary, not an authorization to
run experiments:

```text
S4_A_ACCEPTANCE_REQUIRES_EXPERIMENT_PLAN_FROZEN=true
EXPERIMENT_PLAN_VERSION=v0.3-experiment-plan-v1
EXPERIMENT_PLAN_HASH=PENDING_EXECUTION
CANDIDATE_COUNT=8
CANDIDATE_IDS=01_parameter_calibration,02_quantile_calibration,03_phenology_offset,04_yield_parameter,05_marketable_rate,06_weather_response,07_harvest_efficiency,08_residual_feature
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
PRIMARY_SELECTION_METRIC=daily_wape
PRIMARY_SELECTION_METRIC_STATUS=PENDING_S1_METRIC_CONTRACT_ACCEPTANCE
REGRESSION_GUARDRAILS=daily_mae,cumulative_absolute_error_kg,single_day_peak_quantity_absolute_error_kg_q,sustained_7day_quantity_absolute_error_kg_q,P80_COVERAGE,P90_COVERAGE
GROUP_COVERAGE_REQUIREMENTS=ALL_SIX_REQUIRED_BREAKDOWN_AXES;MIN_COMPARABLE_ROWS_FOR_REPORTING=10;S2_COVERAGE_RATIO_REPORTED;NO_SILENT_EXCLUSION
SELECTION_RULE=MINIMIZE_PRIMARY_SELECTION_METRIC_SUBJECT_TO_GUARDRAILS_AND_COVERAGE
TIE_BREAK_RULE=LEXICOGRAPHIC_CANDIDATE_ID_AFTER_METRIC_ROUNDING_AND_GUARDRAIL_PASS
MULTIPLE_COMPARISON_POLICY=ADJUSTED_MULTI_CANDIDATE_COMPARISON
MULTIPLE_COMPARISON_ADJUSTMENT=HOLM_BONFERRONI_OVER_PREDECLARED_PRIMARY_METRIC_COMPARISONS
```

The candidate registry is closed before the first run. Every candidate must
have all of the following fields; `PENDING_EXECUTION` means that the future
subtask has not yet produced the artifact and is not evidence of completion:

```text
candidate_id=01_parameter_calibration
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=parameter_calibration_reduces_primary_metric_without_guardrail_regression
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=02_quantile_calibration
candidate_family=QUANTILE_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=quantile_calibration_improves_p80_p90_coverage_without_point_metric_regression
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=03_phenology_offset
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_phenology_offset_reduces_timing_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=04_yield_parameter
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_yield_parameter_calibration_reduces_quantity_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=05_marketable_rate
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_marketable_rate_calibration_reduces_marketable_quantity_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=06_weather_response
candidate_family=STRUCTURAL_MODEL_CANDIDATE
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=authorized_weather_response_features_reduce_residual_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=07_harvest_efficiency
candidate_family=PARAMETER_CALIBRATION
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=versioned_harvest_efficiency_calibration_reduces_peak_error
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

candidate_id=08_residual_feature
candidate_family=STRUCTURAL_MODEL_CANDIDATE
parent_model_id=V0_2_CURRENT_MODEL
hypothesis=authorized_residual_features_reduce_unexplained_residual
authorized_change=NOT_AUTHORIZED_UNTIL_S4_SUBTASK_AUTHORIZATION
feature_manifest=PENDING_EXECUTION
parameter_manifest=PENDING_EXECUTION
training_dataset_hash=PENDING_EXECUTION
validation_dataset_hash=PENDING_EXECUTION
code_commit_sha=PENDING_EXECUTION
dependency_lock_hash=PENDING_EXECUTION
random_seed_policy=FIXED_AND_RECORDED_PER_RUN
planned_run_count=4
selection_eligibility=REGISTERED_AND_GUARDRAIL_ELIGIBLE

S4_D_ACCEPTANCE_REQUIRES_ALL_VALIDATION_TRIALS_RECORDED=true
VALIDATION_LEDGER_MUST_RETAIN_FAILED_TRIALS=true
S4_D_ACCEPTANCE_REQUIRES_EXPERIMENT_BUDGET_NOT_EXCEEDED=true
S4_A_ACCEPTANCE_REQUIRES_CANDIDATE_REGISTRY_FROZEN=true
VALIDATION_SELECTION_STATUS=NO_ACCEPTABLE_CANDIDATE_IF_BUDGET_EXHAUSTED
```

#### Validation evaluation ledger and mechanical budget reconciliation

The validation budget counts model or parameter evaluation invocations, not
only successful metric results:

```text
VALIDATION_EVALUATION_UNIT=ONE_ACTUAL_MODEL_OR_PARAMETER_EVALUATION_INVOCATION
VALIDATION_EVALUATION_INVOCATION_TYPES=NORMAL_RUN,FAILED_RUN,ABORTED_RUN,CANCELLED_RUN,TIMEOUT_RUN,AUTOMATIC_RETRY,MANUAL_RETRY,OPERATOR_TRIGGERED_RERUN,DUPLICATE_INVOCATION
VALIDATION_EVALUATION_ID_REUSE_ALLOWED=false
VALIDATION_LEDGER_RECONCILIATION_REQUIRED=true
VALIDATION_BUDGET_FAIL_CLOSED=true
VALIDATION_LEDGER_COUNTS_ALL_STARTED_EVALUATIONS=true
S4_D_ACCEPTANCE_REQUIRES_ALL_ACTUAL_VALIDATION_INVOCATIONS_COUNTED=true
S4_D_ACCEPTANCE_REQUIRES_VALIDATION_LEDGER_RECONCILIATION=true
```

Every invocation that actually starts an evaluation gets a new
`evaluation_id` and a ledger row, even if it fails, is aborted, is cancelled,
times out, or is retried. A retry records `retry_of_evaluation_id` and never
overwrites the original row. Only a preflight that starts no model or parameter
evaluation may be excluded, and it must record the preflight evidence and the
explicit exclusion reason.

Each ledger row must contain:

```text
evaluation_id
experiment_plan_version
candidate_id
candidate_run_ordinal
global_evaluation_ordinal
invocation_type
trigger_source
started_at
finished_at
execution_status
metric_result_status
dataset_hash
validation_split_hash
code_commit_sha
parameter_manifest_hash
random_seed
retry_of_evaluation_id
counted_toward_budget
budget_count_reason
```

For every candidate, the reconciliation record must contain the following
fields. `actual_run_count` is a mechanical count of ledger rows, not a manual
summary:

```text
candidate_id
planned_run_count
actual_run_count=COUNT(evaluation_ledger_rows WHERE candidate_id=<candidate>)
remaining_run_budget=planned_run_count-actual_run_count
candidate_budget_status=PASS|FAIL|BLOCKED
```

The current, unexecuted plan has eight candidates and no actual evaluations:

| candidate_id | planned_run_count | actual_run_count | remaining_run_budget | candidate_budget_status |
| --- | ---: | ---: | ---: | --- |
| `01_parameter_calibration` | 4 | 0 | 4 | `BLOCKED` |
| `02_quantile_calibration` | 4 | 0 | 4 | `BLOCKED` |
| `03_phenology_offset` | 4 | 0 | 4 | `BLOCKED` |
| `04_yield_parameter` | 4 | 0 | 4 | `BLOCKED` |
| `05_marketable_rate` | 4 | 0 | 4 | `BLOCKED` |
| `06_weather_response` | 4 | 0 | 4 | `BLOCKED` |
| `07_harvest_efficiency` | 4 | 0 | 4 | `BLOCKED` |
| `08_residual_feature` | 4 | 0 | 4 | `BLOCKED` |

The following reconciliation must be calculated from the immutable ledger:

```text
actual_validation_evaluation_count=COUNT(all counted evaluation ledger rows)
MAX_VALIDATION_EVALUATIONS=32
MAX_RUNS_PER_CANDIDATE=4
actual_run_count <= planned_run_count
actual_run_count <= MAX_RUNS_PER_CANDIDATE
actual_validation_evaluation_count <= MAX_VALIDATION_EVALUATIONS
```

The reconciliation artifact must contain:

```text
experiment_plan_version
experiment_plan_hash
candidate_count
candidate_ids
planned_total_run_count
actual_total_run_count
per_candidate_planned_counts
per_candidate_actual_counts
failed_run_count
aborted_run_count
cancelled_run_count
timeout_run_count
automatic_retry_count
manual_retry_count
budget_status=PASS|FAIL|BLOCKED
reconciled_by
reconciled_at
artifact_hash
```

If any candidate or total count exceeds its frozen budget, the reconciliation
must set `budget_status=FAIL`, issue no selected candidate, forbid TEST access,
retain the incumbent, and make the selection ineligible. Deleted rows, changed
budgets, or post-hoc reclassification cannot restore PASS. Further experiments
require a new plan version, a preserved prior ledger, a new frozen budget, and
separate authorization.

```text
WHEN_VALIDATION_BUDGET_EXCEEDED:
VALIDATION_BUDGET_STATUS=FAIL
SELECTION_RESULT_ELIGIBLE=false
SELECTED_CANDIDATE_ID=NOT_ISSUED
TEST_ACCESS_MAY_BE_AUTHORIZED=false
MODEL_APPROVED_FOR_PILOT=false
INCUMBENT_MODEL_RETAINED=true
```

The registry includes successful, failed, aborted, rejected, and non-selected
runs. Validation candidates are finite, repeated runs are capped, manual
screening is recorded, and the search space cannot be expanded after the
budget is exhausted. A budget-exhausted search with no eligible candidate must
retain the incumbent:

```text
WHEN_VALIDATION_BUDGET_EXHAUSTED_WITHOUT_ELIGIBLE_CANDIDATE:
VALIDATION_SELECTION_STATUS=NO_ACCEPTABLE_CANDIDATE
TEST_ACCESS_MAY_BE_AUTHORIZED=false
INCUMBENT_MODEL_RETAINED=true
```

Any further experiment requires new independent validation data or a new
pre-approved experiment round, a new plan version, a new complete candidate
list, and separate implementation authorization. The prior ledger remains
immutable.

#### TEST prerequisite contract

The following is a prerequisite contract and is not current authorization:

```text
WHEN_SEPARATELY_AUTHORIZED:
AUTHORIZED_TEST_ACCESS_PREREQUISITES_FROZEN=true
AUTHORIZED_EXPERIMENT_PLAN_FROZEN=true
AUTHORIZED_EXPERIMENT_BUDGET_NOT_EXCEEDED=true
AUTHORIZED_ALL_VALIDATION_TRIALS_RECORDED=true
AUTHORIZED_CANDIDATE_REGISTRY_FROZEN=true
SELECTED_CANDIDATE_ID=PENDING_SELECTION
SELECTED_CANDIDATE_COUNT=1
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
ACCEPTANCE_THRESHOLD_MANIFEST_HASH=PENDING_EXECUTION
SELECTION_DECISION_ARTIFACT_HASH=PENDING_EXECUTION
AUTHORIZED_TEST_ACCESS_GRANTED=true
```

In the current planning document no TEST authorization has been issued:

```text
CURRENT_TEST_ACCESS_PREREQUISITES_FROZEN=false
CURRENT_TEST_ACCESS_AUTHORIZED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED=false
TEST_ACCESS_CURRENTLY_AUTHORIZED_IS_DERIVED_ALIAS=true
S4_D_ACCEPTANCE_MAY_REQUEST_SEPARATE_TEST_AUTHORIZATION=true
PLANNING_DOCUMENT_DOES_NOT_AUTHORIZE_TEST_ACCESS=true
TEST_ACCESS_AUTHORIZATION_ID=NOT_ISSUED
AUTHORIZED_PR_NUMBER=NOT_ISSUED
AUTHORIZED_HEAD_SHA=NOT_ISSUED
AUTHORIZED_DATASET_HASH=NOT_ISSUED
AUTHORIZED_TEST_SPLIT_HASH=NOT_ISSUED
AUTHORIZED_SELECTED_CANDIDATE_ID=NOT_ISSUED
AUTHORIZED_INCUMBENT_MODEL_ID=NOT_ISSUED
AUTHORIZED_METRIC_CONTRACT_VERSION=NOT_ISSUED
AUTHORIZED_THRESHOLD_MANIFEST_HASH=NOT_ISSUED
AUTHORIZED_BY=NOT_ISSUED
AUTHORIZED_AT=NOT_ISSUED
```

The current planning state is explicitly unexecuted:

```text
CURRENT_EXPERIMENT_PLAN_FROZEN=false
CURRENT_CANDIDATE_REGISTRY_FROZEN=false
CURRENT_MODEL_ACCEPTANCE_THRESHOLD_FREEZE_COMPLETE=false
CURRENT_ALL_VALIDATION_TRIALS_RECORDED=false
CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS=NOT_EVALUATED
EXPERIMENT_BUDGET_EVALUATION_STATUS_ENUM=NOT_EVALUATED|PASS|FAIL|BLOCKED
S4_D_ACCEPTANCE_REQUIRES_EXPERIMENT_BUDGET_EVALUATION_STATUS_PASS=true
```

`CURRENT_EXPERIMENT_BUDGET_EVALUATION_STATUS` is the single current state for
the budget evaluation. `NOT_EVALUATED` means that no accepted reconciliation
artifact exists yet; `PASS` means the mechanically counted ledger is within the
frozen limits; `FAIL` means a limit was exceeded; and `BLOCKED` means the
reconciliation cannot yet establish a valid result. None of these states grants
TEST access. The Completion Gate Registry row
`MODEL_VALIDATION_BUDGET_COMPLIANT` must remain consistent with this field.

S3 uses TRAIN and VALIDATION for diagnosis and candidate direction. S4 may
request separate TEST authorization only after the candidate and thresholds
are locked. Only the locked candidate and locked incumbent may enter the final
TEST comparison. If the candidate fails:

```text
WHEN_SELECTED_CANDIDATE_TEST_FAILED:
SELECTED_CANDIDATE_STATUS=REJECTED
MODEL_APPROVED_FOR_PILOT=false
INCUMBENT_MODEL_RETAINED=true
```

The same TEST cannot be used for another tuning cycle. A subsequent attempt
requires unused test data, a new dataset version, a new candidate registration,
separate authorization, and a new review cycle.

If S1 proves an external holdout feasible, it is used once for final evaluation
only and never for feature selection, parameter selection, or threshold tuning.
Until that feasibility decision is accepted:

```text
CURRENT_EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
CURRENT_EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
CURRENT_CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false
CURRENT_S1_HOLDOUT_FEASIBILITY_DECISION=NOT_EVALUATED
CURRENT_S1_HOLDOUT_FEASIBILITY_ARTIFACT_HASH=PENDING_EXECUTION
CURRENT_S1_HOLDOUT_FEASIBILITY_REVIEWED=false
CURRENT_S1_HOLDOUT_FEASIBILITY_CONDITIONAL_BRANCH=NONE_ACTIVE
CURRENT_EXTERNAL_HOLDOUT_NOT_APPLICABLE=false
```

The decision field is intentionally fail-closed. Its schema invariant and
current-state meanings are:

```text
S1_HOLDOUT_FEASIBILITY_DECISION_ENUM=NOT_EVALUATED|FEASIBLE|NOT_FEASIBLE|BLOCKED
S1_HOLDOUT_FEASIBILITY_DECISION_NOT_EVALUATED=NO_ACCEPTED_FEASIBILITY_REVIEW
S1_HOLDOUT_FEASIBILITY_DECISION_FEASIBLE=INDEPENDENT_HOLDOUT_CAN_BE_BUILT
S1_HOLDOUT_FEASIBILITY_DECISION_NOT_FEASIBLE=FORMAL_EVIDENCE_PROVES_NO_INDEPENDENT_HOLDOUT
S1_HOLDOUT_FEASIBILITY_DECISION_BLOCKED=REQUIRED_DATA_IDENTITY_OWNERSHIP_OR_EVIDENCE_MISSING
```

The reviewed feasibility outcome is represented by exactly one of the two
mutually exclusive branches below. No branch is active before the independent
review is complete. A `BLOCKED` feasibility decision remains blocked and never
maps to `NOT_APPLICABLE`.

```text
WHEN_S1_HOLDOUT_FEASIBILITY_REVIEWED_AND_NOT_FEASIBLE:
ALLOWED_NOT_APPLICABLE_GATE=MODEL_EXTERNAL_HOLDOUT_FEASIBILITY
S1_HOLDOUT_FEASIBILITY_DECISION=NOT_FEASIBLE
S1_HOLDOUT_FEASIBILITY_ARTIFACT_HASH=<REAL_ACCEPTED_ARTIFACT_HASH>
S1_HOLDOUT_FEASIBILITY_REVIEWED=true

EXTERNAL_HOLDOUT_GATE_STATUS=NOT_APPLICABLE
EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=NOT_APPLICABLE
CROSS_FARM_GENERALIZATION_CLAIM_ALLOWED=false

NOT_FEASIBLE_REQUIRES_REAL_ACCEPTED_ARTIFACT_HASH=true
NOT_FEASIBLE_REQUIRES_INDEPENDENT_REVIEW=true
NOT_FEASIBLE_MAY_NOT_USE_PENDING_EXECUTION_HASH=true
NOT_FEASIBLE_MAY_NOT_BE_INFERRED_FROM_MISSING_DATA=true
NOT_FEASIBLE_MAY_NOT_BE_INFERRED_FROM_MISSING_PERMISSION=true
EXTERNAL_HOLDOUT_NOT_APPLICABLE_ALLOWED=true
NOT_FEASIBLE_BRANCH_IS_ONLY_SOURCE_OF_EXTERNAL_HOLDOUT_NOT_APPLICABLE=true
```

```text
WHEN_S1_HOLDOUT_FEASIBILITY_REVIEWED_AND_FEASIBLE:
S1_HOLDOUT_FEASIBILITY_DECISION=FEASIBLE
S1_HOLDOUT_FEASIBILITY_ARTIFACT_HASH=<REAL_ACCEPTED_ARTIFACT_HASH>
S1_HOLDOUT_FEASIBILITY_REVIEWED=true

EXTERNAL_HOLDOUT_GATE_STATUS=BLOCKED
EXTERNAL_HOLDOUT_GATE_BLOCK_REASON=NOT_YET_EXECUTED

FEASIBLE_REQUIRES_REAL_ACCEPTED_ARTIFACT_HASH=true
FEASIBLE_REQUIRES_INDEPENDENT_REVIEW=true
EXTERNAL_HOLDOUT_NOT_APPLICABLE_ALLOWED=false
EXTERNAL_HOLDOUT_GATE_PASS_IMPLIED=false
EXTERNAL_HOLDOUT_MATERIALIZED=false
EXTERNAL_HOLDOUT_ACCESS_AUTHORIZED=false
TEST_ACCESS_AUTHORIZED=false
```

The two reviewed branches are exhaustive and mutually exclusive:

```text
S1_HOLDOUT_FEASIBILITY_REVIEWED_BRANCH_ENUM=FEASIBLE|NOT_FEASIBLE
S1_HOLDOUT_FEASIBILITY_BRANCHES_MUTUALLY_EXCLUSIVE=true
S1_HOLDOUT_FEASIBILITY_REVIEWED_REQUIRES_EXACTLY_ONE_BRANCH=true
FEASIBLE_BRANCH_AND_NOT_FEASIBLE_BRANCH_SIMULTANEOUSLY_ACTIVE=false
NO_BRANCH_ACTIVE_BEFORE_REVIEW=true
FEASIBLE_BRANCH_EXTERNAL_HOLDOUT_GATE_RESULT=BLOCKED
NOT_FEASIBLE_BRANCH_EXTERNAL_HOLDOUT_GATE_RESULT=NOT_APPLICABLE
FEASIBLE_BRANCH_MAY_PRODUCE_NOT_APPLICABLE=false
NOT_FEASIBLE_BRANCH_MAY_PRODUCE_NOT_APPLICABLE=true
```

`NOT_APPLICABLE` is the existing non-blocking Gate status value. It is
permitted only in the reviewed `NOT_FEASIBLE` branch. A reviewed `FEASIBLE`
branch leaves the conditional Gate blocked until the external holdout is
materialized and separately accepted; feasibility alone does not authorize
TEST access, external-holdout access, a PASS result, or a cross-farm
generalization claim.

The bare fields in the two blocks above are future conditional-example fields;
current facts remain `CURRENT_`-prefixed. No future artifact hash is asserted
by this planning document.

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
selection rationale, and a reproducible pilot-approval and rollback manifest.

### 4.7 V0.3-S5 — Business forecast operations, explanation, and continuous evaluation

```text
SLICE=V0.3-S5
ENGLISH_ID=BUSINESS_FORECAST_OPERATIONS_EXPLANATION_AND_CONTINUOUS_EVALUATION
```

#### Objective

S5 operates the selected pilot-approved model in the pilot workflow and keeps the
forecast-to-actual loop auditable. It addresses explanation and operations,
not cross-factory routing or automatic production control.

#### Required capabilities

The pilot surface must support:

- comparison of the current forecast with the previous forecast;
- comparison of the current model with the previous pilot-approved model;
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
and a traceable record of business adoption or non-adoption. S5 completion means
only that pilot operations are ready:

```text
S5_ACCEPTANCE_REQUIRES_PILOT_OPERATIONS_READY=true
```

It does not mean that the real-season pilot succeeded or that business
acceptance occurred.

### 4.8 V0.3-S6 — Real-season business pilot and release acceptance

```text
SLICE=V0.3-S6
ENGLISH_ID=REAL_SEASON_BUSINESS_PILOT_AND_RELEASE_ACCEPTANCE
```

#### Objective

S6 runs the pilot-approved model through a real season and records technical,
model, and business acceptance. S6 is the final pilot and acceptance slice,
not an authorization to expand into unrelated operational automation.

#### Minimum pilot scope

```text
FARMS>=2
VARIETIES>=2
S6_ACCEPTANCE_REQUIRES_FIXED_FORECAST_CADENCE=true
S6_ACCEPTANCE_REQUIRES_ACTUAL_RESULT_FEEDBACK_COMPLETE=true
```

The actual pilot scope, source-owner authorization, measurement boundary,
security handling, and business acceptance roles must be documented before
real business data is imported. This plan does not itself grant that
authorization.

The lifecycle states are:

```text
CANDIDATE_SELECTED
CANDIDATE_TEST_PASSED
MODEL_APPROVED_FOR_PILOT
PILOT_OPERATIONS_READY
PILOT_RUNNING
V0_3_BUSINESS_PILOT_ACCEPTED
V0_3_BUSINESS_PILOT_FAILED
PRODUCTION_RELEASE_APPROVED
```

S4 may produce `MODEL_APPROVED_FOR_PILOT=true` at most. S5 owns pilot-operation
readiness. S6 is the sole owner of `V0_3_BUSINESS_PILOT_ACCEPTED` and
`V0_3_BUSINESS_PILOT_FAILED`. Business adoption records are not business
acceptance records. If the pilot fails or is not accepted:

```text
WHEN_V0_3_BUSINESS_PILOT_FAILED_OR_NOT_ACCEPTED:
CURRENT_V0_3_COMPLETE=false
CURRENT_PRODUCTION_RELEASE_APPROVED=false
PILOT_MODEL_ROLLBACK_REQUIRED=true
```

V0.3 does not authorize production release:

```text
CURRENT_PRODUCTION_RELEASE_APPROVED=false
PRODUCTION_RELEASE_IN_V0_3_SCOPE=false
```

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
- `single_day_peak_date_signed_error_days_q` and
  `single_day_peak_date_absolute_error_days_q`;
- `sustained_7day_start_date_signed_error_days_q` and
  `sustained_7day_start_date_absolute_error_days_q`;
- `cumulative_signed_error_kg`, `cumulative_absolute_error_kg`,
  `cumulative_signed_relative_error`, and
  `cumulative_absolute_relative_error`;
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

In this gate, `REAL_DATASET_FROZEN=true` means the final S2 materialized
dataset has passed split and hash re-acceptance; it does not mean that S1 froze
the final cleaned row set.

```text
WHEN_ALL_REQUIRED_COMPLETION_GATES_ACCEPTED:
V0_3_S1_COMPLETE=true
V0_3_S2_COMPLETE=true
V0_3_S3_COMPLETE=true
V0_3_S4_COMPLETE=true
V0_3_S5_COMPLETE=true
V0_3_S6_COMPLETE=true

REAL_DATA_CONTRACT_ACCEPTED=true
REAL_DATASET_FROZEN=true
MATERIALIZED_DATASET_FREEZE_COMPLETE=true
FINAL_SPLIT_MANIFEST_ACCEPTED=true
FINAL_DATASET_HASHES_ACCEPTED=true
DATA_QUALITY_GATE_PASSED=true
POINT_IN_TIME_BACKTEST_PASSED=true
CURRENT_MODEL_BASELINE_COMPLETE=true
ERROR_DIAGNOSIS_COMPLETE=true
SELECTED_MODEL_HOLDOUT_TEST_PASSED=true
PILOT_MODEL_RELEASE_MANIFEST_COMPLETE=true
MODEL_APPROVED_FOR_PILOT=true
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

## 7. V0.3 completion evidence matrix

Every final gate must be represented by an evidence row containing:

```text
gate_id
gate_class
required_or_conditional
owner_role
authoritative_artifact
artifact_identity_source
artifact_hash_or_run_id
metric_contract_version
acceptance_threshold_source
acceptance_threshold
allowed_not_applicable_condition
status
block_reason
reviewer_role
reviewer
reviewed_at
notes
```

Allowed statuses are only:

```text
PASS
FAIL
BLOCKED
NOT_APPLICABLE
```

The following is the V0.3 Completion Gate Registry. Each row is independent;
the current planning document deliberately records every row as `BLOCKED`.
Every required row uses `NOT_YET_EXECUTED`; the only initial block-reason
exception is the single conditional external-holdout row, which uses
`FEASIBILITY_NOT_YET_ACCEPTED`. No future hash, run ID, reviewer name, or review
timestamp is invented here.

```text
REQUIRED_GATE_INITIAL_BLOCK_REASON=NOT_YET_EXECUTED
CONDITIONAL_EXTERNAL_HOLDOUT_INITIAL_BLOCK_REASON=FEASIBILITY_NOT_YET_ACCEPTED
OTHER_INITIAL_BLOCK_REASON_ALLOWED=false
REQUIRED_GATE_COUNT=41
REQUIRED_GATE_NOT_YET_EXECUTED_COUNT=41
REQUIRED_GATE_OTHER_INITIAL_BLOCK_REASON_COUNT=0
CONDITIONAL_HOLDOUT_GATE_COUNT=1
CONDITIONAL_HOLDOUT_FEASIBILITY_REASON_COUNT=1
```

The registry audit classifies each row by whether its acceptance threshold is
structural or quantitative. Structural gates have executable conditions now;
only quantitative gates wait for a separately frozen numeric threshold before
TEST authorization.

```text
STRUCTURAL_GATE_COUNT=38
STRUCTURAL_GATE_PENDING_NUMERIC_THRESHOLD_COUNT=0
QUANTITATIVE_GATE_PENDING_PRE_TEST_THRESHOLD_COUNT=4
```

| gate_id | gate_class | required_or_conditional | owner_role | authoritative_artifact | artifact_identity_source | artifact_hash_or_run_id | metric_contract_version | acceptance_threshold_source | acceptance_threshold | allowed_not_applicable_condition | status | block_reason | reviewer_role | reviewer | reviewed_at | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `SLICE_S1_COMPLETE` | technical | required | `v0_3_plan_owner` | S1 acceptance package | governed manifest | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | S1 acceptance criteria | `SLICE_ACCEPTANCE_CRITERIA_SATISFIED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `SLICE_S2_COMPLETE` | technical | required | `data_governance_owner` | S2 acceptance package | materialized dataset manifest | `f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f` | `NOT_APPLICABLE_FOR_THIS_GATE` | S2 acceptance criteria | `SLICE_ACCEPTANCE_CRITERIA_SATISFIED` | none | `PASS` | `NONE` | `COORDINATOR` | `COORDINATOR` | `2026-08-23T13:22:00Z` | `PR296_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6; DATASET=source-002/e5-live-v1; IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785; V0_3_S3_AUTHORIZED=false; TEST_REMAINS_SEALED=true; USER_WAIVED_THIRD_PARTY_REVIEW=true; CLOSEOUT=s2-slice-complete-registry-closeout-v1; S2_ACCEPTED_DOES_NOT_IMPLY_S3=true` |
| `SLICE_S3_COMPLETE` | model | required | `model_validation_owner` | S3 backtest package | backtest manifest | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S3 acceptance criteria | `ALL_S3_REQUIRED_GATES_PASS` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `SLICE_S4_COMPLETE` | model | required | `model_selection_owner` | S4 selection package | experiment manifest | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | S4 acceptance criteria | `ALL_S4_REQUIRED_GATES_PASS` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `SLICE_S5_COMPLETE` | technical | required | `pilot_operations_owner` | S5 operations package | pilot operations manifest | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | S5 acceptance criteria | `SLICE_ACCEPTANCE_CRITERIA_SATISFIED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `SLICE_S6_COMPLETE` | business | required | `business_pilot_owner` | S6 pilot acceptance package | pilot acceptance manifest | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | S6 acceptance criteria | `SLICE_ACCEPTANCE_CRITERIA_SATISFIED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_UNIQUE_ALEMBIC_HEAD` | technical | required | `engineering_release_owner` | migration head output | exact revision and run ID | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | one expected head | `UNIQUE_HEAD_COUNT_EQUALS_1` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_POSTGRESQL_E2E` | technical | required | `engineering_test_owner` | PostgreSQL E2E report | exact-head CI run ID | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | required PostgreSQL jobs pass | `ALL_REQUIRED_POSTGRESQL_JOBS_PASS` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_BROWSER_E2E` | technical | required | `frontend_test_owner` | browser E2E report | exact-head CI run ID | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | desktop and mobile jobs pass | `DESKTOP_AND_MOBILE_BROWSER_FLOWS_PASS` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_REQUIRED_CI_JOBS` | technical | required | `engineering_release_owner` | CI job registry | exact-head CI run ID | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | all required jobs pass | `ALL_REQUIRED_CI_JOBS_PASS` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_DETERMINISTIC_REPLAY` | technical | required | `engineering_test_owner` | replay evidence package | replay manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | same input produces same identity | `SAME_INPUT_PRODUCES_SAME_CANONICAL_IDENTITY` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_LINEAGE_INTEGRITY` | technical | required | `data_governance_owner` | lineage and correction ledger | lineage manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | every accepted row has lineage | `EVERY_ACCEPTED_ROW_HAS_LINEAGE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `TECH_RELEASE_MANIFEST_INTEGRITY` | technical | required | `engineering_release_owner` | pilot release manifest | manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | code, data, model, and parameter identities bind | `ALL_REQUIRED_IDENTITIES_HASH_VERIFIED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_Q2C_PHYSICAL_ALIGNMENT` | model | required | `data_governance_owner` | Q2C decision package | attestation and decision hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | one closed Q2C outcome | `EXACTLY_ONE_Q2C_TARGET_PATH_ACCEPTED_AND_FORECAST_LABEL_PHYSICAL_BOUNDARIES_MATCH` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_MATERIALIZED_DATASET_ACCEPTED` | model | required | `data_governance_owner` | S2 materialized dataset package | dataset manifest hash | `f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | final rowset and lineage accepted | `FINAL_ROWSET_MANIFEST_LINEAGE_EXCLUSION_CORRECTION_AND_CONTENT_HASH_ALL_ACCEPTED` | none | `PASS` | `NONE` | `COORDINATOR` | `COORDINATOR` | `2026-08-23T13:22:00Z` | `PR296_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6; DATASET=source-002/e5-live-v1; IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785; V0_3_S3_AUTHORIZED=false; TEST_REMAINS_SEALED=true; USER_WAIVED_THIRD_PARTY_REVIEW=true` |
| `MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE` | model | required | `data_governance_owner` | S2 freeze record | materialized dataset hash | `f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | freeze and immutability accepted | `FINAL_MATERIALIZED_DATASET_IDENTITY_AND_CONTENT_HASH_FROZEN` | none | `PASS` | `NONE` | `COORDINATOR` | `COORDINATOR` | `2026-08-23T13:22:00Z` | `PR296_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6; DATASET=source-002/e5-live-v1; IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785; V0_3_S3_AUTHORIZED=false; TEST_REMAINS_SEALED=true; USER_WAIVED_THIRD_PARTY_REVIEW=true` |
| `MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED` | model | required | `model_validation_owner` | final split manifest | split manifest hash | `f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | TRAIN/VALIDATION/TEST accepted | `TRAIN_VALIDATION_TEST_IDENTITIES_HASHES_AND_NON_OVERLAP_RULES_ALL_ACCEPTED` | none | `PASS` | `NONE` | `COORDINATOR` | `COORDINATOR` | `2026-08-23T13:22:00Z` | `PR296_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6; DATASET=source-002/e5-live-v1; IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785; V0_3_S3_AUTHORIZED=false; TEST_REMAINS_SEALED=true; USER_WAIVED_THIRD_PARTY_REVIEW=true` |
| `MODEL_FINAL_DATASET_HASHES_ACCEPTED` | model | required | `data_governance_owner` | final dataset hash package | dataset hash set | `f7856e99ded3cf4c56f1d6e4b283ccd903e35302cb06db606c6446419d76e02f` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | all materialized hashes accepted | `ALL_TRAIN_VALIDATION_TEST_AND_HOLDOUT_HASH_IDENTITIES_ACCEPTED` | none | `PASS` | `NONE` | `COORDINATOR` | `COORDINATOR` | `2026-08-23T13:22:00Z` | `PR296_MERGE=9aa4de9367d065dcb642ae233325640d24da69d6; DATASET=source-002/e5-live-v1; IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785; V0_3_S3_AUTHORIZED=false; TEST_REMAINS_SEALED=true; USER_WAIVED_THIRD_PARTY_REVIEW=true; TRAIN/VALIDATION hashes bound; TEST is sealed placeholder hashes not evaluation; EXTERNAL_HOLDOUT_NOT_APPLICABLE because S1 owner decision REVIEWED_NOT_FEASIBLE (S1-HOLDOUT-FEASIBILITY). Do not claim holdout bytes exist.` |
| `MODEL_DATA_QUALITY_GATE` | model | required | `data_quality_owner` | quality and exclusion report | quality report hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | quality thresholds and exclusions accepted | `PENDING_PRE_TEST_THRESHOLD_FREEZE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_POINT_IN_TIME_REPLAY` | model | required | `model_validation_owner` | historical replay package | replay manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | input and label cutoffs bind | `INPUT_AND_LABEL_CUTOFF_WINNER_LINEAGE_AND_REVISION_RULES_REPLAY_DETERMINISTICALLY` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_FUTURE_LEAKAGE_AUDIT` | model | required | `model_validation_owner` | leakage audit package | audit run ID and hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | no future input or label leakage | `NO_FUTURE_INPUT_OR_LABEL_LEAKAGE_IN_AUDIT` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_CURRENT_BASELINE_COMPLETE` | model | required | `model_validation_owner` | current-model baseline package | baseline manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | all required horizons and groups reported | `ALL_REQUIRED_HORIZONS_GROUPS_AND_METRICS_REPORTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_ERROR_DIAGNOSIS_COMPLETE` | model | required | `model_validation_owner` | attribution matrix package | attribution manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | methods and evidence are complete | `ALL_REQUIRED_ATTRIBUTION_METHODS_AND_EVIDENCE_RECORDED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_EXPERIMENT_PLAN_FROZEN` | model | required | `model_selection_owner` | experiment plan and candidate registry | plan hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | finite budget and candidates frozen | `FINITE_CANDIDATE_LIST_AND_BUDGET_FROZEN` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_VALIDATION_BUDGET_COMPLIANT` | model | required | `model_selection_owner` | validation ledger | ledger hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | budget not exceeded and all trials recorded | `ALL_STARTED_EVALUATIONS_RECORDED_LEDGER_RECONCILIATION_PASS_AND_NO_LIMIT_EXCEEDED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_CANDIDATE_REGISTRY_FROZEN` | model | required | `model_selection_owner` | candidate registry | registry hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | complete finite registry accepted | `FINITE_CANDIDATE_REGISTRY_AND_IDENTITIES_ACCEPTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_TEST_ACCESS_SEPARATELY_AUTHORIZED` | model | required | `model_selection_owner` | independent TEST authorization record | authorization ID and dataset hashes | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | authorized head, split, candidate, and metric version match | `AUTHORIZATION_ID_PR_HEAD_DATASET_SPLIT_CANDIDATE_INCUMBENT_METRIC_AND_THRESHOLD_ALL_MATCH` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_LOCKED_TEST_COMPLETE` | model | required | `model_validation_owner` | locked TEST result | test run ID and result hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | only locked candidate and incumbent evaluated | `LOCKED_CANDIDATE_AND_INCUMBENT_EVALUATED_ON_AUTHORIZED_TEST` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_PRIMARY_METRIC_ACCEPTED` | model | required | `model_validation_owner` | metric result package | metric manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | primary metric and status pass | `PENDING_PRE_TEST_THRESHOLD_FREEZE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_REGRESSION_GUARDRAILS_ACCEPTED` | model | required | `model_validation_owner` | regression guardrail package | guardrail manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | every guardrail passes or is explicitly not computable | `PENDING_PRE_TEST_THRESHOLD_FREEZE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_QUANTILE_CALIBRATION_ACCEPTED` | model | required | `model_validation_owner` | quantile calibration package | calibration manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | P80/P90 semantics and coverage accepted | `PENDING_PRE_TEST_THRESHOLD_FREEZE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_PILOT_ARTIFACT_MANIFEST_COMPLETE` | model | required | `model_selection_owner` | pilot model release manifest | model manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | code, data, parameter, artifact, and rollback identities bind | `CODE_DATA_FEATURE_PARAMETER_MODEL_AND_ROLLBACK_IDENTITIES_PRESENT_AND_HASH_VERIFIED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_APPROVED_FOR_PILOT` | model | required | `model_selection_owner` | pilot approval record | approval record ID and manifest hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | locked TEST and rollback evidence pass | `ALL_REQUIRED_PRECEDING_MODEL_GATES_PASS_AND_PILOT_APPROVAL_RECORD_ACCEPTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `MODEL_EXTERNAL_HOLDOUT_FEASIBILITY` | model | conditional | `model_validation_owner` | S1 holdout feasibility decision | feasibility artifact hash | `PENDING_EXECUTION` | `PENDING_S1_METRIC_CONTRACT_FREEZE` | feasibility decision reviewed | `FEASIBILITY_DECISION_REVIEWED` | only after reviewed `NOT_FEASIBLE` decision | `BLOCKED` | `FEASIBILITY_NOT_YET_ACCEPTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_DATA_OWNER_ACCEPTANCE` | business | required | `business_data_owner_role` | governed source acceptance | attestation hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | formal source-owner acceptance | `FORMAL_SOURCE_OWNER_ACCEPTANCE_PRESENT` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_TARGET_CONTRACT_ACCEPTANCE` | business | required | `business_owner_role` | target semantic acceptance | Q2C decision hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | physical target boundary accepted | `PHYSICAL_TARGET_BOUNDARY_ACCEPTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_PILOT_SCOPE_ACCEPTANCE` | business | required | `business_pilot_owner` | pilot scope record | scope manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | farms, varieties, cadence, and purpose accepted | `PILOT_SCOPE_FIELDS_AND_PURPOSE_ACCEPTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_PILOT_OPERATIONS_READY` | business | required | `pilot_operations_owner` | operations readiness package | readiness manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | run, compare, explain, and feedback paths ready | `RUN_COMPARE_EXPLAIN_FEEDBACK_PATHS_READY` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_REAL_SEASON_EXECUTION_COMPLETE` | business | required | `business_pilot_owner` | real-season pilot ledger | pilot run manifest hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | actual feedback and cadence complete | `CADENCE_AND_ACTUAL_FEEDBACK_COMPLETE` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_ADOPTION_AND_NON_ADOPTION_LEDGER_COMPLETE` | business | required | `business_pilot_owner` | adoption ledger | ledger hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | adoption and non-adoption reasons recorded | `ADOPTION_AND_NON_ADOPTION_REASONS_RECORDED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_FALSE_POSITIVE_FALSE_NEGATIVE_REVIEW_COMPLETE` | business | required | `business_pilot_owner` | business error review | review record ID and hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | false-positive and false-negative review accepted | `FALSE_POSITIVE_AND_FALSE_NEGATIVE_REVIEW_ACCEPTED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |
| `BUSINESS_PILOT_ACCEPTANCE_DECISION` | business | required | `business_acceptance_owner` | pilot accept/fail decision | decision record ID and hash | `PENDING_EXECUTION` | `NOT_APPLICABLE_FOR_THIS_GATE` | explicit accept or fail decision recorded | `EXPLICIT_PILOT_ACCEPT_OR_FAIL_RECORDED` | none | `BLOCKED` | `NOT_YET_EXECUTED` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_INDEPENDENT_REVIEW` | `PENDING_EXECUTION` |

The table above is the single runtime authority. There is no separate initial
status table: every row already contains its current `status`, `block_reason`,
`reviewer`, `reviewed_at`, and evidence identity fields.

```text
COMPLETION_GATE_REGISTRY_IS_AUTHORITATIVE=true
LEGACY_COMPLETION_BOOLEANS_ARE_DERIVED_ONLY=true
LEGACY_COMPLETION_BOOLEANS_MAY_OVERRIDE_GATE_STATUS=false
COMPLETION_GATE_CURRENT_STATUS_MUST_MATCH_CURRENT_STATE_FIELDS=true
UNEXECUTED_REQUIRED_GATES_MUST_REMAIN_BLOCKED=true
```

`NOT_APPLICABLE` is permitted only for
`MODEL_EXTERNAL_HOLDOUT_FEASIBILITY`, and only after the reviewed S1 artifact
proves the reviewed feasibility decision has the `NOT_FEASIBLE` value. All required gates must
be `PASS`; no required gate may use `NOT_APPLICABLE` to bypass evidence.
`FULL_SUITE_CI_PASSED` proves only a technical gate. Browser E2E does not prove
model accuracy, PostgreSQL E2E does not prove real-data representativeness, and
a skipped `full-suite-canary` is never converted to `PASS`.

The existing completion booleans map one-to-one to gate IDs as follows:

```text
V0_3_S1_COMPLETE=SLICE_S1_COMPLETE
V0_3_S2_COMPLETE=SLICE_S2_COMPLETE
V0_3_S3_COMPLETE=SLICE_S3_COMPLETE
V0_3_S4_COMPLETE=SLICE_S4_COMPLETE
V0_3_S5_COMPLETE=SLICE_S5_COMPLETE
V0_3_S6_COMPLETE=SLICE_S6_COMPLETE
REAL_DATA_CONTRACT_ACCEPTED=MODEL_Q2C_PHYSICAL_ALIGNMENT
REAL_DATASET_FROZEN=MODEL_MATERIALIZED_DATASET_ACCEPTED
MATERIALIZED_DATASET_FREEZE_COMPLETE=MODEL_MATERIALIZED_DATASET_FREEZE_COMPLETE
FINAL_SPLIT_MANIFEST_ACCEPTED=MODEL_FINAL_SPLIT_MANIFEST_ACCEPTED
FINAL_DATASET_HASHES_ACCEPTED=MODEL_FINAL_DATASET_HASHES_ACCEPTED
DATA_QUALITY_GATE_PASSED=MODEL_DATA_QUALITY_GATE
POINT_IN_TIME_BACKTEST_PASSED=MODEL_POINT_IN_TIME_REPLAY
CURRENT_MODEL_BASELINE_COMPLETE=MODEL_CURRENT_BASELINE_COMPLETE
ERROR_DIAGNOSIS_COMPLETE=MODEL_ERROR_DIAGNOSIS_COMPLETE
SELECTED_MODEL_HOLDOUT_TEST_PASSED=MODEL_LOCKED_TEST_COMPLETE
PILOT_MODEL_RELEASE_MANIFEST_COMPLETE=MODEL_PILOT_ARTIFACT_MANIFEST_COMPLETE
MODEL_APPROVED_FOR_PILOT=MODEL_APPROVED_FOR_PILOT
BUSINESS_PILOT_COMPLETED=BUSINESS_REAL_SEASON_EXECUTION_COMPLETE
BUSINESS_ACCEPTANCE_RECORDED=BUSINESS_PILOT_ACCEPTANCE_DECISION
POSTGRESQL_E2E_PASSED=TECH_POSTGRESQL_E2E
BROWSER_E2E_PASSED=TECH_BROWSER_E2E
FULL_SUITE_CI_PASSED=TECH_REQUIRED_CI_JOBS
UNIQUE_ALEMBIC_HEAD=TECH_UNIQUE_ALEMBIC_HEAD
```

```text
WHEN_ALL_REQUIRED_COMPLETION_GATES_ACCEPTED:
ALL_COMPLETION_BOOLEANS_MAPPED_TO_GATE_IDS=true
UNMAPPED_COMPLETION_BOOLEAN_COUNT=0
ALL_REQUIRED_TECHNICAL_GATES=PASS
ALL_REQUIRED_MODEL_GATES=PASS
ALL_REQUIRED_BUSINESS_GATES=PASS
ALL_CONDITIONAL_GATES=PASS_OR_PREAUTHORIZED_NOT_APPLICABLE
```

The last four values are completion conditions, not current assertions. The
completion marker may be used only after the registry contains accepted rows
for every required gate and an allowed conditional gate disposition.

## 8. Authorization sequence and dependency gates

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

## 9. Data, privacy, and reproducibility boundaries

Real business data may be used in V0.3 only after a separate authorization has
confirmed the source owner, purpose, approved dataset identity, physical
measurement boundary, historical visibility, access controls, and retention
rules. No real data is added by this planning document.

Every accepted dataset or model result must be reproducible from a stable
manifest. The manifest must identify source version, time boundary, inclusion
and exclusion rules, feature set, parameters, code commit, model artifact, and
random seed where applicable. Sensitive raw rows, credentials, personal data,
and private source URLs must not be committed to the repository.

```text
COMMIT_REAL_BUSINESS_DATA_TO_GIT=false
COMMIT_DERIVED_REAL_BUSINESS_ROW_DATA_TO_GIT=false
COMMIT_PRIVATE_SOURCE_URL_TO_GIT=false
COMMIT_CREDENTIALS_TO_GIT=false
```

The repository may contain contracts, schema, manifest structure, hashes, row
and byte counts, non-sensitive summaries, synthetic fixtures, and explicitly
approved de-identified examples only. Real raw data and cleaned real row-level
data must remain in controlled external storage. S1 must freeze the storage
type, access owner, least-privilege boundary, retention, withdrawal and void
rules, downstream propagation, purpose, usage authorization, and the binding
between the manifest and the external object.

The trial and pilot evidence must distinguish:

- engineering-flow correctness;
- statistical/model evidence;
- real-business data acceptance;
- business adoption and formal acceptance.

Passing one category does not imply passing another category.

## 10. Controlled subtask decomposition

The six formal slices remain fixed, while controlled subtasks and multiple
reviewable PRs are allowed inside a slice:

```text
V0_3_TOTAL_SLICES=6
FORMAL_SLICE_COUNT_FIXED=true
SUBTASK_DECOMPOSITION_ALLOWED=true
SUBTASK_SCOPE_EXPANSION_ALLOWED=false
ONE_FORMAL_SLICE_MAY_USE_MULTIPLE_CONTROLLED_PRS=true
```

Every subtask has an explicit planning record with:

```text
subtask_id
parent_slice
objective
scope
dependencies
authorized_path_prefixes
proposed_new_paths
acceptance_evidence
explicit_non_scope
authorization_state
next_subtask_not_implied
```

The following are controlled subtasks, not additional formal slices. Because
this overall plan does not authorize implementation and cannot safely freeze
implementation paths before the independent subtask authorization, every
record uses `NONE_UNTIL_SUBTASK_AUTHORIZATION` rather than an invented path.

```text
subtask_id=S2-A
parent_slice=V0.3-S2
objective=SOURCE_AUTHORITY_AND_GOVERNED_LANDING
scope=approved source authority binding; external object manifest; immutable raw-source identity; governed landing interface or process
dependencies=S1_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=source authority record; object manifest; raw-source identity and lineage review
explicit_non_scope=data cleaning; final split; model backtest; model change
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-B
parent_slice=V0.3-S2
objective=IDENTITY_MAPPING_AND_DETERMINISTIC_CLEANING
scope=farm/subfarm/variety/season identity mapping; unit normalization; deterministic cleaning; correction and exclusion ledger
dependencies=S2-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=identity mapping manifest; cleaning rules; correction/exclusion ledger; deterministic replay
explicit_non_scope=final dataset split; final metrics; model modification; TEST access
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-C
parent_slice=V0.3-S2
objective=QUALITY_AND_HISTORICAL_VISIBILITY_MATERIALIZATION
scope=data quality report; point-in-time eligibility; source-specific winner selection; historical visibility materialization
dependencies=S2-B_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=quality report; visibility report; winner/lineage evidence; leakage preflight
explicit_non_scope=model backtest; TEST access; model training; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S2-D
parent_slice=V0.3-S2
objective=MATERIALIZED_DATASET_BUILD_AND_FINAL_SPLIT_RE_ACCEPTANCE
scope=TRAIN/VALIDATION/TEST materialization; conditional external holdout; final manifests; final hashes; split re-acceptance
dependencies=S2-C_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=materialized dataset manifests; split manifest; hash set; final row/exclusion lineage
explicit_non_scope=S3 execution; model modification; TEST access; pilot operations
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-A
parent_slice=V0.3-S4
objective=EXPERIMENT_REGISTRY_BUDGET_AND_REPRODUCIBILITY
scope=experiment plan; finite candidate registry; validation budget; run ledger; reproducibility identities
dependencies=S3_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=experiment plan hash; candidate registry; complete validation ledger; reproducibility manifest
explicit_non_scope=unregistered candidate execution; TEST access; pilot approval; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-B
parent_slice=V0.3-S4
objective=PARAMETER_AND_QUANTILE_CALIBRATION
scope=versioned parameter calibration; P80/P90 calibration; validation-only evaluation under the frozen experiment budget
dependencies=S4-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=parameter manifest; quantile calibration report; validation ledger entries; guardrail report
explicit_non_scope=model structure change; TEST access; pilot approval; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-C
parent_slice=V0.3-S4
objective=EVIDENCE_AUTHORIZED_STRUCTURAL_MODEL_CANDIDATES
scope=only S3-supported structural candidates; feature/parameter manifests; candidate artifacts; reproducible validation comparison
dependencies=S4-B_EVIDENCE_REVIEWED_AND_S3_AUTHORIZATION_LIST_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=candidate registry entry; S3 evidence reference; artifact hash; validation result and ledger entry
explicit_non_scope=unsupported model candidate; hidden trial; TEST access; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S4-D
parent_slice=V0.3-S4
objective=LOCKED_CANDIDATE_TEST_AND_PILOT_MODEL_APPROVAL
scope=locked candidate/incumbent comparison; separate TEST authorization; one-time TEST result; pilot-model approval and rollback manifest
dependencies=EXPERIMENT_BUDGET_COMPLETE_AND_CANDIDATE_LOCKED_AND_SEPARATE_TEST_AUTHORIZATION
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=TEST authorization record; locked test result; selection decision; pilot approval and rollback manifest
explicit_non_scope=TEST-after tuning; new hidden candidate; production release; S5 operations
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-A
parent_slice=V0.3-S5
objective=BACKEND_PILOT_OPERATIONS
scope=pilot model execution; versioned forecast operations; persisted comparison and run evidence; export and feedback hooks
dependencies=MODEL_APPROVED_FOR_PILOT
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=operations readiness package; run records; comparison/readback/export evidence
explicit_non_scope=model training; model selection; business acceptance; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-B
parent_slice=V0.3-S5
objective=FRONTEND_COMPARISON_WARNINGS_AND_STRUCTURED_EXPLANATION
scope=forecast comparison; data-quality warnings; evidence-derived explanations; model/parameter version display
dependencies=S5-A_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=browser evidence; persisted explanation evidence; warning and comparison acceptance report
explicit_non_scope=client-side forecast calculation; LLM unsupported explanation; business acceptance; production release
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true

subtask_id=S5-C
parent_slice=V0.3-S5
objective=CONTINUOUS_EVALUATION_AND_ADOPTION_RECORDS
scope=forecast-to-actual feedback; continuous metric updates; adoption/non-adoption ledger; manual adjustment reasons
dependencies=S5-A_ACCEPTED_AND_S5-B_ACCEPTED
authorized_path_prefixes=NONE_UNTIL_SUBTASK_AUTHORIZATION
proposed_new_paths=NONE_UNTIL_SUBTASK_AUTHORIZATION
acceptance_evidence=continuous evaluation package; adoption ledger; non-adoption reasons; adjustment audit
explicit_non_scope=production release; S6 pilot acceptance decision; cross-factory routing
authorization_state=NOT_AUTHORIZED
next_subtask_not_implied=true
```

All eleven subtasks require independent authorization, a scoped PR, and
acceptance evidence. A subtask acceptance does not authorize the next subtask,
and decomposition cannot add a seventh slice or expand the non-scope:

```text
SUBTASK_RECORD_COUNT=11
SUBTASK_ACCEPTANCE_DOES_NOT_AUTHORIZE_NEXT=true
SUBTASK_DECOMPOSITION_DOES_NOT_EXPAND_SCOPE=true
```

## 11. Authority precedence and known documentation conflicts

The following authority order applies:

1. `docs/forecast-quality/q2c-physical-target-equivalence-contract.md`
   (`Q2C`) governs physical target equivalence and target disposition.
2. `docs/forecast-quality/q2a-i7-label-snapshot-and-revision-winner-contract.md`
   (`Q2A/I7`) governs label visibility, winner selection, lineage, and
   canonical grain.
3. `docs/forecast-quality/s3-quality-metrics-contract.md` (`S3`) governs the
   existing metric formulas, masks, zero policies, Decimal semantics, and peak
   tie-breaking.
4. `docs/v0-1/core-forecast-contract.md` (`Core Forecast`) governs the forecast
   quantities, date basis, and strict consecutive-seven-day peak.
5. `backend/app/core_forecast/schemas.py`,
   `backend/app/actual_harvest_import/schemas.py`, and
   `backend/app/rolling_backtest/orchestration.py` are the sampled production
   implementation references for those contracts.
6. The current Actual Harvest contract cannot be silently substituted for
   effective marketable quantity.
7. The older three-day wording in `AGENTS.md` is a documentation conflict for a
   separate governance task; this PR does not modify `AGENTS.md`.
8. README transport, processing-capacity, and cross-factory language is product
   context, not V0.3 authorization.
9. `destination_factory_id` is not a cross-factory routing authority.
10. Older “not implemented” status text in Q2A/I7 does not override current code
   and accepted V0.2 engineering evidence; stale documentation requires a
   separate governance task.

These conflicts must not be resolved by changing an unrelated file in this PR.

The metric authority is pinned independently of this plan:

```text
METRIC_CONTRACT_AUTHORITY=docs/forecast-quality/s3-quality-metrics-contract.md
METRIC_CONTRACT_AUTHORITY_BASE_SHA=b873dd63fc0d5b6375f94674abbd24a94d915f3c
METRIC_INPUT_MASK_POLICY_VERSION=v0.2-s3-metric-input-mask-v1
V0_3_METRIC_CONTRACT_VERSION=v0.3-metric-contract-v1
```

## 11.1. R2 and R3 content-correction closure

The following statuses describe the planning-document corrections only. They
are not implementation, acceptance, TEST access, or release approvals:

```text
V0_3_METRIC_CONTRACT_NOT_UNIQUE=ADDRESSED
HOLDOUT_AND_MODEL_SELECTION_PROTOCOL_UNCLOSED=ADDRESSED
ERROR_ATTRIBUTION_METHOD_UNDEFINED=ADDRESSED
COMPLETION_GATE_EVIDENCE_NOT_CLOSED=ADDRESSED
SLICE_INTERNAL_DECOMPOSITION_UNDEFINED=ADDRESSED
HIDDEN_TEST_ACCESS_AUTHORIZATION=ADDRESSED

R2-METRIC-001=ADDRESSED
R2-MODEL-001=ADDRESSED
R2-ATTRIBUTION-001=ADDRESSED
R2-GATE-001=ADDRESSED
R2-STATE-001=ADDRESSED
R2-MINOR-001=ADDRESSED

R3-METRIC-001=ADDRESSED
R3-GATE-001=ADDRESSED
R3-STATE-001=ADDRESSED
```

## 12. Current authorization status

This document freezes the plan only. No V0.3 implementation is authorized by
this commit or by its Draft PR.

```text
V0_3_PLAN_FROZEN=true
CURRENT_V0_3_S1_COMPLETE=false
CURRENT_V0_3_S2_COMPLETE=true
CURRENT_V0_3_S2_ACCEPTANCE_STATUS=ACCEPTED
S2_ACCEPTED_DOES_NOT_IMPLY_S3=true
CURRENT_V0_3_S3_COMPLETE=false
CURRENT_V0_3_S4_COMPLETE=false
CURRENT_V0_3_S5_COMPLETE=false
CURRENT_V0_3_S6_COMPLETE=false
CURRENT_V0_3_COMPLETION_STATUS=BLOCKED

V0_3_IMPLEMENTATION_AUTHORIZED=false
V0_3_S1_IMPLEMENTATION_AUTHORIZED=false
V0_3_S2_IMPLEMENTATION_AUTHORIZED=false
V0_3_S3_IMPLEMENTATION_AUTHORIZED=true
V0_3_S4_IMPLEMENTATION_AUTHORIZED=false
V0_3_S5_IMPLEMENTATION_AUTHORIZED=false
V0_3_S6_IMPLEMENTATION_AUTHORIZED=false

REAL_DATA_IMPORT_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
PRODUCTION_CODE_CHANGE_AUTHORIZED=false
MIGRATION_AUTHORIZED=false
FRONTEND_CHANGE_AUTHORIZED=false
MULTI_FACTORY_ROUTING_AUTHORIZED=false
PLANNING_DOCUMENT_DOES_NOT_AUTHORIZE_TEST_ACCESS=true
```

The next permitted task is a separately planned and separately authorized:

```text
NEXT_TASK=V0_3_S1
NEXT_TASK_SCOPE=REAL_BUSINESS_DATA_CONTRACT_AND_SOURCE_COHORT_FREEZE
```

That next task must not be started automatically by this plan, this branch, or
the associated Draft PR.
