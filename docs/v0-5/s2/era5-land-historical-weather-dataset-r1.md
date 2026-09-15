# S2 ERA5-Land historical weather facts — R1

Status: **BLOCKED — NATIVE_ACCUMULATION_NEGATIVE_DIFFERENCE**.
This Draft delivers the request planner, retrieval/normalization gates and tests;
it does **not** claim delivery of a complete 38-base dataset.

User authorization `ACTION=RESUME_FROM_CRS_BLOCKER` permits **WGS84 query
assumption only** for the existing 38 Yunnan representative coordinates.
`CRS_VERIFICATION_STATUS=NOT_ESTABLISHED` and
`SOURCE_COORDINATE_STATUS=RANGE_VALID_CRS_UNCONFIRMED` remain unchanged.
No registry coordinate, CRS or elevation authority is upgraded. Spatial anomalies
fail closed as `BLOCKED_CRS_OR_COORDINATE_REVIEW_REQUIRED`.

The source is `reanalysis-era5-land`, historical `REANALYSIS_REFERENCE`, never
historical as-issued weather. Strict operational replay remains blocked and the
existing PIT verifier is unchanged. No agronomic features or model execution.

The three July 1–April 15 business calendars derive from
`configs/base_registry_s1.json`, not yield amounts, peaks or validation scores.
UTC padding is only for complete Asia/Shanghai days and accumulation differences.
Native hourly accumulation semantics follow
[ECMWF ERA5-Land documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=185075237):
00 UTC initialization, steps 1–24; midnight valid time belongs to the previous
initialization. No cross-run subtraction, interpolation, clipping or gap filling.

Private raw files and normalized rows must not be committed. Download completion,
hash verification and two network-disabled replays remain required before a
dataset can be described as complete. CDS authentication and a real retrieval
have succeeded; this is not a credential blocker.

## Frozen scope and reproducible execution

Registry file SHA256:
`502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904`.
38-base ID-set hash:
`79c210ffc5a837b93ae12dce6bc853b8f4f92d8ad91ce7e6a5cbff3bdb12149f`.
38 coordinates qualify for the explicitly authorized **query assumption**, not
for a new CRS authority. A coarse Yunnan range screen rejects clear spatial
anomalies without correcting them. Raw grid coordinates must match the selected
cell; otherwise normalization blocks.

Windows: 2023-07-01..2024-04-15, 2024-07-01..2025-04-15,
2025-07-01..2026-04-15. Thirty-five unique grid cells are shared by 38 bases.
There are 1,155 point/month requests, six variables, all 24 hours on the minimum
enclosing UTC dates. No regional/global raster or off-season research request.
Equidistant positive coordinates select the smaller latitude/longitude.

The private directory is
`/Users/charles/Documents/blueberry-area-yield-artifacts/era5-land-historical-weather-r1`.
It contains the immutable request manifest, submitted-request receipts, downloaded
raw files, source-quality report and both offline rejection/replay records.
No raw data or coordinates are included in this PR.

```bash
python -m scripts.build_era5_land_historical_weather_r1 \
  --registry /path/to/pinned/base-registry-v1.json --output /new/private/directory
python -m scripts.retrieve_era5_land_historical_weather_r1 --root /private/directory
python -m scripts.report_era5_land_historical_weather_r1 \
  --root /private/directory --output /new/private/source-report.json
python -m scripts.normalize_era5_land_historical_weather_r1 \
  --root /private/directory --output /new/private/replay-1
python -m scripts.normalize_era5_land_historical_weather_r1 \
  --root /private/directory --output /new/private/replay-2
```

`report` and `normalize` deny socket connections before reading raw files. Existing
paths are not overwritten. Retrieval resumes from pinned receipts, uses at most
three outstanding requests by default and now stops on negative accumulation.
Five requests had been submitted when source defects were confirmed; two raw
files were downloaded. The submitting worker was stopped; remaining remote
requests retain their receipts and are not represented as downloaded data.

## Actual source gate failure

For `base_05c82656e3dcb06cac487039`, five within-run decreases were found in the
two downloaded files. All fall within required local business dates:

| UTC endpoint | Variable | Native hourly difference |
| --- | --- | --- |
| 2023-06-30 18:00 | tp | -2.0954757928848267e-09 m |
| 2023-06-30 23:00 | tp | -1.6298145055770874e-09 m |
| 2023-07-01 14:00 | ssrd | -2 J m-2 |
| 2023-07-23 00:00 | tp | -6.0535967350006104e-09 m |
| 2023-07-25 11:00 | tp | -7.9162418842315674e-09 m |

The midnight value is compared to the preceding step23 of the **same** run.
The valid-time 01 UTC reset is not differenced against yesterday's step24.
The source audit retains exact IEEE hexadecimal current/previous values.
Small magnitude could be consistent with encoding precision, but that cause is
**not established here**. No tolerance, clipping, interpolation or repaired
authority is invented. Further treatment requires a separately explicit decision;
credentials, CRS and operational PIT are not the blocking conditions.

Two offline source audits are byte-identical, SHA256
`5a30d7b5106f64fa1edf8f7bdb79b5e1276d5df41e1deaa1576aab9acf0674f2`.
Both normalization attempts fail closed before creating an output directory.
There are **no accepted hourly/daily dataset hashes**. Raw hash replay covers
only the two downloaded files, not the planned full source set.
One base is source-quality-blocked, 37 remain unverified; no base is certified complete.

## Normalized contracts (implemented, real dataset not accepted)

Hourly ordering is base ID, business date, local interval start, native variable
(lexical). UTC source-valid times are preserved. Instantaneous samples use local
hours 00..23; accumulated hourly intervals end at hours 01..next-day 00. The
`local_date` is the business date owning the interval, not necessarily the date
of its endpoint. Source reset/step, predecessor hash, native/normalized units and
requested/selected coordinates are recorded.

Native bytes remain authoritative in raw files. Normalized values are fixed
12-place, half-even Decimal strings; no NaN or null weather values are emitted.
Row hashes use sorted-key compact UTF-8 JSON excluding `row_hash`; row-set hashes
cover the complete canonical JSONL byte stream, including newlines. Daily rows
sum precipitation/solar intervals, average 24 sampled temperatures and wind
magnitudes, and label sampled Tmin/Tmax as hourly sample extrema, not continuous
physical extrema. No RH, GDD, VPD, ET0 or agronomic threshold is generated.

Synthetic tests demonstrate successful deterministic normalization/replay only;
they are not substituted for the blocked real source. S1/R2 authority files and
strict operational PIT tests are unchanged. No database, API, MCP, deployment,
forecast model or source authority activation occurs.
