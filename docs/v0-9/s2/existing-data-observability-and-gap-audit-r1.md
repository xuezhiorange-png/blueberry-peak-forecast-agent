# V0.9-S2 Existing Data Observability and Gap Audit

**Task:** `V0_9_S2_EXISTING_DATA_OBSERVABILITY_AND_GAP_AUDIT_R1`  
**Version:** `0.9.0` — `BLUEBERRY_FORECAST_AGENT_V0_9_BIOLOGICAL_FORECAST_FOUNDATION`  
**Authority:** pinned V0.9-S0 evidence and the complete V0.9-S1 R1 artifact manifest.  
**Result:** `PASS_V0_9_S2_DATA_OBSERVABILITY_AUDIT_COMPLETED`

## Scope and audit method

This is a bounded inventory of repository-referenced data, V0.8/V0.9 authorities, known authorized artifact references, and the raw sources already in the project. It is not a scan of the user's computer. S0/S1 scientific conclusions are unchanged. No live database was queried; empty templates and application schemas are not treated as business records. Public artifacts use logical source IDs and contain no machine-specific absolute paths.

S0's six authority artifact hashes were recomputed and matched. The nine S1 contract/evidence files were individually rehashed and recorded in `docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json`. The S2 matrix contains **252 audit rows**: 213 contract/data variables plus 39 causal-edge/quarantine evidence items. It includes 33 biological/inter-season/source-sink fields, 21 phenology states, all 29 event types, environment and production-system inputs, cohort fields, and parameter-authority vocabulary/candidates.

## Current data picture

| Asset | Verified coverage | Authority and boundary |
|---|---|---|
| Productive area | 117 Base-season rows; 39 canonical Bases × 3 seasons; 41,335 mu per season | V0.8 business-confirmed authority; S2 does not reopen it |
| Canonical daily harvest | 33033 Base-date rows; complete daily curves 15 / 22 / 39 by season | Authorized harvest output; not ripe/maturity observation |
| Strict historical training | 37 rows: 15 in 2023–24 and 22 in 2024–25 | Historical target evidence only; no fitting here |
| Raw 2024–25 receipts | 201,434 rows; 323 dates; through 2025-05-27 | 42 dates exceed frozen 2025-04-15 season end; keep out-of-window rows explicit |
| Raw 2025–26 receipts | 232,527 rows; 229 dates; through 2026-04-16 | Consumed benchmark; 1 date exceeds frozen 2026-04-15 end; audit-only |
| Cultivar | Variety label populated on receipt rows | Transaction-level proxy only; no cultivar-to-productive-area binding |
| Production plans / planting / phenology / weather templates | No populated business records; weather files contain only template/synthetic examples | Schema/template presence is not evidence of executed event or observation |

The receipt workbooks contain a fruit-size category but not numeric berry diameter or mean berry mass. Receipt arrivals/harvests are model target/output evidence under the frozen V0.8 business rule; they do not establish when fruit first became physiologically ripe.

## Observability counts

| Actual observability status | Matrix rows |
|---|---:|
| AVAILABLE | 3 |
| BUSINESS_CONFIRMATION_REQUIRED | 35 |
| DERIVABLE | 3 |
| NEW_COLLECTION_REQUIRED | 99 |
| PROXY_AVAILABLE | 9 |
| UNOBSERVABLE | 64 |

These status counts cover the 213 enumerated variables. The matrix additionally carries 39 qualitative S1 causal-edge/quarantine evidence rows, which are not counted as observable variables. Counts are not percentages of the entire company database. Lack of a row in this bounded inventory is not a claim about unqueried live database content. Authority is separately recorded in the matrix and source register.

Phenology state coverage: 0 directly observed, 0 derivable as physiological states, 2 harvest-derived proxy state(s), and 1 unobservable in the reviewed records. No direct bloom/bud/fruit-set/color-break observations were found. Harvest timing proxies remain explicitly non-physiological.

Production system is not assigned for the 117 Base-season candidate scope. `DECIDUOUS_NATURAL`, `DECIDUOUS_FORCING`, and `EVERGREEN` therefore require business confirmation; no region, cultivar label, or harvest date is used to infer system.

## Management, phenology, weather and source–sink gaps

No authorized executed records were found for any of the 29 management-event types. The empty production-plan template/schema has a planned `pruning_date` field, but no actual event row, pruning type/intensity, removed wood/buds, or cane-renewal measurement. Flower/fruit thinning and greenhouse close/open/heating are not evidenced as actual events. Standard procedures or planned dates are not converted to executed histories.

No direct phenology states are present. The only operational timing derivations are from complete harvest curves: first/half-cumulative/last nonzero harvest dates for 76 eligible daily curves; these are harvest-derived proxies, not bloom/ripe observations.

ERA5-Land attempts do not form an accepted normalized history dataset: prior builds are blocked, R3 stopped with 91 requests pending, no accepted normalized hourly/daily rows exist, and coordinate CRS is not established. ECMWF provides 156 prospective outdoor forecast snapshots for 39 Bases across four horizons, with a 360-hour horizon; it is not historical or indoor microclimate. Thus current authorized data cannot derive chill hours, Utah units, dynamic chill portions, or forcing GDD for biological calibration. `GREENHOUSE_TEMPERATURE=NEW_COLLECTION_REQUIRED`.

There are no observed leaf-area/canopy, effective flower load, fruit-set, fruit number, crop-load, or reserve measurements. Fruit-size class is a category proxy only. `carbohydrate_reserve_proxy` and exact source–sink balance remain unobservable/latent; no proxy is silently invented. BloomCohort and FruitCohort have no empirical rows or lineage, so `FRUIT_COHORT_STRUCTURE_SUPPORTED` does not mean empirically calibrated or ready.

## S3 data readiness

| Module | Current readiness | Evidence-bounded reason |
|---|---|---|
| Phenology Engine | SYNTHETIC_ONLY | S1 transitions exist, but no direct bloom/bud phenology history and no accepted continuous temperature series; no chill/forcing model selected. |
| Crop Load Engine | SYNTHETIC_ONLY | No authorized flower-load, pollination, fruit-set or fruit-number observations; thinning execution not recorded. |
| Source-Sink Proxy | SYNTHETIC_ONLY | Composite states have no validated observed proxy bundle; carbohydrate reserve is latent and exact formula unbound. |
| Bloom Cohort | SYNTHETIC_ONLY | No bloom cohort date/quantity/provenance rows or lineage. |
| Fruit Cohort | SYNTHETIC_ONLY | No bloom→fruit-set→color-break→ripe cohort linkage; harvest is not a maturity cohort observation. |
| Maturity Engine | SYNTHETIC_ONLY | No color-break or ripe observations and no cohort calibration; only harvest output is available. |
| InterSeason Carryover | SYNTHETIC_ONLY | No postharvest vigor/reserve/bud-potential observations; cross-season yield is not a substitute. |
| Biological→Harvest Interface | CONTRACT_READY | S1 interface is frozen and historical daily harvest output exists, but daily newly mature biological supply is not observed; interface test inputs must be synthetic/proxy-labeled. |

`CURRENT_MAX_FEASIBLE_LEVEL=LEVEL_1_HISTORICAL_PROXY_MODEL` applies only to coarse historical area/harvest target proxies. The biological state-transition prototype itself is currently **synthetic-only**; Level 2 biological-observation readiness is not established.

## Minimum viable inputs and collection priority

The full field-by-field lists are in `minimum-viable-biological-input-set-r1.csv` and `minimum-new-data-collection-plan-r1.csv`. The minimal practical next-season package prioritizes: stable Base/subfarm/cultivar-area identity, accepted area, explicit production-system assignment and tree age; actual pruning and greenhouse/heating event dates; 10/50/90% bloom; representative indoor hourly air temperature; then flower-thinning event, fruit-set sample, and 10% color-break observation. Existing daily harvest should continue with source/date/quantity authority. Advanced cohort tagging, canopy sampling, extra sensors, and carbohydrate assays remain P2 and are not S3 blockers.

Collection plan counts: P0=8, P1=5, P2=4 fields. These priorities balance causal/identifiability value, likely coverage, and operational burden; they do not select model parameters.

## Answers to the ten audit questions

1. **Directly observed biological states?** None of the 21 phenology states and none of the 33 biological/inter-season/source-sink fields has an authorized direct observation in the reviewed records. Area and harvest output are available, but they are not plant-state observations.
2. **Derivable?** Harvest timing summaries are derivable for 76 complete daily curves, but only as harvest proxies. Chill/forcing and physiological transitions are not derivable from current accepted environment data.
3. **Proxy-only?** Receipt fruit-size category and harvest-derived first/median/end timing are proxies; neither becomes physical berry size, mean berry weight, or ripe state.
4. **Existing management records?** Zero of 29 event types has an authorized executed-event record in the bounded review.
5. **Pruning, thinning, forcing history?** No executed histories. Only an empty planned-pruning schema/template exists; business confirmation and prospective event capture are required.
6. **Indoor hourly microclimate?** No. ECMWF is outdoor forecast context, not greenhouse sensor data; indoor hourly temperature is a P0 new collection.
7. **Chill/forcing identifiable now?** No. Accepted continuous temperature series and indoor forcing records are absent; no chill or forcing model is selected.
8. **Bloom-to-maturity cohort identifiable?** No empirical cohort lineage. Structure may be represented synthetically, but empirical calibration is not identified.
9. **S3 maximum feasible level?** Level 1 only for coarse historical proxy/harvest-output modeling; the biological engine remains synthetic-only.
10. **Minimum next-season collection?** Scope/cultivar-area binding, area, production system, tree age, actual pruning and greenhouse/heating event dates, 10/50/90% bloom, indoor hourly temperature; add thinning, fruit-set, and color-break anchors as P1.

## Lifecycle, privacy and non-actions

2025–2026 remains `AUDIT_ONLY`; this audit performs no model/parameter/management-rule selection and does not reopen the consumed benchmark. Literature values remain priors, not production parameters. Live database content was not assessed. No model code, model parameters, training, refit, backtest, S3/S4 task, deployment, commit, or PR was performed. The source register includes only logical IDs, repository-relative references, hashes, scoped counts, and provenance; private row-level artifacts were not republished.
