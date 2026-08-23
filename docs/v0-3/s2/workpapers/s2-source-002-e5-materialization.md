# SOURCE_002 E5 — Lane D controlled SQL materialization

## Scope

Lane D E5 consumes persisted SQL outputs from Lane A lineage, Lane B cleaned rows,
and Lane C `s2_idfl_label_side_winner_decision`. PIT (`s2_pit_visibility_decision`)
and legacy revision winner (`s2_revision_winner_decision`) tables must remain at
row count 0 for SOURCE_002.

## Boundary oracle (fail-closed)

| Check | Expected |
| --- | --- |
| IDFL SQL rows | 233171 |
| Non-excluded cleaned grains | 33894 |
| B `kg_equal` | true |
| PIT SQL rows | 0 |
| Old revision winner SQL rows | 0 |

## Join

1. Replay canonical grain keys from Lane A lineage using Lane B grain helpers
   (`build_canonical_grain_key`, `compute_collapsed_grain_source_row_identity_hash`).
2. Attach Lane C IDFL `content_sha256` per contributor `source_row_identity_hash`.
3. Align collapsed contributor digest with Lane B `s2_cleaned_row.source_row_identity_hash`
   for non-excluded grains.
4. `revision_winner_identity` = sorted IDFL content hashes digest (singleton = that hash).
5. `pit_visibility_identity` = NOT_APPLICABLE digest from `VISIBILITY_BOUNDARY`.

## Flags

- `SOURCE_002_ROW_LEVEL_READ = false` (unchanged)
- `SOURCE_002_CONTROLLED_SQL_MATERIALIZATION_ENABLED = true` (controlled SQL path in `lane_d/service.py`)

## Live report

When frozen object is available:

```text
SOURCE_002_E5_REPORT e2=233171 e3_grains=33894 e3_kg_equal=true idfl_sql=233171 pit_sql=0 old_winner_sql=0 train_rows=<measured> val_rows=<measured> test_rows=0 dataset_identity=<sha> rebuild_parity=<PASS/FAIL>
```

Otherwise: `OBJECT_MISSING`
