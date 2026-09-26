# V0.8-S7 — Training-season source identity closure

## Result first

1. Of the 41 identity-blocked training Base-seasons, **0 were safely resolved**.
2. Strict training eligibility remains **37/78**.
3. 2023–2024 remains **15/39** eligible.
4. 2024–2025 remains **22/39** eligible.
5. Of the frozen **10,573,929.816 kg** unresolved quantity, **0 kg** was reassigned.
6. Of **1,231** residual partial days, **0** could be closed.
7. Of **10,642** unknown days, **0** could be closed; 6,082 fall under Base-seasons with no accepted source rows and 4,560 under identity-unresolved Base-seasons.
8. Remaining blockers are 21 Base-seasons without accepted source identity and 20 with unresolved candidate identity; frozen daily detail for unresolved source labels is also unavailable for a lawful daily rebuild.
9. The separate retrain technical gate is met by the unchanged 37 strict training samples, 39 strict OOT samples, and deterministic replay. This does **not** authorize training in S7.

**Overall S7 result: `BLOCKED_TRAINING_SOURCE_IDENTITY_CLOSURE`.** This means the targeted identity blockers were not closed; it does not invalidate the 37 already-authorized training samples.

## Scope and method

The run selected only S6-ineligible training Base-seasons from 2023–2024 and 2024–2025. It verified the five supplied S6 SHA-256 pins, S6's frozen summary and manifest, S1's canonical identity/quality/unresolved ledgers, the prior historical identity mapping, the captured business decisions, and the grouped confirmation package. Cross-links recorded by the S1 manifest were checked before analysis.

The target set was 41 rows: 24 from 2023–2024 and 17 from 2024–2025. Its identity-status split was:

- 21 `NO_ACCEPTED_SOURCE_ROWS`;
- 15 `IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES`;
- 5 `IDENTITY_UNRESOLVED`.

The targeted unresolved ledger contained 44 source rows across 33 unique source-farm/season keys. All 44 current identity rows were `UNRESOLVED`; all 44 historical reconstruction entries were `PROPOSED_CANDIDATE_NOT_AUTHORIZED`. Ten `YES_ALL` business-decision rows had no explicit canonical Base target and were not applied. There were 22 exact parent-relation matches, but each was only `SOURCE_REPORTED_PARENT` and none had a canonical quantity Base assignment. No accepted alias, historically accepted mapping, or authorized parent/member assignment was found for the target rows.

No S7 overlay row was emitted. S1/S6 frozen inputs do not retain per-day quantity rows for the unresolved source labels. Reimporting raw harvest files was prohibited, so S7 did not attempt to distribute season aggregates across days or infer identities from quantities.

## Before/after eligibility and conservation

| Measure | Before S7 | After S7 |
| --- | ---: | ---: |
| Strict training Base-seasons | 37 | 37 |
| 2023–2024 eligible | 15 | 15 |
| 2024–2025 eligible | 22 | 22 |
| Identity-blocked target Base-seasons | 41 | 41 |
| Strict OOT Base-seasons, 2025–2026 | 39 | 39 |
| Unknown days | 10,642 | 10,642 |
| Partial days | 1,231 | 1,231 |
| Resolved unresolved quantity | — | 0 kg |

Quantity buckets are byte-for-byte semantically unchanged: raw `122,983,150.913 kg`, mapped `109,010,615.352 kg`, unresolved `10,573,929.816 kg`, excluded `3,398,605.745 kg`, conservation delta `0 kg`. Previously eligible training rows and all 39 OOT rows had zero regressions.

## Interpretation and next step

The identity closure itself remains blocked. The 21 no-accepted-identity rows have no target-linked accepted source identity in the frozen authorities. The other 20 rows remain ambiguous; candidate names, similarity, business `YES_ALL` without an explicit target, quantity conservation, and area were not used to choose a Base. Residual partial days remain unresolved rather than being treated as zero.

Although S7 released no new samples, the existing strict cohort satisfies the task's stated technical preconditions for a separately authorized V0.8 retrain/OOT task: 37 strict training Base-seasons, 39 strict OOT Base-seasons, no eligibility regressions, and byte-identical fresh-process replay. This report is not training authorization; no model operation was performed.

## Non-actions and artifacts

Area, identity authority, canonical quantity ledger, S6 evidence, and quantity semantics were not modified. No raw harvest was reimported; no model was trained/refit; no backtest or forecast replay was run; no PR was created. Row-level ledgers remain in the private artifact directory with mode `0700` and files `0600`. The repository evidence contains aggregate counts and hashes only.

Machine evidence: [S7 evidence](../evidence/s7-training-season-source-identity-closure-r1.json). Runner config: [S7 config](../../../configs/v0_8_s7_training_source_identity_closure_r1.json).
