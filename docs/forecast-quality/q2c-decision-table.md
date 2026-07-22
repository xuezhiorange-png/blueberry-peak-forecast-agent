# Q2C Physical Target Equivalence Decision Table

> Base: `480f64cf093827dc7401ae9cdafe7b9f870bfd66`
> Scope: Q2C audit/design freeze only

## 1. Governance

| decision | status | evidence or next gate |
|---|---|---|
| Q2C scope | READY | contract and evidence audit are docs-only |
| production implementation | NOT_AUTHORIZED | no code, tests or migration in Q2C |
| Q2B implementation | BLOCKED | physical target and independent Q2B blockers remain |
| backtest execution | NOT_AUTHORIZED | no runner exists in this round |
| real external source inspection | NOT_EXECUTED | outside authorized repository audit |
| business attestation | BLOCKED | no versioned owner/system attestation supplied |

## 2. Frozen label boundary

| field | frozen value |
|---|---|
| physical event | `FARM_PICK` |
| quantity basis | `OBSERVED_WEIGHT` |
| quantity unit | `KG` |
| time basis | `FARM_LOCAL_HARVEST_BUSINESS_DATE` |
| missing semantics | `UNKNOWN_NOT_ZERO` |
| grain | `SEASON x FARM x SUBFARM_OR_PLOT x VARIETY x HARVEST_BUSINESS_DATE` |
| primary proxy policy | receipt/arrival is forbidden |

## 3. Candidate target decisions

| candidate | result | reason |
|---|---|---|
| `natural_maturity_supply_kg` | `NOT_ALIGNED_MATURITY_NOT_PICK` | maturity supply is not a physical pick |
| `harvestable_mature_quantity_kg` | `NOT_ALIGNED_AVAILABLE_NOT_PICKED` | available inventory is not picked weight |
| `model_harvested_marketable_quantity_kg` | `CANDIDATE_REQUIRES_BUSINESS_ATTESTATION` | only candidate retained for exact proof |
| `effective_marketable_quantity_kg` | `NOT_ALIGNED_POST_PICK_RETENTION_BOUNDARY` | includes sorting and post-harvest retention |
| `arrival_quantity_kg` | `NOT_ALIGNED_ARRIVAL_EVENT` | arrival is downstream of pick |
| `final_corrected_arrival_quantity_kg` | `NOT_ALIGNED_ARRIVAL_EVENT` | corrected arrival remains downstream |
| `FactReceiptDaily.weight_kg` | `FORBIDDEN_RECEIPT_PROXY` | factory receipt is not FARM_PICK |

## 4. Equivalence result

| dimension | result | required evidence |
|---|---|---|
| physical event | `NOT_VERIFIED` | owner attests physical pick boundary |
| quantity basis | `NOT_VERIFIED` | observed scale measurement, not estimate |
| marketability | `NOT_VERIFIED` | all-picked vs marketable-only policy |
| sorting boundary | `NOT_VERIFIED` | field and packhouse timing |
| post-harvest boundary | `NOT_VERIFIED` | loss/retention before measurement |
| time basis | `PARTIAL_CONTRACT_COMPATIBLE_NOT_VERIFIED` | farm-local date rule and late entries |
| grain | `PARTIAL_CONTRACT_COMPATIBLE_NOT_VERIFIED` | exact membership and identity evidence |
| overall alignment | `BLOCKED_BY_MISSING_BUSINESS_ATTESTATION` | no positive equivalence claim allowed |

## 5. Attestation completeness gate

| field group | required | current status |
|---|---:|---|
| source identity/version | yes | not supplied |
| business owner role/system authority | yes | not supplied |
| physical event and weighing point | yes | not supplied |
| weighing timing relative to pick | yes | not supplied |
| all-picked vs marketable-only | yes | not supplied |
| rejected fruit inclusion | yes | not supplied |
| field/packhouse sorting timing | yes | not supplied |
| post-harvest loss timing | yes | not supplied |
| tare and measurement method | yes | not supplied |
| scale calibration authority | yes | not supplied |
| farm-local date assignment | yes | not supplied |
| late/missing/correction policy | yes | not supplied |
| coverage and exclusions | yes | not supplied |
| canonical attestation hash | yes | not supplied |

The attestation may identify a role or governed system. Personal data is not
required. An unsigned narrative or field name is not authority.

## 6. Closed result vocabulary

```text
PROVEN_EXACT
PROVEN_AFTER_VERSIONED_TRANSFORMATION
BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
BLOCKED_BY_SEMANTIC_MISMATCH
BLOCKED_BY_TRANSFORMATION_AUTHORITY
BLOCKED_BY_GRAIN_OR_DATE_MISMATCH
```

No other positive or fallback result is valid. In particular, `FactReceiptDaily`
cannot become the primary label merely because it has a weight and identity
columns.

## 7. Future acceptance matrix

| gate | acceptance condition | failure result |
|---|---|---|
| source attestation | hash-valid, versioned, role/system-authorized | missing-attestation blocker |
| event | exact FARM_PICK | semantic mismatch |
| quantity | observed weight in KG | semantic mismatch |
| marketability | same boundary or authorized transformation | transformation/semantic blocker |
| sorting | same before/after boundary | transformation/semantic blocker |
| post-harvest | same before/after boundary | transformation/semantic blocker |
| date | farm-local harvest business date | grain/date mismatch |
| identity | exact season/farm/subfarm-or-plot/variety mapping | grain/date mismatch |
| missingness | UNKNOWN_NOT_ZERO preserved | semantic mismatch |
| deterministic evidence | repeated input yields same decision/hash | evidence blocker |
| transformation | separately versioned and authorized if needed | transformation authority blocker |
| Q2B target | only after positive Q2C result | `UNRESOLVED` |

## 8. Final frozen status

```text
ACTUAL_TARGET=FARM_PICK_OBSERVED_WEIGHT_KG
FORECAST_TARGET_CANDIDATE=model_harvested_marketable_quantity_kg
PHYSICAL_TARGET_ALIGNMENT=BLOCKED_BY_MISSING_BUSINESS_ATTESTATION
BUSINESS_SOURCE_ATTESTATION=NOT_AVAILABLE
Q2C_V1_FORECAST_TARGET=UNRESOLVED
Q2B_PHYSICAL_TARGET_BLOCKER=OPEN

Q2B_DESIGN=ARCHIVED
NEXT_ROUND=Q2C_PHYSICAL_TARGET_EQUIVALENCE
Q2B_IMPLEMENTATION=NOT_AUTHORIZED
BACKTEST_EXECUTION=NOT_AUTHORIZED
Q2B_IMPLEMENTATION_READINESS=BLOCKED
```

## 9. Exclusions

This table authorizes no implementation, data import, migration, model or
parameter change, Q2B runner, backtest execution, Q2D/Q2E/Q3-Q5 work, Ready,
merge, issue closure, branch cleanup or worktree cleanup.

```text
PRODUCTION_CODE_CHANGED=false
TEST_CODE_CHANGED=false
MIGRATION_CHANGED=false
NO_STEP_IMPLIES_THE_NEXT=true
```
