# V0.8-S6: No-record-zero semantics and season-total rebuild

## Result

The explicit business rule was applied to the frozen S1 Base-day universe: within a verified frozen harvest window, an expected Base-day with a confirmed identity universe and no harvest business row is a confirmed zero. The rule was not applied to unresolved identity, incomplete member identity, partial source evidence, unavailable source, excluded rows, or missing canonical-day rows.

The overlay converts **4,703** of **15,345** prior unknown days to authorized zero. **10,642** remain unknown: 4,560 have unresolved candidate identity, and 6,082 have no accepted source identity for the Base-season. There were no missing canonical daily rows or identified source-date/source-availability gaps in the frozen 33,033-row universe. It resolves **3,442** of **4,673** partial days; **1,231** remain partial because unresolved identity prevents a safe completion. Confirmed-zero days rise from **4,704** to **9,407**. No nonzero quantity or unresolved quantity is changed.

After applying the zero semantics and then evaluating complete-season authority:

- 2023–2024: 15 of 39 season totals eligible; 15 daily-curve Base-seasons eligible.
- 2024–2025: 22 of 39 season totals eligible; 22 daily-curve Base-seasons eligible.
- 2025–2026 OOT: 39 of 39 season totals eligible; 39 daily-curve Base-seasons eligible.
- Strict training eligibility is **37 of 78** training Base-seasons; strict OOT eligibility is **39 of 39**.
- One existing business total reconciles to the complete daily sum; no business-total mismatch was found.

Thus quantity authority is no longer a zero-sample blocker: training-authority samples are available. Forty-one training Base-seasons remain blocked: 21 have no accepted source identity for the Base-season, while 20 have unresolved candidate identity. These groups explain the remaining unknown-day blocker; separately, 15 Base-seasons still contain partial known-subtotal days (overlapping the identity gaps). This task stops before model training.

## Frozen scope and semantics

The expected daily universe is the frozen 39 canonical Bases crossed with the established business windows (33,033 Base-days total). The existing S1 daily ledger, identity authority, S2 completeness policy, and three-season area authority were read and hash-verified. The original ledgers and S5 evidence were not modified.

Only a verified S1 source row with zero source rows, a frozen source hash, and a confirmed Base-season identity with at least one accepted member and no unresolved candidate labels can receive `CONFIRMED_ZERO / AUTHORIZED_ZERO`. A partial mapped subtotal can become `COMPLETE_MAPPED_MEMBERS` only where the same identity/source conditions hold and accepted members absent from that day have no harvest rows. Unresolved or incomplete identity is never converted to zero.

Season-total authority is computed only after day-level classification. It requires the full frozen window, all daily rows complete after the authorized zero overlay, confirmed identity with no unresolved candidates, the complete season boundary, and exact reconciliation to the frozen mapped seasonal quantity. Daily-curve eligibility is reported separately from season-total eligibility. Existing authorized business totals retain priority and are reconciled against complete daily evidence when possible.

## Conservation and unchanged authority

The quantity conservation totals remain:

| Quantity | kg |
| --- | ---: |
| Raw | 122,983,150.913 |
| Mapped | 109,010,615.352 |
| Unresolved | 10,573,929.816 |
| Excluded | 3,398,605.745 |
| Delta | 0.000 |

Nonzero harvest quantity delta is 0.000 kg; unresolved identity quantity remains 10,573,929.816 kg. Area authority, identity authority, canonical S1 ledgers, and historical S1/S2/S5 evidence remain unchanged. S6 supersedes S5 only for no-record unknown/partial-member semantics and the resulting season-total eligibility overlay.

## Reproducibility and execution boundary

Two fresh executions against the same pinned inputs wrote separate private directories. All artifact bytes and manifest hashes match. Private directory permissions are `0700`; files are `0600`. Row-level farm/Base data stays outside the repository. The committed evidence is aggregate-only.

No raw harvest search/import, model training/refit, backtest, forecast replay, PR creation, Ready, Merge, or full CI was performed. The focused S6 tests, Ruff, and targeted mypy checks passed. This is an authority-application result, not model-effectiveness evidence.

See the aggregate machine evidence at [`s6-no-record-zero-semantics-and-season-total-rebuild-r1.json`](../evidence/s6-no-record-zero-semantics-and-season-total-rebuild-r1.json). The private row-level manifest SHA-256 is `d23ed98beccb98b11d7ca43800d19a6491deed6ff705513531a927139bab7cd7`.
