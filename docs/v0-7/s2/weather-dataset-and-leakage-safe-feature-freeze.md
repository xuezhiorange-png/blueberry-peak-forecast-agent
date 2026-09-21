# V0.7-S2 — Leakage-safe weather dataset and feature freeze

`TASK_ID=V0_7_S2_WEATHER_DATASET_AND_LEAKAGE_SAFE_FEATURE_FREEZE_R1`

## Decision boundary

This Slice freezes weather source semantics, point-in-time visibility, forecast
origin, target horizons, and a small deterministic feature contract for later
S3 work. It does not train Model B, compare Model A with Model B, score weather
incremental value, or introduce a provider integration.

```ini
MODEL_B_CREATED=false
MODEL_B_TRAINED=false
WEATHER_INCREMENTAL_VALUE_SCORED=false
MODEL_A_B_COMPARISON_EXECUTED=false
GDD_GENERATED=false
V0_7_S3_IMPLEMENTATION_AUTHORIZED=false
```

The implementation uses an explicit operator-supplied path for the accepted
private daily artifact. No private path is embedded in the repository and no
raw weather rows are committed.

## Source authority audit

### ERA5-Land historical daily layer

The accepted source remains:

```ini
SOURCE=ERA5_LAND
ROLE=REANALYSIS_REFERENCE
SOURCE_PRODUCT=reanalysis-era5-land-timeseries
DAILY_LAYER=BASE_WEATHER_DAILY_V1
SEASON_COUNT=3
WEATHER_BASE_COUNT=38
DAILY_ROW_COUNT=32984
LOCAL_TIMEZONE=Asia/Shanghai
HISTORICAL_AS_ISSUED_PIT_STATUS=PIT_NOT_ESTABLISHED
```

Frozen identities:

| Artifact | SHA256 |
| --- | --- |
| source manifest | `2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1` |
| accepted daily dataset / private `daily.jsonl` | `5ad49f11895c76e6aadd01d240ada3ba93d599d25138a2609887e527e58dad3b` |
| characterization | `9994f4290bc5c2de144ae792813715aac84acd7b42f634ee69f866fa0bb568a2` |
| raw artifact set | `6df5a8e909447384a3b33414facf6e768d1fb31c52b89ebec59bec37e3f358d8` |

The daily schema used by the builder is the accepted normalized schema:

- `local_day_mean_temperature_c`, `sampled_local_day_tmin_c`,
  `sampled_local_day_tmax_c`;
- `local_day_precipitation_mm`;
- `local_day_solar_energy_j_m2`, converted to MJ/m² by the fixed factor
  `1,000,000`;
- `local_day_mean_wind_speed_10m_m_s`;
- `local_date`, `base_id`, `row_hash`, and `hourly_sample_count=24`.

The source primitive audit is: `t2m` is represented by the temperature fields;
`tp` by precipitation; `ssrd` by solar energy; and `u10`/`v10` by the
accepted normalized wind-speed field. `d2m` exists in the hourly source layer
but no relative-humidity value is derived from it. The S2 feature contract does
not introduce a new vector-wind calculation or a humidity proxy.

No interpolation, DEM downscaling, or coordinate correction is performed.
The accepted spatial policy is `CDS_0P1_NEAREST_GRID_CELL_V1`; query CRS is
WGS84 and CRS verification remains `NOT_ESTABLISHED`.

The 39th registry Base is not filled by interpolation. The weather-comparable
set contains 38 Base IDs; the non-weather Base is:

```ini
base_36bc109841061a7798ed99a3
```

The complete lists and set hashes are in the machine-readable evidence file.

### ECMWF as-issued authority

The existing V0.6 provider qualification remains valid for prospective use:

```ini
PROVIDER=ECMWF_IFS_OPEN_DATA
MODEL=IFS
STREAM=oper
RESOLUTION=0p25
D1_AVAILABLE=true
D3_AVAILABLE=true
D7_AVAILABLE=true
D15_AVAILABLE=true
PROVIDER_MAX_FORECAST_HORIZON=360h
STATUS=QUALIFIED_PROSPECTIVE_ONLY
```

The controlled artifact audit found only the saved prospective run
`20260919000000`, with manifest SHA256
`aad170103e156a11424c2d487fff27c0b7a263223d7552b155f3c275317477f0`.
It is not a 2024–2025 or 2025–2026 historical archive. No retrospective
download or reconstruction was performed.

```ini
RETROSPECTIVE_FORECAST_RECONSTRUCTION_ALLOWED=false
HISTORICAL_AS_ISSUED_WEATHER_ARCHIVE_AUDITED=PASS
HISTORICAL_AS_ISSUED_ARCHIVE_2024_2025=NOT_FOUND_IN_REPOSITORY_OR_CONTROLLED_ARTIFACT_ROOTS
HISTORICAL_AS_ISSUED_ARCHIVE_2025_2026=NOT_FOUND_IN_REPOSITORY_OR_CONTROLLED_ARTIFACT_ROOTS
PRODUCTION_LIKE_HISTORICAL_FORECAST_WEATHER_COMPARISON_STATUS=NOT_COMPUTABLE_NO_AS_ISSUED_ARCHIVE
```

### Three weather lanes

| Lane | Source and role | Allowed use |
| --- | --- | --- |
| `PAST_OBSERVED_WEATHER` | ERA5-Land / `HISTORICAL_REALIZED_OBSERVATION` | Primary historical experiment input, only before the origin |
| `AS_ISSUED_FORECAST_WEATHER` | ECMWF IFS Open Data / as-issued forecast | Only when a saved snapshot has `issued_at <= forecast_origin` and `known_at <= forecast_origin`; historical validation archive is currently unavailable |
| `FUTURE_REALIZED_ORACLE` | ERA5-Land / realized future weather | Research upper bound only; production-like and primary incremental-value results excluded |

ERA5-Land is never renamed or adapted into an as-issued forecast. Missing
historical ECMWF snapshots cannot be replaced by ERA5-Land.

## Frozen time contract

```ini
FORECAST_ORIGIN_POLICY=ROLLING_DAILY_LOCAL_DAY_START
FORECAST_ORIGIN_TIMEZONE=Asia/Shanghai
INFORMATION_CUTOFF_POLICY=MAX_SOURCE_OBSERVATION_LOCAL_DATE=ORIGIN_LOCAL_DATE_MINUS_1;MAX_SOURCE_OBSERVATION_TIME<FORECAST_ORIGIN
TARGET_HORIZON_POLICY=H1=NEXT_1_CALENDAR_DAY;H7=NEXT_7_CALENDAR_DAYS;H15=NEXT_15_CALENDAR_DAYS
```

For a local-day origin `D 00:00:00+08:00`, the latest permitted Lane-A
observation is `D-1`. The target window starts on `D` and is inclusive. The
feature builder rejects a naive origin, a non-midnight local origin, future
realized observations, unsupported target lengths, duplicate daily rows, or
an incomplete feature window.

The horizons are a feature/forecast task contract, not an inference from the
ECMWF archive. They are accepted only when a later A/B comparison uses the
same origin, target dates, and information cutoff for both models. S1's
combined daily WAPE `0.7245703036857014811985535015` remains a reference
baseline; it is not directly compared with a different-origin task.

## Frozen primary feature policy

```ini
FEATURE_POLICY_VERSION=V0_7_S2_LEAKAGE_SAFE_PAST_OBSERVED_V1
PRIMARY_WINDOWS=7,14,30 days before origin
PRIMARY_FEATURE_COUNT=18
RELATIVE_HUMIDITY_FEATURE_STATUS=NOT_AUTHORIZED
GDD_STATUS=NOT_IN_MODEL_UNTIL_DEFINITION_FROZEN
VPD_GENERATED=false
ET0_GENERATED=false
```

For each of the 7-, 14-, and 30-day windows, the fixed features are:

- mean temperature, mean Tmin, and mean Tmax;
- precipitation sum;
- mean solar radiation in MJ/m²;
- mean 10 m wind speed.

Wind is consumed from the already normalized daily wind-speed field. No new
`u10`/`v10` derivation is introduced here. No wet-day threshold, humidity
proxy, GDD base temperature, VPD, ET0, chilling, or frost index is selected.
There is no automatic feature generation or validation-driven feature search.

Every feature row carries:

```text
base_id
forecast_origin
target_start
target_end
feature_window_start
feature_window_end
max_source_observation_time
weather_lane
weather_source
source_dataset_hash
feature_policy_version
feature_hash
```

`max_source_observation_time < forecast_origin` is checked before a row is
accepted. The canonical row hash binds the source dataset, lane, policy,
origin, target window, source window, and normalized feature values.

## S1 model-scope intersection

The S1 Model-A prediction scopes are determined from the frozen immediate-prior
history authority before any validation labels are read. Weather membership is
then intersected without using validation accuracy:

```ini
FOLD_A_MODEL_A_ELIGIBLE_BASE_COUNT=13
FOLD_A_WEATHER_INTERSECTION_BASE_COUNT=13
FOLD_B_MODEL_A_ELIGIBLE_BASE_COUNT=30
FOLD_B_WEATHER_INTERSECTION_BASE_COUNT=29
```

The Fold-B difference is the registry Base without an accepted ERA5-Land daily
projection. It is retained as non-weather, not imputed.

## Deterministic offline artifact

Using the accepted daily artifact, three frozen season-origin examples and the
H1/H7/H15 target windows, the offline builder produced:

```ini
FEATURE_ROW_COUNT=342
FEATURE_BASE_COUNT=38
FEATURE_SEASON_COUNT=3
FEATURE_MANIFEST_HASH=72f70c927bfbfcea36532c81c6832f12c4f4d32cf9fa64d594193271f5788312
OFFLINE_REPLAY_MANIFEST_HASH=72f70c927bfbfcea36532c81c6832f12c4f4d32cf9fa64d594193271f5788312
OFFLINE_REPLAY_PASS=PASS
```

The full rows are caller-selected private output and are not committed. The
repository contains the contract, summary, hashes, and unit tests. A fresh
process can load the module and reproduce the same row and manifest hashes.

## Acceptance boundary

```ini
WEATHER_SOURCE_AUTHORITY_PASS=PASS
WEATHER_TIME_VISIBILITY_PASS=PASS
FEATURE_LEAKAGE_GATE_PASS=PASS
REALIZED_FUTURE_WEATHER_REJECTED_AS_PRODUCTION_INPUT=PASS
FORECAST_ORIGIN_POLICY_FROZEN=true
TARGET_HORIZON_POLICY_FROZEN=true
INFORMATION_CUTOFF_POLICY_FROZEN=true
NO_AS_ISSUED_ARCHIVE_FAIL_CLOSED_POLICY_FROZEN=true
WEATHER_FEATURE_POLICY_FROZEN=true
WEATHER_FEATURE_DATASET_DETERMINISM_PASS=PASS
OFFLINE_REPLAY_PASS=PASS
```

These are S2 dataset and contract results. They do not establish weather
incremental value, create Model B, or authorize S3. Current PR acceptance also
requires the exact current-head CI to pass while the PR remains Draft.
