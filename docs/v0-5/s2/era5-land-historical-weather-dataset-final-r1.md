# S2 ERA5-Land historical weather facts — final R1

This document records the accepted normalization of the already characterized
ERA5-Land point time-series artifact set. It is a source-data build, not a
weather feature or yield-model experiment.

## Frozen acceptance boundary

The accepted source is the official `reanalysis-era5-land-timeseries` product
with role `REANALYSIS_REFERENCE`. The final policy is:

`ERA5_LAND_TIMESERIES_CHARACTERIZED_SET_NEGATIVE_TO_ZERO_V1`

The policy is valid only when all of the following exact identities match:

| identity | value |
| --- | --- |
| source manifest | `2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1` |
| raw artifact set | `6df5a8e909447384a3b33414facf6e768d1fb31c52b89ebec59bec37e3f358d8` |
| characterization | `9994f4290bc5c2de144ae792813715aac84acd7b42f634ee69f866fa0bb568a2` |
| source product | `reanalysis-era5-land-timeseries` |

For this exact, complete artifact set only, a provider value below zero is
normalized to zero for `total_precipitation` (`tp`) and
`surface_solar_radiation_downwards` (`ssrd`). No numeric envelope is used as
the final rule. Positive values are not thresholded, and `t2m`, `d2m`, `u10`,
and `v10` are never corrected. The raw value and its exact binary
representation remain in the hourly projection; every correction has a
separate provenance record.

The prior R3 numeric-envelope path and its two raw artifacts remain historical
diagnostic evidence only. They are not inputs to the accepted dataset and
were not modified.

## Scope and processing

- 38 registered bases and 35 unique provider grid cells are retained as
  separate base projections.
- All 105 already completed raw requests are used. No request was downloaded,
  resubmitted, replaced, or expanded for this build.
- The provider time-series values for `tp` and `ssrd` are already hourly
  de-accumulated. No adjacent cumulative difference is performed.
- Spatial extraction remains
  `CDS_0P1_NEAREST_GRID_CELL_V1`, with no interpolation or DEM downscaling.
- UTC timestamps are retained and local-day aggregation uses
  `Asia/Shanghai`. A complete local day requires 24 hourly samples per
  variable; gaps, duplicates, non-finite values, and coordinate mismatches
  fail closed.
- The output layers are `ERA5_LAND_HOURLY_NORMALIZED_V1` and
  `BASE_WEATHER_DAILY_V1`.
- `PIT_NOT_ESTABLISHED` remains unchanged. ERA5-Land is not historical
  as-issued forecast data.

## Reproducible command

Run from the repository root with the controlled private raw and
characterization paths supplied explicitly:

```sh
.venv/bin/python -m scripts.normalize_era5_land_historical_weather_final_r1 \
  replay \
  --root "$ERA5_R3_EXPLICIT_GRID_ROOT" \
  --output "$FINAL_ARTIFACT_ROOT/replay-1" \
  --characterization "$CHARACTERIZATION_ROOT/replay-1/characterization.json"

.venv/bin/python -m scripts.normalize_era5_land_historical_weather_final_r1 \
  replay \
  --root "$ERA5_R3_EXPLICIT_GRID_ROOT" \
  --output "$FINAL_ARTIFACT_ROOT/replay-2" \
  --characterization "$CHARACTERIZATION_ROOT/replay-1/characterization.json"

.venv/bin/python -m scripts.normalize_era5_land_historical_weather_final_r1 \
  compare \
  --output "$FINAL_ARTIFACT_ROOT/replay-1" \
  --second "$FINAL_ARTIFACT_ROOT/replay-2" \
  --comparison-output "$FINAL_ARTIFACT_ROOT/replay-comparison.json"
```

The runner disables network connections for both replay invocations. The
controlled output used for this evidence is
`blueberry-area-yield-artifacts/era5-land-historical-weather-final-r1/` with
`replay-1`, `replay-2`, and `replay-comparison.json`.

## Results

The exact results, including the accepted hourly/daily hashes, correction
provenance hash, and replay comparison, are in
`era5-land-historical-weather-dataset-final-r1-evidence.json`.

The raw negative counts (`9822` `tp`, `9981` `ssrd`) count provider
observations across the 105 raw requests. The accepted correction file has
`21455` records because the same raw grid observation is projected separately
for each base sharing that grid cell (`10619` `tp` and `10836` `ssrd`). This is
intentional and does not change the raw observation counts.

No GDD, VPD, ET0, RH authority, weather feature selection, weather model
training, or incremental-value scoring was performed. Weather authority and
live forecast authority remain unfrozen.
