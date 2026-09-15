# S3 eligibility authority rebind R3

`V0_5_S3_ELIGIBILITY_AUTHORITY_REBIND_R3` is an append-only evidence rebind for
PR #629.  It replays the S3 qualification and support accounting against the
corrected S1 R2 Base Registry authority.  It does not change qualification
rules, train a model, generate weather features, or authorize S4.

## Authority correction

The previous S3 R1/R2 private evidence used a stale S1 mapping snapshot.  R3
loads the corrected private authority at
`blueberry-area-yield-artifacts/base-registry-s1-r2/`, pinned by the registry
artifact manifest and `BASE_MEMBER_MAPPING_R2` mapping authority.  The
historical R1/R2 evidence remains preserved and is marked superseded by this
rebind; it is not overwritten or deleted.

The required deterministic alias is:

`德宏盈江农场 -> 腾冲德宏农场 -> base_5d98f77f66280b5196f09ceb`

For `2025-2026`, the corrected S1 audit contains exactly zero unresolved
members and a pre-cutoff total of `392895.468000` kg.  This is an explicit
authority proof, not fuzzy matching or a new identity inference.

## Support and scope result

The corrected authority produces 39 active Registry bases and 39 bases with
known daily label support.  The exact 38-base `YUNNAN_CORE` weather scope is a
subset: the intersection is 38, the known-support-only base is
`base_36bc109841061a7798ed99a3` (`乡丰蓝莓基地`), and there are no weather-only
bases.  The 39-base no-weather research ceiling and 38-base weather
common-comparable ceiling therefore remain explicit and are not silently
merged.

| season | known daily rows | bases | base-season pairs | W7 origins | W15 origins |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2023-2024 | 2,106 | 9 | 9 | 1,728 | 1,620 |
| 2024-2025 | 7,025 | 25 | 25 | 6,300 | 5,875 |
| 2025-2026 | 8,892 | 39 | 39 | 8,346 | 8,034 |
| **all seasons** | **18,023** | **39** | **73** | **16,374** | **15,529** |

These are known-support and complete-forward-window populations, not complete
season labels.  Full-season eligibility remains zero: 0 complete, 82 partial,
and 35 blocked base-season candidates.  No full-season model training is
authorized by this evidence rebind.

## Frozen forward folds

Fold A is `2023-2024 -> 2024-2025`; Fold B is
`2023-2024 + 2024-2025 -> 2025-2026`.  For each support unit, the reported
base intersection is the canonical-base intersection, not the count of
overlapping daily rows or origins.  Validation labels are not used for model
training or selection.

| fold | support unit | train rows/origins | validation rows/origins | train bases | validation bases | intersection |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | daily known support | 2,106 | 7,025 | 9 | 25 | 9 |
| A | complete W7 origins | 1,728 | 6,300 | 9 | 25 | 9 |
| A | complete W15 origins | 1,620 | 5,875 | 9 | 25 | 9 |
| B | daily known support | 9,131 | 8,892 | 25 | 39 | 25 |
| B | complete W7 origins | 8,028 | 8,346 | 25 | 39 | 25 |
| B | complete W15 origins | 7,495 | 8,034 | 25 | 39 | 25 |

The Fold A intersection ID hash is
`8d1b5006ddb75dce650517b8d86b9064ae4cfceca894c30e39082bcd95d20052`.
The Fold B intersection ID hash is
`884ec44fb74e89019aa4f1068f89f82af91cf87e619a4a493283f4d4e375975a`.

## Reproducibility and boundary

The R3 runner was executed twice from the same hash-pinned private inputs.  It
produced identical 18-file artifact manifests and identical summaries.  The
private output root is
`blueberry-area-yield-artifacts/s3-eligibility-authority-rebind-r3/`.

The R3 authority rebind is an evidence correction only.  It does not authorize
model training, weather-feature generation, climate-zone authority, S4
ablation, schema changes, API changes, MCP changes, or deployment.  The next
decision remains with the Coordinator after reviewing the corrected
cross-season support evidence.

`FINAL_STATUS=COORDINATOR_S3_ELIGIBILITY_AUTHORITY_REBIND_R3_REVIEW`
