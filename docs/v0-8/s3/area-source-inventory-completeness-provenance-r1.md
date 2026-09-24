# V0.8-S3 Area Source Inventory Completeness Provenance R1

## Result

`RESULT=BLOCKED_INVENTORY_COMPLETENESS_NOT_PROVEN`

The source-discovery run is reproducible, but it does **not** establish that
the prior 2,018-row area inventory is complete or exactly reproducible. The
old inventory has 42 physical source paths and 2,018 rows. The frozen parser
replay emits 2,018 rows; after byte-identical/logical-record deduplication,
the canonical replay contains 41 source artifacts and 1,973 rows. Forty-five
old rows are absent from the deduplicated inventory. Seven old source paths
were not rediscovered by the configured keyword scan, and 521 candidates
remain unresolved for classification (`UNCLASSIFIED_CANDIDATE=100`,
`EXCLUDED_OTHER_REQUIRES_REVIEW=421`). No new source rows or files were
identified as accepted area-source additions.

These differences are not accepted as corrected area data. Per scope, the S3
area recovery/rebind was **not rerun**, no candidate was activated, and the
existing area and quantity authorities were not changed. The previous S3
matrix remains a historical candidate output, not a result re-accepted by
this provenance audit.

## Search and replay evidence

The deterministic scan expanded 253 configured roots; 94 existed and were
searched. It enumerated 46,416 files and recorded 4,134 area-keyword
candidates. The roots covered the repository's configuration, documentation,
scripts and backend; configured Downloads, Desktop and controlled private
artifact roots; and matching historical project-checkout subdirectories.
Missing optional repository/project subdirectories were recorded in the
manifest. No root traversal or file-read error was reported.

Candidate disposition counts are:

| Disposition | Count |
| --- | ---: |
| Included area-source candidate | 34 |
| Byte-identical candidate copy | 2,982 |
| No area field | 2 |
| Reference-only | 77 |
| Generated derivative | 160 |
| Test fixture | 147 |
| Report-only | 211 |
| Other, requires review | 421 |
| Unclassified, requires review | 100 |

The prior parser and source inventory were pinned by their existing SHA-256
values. Replaying the parser into a new temporary directory produced 2,018
rows. Applying the frozen content-and-logical-row deduplication policy
produced the same 1,973-row CSV bytes on an independent replay
(`636e8a58e6e7eab6bdec0bfd08c12fd62a2455bbd58d51e9865604ded9629b25`).
The 45-row difference groups as 40 and 5 by source hash; the 42 physical old
source paths contain 41 distinct file hashes, including one byte-identical
copy. This explains a duplicate-copy component but does not by itself
authorize changing the prior S3 business result.

The seven old source paths not rediscovered are part of the frozen parser's
input set, but did not match the configured keyword scan. This is a discovery
policy gap. The candidate set also contains 521 unresolved classifications.
Therefore the evidence supports deterministic parser replay, but not complete
source discovery or exact old/new inventory parity.

## Prior user-provided area sources

The prior S3 recovery ledger records one source file with two
`BUSINESS_CONFIRMED_HISTORICAL_ACTUAL` records (source SHA-256
`231e769ebd004f02267eb4d2402f5745a8cb690ac873bb871f3db0bdb311eed2`). It also
records one separate business-confirmed review workbook with three rows, but
those rows remain `CURRENT_ONLY_NOT_HISTORICAL_AUTHORITY` (source SHA-256
`465765cb28c3d7d3e6560978471aef99bb8dd2f8f6592e90126ddb249b581795`). The
current Base Registry's reference-area records were searched and retained as
reference evidence only. These counts do not establish historical training
area authority for either training season.

No area was estimated, copied across seasons, or promoted from reference or
current-area semantics. The user was not asked to re-enter area data.

## Training blockers remain independent

The prior S3 candidate reported zero training-season Base-seasons with
historical actual-area authority. The unchanged S1 quantity authority also
has zero complete season-total training Base-seasons. These are two separate
blockers:

1. `TRAINING_AREA_AUTHORITY_STILL_BLOCKING=true`
2. `QUANTITY_TOTAL_AUTHORITY_STILL_BLOCKING=true`

This audit does not resolve either blocker. The previous “quantity authority
is the remaining blocker” wording is superseded by this dual-blocker
statement.

## Pinned artifacts and safeguards

The row-level discovery manifest, source inventory and file/record diffs are
stored only in the controlled private artifact directory. The directory is
mode `0700`; its files are mode `0600`. The committed evidence contains
aggregate counts and SHA-256 references only.

| Artifact | SHA-256 |
| --- | --- |
| Old source inventory | `81341ce629a479db82ad4f02539afd9759c8eacfe29a311683dd38ef63c681cf` |
| Old source manifest | `c66dffe275741b7c985920fed4cf32c8af43420650873b59f6a2bdb2fbfea2f1` |
| Discovery manifest | `217743b3b146cbe6ad18a3abf82dd0b2b6d706c8aee1e51e42ba280148ed4285` |
| Rebuilt private record inventory | `636e8a58e6e7eab6bdec0bfd08c12fd62a2455bbd58d51e9865604ded9629b25` |
| File-set diff | `13de8674a13af0c8180abe121b8b87f5033d0b8cff97ef6f5364182e3e1dd0b8` |
| Record-set diff | `4e0085c329f091bbede7e7a2841a098cf199c798456544709228af6de8e808b7` |
| Private artifact manifest | `8c90bd5f0095cc8cabfe22bbca160fb680d9e7ad57d1e51bb72d77438dae1cea` |

`MODEL_TRAINING_EXECUTED=false`, `MODEL_REFIT_EXECUTED=false`,
`BACKTEST_EXECUTED=false`, `FORECAST_REPLAY_EXECUTED=false`, and
`S3_RECOVERY_RERUN_EXECUTED=false`. Existing V0.7 evidence, identity
authority, Base Registry, area authority, quantity authority and business
decisions remain unchanged.

## Acceptance status

`AREA_SOURCE_INVENTORY_REBUILD_DETERMINISTIC=true`

`AREA_SOURCE_INVENTORY_COMPLETENESS_PROVEN=false`

`AREA_RECOVERY_RESULTS_UNCHANGED=false`

The Draft PR remains blocked for review of the seven undiscovered legacy
source paths, the 45-row deduplication difference, and 521 unresolved
candidate classifications. No Ready or Merge action is authorized.
