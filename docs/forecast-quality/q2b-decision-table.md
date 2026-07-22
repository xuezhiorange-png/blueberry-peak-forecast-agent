# Q2B Point-in-Time Backtest Decision Table

> Status vocabulary is intentionally closed: `READY`, `PARTIAL`, `BLOCKED`,
> `NOT_IMPLEMENTED`, `NOT_AUTHORIZED`, `NOT_APPLICABLE`.

| decision | status | evidence / required next gate |
|---|---|---|
| Q2B scope is design-only | READY | contract doc; no runner implementation in this round |
| historical forecast cutoff | PARTIAL | replay node has cutoff; Q2B run identity not implemented |
| independent label observation cutoff | BLOCKED | I7 supports it, but no Q2B binding and no real source |
| `AS_OF_EVALUATION` mode | PARTIAL | I7 service contract exists; Q2B caller not implemented |
| `FINAL_ADJUDICATED` mode | PARTIAL | I7 immutable snapshot exists; Q2B caller not implemented |
| Task 9 replay authority | READY | exact replay-produced Task 9 row/result hash binding exists |
| Task 10 authority binding | PARTIAL | exact binding module exists; no Q2B output orchestration |
| historical model/code identity | BLOCKED | no Q2B persisted forecast authority snapshot |
| historical parameter identity | PARTIAL | Task 9 availability authority exists; Q2B bundle binding absent |
| weather visibility | PARTIAL | availability surfaces exist; no end-to-end Q2B assertion |
| direct FARM_PICK ingestion and I7 path | READY | production import/commit/snapshot path exists; real committed rows are not verified |
| real committed FARM_PICK data | BLOCKED | read-only aggregate discovery attempted but PostgreSQL client/container was unavailable |
| receipt proxy as label | NOT_APPLICABLE | explicitly forbidden as primary target |
| physical target equivalence | BLOCKED | harvested-marketable vs FARM_PICK equivalence not proven |
| forecast output authority | READY | Q2B v1 freezes `CORE_FORECAST_DAILY_ROW`; Agent aggregate is not used |
| forecast label grain | PARTIAL | Core row is structurally compatible; physical target equivalence and final identity proof remain open |
| stable identity mapping | PARTIAL | I5/I7 evidence exists; Q2B forecast-side snapshot absent |
| duplicate forecast row policy | READY | contract requires structural failure |
| duplicate label row policy | READY | I7 snapshot uniqueness and immutable evidence |
| missing-day policy | READY | no zero-fill; explicit mask exclusion |
| leakage failure taxonomy | READY | contract enumerates structural and evaluation exclusions |
| daily MAE | PARTIAL / P50_ONLY | current helper exists; no Q2B materializer |
| daily WAPE | PARTIAL / P50_ONLY | current WMAPE helper exists; no Q2B materializer |
| daily sMAPE | NOT_IMPLEMENTED / P50_ONLY | Q2B contract only |
| daily MAPE | PARTIAL / P50_ONLY | Q1 uses actual > 0 denominator with eligibility/exclusion counts; Q2B materializer absent |
| daily bias | NOT_IMPLEMENTED / P50_ONLY | Q2B contract only |
| daily relative bias | NOT_IMPLEMENTED / P50_ONLY | all comparable rows remain in numerator; zero total actual is not computable |
| season cumulative actual/forecast/error | PARTIAL / P50_ONLY | Q1 formulas are frozen; no Q2B evidence |
| daily absolute error sum | PARTIAL / P50_ONLY | separate sum(abs(forecast_p50-actual)); not a cumulative-relative numerator |
| cumulative absolute relative error | PARTIAL / P50_ONLY | absolute season-total error divided by absolute season-total actual |
| single-day peak fields | PARTIAL / P50_P80_P90 | exact per-quantile date and quantity fields are frozen |
| quantile coverage | BLOCKED | conditional on verified true upper-quantile semantics |
| pinball loss | BLOCKED | conditional on verified quantile semantics |
| P80/P90 upper spread | BLOCKED | not an interval width; lower bound unavailable and quantile gate is unmet |
| P50/P80/P90 semantics | BLOCKED | semantics not verified; coverage and pinball loss not computable |
| 7/14/21-day horizons | NOT_IMPLEMENTED | Q2B contract only |
| Q3 sustained seven-day metric | NOT_AUTHORIZED | Q3 |
| Q4 naive baseline | NOT_AUTHORIZED | Q4 |
| Q5 quality report | NOT_AUTHORIZED | Q5 |
| Q6 model improvement | NOT_AUTHORIZED | later scope |
| persistence schema | NOT_IMPLEMENTED | design candidates only; no migration authorized |
| real-data aggregate inventory | BLOCKED | discovery attempted; client/container unavailable, current availability unknown |
| implementation readiness | BLOCKED | independent blockers remain; see the blocker set below |

## Final status

```text
Q2B_IMPLEMENTATION_READINESS=BLOCKED
Q2B_BLOCKER_SET=
  REAL_DATA_NOT_VERIFIED
  PHYSICAL_TARGET_NOT_ALIGNED
  FORECAST_AUTHORITY_NOT_FULLY_BOUND
  HISTORICAL_CODE_IDENTITY_NOT_BOUND
  QUANTILE_SEMANTICS_NOT_VERIFIED
POINT_METRIC_QUANTILE=P50_ONLY
SINGLE_DAY_PEAK_QUANTILES=P50_P80_P90
QUANTILE_COVERAGE_DESIGN=CONDITIONAL_NOT_COMPUTABLE
PINBALL_LOSS_DESIGN=CONDITIONAL_NOT_COMPUTABLE
INTERVAL_WIDTH_STATUS=NOT_COMPUTABLE_LOWER_BOUND_UNAVAILABLE
```

This does not authorize implementation. A future authorization must first
verify real FARM_PICK rows, prove physical target equivalence, bind historical
code and forecast authority identities, and verify quantile semantics.
