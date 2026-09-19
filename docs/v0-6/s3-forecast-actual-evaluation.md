# V0.6-S3 Forecast vs Actual Evaluation

## Scope

S3 adds a read-only evaluation path from the immutable V0.6-S1/S2 forecast
snapshot to committed actual-harvest records and separately persisted realized
weather observations.  It creates a new immutable evaluation authority; it
never updates a forecast snapshot and it does not train, tune, promote, or
ablate a model.

The implementation is owned by:

- `backend/app/pit/evaluation.py` — deterministic alignment, revision winner,
  metric, peak, rolling-window, and weather-evaluation rules;
- `backend/app/pit/evaluation_application.py` — reloads the S1/S2 snapshot and
  delegates to the evaluator;
- `backend/app/pit/evaluation_persistence.py` — flush-only append-only save and
  canonical reload validation;
- `backend/app/pit/evaluation_models.py` — `forecast_evaluation` and
  `forecast_evaluation_daily` ORM models;
- `0038_v06_s3_forecast_actual_evaluation` — schema and database immutability
  guards.

The existing actual-harvest import, validation, revision, and commit-manifest
chain remains the source of record.  `load_committed_actual_harvest_records`
only adapts committed rows into the shared PIT vocabulary and requires an
exact farm-to-base mapping.

## Frozen evaluation contract

`EVALUATION_POLICY_VERSION=V0_6_S3_FORECAST_ACTUAL_EVALUATION_V1`.

- Alignment grain: `base_id + target_season + date`.
- Modes: `FULL_AVAILABLE_RANGE` and `AS_OF_DATE`.
- `known_at <= evaluation_created_at` is required for actual and realized
  weather inputs.
- `AS_OF_DATE` clips the evaluated date range; future actual rows are excluded.
- Missing actual dates remain `MISSING` with a null quantity.  They are never
  filled with zero.  A zero quantity is `CONFIRMED_ZERO`.
- Same logical actual record uses the highest visible revision number; equal
  competing revision winners fail closed.
- Error sign is `forecast - actual`.
- WAPE denominator is `sum(abs(actual))`; a zero denominator is explicit
  `UNDEFINED_ZERO_DENOMINATOR`.
- MAPE excludes zero-actual rows and reports the excluded count; if no nonzero
  actual remains it is explicit `UNDEFINED_ZERO_DENOMINATOR`.
- Date errors are signed calendar days (`forecast - actual`); absolute values
  are emitted alongside them.
- Single-day and rolling 7-day ties use earliest date/start date.
- Rolling windows require seven consecutive natural dates and seven actual
  values.  Missing dates never get concatenated into a window.
- GDD is not evaluated because no formal S3-frozen GDD definition exists:
  `GDD_EVALUATION_STATUS=NOT_EVALUATED_DEFINITION_NOT_FROZEN`.

## Weather evaluation boundary

Only persisted S2 as-issued ECMWF forecast snapshots are eligible.  They are
matched to realized observations at the same UTC valid/observation instant;
ERA5-Land, reanalysis, hindsight forecast reconstruction, and provider
substitution are not used.  The persisted weather evaluation reports the
provider-supported horizons D1 (24h), D3 (72h), D7 (168h), and D15 (360h),
with temperature MAE/bias and precipitation error/MAE where both fields are
present.

## Immutability and determinism

The evaluation parent and daily rows are append-only and guarded by database
triggers.  The canonical identity binds the forecast input/result hashes,
actual and realized-weather authority identities/hashes, policy definitions,
mode, cutoff, and evaluated range.  The result hash binds aligned rows and all
metric payloads.  A changed actual revision or cutoff produces a new
evaluation identity; an identity conflict or corrupted reload fails closed.

Repositories are flush-only.  The caller owns commit/rollback.  Reload checks
parent payload/result/identity hashes, daily row order/count, and each daily
row hash.

## Evidence boundary

The fixture and SQLite contract tests prove deterministic S3 behavior.  A
production-shaped evaluation is only reported when a matured committed actual
authority exists for an S2 forecast.  If the prospective S2 forecast has not
yet matured, the correct state is
`INSUFFICIENT_MATURED_ACTUAL_EVIDENCE`; this does not become a claim that
prospective validation is complete.

S4 prospective validation and weather incremental-value/ablation work are out
of scope and remain unauthorized.
