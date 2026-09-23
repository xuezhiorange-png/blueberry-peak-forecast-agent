# V0.8-S1 Cross-Season Identity Authority and Canonical Dataset Rebuild

- Task: `V0_8_S1_CROSS_SEASON_IDENTITY_AUTHORITY_APPLICATION_AND_CANONICAL_DATASET_REBUILD_R1`
- New authority: `CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1`
- Input main baseline: `ec0cbfe134b6eee1159f8bad851664d1c7174b21`
- Result: authority and ledger rebuilt from exact-hash source workbooks; no model, refit, backtest, or weather experiment was run.
- Identity scope: exact source-farm label + season; no fuzzy mapping or cross-season propagation.
- Subfarm parent corrections change relationships only; they do not reallocate quantity.
- Unknown and unresolved quantities are never zero-filled. Confirmed zero requires authorized semantics.
- Registry area remains `REFERENCE_AREA`. Historical actual area requires a business-confirmed, unique source-identity binding.
- The 2025-2026 R7B business window is 2025-07-22 through 2026-04-15; in-window unknown dates remain unknown.

## Frozen input identities

Original workbook SHA-256 identities:

- `2023-2024`: `8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20`
- `2024-2025`: `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6`
- `2025-2026`: `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a`

Previous identity authorities, R7B coverage evidence, and decision-input manifests were hash-verified and left unchanged.

## Applied decision contract

- Confirmed business questions: 40
- Changed Base assignments: 59
- Q14 prior-season rows kept unresolved: 3
- Q14 target-season candidate rows applied: 10
- Q17 exact split relation rows: 20
- Q17 unlisted source-label keys left unresolved: 0
- Q07/Q10 relationship-only parent corrections: 2
- Rules are exact-identity and season-scoped; parent corrections do not reassign quantity.

## Reconciliation

- Raw total: 122983150.913 kg
- Mapped total: 109010615.352 kg
- Unresolved total (including conflicting subset): 10573929.816 kg
- Explicitly excluded total: 3398605.745 kg
- Reconciliation delta: 0 kg
- Mapped gain over prior accepted authority: 18060193.774 kg

## Season totals

| Season | Raw kg | Mapped kg | Unresolved kg | Excluded kg | Mapped rate | Business-window mapped kg |
|---|---:|---:|---:|---:|---:|---:|
| 2023-2024 | 30148211.706 | 23551840.401 | 4957687.84 | 1638683.465 | 0.7812019044669501432882103299 | 15135214.482 |
| 2024-2025 | 42440018.628 | 36755290.292 | 3924806.056 | 1759922.28 | 0.866052642770296194036816623 | 23758908.16 |
| 2025-2026 | 50394920.579 | 48703484.659 | 1691435.92 | 0 | 0.9664363808779403850958095981 | 48070902.334 |

## Base-season coverage and area semantics

The private quality ledger contains all 39 registered Bases for all three seasons (117 Base-season rows). Identity acceptance is distinct from quantity coverage; unknown dates remain unknown.

| Season | Daily rows | Total-evaluable | Peak-evaluable | Rolling-7 evaluable | Reference-area rows | Confirmed historical-area rows |
|---|---:|---:|---:|---:|---:|---:|
| 2023-2024 | 11310 | 0 | 0 | 0 | 39 | 0 |
| 2024-2025 | 11271 | 0 | 0 | 0 | 39 | 0 |
| 2025-2026 | 10452 | 1 | 0 | 0 | 39 | 1 |

Business-total, daily known-support, single-day peak, and rolling-7-day coverage are separate. A computable business total does not imply complete daily-shape or peak authority; frozen R7B metric-specific eligibility is preserved.

## Authority and privacy

Row-level labels, mappings, daily values, and identity diffs are restricted to the private artifact directory. Repository evidence contains hashes, counts, policy semantics, and aggregate reconciliation only.
Previous mapping authorities and V0.7 evidence remain unchanged. This dataset does not grant model-training eligibility.
