# S3 support-count evidence correction R2

`V0_5_S3_TRAINING_ELIGIBILITY_AND_EVALUATION_FREEZE_R2` is an append-only
evidence correction for PR #629. It does not change the R1 qualification
rules, label authority, business cutoff, weather join boundary, or any training
authorization. It makes the denominator of each support count explicit.

## Correction

The R1 runner's `unique_eligible_base_count` and
`unique_eligible_base_season_count` were calculated from
`total_label_evaluable`. Their values were therefore full-season total-label
counts, not general eligibility counts. R2 removes those ambiguous names from
new output and emits:

- `full_season_total_eligible_unique_base_count`
- `full_season_total_eligible_base_season_count`
- `daily_known_support_unique_base_count`
- `daily_known_support_base_season_count`
- `W7_eligible_unique_base_count`
- `W7_eligible_base_season_count`
- `W15_eligible_unique_base_count`
- `W15_eligible_base_season_count`

The strict full-season result remains zero. The known-support and forward
window populations are reported independently and are not promoted to
complete-season evidence.

## Support by season

Counts are based on the reviewed current-authority ledger. A daily row is a
known-support row only when its label is known. A W7/W15 count is a complete
forward origin whose entire window has known labels. The unique counts use
canonical base IDs and base-season pairs; overlapping origins do not increase
the base denominator.

| season | known daily rows | daily bases | daily base-season pairs | W7 origins | W7 bases | W7 pairs | W15 origins | W15 bases | W15 pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023-2024 | 2,106 | 9 | 9 | 1,728 | 9 | 9 | 1,620 | 9 | 9 |
| 2024-2025 | 7,025 | 25 | 25 | 6,300 | 25 | 25 | 5,875 | 25 | 25 |
| 2025-2026 | 8,664 | 38 | 38 | 8,132 | 38 | 38 | 7,828 | 38 | 38 |
| **all seasons** | **17,795** | **38** | **72** | **16,160** | **38** | **72** | **15,323** | **38** | **72** |

The 39-base Registry remains the no-weather extended-scope ceiling. The
weather common-comparable ceiling remains the exact 38-base `YUNNAN_CORE`
scope. The Registry identity outside that weather scope remains retained and
is not silently dropped or given substitute weather data.

## Frozen forward folds

The following folds are support accounting only; no model is fit or selected.
Validation labels are not used for training or selection.

| fold | support unit | train count | validation count | train bases | validation bases | train base-season pairs | validation base-season pairs | train/validation base intersection | intersection IDs hash |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | daily known-support rows | 2,106 | 7,025 | 9 | 25 | 9 | 25 | 9 | `8d1b5006ddb75dce650517b8d86b9064ae4cfceca894c30e39082bcd95d20052` |
| A | complete W7 origins | 1,728 | 6,300 | 9 | 25 | 9 | 25 | 9 | `8d1b5006ddb75dce650517b8d86b9064ae4cfceca894c30e39082bcd95d20052` |
| A | complete W15 origins | 1,620 | 5,875 | 9 | 25 | 9 | 25 | 9 | `8d1b5006ddb75dce650517b8d86b9064ae4cfceca894c30e39082bcd95d20052` |
| B | daily known-support rows | 9,131 | 8,664 | 25 | 38 | 34 | 38 | 25 | `884ec44fb74e89019aa4f1068f89f82af91cf87e619a4a493283f4d4e375975a` |
| B | complete W7 origins | 8,028 | 8,132 | 25 | 38 | 34 | 38 | 25 | `884ec44fb74e89019aa4f1068f89f82af91cf87e619a4a493283f4d4e375975a` |
| B | complete W15 origins | 7,495 | 7,828 | 25 | 38 | 34 | 38 | 25 | `884ec44fb74e89019aa4f1068f89f82af91cf87e619a4a493283f4d4e375975a` |

Fold A is `2023-2024 → 2024-2025`. Fold B is
`2023-2024 + 2024-2025 → 2025-2026`. The different origin counts are not
treated as independent base samples; the base and base-season denominators are
the decision-relevant support evidence.

## Reproducibility and boundary

The R2 audit was replayed twice from the same hash-pinned private Registry and
accepted weather inputs. The private output root is:

`blueberry-area-yield-artifacts/s3-training-eligibility-r2-support-count-correction/`

Both runs produced identical summary and artifact manifests:

- artifact-manifest hash: `3850e492ad4f8ce2c5a49cda4f7cd491d7db2d7356ee57c63c905490af62138a`
- summary hash: `01995fb5650762003c0343ce313b1a60c5e140afa8e11b355aa00bc0a60d9267`
- support-counts-by-season hash: `4efe1d0e802bbb868a375c67d91fa2b535eb4a905271063303075b5525b50c39`
- forward-fold-support hash: `c9f9761afa7da7472c6a8d49c9c878cca8816a081040ee58825d1c2c615d8e68`
- deterministic replay: `true`

R1 qualification rules and R1 private artifacts remain historical snapshots.
No model training, weather-feature generation, climate-zone authority, schema,
API, MCP, or deployment change was performed.

`FINAL_STATUS=COORDINATOR_S3_SUPPORT_COUNT_EVIDENCE_R2_REVIEW`
