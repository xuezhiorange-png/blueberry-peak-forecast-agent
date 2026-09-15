# S2 historical ERA5-Land dataset R3

Task: `V0_5_S2_ERA5_LAND_HISTORICAL_WEATHER_DATASET_R3`, existing Draft PR #628.
R2 baseline: `978e2e70e6d1ff971b9df8bf51491c2889b11aad`.

## Explicit user authorization overlay

R1/R2 evidence and raw files remain unchanged. R3 adds a separate policy and
artifact directory. The standard ERA5-Land accumulation route remains rejected;
the only source candidate is official `reanalysis-era5-land-timeseries`.
This remains ERA5_LAND / REANALYSIS_REFERENCE, not historical as-issued weather.
No operational PIT gate is relaxed and no weather authority is frozen.

`SOURCE_ARTIFACT_CORRECTION_VERSION=ERA5_LAND_TP_SSRD_SOURCE_ARTIFACT_R3_V1`.
Certification here means the **user's scoped authorization**, not a new claim of
provider certification or independent verification of the artifact cause.

| Variable | Authorized native-value interval | Derived value |
| --- | --- | --- |
| total_precipitation (tp) | -3.0e-8 m ≤ value < 0 | 0 m |
| surface_solar_radiation_downwards (ssrd) | -4 J/m² ≤ value < 0 | 0 J/m² |

Every positive value is unchanged by this correction, including tiny positives.
No drizzle/radiation threshold, widened tolerance, neighboring-value substitution,
interpolation, additional deaccumulation or agronomic feature is permitted.
Negative u10/v10 are not changed. Nonfinite values fail before correction.
Native binary values are compared to exact Decimal envelope limits, with tests
on the boundary and the immediately adjacent float outside it.

Any value outside the table stops retrieval and prevents accepted dataset output:
`NEGATIVE_VALUE_OUTSIDE_CERTIFIED_ARTIFACT_ENVELOPE`.
R2's one completed raw ZIP is reused byte-for-byte, not downloaded again. Its
173 negatives pass the R3 envelope preflight; this does not certify later files.

## Check before downloading; request failure rules

Before any CDS connection, revalidate the frozen 38-base/35-cell/three-season
request plan, policy, every existing raw hash, archive readability, units, finite
values, point parity, timestamps and envelope. Only then resume outstanding
requests. Requests remain bounded with at most three active remote requests.

Authentication, submission, polling, terminal failed/dismissed/cancelled status,
download or quality-gate failure stops further submissions and downloads.
Failure receipts record phase, request hash, exception class, pending/active
request hashes and safe machine-readable blocker—not tokens, signed URLs or raw
exception strings. Existing completed receipts and partial files are preserved.
Uncertain submissions are not automatically resubmitted. Pending remote requests
are retained for audit; their mere existence is not accepted input.

CDS API maximum tries is one (zero automatic retries); successful-job polling is
not a new submission. A durable `stop-*.json` causes subsequent invocations to
fail closed with `PRIOR_RETRIEVAL_STOP_REQUIRES_REVIEW`. No automatic retry of a
failed request, automatic tolerance adjustment or quiet overwrite is available.

## Units, coordinates and time

Machine-readable temperature units are consistently `K` for raw t2m/d2m and
`degC` for standardized temperature/dewpoint and daily temperature statistics.
Human-readable `°C` denotes the same Celsius unit, not another conversion.
Conversion is the existing K − 273.15 rule. Daily rows explicitly carry
`temperature_unit=degC`; sample extrema remain hourly-sampled Tmin/Tmax.

Precipitation is raw m / normalized mm; radiation is native J/m². Wind components
remain m/s. Provider-deaccumulated hourly interval values are never differenced
again. Asia/Shanghai local-day support remains 24 samples per variable, with the
existing UTC padding and interval-ending convention. No missing hours are filled.

Original representative coordinates, lower-coordinate grid tie-break and provider
grid parity are unchanged. WGS84 is only a query assumption; source CRS remains
unverified. Base IDs remain separate when raw weather cells are shared. No
geocoding, climate centroid, elevation update or base-membership change occurs.

### Explicit grid query authorization (review 5204323324)

The original 101.95 query returned 102.0 while the project tie-break selected
101.9. This is not evidence of a CDS error: nearest-point selection alone does
not prescribe an equidistant tie-break. User review 5204323324 authorizes sending
the frozen expected grid coordinate instead of the original representative point.
The Registry coordinates and CRS authority remain unchanged.

The immutable `explicit-grid-review-5204323324` child directory contains a revised
request manifest and a pinned copy of the original manifest. Twelve already
qualified requests retain their raw files and requests byte-for-byte. Remaining
requests use explicit frozen grid coordinates; previously submitted superseded
requests are retained in the parent directory as diagnostics, not accepted input.
No already-qualified point is downloaded again. Every accepted returned point
must still equal the expected point. An explicit-query mismatch stops retrieval.
Hourly provenance distinguishes original requested coordinates from actual query
coordinates. `prior-preservation.json` records the original raw/receipt hashes,
including the rejected tie request. No diagnostic file is deleted or rewritten.

```sh
.venv/bin/python -m scripts.era5_historical_dataset_r3 prepare-grid-review --prior-root "$R3_ROOT" --root "$R3_ROOT/explicit-grid-review-5204323324"
```

For subsequent retrieve/report/replay commands, use that child directory as root.

## Raw retention, correction trace and deterministic replay

Private root: `blueberry-area-yield-artifacts/era5-land-historical-weather-r3/`.
The original R2 source manifest remains a raw request-plan record; the separate
`correction-policy.json` is R3's explicit derived-value authorization overlay.
Both hashes are checked. Historical R2 "no correction" decisions are not rewritten.

Hourly rows preserve original `native_value_exact_hex` alongside the corrected
native value and its exact hex. Positive corrected-native text is the exact
Decimal representation of the unchanged float, never a thresholded value.
Existing normalized numeric serialization remains fixed 12-decimal HALF_EVEN;
this is serialization precision, not a positive-value threshold.

Every corrected business-hour projection also has a correction row recording
base ID, selected grid, UTC timestamp, variable, negative raw value/exact hex,
native unit, corrected zero, reason, version and raw SHA256. Provider-negative
counts are unique-grid raw observations; applied correction counts are base-level
business-hour projections. Shared-grid bases can therefore yield different count
denominators. Eligible preflight corrections are not claimed as published rows.

Normalized hourly rows use deterministic gzip JSONL (`mtime=0`, no filename
header). Dataset hashes cover the canonical **uncompressed** line stream; a
separate SHA256 covers each compressed artifact. Daily/correction JSONL have row
and file hashes. Row ordering and base identity are deterministic. R1/R2 artifacts
are never overwritten. No private raw weather is committed to Git.

Replay runs in two fresh processes, against the same pinned raw files. The CLI
rejects socket connections; macOS acceptance additionally uses process-level
`sandbox-exec` network denial, verified by an EPERM connection probe. Dataset
counts/hashes and compressed hashes must agree. Positive synthetic replay tests
are software evidence, never substituted for real weather replay.

```sh
.venv/bin/python -m scripts.era5_historical_dataset_r3 prepare --prior-root "$R2_ROOT" --root "$R3_ROOT"
.venv/bin/python -m scripts.era5_historical_dataset_r3 preflight --root "$R3_ROOT"
.venv/bin/python -m scripts.era5_historical_dataset_r3 retrieve --root "$R3_ROOT"
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' .venv/bin/python -m scripts.report_era5_land_historical_weather_r3 --root "$R3_ROOT" --output "$R3_ROOT/source-replay-1.json"
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' .venv/bin/python -m scripts.normalize_era5_land_historical_weather_r3 --root "$R3_ROOT" --output "$R3_ROOT/replay-1"
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network*)' .venv/bin/python -m scripts.normalize_era5_land_historical_weather_r3 --root "$R3_ROOT" --output "$R3_ROOT/replay-2"
```

Roots are private sibling directories under
`/Users/charles/Documents/blueberry-area-yield-artifacts/`; output paths must be new.

No GDD, VPD, ET0, weather feature selection, model training, incremental-value
scoring, as-issued/live forecast, database/API/MCP or deployment work is included.
Final result and exact-head CI are recorded separately after source qualification.
PR remains Draft. Final gate: `COORDINATOR_S2_ERA5_HISTORICAL_DATASET_R3_REVIEW`.

## Current bounded retrieval checkpoint

Review 5204323324's explicit 23.7/101.9 query passed returned-point verification.
15 of 105 planned raw requests are now qualified (five bases have all three
season sources); 57 files in the prior directory retain their original hashes.
The next batch stopped during download with `ProxyError`, recorded as
`CDS_REQUEST_OR_DOWNLOAD_FAILED`. Three submitted receipts remain preserved.
No automatic download retry or resubmission occurred and no unreceipted raw
remains. Resuming that failed network operation requires a separate decision;
the reviewed grid change itself is working.

The authorized recovery of all 18 existing submitted receipts completed without
resubmission: 15 were already complete and 3 were downloaded after querying the
original jobs. The recovery scope is closed at this point; 87 planned requests
were not submitted. The partial offline source audit now covers 18 raw sources:
1,677 tp and 1,688 ssrd negatives, all within the frozen envelope, with zero
gaps/duplicates. These are not full-dataset acceptance statistics. No real
normalized dataset or full replay result is claimed until the remaining planned
requests receive separate authorization. The earlier ProxyError stop record is
preserved as transport history. Local tests: 50 focused / 215 related passed;
lint, format and mypy passed. Exact-head CI `34915123025` passed on the
recovery implementation head, and final head CI `34917284629` passed on the
evidence update, including full-suite-canary.
