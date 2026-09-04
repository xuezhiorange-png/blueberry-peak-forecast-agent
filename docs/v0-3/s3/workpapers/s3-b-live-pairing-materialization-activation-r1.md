# S3-B Live Pairing Materialization Activation R1

## Task

`V0_3_S3_B_LIVE_PAIRING_MATERIALIZATION_ACTIVATION_R1`

Parent: PR #548 (`458f3e92a8f773f459ddcba0e8af17175dfafbee`)

## Scope delivered

1. **PIT-visible Task 8 daily curve provider**
   - `PitVisibleIncumbentDailyCurveProvider` reads `MaturityDailyPredictionModel` fields `p50_kg` / `p80_kg` / `p90_kg`
   - Daily row identity uses public `task8_daily_prediction_payload_hash` (shared with rolling-backtest resolution)
   - Forecast run selection: unique visible `MaturityForecastRun` per business grain at `forecast_cutoff_at` (fail-closed on ambiguity)

2. **Persisted forecast binding authority loader**
   - `load_persisted_forecast_binding_authority` builds `S2ForecastAuthorityBundle` from persisted `core_forecast_run`, Task 9, Task 10, and code authority rows
   - Rejects synthetic single-character placeholder hashes on live paths

3. **Live obtain wiring**
   - `obtain_live_incumbent_forecast_daily_curve_provider()` uses `AsyncSessionMaker.run_sync` to preload PIT-visible Task 8 cells and return a lawful provider + authority bundle
   - `LAWFUL_PIT_VISIBLE_INCUMBENT_DAILY_FORECAST_VALUE_SOURCE` no longer `NONE`

4. **Materialization execution path**
   - `materialize_train_validation_pairing_inputs_live()` unchanged in semantics; now reaches real provider when DB is bound

## Out of scope (unchanged)

- Pairing package publication
- Partition authority issuance
- Schema registration
- Coverage execution

## Agent runtime result

| Field | Value |
|-------|-------|
| SOURCE_002_ROW_LEVEL_READ_ATTESTED | false |
| LIVE_EXECUTION_BLOCKER | NO_BOUND_PRODUCTION_DB_SESSION |
| REAL_MATERIALIZATION_COMPLETED | false |
| TEST_REMAINS_SEALED | true |

Production DB session on the agent VM returned `FAIL_CLOSED_SESSION_UNREADABLE` (asyncpg sync bridge). Adapter/wiring is complete with unit tests; coordinator must bind production DB for full live package materialization.

## Evidence

See `docs/v0-3/s3/evidence/s3-b-live-pairing-materialization-activation-r1.json`.
