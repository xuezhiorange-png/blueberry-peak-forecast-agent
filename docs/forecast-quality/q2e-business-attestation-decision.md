# Q2E Business Source Attestation Decision

```text
Q2E_ROUND=V0_2_S2_Q2E_BUSINESS_SOURCE_ATTESTATION
BASE_SHA=2e23441dade69fcdc74a64f2eccd220d40db5f27
```

## 1. Gate decision table

| Gate | Decision | Reason |
|---|---|---|
| A: source owner and source identity | `BLOCKED_BY_MISSING_SOURCE_OWNER` | No formal business role or governed source-system authority is identified |
| B: physical event and measurement boundary | `UNVERIFIED` | No attested weighing, sorting, rejection, loss, tare, calibration, or precision boundary |
| C: date, identity, and grain | `UNVERIFIED` | Contract rules exist, but no authoritative source release or identity/date evidence is supplied |
| D: revision and historical visibility | `UNVERIFIED` | No source publication boundary or immutable historical visibility manifest is supplied |
| E: physical target equivalence | `NOT_EVALUATED` | Gate A-D prerequisites are not all satisfied; no equivalence claim is made |

The only canonical round status is:

```text
Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_ATTESTATION_READY=false
ACTUAL_LABEL_STATUS=UNVERIFIED
ATTESTATION_PAYLOAD_SHA256=NONE
```

## 2. Frozen target and non-claims

```text
ACTUAL_PHYSICAL_EVENT=FARM_PICK
ACTUAL_QUANTITY_BASIS=OBSERVED_WEIGHT
ACTUAL_QUANTITY_UNIT=KG
ACTUAL_TIME_BASIS=FARM_LOCAL_HARVEST_BUSINESS_DATE
ACTUAL_MISSING_SEMANTICS=UNKNOWN_NOT_ZERO
ACTUAL_GRAIN=SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
```

These are frozen contract targets, not evidence that the historical dataset
has those physical semantics. Receipt, arrival, marketable model output, or
current master-data rows are not substituted for missing proof.

## 3. Required evidence to reopen the decision

The next evidence package must contain, without personal data or raw business
rows:

- formal source-owner role or governed authority code;
- stable source system, dataset, immutable version, and snapshot reference;
- versioned effective attestation with `ATTESTED` status;
- weighing and physical-boundary evidence proving FARM_PICK observed KG;
- farm-local date and canonical identity/grain authority;
- revision/correction/finalization policy and source publication boundary;
- immutable historical visibility snapshot or manifest that can reconstruct
  source state at a prediction cutoff;
- any explicit transformation needed to compare the actual label with
  `model_harvested_marketable_quantity_kg`.

## 4. Authorization boundary

```text
Q2B_IMPLEMENTATION_AUTHORIZED=false
BACKTEST_EXECUTION_AUTHORIZED=false
DATA_IMPORT_AUTHORIZED=false
RAW_BUSINESS_DATA_EXPORT_AUTHORIZED=false
MODEL_CHANGE_AUTHORIZED=false
PARAMETER_CHANGE_AUTHORIZED=false
SCHEMA_CHANGE_AUTHORIZED=false
MIGRATION_CHANGE_AUTHORIZED=false
TEST_CHANGE_AUTHORIZED=false
API_CHANGE_AUTHORIZED=false
FRONTEND_CHANGE_AUTHORIZED=false
READY=false
MERGE=false
ISSUE102_CLOSE=false
NO_STEP_IMPLIES_THE_NEXT=true
```

This decision only records the Q2E evidence status. It does not authorize Q2B
implementation, backtest execution, data collection, data import, or any later
slice.

## 5. Final decision

```text
SOURCE_OWNER_IDENTIFIED=NO
SOURCE_SYSTEM_IDENTIFIED=NO
SOURCE_DATASET_IDENTIFIED=NO
SOURCE_VERSION_IDENTIFIED=NO
MEASUREMENT_BOUNDARY_VERIFIED=NO
DATE_AND_GRAIN_AUTHORITY_VERIFIED=NO
REVISION_AUTHORITY_VERIFIED=NO
HISTORICAL_VISIBILITY_VERIFIED=NO
PHYSICAL_TARGET_EQUIVALENCE_VERIFIED=NO
Q2E_CURRENT_STATUS=BLOCKED_BY_MISSING_SOURCE_OWNER
BUSINESS_ATTESTATION_READY=false
```
