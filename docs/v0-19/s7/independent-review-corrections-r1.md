# S7 independent-review corrections R1

Task: `V0_19_S7_INDEPENDENT_REVIEW_CORRECTIONS_R1`.
Reviewed baseline: `9cff28b7a54fb97791033a2fe8a0effd30c2a269`, existing Draft PR #757.
This is a three-finding correction, not new forecasting research, approval
infrastructure, model training, promotion or deployment.

## Comparison admission before arithmetic

Both sides must be computed and have matching Base, season, known feature
observation basis, model ID/parameter hash and known training/forecast target
basis. Unknown/null physical bases are not equality evidence. Incomplete models
remain `NOT_COMPUTABLE`; failed comparability returns `NOT_COMPARABLE` with
specific reasons, without window or common-date numerical deltas.

The frontend renders differences only for `COMPARABLE`. Its response schema
rejects numerical-delta fields on either non-comparable status. The original
14-date legitimate comparison remains available and unchanged.

## Four separate physical meanings

* `feature_observation_quantity_basis`: prior observation input, not the target.
* `model_training_target_quantity_basis`: frozen training-label meaning.
* `forecast_target_quantity_basis`: predicted quantity's meaning.
* `evaluation_label_quantity_basis`: independently admitted review labels only;
  null before review, never inferred from observed features.

`REAL_FROZEN_S6` retains the frozen 2023–2024/2024–2025 training contract's
`RECORDED_INBOUND_WEIGHT` target (see `v019_origin_features.py`). Its restored
parameter pair receives metadata only; coefficients, scales, feature order,
Ridge predictor and rounding are unchanged. A conflicting ModelReference target
is rejected. No observation field can relabel this target as field harvest.
Synthetic model fixtures declare their test target explicitly and remain marked
`SYNTHETIC_TEST_FIXTURE`.

Review checks forecast/training target against the label basis **before** label
quantity reads. Missing/unproved target identity, mismatched sources, or use of
a synthetic fixture against real labels returns
`CROSS_SOURCE_TARGET_BASIS_UNVERIFIED`. No conversion factor, calibration or
physical-equivalence authority is fabricated. The existing field-weight I5/I7
adapter is not expanded into an inbound-weight importer. Synthetic matched-basis
review still exercises the unchanged S1 arithmetic; it proves no real accuracy.

Legacy saved results are not rewritten. Missing target metadata remains unknown
and cannot qualify for comparison or scoring. New metadata participates in the
existing input/result digests, so new hashes may differ although numerical
predictions are unchanged. Historical expected hashes and evidence stay intact.

## Independent persisted-row verification

Canonical reload still checks identity, input/result hashes and exact daily-row
parity. It additionally verifies 15 consecutive D+1…D+15 rows for each computed
model, then independently recomputes H7/H15 totals, single-day maxima and every
complete rolling-seven window from database Decimal quantities. Chronological
ordering preserves earliest-date/earliest-start ties. Every summary field and
window scope is compared; no saved summary or Ridge rerun substitutes for this.

Wrong summary: `ROLLING_PERSISTED_METRIC_MISMATCH`; invalid support/count/order:
`ROLLING_DAILY_CALENDAR_MISMATCH`. Existing row-parity errors retain
`ROLLING_DAILY_ROW_MISMATCH`. No complete success response is released on error.
The PostgreSQL negative test deliberately makes a wrong summary internally
hash-consistent while preserving correct daily rows: old code accepted HTTP 200,
new code returns HTTP 409 with no committed ghost run.

## Actual local execution evidence

Before implementation, the isolated real PostgreSQL/ASGI run recorded 9 failures,
37 passes, zero errors/skips; frontend probes recorded 2 failures and 6 passes.
The original logs are preserved, not relabeled green. A direct execution of the
reviewed Git `compare` function also confirmed both NOT_COMPARABLE models still
returned `windows` and `common_target_daily_delta_kg`.

Post-fix results:

| Execution | Actual result |
| --- | --- |
| S7 backend, including real PostgreSQL/ASGI authorization | 68 passed, 0 failed/skipped |
| Focused original S4 + S7 TLS browser regression | 30 passed, desktop/mobile |
| Complete existing Playwright suite | 188 passed, 0 failed/errors/skipped |
| Frontend Unit | 168 passed |
| Related immutable-history contracts | 112 passed |
| Ruff / format / Mypy; frontend lint / typecheck / format / build | PASS |

Run roots: `/tmp/SYNTHETIC-s7-review-red-r1-20261023`,
`/tmp/SYNTHETIC-s7-review-green-r1-20261024`,
`/tmp/SYNTHETIC-s7-review-full-e2e-r1-20261024`, and
`/tmp/SYNTHETIC-s7-review-r1-4HAvnq`. Original source/test snapshots are retained
outside Git under the last root. Early local bootstrap attempts rejected a
non-SYNTHETIC output basename or missing module path before execution; neither
guard was weakened. All owned PostgreSQL runs report verified directory identity,
STOPPED, absent postmaster and closed listener. The full browser wrapper also
records actual SIGTERM exit, completed lifespan shutdown and a closed socket.

Unchanged M1 test-model business quantities:

| Origin | H7 kg | H15 kg |
| --- | ---: | ---: |
| 2026-11-05 | 538.941049 | 1031.362335 |
| 2026-11-06 | 526.137595 | 1002.702182 |

Window deltas remain -12.803454/-28.660153 kg; all 14 common-date deltas remain
+0.021275 kg. These are synthetic business acceptance values, not real accuracy.

The exact existing real S6 model and its pinned execution manifest were also
restored in two independent processes on synthetic observations. Daily values,
H7/H15, peaks, fit and parameter hashes match the pre-correction probe exactly;
only provenance metadata/source identity changes. Compact numerical receipt
SHA256: `a97312011d110812e05afb5cd81a1a63c272515738d4cc52695e2de22e3654f9`.
No private parameters or harvest rows are published.

No real/current-season labels were read or scored. Frozen research code, model
files, migrations, CI, dependencies and old evidence are unchanged. Final PR
exact-head CI is post-commit external evidence, not predeclared here. PR stays
Draft pending independent reassessment; Ready/Merge/Release/Deploy remain false.
