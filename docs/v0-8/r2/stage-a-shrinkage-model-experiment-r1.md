# V0.8-R2 Stage-A shrinkage experiment

## Executive result

1. **Training-only CV selected:** `GLOBAL_POOLED_YIELD` (no hyperparameter), from 26 grouped leave-one-Base-out folds.
2. **Selection evidence:** global yield and all six shrinkage lambdas tied at CV season-total WAPE `0.3938284667691153331125703063`. A held-out Base has zero training support in every LOBO validation fold, so shrinkage falls back to global yield and this CV cannot identify a useful lambda. The pre-frozen tie-break therefore selected the simpler global model. The best regularized-Base-effect candidate (alpha `0.1`) scored `0.4406852848738388313683221368`.
3. **Full-39 baseline season-total WAPE:** `0.3429935582924604063039679242`.
4. **Full-39 V0.8 R1 season-total WAPE:** `0.3925893218351959883557945280`.
5. **Full-39 selected R2 season-total WAPE:** `0.3429935582924604063039679242`.
6. **Did R2 beat the global baseline?** No. It selected that global-yield candidate and reproduces the baseline exactly on the frozen benchmark (`delta=0`).
7. **Bias:** R2 is `-12,706,357.733154 kg`, compared with R1 `-14,809,615.303231 kg`; underprediction is smaller than R1 by `2,103,257.570077 kg`, but R2 bias equals the baseline.
8. **Training-support strata:** R2 WAPE is `0.2819225473780435968592031667` for support 0 (13 Bases), `0.3519370380584095063462341256` for support 1 (15), and `0.3889622349960694394236272972` for support 2+ (11). The first two match the baseline; R1 was better than baseline in support 2+.
9. **Daily WAPE:** R2 is `0.5812862592207732948356517114`, equal to the baseline and lower than R1 (`0.6292132974633544144280801218`).
10. **Peak dates:** unchanged versus R1 on all 39 Bases: single-day peak and rolling-7 start-date changed counts are both zero.
11. **Worth promoting R2?** No production promotion is supported. R2 reaches baseline parity but does not beat it, and no business acceptance threshold is defined.
12. **Next evidence boundary:** 2025–2026 is a frozen benchmark, not pristine OOT. Future R2 evaluation needs a genuinely new, untouched season.

## Frozen scope and inputs

The experiment reused the exact S8 37-row training cohort (`15` rows from 2023–2024 and `22` from 2024–2025), with zero blocked rows. Training dataset SHA-256 is `72363ec56dae682fba80ccf984a6fedb2c57425e1fbdcea8b8fca10aca0b5aba`. The complete frozen benchmark has 39 Base-season rows from 2025–2026; V0.7 is compared only on the common 30.

All 59 S8-manifested artifacts were re-hashed successfully. The S8 private manifest SHA-256 is `6561ac984de2b3ac1a7ba86e8fee91f888b641478a19af67355e4dba8cc8216e`; the S8 evidence/config, R1 model artifact, S9 evidence, and S9 private manifest hashes are recorded in the machine evidence. No area, quantity, identity, or model-data authority was changed.

The selected model was trained and its model hash sealed before the benchmark actuals were opened. The 2025–2026 actuals were used only to score the frozen candidate; they were not used for CV, model selection, hyperparameter tuning, or fitting. Candidate C and the shrinkage candidates were limited to the predeclared configuration; no search beyond those candidates occurred.

## Stage-A selection

Primary selection metric was pooled out-of-fold season-total WAPE, with Base-grouped leave-one-Base-out CV. Every season for a Base remained together. The three frozen candidate families were global pooled yield, Base-yield shrinkage (`lambda=0.25, 0.5, 1, 2, 4, 8`), and a regularized Base effect (`alpha=0.1, 1, 10, 100`).

| Candidate | Hyperparameter | Grouped CV WAPE | CV MAE (kg) | CV bias (kg) |
|---|---:|---:|---:|---:|
| Global pooled yield | none | 0.3938284667691153331125703063 | 338,291.3907 | -53,772.5988 |
| Shrinkage Base yield | each of 0.25–8 | 0.3938284667691153331125703063 | 338,291.3907 | -53,772.5988 |
| Regularized Base effect | best alpha 0.1 | 0.4406852848738388313683221368 | 378,540.5334 | -7,049,000.2089 |

Under Base-grouped LOBO, the validation Base is wholly absent from that fold's training partition. Consequently, every shrinkage lambda uses the prescribed zero-support global fallback in validation. The lambda values are therefore unidentifiable under this frozen CV design; the tied, less complex global candidate wins under the predeclared simplicity tie-break. The benchmark was not used to resolve this limitation.

## Frozen benchmark results

WAPE deltas below are `R2 - comparator`; negative favors R2. Full-39 results and common-30 results are reported separately.

| Full 39, 2025–2026 | Global baseline | V0.8 R1 | Selected R2 |
|---|---:|---:|---:|
| Season-total WAPE | 0.3429935582924604063039679242 | 0.3925893218351959883557945280 | 0.3429935582924604063039679242 |
| Season-total MAE (kg/Base) | 422,769.4831 | 483,900.5884 | 422,769.4831 |
| Daily WAPE | 0.5812862592207732948356517114 | 0.6292132974633544144280801218 | 0.5812862592207732948356517114 |
| Daily MAE (kg/row) | 2,673.4553 | 2,893.8816 | 2,673.4553 |
| Single-day peak quantity WAPE | 0.3022025958947355416785549739 | 0.3404074580806719157106758536 | 0.3022025958947355416785549739 |
| Single-day peak date MAE (days) | 30.5128 | 30.5128 | 30.5128 |
| Rolling-7 quantity WAPE | 0.2831406887616327543355090948 | 0.3348116783694683981147325588 | 0.2831406887616327543355090948 |
| Rolling-7 start-date MAE (days) | 23.1538 | 23.1538 | 23.1538 |

| Full-39 season-total diagnostic | Global baseline | V0.8 R1 | Selected R2 |
|---|---:|---:|---:|
| Median per-Base APE | 0.3380278746096637845923721843 | 0.3193194749526302384423707190 | 0.3380278746096637845923721843 |
| Signed bias (kg, predicted − actual) | -12,706,357.733154 | -14,809,615.303231 | -12,706,357.733154 |
| Overpredicted Bases | 10 | 11 | 10 |
| Underpredicted Bases | 29 | 28 | 29 |

Full-39 R2-minus-baseline season-total WAPE delta is exactly `0`. R2-minus-R1 season-total WAPE delta is `-0.0495957635427355820518266038`; daily WAPE delta versus R1 is `-0.0479270382425811195924284104`. These are improvements over the R1 per-Base Stage A on this already-seen benchmark, but R2 is the pooled baseline candidate, not a learned shrinkage improvement over the baseline.

| Common 30 | V0.7 | Global baseline | V0.8 R1 | Selected R2 |
|---|---:|---:|---:|---:|
| Season-total WAPE | 0.3565703507552211518045530094 | 0.3718680320214416088905949004 | 0.4295085823774648217328803026 | 0.3718680320214416088905949004 |
| Daily WAPE | 0.7391211072773783730171586934 | 0.5783462535574595492170871309 | 0.6375486158927208783266126936 | 0.5783462535574595492170871309 |
| Single-day peak quantity WAPE | 0.4523239714810114995308642954 | 0.3126617824414381213818458107 | 0.3644422981872252148259636832 | 0.3126617824414381213818458107 |
| Rolling-7 quantity WAPE | 0.4444987003783528082386557904 | 0.2873476075436469115881475284 | 0.3561760399332264772455906911 | 0.2873476075436469115881475284 |

On common 30, R2 season-total WAPE is `0.0152976812662204570860418910` higher than V0.7. The common-30 daily WAPE is `0.1607748537199188238000715625` lower than V0.7. The full-39 and common-30 cohorts are not mixed.

Per-Base season-total absolute-error counts: against the full-39 baseline, R2 wins `0`, baseline wins `0`, and `39` tie; against R1, R2 wins `13`, R1 wins `13`, and `13` tie. This matches the pooled result: selected R2 reproduces the baseline, while replacing R1's Base-specific Stage A changes some Base outcomes in both directions.

## Stage B and determinism gates

Stage B was copied exactly from the frozen R1 model. Its R1 and R2 effective shape hashes are both `7ae53f5888947053057071f9b097e38b03bb8112a41de972b8e2d51fd311cb2e`. The 39-by-268 daily-share matrix is unchanged. Daily prediction sums reconcile to season totals, and both peak-date invariants pass (`0` single-day peak dates changed; `0` rolling-7 start dates changed).

Two independent training/frozen-benchmark replays produced byte-identical private artifacts, matching model hashes, and matching prediction hashes. The selected R2 model SHA-256 is recorded in the machine evidence. Private per-Base/per-day outputs and CV assignments remain in the controlled artifact directory and are not committed.

## Readiness and boundaries

Result: `PASS_EXPERIMENT_COMPLETED_NO_STAGE_A_IMPROVEMENT`. Readiness is `R2_NO_MATERIAL_BENCHMARK_IMPROVEMENT`; production readiness remains false because the selected candidate only matches the global baseline and no business acceptance threshold is defined. A future model iteration must not be described as independently validated on 2025–2026; that season is now a frozen benchmark. No PR, Ready, Merge, deployment, or production promotion was performed.

Focused tests: 25 passed. Ruff and Mypy passed. Full CI was not run; this task remains local-only.

Machine evidence: [R2 experiment evidence](../evidence/r2-stage-a-shrinkage-model-experiment-r1.json). The final private replay artifacts are under `~/Documents/blueberry-area-yield-artifacts/` in `v0-8-r2-stage-a-shrinkage-experiment-r1-verified-replay-6` and `...-replay-7`. Earlier failed or superseded replay directories were preserved and were not used for the final deterministic comparison.
