# Q2B Source Authority and Leakage Audit

> Audit type: read-only repository and checked-artifact audit
> Base: `6a2489e8685d2ffb2cff83597503f2dcd0203621`
> Issue: #102
> No live production rows, DDL, DML or backtest execution were performed.

## 1. Baseline and evidence boundary

PR #122 is merged into `main` at `6a2489e8685d2ffb2cff83597503f2dcd0203621`.
The main push CI observed for that merge is run `29880056152`, completed with
success. The audited Alembic head is the single
`0022_finalized_at_lineage_basis_member` head.

This audit covers checked-in application code, ORM models, migrations, tests
and forecast-quality documents. It does not claim that an external farm ERP,
picking system, spreadsheet, weighing system or unconnected database has no
data. No DSN was opened and no row-level business data was exported.

## 2. Existing authority surfaces

| area | source evidence | classification | Q2B interpretation |
|---|---|---|---|
| rolling backtest node identity and cutoff | `backend/app/rolling_backtest/schemas.py`, `models/rolling_backtest.py` | PRODUCTION_IMPLEMENTED | reusable input boundary, not a Q2B runner |
| `retrospective_replay` dispatch | `rolling_backtest/replay_pipeline.py`, `replay_audit.py` | PRODUCTION_IMPLEMENTED | Task 9 replay/audit path exists |
| `forecast_effective_cutoff_at` | `models/harvest_state.py`, migration 0015, `replay_metadata.py` | PRODUCTION_IMPLEMENTED | forecast-side carrier exists; evaluation binding is separate |
| `replay_executed_at` | migration 0015 and replay metadata writer | PRODUCTION_IMPLEMENTED | explicit caller/database-authoritative replay timestamp |
| `replay_code_version` | migration 0015 and replay metadata writer | PRODUCTION_IMPLEMENTED | runtime identity is explicit for Task 9 replay |
| `replay_run_correlation_id` | migration 0015 and replay metadata writer | PRODUCTION_IMPLEMENTED | correlation evidence exists |
| Task 9 historical authority | migration 0014, `models/task9_authority.py` | PRODUCTION_IMPLEMENTED | rows have availability dates, lifecycle, source and row hashes |
| Task 9 replay authority | `replay_pipeline.py`, `replay_task10_binding.py` | PRODUCTION_IMPLEMENTED | exact replay-produced Task 9 row/result hash is required |
| Task 10 binding | `replay_task10_binding.py` | PARTIAL | exact Task 9 binding exists; Q2B forecast output/evaluation orchestration does not |
| replay-trained Task 10 | `replay_trained_*`, Task 12 documents/tests | PARTIAL | explicit policy and cutoff filters exist, but this is not the Q2B runner |
| I7 actual-harvest snapshot | `actual_harvest_labels/service.py`, `models.py`, migration 0021 | PRODUCTION_IMPLEMENTED | immutable AS-OF and FINAL-ADJUDICATED evidence exists |
| I7 snapshot identity hashes | `actual_harvest_labels/hashes.py`, `service.py` | PRODUCTION_IMPLEMENTED | request/instance/manifest/label hashes are persisted |
| actual-harvest source records | no direct FARM_PICK production model/table in audited repository | ABSENT | physical evaluation is blocked without a real source |
| receipt facts | `models/analytics.py:87`, `FactReceiptDaily` | PRODUCTION_IMPLEMENTED | arrival/receipt proxy only, never primary actual harvest |
| metrics: current rolling slice | `rolling_backtest/metrics.py`, `service.py`, `cli.py` | PARTIAL | pure metric helpers exist; Q2B binding, mask and target proof do not |
| metric golden/helper tests | `backend/tests/rolling_backtest` and related tests | TEST_ONLY | evidence of formulas, not production runner authority |
| Q2B runner/API/CLI | no Q2B runner module or endpoint | NOT_IMPLEMENTED | design only in this PR |

## 3. Existing forecast grains and physical fields

`backend/app/agent/schemas.py:807` defines an Agent `ForecastDailyRow` with
date and six physical quantity families, each with P50/P80/P90. Its identity is
carried by request/location/season context; variety appears in
`per_variety_contribution`. It is therefore an aggregate output, not a
self-contained I7 label-grain row.

`backend/app/models/core_forecast.py:154` defines
`CoreForecastDailyRowModel`. Its unique business key is
`core_forecast_run_id`, date, farm, subfarm, variety and quantile. This is the
preferred structural candidate for Q2B alignment because it matches the I7
identity dimensions, but the audited code does not prove that its
`model_harvested_marketable_quantity_kg` is the same physical event as a
FARM_PICK observed weight.

`backend/app/models/analytics.py:87` defines `FactReceiptDaily` at season,
receipt date, factory, farm key, subfarm key and variety, with `weight_kg`.
The Q2A source contract labels this a factory-receipt/arrival proxy. It cannot
be used as actual-harvest ground truth.

## 4. Actual-harvest and I7 evidence

I7 snapshot headers persist visibility mode, optional label cutoff, request and
instance hashes, source manifest set hash, winner manifest hash, label-row-set
hash and label snapshot hash. Winner rows persist stable business keys,
canonical record hashes, source-time authority, commit manifest, mapping
snapshot, resolved identity snapshot, registry content and row hashes. Label
rows aggregate exact Decimal actual quantity at
`SEASON x FARM x SUBFARM x VARIETY x HARVEST_BUSINESS_DATE`.

This proves that I7 can supply an immutable evaluation snapshot once a valid
source commit exists. It does not prove the existence of a production FARM_PICK
source in this repository. The Q2A data audit therefore remains:

```text
DIRECT_ACTUAL_HARVEST_SOURCE_STATUS=NOT_FOUND_IN_CURRENT_REPOSITORY
LIVE_DATABASE_SOURCE_DISCOVERY_STATUS=NOT_EXECUTED
EXTERNAL_BUSINESS_SOURCE_DISCOVERY_STATUS=NOT_AUTHORIZED_NOT_EXECUTED
REAL_DATA_COVERAGE_STATUS=NOT_VERIFIED_SOURCE_UNAVAILABLE
PRIMARY_ACTUAL_HARVEST_LABEL_READY=NO
```

## 5. Leakage vector audit

| vector | current evidence | status | required Q2B gate |
|---|---|---|---|
| future actual records/revisions | I7 AS-OF source-time and committed-lineage preflight | PARTIAL | bind the exact I7 snapshot; never rebuild labels |
| future weather | weather models contain `available_at`; replay resolver audits source visibility | PARTIAL | persisted per-input visibility hash at forecast cutoff |
| future Task 9 authority | migration 0014 has `available_at_local_date`, ranges, lifecycle and row hashes | PRODUCTION_IMPLEMENTED / Q2B PARTIAL | assert every selected row is visible at cutoff |
| future Task 10 prediction/artifact | replay binding requires exact replay Task 9 result and policy checks | PARTIAL | bind forecast output to exact model/parameter/data identity |
| future model version | replay-trained identity has cutoff fields and hash checks | PARTIAL | historical model artifact availability must be persisted |
| future parameter version | Task 9 authority rows have availability dates | PARTIAL | use the exact Task 9 authority bundle hash |
| future mapping/master data | I5/I7 mapping and resolved identity evidence is immutable | PARTIAL | forecast-side master-data snapshot is still unbound |
| manual corrections | I7 revision/status/evidence contract is explicit | PRODUCTION_IMPLEMENTED / Q2B PARTIAL | select only the snapshot named by the run identity |
| current code/defaults | no Q2B runner binds a historical code/config snapshot | ABSENT | `FORECAST_AUTHORITY_DRIFT` on missing binding |
| current main or latest row fallback | replay modules explicitly reject latest/current fallback in their scope | PRODUCTION_IMPLEMENTED / Q2B PARTIAL | end-to-end runner must preserve the rejection |

## 6. Audit classifications for requested metrics

The classifications below distinguish current production metric helpers from
Q2B point-in-time availability. A unit or golden helper is never treated as a
production backtest runner.

| requested Q2B metric | current repository classification | reason |
|---|---|---|
| `daily_mae` | PARTIAL | `mean_absolute_error` helper exists; no Q2B aligned-row materializer |
| `daily_wape` | PARTIAL | `wmape` helper exists; no dual-cutoff binding |
| `daily_smape` | ABSENT | no frozen Q2B sMAPE implementation |
| `daily_zero_safe_mape` | ABSENT | no Q2B epsilon policy implementation |
| `daily_signed_bias` | ABSENT | no Q2B daily signed-bias implementation |
| cumulative absolute/signed error | PARTIAL | related cumulative formulas exist, not Q2B scoped evidence |
| cumulative absolute relative error | PARTIAL | related cumulative relative helper exists; Q2B contract differs and lacks runner |
| single-day peak date/quantity errors | PARTIAL | P50 peak helpers exist; Q2B per-quantile target-bound metrics do not |
| P80/P90 coverage | PARTIAL | current coverage slice is P50-oriented, not Q2B P80/P90 target contract |
| P80/P90 interval width | PARTIAL | related interval-width helper exists, no Q2B materialization |
| horizons 7/14/21 | ABSENT | no Q2B horizon-scoped runner/evidence |
| sustained seven-day peak | NOT_AUTHORIZED | Q3 scope |
| naive baseline | NOT_AUTHORIZED | Q4 scope |
| quality report | NOT_AUTHORIZED | Q5 scope |

## 7. Data inventory result

The inventory was read-only and aggregate-only. No live DSN was opened because
the repository contains no authorized production actual-harvest source and no
local database file in the isolated worktree. The inventory is therefore a
schema/source inventory, not a row count claim.

| source | schema evidence | safe inventory result | status |
|---|---|---|---|
| direct FARM_PICK source | no model/table/migration found in audited scope | zero repository objects found; no live row claim | NOT_VERIFIED_SOURCE_UNAVAILABLE |
| receipt/arrival proxy | `FactReceiptDaily` and analytics migrations | object exists; no rows queried | PRODUCTION_SCHEMA_ONLY |
| I5 committed evidence | actual-harvest import/commit tables and hashes | object exists; no rows queried | PRODUCTION_SCHEMA_ONLY |
| I7 snapshot | four snapshot tables and immutable triggers | object exists; no rows queried | PRODUCTION_SCHEMA_ONLY |
| Task 9 authorities | migration 0014 and ORM models | authority schema exists; no rows queried | PRODUCTION_SCHEMA_ONLY |
| forecast output | core forecast run/daily rows and Agent schemas | output schema exists; no rows queried | PRODUCTION_SCHEMA_ONLY |

No fixture, test row, receipt row, or I7 test snapshot is promoted to real
business data. Until an authorized source artifact and a real aligned example
are supplied, Q2B implementation readiness is `NO`.

## 8. Final audit conclusion

```text
Q2A_I7_POST_MERGE=PASS
RETROSPECTIVE_REPLAY_STATUS=PRODUCTION_PARTIAL_TASK9_AUTHORITY_ONLY
TASK9_REPLAY_AUTHORITY_STATUS=PRODUCTION_IMPLEMENTED
TASK10_AUTHORITY_BINDING_STATUS=PARTIAL_EXACT_BINDING_NO_Q2B_RUNNER
FORECAST_PHYSICAL_TARGET_ALIGNMENT=BLOCKED_BY_PHYSICAL_TARGET_GAP
FORECAST_LABEL_GRAIN_ALIGNMENT=BLOCKED_BY_GRAIN_ALIGNMENT
DUAL_CUTOFF_MODEL=DESIGN_FROZEN_NOT_IMPLEMENTED
HISTORICAL_CODE_IDENTITY=PARTIAL_NOT_Q2B_BOUND
HISTORICAL_PARAMETER_IDENTITY=PARTIAL_TASK9_AUTHORITY_ONLY
I7_LABEL_SNAPSHOT_BINDING=PRODUCTION_IMPLEMENTED_NOT_Q2B_BOUND
DAILY_METRICS_DESIGN=DESIGN_FROZEN
QUANTILE_COVERAGE_DESIGN=DESIGN_FROZEN
SINGLE_DAY_PEAK_DESIGN=DESIGN_FROZEN
SUSTAINED_7DAY_STATUS=NOT_AUTHORIZED_Q3
NAIVE_BASELINE_STATUS=NOT_AUTHORIZED_Q4
REAL_DATA_COVERAGE_STATUS=NOT_VERIFIED_SOURCE_UNAVAILABLE
Q2B_IMPLEMENTATION_READINESS=BLOCKED_BY_DATA
```

The primary blocker is missing verifiable FARM_PICK data. Physical target and
grain alignment are independent secondary blockers and must be resolved before
implementation authorization.
