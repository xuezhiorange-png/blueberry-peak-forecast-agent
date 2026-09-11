# Banna parameter observation materialization R3 — fail-closed result

TASK_ID=V0_3_BANNA_AUTHORIZED_PARAMETER_OBSERVATION_MATERIALIZATION_AND_TASK5_RECOVERY_R3

PR607 remains Draft. R2 identity correction is accepted and unchanged. This task
does not recover a lawful parameter source, implement a materializer, activate a
library or call Task5 again. The user's condition requires lawful observations
before another real Task5 call. R2's actual 422 remains historical API evidence.

## Preflight

Clean branch `acceptance/v0-3-banna-mengwang-dx-first-forecast-r1` at
`d746e526927977255302ccca33cc43753cac0585`; fresh origin/main is
`68ed5691b5ee1163cc18e1ad1208146e3ebf82f3`. PR607 is OPEN/DRAFT at the specified
head. Alembic has one head, `0032_s4_validation_budget_durable_persistence`.
No migration or production-code change is warranted before the semantic gate.

## What is defined, and what is not

The complete seven-row audit is in
[R3 evidence](evidence/banna-parameter-materialization-r3.json).
Each row binds business role, unit, actual schema range, required source fields,
denominator/anchor and an exact missing semantic contract. Common fields bind
grain, farm/subfarm, variety, season, PIT, aggregation and observation eligibility.

| Parameter | Established contract | Missing materialization authority |
|---|---|---|
| yield_kg_per_mu | 1–4 month expected yield per mu; stored >0; multiplied separately by marketable rate | Gross-yield numerator and historical planted-area/window mapping |
| marketable_rate | Independent effective marketable factor; ratio 0..1 | Grading stage, numerator, denominator and exclusions |
| first_harvest_offset_days | Day-valued first-harvest component | First-event criterion and zero-date/anchor |
| maturity_peak_offset_days | Day-valued maturity peak component | Peak selection, anchor and approved proxy equivalence |
| maturity_width_days | Positive day-valued width component | Width statistic and series support/window |
| maturity_skewness | Scalar maturity shape component | Moment versus distribution parameter, normalization and proxy equivalence |
| harvest_realization_rate | Ratio 0..1; reserved in Task013 logical mapping | Realized-harvest numerator, supply/backlog denominator and window |

These gaps are not new definitions. In particular, we do not choose standard
deviation as width, standardized third moment as skewness, January 1 as an offset
anchor, or receipt kg / 736 as yield. Product equations do not uniquely determine
all seven independent parameters. The user's current area is not historical area
authority. Ordinary users are not asked to supply these seven model parameters.

Task5's existing aggregation takes already-authorized scalar observations and
computes weighted P50/P10/P90 using configured fallback levels. It does not define
how to manufacture those scalars from receipts. `docs/13_natural_maturity_curve.md`
explicitly labels Task8's series as `smoothed_arrival_proxy_for_natural_maturity`,
not physiological truth; it supplies no Task5 width/skewness extraction contract.
The historical Task5 importer at commit `84b004f` also imports formed observations,
not raw harvest semantics.

## Source search and live read-only evidence

Search was limited to this repository, the previously authorized V0.2 working
copy data directory, accepted R1/R2 evidence and the existing acceptance store.
Current read-only PostgreSQL counts: library versions=0, observations=0,
farm-season-variety plans=0, maturity artifacts=0. No other DB was discovered or
created. No raw receipt quantities, VALIDATION or TEST were opened in R3.

R2's verified source/template inventory remains linked by hash. Historical receipt
facts and the coordinator's area/analysis facts are real, but not authorized scalar
parameter observations. Template/default/fixture classes remain distinct. No
recoverable observation source was found in the checked scope; this is not a
claim of global absence. There is no source visibility timestamp to invent.

## Persistence and determinism findings

Existing schema already has scalar value/unit, scope IDs, source names/versions,
row/file hashes, availability and validity dates. It has no dedicated structured
derivation-input payload field. This alone does not authorize a migration.
The existing CSV importer hashes sorted row payloads but sets library effective
date using `date.today()` and writes subfarm_id=None. A future historical builder
cannot simply claim those choices fulfill replayable scoped materialization.
No change is made until a lawful source-to-parameter definition exists.

The exact observation PIT implementation prioritizes explicit available_at:
future availability is excluded even if the season has ended. Only if available_at
is absent is season_end_date used. This is retained, not weakened into a loose OR.

## Verification boundary

New regression checks cover all seven no-authority cases returning unavailable
with null values and no source IDs, plus source-hash-bound R3 consistency.
Existing tests cover PIT, deterministic hashes, same-farm/no-geo selection,
cross-farm rejection, library import and traceable Task5 results on test fixtures.
Those fixtures do not become acceptance authority.

Positive real-source materialization and real Task5 recovery tests are **not
applicable/executed** because no lawful materializer can yet be implemented.
Synthetic inference/hash tests are not reported as successful real materialization.
Local skipped PostgreSQL tests and exact-head CI are reported separately.

INTERNAL_DATA_PRODUCT_BLOCKER=AUTHORIZED_PARAMETER_OBSERVATION_MATERIALIZATION_NOT_AVAILABLE

FIRST_MATERIALIZATION_GATE=SOURCE_TO_PARAMETER_SEMANTIC_CONTRACT_NOT_ESTABLISHED

MISSING_EXTERNAL_BUSINESS_FACTS=NONE

No Task8/9, Forecast, retraining, S4 reopening, validation scoring, budget use or
TEST access. R1/R2 evidence is preserved. Keep Draft; no Ready/Merge.

FINAL_STOP_GATE=COORDINATOR_BANNA_PARAMETER_SOURCE_SEMANTIC_CONTRACT_REVIEW
