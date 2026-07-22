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
| direct FARM_PICK source | BLOCKED | no direct production source in audited repository |
| receipt proxy as label | NOT_APPLICABLE | explicitly forbidden as primary target |
| physical target equivalence | BLOCKED | harvested-marketable vs FARM_PICK equivalence not proven |
| forecast label grain | BLOCKED | Core row is compatible; Agent aggregate needs explicit path and proof |
| stable identity mapping | PARTIAL | I5/I7 evidence exists; Q2B forecast-side snapshot absent |
| duplicate forecast row policy | READY | contract requires structural failure |
| duplicate label row policy | READY | I7 snapshot uniqueness and immutable evidence |
| missing-day policy | READY | no zero-fill; explicit mask exclusion |
| leakage failure taxonomy | READY | contract enumerates structural and evaluation exclusions |
| daily MAE | PARTIAL | current helper exists; no Q2B materializer |
| daily WAPE | PARTIAL | current WMAPE helper exists; no Q2B materializer |
| daily sMAPE | NOT_IMPLEMENTED | Q2B contract only |
| daily zero-safe MAPE | NOT_IMPLEMENTED | Q2B epsilon policy only |
| daily signed bias | NOT_IMPLEMENTED | Q2B contract only |
| cumulative absolute/signed error | PARTIAL | related helpers exist; no Q2B evidence |
| cumulative absolute relative error | PARTIAL | related helper exists; Q2B policy differs |
| single-day peak errors | PARTIAL | P50 helpers exist; Q2B per-quantile target contract only |
| P80/P90 coverage | PARTIAL | current P50 coverage is not Q2B coverage |
| P80/P90 interval width | PARTIAL | related helper exists; no Q2B binding |
| 7/14/21-day horizons | NOT_IMPLEMENTED | Q2B contract only |
| Q3 sustained seven-day metric | NOT_AUTHORIZED | Q3 |
| Q4 naive baseline | NOT_AUTHORIZED | Q4 |
| Q5 quality report | NOT_AUTHORIZED | Q5 |
| Q6 model improvement | NOT_AUTHORIZED | later scope |
| persistence schema | NOT_IMPLEMENTED | design candidates only; no migration authorized |
| real-data aggregate inventory | BLOCKED | no live source query authorized or executed |
| implementation readiness | BLOCKED | primary `Q2B_IMPLEMENTATION_BLOCKED_BY_DATA` |

## Final status

```text
Q2B_IMPLEMENTATION_BLOCKED_BY_DATA
```

This does not authorize implementation. A future authorization must first
provide a real FARM_PICK source, prove physical target equivalence, and prove
lossless forecast/label grain alignment.
