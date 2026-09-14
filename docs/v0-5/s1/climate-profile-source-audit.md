# S1 R2 climate source audit

TASK_ID=V0_5_S1_CLIMATE_PROFILE_AND_YUNNAN_ZONE_STUDY_R2

Base main: `7de37a0db5fdfef1504582090825483d7c97c52f`.
Registry: `d942f78e33495739319753c3f4d184fd0d4ee98a23888c8e710cc17e474cd293`. Frozen S1 input hashes verified before study.
Source: ERA5-Land monthly means, CDS dataset `reanalysis-era5-land-monthly-means`.
[Official catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means)
and frozen catalogue/constraints both show 2026-08, not inferred from today's month.
Purpose: LONG_TERM_AND_RECENT_CLIMATE_PROFILE_RESEARCH; not operational weather authority.

Minimal NetCDF: 25,176 bytes; SHA256
`d68c66bd3ac33099811dee8f996ac6dd1332777057c1f854f12389dc52e51f37`.
It was fully loaded: 2020-01; t2m in K; 21×21 points; CF-1.7; ECMWF.
User-provided minimal request ID: `e7b4ca5e-a4da-452c-ad4c-50af07c334c8`.
No credentials are included in code, requests or evidence.

## Raw snapshot gate and offline replay

All five original NetCDF files fully readable. Four variables each have exactly 428 ordered
monthly observations, no duplicates/missing months, finite values on the entire downloaded grid.
1991–2020=360, 1996–2025=360, 2021–2025=60, 2026 Jan–Aug=8 **for each variable**.
Source gate and separate replay with socket connections disabled both PASS, before profiling.
Snapshot hash: `ddb4e9beb6a68927de882186cd3cbb7efa6b3238d56fb4f20bb2d36b8655ac70`.

| Raw file | Months | SHA256 |
|---|---:|---|
| regional-0.nc | 120 | 3191f301914196a8a7c928067edade87c3fa04a6a204cb9da77e3f0ad0cbba9e |
| regional-1.nc | 120 | ca7ea7bdd02a4392a180b8675a5d0e7d67db21ea8ec2884a817119c4c0906492 |
| regional-2.nc | 120 | f65f2a124c59f9f3484f182cfa23951dde89e967e9896f6e6ff2b216661e4eac |
| regional-3.nc | 60 | 1c590dc178855faf68112090a91639a6c79104cee79fe333bfbea4182a8cbfc3 |
| regional-4.nc | 8 | cbd5b58177852f866da081a1b7915c52a2dad2a387e007e19674a64648288548 |

Private root: `blueberry-area-yield-artifacts/climate-zone-r2-source`.
Every request, receipt, variable metadata, size, timestamp and original file is retained.
The completed-results object did not expose a request_id attribute. Original receipts retain null.
An append-only supplement recovered all five successful job IDs by exact request equality from
the CDS jobs API, without another retrieval. Supplement SHA256: `5658716d214b79fc47da1e2b168a14cb7b5bb26f12d6315bd87c8c9a1360eef0`.
Job IDs: 345bfd42-15df-4c63-8132-ed007e2514a0, ee16a10b-90d2-42b0-8823-85efe120ef4c, 6defe269-eb4a-41f1-a1ed-5bf6a9bdee58, ca5f3b1e-ffcf-421a-bcae-d2707647071c, 952c8389-e991-47d7-9191-41d191d21601.

## Units and extraction

[ERA5-Land monthly accumulation documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=177471794)
establishes that moda accumulation values have an effective daily period.
Actual file units: t2m/d2m=K, tp=m, ssrd=J m**-2. Conversion:

- temperatures: K − 273.15;
- precipitation: daily-mean accumulation ×1000×actual calendar days → monthly mm;
- radiation: daily-mean energy ×actual calendar days/1e6 → monthly MJ/m²;
- moisture: day-weighted temperature minus dewpoint, in °C; no nonlinear VPD proxy asserted.

Nearest 0.1° cell, tie to lower coordinate; no interpolation. Every profile records selected
grid coordinates and haversine distance (Earth radius 6371.0088 km).
Canonical coordinates unchanged:
`SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION`; DEM elevation still requires CRS review.
VPD, GDD, chilling, frost, heat-stress and ET0 are explicitly deferred, never imputed.

本报告只提出候选，不建立生产气候区 authority，不开启 S2。BASE_REGISTRY_V1 及 R2 alias authority 保持不变。不使用采摘量、亩产、面积、峰值或预测误差。

## Reproduction and delivery

Install the isolated research extras with `uv sync --extra dev --extra climate`.
Run commands from the repository root. Paths below are private artifact directories, not Git inputs.

```sh
python -m scripts.climate_source_r2 --source /path/to/climate-zone-r2-source --replay
python -m scripts.run_climate_study_r2 --source /path/to/climate-zone-r2-source --registry /path/to/base-registry-s1-final --output /path/to/new-exclusive-output
```

Source replay was additionally executed with `socket.socket.connect` disabled; the complete study
was replayed in a fresh process under the same network prohibition. Every file hash in the final
study manifest matched. Final artifact directory:
`blueberry-area-yield-artifacts/climate-zone-r2-review-complete`;
replay: `blueberry-area-yield-artifacts/climate-zone-r2-review-complete-replay`.
The earlier `climate-zone-r2-study` is an intermediate snapshot preserved, not the final pointer.
Only geographic extent diagnostics were subsequently added; scores, parameters and assignments did
not change. The final review-complete snapshot additionally aggregates the already-computed
recent-normal stability, recent drift and Jan-Aug anomalies per zone. All other payload hashes
match the preceding final snapshot. Raw files and the frozen source manifest were never rewritten.

For a new authorized download, use `python -m scripts.retrieve_climate_zone_r2 --output <new-private-directory>`.
Existing directories are refused. Five regional requests, never 38 separate per-base downloads.
Only a configured CDS client may retrieve; credentials are never command-line inputs.
