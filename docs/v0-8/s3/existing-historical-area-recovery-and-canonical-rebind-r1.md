# V0.8-S3 Existing Historical Area Recovery and Canonical Rebind R1

## Inventory provenance correction

The later source-completeness audit is `BLOCKED_INVENTORY_COMPLETENESS_NOT_PROVEN`.
It enumerated 46,416 files and 4,134 area-keyword candidates, but seven
previously listed source paths were not rediscovered by the configured
keyword scan, 45 rows were removed by logical deduplication (2,018 → 1,973),
and 521 candidates remain unresolved for classification. The parser replay
itself is deterministic, but these differences mean the 2,018-row inventory
and the area-recovery conclusions below are not re-accepted as complete.

No S3 rebind was rerun, and no area authority or business result was changed.
The source-level diff and aggregate hashes are in
[`s3-area-source-inventory-completeness-provenance-r1.json`](../evidence/s3-area-source-inventory-completeness-provenance-r1.json);
private row-level paths and records remain outside Git.

## Executive result

Existing, season-bound business-confirmed area evidence was found; no area was
estimated and the user was not asked to re-enter it. Two Base-season records
are supportable for 2025-2026 after rebinding through the current V0.8 canonical
identity authority. One was already present in the V0.8-S1 quality ledger; one
additional Base-season binding was missing from that ledger. The recovered
candidate therefore increases the audited count from one to two, a gain of
one.

No accepted season-specific historical actual area was found for 2023-2024 or
2024-2025. The 117-row candidate matrix contains 2 business-confirmed actual
records, 12 conflicting candidate Base-seasons, 17 reference/candidate-only
rows, and 86 rows with no bindable season-specific area source. These are
candidate/recovery findings only: the existing V0.8-S1 authority, Base
Registry, identity authority, and quantity authority remain unchanged.

The additional area binding does not unblock training. The two previously
reported candidate areas are both in the 2025-2026 OOT season;
training-season area-qualified Base-seasons remain zero. These counts remain
provisional because source inventory completeness was not established.
Training is independently blocked by both zero training-season historical
actual-area authority and zero complete-season-total quantity authority.

## Scope and safeguards

- Read and hash-verified the complete prior area inventory: 2,018 source rows
  across 42 source files. All 42 source-file hashes matched the inventory.
- Reused `CROSS_SEASON_BASE_IDENTITY_AUTHORITY_R1` for rebinding and the V0.8-S1
  canonical Base-season quality ledger for the 39 Base × 3 season matrix.
- Revalidated the frozen historical-area authority and all files listed by the
  R7B artifact manifest. Source-season hash, `BUSINESS_CONFIRMED` area basis,
  season, accepted identity binding, and area-source inventory row had to agree.
- Kept current/reference areas, previous-season proxies, planned/planted
  areas, processing-factory report values, unresolved identities, and
  conflicting evidence out of historical actual area.
- Did not copy area across seasons, average conflicts, edit any existing
  authority, change harvest quantity/zero/missing semantics, or run a model.
- Detailed farm names and source rows are private. The committed evidence is
  aggregate-only; row-level source ledger and 117-row authority candidate are
  in the controlled private artifact directory.

## What was recovered and why it was previously absent

The frozen area authority and R7B qualification evidence contain two
business-confirmed, explicitly 2025-2026-bound area records. Both raw season
source hashes and both files' manifest hashes were verified; the current S1
identity authority maps both records to unique canonical Bases. One of those
records was already represented in the S1 quality ledger. The other was
present in the frozen area authority and R7B evidence but absent from the S1
canonical Base-season area field. This was a prior authority-application / Base
season projection gap, not missing user input or a need to infer identity.

For 2023-2024, the audited area-source inventory contained no season-bound
actual-area rows. The prior season-specific recovery package had 13 priority
Base rows marked `NOT_FOUND`; the harvest source itself has no area columns.

For 2024-2025, the inventory contains proxy, report, and planning candidates,
not accepted season-specific actual-area authority. The existing business
confirmation package records 12 `CONFLICTING_EVIDENCE` rows and one
`BUSINESS_CONFIRMATION_REQUIRED` row. None is promoted here. Current Base
Registry values remain `REFERENCE_AREA_ONLY`; they are not historical actual
area.

The complete private source ledger retains every inventoried area record,
including rejected, unresolved, proxy, planned, report-derived, and
unseasoned rows, with source path/hash and source revision. The conflict ledger
preserves each of the 12 conflict groups without choosing a value.

## Canonical candidate and eligibility

The private candidate matrix has exactly 117 unique Base-season rows. Only
two rows carry `BUSINESS_CONFIRMED_HISTORICAL_ACTUAL`, both for 2025-2026.
Neither historical training season carries an accepted area. The unchanged S1
quantity authority has zero complete season-total rows in the 2023-2024 and
2024-2025 training seasons. In 2025-2026, one of the two area-qualified
Base-seasons intersects the frozen complete season-total authority.

| Measure | Audited result |
| --- | ---: |
| Historical actual area Base-seasons before this rebind | 1 |
| Historical actual area Base-seasons in the recovery candidate | 2 |
| Additional canonical binding recovered | 1 |
| 2023-2024 / 2024-2025 area-qualified training Base-seasons | 0 |
| 2025-2026 area-qualified OOT Base-seasons | 2 |
| Strict training Base-seasons if the candidate were applied now | 0 |
| Strict OOT Base-seasons if the candidate were applied now | 1 |

The prior candidate therefore reported one additional OOT Base-season, but
area recovery did not increase the strict training sample from zero. The two
independent training blockers remain: training-season historical actual-area
authority is zero, and complete season-total quantity authority is zero. No
quantity records were changed. These candidate results are not re-accepted
until source-inventory completeness is resolved.

## Replay and artifact integrity

The recovery runner validates pinned SHA-256 values for the prior area source
inventory, its manifest, the current identity and quality ledgers, the frozen
area authority, the R7B artifact manifest and qualification, and the two
season-specific area review matrices. It also re-hashes all 42 source files
and verifies all R7B manifest entries before creating outputs.

The final artifact set was generated twice from the same inputs. CSV, summary,
and manifest bytes were identical. Files are private (`0700` directory,
`0600` files); no detailed records are committed.

The aggregate hashes and source identities are in
[`s3-existing-historical-area-recovery-and-canonical-rebind-r1.json`](../evidence/s3-existing-historical-area-recovery-and-canonical-rebind-r1.json).

## Frozen boundaries and result

This deliverable is a read-only recovery/rebind candidate. It does not activate
the additional row in the old S1 ledger. Any authority application must be a
separately reviewed step. No area estimation, reference-area promotion,
cross-season propagation, model training/refit, backtest, or forecast replay
was performed.

`RESULT=PARTIAL_AREA_AUTHORITY_RECOVERED`

Partial is intentional: one previously omitted 2025-2026 confirmed area was
rebound; the other two historical seasons still have no accepted season-bound
actual areas, and 12 Base-season candidate groups remain conflicting.
