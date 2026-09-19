# V0.6-S2 Shadow Forecast and Weather Capture

`V0_6_S2_SHADOW_FORECAST_AND_WEATHER_CAPTURE_R1` adds the application boundary
for prospective shadow runs. It reuses the V0.6-S1 PIT tables and the frozen
V0.5 area forecast product; it does not change forecast mathematics.

## Frozen contract

- `FORECAST_MODE=SHADOW`
- `MODEL_STATUS=EXPERIMENTAL`
- total model: `BASE_AWARE_BASELINE_R1`
- temporal reference: `AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE`
- `WEATHER_USED_BY_MODEL=false`
- area revisions use `ACTUAL_PRODUCTIVE_AREA`, `PLANTED_AREA`, then
  `REFERENCE_AREA`; `PLANNED_AREA` is not an authorized S2 input
- immediate-prior history is selected by the existing V0.5 selector; no older
  season fallback, fill, interpolation, or model-generated history is allowed
- phenology is optional and only same-base, same-target-season observations
  visible at `forecast_created_at` are bound

The CLI supports one run and a deterministic registry-ordered batch:

```text
python -m backend.app.cli shadow-forecast \
  --base-id <base_id> --season 2026-2027
python -m backend.app.cli shadow-forecast-batch --season 2026-2027
```

## Weather provider boundary

The repository's existing CSV and ERA5 capabilities are realized/historical
weather. They are not forecast-time/as-issued data and are not adapted to the
S2 provider interface. Until an authorized provider with issue/fetch/known
timestamps is configured, the default provider returns:

```text
WEATHER_CAPTURE_STATUS=UNAVAILABLE
WEATHER_FORECAST_NOT_AVAILABLE
```

Therefore this checkout's weather-capture gate is explicitly
`BLOCKED_WEATHER_FORECAST_PROVIDER_NOT_CONFIGURED`; it is not an accepted
forecast-weather dataset. The history-only shadow execution remains useful
for exercising the PIT snapshot and frozen V0.5 product path, but it does not
make S2 complete and it never claims that weather was captured.

The historical-only frozen model may still execute in Shadow mode, but the
snapshot records the warning and binds no weather IDs. A supplied provider
must return Base-bound snapshots satisfying:

```text
issued_at <= fetched_at <= known_at <= forecast_created_at
```

Location-only snapshots can be persisted by S1 but fail closed when a shadow
run attempts to bind them without a Base-location authority.

## Non-goals

S2 does not score forecasts, compare against actual harvest, train weather or
phenology models, modify V0.5 artifacts, add MCP/UI, or deploy a provider.
