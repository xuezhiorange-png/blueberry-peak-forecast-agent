# R7: second rolling-origin validation (partial coverage)

Task: `NEXT_VERSION_THREE_SEASON_ROLLING_OUT_OF_TIME_VALIDATION_R7`.
Base: PR #615 head `179f4b8a566312f05cff783594d7353b60ecdcfa`, stacked Draft.
Verdict: **THREE_SEASON_PARTIAL_VALIDATION**. No model selection/tuning/deployment.

## Source authority and qualification

The original Office XLS `原果入库汇总表.xls` was downloaded from Drive file
`1L1WlljuU04dvkS8Owd8ekl9Vi1ZunlRa`. MIME `application/vnd.ms-excel`,
28,668,416 bytes, CDFV2 Excel bytes, no conversion. SHA256:
`fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a`.

Four pagination sheets contain 65,535 / 65,535 / 65,535 / 36,566 records,
233,171 total. All have 时间、链路、农场、分场、品种、果径、入库公斤数.
Dates: **2025-07-22 through 2026-04-16**, 84 farm labels, 192 subfarm labels,
20 variety labels. Invalid dates, null quantities, negative quantities and exact
seven-field duplicates: all zero. This is the same receipt-ledger schema, not the
legacy sealed evaluation partition. No legacy TEST file was opened.

Arrival equals harvest. User-authorized complete-export semantics are reused:
source-active farm absence is recorded zero; global no-record days remain UNKNOWN.
Complete export does **not** mean complete agricultural season. The R6 14-day
boundary rule and active-span UNKNOWN rejection remain unchanged.

Only the previously user-authorized `建水南庄农场 → 建水南庄基地` alias is applied.
Original labels and bytes are retained. No other fuzzy matching. Exact matches:49;
with this authorized alias:50. 华兴 is not an exact name in this source; no guessed
identity/area substitution is performed.

Global shape training uses all 18 strictly qualified **2425** historical farms,
not only farms matching the new export. Nine have target identities and receive
predictions. Only 澜沧上允一场 also passes strict 2526 qualification. Its two model
peaks and seven-day windows are RIGHT_CENSORED; common exact denominator:0.
Its known-support WAPE remains reportable: Ridge 1.9942622804, Prior 2.0;
unknown prediction mass: Ridge 0.4782488842, Prior 0.6304163839.
These are not exact peak comparisons or biological full-season validation.

Yangliu393.4 and Nanzhuang152.35 mu remain BUSINESS_CONFIRMED across seasons.
Both 2526 farm-seasons are RIGHT_CENSORED, so total and strict composite validation
denominators are **0**, independently of their valid area authority.

## Frozen rules and execution ordering

Origin1 remains 2324→2425. R5's eight per-farm composite metric rows agree exactly
with R6 (totals, daily MAE/WAPE, relative errors, peak/7-day shifts, mass balance).
No origin1 tuning/refitting was performed. Origin1 limited macro best remains B2.

Origin2 uses2425→2526. Old fit entrypoints retain their old season restrictions;
explicit R7 wrappers reuse the unchanged numerical implementations:

- Global total: median of two eligible2425 farm yields.
- Prior total: each farm's2425 yield; no silent unknown-farm fallback.
- Global shape: all18 eligible2425 farm curves, equal-farm fitting weights,
  StandardScaler + Ridge alpha10, SVD, two annual harmonics.
- Prior shape: same farm2425 known-recorded shares, frozen July–June position mapping;
  prediction-only interpolation does not change unknown history labels.
- Full-year predictions are nonnegative and normalized. A1/A2/B1/B2 definitions unchanged.

Actual separate-process order: qualify → build past-data components → load/predict
→ save prediction hash → evaluate. The predict process does not open validation
labels or fit models. All training positions are in2425; code and input hashes are
sealed. The source audit necessarily inspected2526 records before prediction for
qualification, so this is **NOT_BLIND**, not strict historical-availability/PIT proof.
No2526 labels are passed to fit, features, total calibration or prediction alignment.

Prediction hash: `f2c99c9c1b858ac091b0862214fe2d6e1670c95e8f19824239ef7b5c60839f88`.
An initial qualification-only attempt without the existing Nanzhuang alias is
retained separately; no prediction/scoring occurred in that attempt. Final qualification
was frozen after the authorized identity binding, before all model building/scoring.

## Partial-window diagnostics (not full-season scores)

The following WAPE uses known2526 label days, without modifying predictions or
renormalizing daily kg. Full-season total errors are null for all these rows.

| Farm | A1 | A2 | B1 | B2 |
| --- | ---: | ---: | ---: | ---: |
| 保山杨柳农场 | 0.713101 | 0.668005 | 0.640808 | 0.683908 |
| 建水南庄基地 | 0.668758 | 1.227269 | 0.706049 | 0.990714 |

Predicted full-season totals (kg): Yangliu Global337648.204104 / Prior448751.250965;
Nanzhuang Global130759.287990 / Prior87732.980951. These use2425 history, not2526
actual totals. Each total is conserved across both shape variants and daily rounding.

Yangliu Prior's predicted peak lies on known support (1 day from the observed maximum),
but its seven-day peak crosses coverage. This is an observed-support diagnostic,
not evidence of exact full-season peak truth. All other composite peaks/windows are
right-censored. No new preferred production combination is selected.

## Three-season conclusion and limits

Prior total better in2526? **Not computable** for full-season totals.
Prior shape timing better? **Not computable on a common exact set**.
B2 macro best replicated? **Not computable**. Yangliu/Nanzhuang prior preferences and
persistent heterogeneity cannot be confirmed from truncated-season daily diagnostics.
Direction is neither established stable nor established reversed.
Total and shape research-reopening thresholds (3 qualifying farms) are not reached.

No weather, future plan, new algorithm, parameter search, legacy S4 budget use,
legacy TEST access, baseline replacement or business accuracy approval.

## Reproduction and artifacts

Run from repository root with installed project dependencies:

```bash
python -m scripts.run_three_season_r7 qualify --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7-new-run --source /Users/charles/Documents/blueberry-area-yield-artifacts/source-25-26-r7/原果入库汇总表.xls
python -m scripts.run_three_season_r7 build --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7-new-run
python -m scripts.run_three_season_r7 predict --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7-new-run
python -m scripts.run_three_season_r7 evaluate --root /Users/charles/Documents/blueberry-area-yield-artifacts --output /private/tmp/r7-new-run
```

Use a new output directory; phases fail rather than overwrite. Actual private output:
`/Users/charles/Documents/blueberry-area-yield-artifacts/three-season-r7/`.
Manifest SHA256 `44d9ff2f7fa88dd9c326aaa2c7ed3e736b9b4637df3633c3db69392625596581`.
Includes original-source audit/label inventories, all qualification rows, frozen
training input/models, predictions-before-scoring, per-farm diagnostic metrics,
three-season comparison, code/input hashes. All151 prior R1–R6 files unchanged.
Raw XLS, private farm rows and model files are not committed.

Local:140 area-yield tests (R1–R7) passed; Ruff/format passed; Mypy passed on affected
modules/runner. CI must run against final head, including required full-suite-canary.
Final gate: `COORDINATOR_THREE_SEASON_R7_FINAL_VALIDATION_REVIEW`.
