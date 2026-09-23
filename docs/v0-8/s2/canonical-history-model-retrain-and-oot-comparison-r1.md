# V0.8-S2 Canonical History Model Comparison

## Quantity-completeness correction

**Correction result: `PASS_WITH_INSUFFICIENT_EVIDENCE`.** The previous exploratory daily comparison is invalidated. A `KNOWN_MAPPED_SUBTOTAL` is scoreable only when its completeness is `COMPLETE_MAPPED_MEMBERS`; `PARTIAL_KNOWN_SUBTOTAL` is retained for audit but excluded from daily metrics and season-total training. `UNKNOWN` stays null and is never treated as zero. Confirmed zero is scoreable only with S1-authorized completeness `COMPLETE_SOURCE_ROWS_ZERO` or `AUTHORIZED_ZERO`.

| Question | Corrected conclusion | Evidence |
| --- | --- | --- |
| Season total more accurate? | **INSUFFICIENT_EVIDENCE** | No eligible prior-season complete season-total training authority exists; no V0.8 candidate was trained. The prior V0.8 total prediction is superseded and nonauthoritative. |
| Daily curve more accurate? | **INSUFFICIENT_EVIDENCE** | On 7,976 complete daily actual rows, baseline WAPE is `0.5940263968383673651008089173`, V0.7 WAPE is `0.7195790799353937948127680318`; V0.8 has no trained candidate and its WAPE is not computable. |
| Single-day peak more accurate? | **INSUFFICIENT_EVIDENCE** | No frozen peak authority qualifies a common OOT Base-season. |
| Rolling 7-day peak more accurate? | **INSUFFICIENT_EVIDENCE** | No frozen rolling-7 authority qualifies a common OOT Base-season. |

`PREVIOUS_S2_METRICS_SUPERSEDED_BY_QUANTITY_COMPLETENESS_CORRECTION=true` and `PREVIOUS_EXPLORATORY_DAILY_WAPE_COMPARISON_INVALIDATED=true`. The earlier daily improvement claim must not be used. The previous V0.8 predicted total `223540.014148 kg` is `SUPERSEDED_NONAUTHORITATIVE_PRIOR_EXPLORATORY_RESULT`; it is not a corrected-model comparison.

## Frozen scope and authority

- Task: `V0_8_S2_CANONICAL_HISTORY_MODEL_RETRAIN_AND_OOT_COMPARISON_R1`; correction: `V0_8_S2_QUANTITY_COMPLETENESS_TRAINING_AND_SCORING_CORRECTION_R1`.
- Base: `91d9d8a04be05576fc8c3ae8fec0fbad899057d8`.
- S1 authority: `CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1`; the verified S1 evidence, config, private manifest, identity authority, daily ledger and quality ledger hashes are recorded in [machine evidence](../evidence/s2-canonical-history-model-retrain-and-oot-comparison-r1.json).
- Raw/mapped/unresolved/excluded totals remain `122983150.913 / 109010615.352 / 10573929.816 / 3398605.745 kg`; 44 unresolved source-farm labels remain excluded.
- V0.7 model configuration and frozen model artifacts were not changed. Model architecture is unchanged; no weather was used. No identity or area authority was changed.
- S1 `REFERENCE_AREA_ONLY` remains exploratory, never historical actual productive area. Strict area training remains infeasible with 0 eligible training Base-seasons.
- Folds remain A: train `2023-2024`, OOT `2024-2025`; B: train `2023-2024, 2024-2025`, OOT `2025-2026`.

## Completeness-qualified daily scoring

The private common OOT artifact preserves every candidate row and labels it `SCORED_COMPLETE`, `EXCLUDED_PARTIAL` or `EXCLUDED_UNKNOWN`, with an explicit reason. No row was deleted to inflate coverage.

| Fold | Candidate daily rows | Complete scored | Partial subtotal excluded | Unknown excluded |
| --- | ---: | ---: | ---: | ---: |
| A | 3,757 | 2,291 | 483 | 983 |
| B | 8,040 | 5,685 | 1,235 | 1,120 |
| Combined | 11,797 | 7,976 | 1,718 | 2,103 |

The complete-day evaluation dataset SHA-256 is `f5dc421b4346514fef0e5f9fded42cd56f69e0cdf8a3807dca86e026d016f080`; full candidate OOT dataset SHA-256 is `6ce3dc420fcdf96f586d6f1fb395dd35eb6b21eb7fe0d01bb8fae0bdeebca5f1`.

Corrected pooled daily metrics (negative bias means underprediction; bias is predicted minus actual):

| Scope | Model | Complete-day WAPE | MAE (kg/day) | Bias (kg/day) | Scored | Partial excluded | Unknown excluded |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fold A | Frozen area-normalized baseline | 0.6659547393760524178926438681 | 2624.513272501361257942121344 | -554.3973589275571286737669140 | 2,291 | 483 | 983 |
| Fold A | V0.7 replay | 0.7469702528745901004938638113 | 2943.793664821475338280226975 | -422.1765772160628546486250546 | 2,291 | 483 | 983 |
| Fold A | V0.8 candidate | NOT_COMPUTABLE_NO_COMPLETE_SEASON_TOTAL_TRAINING_AUTHORITY | NOT_COMPUTABLE | NOT_COMPUTABLE | 0 | 483 | 983 |
| Fold B | Frozen area-normalized baseline | 0.5724112744748603264376977376 | 3025.166017728942921198065084 | -1615.113769121570568617941953 | 5,685 | 1,235 | 1,120 |
| Fold B | V0.7 replay | 0.7113477828712286637245014624 | 3759.438773289533861037818821 | -1230.306457566051011433597186 | 5,685 | 1,235 | 1,120 |
| Fold B | V0.8 candidate | NOT_COMPUTABLE_NO_COMPLETE_SEASON_TOTAL_TRAINING_AUTHORITY | NOT_COMPUTABLE | NOT_COMPUTABLE | 0 | 1,235 | 1,120 |
| Combined | Frozen area-normalized baseline | 0.5940263968383673651008089173 | 2910.083841285062581363640923 | -1310.437077076123628934879639 | 7,976 | 1,718 | 2,103 |
| Combined | V0.7 replay | 0.7195790799353937948127680318 | 3525.155555699222668004012036 | -998.1818893762537612838515547 | 7,976 | 1,718 | 2,103 |
| Combined | V0.8 candidate | NOT_COMPUTABLE_NO_COMPLETE_SEASON_TOTAL_TRAINING_AUTHORITY | NOT_COMPUTABLE | NOT_COMPUTABLE | 0 | 1,718 | 2,103 |

These figures do not establish V0.8 daily improvement: V0.8 has no valid prediction set to compare. `DAILY_CURVE_IMPROVED_STRICT=INSUFFICIENT_EVIDENCE`; `DAILY_CURVE_IMPROVED_EXPLORATORY=INSUFFICIENT_EVIDENCE`.

## Training eligibility and season totals

An eligible V0.8 season-yield training target now requires S1 quality authority `business_total_coverage_status=BUSINESS_TOTAL_AUTHORITY_ELIGIBLE` and `season_total_complete=true`. Complete daily quantities may support daily rows, but summing them cannot manufacture a complete business-season label. Partial subtotals are excluded from training rows.

The immediate-prior seasons have no complete season-total training Base-seasons: Fold A prior `2023-2024` = 0; Fold B prior `2024-2025` = 0. Therefore:

- `STRICT_AREA_MODEL_TRAINING_FEASIBLE=false`; strict training Base-season count = 0.
- `EXPLORATORY_TOTAL_MODEL_TRAINING_FEASIBLE=false`; eligible complete training Base-season count = 0.
- `V0.8 candidate trained=false`; fold artifacts and candidate predictions were not generated. Season-total and daily V0.8 comparisons are not computable. No older-season fallback, daily subtotal aggregation, zero-fill, interpolation or quantity backfill was used.

One 2025-2026 OOT Base-season remains authorized for evaluating V0.7: actual `484802.056 kg`, V0.7 prediction `448751.251004 kg`, absolute error `36050.804996 kg`, WAPE `0.07436190616320323526020689978`. Baseline WAPE on that same total is `0.2464007334629170554920253886`. This OOT total is not training authority for either fold.

Single-day peak and rolling-7 quantity/date metrics remain `NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY` and `NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY`; partial/unknown daily values were not used to synthesize a peak window.

## Reproducibility and boundaries

Two independent replays in the new private root produced identical `comparison-summary.json` SHA-256 `c9abd5164dd2f7690de54ace4769eb35e40f3f3b870972b3ecad9ac986bc313d` and private artifact manifest SHA-256 `087db9d41fc1271adb36eab9374a37697edfd883674f0939c0cee3a8c793d843`. The complete-day dataset hash also matched. Row-level CSVs remain in controlled private storage and are not committed.

**Corrected result:** `PASS_WITH_INSUFFICIENT_EVIDENCE`. This correction fixes quantity-completeness eligibility; it does not revise the identity authority, area authority, V0.7 model, model architecture, weather inputs, or production promotion state.
