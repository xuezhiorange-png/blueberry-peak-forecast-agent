# V0.8-S4 Original User Area Source Recovery

**Result: `PARTIAL_ORIGINAL_USER_AREA_SOURCE_RECOVERED`.** Existing area data was recovered and classified, but the source-of-truth recovery is not complete enough to add historical area authority for the training seasons.

## Direct answers

1. **Previously supplied area data recovered:** 2,018 source-classification rows, deduplicated to 1,973 canonical source records by the pinned inventory audit. These include different evidence classes and are not 2,018 historical actual-area records.
2. **Direct user area input:** 39 Base-grain rows, summing exactly to 41,335 mu. The raw workbook and the prior user prompt were hash-verified; three literal addition cells were evaluated with the restricted two-term parser. Each name and value matches the current registry exactly.
3. **Time scope of that 39-Base input:** `CURRENT/UNSPECIFIED`. It is a recovered original user input, not a season-specific historical area dataset and is not copied into any past season.
4. **Season-bound historical records:** the existing product authority contains two 2025–2026 business-confirmed records: one full-Base scope and one member-only scope. The full-Base record remains one Base-season candidate; the member-only area is not promoted to its whole Base.
5. **Raw original area file behind those two records:** not recovered. Both records refer to a workbook whose SHA-256 is pinned and whose four sheets / 1,632,225 cells were scanned; no area-like field or text was found. That workbook is harvest-quantity evidence, not an original area document. The business-confirmed values remain in the existing product authority and are not modified here.
6. **2023–2024:** no season-bound historical-area source record was recovered.
7. **2024–2025:** 921 classified source rows were found, but they are planned-area, previous-season proxy, processing/statistical, or unknown semantics; none qualifies as historical actual area.
8. **2025–2026:** 535 classified source rows were found, including the two existing business-confirmed anchors (one full Base and one member-level), plus planting, processing/statistical, and unknown evidence.
9. **Conflicts:** 12 Base-season candidate conflict groups from the prior area review remain unresolved. No value was selected, averaged, or promoted.
10. **Strict training-area potential:** no area candidates were recovered for either training season (2023–2024 or 2024–2025), so strict training area eligibility remains 0. The existing full-Base 2025–2026 candidate is in the OOT season and does not repair the training-season gap.

## Source and authority interpretation

The user-provided 39-Base workbook is the source for the 41,335-mu registry input. Its values exactly reconcile to the current Base Registry, but neither that workbook nor its prior prompt identifies a historical season. It therefore remains `CURRENT_AREA_SEASON_UNRESOLVED`.

The existing two 2025–2026 records are traceable to the product-integration authority and the S4 reclassification artifact. Their referenced source workbook is the 2025–2026 raw-fruit intake/harvest workbook. A workbook-wide scan found no area-like values, so it is not represented as the original area source. The original area-bearing document for those two confirmed records was not recovered in the searched inventory.

The complete prior source inventory covered 46,429 enumerated files and 4,152 area-candidate files, with 41 included source files (42 source paths in the recovery ledger because one byte-identical duplicate path is separately retained as excluded), 41 unique content hashes, and no scan errors. All area candidates were reconciled to the pinned inventory. The audit also reviewed repository history/refs, worktrees, controlled private artifacts, Desktop/Downloads/Documents area sources, 15 attachment text files, and 35 local Codex session records; no additional structured user area table was found.

The frozen prior classification reasons are preserved as classification-row counts: identity unresolved 1,791; previous-season proxy 95; reference-only 109; report/plan candidate 10; season missing 6; non-historical semantics 5; already in V0.8-S1 1; and old area authority not rebound 1. These are not counts of unique historical actual areas.

The legacy V0.3 package contains 31 previous-season proxy rows. Its original workbook bytes were not found in the complete inventory. A same-title planning workbook is not byte-identical and remains planning/proxy evidence. No proxy, planned value, statistical area, or registry reference value was promoted.

## Frozen boundaries

- The private recovery package contains the complete 39 × 3 = 117 Base-season matrix, source and member views, the 41,335-mu input lineage, proxy lineage, conflict ledger, source lineage, and manifest. It is stored under the controlled private artifact root with directory mode `0700` and file mode `0600`.
- Final private run id: `v0-8-s4-original-user-area-source-of-truth-recovery-r1-final-r4`; its artifact-manifest SHA-256 is `87fc729ef90d1f6f8a8a6c5a55136a1a4a4e26b6a3e2ef34981143dd944d4bf3`.
- The public machine evidence contains aggregate counts and hashes only. It contains no Base names or row-level area values.
- Area, identity, quantity, Base Registry, and V0.7 authorities were not modified. No season was inferred, no area was estimated, no reference/proxy area was promoted, and no cross-season area was copied.
- No model training, refit, backtest, forecast replay, or deployment was performed.
- Two independent private replays were byte-identical, including the artifact manifest.

This recovery therefore confirms that area data exists, but separates that fact from whether its season, Base/member scope, and source authority qualify as historical actual productive area. A follow-up authority decision is needed before any recovered candidate can affect training eligibility.
