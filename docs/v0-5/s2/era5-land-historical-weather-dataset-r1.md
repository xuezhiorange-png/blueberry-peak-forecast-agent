# S2 ERA5-Land historical weather facts — R1

Status: IN_PROGRESS; this Draft is not dataset acceptance.

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
dataset can be described as complete. CDS access is not yet verified.
