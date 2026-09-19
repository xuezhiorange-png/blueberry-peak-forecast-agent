# V0.6-S2 weather provider qualification R2

`TASK_ID=V0_6_S2_WEATHER_PROVIDER_QUALIFICATION_AND_INTEGRATION_R2`

## Decision

The weather-capture gate is qualified for the prospective run recorded below.
ECMWF IFS Open Data is used as the single provider identity for this capture;
ERA5-Land remains rejected for forecast capture because it is realized/
reanalysis data.

`WEATHER_PROVIDER_SELECTED=ECMWF_IFS_OPEN_DATA`
`WEATHER_PROVIDER_USE_ELIGIBLE=true`

The existing private S1 Base Registry authority contains 39 representative
coordinates and binds them to the frozen registry source:

```ini
BASE_LOCATION_AUTHORITY_FILE_SHA256=502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904
BASE_LOCATION_AUTHORITY_STATUS=RANGE_VALID_CRS_UNCONFIRMED
QUERY_CRS_ASSUMPTION=WGS84
CRS_VERIFICATION_STATUS=NOT_ESTABLISHED
```

Those coordinates are used only as the already-authorized Base location
authority; no geocoding, centroid fallback, coordinate correction, or elevation
upgrade is performed. The provider query assumes WGS84 while the registry CRS
remains unestablished. Provider grid parity is checked against the explicit
ECMWF 0.25-degree nearest-grid policy before any snapshot is accepted.

## Candidate disposition

| Candidate | Role | Disposition | Reason |
| --- | --- | --- | --- |
| ERA5-Land | realized/reanalysis | rejected for this task | It is not forecast-time/as-issued data. |
| ECMWF operational/open data | primary as-issued provider | selected | IFS operational run, issue/cycle identity, raw index/GRIB preservation, and 39-Base grid parity passed. |
| Open-Meteo | conditional aggregator candidate | not selected | Provider-native issue/run semantics and use eligibility are not frozen by the existing audit. |

The existing source audit remains the governing evidence:

- `docs/v0-5/weather-source-evaluation.md`
- `docs/v0-5/s2/weather-source-authority-audit-r1.md`
- `docs/v0-5/s2/weather-source-authority-evidence-r1.json`

ERA5-Land remains historical/reanalysis research data and is never adapted to
the `WeatherForecastProvider` contract.

ECMWF Open Data use is bound to the official [open-data licence and
terms](https://www.ecmwf.int/en/forecasts/datasets/open-data), with the
general [licence terms](https://apps.ecmwf.int/datasets/licences/general/)
and ECMWF attribution retained in the source metadata. The selected run was
`20260919000000` (`IFS`, `oper`, `0p25`), whose provider-native cycle timestamp
is the `issued_at`; no GRIB generation time is used as an issue timestamp.

## Contract corrections included in this revision

- Same weather snapshot ID plus the same canonical payload hash is an
  idempotent reuse; a different payload fails with
  `WEATHER_SNAPSHOT_ID_CONFLICT`.
- The same rule applies to area revisions with
  `AREA_REVISION_ID_CONFLICT`.
- `CAPTURED`, `UNAVAILABLE`, and `FAILED` are explicit capture states; the
  state and provider are bound into both the input snapshot and result hash.
- Impossible capture-result combinations fail with
  `WEATHER_CAPTURE_RESULT_INVALID`.
- Existing Base binding and PIT visibility checks remain fail-closed.
- `CAPTURED` requires a non-empty provider and snapshots whose provider
  identity is identical to the capture provider; `UNAVAILABLE` and `FAILED`
  require zero snapshots.
- Capture status and provider identity are explicit fields in both the
  canonical PIT input and result hash.

## Prospective capture evidence

The bounded real capture used one current provider run and the private raw
artifact set below. The source files are not committed to Git.

```ini
RUN_ID=20260919000000
ISSUED_AT=2026-09-19T00:00:00Z
PROVIDER_IDENTITY=ECMWF_IFS_OPEN_DATA|model=IFS|stream=oper|resolution=0p25|run=20260919000000
RAW_SOURCE_ARTIFACT_COUNT=28
RAW_ARTIFACT_MANIFEST_SHA256=aad170103e156a11424c2d487fff27c0b7a263223d7552b155f3c275317477f0
BASE_LOCATION_AUTHORITY_SHA256=502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904
BASE_COUNT=39
UNIQUE_SELECTED_GRID_POINT_COUNT=30
PROVIDER_GRID_SELECTION_PARITY=PASS
SNAPSHOT_COUNT=156
D1_AVAILABLE=true
D3_AVAILABLE=true
D7_AVAILABLE=true
D15_AVAILABLE=true
PROVIDER_MAX_FORECAST_HORIZON=360
WEATHER_CAPTURED_BASE_COUNT=39
WEATHER_UNAVAILABLE_BASE_COUNT=0
WEATHER_FAILED_BASE_COUNT=0
```

The raw set contains the four exact provider index responses and the 24
selected GRIB field byte ranges (`2t`, `tp`, `ssrd`, `10u`, `10v`, plus
provider-supplied `mn2t3`/`mx2t3` where available). D7/D15 min/max are null
because this open-data run does not provide those parameters at those steps;
no cross-provider or hindsight value is substituted.

The capture was executed before the shadow forecast persistence cutoff was
finalized. Consequently `fetched_at`/`known_at` are no later than the final
`forecast_created_at`. Each snapshot is Base-bound and carries the requested
and selected coordinates in its raw reference.

The following are proven for this revision:

```ini
WEATHER_SOURCE_AUTHORITY_FROZEN=true
WEATHER_PROVIDER_USE_ELIGIBLE=true
WEATHER_CAPTURED_BASE_COUNT=39
REAL_WEATHER_CAPTURE_EXECUTED=true
WEATHER_USED_BY_MODEL=false
MODEL_OUTPUT_UNCHANGED_BY_WEATHER_CAPTURE=true
INPUT_SNAPSHOT_HASH_CHANGES_WITH_WEATHER_ID=true
FINAL_PIT_RESULT_HASH_CHANGES_WITH_WEATHER_ID=true
V0_6_S2_COMPLETE=true
```

The history-only Shadow path remains available when no provider is configured,
with an explicit `UNAVAILABLE` capture result. It is not the evidence path
used for the 39-base S2 acceptance above.
