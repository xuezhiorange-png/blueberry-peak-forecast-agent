# V0.8-S5 — Complete-season quantity authority closure

**Task:** `V0_8_S5_EXISTING_HISTORICAL_QUANTITY_COMPLETE_SEASON_AUTHORITY_CLOSURE_R1`

**Result:** `PARTIAL_COMPLETE_SEASON_QUANTITY_AUTHORITY_RECOVERED`

**Baseline:** `5c66d8d8565eb87e1434e61de2939dcce4d7df75`

**Delivery:** local-only; no PR, commit, or push.

## Findings first

1. Of the 78 training Base-seasons, **0** currently qualify for a complete season-total target.
2. The 2023–2024 season has **0 of 39** eligible training totals.
3. The 2024–2025 season has **0 of 39** eligible training totals.
4. The 2025–2026 OOT season has **2 of 39** eligible totals: one frozen S1 business total reconciles to its complete daily series, and one additional Base-season qualifies from a complete, identity-bound daily series over the frozen business window.
5. The earlier zero training count did not mean harvest data was absent. It resulted from no frozen complete-season business-total authority in either training season, while every one of the 78 training Base-seasons has unknown days; 28 also have partial-known-subtotal days.
6. Both gates matter, but the direct season-total gate is missing for all 78 training rows. Daily incompleteness independently prevents deriving a total by summing observed days. An independently authorized business total remains eligible under the frozen S2 rule even when daily coverage is incomplete; the two eligibility dimensions are kept separate.
7. The current strict training sample remains **0**. Strict OOT eligibility is **2**; those OOT samples do not become training rows.
8. The largest blockers tie at 78 training Base-seasons each: `UNKNOWN_DAYS_PRESENT`, `BUSINESS_TOTAL_AUTHORITY_MISSING`, `SOURCE_COVERAGE_INCOMPLETE`, and `MEMBER_COVERAGE_INCOMPLETE`. The minimum closure path is to establish an independently authorized total for an exact training Base-season, or to close its entire frozen daily window with complete member coverage and authorized zeros. No partial subtotal or unknown day may be promoted.

The two recovered OOT totals do not establish that the quantity blocker is closed for training. Therefore this is a partial authority recovery, not a model-readiness or model-performance result.

## Frozen scope and method

The run consumed only the pinned S1 canonical daily ledger, S1 quality ledger, S1 identity and unresolved-identity authorities, corrected S2 daily-completeness policy, frozen season boundaries, and the already business-confirmed S4 area authority. Source workbooks were not searched or reimported. No model, forecast, or backtest path was run.

The three authority windows were held fixed:

| Season | Frozen business window |
| --- | --- |
| 2023–2024 | 2023-07-01 through 2024-04-15 |
| 2024–2025 | 2024-07-01 through 2025-04-15 |
| 2025–2026 | 2025-07-22 through 2026-04-15 |

Each daily row was classified first under the S2 rule. Only `KNOWN_MAPPED_SUBTOTAL + COMPLETE_MAPPED_MEMBERS` and authorized `CONFIRMED_ZERO` statuses are complete daily values. `PARTIAL_KNOWN_SUBTOTAL`, `UNKNOWN`, absent source rows, and unresolved identity remain distinct and are never zero-filled.

Season-total eligibility is separate from daily-curve eligibility:

- Existing totals require the frozen `BUSINESS_TOTAL_AUTHORITY_ELIGIBLE` status and `season_total_complete=true`.
- A daily-derived total requires every date in the frozen business window to be complete, identity-bound, and reconciled to S1's business-window mapped amount.
- An independently authorized business total may remain season-total eligible when daily coverage is incomplete. If the full daily window is complete, its sum is compared exactly with the business total; a mismatch fails closed.
- Daily-curve eligibility always requires the complete daily window. Neither peak nor rolling-7 eligibility is inferred by this task.

## Coverage and quantity findings

| Season | Base-seasons | Season-total eligible | Daily-curve eligible | Unknown days | Partial days | Authorized zero days | Complete mapped days |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023–2024 | 39 | 0 | 0 | 8,399 | 585 | 592 | 1,734 |
| 2024–2025 | 39 | 0 | 0 | 5,403 | 2,489 | 1,575 | 1,804 |
| 2025–2026 | 39 | 2 | 2 | 1,543 | 1,599 | 2,537 | 4,773 |
| **Total** | **117** | **2** | **2** | **15,345** | **4,673** | **4,704** | **8,311** |

The 4,673 partial days contain **28,299,468.146 kg** of known subtotal, including **17,160,475.924 kg** in the training seasons. These are reported as known partial amounts, not complete actuals. Unknown remains null.

The existing S1 business-total gate contained one record, in the OOT season; it reconciled with its fully complete daily series. A second OOT Base-season has all business-window days complete and identity-bound and its daily sum reconciles, so the overlay records a `COMPLETE_DAILY_WINDOW_SUM_AUTHORITY`. No training season has a complete total. No business-total/daily-sum mismatch was found.

## Source conservation

Raw season totals reconcile exactly to mapped + unresolved + explicitly excluded quantities. Frozen daily mapped sums also match the S1 business-window mapped quantities in all three seasons.

| Season | Raw kg | Mapped kg | Unresolved kg | Excluded kg | Delta kg |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023–2024 | 30,148,211.706 | 23,551,840.401 | 4,957,687.840 | 1,638,683.465 | 0 |
| 2024–2025 | 42,440,018.628 | 36,755,290.292 | 3,924,806.056 | 1,759,922.280 | 0 |
| 2025–2026 | 50,394,920.579 | 48,703,484.659 | 1,691,435.920 | 0 | 0 |
| **Total** | **122,983,150.913** | **109,010,615.352** | **10,573,929.816** | **3,398,605.745** | **0** |

The unresolved-identity quantity remains unallocated to candidate Bases. Training-season unresolved quantities are **8,882,493.896 kg** in total. The frozen unresolved ledger reports 22 labels in 2023–2024 affecting 11 candidate Bases, and 13 labels in 2024–2025 affecting 9 candidate Bases. This is a separate identity-quality limitation; it does not justify assigning those amounts.

## Training eligibility and blockers

The confirmed area authority remains unchanged: 39 Bases, 41,335 mu per season, 117 qualified Base-seasons, including all 78 training-season rows and all 39 OOT rows. The area side is not blocking.

| Eligibility | 2023–2024 | 2024–2025 | 2025–2026 OOT |
| --- | ---: | ---: | ---: |
| Area qualified | 39 | 39 | 39 |
| Season-total quantity qualified | 0 | 0 | 2 |
| Daily-curve evaluation qualified | 0 | 0 | 2 |
| Strict training / OOT intersection | 0 | 0 | 2 OOT |

All 78 training Base-seasons have unknown dates and lack a qualifying complete season-total authority. In addition, 28 have at least one partial subtotal day and 20 have unresolved identity/member-coverage blockers. These blocker counts overlap; they are not additive. The persisted blocker table reports the exact Base-season impact of each category.

The prior zero **training** eligibility conclusion remains true. The prior overall Base-season zero is superseded in the OOT scope only: strict OOT eligibility increased from 1 to 2. This task does not alter S1/S2 evidence or materialize the overlay into the canonical ledger.

Peak and rolling-7 authority remain outside this closure and are not made computable by a complete season total or a complete daily-window classification.

## Reproducibility and boundaries

Two independent private runs used the same pinned inputs and policy. All nine output files were byte-for-byte identical. Output directories use mode `0700`; files use `0600`. Private row-level CSVs remain outside the repository. The public evidence records only aggregate counts, authority hashes, and private artifact hashes.

Focused tests: 13 passed. Ruff and Mypy passed. Full CI was not run because this task is local-only and no PR was authorized.

No area, identity, S1 quantity, or S2 evidence was changed. No model training, refit, backtest, or forecast replay was performed. The next blocker is complete-season quantity authority in the two training seasons; the area authority is not to be revisited.
