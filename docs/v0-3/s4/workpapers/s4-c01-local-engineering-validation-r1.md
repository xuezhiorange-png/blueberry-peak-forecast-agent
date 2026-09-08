# S4-C01 local engineering validation R1

## Disposition

This workpaper records the authorized local engineering lane only. It is not
production forecast authority, retained historical PIT authority, pilot
approval, or a final model-selection decision.

```text
TASK_ID=V0_3_S4_LOCAL_ENGINEERING_VALIDATION_BOOTSTRAP_AND_C01_EXECUTION_R1
BASE_MAIN_SHA=77e3d8ac63d794babfe0c8549fd34d0467f0d57e
EVALUATION_LANE=LOCAL_ENGINEERING_REPLAY
TEST_REMAINS_SEALED=true
TEST_EVALUATION_PERFORMED=false
PRODUCTION_DATABASE_MUTATION_PERFORMED=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The local PostgreSQL instance was created as an isolated user-owned database
named `blueberry_peak_s4_local_engineering` on loopback port `55435`. The
repository Alembic head applied was
`0031_forecast_authority_task10_extension`. No production endpoint, historical
authority store, Docker volume, or TEST payload was used.

## Frozen SOURCE-002 inputs

The raw object was verified before the local rebuild:

| identity | value |
| --- | --- |
| raw object SHA-256 | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| raw object byte count | `28668416` |
| declared raw row count | `233171` |
| materialized dataset identity | `f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785` |
| TRAIN rows / bytes | `16224 / 9087071` |
| TRAIN content SHA-256 | `be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2` |
| VALIDATION rows / bytes | `8006 / 4484905` |
| VALIDATION content SHA-256 | `4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06` |
| TEST rows | `0` |
| controlled rebuild parity | `PASS` |

The existing controlled Lane A → Lane B → Lane C → Lane D path was reused.
The runner reads only the persisted TRAIN and VALIDATION partition bytes from
the isolated database and checks them against the frozen partition hashes.
TEST metadata is checked only for zero rows; TEST content is not parsed or
scored.

## Replay contract

The regenerated incumbent is explicitly classified as
`LOCAL_ENGINEERING_REPLAY`, with model identity `V0_2_CURRENT_MODEL`. It uses
the current frozen configuration:

```text
curve.spline_knot_count=6
curve.ridge_alpha=0.10
random_seed=20260624
INCUMBENT_CONFIG_HASH=3571477d5822f57cd2c424620915560e22481f48983b397a1f1b8934e1a7612c
NO_FUTURE_LABEL_LEAKAGE=true
NO_TEST_ACCESS=true
```

The incumbent replay was run twice. Row-set identity, forecast identity,
metrics, and aggregate payloads were exactly equal:

```text
LOCAL_INCUMBENT_REPLAY_STATUS=PASS
LOCAL_INCUMBENT_REPLAY_COUNT=2
LOCAL_INCUMBENT_REPLAY_DETERMINISTIC=true
INCUMBENT_PREDICTION_IDENTITY_SHA256=d27f732c4be8566e88ace8a141f9a5cd143ec61ddcf4bdddd94dd256e318a39f
ACTUAL_LABEL_SET_IDENTITY_SHA256=32844f7cb63fdee2c6f6adba83b7c7f1d748b28c3d3e52e8c53d5cf35ccfa8f4
BUSINESS_GRAIN_SET_IDENTITY_SHA256=3a417a95293bab196562ad035632f482427ff3e288699351c6ee82c98edbda6f
```

The incumbent aggregate metrics were:

| metric | value |
| --- | ---: |
| daily_wape | `0.824404` |
| daily_mae | `1177.913143` |
| cumulative_absolute_error_kg | `9159967.333977` |
| single_day_peak_quantity_absolute_error_kg_q | `23639.741893` |
| sustained_7day_quantity_absolute_error_kg_q | `2801815.894075` |
| P80_COVERAGE | `0.134649` |
| P90_COVERAGE | `0.193355` |

## Candidate 01 execution

The frozen Candidate 01 manifest was validated before execution:

```text
CANDIDATE_ID=01_parameter_calibration
CANDIDATE_01_PARAMETER_MANIFEST_HASH=eba8af27f926635d654aa4c5331f323a9e4edfa399659e1917b729ac6550910b
RANDOM_SEED=20260624
RUN_COUNT=4
```

All four runs used the same TRAIN rows, VALIDATION rows, actual labels,
cutoff policy, forecast horizon policy, business-grain set, and metric
contract. The incumbent reference replay is not counted as a candidate
evaluation. The four candidate invocations are real validation-driven
engineering evaluations:

| run | frozen delta | daily_wape | daily_mae | cumulative abs. error | P80 | P90 | primary relation | guardrail | coverage |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| 1 | knot 5, alpha 0.10 | `0.833222` | `1190.512567` | `9278025.113961` | `0.128903` | `0.181864` | WORSE | BLOCKED | BLOCKED |
| 2 | knot 7, alpha 0.10 | `0.820739` | `1172.676475` | `9098307.074315` | `0.141519` | `0.202348` | IMPROVED | BLOCKED | BLOCKED |
| 3 | knot 6, alpha 0.05 | `0.823557` | `1176.703613` | `9147321.490436` | `0.135274` | `0.194479` | IMPROVED | BLOCKED | BLOCKED |
| 4 | knot 6, alpha 0.20 | `0.825535` | `1179.529266` | `9176280.083193` | `0.133525` | `0.193105` | WORSE | BLOCKED | BLOCKED |

The complete run payload also contains the required aggregate breakdown
metrics for all six axes:

```text
forecast_horizon_days: 38 cells
farm_business_key: 74 cells
subfarm_business_key: 186 cells
variety_business_key: 17 cells
season_business_key: 1 cell
model_identity: 1 cell
BREAKDOWN_METRICS_SET_SHA256=47a4027f5a641faf13206c813fc5e869eefd8bab07e2b3655ff04327858ef058
```

Runs 2 and 3 improved the primary metric and the lower-is-better guardrails,
but every run was correctly blocked by the existing coverage gate because at
least one required breakdown cell was below
`MIN_COMPARABLE_ROWS_FOR_REPORTING=10`. No cell was silently excluded. As a
result:

```text
CANDIDATE_01_LOCAL_ENGINEERING_BEST_RUN=NONE
CANDIDATE_01_LOCAL_ENGINEERING_RESULT=BLOCKED
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
```

This task does not issue Candidate 02 authorization. A future Candidate 02
task, if separately authorized, must consume the remaining budget under the
frozen governance contract.

## Budget and execution identity

```text
LOCAL_ENGINEERING_VALIDATION_EVALUATION_COUNT=4
CANDIDATE_01_ENGINEERING_RUN_COUNT=4
EFFECTIVE_VALIDATION_EVALUATIONS_CONSUMED=4
REMAINING_EFFECTIVE_VALIDATION_BUDGET=28
VALIDATION_BUDGET_STATUS=PASS
```

The PASS result was generated by runner commit
`83084a583497547e317ccdfa2a6c5fbc91a9f9d9`. After that controlled run, the
runner was hardened so its existing-database path projects only partition
metadata and loads TRAIN/VALIDATION payloads explicitly; it does not parse or
load TEST content. The follow-up commit also added type annotations only. A
direct current-code database preflight re-verified the same dataset identity,
partition hashes, rebuild parity, and zero TEST rows. No scoring semantics,
candidate definitions, or metric results changed, and the four-evaluation
budget was not consumed a second time.

## Boundaries

```text
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
PRODUCTION_DATABASE_MUTATION_PERFORMED=false
PRODUCTION_MODEL_CHANGE=false
PARAMETER_CHANGE_TO_PRODUCTION=false
MODEL_APPROVED_FOR_PILOT=false
FINAL_MODEL_SELECTED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_C01_LOCAL_ENGINEERING_RESULT_REVIEW
```
