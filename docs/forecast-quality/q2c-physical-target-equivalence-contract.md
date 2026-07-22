# V0.2-S2 Q2C Physical Target Equivalence Contract

> Issue: #102
> Round: V0_2_S2_Q2C_PHYSICAL_TARGET_EQUIVALENCE
> Status: design freeze only; implementation is not authorized
> Base: `480f64cf093827dc7401ae9cdafe7b9f870bfd66`

## 1. Scope and authority

Q2C answers one question only: whether the physical target used by the
forecast is the same business event, quantity basis, unit, time basis and
grain as the actual-harvest label used for evaluation. It does not implement a
backtest runner, change a forecast field, ingest data, or create a migration.

The authoritative actual-label contract is the Q2A source and import contract.
The authoritative forecast-side contract is the V0.1 core forecast contract.
Q2B remains implementation-blocked until the Q2C result is accepted and all
independent Q2B blockers remain resolved.

```text
Q2C_PHYSICAL_TARGET_AUDIT_ONLY=true
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
MIGRATION_CHANGED=false
```

## 2. Canonical actual-label boundary

The only actual-label boundary accepted by Q2C v1 is:

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

The event is the physical removal of fruit from plants. A source is not
accepted because a field contains the word `harvest`; the source must provide
business evidence for the event, measured quantity, time boundary, identity,
revision behavior and ownership.

The following are explicitly excluded from the primary actual label:

- forecast, plan, capacity, allocation or model output;
- natural maturity supply, mature inventory or harvestable mature quantity;
- backlog or other unpicked state;
- factory arrival, factory receipt, processing input or corrected receipt;
- estimated yield, synthetic fixture or a value inferred from another field;
- a post-pick sorting or post-harvest retention result unless a separately
  authorized actual-label contract changes the target boundary.

No missing day may be silently converted to zero. Missingness is an explicit
UNKNOWN_NOT_ZERO state and must remain visible to future evaluation masks.

## 3. Target equivalence rule

Q2C evaluates equivalence across six dimensions:

1. physical event: the measured event is FARM_PICK;
2. quantity basis: the value is observed weight, not an estimate or a
   downstream retained quantity;
3. marketability boundary: the point at which marketability is applied;
4. sorting boundary: whether sorting occurred before or after measurement;
5. post-harvest boundary: whether handling or retention occurred before or
   after measurement;
6. time and grain: farm-local harvest date and the frozen identity grain.

An exact result requires all six dimensions to be proven by the source
contract and versioned business attestation. A compatible field name, formula,
fixture, database row or unit test is not proof.

The only permitted final Q2C outcomes are:

```text
PROVEN_EXACT
PROVEN_AFTER_VERSIONED_TRANSFORMATION
BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
BLOCKED_BY_SEMANTIC_MISMATCH
BLOCKED_BY_TRANSFORMATION_AUTHORITY
BLOCKED_BY_GRAIN_OR_DATE_MISMATCH
```

`PROVEN_AFTER_VERSIONED_TRANSFORMATION` requires an independently authorized
transformation policy, version, source authority and deterministic evidence.
Q2C does not create that transformation.

## 4. Candidate forecast targets

Q2C v1 retains one forecast-side candidate but does not promote it without
proof:

```text
TASK9_HARVESTED_BASIS=MARKETABLE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
Q2C_V1_FORECAST_TARGET=UNRESOLVED
PHYSICAL_TARGET_ALIGNMENT=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
```

`model_harvested_marketable_quantity_kg` is the Task 9/Core Forecast model
output. Its name and the model's marketable quantity basis do not prove that
it represents the same physical event as a FARM_PICK observed weight.

`effective_marketable_quantity_kg` is not selected for the FARM_PICK target.
The V0.1 formula applies both sorting and post-harvest retention:

```text
effective_marketable_quantity_kg
  = model_harvested_marketable_quantity_kg
  * sorting_retention_rate
  * postharvest_retention_rate
```

That is a post-pick retained quantity boundary unless a future business
attestation proves otherwise. Q2C cannot infer equivalence from rates.

## 5. Candidate equivalence matrix

| candidate | event/boundary interpretation | Q2C status | required disposition |
|---|---|---|---|
| `natural_maturity_supply_kg` | natural maturity supply state | `NOT_ALIGNED_MATURITY_NOT_PICK` | never use as actual label |
| `harvestable_mature_quantity_kg` | mature and available but unpicked inventory | `NOT_ALIGNED_AVAILABLE_NOT_PICKED` | never use as actual label |
| `model_harvested_marketable_quantity_kg` | Task 9/Core Forecast model output | `CANDIDATE_REQUIRES_BUSINESS_ATTESTATION` | only candidate for exact proof |
| `effective_marketable_quantity_kg` | model output after sorting and post-harvest retention | `NOT_ALIGNED_POST_PICK_RETENTION_BOUNDARY` | do not substitute for FARM_PICK |
| `arrival_quantity_kg` | predicted or downstream arrival quantity | `NOT_ALIGNED_ARRIVAL_EVENT` | never use as actual label |
| `final_corrected_arrival_quantity_kg` | corrected arrival/receipt boundary | `NOT_ALIGNED_ARRIVAL_EVENT` | never use as actual label |
| `FactReceiptDaily.weight_kg` | factory receipt weight | `FORBIDDEN_RECEIPT_PROXY` | secondary diagnostics only |

The matrix is semantic, not a ranking. A candidate marked as not aligned cannot
be selected by choosing a more convenient name or by applying an undocumented
conversion.

## 6. Explicit semantic questions to resolve

The following questions must be answered by a versioned source attestation
before Q2C can return a positive result:

### A. Physical event

Does the source measure the fruit being physically picked from plants, or does
it measure a later arrival, receipt, processing or inventory event?

### B. Quantity and marketability

Does the measured quantity include all fruit picked, or only fruit considered
marketable at a later business boundary? If marketability is applied, where and
under whose authority is it applied?

### C. Sorting boundary

Does field or packhouse sorting occur before the scale measurement? If so, does
the source record excluded fruit separately? A sorting retention rate alone is
not evidence of this boundary.

### D. Post-harvest boundary

Does any transport, storage, dehydration, handling, rejection or post-harvest
retention occur before measurement? If yes, the source is not an exact FARM_PICK
weight without an authorized transformation.

### E. Time authority

How is a farm-local harvest business date assigned to an observation? The
assignment must not be inferred from UTC conversion, factory receipt date,
insertion date or a filename.

### F. Identity and grain

Are farm, subfarm or plot, variety and season source identities exact and
versioned? Can a source row be mapped without fuzzy matching, display-name
fallback or latest/current lookup?

An unanswered question is a blocker, not an implicit negative or positive.

## 7. Required business source attestation

The attestation is a business authority record, not an informal note. The
minimum canonical template is:

```text
source_system=<stable source system code>
source_dataset=<stable dataset code>
source_version=<source schema or snapshot version>
business_owner_role=<role or system authority, not a person name>
attestation_effective_at=<timezone-aware effective timestamp>
attestation_version=<monotonic attestation version>
physical_event=FARM_PICK|OTHER
weighing_point=<field scale, harvest container, packhouse, factory, ...>
weighing_time_relative_to_pick=<before/during/after and bounded description>
all_picked_or_marketable_only=<ALL_PICKED|MARKETABLE_ONLY|UNKNOWN>
rejected_fruit_included=<true|false|unknown>
field_sorting_before_weight=<true|false|unknown>
packhouse_sorting_before_weight=<true|false|unknown>
postharvest_loss_before_weight=<true|false|unknown>
tare_policy=<stable policy description/code>
unit=KG|OTHER
measurement_method=<scale or measurement method code>
scale_calibration_authority=<role/system authority>
harvest_business_date_assignment_policy=<versioned rule>
late_entry_policy=<versioned rule>
missing_day_policy=<versioned rule>
correction_and_revision_policy=<versioned rule>
coverage_scope=<farms/seasons/records covered>
known_exclusions=<bounded list>
attestation_hash=<SHA-256 over canonical attestation payload>
```

The following governance rules are frozen:

```text
NO_PERSONAL_DATA_REQUIRED=true
ROLE_OR_SYSTEM_AUTHORITY_ONLY=true
UNSIGNED_NARRATIVE_IS_NOT_AUTHORITY=true
FIELD_NAME_IS_NOT_ATTESTATION=true
```

The source owner may be a role, system or formally governed authority. A
personal name, token, credential, raw spreadsheet row or private URL is not
required and must not be copied into Q2C evidence.

## 8. Attestation and equivalence decision procedure

The future Q2C evaluator must:

1. bind the attestation to `source_system`, `source_dataset` and
   `source_version`;
2. verify the attestation hash and effective version;
3. verify the physical event, quantity basis and unit;
4. verify marketability, sorting and post-harvest boundaries;
5. verify farm-local date assignment and late-entry behavior;
6. verify exact identity and grain coverage;
7. compare the attested source boundary to
   `model_harvested_marketable_quantity_kg` without modifying forecast data;
8. return one of the closed Q2C outcomes;
9. persist the evidence and decision hash for later Q2B binding.

If the attestation is missing, unsigned, expired, ambiguous, internally
contradictory or unavailable for the relevant source version, the result is
`BLOCKED_BY_MISSING_BUSINESS_ATTESTATION` or
`BLOCKED_BY_TRANSFORMATION_AUTHORITY`, as applicable.

## 9. Versioned transformations

Q2C does not define a universal factor that converts receipt, sorted,
marketable or retained quantities into FARM_PICK weight. Such a conversion is
valid only if a separately governed transformation authority provides:

- an explicit event boundary and direction;
- source and target units and grain;
- a versioned formula or calibrated mapping;
- applicability scope and time validity;
- source and parameter evidence;
- exact Decimal behavior and rounding policy;
- residual/error semantics;
- deterministic transformation and hash;
- business-owner attestation.

Absent all of these, a transformation result is not a Q2C target. In
particular, multiplying by or dividing by `sorting_retention_rate` or
`postharvest_retention_rate` is not authorized by this document.

## 10. Time and grain contract

The actual side uses `HARVEST_BUSINESS_DATE`, assigned in the farm's declared
timezone. The forecast-side candidate must be joined to the same business
date, not a factory receipt date or an ingestion timestamp.

The canonical identity grain is:

```text
SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
```

No aggregate may be accepted when it silently drops farm, subfarm/plot,
variety, season or harvest date. If a forecast output is aggregate-only, a
versioned deterministic membership map and row-set hash are required before
equivalence can be proven. Q2C does not create that map.

## 11. Future acceptance gates

Before any implementation or Q2B execution, all gates below must be true:

```text
BUSINESS_SOURCE_ATTESTATION=VERIFIED_VERSIONED
MARKETABILITY_EQUIVALENCE=PROVEN
SORTING_BOUNDARY_EQUIVALENCE=PROVEN
POSTHARVEST_BOUNDARY_EQUIVALENCE=PROVEN
TIME_BASIS_EQUIVALENCE=PROVEN
GRAIN_EQUIVALENCE=PROVEN
POSITIVE_RESULT_ALLOWED_ONLY_AFTER_ALL_DIMENSIONS_ARE_PROVEN
```

If the source is physically different but a versioned transformation is
authorized, the result may instead be:

```text
PHYSICAL_TARGET_ALIGNMENT=PROVEN_AFTER_VERSIONED_TRANSFORMATION
```

The implementation must fail closed for missing or contradictory evidence and
must not choose a proxy merely to unblock metrics.

## 12. Hard exclusions

This Q2C design does not authorize:

- production code, test code, migration, schema, model or parameter changes;
- source import, live database inspection or business data loading;
- Q2B runner, backtest execution or metric materialization;
- changing the actual label or forecast target;
- Q2D, Q2E, Q3, Q4, Q5 or later rounds;
- Ready, merge, issue closure, branch cleanup or worktree cleanup.

```text
Q2B_IMPLEMENTATION_READINESS=BLOCKED
Q2B_DESIGN=ARCHIVED
NEXT_REQUIRED_GATE=Q2D_HISTORICAL_LABEL_SOURCE_ATTESTATION
Q2D_AUTHORIZATION_NOT_IMPLIED=true
Q2B_IMPLEMENTATION=NOT_AUTHORIZED
BACKTEST_EXECUTION=NOT_AUTHORIZED
NO_STEP_IMPLIES_THE_NEXT=true
```
