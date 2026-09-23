# Cross-season Data Mapping and Quality Audit R1

**Task:** `CROSS_SEASON_DATA_MAPPING_AND_QUALITY_AUDIT_R1`

**Audit baseline:** `main` at `3c0ae295dfbd327fcbc9dcd92dea7511b5030e8b`

**Result:** `PARTIAL — REQUIRES_BUSINESS_CONFIRMATION`

## Conclusion

The three raw files and the frozen identity authorities were re-read and hash-verified. Quantity reconciliation passes exactly, with no raw row duplicated in the source workbook, no accepted same-season label conflict, and no accepted source label assigned to different Bases across seasons. However, the audit cannot prove all three seasons’ mappings correct: 75 season-scoped farm labels remain unresolved, 15 are explicitly outside the current Base scope, and 35 Bases have a change in their authority-visible member/candidate label set across adjacent seasons. These are audit findings, not proposed authority changes.

`CROSS_SEASON_MAPPING_STATUS=REQUIRES_BUSINESS_CONFIRMATION`

`CAN_WE_PROVE_ALL_THREE_SEASON_MAPPINGS_CORRECT=false`

`QUANTITY_RECONCILIATION_PASS=true`

This is an identity and source-quality audit only. It did not alter mapping authority, Base Registry, V0.7 evidence, model configuration, or model behavior; it did not train, refit, or backtest a model.

## Sources and authority

The three original workbooks were identified by SHA256, not by filename alone:

| Season | Source filename | SHA256 | Frozen mapping authority |
|---|---|---|---|
| 2023–2024 | `23~24.xls` | `8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20` | `HISTORICAL_IDENTITY_RECONSTRUCTION_R1`, cross-checked against R2 |
| 2024–2025 | `24~25.xls` | `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6` | `HISTORICAL_IDENTITY_RECONSTRUCTION_R1`, cross-checked against R2 |
| 2025–2026 | `原果入库汇总表.xls` | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` | `BASE_MEMBER_MAPPING_R2` plus the 39-Base Registry; R1 has no rows for this season |

The audit also verified the R1 mapping, R2 member map, R1 Base-season matrix and coverage summary, Base Registry, mapping policy, and the combined identity-authority hash declared by V0.7 S1. A standalone serialized preimage for that combined hash was not found; therefore replay is explicitly based on the parsed, hash-verified R1/R2 authorities and registry, not a claimed reconstruction of that preimage.

No fuzzy or similarity-based assignment was accepted. Candidate labels remain unresolved. Farm aggregate and farm-plus-subfarm aggregate are parallel inventories of the same source rows; they were never added together.

## Raw inventory and conservation

Counts below are season-scoped farm labels. The separate farm-plus-subfarm ledger contains every observed pair, including blank subfarm values. Full-source totals retain rows outside the frozen business windows; those rows are not silently discarded or moved into another season.

| Season | Raw rows | Farm labels | Non-empty subfarm labels | Farm+subfarm pairs | Source date range | Raw kg | Mapped kg | Unresolved kg | Explicitly excluded kg | Mapped/raw |
|---|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 2023–2024 | 93,761 | 56 | 2 | 58 | 2023-07-26–2024-06-30 | 30,148,211.706 | 11,656,395.430 | 16,853,132.811 | 1,638,683.465 | 0.3866363797518438455667649742 |
| 2024–2025 | 202,072 | 88 | 132 | 194 | 2024-07-01–2025-05-27 | 42,440,018.628 | 30,590,748.252 | 10,089,348.096 | 1,759,922.280 | 0.7207995953097346505716995559 |
| 2025–2026 | 233,171 | 84 | 192 | 214 | 2025-07-22–2026-04-16 | 50,394,920.579 | 48,703,277.896 | 1,691,642.683 | 0 | 0.9664322780239696982180256409 |

Overall: 529,004 raw rows; 228 season-scoped farm labels (144 distinct label strings across seasons); 138 mapped, 75 unresolved, 15 explicitly excluded, and 0 conflicting labels. The complete source reconciliation is:

```text
122,983,150.913 kg
= 90,950,421.578 kg mapped
+ 28,634,123.590 kg unresolved (conflicting quantity, if any, is included here)
+  3,398,605.745 kg explicitly excluded from current 39-Base scope
```

Delta is exactly `0 kg` in each season and overall. Farm-level and farm/subfarm-pair totals independently equal each raw source total. There were zero exact duplicate raw rows by canonical row hash and zero rows resolving to multiple accepted Bases. Reused subfarm labels under multiple parent labels are separately recorded for review; they are not treated as proof of identity or added twice.

The old rough unresolved figures for 2023–2024 and 2024–2025 combined unresolved quantity with explicit out-of-current-scope exclusions. This audit separates those categories: 2023–2024 is 16.853m unresolved plus 1.639m excluded; 2024–2025 is 10.089m unresolved plus 1.760m excluded. The 2025–2026 unresolved quantity independently replays to 1.692m.

## Frozen business windows and coverage

The frozen windows used for business-window diagnostics are 2023-07-01–2024-04-15, 2024-07-01–2025-04-15, and 2025-07-22–2026-04-15. In-window global unknown/no-record dates for 2025–2026 remain 40; they were not filled with zero. The 2025–2026 source includes a row after the business end, retained in full-source reconciliation and excluded from the business-window subtotal.

Identity and quantity coverage are separate. An accepted identity does not establish a complete season total. The private Base-by-season matrix has all 117 Base-season cells and reports identity status separately from quantity coverage. For 2025–2026, R7B source-label qualifiers remain source-label scoped; they do not prove the corresponding multi-member Base aggregate complete.

All 39 registry areas remain `REFERENCE_AREA_ONLY` unless a season/source-specific area authority exists. Two 2025–2026 source-label-level historical productive-area authorities were verified against source hash, accepted Base binding, and exact business-window quantity; neither is silently promoted to complete Base-level historical area. No absent historical area was inferred from reference area.

There are 15 Base-season cells with 1–29 observed business-window days, plus 35 cells with no accepted mapped day. Two one-day examples are 2023–2024 版纳勐旺 and 2024–2025 砚山阿猛. These are high-risk partial-coverage evidence even where identity is accepted; they are not complete season totals.

## Cross-season membership and high-risk business review

No identical accepted source label changed canonical Base across seasons (`SAME_LABEL_DIFFERENT_BASE_COUNT=0`). This does not mean the full membership history is settled. The authority-visible accepted/candidate label set changed for 35 Bases (55 adjacent-season change records). Those differences can represent real organization change, rename, split/merge, or historical omission; the audit does not infer which.

The four requested review groups remain open and are itemized in the private confirmation sheet:

1. **Jianshui Chake / Nanzhuang:** the frozen alias places Nanzhuang under Chake in earlier seasons, while the raw `建水岔科基地` label is unresolved in the first two seasons; accepted farm labels also vary. The audit found no duplicate source-row assignment, but cannot establish whether these are one business Base or separate operations, nor rule out quantity mixing.
2. **Yuanjiang Ganzhuang / Xinping Yangwu:** both source labels are accepted to the same canonical Base where present, but the observed member/coverage composition changes by season. Reference-area yield diagnostics show large jumps (including the supplied approximately 3.30× 2023–2024 to 2024–2025 change); the source and business-window ratios are both retained. Coverage, membership, area denominator, source boundaries, and real production change remain unresolved alternatives.
3. **Tengchong Dehong / Yingjiang:** `盈江联农带农` is accepted by current R2 to Tengchong Dehong and appears in 2025–2026 with limited observed days. Name and mapping status alone do not establish the business relationship; confirmation is required.
4. **Yanshan Huilong / center station:** the 2023–2024 parenthesized center-station label is unresolved, the later center-station label is accepted, and the 2025–2026 record has only five observed days. Addition, rename, historical omission, and duplicate reporting remain open possibilities.

The audit flags 20 adjacent-season Base yield transitions beyond the diagnostic ratio bounds (>2.5 or <0.4). These use mapped source quantities divided by the current reference area and are anomaly flags only—not actual yield estimates or proof of production change. The prominent supplied cases (版纳勐旺, 永仁猛虎, 建水岔科, 元江甘庄) remain high-risk for coverage, mapping, area denominator, source truncation, or real-business-change review.

## Findings and artifacts

| Severity | Count | Interpretation |
|---|---:|---|
| `P0_CRITICAL` | 0 | No observed quantity non-conservation, accepted same-season identity conflict, or multi-Base source-row assignment |
| `P1_HIGH` | 114 | Unresolved positive-quantity identity, high-risk alias/member changes, very short support, or extreme yield diagnostics |
| `P2_REVIEW` | 149 | Membership/name changes, reused subfarm labels, partial coverage, exclusions, and area limitations |
| `INFO` | 177 | Traceability/context findings, including rows outside business windows |

The private controlled artifact set contains the complete requested source identity ledger, 39-Base membership matrix, anomaly ledger, Base-season quality table, membership-change detail, and `manual_business_confirmation.csv` with blank `business_decision` cells. It contains 263 confirmation items. Raw row-level business data and local file paths are not committed to this repository.

The private artifact manifest SHA256 is `04e540ffa019dcfd07d4140dc498800f4df11e74184ff6db853fd4f2d9deb17b`; its file hashes and row counts are summarized in [`evidence/cross-season-data-mapping-and-quality-audit-r1.json`](evidence/cross-season-data-mapping-and-quality-audit-r1.json). Two independent runs produced byte-identical manifests. The private directory is mode `0700`; row-level files are mode `0600`.

No mapping correction is applied here. Any business decision must be authorized as a separate data-authority correction, leaving the published V0.7 evidence and release history intact.
