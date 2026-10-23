# V0.19 S6 origin-aware harvest research

Task: `V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1`.
Authorized main: `c3cb8095b55465745d85d12e46144cd6031a5dc6`.
The current Owner instruction authorizes bounded historical feature construction,
training, prediction and scoring, one research branch, one Draft PR and one final
exact-head CI. No production registration, model promotion, Ready or Merge.

## Frozen matched experiment, before scoring

M0=`BASE10_RIDGE_MATCHED_CONTROL`; M1=`BASE10_PLUS_HARVEST_STATE_V1`.
Reuse `v015_harvest_state.build_row`, `_base_feature_values`, `RollingTargetRow`
and `fit_ridge_artifact`. The four existing aggregates are not reimplemented.
Both models share training origins, targets, labels, scaler policy, solver,
evaluation members and per-metric denominators. M1 only adds the four frozen
Harvest State values. Base ID is an exact identity key, never a feature.

Ridge remains alpha 10, train-only population standard deviation, scale 1 for a
zero standard deviation, unpenalized intercept, `numpy.linalg.solve`, nonnegative
prediction. The original solver and trigonometric Base10 features use float64;
they are not replaced with a different estimator. Aggregates and S1 scoring use
Decimal precision 50; output kg is half-even quantized to six decimal places.
No search, validation-based selection, new adjustment coefficient or imputation.

A fits only 2023–2024 and validates 2024–2025. B refits the same configuration
on both historical training seasons and evaluates 2025–2026. The 37 admitted
Base-seasons are candidates, not a claim that every origin has 28 prior days.
Training uses complete 15-day targets and complete four-feature snapshots.
Short H7-only evaluation tails remain H7-only; no target dates outside the season.
All original A/B C0 members and failure records remain in the prediction and
scoring inventories, including the full 19,032-member B C0.

## Date and authority semantics

Origin D retains the V0.19 local end-of-day research cutoff, with targets D+1
through D+7/D+15. **All harvest inputs still require business_date < D**;
Existing C0 second-precision and microsecond-precision end-of-day timestamps
are validated and preserved verbatim, not rewritten into a new member identity.
the day's completed total is not assumed available at the cutoff. The V0.15
kernel's 17:00 timestamp is only an internal date-predicate bridge. Neither
timestamp is represented as historical issuance or source availability.

The frozen business season starts July01 in 2023–2024/2024–2025 and July22 in
2025–2026. `season_to_date` is not rebased to the V0.19 target start August05.
Unknown, partial, missing, conflicting and invalid days never become zero.
Only existing explicit observed/confirmed-zero authority is usable.

The V0.19 Owner Scope changed three Bases' source membership. For July22–August04,
old S6 daily authority can transfer only when the entire exact source-identity
member set equals the current Owner research set, member counts match, source
SHA matches SOURCE_002, and the frozen daily completeness/zero checks pass.
Changed-member Bases retain UNKNOWN prior days, even when the old overlay said
zero. This adapter does not rewrite or extend any historical authority. All
matches, mismatches, accepted/rejected prior days and reasons are private evidence.

The feature materializer explicitly reads already-exposed complete historical
sources, including the fixed SOURCE_002-derived report and bounded prior-day
authority. It emits only origin-specific aggregates, prior lineage, area,
calendar and admission metadata. Full-file provenance is in the outer manifest,
not a numerical dependence on future rows in each feature snapshot.
The predictor receives this feature projection plus legal historical training
labels; it has no full historical report path. A change to D or later quantities
cannot affect D's snapshot; D−1 changes are observable and tested.
This is application-path separation, not an OS label vault or never-exposed claim.

## Reference reliability audit

Use the frozen A/B profile files and their manifest-pinned training/input
metadata. A's original 9 Base-seasons and B's 34 are not the expanded V0.8
15/37 quantity-complete training population. The original train-row identities,
known-label subset, input ledger hash and Registry identity stay distinct.
No profile is refitted or selected using the exposed evaluation season.

Holding Base, area, dates and support fixed, calculate every bin's change,
nearest-available resolution, total kg, daily peak and rolling-seven peak.
The bin anchor stays July01; profile values are daily kg/mu, not seven-day mass.
With a shared profile multiplied by area, relative sensitivity is common except
micro-kg rounding; absolute kg sensitivity largely reflects area, not identified
biological heterogeneity. Profile source differences are not a causal season effect.

Historical recorded inbound kg versus SOURCE_002 inbound net weight remains a
conditional cross-source comparison, not proven physical equivalence. Historical
area known_at and source available_at remain NOT_PROVEN. Phenology simulation
code is not field observation; no verified management execution or as-issued
weather authority is supplied by these inputs. None enters M0/M1.

## Four execution stages

Use the existing locked Python 3.12 environment with
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`.
All outputs must be new explicit private directories (0700 / files 0600).

```sh
python -m backend.research.v019_origin_cli features \
  --owner-task V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1 \
  --artifact-root /absolute/authorized/artifact-root --output /absolute/new-run/features
python -m backend.research.v019_origin_cli predict \
  --owner-task V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1 \
  --features /absolute/new-run/features --output /absolute/new-run/a
python -m backend.research.v019_origin_cli verify \
  --owner-task V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1 \
  --features /absolute/new-run/features --predictions /absolute/new-run/a \
  --output /absolute/new-run/verification
python -m backend.research.v019_origin_cli score \
  --owner-task V0_19_S6_ORIGIN_AWARE_HARVEST_FORECAST_R1 \
  --artifact-root /absolute/authorized/artifact-root \
  --features /absolute/new-run/features --predictions /absolute/new-run/a \
  --verification /absolute/new-run/verification --output /absolute/new-run/b
```

`predict`/`verify` refuse an artifact-root argument and do not read target reports.
Independent verification refits and recomputes byte-identical models and curves
in a separate process, before score opens target sources. UTC execution times,
process IDs, exact command, source/code SHA and output hashes are receipts,
separate from deterministic model bytes. Old S3/S4/S5 results remain unchanged.

S1 ten-metric arithmetic is reused. Full-season WAPE remains NOT_COMPUTABLE.
Paired M0/M1 and static-on-common masks/denominators must match; static full-C0
context is also reported. All exclusions, zero-actual peaks and failures remain.
Static and Ridge families are not combined into a fair promotion ranking.
If quantity improves while peak-date errors worsen, the conclusion is MIXED.
Incomplete cohort coverage is explicitly conditional, not full-C0 success.

Private outputs include origin-feature-manifest.json, training-labels.json,
reference-profile-diagnostics.json, dynamic-model-fits.json,
dynamic-predictions.json, verification.json, dynamic-comparison.json,
report.md/report.html and computed SVG figures. Real values never enter Git.
`RETROSPECTIVE_DATE_BOUND`, `STRICT_PIT=false`,
`PRODUCTION_ACCURACY_VALIDATED=false`; no blind-test, deployment or promotion claim.
