# V0.5 S2-01 — Weather source authority / PIT audit R1

## 1. Decision and execution identity

`TASK_ID=V0_5_S2_WEATHER_SOURCE_AUTHORITY_AUDIT_R1`

Actual base: `e47dc930198d96f8044058f45b9d228f84c9bc14` (PR #626 merge,
verified on fetched `origin/main`). Branch: `codex/v0-5-s2-weather-source-authority-r1`.
Official sources were refreshed on **2026-09-14**, not copied from the earlier
[candidate framework](../weather-source-evaluation.md).

| Role | Recommendation | Qualification boundary |
|---|---|---|
| LONG_TERM_CLIMATOLOGY | ERA5-Land monthly | Candidate; reuse immutable S1 source evidence, not candidate zones |
| HISTORICAL_ACTUAL_WEATHER | ERA5-Land hourly reanalysis reference | Candidate, not observed field truth; hourly extraction not executed here |
| HISTORICAL_FORECAST_ARCHIVE | **NONE qualified** | Historical issued/available evidence and project access not established |
| LIVE_FORECAST | ECMWF Open IFS control, conditional | Public index verified; actual fields/local-day aggregation not verified; not a W15 guarantee |

`S2_OPERATIONAL_WEATHER_BACKTEST_BLOCKED=true` and `S2_04_BLOCKED=true`.
This is an **audit completed with an operational-data dependency**, not permission
to substitute actual weather or hindcast. No source becomes active authority.
Open-Meteo remains a secondary, entitlement-dependent live candidate, not a
shortcut around the missing historical PIT evidence.

## 2. Evidence and minimum probe

[Evidence JSON](weather-source-authority-evidence-r1.json) records 18 official
document/catalogue/index captures, each with source, title, URL, UTC access time,
fact, separate project interpretation, status and raw SHA256. Its seven-row
`source_matrix` contains all required licence/access/cost, W7/W15, timing,
version, variables, grid, coverage and limitation fields. `variable_matrix`
contains eight variables for each of three provider groups (24 rows).

Statuses are deliberately distinct:

- DOCUMENTED: a current official description, not a project acceptance result.
- PROJECT_VERIFIED: only the narrow experiment actually performed (e.g. catalogue
  HTTP200, source snapshot hash, software gate or timezone arithmetic).
- NOT_VERIFIED: access, behaviour or availability not established here.
- NOT_SUPPORTED: known semantic incompatibility, such as stitched runs for PIT.
- NOT_APPLICABLE: a role genuinely does not apply, such as reanalysis live issue.

Private snapshots: `blueberry-area-yield-artifacts/weather-source-authority-r1/`,
under the existing local controlled artifact root. Manifest: `capture-manifest.json`.
Only public document metadata/hashes are committed, not the captured HTML.
All 18 requests returned HTTP200; **zero weather field requests**, zero accounts,
zero secret access, zero paid operations and no bulk downloads. The public ECMWF
index is a real accessibility probe, not an assertion that native GRIB field,
lead, variable or timezone support has passed. CDS catalogue metadata is likewise
not a successful project hourly extraction.

Open-Meteo's free-service terms exclude undisclosed commercial research; public
documentation was read, but a business-use weather query was **not** made without
verified entitlement. See [terms](https://open-meteo.com/en/terms) and
[pricing](https://open-meteo.com/en/pricing). No purchase is authorized.

## 3. Provider findings

### C1 — ERA5-Land

The [current CDS catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview)
describes hourly reanalysis from 1950; the captured catalogue extent ends
2026-09-08. Its current CC-BY-4.0 entry supports an attribution-bearing candidate,
not an availability-time claim for historical origins. Monthly climate and
hourly actual-weather research are separate roles.

The [data documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=185075237)
distinguishes instantaneous fields from 00 UTC short-forecast accumulations.
The step24 accumulation belongs to the preceding UTC day. Native ~9km and CDS
regular 0.1-degree grids are not the same extraction contract. Older introductory
coverage/update statements conflict with the refreshed catalogue; no latency SLA
is inferred from them. Neither version is historical as-issued operational weather.

### C2 — ECMWF archive versus live

The [operational archive](https://www.ecmwf.int/en/forecasts/datasets/operational-archive)
really exists in MARS. Project-entitled years, exact parameters, extraction and
historical issue/access receipts are **NOT_VERIFIED**. Access depends on
[entitlement](https://www.ecmwf.int/en/forecasts/access-forecasts/access-archive-datasets)
and [service agreement](https://www.ecmwf.int/en/forecasts/accessing-forecasts/service-agreements);
free data licensing does not imply free archive delivery. Stop before procurement.

[Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data) is a rolling
12-run public subset, not the needed multi-year archive. Current IFS control
00/12 UTC steps extend to360h; 06/18 reach144h. The public 0.25-degree product
does not automatically match historical native grids. Current cycle/stream/step
rules must not be retroactively applied to every historical run.

[Official cycle history](https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model)
places 49r1 at2024-11-12 and50r1 at2026-05-12. Pin cycle, stream, control/member,
parameter and [GRIB step metadata](https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF+open+data+real-time+forecasts+from+IFS+and+AIFS).
A published dissemination schedule is not an actual historical availability receipt.

### C3 — Three different Open-Meteo services

[Historical Forecast](https://open-meteo.com/en/docs/historical-forecast-api)
stitches short leads from successive runs: rejected for this single-origin task.
[Single Runs](https://open-meteo.com/en/docs/single-runs-api) identifies UTC
initialization, not publication/access time. The early IFS archive explicitly
contains 49r1 hindcasts, including dates preceding operational49r1 deployment;
these cannot be treated as contemporaneous forecasts. Later archive availability
still requires proof. Its IFS10-day table is not silently overridden by the
dedicated live page's advertised15-day horizon.

[Live API](https://open-meteo.com/en/docs) defaults can choose/merge models and
apply elevation downscaling. Explicit model and processing choices are required.
[Model Updates](https://open-meteo.com/en/docs/model-updates) explicitly distinguishes
file modification from API availability. `generationtime_ms` measures query
processing; it is not `issued_at`. `OPEN_METEO_PIT_STATUS=PIT_NOT_ESTABLISHED`.

## 4. Frozen research PIT contract

[Configuration](../../../configs/weather_source_authority_r1.json) is located at
repository `configs/weather_source_authority_r1.json` (see executable command below).
The independent offline [verifier](../../../scripts/audit_weather_source_r1.py)
is at repository `scripts/audit_weather_source_r1.py`.
It does not implement ingestion, interpolation, model features or weather scoring.

Every sample binds `base_id`, `forecast_origin_at`, `forecast_origin_timezone`,
`issued_at`, `available_at`, `retrieved_at`, `raw_artifact_hash`,
`normalized_payload_hash`, `processing_version` and one run identity containing
`model_initialization_at`, `provider`, `model`, `model_cycle`, `product`, `stream`,
`member_or_control`, `source_revision`. Every support interval repeats that run
identity and has `valid_time` plus integer `lead_time` seconds since initialization.
All timestamps require offsets; comparisons use instants, not bare date strings.

Hard gates:

1. `init <= issued <= origin`, `init <= available <= origin`, `issued <= available`.
   Equality at origin is allowed; one second after origin is rejected.
2. Missing issued/available evidence remains `PIT_NOT_ESTABLISHED`. Later retrieval
   is allowed only with independent historical proof; it cannot supply that proof.
3. Reviewed evidence references must accompany PROJECT_VERIFIED status for issue,
   availability, archive coverage, access, licence, commercial use, as-issued
   provenance and support semantics. DOCUMENTED alone cannot pass this gate.
4. Only one origin/run; reject reanalysis, hindcast, stitched products, mixed runs,
   duplicate/overlapping supports, unknown variables and malformed payload hashes.
5. No candidate climate-zone authority. No actual-weather filling, later-run
   stitching, silently clipped accumulation or inferred missing monthly/daily data.

The verifier checks **evidence structure and declared normalized support**, not
the authenticity of a publisher's receipt. A caller cannot turn synthetic tests
into actual provider qualification. Raw weather-byte verification and independently
reviewed timestamp/provenance evidence remain prerequisites before any later pipeline.
`PIT_CONTRACT_PASS` therefore is not authority activation.

## 5. W7/W15 and interval semantics

For local origin date D, W7 is `[D+1 00:00,D+8 00:00)` and W15 is
`[D+1 00:00,D+16 00:00)` in Asia/Shanghai. Every required variable must cover
the complete normalized window without gaps, duplicates or overlapping intervals.
Wind is audited conservatively but not yet required as a model feature.

Executable synthetic geometry: init2026-09-14T00Z, origin06Z (14:00 Shanghai).
Both windows begin2026-09-14T16Z. W7 ends2026-09-21T16Z; W15 ends2026-09-29T16Z.
The360h horizon ends2026-09-29T00Z: **16 hours short**. This proves the arithmetic,
not actual provider issuance or data access. Six-day06/18UTC runs cannot W7 either.

Shanghai midnight16UTC is not on the3h UTC grid. Temperature point interpolation,
interval extrema, precipitation increments and radiation energy require distinct
future processing decisions. A fractional split of a6h precipitation interval is
not documented truth. The verifier deliberately refuses intervals crossing a
window edge instead of inventing values. No normalization routine is implemented.

## 6. Variables, grids and compatibility

The JSON variable matrix records native IDs, units, level, instant/accumulated
type, reset, resolution, necessary conversion and archive/live status. Important
non-equivalences are explicit: IFS `tp/228` versus AIFS `tp/228228`; downward
`ssrd/169` versus net `ssr/176`;2m RH derived from T/Td versus pressure-level RH;
energy J/m² versus hourly mean W/m²; sampled daily extrema versus native interval
extrema. Formula descriptions are audit requirements, not executable weather features.
VPD/ET0/GDD/chilling remain DERIVED_CANDIDATE; constants and applicability unapproved.

All extraction is at **base representative location**, never farm-name geocoding.
Retain requested and returned coordinates, selected grid, interpolation method,
model orography, and separately qualified base elevation. Model orography or a90m
DEM is not a new registry authority. Open-Meteo's `elevation=nan`/nearest cell is a
possible explicitly pinned raw-grid research choice, not an activated policy.

Archive/live equivalence is **NOT_VERIFIED** across provider, model family/cycle,
parameters, level, grid, forecast step, reset, post-processing, interpolation and
availability. Same brand or same display variable name is insufficient. Yunnan is
within the documented global grids; no actual base extraction was performed here.

## 7. Reproduction, tests and stop gate

From repository root, without network:

```bash
.venv/bin/python -m scripts.audit_weather_source_r1
.venv/bin/pytest -q backend/tests/base_registry/test_weather_source_authority_r1.py
.venv/bin/ruff check scripts/audit_weather_source_r1.py backend/tests/base_registry/test_weather_source_authority_r1.py
.venv/bin/ruff format --check scripts/audit_weather_source_r1.py backend/tests/base_registry/test_weather_source_authority_r1.py
.venv/bin/mypy scripts/audit_weather_source_r1.py
git diff --check
```

Local execution: **33 focused tests PASS; 96 base-registry tests including those
33 PASS**. Repository-wide Ruff/format PASS (1044 files); Mypy backend/app PASS
(444 files), audit-script Mypy PASS. JSON and relative references PASS. These are
software/document checks, not successful provider PIT backtests.

Private document snapshot replay compares every raw SHA256 against both capture
manifest and checked-in evidence, with no network. The unit replay additionally
forbids socket creation. Focused software gates cover timestamps, full W7/W15,
360h shortfall, local accumulation edges, mixed runs, source substitution, access,
licence, archive coverage, proof references, candidate zones and canonical hashes.
Relevant S1 regressions must pass; GitHub full-suite remains required on new HEAD.

Next evidence need, **not a new authorized task**: project-legal operational
archive access plus original issue/availability provenance, exact years/cycles,
full local W7/W15 parameter support and archive/live compatibility. If unavailable,
weather operational backtesting stays blocked; weather is optional and must later
prove incremental value. No new supplier account, purchase or S2-04 pipeline here.

```ini
WEATHER_SOURCE_AUTHORITY_STATUS=CANDIDATE
WEATHER_SOURCE_AUTHORITY_FROZEN=false
HISTORICAL_AS_ISSUED_AUTHORITY_CANDIDATE=NONE
S2_OPERATIONAL_WEATHER_BACKTEST_BLOCKED=true
CLIMATE_ZONE_MAPPING_REQUIRED=false
CLIMATE_ZONE_MAPPING_USED_AS_AUTHORITY=false
ELEVATION_EXTERNAL_VERIFICATION_NOT_AUTHORIZED=true
WEATHER_MODEL_TRAINING=false
FORECAST_MODEL_CHANGED=false
DATABASE_SCHEMA_CHANGED=false
MCP_CHANGED=false
PRODUCTION_DEPLOYMENT_CHANGED=false
CLIMATE_ZONE_MAPPING_CHANGED=false
BASE_REGISTRY_MEMBERSHIP_CHANGED=false
WEATHER_BULK_DOWNLOAD=false
WEATHER_INGESTION_PIPELINE=false
S2_02_NOT_AUTHORIZED=true
S2_03_NOT_AUTHORIZED=true
S2_04_IMPLEMENTATION_NOT_AUTHORIZED=true
S2_05_NOT_AUTHORIZED=true
S2_06_NOT_AUTHORIZED=true
S2_07_NOT_AUTHORIZED=true
READY_ELIGIBLE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
FINAL_STATUS=COORDINATOR_S2_WEATHER_SOURCE_R1_REVIEW
```
