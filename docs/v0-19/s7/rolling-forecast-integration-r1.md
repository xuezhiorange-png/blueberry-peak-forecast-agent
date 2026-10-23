# V0.19 S7 — controlled rolling forecast shadow

Task: `V0_19_S7_ROLLING_FORECAST_ENGINEERING_INTEGRATION_R1`.
Base: `82682ac364e492b8cd29cd80014002c991238f42`.

This is manual research-shadow issuance, persistence and business application,
not a production model promotion, a scheduler or a future accuracy validation.
No current 2026–2027 actual harvest records were read, imported or scored.
The example season below is explicitly **SYNTHETIC**.

## Reuse and narrow additions

| Existing capability | S7 use |
| --- | --- |
| S6 `compile_pair` / `restore`, V0.15 `RidgeArtifact.predict` | Restore sealed M0/M1; no fitting, parameter search or second solver |
| V0.15 `FEATURES`, `valid_day`, Base10 `_base_feature_values` | Frozen feature definitions, eligibility and numerical inputs |
| V0.15 four-window aggregation block | Thin explicit-calendar bridge, guarded against fixed historical Git source on three seasons; historical V0.15 source remains unchanged |
| I5 import/commit/attestation + I7 immutable snapshot/revision winners | Read-only exact source/member/date adapter; no importer or second actuals table |
| Local Auth sessions, CSRF, PostgreSQL account admission locks | Authenticate and reauthorize before business reads and through ASGI response release |
| Existing Dashboard Forecast page, request client and session boundary | Separate shadow panel and state, not another site or formal ForecastIdentity |
| Frozen S1 ten-metric arithmetic and S6 peak calculation | Independent mature-label review, exact Decimal denominators and window-scoped peaks |

Existing Operational Peak, Area Forecast and Core Forecast records cannot
safely express two research point models with no approved P50/Upper80/Upper90
or production identity. Alembic `0041_rolling_shadow_forecast` therefore adds
only `rolling_forecast_run` and `rolling_forecast_daily`. Append-only database
triggers reject updates/deletes. No observation or new authorization tables.

## Frozen model and runtime calendar

The operator registers an explicit absolute, non-symlink model file, SHA256,
fit hash, source code identity, original code SHA and (for real S6 artifacts)
the independently hash-pinned original Phase A manifest. No directory scan,
training or historical-label reader exists in this loader. Missing assets return
`MODEL_ARTIFACT_UNAVAILABLE`; inconsistent assets return
`MODEL_IDENTITY_MISMATCH`. Both model identities, feature order, alpha=10,
standardization and finite restored parameters are checked.

The runtime takes explicit sourced Base, season calendar, effective area in mu,
origin D and timezone-aware cutoff. It does not relabel a future season as a
frozen historical season. Observations must have `business_date < D`; targets
are D+1 through D+15. The first seven days are H7, not a separately fitted or
renormalized curve. Frozen Ridge inference and HALF_EVEN six-place kg output
are unchanged. No artificial dynamic adjustment coefficient is added.

## Observation authority and physical/time boundaries

The server catalog binds exact I7 snapshot hash, source system, registry hash,
season/farm/subfarm/variety members, membership authority, complete dates and
separate confirmed-zero authority to one Base. Ambiguous cross-Base mappings
are rejected. A missing member/day is never implicitly zero.

The adapter verifies snapshot winner membership and individual winner/committed
record hashes. SQL selects quantities only for authorized members and prior
dates. Trusted source-recorded, server-ingested and commit times must all be at
or before cutoff. Completeness evidence must also be known at cutoff. A late
winning revision yields incomplete input; it cannot rewrite an earlier run.

The existing I5/I7 attestation currently supports `FARM_PICK / OBSERVED_WEIGHT /
KG`. This bridge admits it explicitly as `FIELD_HARVEST_WEIGHT`; it does **not**
reinterpret SOURCE_002 inbound net weight as field harvest or marketable fruit.
Other source semantics need a separately justified adapter, not a changed label.

Four features retain the frozen 7/14/28-day and season-to-date rules. UNKNOWN,
PARTIAL, MISSING and CONFLICTING never become zero. Incomplete history blocks
M1; M0 may remain an explicitly named control. No M0 result is called M1.
Historical dates alone do not prove availability: date-bound execution remains
`RETROSPECTIVE_DATE_BOUND`. This delivery does not certify STRICT_PIT even for
the synthetic trusted-timestamp path. Real current-season sources are denied.

## Controlled application and API

Default configuration is disabled (`rolling_forecast_catalog_path=""`). A
private operator-owned catalog registers exact resources and expiring,
principal/auth-revision/grant-revision-bound operations. Existing organization
authority is checked. No wildcard, implicit admin privilege, public file path,
new role-management API or inheritance from a formal Saved Run grant is added.
It is deployment resource wiring, not an independent authorization platform.

All calls use existing login/session/CSRF. Account revocation is synchronized
with the existing PostgreSQL shared/exclusive lock protocol. The catalog is
freshly read and fingerprint-checked again before response bytes; no claim is
made about cross-host atomic file-policy revocation.

| Route | Purpose |
| --- | --- |
| `POST /api/v1/rolling-forecast-runs` | Manually compute, persist and reload exact input snapshot |
| `GET /api/v1/rolling-forecast-runs` | Authorized history, Base/season/origin filters and bounded pagination |
| `GET /api/v1/rolling-forecast-runs/{id}` | Owned authorized immutable run |
| `GET /api/v1/rolling-forecast-runs/{id}/daily` | Saved daily curve and model identities |
| `GET /api/v1/rolling-forecast-runs/compare` | Two explicit authorized run IDs |
| `POST /api/v1/rolling-forecast-runs/{id}/review` | Separate mature-label authorization, not part of prediction |

Idempotence uses principal + canonical input hash and a PostgreSQL transaction
lock. Source, authority, model, features and runtime implementation identity
participate in the immutable input. A changed input creates a new run. Reload
verifies header identity, input/result hashes and exact daily rows. Research
`issued_at` stays null; actual creation time is not backdated.

Compare labels changing-window H7/H15 totals separately from common-target-day
revisions. Incompatible Base/season/basis/model assets are NOT_COMPARABLE, not
a fair accuracy ranking. H15 rolling-7 is local to those 15 dates only.

Independent review requires a registered, mature, same-basis label snapshot and
separate `evaluate` permission. It loads only D+1..D+15 and uses the same
computable model/date cohort. S1's ten metric definitions remain unchanged;
full-season WAPE is not available. BIAS is an additional signed mean kg error,
with numerator and day count, matching forecast-quality's `daily_bias_kg`
definition without fabricating P50 or farm-grain identities for point H15 data.
Per-Base matched-MAE outcome and NC reasons are explicit. All-zero actual peak
timing remains not computable; H7 rolling-start zero is structurally trivial.

## Usable Dashboard flow

On the existing Forecast page, use **查询研究预测**, select authorized resource,
origin and cutoff, then **生成并保存研究预测**. M0/M1 have distinct IDs, status,
physical basis, totals, 15 daily values/curve and peaks. Select saved runs and
two IDs for comparison. Mobile tables scroll rather than changing business
quantities. SVG floating coordinates are display-only, never business math.

Cancellation, account switching, logout, security revision or changed inputs
prevent late responses restoring old results. A shadow 403/409 clears shadow
state without revoking an unrelated formal Forecast context; a 401 retains the
existing global session invalidation. No production default model is changed.

## Executed synthetic business example

The actual I5 lifecycle → I7 snapshot → ASGI login/CSRF → frozen test Ridge →
PostgreSQL save/reload → two-origin comparison → separate synthetic-label review
ran with Base `SYNTHETIC_BASE`, 100 mu. These are computed test values, **not
real current-season predictions**.

| M1 origin | H7 kg | H15 kg | Single-day peak | H15 rolling-7 start |
| --- | ---: | ---: | --- | --- |
| 2026-11-05 | 538.941049 | 1031.362335 | 2026-11-06 / 81.981374 kg | 2026-11-06 |
| 2026-11-06 | 526.137595 | 1002.702182 | 2026-11-07 / 80.649834 kg | 2026-11-07 |

Changing-window deltas are −12.803454 kg (H7) and −28.660153 kg (H15).
On the 14 common target dates, each M1 daily revision is +0.021275 kg.
For the first origin, synthetic-label matched daily WAPE is
M0/M1 0.925621814286 / 0.924789460714 (H7) and
0.563083701515 / 0.562670204545 (H15); actual denominators are 280 and 660 kg.
Only one synthetic Base is assessed: both window MAE outcomes improve, not a
real-model performance claim. Removing prior completeness blocks M1 while
retaining the explicitly labeled M0 control and no M1 daily rows.

An additional authorized S6 real frozen artifact positive-load/inference probe
ran on synthetic observations only, twice in independent processes. The model
file hash was `352a618ffbd970adf8ce896cd6aa70513d931786a1c3150cd158e232e7c4848e`;
fit hash `34311a7c3bea5b5306bb30e562fcccc94c15027a52a03f7fb3dc4b25f039d9c1`.
Low synthetic progress produced clipped zero forecasts for both models. This
proves restoration and deterministic inference, not useful yield or accuracy.
Private parameters and training rows are not published. Proof bytes SHA256:
`75a4bdfe8091327014daac2cb1e92b06797deb222fde599d77621bcd60d74543`.

## Reproduction and limitations

Local acceptance on 2026-10-23: S7 33 tests (including real PostgreSQL), full
Playwright 188 tests across desktop/mobile, frontend Unit 164, historical
Forecast Intelligence 1,029, and the separately isolated legacy-live PostgreSQL
50 all passed. The broad related run had 1,006 passes, 10 failures and 50 skips;
the failures were a missing local pip module, subprocess PATH and the S2
historical source boundary. Focused corrected reruns passed; all 50 skipped
tests were then actually executed with isolated DB identity and passed.
Area Yield had 2,541 passes and two missing-libomp failures; the complete
affected test file then passed all 42 after installing the local native runtime.
These are distinct run receipts, not a rewritten original all-green report.

Preserved local run roots: `/tmp/SYNTHETIC-s7-full-regression-20261023`,
`/tmp/SYNTHETIC-s7-related-corrected-20261023`,
`/tmp/SYNTHETIC-s7-legacy-live-20261023`, and
`/tmp/SYNTHETIC-s7-complete-local-e2e-v4-20261023` (33 backend / 188 browser).
The final root reuses the existing CI Trial seed and legacy test-only backend
alongside the controlled TLS applications; it does not mount the legacy test
entry in production. Each owned PostgreSQL cluster reports STOPPED with absent
postmaster and closed listener. Earlier misconfigured local E2E attempts remain
archived, including the explicitly cancelled one; they are not PASS.

The v4 browser JUnit itself has 188 passes and no failures/errors/skips. Its
ad-hoc local wrapper exited 1 because it required the unmodified legacy Uvicorn
process to exit 0 after SIGTERM. The original wrapper receipt is preserved:
the actual log records completed lifespan shutdown and finished PID, and a
separate socket check confirms the listener is closed. This bookkeeping failure
is not relabeled a green wrapper run or hidden in the browser count. The final
S7 smoke records the actual return code, shutdown log and closed socket; the
tracked owned-HTTPS lifecycle assertions are unchanged.

Vite's existing API proxy also includes the finite rolling-run prefix, so the
same dashboard client works in the usual local development composition. This
does not widen the production ingress allowlist to legacy trial routes.

With locked Python 3.12 dependencies, PostgreSQL 16 tools and Node on PATH:

```sh
python -m backend.tests.rolling_forecast.run --output /tmp/SYNTHETIC-s7-new-run --browser
```

This reuses the S5 owned PostgreSQL/SIGTERM/exit verification protocol and runs
S7 plus original S4 HTTPS browser flows, on desktop/mobile. Full existing E2E
and related auth/revocation/OP/Core regressions are separately verified. The
optional `backend.tests.rolling_forecast.frozen_inference` probe takes only an
explicit hash-pinned ModelReference on stdin and always synthesizes observations;
it does not read actuals or fit a model.

Historical source assertions affected by legal integration edits are checked
against their original, individually verified fixed Git bytes. Original expected
Hash values, JSON, assertions and frozen evidence are not rewritten. Current
runtime tests still exercise the changed source; old source hashes do not stand
in for new behavior acceptance.

Real input enrollment, actual field coverage, reliable source availability,
prospective accuracy, model promotion, production rollout and unattended
scheduling remain outside this delivery. No Ready, Merge, Tag, Release or Deploy
is performed. PR exact-head results are external post-commit evidence, never
predeclared by this document.
