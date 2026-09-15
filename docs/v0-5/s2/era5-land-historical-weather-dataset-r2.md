# S2 ERA5-Land official point time-series R2

Task: `V0_5_S2_ERA5_LAND_HISTORICAL_WEATHER_DATASET_R2`. Continues Draft #628
from `224d801d483358bb3bf8af766fe8610413b556ae`; no new PR, Ready or Merge.

## Result: source quality gate BLOCKED

The official point time-series route was actually requested and downloaded.
CDS authentication succeeded. The first ZIP contains four readable NetCDF files,
six variables, 6,984 hours per variable (41,904 native values), correct point
selection and no missing/duplicate hours. **The provider's hourly values contain
173 negatives: 84 precipitation and 89 downward solar radiation values.** All
173 fall inside the business-day window, not merely UTC padding.

`DATASET_BUILD_STATUS=BLOCKED`;
`BLOCKER=PROVIDER_DEACCUMULATED_NEGATIVE_VALUE`.

These values were read directly, **without adjacent accumulation subtraction**.
Precipitation negatives range from -2.9249690669530537e-08 to
-4.4019543565809727e-10 m; radiation negatives range from -4 to -1 J/m².
For example, provider `ssrd` at 2023-07-01T14:00:00Z is exactly -2 J/m².
This report does not infer a physical or encoding cause or authorize clipping.
Small magnitude does not waive the user's zero-tolerance quality gate.

Only one of 105 planned requests was submitted/downloaded. The other 104 were
not started after the defect was established. There is no accepted hourly or
daily dataset: 0 complete / 38 incomplete bases. Zero observed gaps applies only
to the downloaded request, not to the 104 unrequested point-season slices.

## Source separation and preservation

| Path | Disposition | Processing |
| --- | --- | --- |
| R1 `reanalysis-era5-land` | REJECTED_DIAGNOSTIC_SOURCE_PATH | Old accumulated-product parser retained only as diagnostic history |
| R2 `reanalysis-era5-land-timeseries` | ACCEPTED_CANDIDATE, currently quality-blocked | CDS official provider-deaccumulated hourly values, direct unit conversion |

Both belong to ERA5_LAND / REANALYSIS_REFERENCE. Neither is an as-issued forecast.
Official references: [CDS point-series catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries)
and [ECMWF point-series documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=699689224).
The live CDS form was checked for `location`, inclusive UTC `date` range and
`data_format=netcdf`. Actual delivery uses `valid_time` and scalar coordinates;
the parser also supports the documented `time` spelling but rejects ambiguity.
Stale accumulated-product GRIB metadata does not trigger local deaccumulation.

R1's two raw files, five submitted receipts (three not downloaded), five negative
differences and existing reports remain byte-for-byte untouched. The old 1,155
requests are not resumed. The R2 private preservation overlay inventories all
16 R1 files; its semantic hash is
`1394f8db5389c2a4f1920bdb0ee808f2028eeb893e5574b8055bcb14a06f2d1c`.
No R1 file is an accepted R2 input.

## Frozen query and normalization contracts

- 38 original base IDs project independently from 35 unique 0.1° cells × three
  authorized seasons = 105 point-season requests. Source dates come only from
  frozen business windows: 2023-07-01..2024-04-15,
  2024-07-01..2025-04-15, 2025-07-01..2026-04-15.
- The lexicographically first base ID in a shared cell supplies the original
  request coordinate. Each base retains its own original coordinate and ID.
  Nearest-grid ties follow the existing lower-coordinate rule. Provider returned
  coordinates must match that expected grid. Only coordinate representation is
  compared at six decimal degrees (e.g. 22.400000000000887 → 22.400000);
  this is **not** a weather/accumulation tolerance or coordinate correction.
- WGS84 is an authorized query assumption only; CRS verification remains
  NOT_ESTABLISHED. No registry coordinates, CRS, elevation or climate-zone
  authority are changed. No name geocoding or interpolation.
- Six variables only: t2m/d2m K → °C, tp m → mm, ssrd J/m², u10/v10 m/s.
  Hourly precipitation and radiation are used directly as provider-deaccumulated
  interval-ending values. There is no predecessor lookup or cross-run difference.
- Asia/Shanghai local day: instantaneous samples at 00..23 local; hourly interval
  totals ending at 01..next 00 local. Requests pad UTC dates accordingly.
  Each daily projection requires 24 samples of every variable; missing, duplicate,
  nonfinite, wrong-unit or negative provider interval values fail closed.
- Stable base/date/hour/variable order; canonical sorted JSONL, row SHA256 and
  whole-file SHA256. Normalized values use fixed 12-decimal HALF_EVEN strings;
  exact binary native values are also retained as hex. No missing-value filling.
  Sampled Tmin/Tmax are hourly-sample extrema, not continuous physical extrema.
- No GDD, VPD, ET0, RH authority, agricultural thresholds, feature selection,
  weather gain scoring or model training. Operational PIT remains unestablished;
  existing strict PIT verifiers are unchanged.

## Actual artifacts and offline replay

Private root:
`/Users/charles/Documents/blueberry-area-yield-artifacts/era5-land-historical-weather-r2`.
No raw/private business dataset is committed to Git.

The downloaded ZIP SHA256 is
`0cfb6017df0b8374fc826f0e9de9d93498ce0ace181309f62dc4a1174e7164ad`.
Its immutable completion receipt and per-member hashes are retained beside it.
Raw artifact-set hash:
`d0fe9ff694ef89e268813eb2dc288885b61c712b942df3270ef7117f1d19199d`.

Two fresh-process source audits with network socket connections disabled produced
identical files, SHA256
`380919532170ecce5a3c54037e1ffc763fb15c1ae22bbaf4794bc715711e2ee7`.
Both raw hashes and the same 173 defects replayed. Two normalization attempts
blocked before creating an output directory; identical failure receipt SHA256
`3da8fa491cc7cea11ab504adbfa7aee2cb7451c3a9e179ca17871536da65f6f6`.
**Raw diagnostic replay PASS is not accepted hourly/daily replay PASS.** Real
hourly/daily hashes are null; deterministic accepted-dataset replay is BLOCKED.

Commands (from repository root, independent output paths):

```sh
.venv/bin/python -m scripts.build_era5_land_historical_weather_r2 --r1-root "$R1_ROOT" --output "$R2_ROOT"
.venv/bin/python -m scripts.retrieve_era5_land_historical_weather_r2 --root "$R2_ROOT" --max-active 2
.venv/bin/python -m scripts.report_era5_land_historical_weather_r2 --root "$R2_ROOT" --output "$R2_ROOT/offline-source-replay-1.json"
.venv/bin/python -m scripts.report_era5_land_historical_weather_r2 --root "$R2_ROOT" --output "$R2_ROOT/offline-source-replay-2.json"
.venv/bin/python -m scripts.normalize_era5_land_historical_weather_r2 --root "$R2_ROOT" --output "$R2_ROOT/normalized-replay-1"
.venv/bin/python -m scripts.normalize_era5_land_historical_weather_r2 --root "$R2_ROOT" --output "$R2_ROOT/normalized-replay-2"
```

`R1_ROOT` and `R2_ROOT` refer to the two explicit private sibling directories
documented here and in R1. The planner creates a new immutable manifest; do not
overwrite the existing one. Retrieval rechecks existing raw files and blocks
before submitting more work when this defect is present. It must not be resumed
to evade the source gate. The normalizer currently raises the stated blocker.

## Verification and stop gate

Focused R1/R2 tests and relevant S1/S2 tests cover direct hourly use, both negative
variables without tolerance, grid parity, UTC/local edges, gaps, duplicates,
hash tampering, immutable raw replay, 38 projections, research restrictions and
the unchanged R1 diagnostic path. Synthetic positive datasets verify successful
two-replay code behavior; they are never represented as real weather acceptance.

Exact-head CI and full-suite-canary must finish after pushing the revision; the
prior R1 CI is not R2 acceptance. CI verifies software, not provider data quality.
No Ready, Merge, source-authority freeze or model research is authorized.

Final stop: `COORDINATOR_S2_ERA5_HISTORICAL_DATASET_R2_REVIEW`.
