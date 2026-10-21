# V0.19 S3 Owner-scope adapter rebind R2

Task: `V0_19_S3_OWNER_SCOPE_ADAPTER_REBIND_R2`.
Reviewed base: `92cc8904e3af211300a88a20720d2c03848c43b8`.
Main push CI `39554253546` completed successfully before delivery. Its eight
PR-only jobs were skipped by the existing workflow; this is not a claim that
all twelve main-push jobs executed. The new PR must obtain its own exact-head CI.

## Version boundary

The new `backend/research/v019_owner_scope_adapter.py` entry authenticates
`V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1`. The original R1 adapter, constants,
synthetic experiment, profile, Registry, algorithms, strict scoring gate and
all historical evidence remain unchanged. Callers must explicitly use
`OwnerScopeInputPaths` and `validate_owner_scope_inputs(paths, support=...)`.
There is no automatic fallback, input discovery, authorization flag, label
loader, generation implementation or scoring implementation.

The Owner's five exact bindings are checked against Registry IDs and canonical
names. In particular, a shortened `盘龙基地` name is not accepted in place of
`砚山盘龙基地`. The four exclusions are research-only. All nine rows preserve
their original global `UNRESOLVED` identity status, separately from the new
five inclusions and four research exclusions. This does not revise V0.8.

## Reconciliation and metadata

The controlled parent Manifest SHA256 is
`0111ab23c3c1fbe33d96b738f2755ce79874319c9a54ef82b8b9c3b170bece05`.
All ten declared output hashes were verified. The new private, independent
`owner-scope-metadata-r2.json` has SHA256
`bc1248835055c2488f9d5fa29351ef3d3605f3c91b36539f4c236f1ca584e572`.
Its 6,534,009 bytes contain mapping provenance, member and area authority hashes,
daily metadata and prior daily status, but no actual harvest weights. Neither
the sidecar nor any private roster, daily ledger or raw workbook is committed.
The private directory is 0700 and files are 0600; existing evidence is not overwritten.

The admitted **research mapping**, not formal C0, has 80 source-farm labels and
four research exclusions. The corresponding counts are 231,634 included rows
and 1,535 excluded rows through April 16. Only 230,166 included rows are within
the candidate target window August 5, 2025 through April 15, 2026. April 16
remains outside candidate evaluation. No full-season admission is claimed.

The adapter independently checks all 39 Bases and 9,906 daily metadata rows:
6,416 observed Base-days and 3,490 authorized-zero Base-days. It checks the
previous 3,535 zero / 6,371 observed counts and recomputes exactly 17, 14 and 14
zero-to-observed changes for 砚山盘龙, 大理巍山 and 弥勒朋普 respectively.
Missing days, source gaps, unresolved member conflicts, missing area evidence,
duplicate identities and extra label columns are rejected, not filled with zero.
This is completeness under the recorded-source business rule; it does not
independently prove that every physical field harvest was scanned.

| Candidate window | Count | New file SHA256 |
| --- | ---: | --- |
| H7 | 9,672 | `fc047941cda320d12f5b4bc913cf5585ccbcae508f73e976b557c83a8892abea` |
| H15 | 9,360 | `699f75d7543bbe2ef9bd0c8c991ada3bf2d61bc0c9cea2fed02790f35b5e281f` |

Each candidate is checked against the complete Base×origin universe, dates,
window, source, new scope decision, Base member hash, area authority row hash
and the exact daily metadata slice. Selection does not use weights or errors.
No curves are generated or renormalized. Complete support remains an explicit
proposal (July 1, 2025 through April 15, 2026), not approval to execute it.

## Validation evidence

- Initial test-first run: collection failed because the new module did not yet
  exist. This is scaffolding RED, not a newly reproduced production defect.
- Final focused tests and related protocol regressions are recorded in the
  accompanying machine evidence; no skips, xfails or retries were added.
- V0.18 contract regression: 255 passed, 763 deselected by the explicit
  `-k v0_18` filter. The deselected cases are not claimed as executed.
- Two real-file read-only processes, PIDs 29949 and 30024, produced identical
  normalized review SHA256
  `78abf731a0633d9281e805277a7a73c021c3a41fe784bca2c18e372799c7d4eb`.
  An audit hook allowed only the five explicit input files, rejected writes
  and other file opens, and recorded zero raw-workbook reads and zero prediction
  or scoring calls during the review. Both also verified real execution refusal.
- Private positive verification report SHA256:
  `b63ab8a69d10f9d64d7f9d8bef4cf63bb5581135b4816061d07c1c880a96c798`.

## Unchanged gates

`STRICT_PIT=false`, historical area known-at and training-label/SOURCE_002
physical-basis equivalence remain unproven. Origin time and cutoff remain
unregistered date-only metadata, not historical issuance evidence.
`RETROSPECTIVE_PROTOCOL_EFFECTIVE=false`, `FORMALLY_ADMITTED_C0_COUNT=0`,
`PRODUCTION_ELIGIBLE=false`, `S3_FORMAL_COMPLETE=false`.

`generate_real_predictions` remains R1's unconditional refusal even when an
Owner approval object or environment flags are supplied. Real generation,
scoring, training, Ready and Merge require separate authorization. This delivery
does not grant any of them. Exact-head CI is reported from GitHub after push;
local results and these private checks do not substitute for that CI or
independent review.
