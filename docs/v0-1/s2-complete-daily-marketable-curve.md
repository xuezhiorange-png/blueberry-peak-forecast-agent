# V0.1-S2 Complete Daily Marketable Curve

## Scope and boundary

V0.1-S2 is a read-only projection over persisted Task 8 maturity authority
and persisted Task 9 detailed harvest-state member rows. It does not write
database rows, add persistence tables, alter the Agent daily-row contract, or
reimplement either upstream numerical algorithm.

The production entry point is
`backend.app.core_forecast.service.compose_complete_daily_marketable_curve`.
The production read adapter is
`backend.app.core_forecast.repository.SqlAlchemyCoreForecastRepository`.
The adapter reads `MaturityForecastRun`, `MaturityModelArtifact`,
`MaturityDailyPredictionModel`, `HarvestStateRun`, and
`HarvestStateDailyMemberRowModel` through the caller-owned SQLAlchemy session.

S2 emits rows at:

```text
HARVEST_BUSINESS_DATE x farm x subfarm x variety x forecast_quantile
```

The fixed quantile set is `P50`, `P80`, and `P90`. A requested scope must have
one complete calendar row for every requested date and every quantile. Missing,
duplicate, extra, or malformed authority blocks the whole result; no partial
curve is returned.

## Authority mapping

Task 8 is reused as the marketable-basis maturity authority. The service
requires a completed forecast run, an artifact with a lowercase SHA-256 hash,
date coverage for the request, and daily P50/P80/P90 predictions. It does not
multiply the Task 8 or Task 9 quantity by `marketable_rate` again.

Task 9 is reused as the detailed member-state authority. The service requires
the completed run to match season, destination factory, date range, Task 8
forecast run, and Task 8 artifact hash. Scope quantities are read only from
`HarvestStateDailyMemberRowModel`; in particular:

```text
effective_harvest_capacity_kg
    = allocated_harvest_capacity_kg
```

Pool-level capacity fields and arrival quantities are not used for the S2
daily curve. `subfarm_id` must be present, and the service reconciles the sum
of member natural-maturity supply to each Task 8 daily quantile exactly with
`Decimal` equality.

## Retention policy

The caller supplies an explicit `MarketableRetentionPolicySnapshot`. Each
requested `(forecast_season_id, forecast_season_code, farm_id, subfarm_id,
variety_id)` must have exactly one matching entry. There is no default, global,
nearest, latest, farm-level, subfarm-level, or variety-level fallback.

Both retention rates are canonical finite Decimal strings in `[0, 1]`. The
policy source, version, and explicit lowercase SHA-256 identity are required.
S1 did not freeze a policy-hash preimage, so S2 validates the hash shape and
preserves the supplied identity without inventing a new hash contract.

## Quantity and hash rules

All upstream quantities and policy rates are handled as `Decimal`; native
floats and non-finite values are rejected. Derived quantities are quantized to
six decimal places with `ROUND_HALF_EVEN` and serialized as fixed six-place
strings. Negative zero is not emitted.

The only S2 marketable conversion is:

```text
effective_marketable_quantity_kg
    = model_harvested_marketable_quantity_kg
      x sorting_retention_rate
      x postharvest_retention_rate
```

For every output row, `row_hash` is SHA-256 over UTF-8
`canonical_json_dumps(row_without_row_hash)` from
`backend.app.rolling_backtest.canonical`. The curve hash is a SHA-256 over
the ordered rows and the frozen schema version; it is an output identity only
and is not persisted by S2.

## Fail-closed conditions

The service returns `BLOCKED` with no rows for missing or incomplete Task 8 or
Task 9 authority, malformed hashes, lineage or scope mismatch, retention
policy missing/conflict/invalid, Task 8/Task 9 supply mismatch, duplicate or
incomplete calendar series, cross-day continuity failure, or a daily state
invariant failure. The result schema enforces the completed/blocked XOR
contract.

For each member row the service validates:

```text
available = opening + natural_supply
harvestable = available - loss
harvested <= harvestable
harvested <= allocated_capacity
closing = harvestable - harvested
backlog = closing
opening + natural_supply = loss + harvested + closing
opening[d] = closing[d - 1] for each scope and quantile
```

The entire post-read composition path is fail closed. Expected malformed
authority data, Decimal conversion or quantization failures, and Pydantic
output validation failures are converted to a deterministic blocker; they do
not escape to the caller and never produce partial rows. Task 8 quantity
failures use `TASK8_TASK9_SUPPLY_RECONCILIATION_FAILED`, while malformed Task 9
member quantities use `DAILY_CURVE_STATE_INVARIANT_FAILED`.

Retention policy resolution distinguishes missing requested entries from
duplicate or extra entries (`MARKETABLE_RETENTION_POLICY_MISSING` versus
`MARKETABLE_RETENTION_POLICY_CONFLICT`). An invalid or bypassed policy value,
including negative zero, is `MARKETABLE_RETENTION_POLICY_INVALID`. Output
quantity and rate fields use the exact lexical six-place contract
`^(?:0|[1-9]\\d*)\\.\\d{6}$`.

State-equation failures use `DAILY_CURVE_STATE_INVARIANT_FAILED`; a cross-day
inventory break uses the dedicated `DAILY_CURVE_CONTINUITY_FAILED` blocker.

## Fixture replay evidence

`backend/tests/core_forecast/test_complete_daily_curve_service.py` constructs
synthetic upstream authority from the S1 `daily_inputs` fields only. Retention
policy, authority hashes, effective quantities, and row hashes are not read
from expected output to build the service inputs. The production service
computes policy resolution, Decimal formatting, effective quantity, ordering,
row hashes, and curve hash independently.

The exact S1 oracle remains unchanged:

```text
rows=1080
unique_keys=1080
series=12
rows_per_series=90
transitions=1068
```

`backend/tests/integration/test_v0_1_s2_complete_daily_curve_postgres.py`
seeds the existing ORM authority tables in a real PostgreSQL session, calls
the production SQLAlchemy repository and S2 service, and compares all 1080
serialized rows byte-for-byte with the canonical fixture. It is uniquely owned
by the `postgres-domain-1` PR shard. The unit suite is owned by
`unit-contract-golden`.

## Explicit exclusions

S2 does not implement single-day or seven-day peak metrics, season cumulative
metrics output, persistence or recalculation lineage, a query API, Agent
orchestration, CLI, actual-harvest import, CSV/XLSX parsing, multi-factory
routing, allocation optimization, peak shaving, frontend/dashboard/reporting,
backtesting, actual labels, Q2A-I3+, or any Task 8/9 numerical algorithm.

The following remain separately unauthorized:

```text
V0_1_S3_NOT_AUTHORIZED
V0_1_S4_NOT_AUTHORIZED
V0_1_S5_NOT_AUTHORIZED
READY_NOT_AUTHORIZED
MERGE_NOT_AUTHORIZED
```
