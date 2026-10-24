# S8: target-aligned recorded-inbound rolling shadow forecasts

Task: `V0_19_S8_TARGET_ALIGNED_ROLLING_FORECAST_SOURCE_R1`.
Base: `3b6ff77532198d4b2a3fc38f0b73208995b5366c` (main CI `40058547846` succeeded).
This is engineering integration, not training, promotion, production accuracy
acceptance, or authorization to read current-season business data.

## Reuse and source decision

S7's application service, capability catalog, authentication/CSRF, account read
admission and response-release reauthorization, frozen S6 model loader, V0.15
four Harvest State sums, Ridge inference, run/daily tables, immutable save/reload,
independent persisted-row peak recomputation, history, comparison and S1 review
arithmetic are reused. No migration, solver, importer, scheduler or permission
platform is added. I5/I7 `FARM_PICK / OBSERVED_WEIGHT / KG` semantics are unchanged.

`FactReceiptRaw` records `receipt_date`, `weight_kg`, source row/sheet/fingerprints,
grade, duplicate/exclusion flags, and ingest-file identity. The history parser
recognizes `入库公斤数`. These declarations do **not** establish authoritative Base
membership, an immutable revision-winner set, trustworthy pre-cutoff availability,
daily member completeness, or confirmed zeros. `created_at` is not source
availability. Neither this table nor SOURCE_002 is automatically read by S8.

S6 training's recorded `入库公斤数 / KG` is `RECORDED_INBOUND_WEIGHT`.
SOURCE_002 records inbound weighing **net** weight; equality to old training
weights, gross weight or complete field harvest remains unproved. Unknown
physical meaning returns `SOURCE_BASIS_UNVERIFIED`; no tare correction, conversion
factor, inferred Base alias, or relabeling of I5 is introduced.

Therefore S8 implements option B: an explicitly registered, read-only controlled
source snapshot. A real custodian must supply the missing source evidence before
real registration/use. No real business source was admitted in this delivery.

## Controlled snapshot contract

An `InboundSnapshot` in the existing server catalog has
`source_kind=CONTROLLED_RECORDED_INBOUND_V1`, an absolute manifest path, exact
manifest file SHA256, normalized index SHA256 (`snapshot_hash`), physical
definition SHA256, exact source members, mapping/membership/completeness authority
hashes, and an explicit source-to-frozen-fit `target_binding`.

The index is quantity-free. It binds Base, season, source system, an inbound event
date definition, kg, the weight **as recorded** (no implicit net/gross/field
conversion), a physical-definition proof hash, accepted/excluded grade lists, and
`EXPLICIT_IMMUTABLE_WINNERS`. Each day references a separately hash-pinned JSON
payload, member coverage, completeness and its `known_at`. Canonical serialization
is `Index.model_validate(...).model_dump(mode="json")` followed by the existing
`digest`; this normalizes timezone strings, so noncanonical identities fail.

Each day payload contains only that Base/date/source's records. Each record has
an exact canonical source member, logical ID, winner revision ID, grade, kg,
source-recorded time, server-ingested time and availability authority. Duplicate
logical/revision IDs, wrong entities, unknown grades, invalid values, identity or
byte drift are rejected. The adapter does not choose a new revision winner.

Missing dates, incomplete member coverage, unknown times and late records remain
unknown, never zero-filled. A no-record zero needs a separately registered
confirmed-zero date plus complete member coverage and timely completeness proof.
Nonzero rows conflict with a confirmed zero. Excluded grades are only excluded by
the sealed, explicit grade contract, not by forecast error or magnitude.

Manifest and day files must be explicit, bounded, nonsymlink objects, not writable
by group/others. Day references are safe basenames, never discovery paths. HTTP
callers supply only existing resource references, not filesystem paths. Private
manifest paths are excluded from saved/API input projections.

`target_binding` cites a source/fit evidence identity, not an execution grant or
new reviewer workflow. Its fit must match the actual restored pair and target
basis. Synthetic contracts are marked `SYNTHETIC_CONTRACT_ONLY`; they cannot
authorize real labels. Real registration requires `SOURCE_AUTHORITY` and actual
source-equivalence evidence supplied by the operator. A matching enum alone is
not sufficient. No real-source equivalence proof is invented here.

## Time, inference, persistence and comparison

The loader selects `[season_start, origin)` **before opening day quantity files**.
It never opens D or future day payloads for issuance. Source timestamps and
completeness must be known by the requested cutoff. Four Harvest State values
flow through the existing S7 bridge into the unchanged frozen M0/M1 predictors.
M1 is `NOT_COMPUTABLE` for incomplete required history; M0 may remain an explicit
control. Neither run is relabeled as the other.

Fifteen D+1…D+15 values are computed once at frozen Decimal/six-place rounding.
H7 is their first seven dates. Existing persisted-row validation independently
checks all dates, sums, maxima and every rolling-seven window with earliest ties.
Two origins use the original comparison admission: same Base, season, known
feature/target bases, model identities and overlapping target dates. Different
window totals are not same-date revisions; common-date deltas remain separate.

The whole source identity participates in the input seal. A new immutable source
version changes that identity even if only future metadata changes. Altering D
or later quantities cannot change consumed feature **values** or predictions;
those day payloads are not read. Altering a legitimate D-1 record changes the
four corresponding feature sums and M1 inference without changing M0 parameters.
STRICT_PIT remains false; neither retrospective files nor synthetic availability
timestamps prove actual historical issuance or prospective source visibility.

## Independent review and Dashboard

Existing POST `/{run_id}/review` requires the separate `evaluate` capability and
CSRF, and reads only saved predictions plus a separately registered mature label
snapshot. New GET `/{run_id}/review` is metadata-only and also requires evaluate
permission. It returns `NOT_SCORABLE` reasons or `PREFLIGHT_ELIGIBLE`; the latter
does not promise complete labels. Both retain response-release reauthorization.

Training target, forecast target, feature observation basis and evaluation label
basis remain separate. Review compares **forecast target** with labels before
label quantity reads, including frozen-fit/source binding and exact member,
mapping and physical-definition evidence. Wrong target/source meaning returns
`CROSS_SOURCE_TARGET_BASIS_UNVERIFIED`; immature labels fail without reads.
The unchanged ten S1 metrics retain common samples, denominators and explicit
not-computable reasons; full-season WAPE is not admitted. H7 rolling-seven start
MAE zero is structural, not peak-timing skill. No legacy S6 WAPE is reused.

The existing rolling panel shows source completeness and four physical meanings,
saved curves, peaks, origin comparison, metadata admission and separately
requested review numerators/denominators, errors, coverage and Base outcome.
No authoritative business metric is calculated in the browser. Responses are
bound to the selected saved run/result hash and selected label snapshot hash.
Input changes, cancellation, account changes and authority invalidation prevent
late responses from restoring stale review data. Research status remains visible.

## Numerical acceptance and limitations

The explicit synthetic recorded-inbound fixture (52 dated events, one exact Base
member, 100 mu) runs real application code, PostgreSQL, auth and frozen fixture
Ridge arithmetic, not mocked prediction responses. Its two-origin M1 values are:

| Origin     |      H7 kg |      H15 kg |
| ---------- | ---------: | ----------: |
| 2026-11-05 | 538.941049 | 1031.362335 |
| 2026-11-06 | 526.137595 | 1002.702182 |

These deliberately retain the original S7 numerical example with an independently
defined synthetic inbound contract. The original FARM_PICK path remains tested.

The exact previously authorized real S6 fitted artifact and original execution
manifest were also verified and restored without fitting. On the same synthetic
inbound observations, actual M1 inference produced:

| Origin     |      H7 kg |      H15 kg | H15 single peak            | H15 rolling-seven start |
| ---------- | ---------: | ----------: | -------------------------- | ----------------------- |
| 2026-11-05 | 675.843026 | 2128.694696 | 2026-11-20 / 241.801806 kg | 2026-11-14              |
| 2026-11-06 | 722.941802 | 2317.006743 | 2026-11-21 / 260.665105 kg | 2026-11-15              |

No parameter was changed to obtain these values. Real-model parameters and their
local probe outputs remain private. Independent-process equality verifies
deterministic numerical inference, **not** realistic source availability, model
accuracy, net/gross equivalence, future season skill, training or promotion.

Real/current-season observations and labels were not read, imported or scored.
Real-source member/revision/completeness/time and target-equivalence proof,
explicit source registration and separate evaluation authorization remain
necessary for future real use. Unknown physical meaning, missing/duplicate days,
ambiguous members, late/partial rows, wrong source/fit identity, immature labels,
cross-basis review and missing capability remain blocked/not computable.
No production database, formal forecasting service, frozen historical evidence, model file,
dependency, CI workflow or existing assertion was modified. This ships as one
Draft PR, not Ready/Merged/deployed.

## Executed checks

Local application/PostgreSQL suite: 88 passed. Frontend Unit: 174 passed.
Related immutable history/forecast protocols: 191 + 166 passed. Ruff/format,
Mypy (595 application files), frontend lint/typecheck/format/build passed.
Desktop/mobile full Playwright JUnit: 190 passed, zero failed/skipped; the
original 188 test identities are retained and two inbound test identities added.
Logs and original failures are preserved under the task's SYNTHETIC `/tmp` roots.

The local full-suite outer launcher returned 1 after all tests passed because
its disposable Vite shutdown guard required exit 0. The requested SIGTERM
instead produced standard exit 143 with the owned listener closed; its original
failed guard receipt is not overwritten. PostgreSQL ownership, postmaster exit,
closed listener, business ASGI lifespan shutdown and all HTTPS/TLS audit proofs
are separately successful. This launcher is outside Git; no repository test or
CI acceptance criterion was changed to accommodate it. Final exact-head CI is
separate external evidence, not predeclared by this document.

An independent repeat of that Vite lifecycle confirmed SIGTERM -> exit 143 with
the owned socket closed. It validates the termination interpretation without
rewriting the failed outer-wrapper receipt or rerunning/weakening any assertion.
Project-aware JUnit identity comparison also confirms 188 retained + 2 added,
with no removed or newly skipped test identities.
