# ERA5-Land source artifact characterization R1

`V0_5_S2_ERA5_LAND_SOURCE_ARTIFACT_CHARACTERIZATION_R1` completed the
authorized source-only characterization for the frozen 105-request
`reanalysis-era5-land-timeseries` plan.

## Scope and safety boundary

The existing R3 envelope remains unchanged:

```ini
TP_NEGATIVE_ARTIFACT_ENVELOPE_MIN_M=-3.0e-8
SSRD_NEGATIVE_ARTIFACT_ENVELOPE_MIN_J_M2=-4
R3_PROVISIONAL_ENVELOPE_STATUS=INSUFFICIENT_FOR_FINAL_AUTHORITY
```

This task was allowed to retrieve all already-planned requests so that the
provider value distribution could be measured. A value outside that provisional
envelope did not stop retrieval, but it prevents acceptance of a normalized
hourly/daily dataset. No correction was applied, no positive-value threshold
was used, and no normalization or model work was performed.

The 22 receipts and 21 raw files from the earlier R3 checkpoint were retained.
The one pending submitted receipt was recovered by its existing remote request
identity. The remaining 83 frozen entries were submitted without generating a
new plan or replacement request IDs. Two transient download failures were
resumed using their existing receipts; no request was resubmitted.

## Characterized source

All 105 frozen requests now have a verified raw artifact. The plan covers 35
unique provider grid cells, 38 base projections, and the three authorized
business seasons. The six requested native variables are 2m temperature, 2m
dewpoint temperature, total precipitation, downward surface solar radiation,
and the 10m u/v wind components. Each raw artifact passed request/receipt
identity, raw hash, provider point, variable/unit, finite-value,
duplicate-timestamp, and hourly coverage checks.

The frozen request manifest hash is:

```text
2bd5f909945f0ba677d9818c9cb23a3eb80119cb9e03407707cbbe83880bddb1
```

The committed characterization configuration is
`configs/era5_land_source_characterization_r1.json`; its SHA256 is
`33a0b11a081d05297778b08d3ef7e7d40dce7a965bc9fc0bd2575c36bab393a4`.

The resulting private characterization artifact is:

```text
blueberry-area-yield-artifacts/era5-land-source-characterization-r1/
```

Its deterministic characterization hash is:

```text
9994f4290bc5c2de144ae792813715aac84acd7b42f634ee69f866fa0bb568a2
```

The raw artifact set hash is:

```text
6df5a8e909447384a3b33414facf6e768d1fb31c52b89ebec59bec37e3f358d8
```

## Negative-value distribution

The statistics below use provider raw values and do not rewrite them.

| variable | observations | negatives | rate | minimum raw value | maximum negative | minimum positive | provisional exceedances |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `tp` | 731,640 | 9,822 | 1.34246350664261112% | -4.3499312596395612e-08 m | -4.5474735088646412e-13 m | 5.6843418860808015e-14 m | 10 |
| `ssrd` | 731,640 | 9,981 | 1.36419550598655076% | -4 J/m² | -0.125 J/m² | 0.125 J/m² | 0 |

The negative observations occur across all 105 requests, all 35 grid cells,
and all three seasons. The `tp` exceedances are therefore not treated as a
single-file transport anomaly; they remain a source-policy decision for
Coordinator review. The full month, UTC-hour, season, and grid-cell breakdown
is in `characterization.json` under `by_dimension`.

For `tp`, the negative-value quantiles are:

```text
p01=-2.6101640742126619e-08 m
p05=-1.4901161193847656e-08 m
p50=-7.4505805969238281e-09 m
p95=-1.5124896890483797e-09 m
p99=-3.4924596548080444e-10 m
```

For `ssrd`:

```text
p01=-4 J/m²
p05=-2 J/m²
p50=-2 J/m²
p95=-0.5 J/m²
p99=-0.25 J/m²
```

The smallest positive provider values were retained as observations; no
drizzle or radiation threshold was introduced.

## Replay and next gate

Two fresh processes replayed source verification and characterization from the
same local raw artifacts with networking disabled. Both produced identical raw
artifact-set hashes, source-audit replay hashes, and characterization hashes.

The accepted normalized dataset remains intentionally unbuilt:

```ini
NORMALIZED_DATASET_GENERATED=false
HOURLY_DATASET_GENERATION_AUTHORIZED=false
DAILY_DATASET_GENERATION_AUTHORIZED=false
FINAL_SOURCE_ARTIFACT_CORRECTION_NOT_FROZEN=true
```

The next decision is a source-policy disposition for the characterized `tp`
distribution. It is not a model-training or historical-as-issued forecast
decision.

Historical as-issued PIT remains unestablished; ERA5-Land remains a
reanalysis reference only.
