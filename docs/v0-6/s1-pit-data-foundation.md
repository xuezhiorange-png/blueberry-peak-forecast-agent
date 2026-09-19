# V0.6-S1 Point-in-Time Data Foundation

`V0_6_S1_POINT_IN_TIME_DATA_FOUNDATION_R1` adds the append-only data
foundation for future point-in-time forecast replay. This slice is a data
contract and persistence boundary only. It does not run a model, call a
weather provider, score a forecast, or start the S2 shadow-forecast process.

## Reused repository capabilities

- Existing `actual_harvest_import` staging, validation, revision, and commit
  manifest chain remains the actual-harvest source of record. The S1 adapter
  maps its persisted import receipt time to the common `known_at` vocabulary;
  no second actual-harvest framework is introduced.
- Existing `UTCDateTime` is used for all PIT instants.
- Existing canonical JSON and SHA-256 helpers in
  `backend.app.rolling_backtest.canonical` are used for payload and input
  snapshot identity.
- Existing caller-owned transaction conventions are retained. The new
  repository flushes but never commits or rolls back.
- Existing immutable migration trigger patterns used by forecast and harvest
  evidence tables are reused.

## Persistence contract

The Alembic revision `0036_v06_pit_data_foundation` creates the tables below;
the follow-up `0037_v06_pit_scope_time_integrity` revision adds the scope and
timestamp-ordering constraints described after the table list:

- `area_revision`: append-only area versions. The current Base Registry is
  represented only as `REFERENCE_AREA`; it is never promoted automatically to
  `ACTUAL_PRODUCTIVE_AREA`.
- `weather_forecast_snapshot`: forecast-time provider snapshots only. No ERA5
  realized/reanalysis value may be inserted as an as-issued forecast record.
- `realized_weather_observation`: separate realized-weather facts.
- `phenology_observation`: append-only, repeatable observations by base/season.
- `forecast_run_snapshot` and `forecast_run_snapshot_daily`: immutable forecast
  input/result envelopes and normalized daily child rows.

All six tables reject `UPDATE` and `DELETE` at the database layer on both
SQLite and PostgreSQL. New area revisions supersede old rows by reference;
they do not overwrite them.

## Visibility rule

The single shared rule is:

```text
record.known_at <= forecast_created_at
```

Weather additionally requires:

```text
weather.issued_at <= forecast_created_at
```

The repository rejects a forecast snapshot that references a hindsight area
revision, weather snapshot, or phenology observation. Input snapshot hashes
bind the request, base identity, target area/revision, prior-history coverage
and source hashes, weather/phenology IDs, model artifact hashes, mode, and
warnings. Changing any of those identities changes `input_snapshot_hash`.

Forecast phenology references must match both the forecast Base and its target
season. A weather snapshot with a Base scope must match the forecast Base;
location-only weather may be stored as an unbound snapshot, but cannot be
attached to a forecast without a later, explicit Base-to-location authority.
The persistence boundary also enforces `recorded_at <= known_at` for area
revisions, `observed_at <= known_at` and `recorded_at <= known_at` for
phenology, `observation_time <= known_at` and `recorded_at <= known_at` for
realized weather, and `issued_at <= fetched_at <= known_at` for forecast
weather. A forecast's `forecast_created_at` cannot be later than its
persistence time.

## Explicit non-scope

`V0_6_S2_IMPLEMENTATION_AUTHORIZED=false`, so this PR does not add a weather
provider, create forecast snapshots in batch, schedule 39 bases, import ERA5
as forecast weather, or expose a new API/MCP surface. S3/S4 remain
unauthorized.
