# V0.8-S2 Canonical History Model Retrain and OOT Comparison

## Business conclusion

**A strict historical-area comparison is not supportable.** No training Base-season has the required business-confirmed historical productive-area authority, so the formal result is `INSUFFICIENT_STRICT_AUTHORITY_FOR_COMPARISON`.

An explicitly non-production exploratory `REFERENCE_AREA_ONLY` lane was run on the common OOT rows:

| Question | Exploratory result | Evidence |
| --- | --- | --- |
| Season total more accurate? | **NO, on the only computable Base-season** | 2025-2026 WAPE: V0.7 `0.07436190616320323526020689978`; V0.8 `0.5389045665515906970493540976`; one eligible Base-season. Fold A has no complete-total authority. |
| Daily curve more accurate? | **YES, exploratory only** | Combined pooled daily WAPE: V0.7 `0.7300081450131058779261255029`; V0.8 `0.6942604931630213721690104058`; 9,694 comparable daily rows. Both folds have lower V0.8 WAPE. |
| Single-day peak more accurate? | **INSUFFICIENT_EVIDENCE** | Frozen S1 peak authority permits zero common OOT Base-seasons to be scored. |
| Rolling 7-day peak more accurate? | **INSUFFICIENT_EVIDENCE** | Frozen S1 rolling-7 authority permits zero common OOT Base-seasons to be scored. |

The exploratory daily WAPE change is `-0.0357476518500845057571150971` (V0.8 minus V0.7; negative means lower error), or a `4.896883972362079072626418121%` reduction relative to V0.7. This is not a strict-area result and is not production-eligible. The only computable season-total comparison moves in the opposite direction, on one Base-season only. No claim of overall model improvement is justified.

## Scope and frozen authority

- Task: `V0_8_S2_CANONICAL_HISTORY_MODEL_RETRAIN_AND_OOT_COMPARISON_R1`.
- Base: `91d9d8a04be05576fc8c3ae8fec0fbad899057d8` (fresh `origin/main`, containing the V0.8-S1 merge).
- V0.8-S1 authority: `CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1`.
- Raw/mapped/unresolved/excluded totals: `122983150.913 / 109010615.352 / 10573929.816 / 3398605.745 kg`; 44 unresolved source-farm labels remain excluded.
- Verified S1 evidence SHA-256: `fea7741e85b86d84f2d7beab9f89d458c4fe32e0cfd7fd141da2a8ca5dc70aa7`.
- Verified S1 config SHA-256: `957a84ecdb6ab25da51230a14d90e8eb6bfb6eb299aeb73e312b9421d3a77824`.
- Verified private S1 manifest SHA-256: `acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6`.
- Verified private identity authority / daily ledger / quality ledger SHA-256: `7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b` / `be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75` / `64a0a41afcde4ffe3c8713f62ca5cc03ee0f36599289bafd409e641df0a2f2fd`.
- V0.7 model config SHA-256: `cf0e1c4bffc4acc404dd0479d36b02f78df893ef25dda819359eaa317157dabf`; frozen product artifact identity: `399c38f81abdea0122097cd5a68bc25147cc55f58dc51e1393b9282e5bc4cbad`.
- Architecture, model family, parameters, temporal model, and weather usage were unchanged. The V0.8 candidate changes the accepted canonical history authority only and uses `REFERENCE_AREA_ONLY`; it is exploratory and not production-eligible.
- History policy remains `IMMEDIATE_PRIOR_SEASON_ONLY_FAIL_CLOSED_NO_GLOBAL_FALLBACK`.
- No unresolved, conflicting, excluded, unknown, or missing quantity was converted into a training zero. Only accepted mapped quantities and authority-confirmed zeros were used.

## Folds, authority qualification, and common OOT set

| Fold | Training authority window | Immediate-prior yield input | OOT season | Common Base-seasons | Fit input rows |
| --- | --- | --- | --- | ---: | ---: |
| A | 2023-2024 | 2023-2024 | 2024-2025 | 13 | 2,911 |
| B | 2023-2024, 2024-2025 | 2024-2025 only, per the frozen immediate-prior rule | 2025-2026 | 30 | 8,779 |

The common OOT set has 43 Base-seasons and 11,797 Base-season-date rows. It contains 9,694 known/comparable rows and 2,103 `UNKNOWN` rows. The same common rows, accepted quantity authority, reference-area semantics, dates, and metric implementation are used for the baseline, V0.7 replay, and V0.8 candidate. Common dataset SHA-256: `585199bff8e29344b5f2f62486defc0e90f2f34a69ea3f80949ff616761355ee`.

Area qualification covers 117 Base-season records: 116 are `NOT_ESTABLISHED`; one is `BUSINESS_CONFIRMED_SOURCE_LABEL_BOUND` in an OOT season. Strict training-eligible Base-seasons: **0**. Strict OOT area-qualified Base-seasons: **1**, but that does not create a trainable strict model. Every registry reference area remains `REFERENCE_AREA_ONLY`, never historical actual productive area.

Predictions and their manifests were written and hashed before the runner first loaded OOT quantity labels. OOT labels only determine post-seal comparability and metric coverage. Training seasons and target boundaries exclude their corresponding OOT season. A second independent offline replay reproduced the same common dataset, candidate artifacts, prediction hashes, score values, and private manifest hash.

## Daily metrics (known support only; pooled WAPE)

All weights use the same scored actual rows. `Absolute change` is V0.8 minus V0.7; negative WAPE/MAE change means lower error.

| Scope | Model | Daily WAPE | Daily MAE (kg) | Scored rows | Unknown rows |
| --- | --- | ---: | ---: | ---: | ---: |
| Fold A | Frozen area-yield baseline | 0.6880219846803483520613577585 | 2990.678847607019696744051911 | 2,774 | 983 |
| Fold A | V0.7 replay | 0.7308045490122817524092039460 | 3176.645158339581831290555155 | 2,774 | 983 |
| Fold A | V0.8 candidate | 0.6620471854494875120258058044 | 2877.772160959985580389329488 | 2,774 | 983 |
| Fold B | Frozen area-yield baseline | 0.5626870062408877451664698429 | 3218.662375780135250500072254 | 6,920 | 1,120 |
| Fold B | V0.7 replay | 0.7297655439381598849003885043 | 4174.379136825 | 6,920 | 1,120 |
| Fold B | V0.8 candidate | 0.7040733307265649669633016970 | 4027.415444581358381502890173 | 6,920 | 1,120 |
| Combined OOT | Frozen area-yield baseline | 0.5919519263602090871788899417 | 3153.423433428967255232979162 | 9,694 | 2,103 |
| Combined OOT | V0.7 replay | 0.7300081450131058779261255029 | 3888.871187957808953992160099 | 9,694 | 2,103 |
| Combined OOT | V0.8 candidate | 0.6942604931630213721690104058 | 3698.437678048896224468743553 | 9,694 | 2,103 |

V0.8 vs V0.7 daily WAPE deltas: Fold A `-0.0687573635627942403833981416`; Fold B `-0.0256922132115949179370868073`; combined `-0.0357476518500845057571150971`.

## Season total and peak metrics

Only one common OOT Base-season has complete business-total authority, in Fold B / 2025-2026. On that single eligible Base-season:

| Model | Actual total (kg) | Predicted total (kg) | Absolute error (kg) | Absolute percentage error / WAPE |
| --- | ---: | ---: | ---: | ---: |
| Frozen area-yield baseline | 484,802.056 | 338,319.8006053561427065 | 146,482.2553946438572935 | 0.3021485853489116747753644015 |
| V0.7 replay | 484,802.056 | 448,751.251004 | 36,050.804996 | 0.07436190616320323526020689978 |
| V0.8 candidate | 484,802.056 | 223,540.014148 | 261,262.041852 | 0.5389045665515906970493540976 |

V0.8 minus V0.7 total WAPE is `+0.4645426603883874617891471978`; absolute error increases by `225211.236856 kg`. Fold A has zero complete-total-authority Base-seasons. Thus one Fold-B case is not a reliable general season-total estimate, but it is the only authorized comparison available and must not be concealed.

Single-day peak quantity/date and continuous rolling-7-day peak quantity/start-date metrics are `NOT_COMPUTABLE_NO_FROZEN_PEAK_AUTHORITY` and `NOT_COMPUTABLE_NO_FROZEN_ROLLING7_AUTHORITY`, respectively; eligible common OOT Base-season count is zero. No missing day was filled to create peak windows.

## Reproducibility and limitations

- Candidate model artifact hashes: Fold A `a5e298edf3b020ebf065dccfb149ce74aad99aea7c78db950fc08b28750badb2`; Fold B `798fbc6660c72fb7f7d41ba1a1545ad8f32670019bbc67f87fe2124c20f51cae`.
- Candidate training hashes: Fold A `72997c9fc3201f7c6ed3b8deae40d90bec33b0777a5525b514a7721fc03572d7`; Fold B `142cea15665dab25f79cc7076f23817154933ca15986be3939e29296474b6`.
- V0.8 prediction hash: `fbc420f9f1e3b685bd1d8d430dbc9685791925f5d2426613d7e78c5d7f032e28`; the common dataset and model/prediction hashes matched on independent replay.
- Private row-level artifacts remain outside Git. The private run manifest SHA-256 is `17280cf6d0a10135974e761c42d5eb530c02353b5475f5550bc51586a9328fb2`.
- Strict area-driven training was not performed because strict training authority count is zero. The completed candidate is explicitly `EXPLORATORY_REFERENCE_AREA`, `PRODUCTION_ELIGIBLE=false`.
- No weather inputs, new architecture, model family search, hyperparameter search, production model edits, or promotion occurred.
- S1 unknown/zero semantics and area semantics are unchanged; V0.7 authority/evidence/config were not modified.

**Result:** `INSUFFICIENT_STRICT_AUTHORITY_FOR_COMPARISON`. Exploratory known-support daily metrics show lower error on both folds, while the one complete-total case regresses substantially and peak outcomes cannot be evaluated. This does not establish that V0.8 canonical history improves the model overall.
