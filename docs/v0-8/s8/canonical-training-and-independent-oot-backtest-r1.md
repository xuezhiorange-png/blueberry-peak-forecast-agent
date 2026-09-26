# V0.8-S8 Canonical Training and Independent OOT Backtest

## Executive result

The frozen training cohort contained 37 eligible Base-season rows (15 from
2023–2024 and 22 from 2024–2025; 26 unique Bases). None of the 41 blocked
training rows was included. All 39 eligible 2025–2026 Base-seasons passed the
OOT preflight, including a complete 268-day curve and season-total, single-day
peak, and rolling-7 truth. Training and OOT keys were disjoint.

On all 39 OOT Bases, V0.8 season-total WAPE was **39.26%** and daily WAPE was
**62.92%**. The frozen pooled-area baseline scored **34.30%** season-total WAPE
and **58.13%** daily WAPE on the same 39 Bases. Thus V0.8 was worse than the
baseline on both pooled measures. The frozen V0.7 model supports only 30 of the
39 OOT Bases under its immediate-prior/no-fallback policy. On that same
30-Base common cohort, V0.8 had worse season-total WAPE than V0.7 (42.95% vs
35.66%), but lower daily WAPE (63.75% vs 73.91%) and lower peak/rolling-7
quantity WAPE. These are mixed model results, not an overall win.

The run is a completed experiment, **not production validation or approval**.
No business acceptance threshold is defined; readiness remains
`BACKTEST_COMPLETED_NOT_PRODUCTION_READY`.

## Frozen experiment scope and authority

The experiment used the S4 three-season area authority, S6 no-record-zero and
complete-season-quantity authority, and S7 strict training eligibility and
identity-closure output. Their pinned hashes, plus the frozen V0.7 config,
artifact, and registry hashes, are recorded in the machine evidence. S7 did not
release additional training rows; S8 materialized exactly the existing 37
strictly eligible rows and kept all blocked rows out.

The input split was frozen before scoring:

- Training: 2023–2024 and 2024–2025, 37 Base-season rows.
- Independent OOT: 2025–2026, 39 Base-season rows.
- Train/OOT Base-season key overlap: zero.
- OOT labels were not read for fitting, normalization, calibration, or tuning.
  Model predictions were produced twice, sealed and hash-checked before the
  scoring phase loaded OOT actuals.
- No weather, future production plan, feature search, hyperparameter search,
  cross-validation, or randomized fitting was used.

All 39 OOT areas were in the V0.8 and baseline cohort. Two OOT areas were above
the training-area range (216–2,548 mu); 37 were in range. Four OOT yields were
outside the training-yield range (29.8177–1,745.2325 kg/mu); these are
diagnostic flags only and none was removed.

## Frozen model and comparators

V0.8 is `V0_8_AREA_SCALED_BASE_YIELD_AND_SHARED_DAILY_SHAPE_R1`, a deterministic
two-stage model:

1. Season total = target area × arithmetic mean eligible historical yield for
   that Base. A Base unseen in training uses pooled strict-training quantity
   divided by pooled strict-training area.
2. The daily curve uses the equal-weight mean of strict-training normalized
   daily shares by calendar month/day, filtered to the frozen 2025–2026
   business window and renormalized to sum to one. Daily quantities are scaled
   from the predicted season total; the final day absorbs the defined rounding
   residual. Single-day and rolling-7 peaks are derived from that same curve.

The area-proportional baseline uses pooled strict-training yield × target area
and the same frozen training daily shape for daily comparison. V0.7 uses its
frozen model/config and immediate-prior-season-only, fail-closed behavior; it
is not refit in this task. Its separately rounded daily rows and season-total
predictions differ in sum by at most 0.000012 kg/Base in the common cohort; the
S8 mass-balance gate is applied to V0.8 and the area baseline, not retroactively
to the frozen V0.7 artifact.

V0.8's model architecture differs from V0.7. Therefore the V0.8/V0.7 delta is
not attributable solely to the expanded canonical training data.

## Season-total results

WAPE is pooled absolute error divided by pooled actual quantity; MAE is over the
fixed Base-season cohort. Bias is predicted minus actual.

| Cohort | Model | n | WAPE | MAE (kg/Base-season) | Median APE | Mean bias (kg/Base-season) |
|---|---|---:|---:|---:|---:|---:|
| Full OOT | Area-proportional baseline | 39 | 0.3429935583 | 422,769.4831 | 0.3380278746 | -325,804.0444 |
| Full OOT | V0.8 | 39 | 0.3925893218 | 483,900.5884 | 0.3193194750 | -379,733.7257 |
| Common cohort | Area-proportional baseline | 30 | 0.3718680320 | 490,661.7711 | 0.3693304909 | -435,487.4425 |
| Common cohort | Frozen V0.7 | 30 | 0.3565703508 | 470,477.2252 | 0.3971619901 | -299,759.7262 |
| Common cohort | V0.8 | 30 | 0.4295085824 | 566,715.6722 | 0.3359567463 | -502,179.4924 |

On the full 39, actual quantity totaled 48,070,902.334 kg; V0.8 predicted
33,261,287.030769 kg and the baseline predicted 35,364,544.600846 kg. V0.8
minus baseline WAPE was +0.0495957635 on all 39. On the common 30, V0.8 minus
V0.7 WAPE was +0.0729382316 and V0.8 minus baseline was +0.0576405504.

## Daily curve, peak, and rolling-7 results

Daily scores use all 268 business-window dates per eligible Base and preserve
zero-actual days; daily WAPE's denominator is pooled actual kg. Peak and
rolling-7 metrics are computed from each model's daily curve. Rolling-7 means
the maximum sum over seven consecutive calendar days, with earliest start on
ties.

| Cohort | Model | Daily WAPE | Daily MAE (kg/day) | Single-day peak quantity WAPE | Peak-date MAE (days) | Rolling-7 quantity WAPE | Rolling-7 start MAE (days) |
|---|---|---:|---:|---:|---:|---:|---:|
| Full 39 | Baseline | 0.5812862592 | 2,673.4553 | 0.3022025959 | 30.5128 | 0.2831406888 | 23.1538 |
| Full 39 | V0.8 | 0.6292132975 | 2,893.8816 | 0.3404074581 | 30.5128 | 0.3348116784 | 23.1538 |
| Common 30 | Baseline | 0.5783462536 | 2,847.3871 | 0.3126617824 | 31.5000 | 0.2873476075 | 23.7333 |
| Common 30 | Frozen V0.7 | 0.7391211073 | 3,638.9341 | 0.4523239715 | 33.1667 | 0.4444987004 | 24.4667 |
| Common 30 | V0.8 | 0.6375486159 | 3,138.8596 | 0.3644422982 | 31.5000 | 0.3561760399 | 23.7333 |

On the common 30, V0.8 minus V0.7 deltas were: season-total WAPE +0.0729382,
daily WAPE -0.1015725, peak-quantity WAPE -0.0878817, peak-date MAE
-1.6667 days, rolling-7 quantity WAPE -0.0883227, and rolling-7 start-date MAE
-0.7333 days. Negative is lower error. Against the baseline on all 39, V0.8
had higher daily WAPE by +0.0479270 and higher rolling-7 quantity WAPE by
+0.0516710; single-day peak-date and rolling-7 start-date MAE were unchanged.

V0.8 per-Base daily WAPE on the full cohort had median 0.6190, P25 0.5436,
P75 0.7064, and maximum 1.5629. Per-Base season-total APE had median 0.3193,
P25 0.1392, P75 0.5225, and maximum 1.3738. The five largest V0.8
season-total absolute errors were 2,182,930.155; 1,780,675.366; 1,709,579.538;
1,686,091.281; and 1,113,398.865 kg. The five largest per-Base daily WAPEs
were 1.5629, 1.5512, 0.9756, 0.9534, and 0.9116. The five largest peak-date
errors were 185, 162, 130, 111, and 81 days; the five largest rolling-7
quantity absolute errors were 280,339.751; 161,223.970; 113,346.396;
113,182.035; and 93,757.670 kg. Base identities and row-level diagnostics
remain in the private comparison artifact.

## Determinism, leakage, and artifact integrity

Two independent model fits produced byte-identical model artifacts; two
prediction replays produced identical prediction hashes; two scoring replays
produced identical metric hashes. The prediction seal was verified before OOT
truth was read. The private artifact manifest covers 59 files and currently
verifies with zero hash mismatches. The private run directory is mode `0700`
and its files are mode `0600`. Private row-level data was not added to Git.

Focused tests, Ruff, and Mypy are run locally. Full repository CI is not run
because this task remains local-only with no PR. CI status is not a model
acceptance signal.

## Conclusion and boundary

The OOT comparison does not support an overall V0.8 improvement claim: on the
full 39, V0.8 is worse than the area-proportional baseline in season-total and
daily pooled WAPE; on the common 30, it is worse than V0.7 in season-total
WAPE, while daily and peak/rolling-7 measures are lower. This mixed evidence,
the 37-row/26-Base training cohort, the nine-Base V0.7 support gap, and the
absence of a frozen business acceptance threshold rule out a production-ready
claim. The experiment does not authorize model promotion, deployment, release,
or a future-version implementation.

Machine-readable metrics, authority pins, run hashes, and non-action flags are
in [`s8-canonical-training-and-independent-oot-backtest-r1.json`](../evidence/s8-canonical-training-and-independent-oot-backtest-r1.json).
