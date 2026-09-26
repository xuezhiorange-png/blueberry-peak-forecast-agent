# V0.8-S9: Scale/shape error decomposition and model diagnosis

## Executive answer

On S8's frozen 2025–2026 benchmark, the main reason V0.8 loses to the pooled-area baseline on season totals is the Stage-A total scale. Across all 39 Bases, V0.8's season-total WAPE is **39.2589%**, versus **34.2994%** for the baseline. The baseline and V0.8 daily-share vectors have identical hashes for all 39 Bases, so their daily-WAPE difference is also attributable to the season-total scale, not a different daily shape.

The shape itself is not error-free. With actual season totals substituted, V0.8's shape-only daily WAPE is **58.5159%** and mean normalized-shape L1 is **0.6112**. Scale-only daily WAPE is **39.2589%**; the observed combined V0.8 daily WAPE is **62.9213%**. These are separate absolute-error scenarios and **must not be added** or presented as percentages of a decomposed total.

1. Scale-only counterfactual daily WAPE: **0.3925893218351959883557945264**.
2. Shape-only counterfactual daily WAPE: **0.5851588537121282064362044141**.
3. V0.8 normalized shape L1: mean **0.6112067127342365552473070079**, median **0.5807231937399455191765908164**.
4. Baseline and V0.8 use the exact same frozen daily shape: **yes**, share hash `7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e` for both.
5. Holding actual total fixed does not move peak dates: single-day peak date MAE remains **30.5128 days**; rolling-7 start-date MAE remains **23.1538 days**. Shape-only peak-quantity WAPEs are **24.5064%** (single day) and **23.6015%** (rolling-7).
6. One-season support is a risk signal, not an estimable within-Base variance: its total WAPE is **54.1125%**. For the 11 Bases with two training seasons, median pairwise yield spread is **32.1743%**; two observations are not a reliable variance estimate.
7. OOT Bases average **0.9487** strict historical training seasons: 13 have zero, 15 have one, and 11 have two.
8. The comparative V0.8 regression is in total scale: the Stage-A season-total WAPE is worse than the frozen baseline, while their daily shape is exactly the same. Shape remains a separate source of absolute daily error.
9. Keep Stage B fixed as a controlled component for an R2 diagnosis: **yes**, not as a claim that its timing is production-ready. In the common-30 shape-only view, V0.8 WAPE is lower than V0.7 (59.6830% vs 68.4558%).
10. If a later R2 is authorized, prioritize replacing Stage A while holding Stage B constant. **No R2 work is performed here.**

Formal classification:

```ini
PRIMARY_FAILURE_MODE=SEASON_TOTAL_SCALE
RETAIN_CURRENT_DAILY_SHAPE_FOR_R2=true
REPLACE_SEASON_TOTAL_MODEL_FOR_R2=true
MODEL_PRODUCTION_READY=false
```

## Frozen scope and evidence boundary

S9 reads the S8 training dataset (37 Base-season rows), full OOT dataset (39 Base-season rows), frozen V0.8/baseline/V0.7 predictions, model comparison, metrics, and S8 artifact manifest. It does not fit a model, generate predictions, re-score a changed model, tune, search, or change any S8 input.

All 59 files in the S8 private manifest were re-hashed and matched. The manifest SHA is `6561ac984de2b3ac1a7ba86e8fee91f888b641478a19af67355e4dba8cc8216e`; the S8 repository evidence and configuration also matched their pins. The S8 headline metrics recomputed from the frozen prediction files passed numeric parity.

The cohorts remain separate:

- **Full 39:** V0.8 and the area-proportional baseline.
- **Common 30:** V0.7, V0.8, and baseline only. V0.7 is never treated as a 39-Base comparator.

S8 has already exposed 2025–2026 actuals. It is now a **FROZEN_EVALUATION_BENCHMARK**, not a pristine unseen OOT set. Tuning R2 on these results would invalidate any future claim that this same season is unseen independent OOT.

## Scale and shape counterfactuals

For each Base, S9 forms actual daily shares and V0.8 predicted daily shares from the frozen daily quantities. It constructs:

- **Scale-only:** V0.8's predicted season total × actual daily shares.
- **Shape-only:** actual season total × V0.8's predicted daily shares.
- **Observed combined:** the original S8 V0.8 daily prediction.

| Full-39 scenario | Daily WAPE | Daily MAE (kg) | Interpretation |
|---|---:|---:|---|
| Scale-only counterfactual | 0.3925893218351959883557945264 | 1,805.5992 | Only V0.8 season-total scale remains wrong |
| Shape-only counterfactual | 0.5851588537121282064362044141 | 2,691.2662 | Only V0.8 normalized timing profile remains wrong |
| Observed V0.8 combined | 0.6292132974633544144280801218 | 2,893.8816 | Both frozen Stage A and Stage B outputs |

Absolute-error metrics are nonlinear: `observed combined error` is not `scale-only error + shape-only error`. The scale-only WAPE is numerically equal to V0.8's season-total WAPE up to Decimal aggregation tolerance because each Base's counterfactual uses its actual normalized shape.

The baseline and V0.8 share the exact same frozen daily-share vectors across all 39 Bases. Their full-39 daily WAPEs are 0.5812862592207732948356517114 and 0.6292132974633544144280801218. Accordingly, that difference is from their different predicted total scales. This does **not** mean the shared shape is perfect: normalized-shape L1 mean is 0.6112, maximum cumulative-share deviation averages 0.2193, and the peak-date errors remain substantial.

On common 30, shape-only daily WAPE is 0.6845575633076192714034352008 for V0.7 and 0.5968296511225465721441994129 for V0.8. This is a common-cohort shape diagnostic, not a full-39 comparison.

## Frozen total results and direction

| Metric | Baseline full 39 | V0.8 full 39 | V0.8 − baseline |
|---|---:|---:|---:|
| Season-total WAPE | 0.3429935582924604063039679242 | 0.3925893218351959883557945280 | +0.0495957635427355820518266038 |
| Daily WAPE | 0.5812862592207732948356517114 | 0.6292132974633544144280801218 | +0.0479270382425811195924284104 |

On the common 30, V0.7 season-total WAPE is 0.3565703507552211518045530094 and V0.8 is 0.4295085823774648217328803026 (delta +0.0729382316222436699283272932). V0.7 daily WAPE is 0.7391211072773783730171586934 and V0.8 is 0.6375486158927208783266126936 (delta -0.1015724913846574946905459998). These common-30 numbers are not mixed with the full-39 baseline/V0.8 values above.

V0.8's signed full-39 season-total bias is **−14,809,615.303231 kg** (bias ratio **−30.8079%** of actual total); 28 Bases are underpredicted and 11 overpredicted.

## Shape timing and peak diagnostics

Normalized shape L1 is computed per Base from normalized daily quantities, then summarized across Bases. Mean L1 is 0.6112; median is 0.5807. Mean per-Base maximum cumulative-share deviation is 0.2193 (median 0.2149), indicating material accumulated timing drift.

With actual total fixed, shape-only peak-date MAE is unchanged from observed V0.8: 30.5128 days for the single-day peak and 23.1538 days for the rolling-7 start. Shape-only quantity WAPE is 0.2451 for the single-day peak and 0.2360 for rolling-7. Peak dates and rolling-7 values are re-derived from the corresponding daily counterfactual curves; rolling-7 uses seven consecutive calendar days and earliest-start tie-breaking.

## Stage-A support and yield diagnostics

Frozen V0.8 Stage A is `BASE_SPECIFIC_MEAN_HISTORICAL_YIELD_SCALED_BY_TARGET_AREA`; a Base with no training season falls back to pooled training quantity divided by pooled training area. The global pooled yield is **855.5593226284 kg/mu**.

| Strict historical seasons supporting OOT Base | Bases | Season-total WAPE | Season-total MAE (kg/Base) | Shape-only WAPE |
|---:|---:|---:|---:|---:|
| 0 (pooled fallback) | 13 | 0.2819225473780435968592031667 | 298,392.60 | 0.5246496300836539219418303363 |
| 1 | 15 | 0.5411249450720242022947563917 | 718,034.06 | 0.5828283565156711488108854561 |
| 2+ | 11 | 0.2930768913138939074595224946 | 383,864.38 | 0.6461659732100679921870742823 |

The one-season group has the highest season-total WAPE, but has no within-Base variance estimate from one observation. Among the 26 Bases with training history, the Base-specific yield deviation from the pooled yield has median +7.3077%, P25 −17.4407%, and P75 +33.5774%. Among 11 two-season Bases, median pairwise relative spread is 32.1743% (population CV 16.0871%). Those two-season statistics are descriptive pairs only, not reliable variance estimates.

Training-area tertile cut points are 637 mu and 1,017 mu, computed from the 37 training Base-season area rows. OOT area strata are small 15, medium 8, large 16. There are 37 area-in-range and 2 high-area extrapolation Bases. Four OOT actual yields lie outside the training yield range; all four remain included. The extrapolation subsets are diagnostics, not exclusion rules.

## Diagnosis and bounded next direction

The S8 comparison's **relative regression versus baseline is Stage-A scale**: the total WAPE is worse, and baseline/V0.8 normalized daily shape is hash-identical. Separately, the shape-only counterfactual has higher daily WAPE than scale-only and peak timing errors remain large; this is evidence of a shape limitation, not an additive share of total error.

For a later, separately authorized R2, the bounded first direction is to replace Stage A while keeping Stage B frozen as a control. At most two other candidate directions are recorded: training-only partial pooling/shrinkage, or training-only global yield plus a regularized Base effect. Any parameter selection must use training-only validation. S8/S9 OOT actuals may be used only as a frozen benchmark replay, not for hyperparameter tuning or a new unseen-OOT claim.

No Stage A/B change, training, refit, tuning, new prediction, backtest, PR, Ready, or Merge occurred in S9. No business accuracy threshold is defined; production readiness remains false.

## Artifacts and checks

Aggregate evidence: [S9 machine evidence](../evidence/s9-scale-shape-error-decomposition-and-model-diagnosis-r1.json). Private per-Base and per-day files are stored under the S9 private artifact root recorded in that evidence; they are not committed.

S9 completed 15 focused tests, Ruff, and Mypy. Full CI was not run because this task is local-only. The private S9 manifest hash is `02f69ce570182577fe6aebf8b59a90c98ff7cf6db81bf8af2833839a3d296ba9`; an independent replay in a second output directory produced byte-identical output and manifest hashes.
