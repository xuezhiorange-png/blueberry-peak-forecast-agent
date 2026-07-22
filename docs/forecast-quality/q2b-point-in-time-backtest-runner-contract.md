# Q2B Point-in-Time Historical Backtest Runner Contract

> Issue: #102
> Scope: design freeze only
> Base: `6a2489e8685d2ffb2cff83597503f2dcd0203621`
> Alembic head audited at base: `0022_finalized_at_lineage_basis_member`

## 1. Scope and non-goals

Q2B freezes the contract for a deterministic point-in-time historical backtest
runner. The runner reconstructs what a forecast would have been allowed to see
at a historical forecast cutoff, binds the evaluation to an immutable Q2A-I7
label snapshot, aligns the two physical quantities and grains, and computes
authorized metrics. It does not implement any of those operations in this
round.

The following statements are binding:

```text
FORECAST_REPLAY_IS_NOT_MODEL_RETRAINING=true
BACKTEST_IS_NOT_LIVE_FORECAST=true
LABEL_OBSERVATION_IS_NOT_MODEL_INPUT=true
NO_FUTURE_AUTHORITY_LEAKAGE=true
Q2B_DESIGN_ONLY=true
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
```

Explicit exclusions are Q3 sustained seven-day peak quality, Q4 naive
baseline, Q5 quality reporting, Q6 model improvement, atomic source commit,
new label snapshots, frontend/API work, migration, and any forecast/model
change. The legacy three-day metric remains compatibility-only and is not the
Q2B primary business peak.

## 2. Historical time model

Q2B uses two independent cutoffs and one runtime timestamp. They must be
timezone-aware and canonicalized to UTC for identity and hash purposes.

```text
forecast_cutoff_at
  < forecast_target_date_or_window_end
  <= label_observation_cutoff_at
  <= replay_executed_at
```

`forecast_cutoff_at` is the model-input cutoff. It gates training data,
features, weather observations, model artifacts, parameter authorities, Task
9 authorities, Task 10 inputs, and every other model input. It must never be
replaced by the label cutoff or the time at which the runner happens to run.

`label_observation_cutoff_at` is the evaluation visibility cutoff. It gates
which actual-harvest revisions may be visible to an `AS_OF_EVALUATION` I7
snapshot. It is not a model feature, training label, or replay input.

`FINAL_ADJUDICATED` evaluation consumes the exact immutable I7 snapshot whose
visibility mode is `FINAL_ADJUDICATED`; it is not allowed to rebuild labels
from staging or from current master data. A late correction cannot rewrite an
earlier AS-OF snapshot. A snapshot identity, hash, or source manifest drift is
a structural failure.

## 3. Canonical backtest identity

The future runner must persist or emit the following identity fields. Database
IDs are allowed only as opaque foreign-key references and never enter business
hashes or public evidence.

```text
backtest_run_id
backtest_request_identity_hash
backtest_instance_identity_hash
source_system
forecast_season_identity
forecast_cutoff_at
label_observation_cutoff_at_or_null
label_visibility_mode
label_snapshot_id
label_snapshot_hash
label_snapshot_request_identity_hash
label_snapshot_instance_identity_hash
forecast_model_version
forecast_parameter_version
forecast_code_version
forecast_data_snapshot_hash
task9_replay_authority_hash
task10_forecast_authority_hash
replay_run_correlation_id
requested_horizons
requested_farms
requested_varieties
evaluation_policy_version
```

The request identity excludes runtime-only fields. The instance identity adds
all immutable resolved authority hashes, the exact I7 snapshot identity, the
resolved forecast authority identities, and the evaluation policy version.
Repeated calls with identical immutable inputs are an idempotent read/replay
of the same instance; any identity or evidence drift creates a new instance or
fails closed. A runner must not silently substitute the latest run, latest
model, latest parameter, latest master-data row, or current main code.

### 3.1 Canonical JSON and hash policy

The proposed policy identifier is
`q2b-backtest-identity-hash-v1`. Its canonical JSON rules are:

* UTF-8, JSON object keys sorted lexicographically, compact separators;
* arrays ordered by the contract's explicit stable key, never by database or
  query order;
* enum values are their frozen string values;
* timestamps are timezone-aware ISO-8601 UTC values with `Z`;
* `null` is retained as JSON `null`, never omitted or converted to an empty
  string;
* exact Decimal values are rendered as non-float decimal strings;
* NaN and Infinity are rejected;
* SHA-256 is lowercase hexadecimal;
* the policy version is included in every request and instance hash payload.

The hash excludes database IDs, insertion order, host, request tokens,
pagination tokens, runtime timestamps not explicitly authoritative, and secret
or credential material.

## 4. Replay authority chain

The only authorized future execution chain is:

```text
historical forecast cutoff
 -> retrospective_replay
 -> leakage-safe source visibility
 -> Task 9 replay authority
 -> Task 10 consumes exact Task 9 authority
 -> deterministic forecast output
 -> immutable I7 label snapshot
 -> grain alignment
 -> metric computation
```

| edge | required input identity | required output identity/hash | persisted evidence | fail-closed condition |
|---|---|---|---|---|
| cutoff -> replay | `forecast_cutoff_at`, node identity, historical code/config policy | replay node identity and source-visibility manifest hash | rolling node, resolved-input and availability-audit rows | missing cutoff, ambiguous visibility, current-data fallback |
| replay -> source visibility | each source semantic identity plus availability timestamp | visible-source set hash | availability audit and source identity rows | source not visible, authority drift, missing parent |
| visibility -> Task 9 | exact visible authorities and replay runtime identity | replay `HarvestStateRun` identity and result hash | replay metadata columns and Task 9 result | missing replay row, runtime identity mismatch |
| Task 9 -> Task 10 | replay-produced Task 9 run ID and result hash | Task 10 prediction/training binding identity | Task 10 binding event and prediction identity | cross-run substitution, unsupported policy |
| Task 10 -> forecast output | exact model/config/artifact identity and target scope | ordered forecast rows and output hash | forecast run, daily rows, row hashes | version not visible, duplicate row, hash mismatch |
| forecast -> I7 | forecast identity is independent of label visibility | immutable I7 snapshot identity/hash | I7 snapshot header, winners, labels and exclusions | missing snapshot or snapshot drift |
| I7 -> grain alignment | exact snapshot label rows and forecast rows | aligned evaluation-row set and mask hash | future evaluation materialization evidence | physical target or grain mismatch |
| aligned rows -> metrics | metric policy, mask and horizon | ordered metric payload and metric hash | metric evidence or deterministic export | insufficient coverage, invalid denominator, duplicate row |

The current repository implements portions of the first four edges, but no
Q2B application runner or end-to-end evaluation transaction is authorized by
this document.

## 5. Source authority and anti-leakage rules

Every input class must have a visibility timestamp, a source authority, a
stable content/row hash, a fail-closed code, and an acceptance test. The future
runner must make the following table executable rather than relying on naming
conventions.

| leakage vector | visibility timestamp | authority/hash required | structural failure code | minimum test |
|---|---|---|---|---|
| future source records | source recorded/available time | source row hash and committed lineage basis | `DATA_SNAPSHOT_NOT_VISIBLE` | future row excluded and hash changes |
| future revisions | source-time authority and predecessor graph | revision/canonical hash | `LABEL_SNAPSHOT_DRIFT` or lineage blocker | late correction cannot alter prior AS-OF |
| future weather | weather `available_at` | observation row hash and source version | `DATA_SNAPSHOT_NOT_VISIBLE` | post-cutoff observation rejected |
| future model version | model artifact availability | artifact/config hash | `MODEL_VERSION_NOT_VISIBLE` | latest model is not selected |
| future parameter version | parameter `available_at_local_date` | authority row hash | `PARAMETER_VERSION_NOT_VISIBLE` | future Task 9 parameter rejected |
| future mapping registry | registry version seal/availability | registry content hash | `DATA_SNAPSHOT_NOT_VISIBLE` | current mapping cannot rewrite replay |
| Task 9 substitution | replay Task 9 run ID | result hash and replay metadata | `TASK9_REPLAY_AUTHORITY_DRIFT` | earlier/latest Task 9 row rejected |
| Task 10 substitution | exact Task 10 authority | prediction/training hashes | `TASK10_AUTHORITY_MISMATCH` | cross-run prediction rejected |
| manual correction | correction effective/source time | immutable correction evidence | `LABEL_SNAPSHOT_DRIFT` | correction appears only when visible |
| current defaults/code | code/config identity at cutoff | code/config version hash | `FORECAST_AUTHORITY_DRIFT` | current defaults cannot enter old run |
| current master data | master-data version/availability | stable master snapshot hash | `DATA_SNAPSHOT_NOT_VISIBLE` | later identity changes fail closed |

Ordinary missing labels or missing forecast days are evaluation exclusions,
not structural validation failures. Structural failures stop the run and
produce no metrics.

## 6. Physical target contract

The target is a physical event, not a convenient numeric field. Candidate
forecast quantities are:

```text
natural_maturity_quantity_kg
harvested_quantity_kg
closing_mature_inventory_kg
unharvested_backlog_kg
arrival_quantity_kg
final_corrected_arrival_quantity_kg
```

The actual-harvest contract defines the primary event as `FARM_PICK`, with
`OBSERVED_WEIGHT`, `KG`, and missing semantics `UNKNOWN_NOT_ZERO`. The
repository's `FactReceiptDaily.weight_kg` is a factory-gate receipt/arrival
proxy and is explicitly not a primary harvest label. It must not be used as a
silent fallback.

Q2B may evaluate a forecast field only after an explicit physical equivalence
contract proves that it represents the same event, unit, and loss boundary as
the I7 label's `actual_harvest_quantity_kg`. At the audited base,
`model_harvested_marketable_quantity_kg` and the Agent aggregate fields are
not sufficient proof of FARM_PICK equivalence.

Required alignment outcomes are:

```text
ALIGNED
NOT_ALIGNED
BLOCKED_BY_PHYSICAL_TARGET_GAP
```

The runner must not assume `harvested == actual`, `arrival == harvest`, or
apply a subtraction/conversion formula without a separately versioned
business contract and evidence.

## 7. Grain contract

The frozen I7 label grain is:

```text
SEASON x FARM x SUBFARM x VARIETY x HARVEST_BUSINESS_DATE
```

The preferred Q2B forecast input is the persisted core daily row, whose
business key is:

```text
CORE_FORECAST_RUN x DATE x FARM_ID x SUBFARM_ID x VARIETY_ID x FORECAST_QUANTILE
```

This is a structurally compatible candidate after stable business identity
projection and quantile expansion. The Agent `ForecastDailyRow` is a separate
aggregate output: its identity is carried by enclosing request/location/season
context and its variety information is nested in
`per_variety_contribution`. It cannot be joined to I7 by arbitrary splitting.

The future runner must freeze:

* one explicit forecast grain and one explicit label grain per evaluation;
* stable season, farm, subfarm/plot and variety identities for both sides;
* quantile handling (`P50`, `P80`, `P90`) without collapsing the rows;
* duplicate policy: duplicate business keys are structural failure;
* missing-day policy: do not zero-fill an absent physical observation;
* cross-farm and cross-variety policy: no implicit aggregation or allocation;
* disaggregation policy: aggregate forecast to label grain only with a frozen,
  identity-bearing contribution manifest; otherwise block.

If a forecast aggregate is coarser than the I7 label grain, the run is blocked
unless a deterministic nested contribution and location authority can exactly
reconstruct every label grain row. No arbitrary ratio, insertion order, or
display-name split is permitted.

## 8. Authorized Q2B v1 metrics

All metrics use exact Decimal arithmetic, operate on an explicit evaluation
mask and horizon, and return a value plus denominator, coverage, policy
version, mask hash, and a computability status. The following table is the
contract; implementation must not silently add metrics.

| metric | formula | unit | grain | denominator / weighting | zero denominator | missing day | minimum coverage |
|---|---|---|---|---|---|---|---|
| `daily_mae` | `mean(abs(pred-actual))` | kg | aligned day x quantile | comparable days, equal day weight | not computable | exclude, no zero-fill | 1 comparable day |
| `daily_wape` | `sum(abs(error))/sum(abs(actual))` | ratio | aligned day | absolute-actual denominator | `ZERO_ACTUAL_DENOMINATOR` | exclude | 1 day and nonzero denominator |
| `daily_smape` | `mean(2*abs(error)/(abs(pred)+abs(actual)))` | ratio | aligned day | equal comparable-day weight | zero/zero contributes 0 | exclude | 1 comparable day |
| `daily_zero_safe_mape` | `mean(abs(error)/max(abs(actual), 0.000001 kg))` | ratio | aligned day | equal comparable-day weight | fixed Decimal epsilon | exclude | 1 comparable day |
| `daily_signed_bias` | `mean(pred-actual)` | kg | aligned day | equal comparable-day weight | no denominator beyond count | exclude | 1 comparable day |
| `cumulative_absolute_error_kg` | `sum(abs(error))` | kg | requested horizon | equal row contribution | no denominator | incomplete horizon blocks | complete requested horizon |
| `cumulative_signed_error_kg` | `sum(pred-actual)` | kg | requested horizon | equal row contribution | no denominator | incomplete horizon blocks | complete requested horizon |
| `cumulative_absolute_relative_error` | `sum(abs(error))/sum(abs(actual))` | ratio | requested horizon | absolute-actual denominator | `ZERO_ACTUAL_DENOMINATOR` | incomplete horizon blocks | complete horizon and nonzero denominator |
| `single_day_peak_date_error_days` | `predicted_peak_date - actual_peak_date` after stable argmax | days | season x identity x quantile | peak rows only | no comparable peak blocks | incomplete peak window blocks | complete peak window |
| `single_day_peak_quantity_absolute_error_kg` | `abs(predicted_peak - actual_peak)` | kg | season x identity x quantile | peak rows only | no comparable peak blocks | incomplete peak window blocks | complete peak window |
| `single_day_peak_quantity_signed_error_kg` | `predicted_peak - actual_peak` | kg | season x identity x quantile | peak rows only | no comparable peak blocks | incomplete peak window blocks | complete peak window |
| `single_day_peak_quantity_absolute_relative_error` | `abs(predicted_peak-actual_peak)/abs(actual_peak)` | ratio | season x identity x quantile | actual peak denominator | zero actual peak blocks | incomplete peak window blocks | complete peak window and nonzero peak |
| `p80_coverage` | `count(actual <= p80)/count(comparable)` | ratio | aligned day | equal day weight | no comparable rows blocks | exclude | 1 comparable day |
| `p90_coverage` | `count(actual <= p90)/count(comparable)` | ratio | aligned day | equal day weight | no comparable rows blocks | exclude | 1 comparable day |
| `p80_interval_width` | `mean(p80-p50)` | kg | aligned day | equal comparable-day weight | no comparable rows blocks | exclude | 1 comparable day |
| `p90_interval_width` | `mean(p90-p50)` | kg | aligned day | equal comparable-day weight | no comparable rows blocks | exclude | 1 comparable day |
| `horizon_7d` | scope selector for seven complete target days | days | requested horizon | not a scalar metric | invalid horizon blocks | incomplete horizon blocks | 7 days |
| `horizon_14d` | scope selector for fourteen complete target days | days | requested horizon | not a scalar metric | invalid horizon blocks | incomplete horizon blocks | 14 days |
| `horizon_21d` | scope selector for twenty-one complete target days | days | requested horizon | not a scalar metric | invalid horizon blocks | incomplete horizon blocks | 21 days |

Peak ties are resolved by earliest business date, then stable canonical
identity. Metrics are computed separately per requested horizon and forecast
quantile. No forecast row is silently reused across horizons. `sMAPE` and the
zero-safe MAPE rule are new Q2B contracts even though current rolling-backtest
code contains related but different metric slices.

## 9. Failure taxonomy

### 9.1 Structural run failures

```text
FORECAST_AUTHORITY_MISSING
FORECAST_AUTHORITY_DRIFT
TASK9_REPLAY_AUTHORITY_MISSING
TASK9_REPLAY_AUTHORITY_DRIFT
TASK10_AUTHORITY_MISMATCH
MODEL_VERSION_NOT_VISIBLE
PARAMETER_VERSION_NOT_VISIBLE
DATA_SNAPSHOT_NOT_VISIBLE
LABEL_SNAPSHOT_MISSING
LABEL_SNAPSHOT_DRIFT
LABEL_VISIBILITY_MODE_MISMATCH
PHYSICAL_TARGET_NOT_ALIGNED
EVALUATION_GRAIN_NOT_ALIGNED
HORIZON_CONTRACT_INVALID
DUPLICATE_FORECAST_ROW
DUPLICATE_LABEL_ROW
LEAKAGE_DETECTED
```

These failures invalidate the run and cannot be converted to a metric value.

### 9.2 Ordinary evaluation exclusions

```text
ACTUAL_LABEL_NOT_YET_AVAILABLE
ACTUAL_LABEL_MISSING_DAY
FORECAST_MISSING_DAY
INCOMPLETE_HORIZON
ZERO_ACTUAL_DENOMINATOR
INSUFFICIENT_COVERAGE
OUTSIDE_REQUEST_SCOPE
```

Exclusions are part of the ordered evaluation mask and metric evidence. They
are not source-integrity success, and they must never be hidden by zero-fill.

## 10. Evidence and persistence design only

No table or migration is authorized in this round. The following is a design
candidate only:

```text
SCHEMA_STATUS=DESIGN_CANDIDATE_ONLY
MIGRATION_AUTHORIZED=NO
```

Candidate objects are:

* `backtest_run`: request/instance identity, both cutoffs, label snapshot
  identities, forecast/Task9/Task10 authority hashes, policy versions and
  lifecycle status;
* `backtest_forecast_row`: one canonical forecast grain row per quantile,
  source authority references, visibility timestamps, and row hash;
* `backtest_evaluation_row`: one aligned forecast/label pair or explicit mask
  exclusion, physical target and grain policy versions, and row hash;
* `backtest_metric_result`: one metric/horizon/grain output, denominator,
  mask hash, metric policy version and result hash;
* `backtest_leakage_audit`: vector, source, visibility decision, authority
  hash, and stable failure code.

Required constraints include unique run instance identity, unique forecast
business key `(run, season, farm, subfarm, variety, date, quantile)`, unique
evaluation key `(run, forecast row, label row)`, immutable evidence semantics,
and foreign keys with `ON DELETE RESTRICT` to I7 snapshot and authority
records. No aggregation table, active-label table, or source-commit table is
created by Q2B design.

## 11. Acceptance gates for a future implementation

The future implementation is not ready until all of the following are real
tests, not only documentation or golden helpers:

1. dual-cutoff visibility rejects every future source, weather, parameter,
   model, Task 9, Task 10, mapping and master-data input;
2. exact replay, code, model, parameter, data and I7 snapshot identities are
   persisted and reloaded from the same hashes;
3. `AS_OF_EVALUATION` and `FINAL_ADJUDICATED` are distinct and immutable;
4. physical target alignment is proven with a real source, not receipt proxy;
5. forecast and label grains are exactly aligned or a deterministic
   contribution manifest proves lossless disaggregation;
6. all 18 metric entries have formula, unit, denominator, zero policy,
   missing-day policy and minimum coverage tests;
7. leakage vectors fail closed and do not emit metrics;
8. repeated identical requests are deterministic and idempotent;
9. duplicate/missing/extra rows, ambiguous mappings and lineage conflicts are
   structural failures;
10. real PostgreSQL tests prove transaction and immutable-evidence behavior;
11. no Q3/Q4/Q5/Q6 behavior is introduced.

## 12. Scope governance

```text
Q2B_DESIGN_ONLY=true
BACKTEST_EXECUTION_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
Q3_AUTHORIZED=false
Q4_AUTHORIZED=false
Q5_AUTHORIZED=false
TASK013_C2_REMAINS_PAUSED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ISSUE102_REMAINS_OPEN=true
```

Q2B design acceptance does not authorize implementation, execution, model
change, Ready, merge, or the next slice.
