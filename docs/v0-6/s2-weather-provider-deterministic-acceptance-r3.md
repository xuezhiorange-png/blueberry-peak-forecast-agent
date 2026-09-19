# V0.6-S2 ECMWF provider deterministic acceptance R3

`TASK_ID=V0_6_S2_ECMWF_PROVIDER_DETERMINISTIC_ACCEPTANCE_R3`

This document records the offline acceptance layer for the already-qualified
ECMWF IFS Open Data adapter. It does not select a new provider, download new
weather data, change the Shadow Forecast path, or promote weather into the
frozen V0.5 model.

## Scope and source boundary

The provider remains:

```ini
WEATHER_PROVIDER=ECMWF_IFS_OPEN_DATA
MODEL=IFS
STREAM=oper
RESOLUTION=0p25
WEATHER_USED_BY_MODEL=false
```

ERA5-Land remains realized/reanalysis data and is not used as forecast-time
input. The existing real capture evidence is preserved and is not replaced by
the test fixture:

```ini
RUN_ID=20260919000000
RAW_ARTIFACT_MANIFEST_SHA256=aad170103e156a11424c2d487fff27c0b7a263223d7552b155f3c275317477f0
WEATHER_CAPTURED_BASE_COUNT=39
```

The real index/GRIB artifacts remain in the operator-controlled private
artifact store; no large raw file is committed to Git.

## Offline fixture acceptance

`backend/tests/v06_s2/test_ecmwf_open_data_provider.py` contains a small
deterministic transport and decoder fixture. It models the provider index
entries and bounded field byte ranges for `2t`, `tp`, `ssrd`, `10u`, and `10v`,
with optional `mn2t3`/`mx2t3`. It is deliberately not a production raw
artifact and makes no network request.

The fixture proves:

- future runs after the forecast cutoff are never selected;
- the nearest qualified run is selected, with deterministic fallback and
  `ECMWF_NO_QUALIFIED_RUN` when no candidate is usable;
- `levtype=sfc`, parameter, step, byte offset, and byte length are parsed;
- malformed indexes and missing required parameters fail closed;
- Kelvin-to-Celsius, metre-to-millimetre, vector wind speed, and unchanged
  SSRD semantics are deterministic;
- non-finite values and negative precipitation/solar values fail closed;
- D1/D3/D7/D15 are represented by 24/72/168/360-hour `valid_at` values;
  unavailable D15 is omitted rather than fabricated;
- raw artifact same-bytes reuse is idempotent and changed bytes raise
  `ECMWF_RAW_ARTIFACT_CONFLICT`;
- raw manifest, raw payload, normalized payload, and snapshot identity are
  deterministic and bind run, Base, grid, horizon, and source values;
- the explicit 0.25-degree grid and lower-coordinate tie-break remain bound;
- one Base and all 39 registry Bases capture offline with deterministic order,
  provider identity, Base binding, and four available horizons.

The fixture decoder is the permitted deterministic decoder equivalent for this
unit boundary; no large GRIB2 fixture is stored in the repository.

## Acceptance result

```ini
ECMWF_RUN_SELECTION_TEST=PASS
ECMWF_INDEX_PARSING_TEST=PASS
ECMWF_GRIB_DECODE_TEST=PASS
ECMWF_UNIT_NORMALIZATION_TEST=PASS
D1_FIXTURE_PASS=PASS
D3_FIXTURE_PASS=PASS
D7_FIXTURE_PASS=PASS
D15_FIXTURE_PASS=PASS
RAW_ARTIFACT_IDEMPOTENCY_PASS=PASS
RAW_ARTIFACT_CONFLICT_PASS=PASS
ARTIFACT_MANIFEST_DETERMINISM_PASS=PASS
RAW_PAYLOAD_HASH_DETERMINISM_PASS=PASS
NORMALIZED_PAYLOAD_HASH_DETERMINISM_PASS=PASS
WEATHER_SNAPSHOT_ID_DETERMINISM_PASS=PASS
BASE_GRID_BINDING_PASS=PASS
CAPTURE_CONTRACT_PASS=PASS
OFFLINE_39_BASE_CAPTURE_PASS=PASS
OFFLINE_CAPTURED_BASE_COUNT=39
REAL_CAPTURE_EVIDENCE_PRESERVED=PASS
```

The acceptance fixture is additive regression coverage. It does not alter the
provider's real artifact manifest, the location authority, V0.5 forecast
mathematics, or the S2/S3/S4 authorization boundary.
