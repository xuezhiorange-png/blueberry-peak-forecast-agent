# Q2D Backtest Readiness Gate

> Issue: #102
> Round: V0_2_S2_Q2D_HISTORICAL_LABEL_SOURCE_ATTESTATION
> Scope: readiness contract only; no Q2B implementation or backtest execution
> Base: `480f64cf093827dc7401ae9cdafe7b9f870bfd66`

## 1. Purpose

This document defines when the Q2C physical-target blocker may be released to
Q2B implementation review. It is a fail-closed gate, not a runner design or
execution plan. It does not create a source, import historical data, resolve a
missing owner, or approve a forecast-vs-actual comparison.

```text
Q2D_READINESS_GATE_ONLY=true
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
READY=NO
MERGE=NO
ISSUE102_CLOSE=NO
```

## 2. Required target boundary

The gate consumes the frozen Q2C actual-label boundary and does not redefine
it:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
```

The candidate is not accepted because its name contains `harvested` or
`marketable`. `effective_marketable_quantity_kg` and
`FactReceiptDaily.weight_kg` remain excluded from the primary target unless a
new, separately authorized physical contract proves otherwise.

## 3. Final status vocabulary

Only these final statuses are permitted:

```text
BUSINESS_ATTESTATION_READY
BLOCKED_BY_MISSING_SOURCE_OWNER
BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY
BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY
```

Current status:

```text
Q2D_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
Q2B_PHYSICAL_TARGET_BLOCKER=OPEN
```

`READY` and `MERGE` are governance operations, not readiness statuses. They
remain unauthorized even if a future attestation becomes ready.

## 4. Mandatory gate sequence

The gate executes in this order. A failed earlier gate prevents later evidence
from being used to claim readiness.

### Gate A: source owner and source identity

Require:

```text
business_owner_role
source_system
source_dataset
source_version
attestation_version
attestation_effective_at
attestation_status=ATTESTED
attestation_hash
```

The owner must be a formal role or governed source-system authority. Personal
identity data is not required. A field name, developer statement, test fixture,
filename or unsigned narrative fails the gate.

Failure:

```text
BLOCKED_BY_MISSING_SOURCE_OWNER
```

### Gate B: physical measurement boundary

Require explicit and internally consistent evidence for:

```text
physical_event=FARM_PICK
weighing_point
weighing_time_relative_to_pick
all_picked_or_marketable_only
rejected_fruit_included
field_sorting_before_weight
packhouse_sorting_before_weight
postharvest_loss_before_weight
postharvest_handling_before_weight
tare_policy
unit=KG
measurement_method
scale_calibration_authority
rounding_policy
```

The evidence must show whether the measurement is all picked fruit or a later
marketable-only population, and must distinguish field sorting, packhouse
sorting and post-harvest loss. A factor applied in forecast code is not proof
of an actual-label boundary.

Failure:

```text
BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY
```

### Gate C: date and grain authority

Require a versioned policy for:

```text
harvest_business_date_assignment_policy
farm_timezone_authority
day_boundary_policy
late_entry_policy
missing_day_policy=UNKNOWN_NOT_ZERO
correction_date_policy
```

Require exact, case-sensitive or explicitly versioned identities for season,
farm, subfarm/plot and variety. The source grain must be the frozen Q2C grain,
or a separately authorized deterministic transformation with a membership
manifest.

Failure:

```text
BLOCKED_BY_MISSING_MEASUREMENT_BOUNDARY
```

### Gate D: revision and historical visibility authority

Require a reconstructable source history with:

```text
logical_record_key
revision_key
revision_number_policy
predecessor_policy
correction_policy
void_policy
finalization_policy
visibility_authority
visibility_timestamp
publication_boundary
late_entry_visibility
correction_visibility
immutable_source_snapshot_or_visibility_manifest
```

The historical view must be reproducible as of the forecast cutoff. Current
latest rows, current mappings, post-cutoff corrections and database insertion
order are not acceptable substitutes.

Failure:

```text
BLOCKED_BY_MISSING_HISTORICAL_VISIBILITY
```

### Gate E: physical equivalence decision

Only after Gates A-D may the source attestation be compared with
`model_harvested_marketable_quantity_kg`. The comparison must explicitly
resolve event, observed quantity, marketability, sorting, post-harvest, unit,
date, grain and missingness. No undocumented conversion is allowed.

If all dimensions are proven equivalent, the source decision is
`BUSINESS_ATTESTATION_READY`. This status authorizes only a future Q2B
implementation review; it does not authorize code or backtest execution.

## 5. Readiness matrix

| gate | required proof | current result | release condition |
|---|---|---|---|
| owner | formally accountable business/system authority | missing | named role and governed source record |
| source version | immutable dataset/schema/snapshot version | missing | exact source identity and effective version |
| physical event | FARM_PICK | unverified | attested process boundary |
| weighing | point and timing relative to pick | unverified | scale/process evidence |
| quantity population | all picked vs marketable-only | unverified | explicit inclusion/exclusion rule |
| sorting | field and packhouse boundary | unverified | explicit before/after measurement rule |
| post-harvest | losses/handling before weight | unverified | explicit loss boundary |
| date | farm-local business date | unverified | versioned timezone/date policy |
| grain | exact identity and date grain | unverified | mapping and membership authority |
| revision | correction and finalization graph | unverified | append-only source lineage |
| visibility | AS-OF source snapshot | missing | replayable timestamp/manifest |
| target | candidate equals physical boundary | unverified | equivalence evidence or authorized transform |
| result | canonical attestation hash | missing | immutable hash-bound evidence |

All rows must pass. A partial table does not yield readiness.

## 6. Required evidence package

Before Q2B implementation can be reconsidered, the package must contain:

1. an owner authority record;
2. a versioned attestation payload and SHA-256 hash;
3. source system/dataset/version identity;
4. measurement, sorting and post-harvest boundary evidence;
5. farm-local date and missing-day policy;
6. exact identity/grain mapping policy;
7. revision and correction authority;
8. historical visibility timestamp and immutable snapshot/manifest;
9. bounded coverage and known exclusions;
10. a Q2C decision bound to the attestation hash.

The package must not contain credentials, private URLs, raw personal data,
unbounded business rows or database IDs. Stable business references and hashes
are sufficient for design and later audit.

## 7. Rejection rules

The gate must remain blocked when any of the following applies:

```text
OWNER_UNKNOWN=true
ATTESTATION_UNSIGNED=true
SOURCE_VERSION_MISSING=true
WEIGHING_POINT_UNKNOWN=true
MARKETABILITY_BOUNDARY_UNKNOWN=true
SORTING_BOUNDARY_UNKNOWN=true
POSTHARVEST_BOUNDARY_UNKNOWN=true
DATE_AUTHORITY_UNKNOWN=true
GRAIN_AUTHORITY_UNKNOWN=true
REVISION_AUTHORITY_UNKNOWN=true
HISTORICAL_VISIBILITY_UNKNOWN=true
CURRENT_OR_LATEST_FALLBACK=true
RECEIPT_PROXY_USED_AS_PRIMARY_LABEL=true
MODEL_OUTPUT_TREATED_AS_ACTUAL=true
```

No test, fixture, model formula, database row or CI result can override these
business authority failures.

## 8. Current conclusion and governance

```text
Q2D_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
ACTUAL_LABEL_STATUS=UNVERIFIED
BACKTEST_AUTHORITY=BLOCKED
Q2B_IMPLEMENTATION_READINESS=BLOCKED
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
READY=NO
MERGE=NO
ISSUE102_CLOSE=NO
NO_STEP_IMPLIES_THE_NEXT=true
```

Q2D completion is a design decision and evidence gate only. It does not start
Q2B implementation, forecast-vs-actual comparison or data acquisition.
