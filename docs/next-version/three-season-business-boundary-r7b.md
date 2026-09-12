# R7B — corrected 2526 business-season validation

Task: `NEXT_VERSION_THREE_SEASON_COMPLETE_SEASON_BOUNDARY_CORRECTION_R7B`.
Continues Draft PR #616 from `ae1ad14963bee161b47fd661f8ed8adc0aa978be`.
Result: **NO_CLEAR_WINNER**. Formal validation completed for 2 total/composite farms
and 9 common-exact shape farms. B2 did not replicate as the unique macro winner.

## Explicit business authority

The user confirms the complete 2526 business season is **2025-07-22..2026-04-15**,
inclusive (268 calendar days). Post-April15 fruit is `TAIL_FRUIT_OUT_OF_SCOPE`.
It is not missing data, global UNKNOWN, or right censoring. Source right-truncated:
false; business season complete:true. Original XLS audit remains unchanged:
233171 rows through2026-04-16, SHA256
`fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a`.

`R7_PARTIAL_STATUS_CAUSE=INCORRECT_SEASON_BOUNDARY_INTERPRETATION`.
`R7B_BUSINESS_BOUNDARY_AUTHORITY=USER_CONFIRMED`.
R7's partial result remains immutable historical evidence; this document supersedes
its current business-window interpretation, not its source audit or execution facts.
2324/2425 dates, results, models and artifacts are not clipped or rewritten.

The explicit start/end replace the14-day boundary inference heuristic **only for2526**.
R6 source completeness, identity, area and active-span UNKNOWN rules remain.
40 global no-record dates inside the business window remain UNKNOWN, not zero;
none occurs inside these9 farms' positive active spans. Labels remain unknown on
those dates, and known-support daily scores use228 known days per farm. Business
total means the user-defined sum of recorded harvest within the window, not an
imputed biological total. No record on4/16 contributes to any formal metric.

## Frozen prediction application, no refit

R7 raw predictions are loaded from their SHA-bound private artifact. Each shape is
cropped to the confirmed business window and divided by its own raw in-window mass.
This normalization reads no actual quantities. All out-of-window raw prediction
mass is retained separately as diagnostic evidence, not a censoring trigger.

Global/Prior total predictions are unchanged. Multiplication by normalized business
shares preserves each predicted total within the existing Decimal rounding tolerance.
No fit, new coefficients, shift, weights, selector or replacement model is introduced.
Predictions are persisted before evaluation in separate processes.

Raw R7 prediction identity:
`f2c99c9c1b858ac091b0862214fe2d6e1670c95e8f19824239ef7b5c60839f88`.
R7B windowed prediction identity:
`52f417d9d3aa17560505049eec761d07eec0e81f567c8d5b057c09903668146e`.

This is NOT_BLIND retrospective re-evaluation under a newly user-confirmed business
boundary. It is not a new blind holdout or strict historical-PIT proof. Validation
labels do not enter model fitting, parameter selection or prediction normalization.

## Formal total results (2 farms, equal farm weighting)

| Farm | Mu | Actual business total kg | Actual kg/mu | Global total relative error | Prior total relative error |
| --- | ---: | ---: | ---: | ---: | ---: |
| 保山杨柳农场 |393.4|484802.056000|1232.338729|0.303534|0.074362|
| 建水南庄基地 |152.35|67562.420000|443.468461|0.935385|0.298547|

Global mean total relative error:0.619460; Prior:0.186454.
Global yield MAE:394.435134kg/mu; Prior:112.017628kg/mu.
Global kg-weighted WAPE diagnostic:0.380819; Prior:0.101783.
Prior total wins on both farms this origin. Yangliu's former Global-total preference
did not persist; Nanzhuang's Prior-total preference did. This remains limited evidence.

## Shape results and denominators

All9 strict pairs have exact business-window peak and seven-day comparisons.
No post-April15 prediction or label can cause RIGHT_CENSORED.

| Equal-farm metric | Global Ridge (9 farms) | Prior (9 farms) |
| --- | ---: | ---: |
| Mean peak-date error, days |66.222222|70.333333|
| Median peak-date error, days |26|19|
| Mean seven-day start shift, days |50.666667|54.666667|
| Known-support WAPE |0.869146|1.592997|

On the **same2 farms as Origin1**, Global/Prior mean peak errors are3.5/9.5days,
seven-day shifts3.0/2.5days, known-support WAPE0.633955/1.355556.
Prior's peak-date improvement direction has reversed on that matched cohort;
its seven-day shift retains a small improvement. Expanded9-farm scores must not
be compared to Origin1's2-farm macro as if the denominator were unchanged.

## End-to-end composites (2 farms)

| Composite | Mean total relative error | Daily MAE kg | Daily WAPE | Peak error days | Seven-day shift days |
| --- | ---: | ---: | ---: | ---: | ---: |
| A1 Global total × Global shape |0.619460|745.026247|0.802414|3.5|3.0|
| A2 Global total × Prior shape |0.619460|1337.576422|1.660259|9.5|2.5|
| B1 Prior total × Global shape |0.186454|702.642020|0.636074|3.5|3.0|
| B2 Prior total × Prior shape |0.186454|1489.043984|1.463770|9.5|2.5|

| Farm daily WAPE | A1 | A2 | B1 | B2 |
| --- | ---: | ---: | ---: | ---: |
| 保山杨柳农场 |0.554372|0.924152|0.561920|1.153323|
| 建水南庄基地 |1.050455|2.396366|0.710228|1.774218|

The existing R5 unique Pareto-dominance rule is unchanged. B1 has the lowest macro
daily WAPE, but B2 has a0.5-day lower mean seven-day shift. Neither dominates all
metrics, so macro and both farm winners are `NO_CLEAR_WINNER`. No post-hoc metric
weights or single-metric selector are introduced. Accordingly:

- `B2_REPLICATED_ACROSS_TWO_OUT_OF_TIME_ORIGINS=false`.
- `CROSS_SEASON_DIRECTION_STABLE=false`: on the same2-farm cohort, Prior total improves
  but Prior shape does not improve both timing metrics as it did in Origin1.
- `FARM_HETEROGENEITY_PERSISTS=NOT_ESTABLISHED`: two unidentified unique winners
  do not establish identical or different preferred composites. Metric tradeoffs remain.
- All8 composite rows pass mass balance; shapes do not alter their total model outputs.

Origin1 parity with R5 remains PASS. The business-window definition differs across
origins by explicit authorization; this limits causal/generalization claims.

## Reproduction, checks and immutable evidence

```bash
python -m scripts.run_business_boundary_r7b qualify --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7b-new-run
python -m scripts.run_business_boundary_r7b predict --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7b-new-run
python -m scripts.run_business_boundary_r7b evaluate --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7b-new-run
```

Actual append-only private output:
`/Users/charles/Documents/blueberry-area-yield-artifacts/three-season-r7b/`.
Manifest SHA256 `611507ab99c697ab72921bc478c598cee3315ca4ec103632d6ea158d320efbea`.
Includes policy, qualification, retained UNKNOWN labels, excluded-tail audit,
windowed frozen predictions, total/shape/composite metrics and comparison.
179 R1–R7 artifact files were hash-verified unchanged. No raw XLS or private daily
business rows are committed.

A preliminary local result classification treated two NO_CLEAR_WINNER outcomes as
heterogeneity=false. A regression test corrected this to NOT_ESTABLISHED; the earlier
run is retained in `three-season-r7b-pre-classification-fix`. Final replay has the
identical prediction identity and byte-identical total/shape/composite metric files.
No models or metric values were adjusted. Two local evaluations, zero model fits.

Local verification:161 tests passed (21 R7B tests plus R1–R7 regression), full-repository
Ruff and format checks PASS; Mypy backend/application plus runner PASS (428 source files).
CI must verify the new exact head including full-suite-canary; no workflow changes.

No Ready/Merge/Release, new research, weather, legacy TEST, production readiness or
business accuracy approval. Gate: `COORDINATOR_R7B_BUSINESS_SEASON_VALIDATION_REVIEW`.
