# Banna scope identity rebind and parameter authority gate R2

TASK_ID=V0_3_BANNA_SCOPE_IDENTITY_REBIND_AND_PARAMETER_AUTHORITY_GATE_R2

Current conclusion for Draft #607: farm identity is resolved without invented geography.
The real `POST /planning/tasks` returned **422** with
`parameter library version not found`. This is a real request, not a successful
parameter inference run. No inferred numbers or per-parameter confidence values
were issued. No Task8, Task9 or Forecast was executed.

## Corrected scope and actual identity proof

`BANNA_MENGWANG_DX_736MU_R1` binds farm `版纳勐旺农场`, destination factory
`勐旺加工厂`, display label `版纳勐旺加工厂`, variety `Dx`, and farm-level
aggregate area `736.000000` mu. The coordinator supplies the area authority.
No area is assigned to any subfarm.

Re-reading only identity columns in the 2024–2025 source yields one unique
farm/factory pair across all rows matching either name: 3420 records.
Subfarm counts 1271 + 1159 + 990 reconcile to 3420. No matching farm record has
a missing/different factory, including the sheet without a factory header.
This proves 1:1 within this source, not across every season.
The full source hash is in the [R2 evidence](evidence/banna-scope-parameter-authority-r2.json).
The 2025–2026 source and TEST were not opened.

Canonical `create_master_data` created Farm and Factory in the existing acceptance
database, reusing R1's Dx Variety. Fresh readback confirms identities 1/1/1 and
null coordinates. No SQL seed or fabricated location reference was used.

## Software correction

`LocationInput.farm_id` is a fourth explicit input mode and rejects location
overrides. The resolver reads the canonical Farm and returns an identity-scoped
resolved location. Its snapshot binds farm ID/name and method. Missing geography
is explicit and does not prevent same-farm observation selection.

The candidate loader matches canonical IDs in this mode. Similarity ranking no
longer discards same-farm candidates merely because coordinates are null.
Distance, township-altitude and climate-zone fallback remain unavailable in
farm-only mode. An explicitly labeled, PIT-eligible literature prior remains
usable; another farm's history cannot be relabeled as a literature prior.
Legacy address/reference payloads omit null farm_id to retain their serialized
identity. Source signatures bind `farm:<id>` for the new mode.

## Actual Task5 gate

The PR working tree ran on loopback HTTP 8007 against the existing nonproduction
acceptance PostgreSQL port 55437. `/health/live` and `/health/ready` returned 200.
Normal `/planning/tasks` received farm_id=1, Dx, 736 mu, as_of_date=2026-09-11.
No dependency override or mock was used for this business call.

`MINIMAL_PLANNING_EXECUTED=true` means the actual API request was made.
`MINIMAL_PLANNING_STATUS=HTTP_422_PARAMETER_LIBRARY_VERSION_NOT_FOUND` is its actual
result. Canonical library selection occurs before inference and rejects an empty
store. We did not create an empty library to disguise that rejection.
The canonical farm resolver was also checked separately in a fresh read-only
session and returned `resolved`, with latitude/longitude/climate zone null.

## Parameter data-product conclusion

Read-only counts: ParameterLibraryVersion=0, ParameterObservation=0,
FarmSeasonVarietyPlan=0, maturity_model_artifact=0. Current and retained V0.2
observation CSV templates have zero data rows. The located V0.2 copy has no .env
runtime binding; defaults/demo configuration are not proof of recoverable authority.
No default database was probed or fixture transferred. Config thresholds, model
code and a fallback-tier implementation do not constitute parameter observations.
This is a scoped search result, not a claim that no authority exists globally.

All seven parameters remain unavailable: yield_kg_per_mu, marketable_rate,
first_harvest_offset_days, maturity_peak_offset_days, maturity_width_days,
maturity_skewness, harvest_realization_rate. The seven-parameter R1 semantic
analysis remains applicable. No historical materializer is safe to implement
without those definitions' denominators, anchors and visibility provenance.

The coordinator's matched_relationship.csv values annual_t=1145 and planting_mu=736
are accepted as analysis context; that file was not independently located in this
checkout/search. Neither value was used to generate a parameter. Receipt tonnage
cannot identify both gross yield and marketable rate in
`effective volume = area × yield × marketable_rate`. It also does not identify
natural maturity or harvest realization.

INTERNAL_DATA_PRODUCT_BLOCKER=AUTHORIZED_PARAMETER_OBSERVATION_MATERIALIZATION_NOT_AVAILABLE

PARAMETER_SOURCE_AUTHORITY_REQUIRED=true

MISSING_EXTERNAL_BUSINESS_FACTS=NONE

## Boundaries and review

R1 remains historical evidence; this R2 supersedes its live location blocker.
S4 remains closed. No VALIDATION, scoring, TEST, model approval or downstream run.
Budget is the last accepted durable snapshot (8 consumed, 24 remaining), not a
new database readback. Delta=0. Keep #607 Draft; no Ready/Merge.

FINAL_STOP_GATE=COORDINATOR_BANNA_PARAMETER_AUTHORITY_R2_REVIEW
