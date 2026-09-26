# V0.8 Stage A decision freeze and R2C review closeout

## Decision

The frozen 2025–2026 benchmark does **not** support replacing the global pooled-yield reference baseline with the R2C shrinkage candidate. On the same full-39 cohort, R2C season-total WAPE is `0.3585864322241786026216929885`, versus `0.3429935582924604063039679242` for the global baseline: R2C is worse by `0.0155928739317181963177250643` (1.5592873931718196 percentage points). R2C is better than V0.8 R1, but that does not make it better than the baseline or production-validated.

Accordingly, the frozen decision is:

- `STAGE_A_DECISION=RETAIN_GLOBAL_POOLED_YIELD_AS_REFERENCE_BASELINE`
- `SHRINKAGE_LAMBDA_1_PROMOTED=false`
- `STAGE_A_RETROSPECTIVE_MODEL_SEARCH_CLOSED=true`
- `GLOBAL_POOLED_YIELD_PRODUCTION_APPROVED=false`
- `MODEL_PRODUCTION_READY=false`

This document records an evidence review and decision freeze. It is not an independent external approval, production approval, or authorization to start final V0.8 closeout.

## 1. Reviewed inputs and integrity

The review used the existing R2C report and machine evidence, the pinned R2B selection evidence, S8 canonical training evidence, and private manifests/replay outputs. No training, refit, benchmark replay, or prediction generation was run for this closeout.

| Input | SHA-256 |
|---|---|
| R2C report `docs/v0-8/r2c/frozen-shrinkage-model-and-2025-2026-benchmark-replay-r1.md` | `faf28e704c3a12e86b77ef96d6c1b15481571180248680a98fdde22e8e027541` |
| R2C evidence `docs/v0-8/evidence/r2c-frozen-shrinkage-model-and-benchmark-replay-r1.json` | `ece8cdd7fc5112c1ced831e8820fe99a68e5ed1194c029efd86b85469beba04e` |
| R2B selection evidence | `fdec3d80256293baa946ea218521cd492be9d919169f2046e63395c1f342ae69` |
| S8 evidence | `98213f283d7366f2bbdad7b5001e0ed60c842dabc4d2f030a727221116780b15` |
| S8 private artifact manifest | `6561ac984de2b3ac1a7ba86e8fee91f888b641478a19af67355e4dba8cc8216e` |
| R2C private artifact manifest | `d431875bde9a1028fca19d764a569c1ba0e7a792df911dcf3df5a0918ddff962` |
| R2C replay artifact manifest | `782a9ed0b9b4511987d1b25e10db4f4f8e410525d96987b542774cb0cd5b0973` |

Both R2C replay manifests and their listed artifacts were hash-checked; the two replay artifact sets are byte-identical. The S8 and R2B private manifest pins match the R2C evidence. Private per-Base/per-day files remain outside Git.

## 2. Training freeze and selection provenance

R2C uses the exact S8 canonical training dataset: 37 Base-season rows, 15 from 2023–2024 and 22 from 2024–2025, with zero blocked rows. Its dataset hash is `72363ec56dae682fba80ccf984a6fedb2c57425e1fbdcea8b8fca10aca0b5aba` and matches the S8 dataset.

The R2B temporal validation selected `SHRINKAGE_BASE_YIELD` with `lambda=1` on the 11-Base support-1 validation cohort (2023–2024 training, 2024–2025 validation); its best shrinkage WAPE was `0.302782961397559568419654371030744204094146089631995360973140`, and 2025–2026 was not used for selection. R2C froze that selection before benchmark scoring. Its 2025–2026 actuals were not used for fitting, lambda selection, hyperparameter selection, or candidate selection.

## 3. Global baseline recomputation

Using Decimal arithmetic on the frozen 37 training rows and the pinned pooled aggregation rule:

`sum(training season total kg) / sum(training area mu)`

the recomputed global yield is exactly `855.5593226284052977280068913535048993216 kg/mu`. It matches the frozen global baseline parameter. The R2C Base-mean policy is the arithmetic mean of eligible Base-season yields; shrinkage uses `w=n/(n+1)`.

## 4. R2C full-39 frozen benchmark

All three season-total comparators use the same 39 Base-season 2025–2026 cohort. WAPE is computed with the fixed cohort denominator. The benchmark role is `FROZEN_BENCHMARK_REPLAY`, not pristine or unseen OOT.

| Model | Season-total WAPE | MAE (kg) | Median APE | Bias (kg) |
|---|---:|---:|---:|---:|
| Global pooled-yield reference | 0.3429935582924604063039679242 | 422769.4831248205128205128205 | 0.3380278746096637845923721843 | -12706357.733154 |
| V0.8 R1 | 0.3925893218351959883557945280 | 483900.5883925897435897435897 | 0.3193194749526302384423707190 | -14809615.303231 |
| V0.8 R2C, shrinkage λ=1 | 0.3585864322241786026216929885 | 441989.0605575897435897435897 | 0.3371715636364878918367474622 | -13407443.589846 |

R2C minus global WAPE is `+0.0155928739317181963177250643`; R2C minus R1 is `-0.0340028896110173857341015395`. Thus `R2C_BEATS_GLOBAL_BASELINE=false` and `R2C_BEATS_R1=true`. Improvement over R1 does not establish baseline superiority.

## 5. Support-stratum review

The support cohort sums to 39: support 0 = 13, support 1 = 15, support 2 = 11.

| Training support | n | Global WAPE | R2C WAPE | Finding |
|---:|---:|---:|---:|---|
| 0 | 13 | 0.2819225473780435968592031667 | 0.2819225473780435968592031667 | Exact prediction parity |
| 1 | 15 | 0.3519370380584095063462341256 | 0.4386897050370896896751757952 | R2C worse |
| 2 | 11 | 0.3889622349960694394236272972 | 0.3211396082705310843948332075 | R2C better |

These are descriptive frozen-benchmark strata, not a license to choose a support-gated hybrid after seeing benchmark results. `SUPPORT_GATED_HYBRID_AUTHORIZED=false`.

## 6. Stage B and peak interpretation

The R1 and R2C Stage B shape hashes are both `7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e`; daily-share shape is unchanged and daily sums reconcile for all 39 Bases. R1→R2C peak-date changes = 0 and rolling-7 start-date changes = 0.

Full-39 daily WAPE is 0.5812862592207732948356517114 for global and 0.5871408241634609795631468040 for R2C. Single-day peak quantity WAPE is 0.3022025958947355416785549739 for global and 0.2954285405168558428809517302 for R2C; rolling-7 quantity WAPE is 0.2831406887616327543355090948 and 0.2770877685043859274695617846, respectively. Peak quantity changes are scale effects under unchanged Stage B shape; they do not establish a new timing/shape model improvement.

## 7. Common-30 V0.7 comparison

V0.7 covers only the common 30 Bases. On that same common-30 cohort, season-total WAPE is 0.3565703507552211518045530094 for V0.7, 0.3718680320214416088905949004 for global, 0.4295085823774648217328803026 for R1, and 0.3890780340614061982750043191 for R2C. These common-30 values are not compared directly with full-39 figures.

## 8. Frozen benchmark consumption rule

`BENCHMARK_2025_2026_CONSUMED=true` and its role is `FROZEN_MODEL_SELECTION_CONFIRMATION_BENCHMARK`. It remains available for audit, replay, reporting, and already-frozen comparisons only. It is not allowed for new model selection, lambda retuning, support-rule selection, or hybrid-policy selection. Future model work using these results must not describe 2025–2026 as unseen independent OOT.

## 9. Stage A decision

The R2B temporal validation signal is retained as a historical result, but its generalization was not confirmed by the frozen benchmark (`R2B_R2C_DIRECTION_CONSISTENT=false`). The λ=1 shrinkage research result is `FAILED_TO_BEAT_FROZEN_GLOBAL_BASELINE`; it is not promoted. Retain `GLOBAL_POOLED_YIELD` as the reference baseline and close retrospective Stage A model search. This reference status is not production approval.

No support-gated hybrid or other model candidate is authorized by this review.

## 10. Conditions to reopen future research

Stage A research may be reconsidered only after at least one of the following is available: (A) new future-season actuals not involved in current model selection; or (B) new authoritative historical productive-area and complete season-total evidence that materially expands the training cohort. This closeout defines no new model family, feature, or hyperparameter.

## 11. Production readiness and authorization

`GLOBAL_POOLED_YIELD_PRODUCTION_APPROVED=false`, `MODEL_PRODUCTION_READY=false`, and `PRISTINE_FUTURE_VALIDATION_PENDING=true`. This evidence package being prepared (`V0_8_FINAL_CLOSEOUT_READY=true`) means only that the Stage A decision record is machine-readable and reviewable. It does not execute or authorize the separate V0.8 final closeout. PR creation, Ready, Merge, deployment, tag, and release were not authorized or performed.

## 12. Reproducibility and integrity

The frozen R2C evidence reports deterministic training/replay, matching model/prediction/metric hashes, and byte-identical independent replay artifacts. This review independently recomputed the pooled yield, full-39 WAPE values and delta, support-stratum WAPEs, and Stage B shape hash from the pinned frozen inputs. The original R2C report/evidence and private artifacts were not modified. No model was trained or refit, no OOT replay was rerun, and no full CI was run for this documentation/evidence-only closeout.

## Status

Evidence verification completed; Stage A decision freeze artifact prepared. This is not an external reviewer approval. Await user review and explicit authorization before any next task.

Machine-readable evidence: [`stage-a-decision-freeze-and-r2c-review-closeout-r1.json`](../evidence/stage-a-decision-freeze-and-r2c-review-closeout-r1.json).
