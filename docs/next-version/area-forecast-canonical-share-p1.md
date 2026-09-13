# Canonical public share serialization P1

TASK_ID=NEXT_VERSION_AREA_FORECAST_DETERMINISTIC_SHARE_SERIALIZATION_FIX_P1
Base main: `926f30a3c9a5b4c67e421ef11a6c2d1025631b55`.

## Fix boundary

BUG_CLASS=FLOAT_STRINGIFICATION_ULP_DRIFT

The caller supplied forensic finding is five share strings differing by at most
`2e-18`, plus result_hash, with no date/kg/peak/authority/identity differences.
The local pre-fix execution independently reproduces the historical hash below.
The **server's five exact share pairs have not yet been supplied/found locally**.
Their pair-specific convergence regression remains a review dependency; synthetic
neighbor-ULP tests are explicitly not presented as that missing forensic test.

`canonical_share_text` is used only when constructing new `DailyAreaForecast.share`.
It uses exact `Decimal.from_float`, finite/nonnegative validation, `ROUND_HALF_EVEN`,
quantum `0.000000000000001`, and fixed `.15f` output. An independent local Decimal
Context avoids ambient precision/trap changes; signed zero is emitted as positive zero.
No NumPy/string/repr formatting is used at this boundary.

The original `normalize -> compose(total, raw shares)` order and numerical inputs
are unchanged. Canonical shares are never fed back into compose. No request hash,
model/authority, DB schema/migration, MCP schema/tool contract or historical document
is changed. The five MCP tool names remain unchanged.

Quantization is not a mathematical guarantee that *all* neighboring floats round to
the same decimal: values straddling a half-quantum boundary can differ. Tests cover
representative neighbor ULPs and five synthetic output perturbations, with exact
half-even ties tested separately. Do not claim the missing five server pairs passed.
For 366 rows, the serialization rounding bound `1.83e-13` stays below the existing
`1e-12` share-sum integrity tolerance; that tolerance is not relaxed.

## Golden and historical evidence

| Identity | Hash |
| --- | --- |
| Old historical, independently reproduced locally before fix | `6d406e8a4a436b2c9bf347dca5f52b3f9b048ea4fb1602405225fc4f2ac39d1b` |
| Old server, supplied forensic identity; full payload not available locally | `72b5a910f32c99dcc58f4cf7a97fed7399b6d8666612209b9d360ee31942c283` |
| New canonical output, computed after fix | `869ace798d59564e71bd4f9e8868060073dc7a346e401948767b814092b99dba` |

Old hashes remain historical evidence, not post-fix golden expectations. No attempt
was made to force the new digest to either old digest.

Actual Yangliu request: 393.4 mu, target 2026-2027, window 2026-10-15..2027-05-09,
as_of 2026-09-12. The pinned original authority remains outer SHA256
`231e769ebd004f02267eb4d2402f5745a8cb690ac873bb871f3db0bdb311eed2`.
All 207 date/predicted_kg pairs are byte-for-byte equal before/after; all other result
fields except share strings/result_hash are equal:

- yield: `1232.338729 kg/mu`; total: `484802.055989 kg`;
- single peak: `2027-04-18`, `6450.429844 kg`;
- 7-day peak: `2027-04-15..2027-04-21`, `45110.003741 kg`;
- mass-balance difference: `-0.000002 kg`, unchanged, PASS.

Python / REST / CLI / actual MCP stdio / actual TCP Streamable HTTP all returned
the new canonical hash. Fresh isolated PostgreSQL execution saved 207 rows and
repeated create reused run 1. No production deployment was performed.

## Persistence compatibility and operational consequence

`share_text` and old result_hash are not reserialized during reload. Actual pre-fix
PostgreSQL run 1 from the old Streamable HTTP acceptance DB was read without authority
through get/list/daily and transports after this fix; its old historical hash and
all share strings remained intact. Synthetic SQLite and PostgreSQL tests cover long
legacy strings alongside canonical new rows, fresh-session reload and idempotency.

**Existing execution identities still return their old immutable run.** A repeated
create with the same request/policy/authority does not create a canonical replacement,
even after this fix. New execution IDs use the new serializer; historical IDs retain
their original result. This is intentional: request_hash semantics must not change.
No rewrite, delete, migration, background job or implicit rerun is introduced.

## Verification and remaining dependency

Private new artifacts: `blueberry-area-yield-artifacts/canonical-share-p1/` contains
before.json, after.json, request.json, legacy-readback.json and integration receipts.
No private full authority, curve or saved-run payload is committed to Git.

The 17 new unit/SQLite/PostgreSQL cases cover context isolation, finite/nonnegative,
fixed formatting, half-even ties, representative ULPs, perturbation result identity,
unchanged compose inputs/kg, legacy reload and canonical new idempotent persistence.
Related product, persistence, MCP, REST/CLI, Core/Agent/trial and empirical regressions
are executed with PostgreSQL enabled. Exact-head CI is recorded in the PR terminal
verification receipt, not taken from an older PR.
Local result: **1018 passed / 140 warnings** (PostgreSQL enabled); Ruff check,
format check (1025 files), Mypy (440 source files), JSON/artifact hash/diff PASS.
The original authority, #621 saved-run and 179 earlier artifact hashes were rechecked.

Required remaining input: the **five actual server share strings paired with dates
and historical share strings**, or the original server result payload with hash 72b5… .
Searched current repository docs/tests, historical artifact filenames and Downloads;
only the historical #621 payload was found. A specific asynchronous request for this
input was made. No guessed/reconstructed server artifact is used.

BUSINESS_FORECAST_CHANGED=false
AUTHORITY_CHANGED=false
MODEL_CHANGED=false
PREDICTED_KG_CHANGED=false
PEAK_CHANGED=false
SHARE_SERIALIZATION_CHANGED=true
SHARE_CANONICAL_SCALE=15
SHARE_ROUNDING=ROUND_HALF_EVEN
FORENSIC_PAIR_REGRESSION=AWAITING_ORIGINAL_SERVER_VALUES
READY_ELIGIBLE=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
