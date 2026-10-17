# Forecast Intelligence P1 — Hierarchical Forecast Contract R1

TASK_ID=FORECAST_INTELLIGENCE_P1_HIERARCHICAL_FORECAST_CONTRACT_R1

Base main: `b69e526a7a6d7c40bd22351cf16bad6c8befea14`.

This task freezes the hierarchy/reconciliation contract only. It does not implement runtime aggregation, uncertainty intervals, model attribution, ForecastOps scoring, business-loss optimization, What-if simulation, V0.16 prospective validation, or production promotion.

## 1. Current authority boundary

The repository already has a canonical Base registry. Historical farm identities are mapped into a canonical `base_id`; they are source/member identities and are **not** automatically forecast hierarchy parents. The registry also carries `region_scope`.

Therefore P1 freezes the current forecast hierarchy as:

```text
BASE (atomic forecast node)
  -> REGION
      -> COMPANY
```

`FARM` is not admitted as a hierarchy level in R1 unless a future explicit authoritative entity relationship is separately frozen.

`FACTORY` is explicitly excluded. Base-to-factory assignment is a routing/allocation relationship, not a stable production-ownership hierarchy.

## 2. Atomic forecast unit

```text
FORECAST_ATOMIC_ENTITY_TYPE=BASE
FORECAST_ATOMIC_ENTITY_ID=base_id
```

A Base forecast is immutable input to reconciliation. P1 must never mutate an existing Area Forecast, Operational Peak, V0.14 prospective forecast, or V0.15 research artifact.

## 3. Hierarchy authority

R1 hierarchy membership is snapshot-bound.

Required hierarchy snapshot fields:

```text
hierarchy_contract_version
authority_hash
snapshot_created_at
company_id
company_name
regions[]
  region_id
  region_name
  child_base_ids[]
bases[]
  base_id
  canonical_base_name
  region_id
  active
```

The current Base registry `region_scope` may seed a future implementation, but P1 does not claim historical effective-dating that the existing authority does not prove.

```text
HIERARCHY_EFFECTIVE_DATING_ESTABLISHED=false
HISTORICAL_HIERARCHY_RECONSTRUCTION_AUTHORIZED=false
```

Every reconciliation output must bind the exact hierarchy authority hash used for that run.

## 4. Reconciliation strategy

R1 uses deterministic bottom-up reconciliation only.

```text
RECONCILIATION_METHOD=BOTTOM_UP_EXACT_SUM
STATISTICAL_RECONCILIATION=false
MINT=false
TOP_DOWN=false
MIDDLE_OUT=false
PARENT_MODEL_FIT=false
```

Reason: current trusted forecast output is generated at the atomic Base level; there is no separately validated Region or Company forecast model requiring statistical reconciliation.

## 5. Compatible child-run contract

Base forecasts may be aggregated only when all included child runs share the same reconciliation key:

```text
forecast_family
forecast_policy_version
model_version
target_season
forecast_origin / issue identity
season_start
season_end
target_date
scenario_id
quantile_or_point_label
```

R1 is point-forecast-only:

```text
quantile_or_point_label=POINT
UNCERTAINTY_RECONCILIATION_IN_SCOPE=false
```

P2 may extend this to P50/P80/P90, but P1 must not pre-claim interval coherence.

Mixing incompatible model families, origins, target windows, scenarios, or policy versions is forbidden.

## 6. Missing-child policy

Missing Base forecasts are never treated as zero.

For each Region/Company/date:

- determine the expected active child set from the pinned hierarchy snapshot;
- compare it with the compatible Base forecasts actually present;
- duplicate Base rows fail closed;
- unknown Base IDs fail closed;
- inactive Base handling must follow the pinned snapshot;
- an aggregate is `COMPLETE` only when all expected child forecasts exist.

If any expected child is missing:

```text
status=INCOMPLETE_CHILD_COVERAGE
official_aggregate_kg=null
observed_child_subtotal_kg=<optional diagnostic only>
```

The subtotal must never be presented as the official Region/Company forecast.

## 7. Arithmetic invariants

All quantity arithmetic uses exact Decimal semantics consistent with existing forecast outputs.

For every compatible target date:

```text
region_daily_kg
  = sum(base_daily_kg for all active Bases in the Region)

company_daily_kg
  = sum(region_daily_kg for all complete Regions)

company_daily_kg
  = sum(base_daily_kg for all active Bases)
```

The two Company paths must be equal.

For an aggregate run:

```text
aggregate_total_kg
  = sum(aggregate_daily_kg)
```

No hidden normalization, redistribution, negative clipping, residual allocation, or missing-as-zero behavior is allowed in P1.

## 8. Peak metrics

Peak metrics are **recomputed from the aggregated daily curve**.

They must never be produced by summing child peak quantities or child peak dates.

R1 inherits existing deterministic semantics:

- single-day peak: maximum aggregate daily quantity;
- rolling-7 peak: maximum sum of 7 consecutive natural days;
- ties resolve to the earliest date/window;
- an incomplete calendar window cannot be silently bridged.

## 9. Output contract

A future P1 implementation must produce a separate immutable reconciliation artifact containing at least:

```text
reconciliation_run_id
hierarchy_contract_version
hierarchy_authority_hash
reconciliation_method
entity_type
entity_id
target_season
forecast_origin
season_start
season_end
child_expected_count
child_included_count
child_base_ids_hash
status
daily_forecast[]
aggregate_total_kg
single_day_peak
rolling_7day_peak
source_forecast_run_ids
source_forecast_hashes
result_hash
```

The result hash must bind the hierarchy snapshot, child forecast identities, daily output, totals and peak metrics.

## 10. Determinism and immutability

Required properties for later implementation:

```text
SAME_INPUTS_SAME_OUTPUT=true
SAME_INPUTS_SAME_RESULT_HASH=true
SOURCE_FORECAST_MUTATION=false
HISTORICAL_AGGREGATE_OVERWRITE=false
APPEND_ONLY_RUN_HISTORY=true
```

A hierarchy-authority change or any child forecast identity change must produce a different execution/result identity rather than rewriting an old reconciliation run.

## 11. Explicit exclusions

P1 does not authorize:

```text
FARM_HIERARCHY_INFERENCE
FACTORY_ROUTING
MULTI_FACTORY_ALLOCATION
UNCERTAINTY_INTERVALS
CONFORMAL_CALIBRATION
FORECAST_ATTRIBUTION
ACTUAL_IMPORT
FORECAST_SCORING
MODEL_DRIFT
BUSINESS_LOSS
WHAT_IF_SIMULATOR
OPTIMIZATION
V0_16_PROSPECTIVE_VALIDATION
MODEL_RETRAINING
MODEL_PROMOTION
PRODUCTION_DEPLOYMENT
```

## 12. Acceptance gate for P1 implementation

A later implementation is acceptable only if tests prove at minimum:

1. exact Base -> Region -> Company summation;
2. direct Base->Company and Base->Region->Company parity;
3. no missing-as-zero;
4. duplicate/unknown Base fail closed;
5. incompatible forecast identity/policy/origin/window fails closed;
6. peak metrics are recomputed from the aggregate curve;
7. earliest-date tie behavior;
8. deterministic replay and stable hash;
9. hierarchy-authority changes create new identity;
10. source forecasts remain byte/record immutable.

## 13. Roadmap boundary

The approved Forecast Intelligence roadmap remains:

```text
P1 Hierarchical Forecast Contract
P2 Uncertainty & Conformal Calibration
P3 Forecast Attribution
P4 ForecastOps Monitoring
P5 Business Loss Contract
P6 What-if Decision Simulator
```

Only P1 contract freeze is implemented by this task. P2-P6 remain unauthorized implementation work until separately started.

```text
P1_CONTRACT_FROZEN=true
P1_RUNTIME_IMPLEMENTED=false
P2_STARTED=false
P3_STARTED=false
P4_STARTED=false
P5_STARTED=false
P6_STARTED=false
V0_16_STARTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
```
