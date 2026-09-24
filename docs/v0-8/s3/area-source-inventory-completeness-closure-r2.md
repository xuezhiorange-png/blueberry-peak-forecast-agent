# V0.8-S3 Area Source Inventory Completeness Closure R2

## Result

`RESULT=PASS_INVENTORY_COMPLETENESS_PROVEN`

R2 resolves the four inventory-provenance gaps without re-evaluating or
activating any area authority. The completeness gate counts both R1 review
buckets (`421 EXCLUDED_OTHER + 100 UNCLASSIFIED_CANDIDATE = 521`) and requires
all 521 prior rows to have a current deterministic disposition. Of those,
520 match current path and SHA-256; one evidence JSON changed at the same path
after the R1 scan. Its historical bytes were retrieved from the pinned Git
revision, verified against the R1 SHA-256, checked as the expected R1 evidence
document, and classified under the same generated-evidence rule as its current
version. No prior review row remains unresolved.

The scan covered 253 configured roots (94 existing roots), enumerated 46,429
files, and classified 4,152 area-related candidates. Current review-required
and unclassified counts are both zero, and the scan has zero unresolved errors.
The two R2 report/evidence output paths are explicitly excluded from the scan
input universe so the result can be replayed after those files are committed.
The result proves inventory completeness only for the declared roots and the
pinned source inputs; it does not claim completeness outside that scope.

## Seven prior path gaps

All 42 physical source paths in the pinned legacy inventory still exist and
match their recorded SHA-256. Seven had not appeared as candidates in R1's
keyword scan. R2's bounded spreadsheet-header inspection rediscovered them
using the generalized `STRUCTURAL_AREA_SOURCE_DETECTION` rule. Therefore the
R2 path-level gap is zero and no old logical source hash is missing. The seven
records remain individually present in the private path reconciliation ledger;
they were not silently allow-listed.

## Old/new canonical inventory parity

The old 2,018-row inventory and frozen-parser replay each pass through the same
normalization, `_record_key`, ordering, and deduplication implementation:

| Check | Old inventory | Rebuilt replay |
| --- | ---: | ---: |
| Raw records | 2,018 | 2,018 |
| Canonical records | 1,973 | 1,973 |
| Duplicate rows removed | 45 | 45 |
| Canonical records only on this side | 0 | 0 |

All 45 removals are exact logical duplicates, grouped by source hash as 40 and
5 removed rows. The private duplicate-field parity ledger records every
duplicate key group and confirms equality of source hash, season, identity,
area value and semantics, area basis, decision, and authority eligibility.
The old and new canonical CSVs have the same SHA-256; the canonical diff is
empty. No new historical farm-area source was discovered.

## Candidate classifications

All 4,152 current candidates have a deterministic rule ID, reason, SHA-256,
path, scan status, and evidence in the private classification ledger. Counts:

| Classification | Count |
| --- | ---: |
| Included frozen-parser area-source files | 41 |
| Byte-identical copies | 2,998 |
| Engineering/facility area | 159 |
| Generated derivatives | 315 |
| Harvest-only | 2 |
| Non-area business files | 160 |
| No area field | 2 |
| Reference-only | 141 |
| Reports | 156 |
| Templates | 5 |
| Test fixtures | 145 |
| Unsupported format | 1 |
| Weather files | 26 |
| Office temporary copy | 1 |
| Review required / unclassified | 0 |

One legacy-format maintenance checklist raised a workbook decoder exception.
Independent maintenance/checklist context supports the report-only rule; the
exception and its evidence are retained in the private manifest. It is not
counted as a scan error. Any decoder exception without an allowed evidence
rule remains fail-closed.

## Area recovery result remains unchanged

No newly discovered source changed the prior S3 recovery result. The 117-row
candidate matrix remains: 0 authorized Base-seasons in 2023-2024, 0 in
2024-2025, and 2 business-confirmed 2025-2026 candidates; 12 conflicts and 86
`NOT_FOUND` rows remain. The two 2025-2026 candidates remain candidates only;
this task did not activate area authority or rerun the S3 recovery. The
previously reported training-area and quantity-total authority blockers
therefore remain.

This is not a claim that historical area was never supplied. The precise
finding is: within the fully audited declared sources, no authority-eligible
historical actual-area record was found for 2023-2024 or 2024-2025.

## Determinism, privacy, and boundaries

The official run and an independent run used separate private directories.
All 13 output files, including the artifact manifest, are byte-identical across
the two runs; the private artifact-manifest SHA-256 is
`fbd6c09824c4619962fe4b7e991ec139e8be435cade25c60d73061ac8303a66f`. Private
directories are mode `0700`, files are mode `0600`; row-level source labels
and paths are not committed.

`S3_RECOVERY_RERUN_EXECUTED=false`; area, identity, quantity, registry, and
V0.7 authorities were not modified. No model training/refit, backtest, or
forecast replay was run. PR #655 remains Draft; Ready and Merge are not
authorized.

Machine-readable aggregates and hashes are in
[`s3-area-source-inventory-completeness-closure-r2.json`](../evidence/s3-area-source-inventory-completeness-closure-r2.json).
