# Workpaper: C03 canonical shift semantics correction R2

## Scope and stop conditions

This workpaper records a code-level equivalence audit and fail-closed
correction for C03. It does not execute a candidate, read VALIDATION rows,
write the durable ledger, or access TEST. The prior R1 evidence remains
immutable historical evidence; this workpaper is the current correction.

## 1. Production reference

The production reference is:

```text
train_maturity_curve
  -> _resolve_training_sample
  -> _build_shift_model
  -> _predict_shift_days
  -> forecast_natural_maturity
```

The canonical shift target is the observed peak day relative to the parent
curve artifact peak day. The learned model uses the five numeric features
`altitude_m`, `tree_age_years`, `pruning_offset_days`,
`flowering_peak_offset_days`, and `first_pick_offset_days`, plus `facility_type`
categorical encoding. It performs the production imputation, scaling, Ridge
fit, and symmetric bound construction. Prediction evaluates that learned
model and clamps its output to the artifact bounds.

## 2. Why SOURCE-002 is insufficient for canonical equivalence

The historical SOURCE-002 materialized row is a historical business-grain
record with dates, actual quantities, and lineage identity. It is not a
resolved `ResolvedTrainingSample` and does not contain the production parent
curve artifact or the canonical feature authorities.

In the current production code, `_resolve_training_sample` obtains the
required values through analytics/build, production-plan, location-reference,
base-temperature-search, and weather mapping/observation authorities. Those
dependencies are part of the canonical sample-construction boundary. No
evidence authorizes deriving them from row identity, first harvest date, a
curve peak, or another approximation.

Therefore a new SOURCE-002-only C03 scorer cannot claim equivalence merely by
changing a bound on a custom model. Extracting a pure primitive without also
having the canonical resolved inputs would change the execution semantics, so
no primitive was extracted in this correction.

## 3. Prototype downgrade

The existing group/variety peak-delta implementation is retained only for
isolated prototype fixtures. It is not the production learned shift model and
is not an S4 execution authority. The authority-bound builder fails closed with
`C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY`.
The previous synthetic identity-difference checks are not treated as proof of
canonical parameter effect.

## 4. Plan eligibility versus runnability

The corrected audit keeps the V2 plan overlay independent from current
execution readiness:

| Candidate | V2 plan overlay | Current V4 runnable | Current reason |
| --- | --- | --- | --- |
| 01_parameter_calibration | eligible | false | CANDIDATE_01_RERUN_FORBIDDEN |
| 02_quantile_calibration | eligible | false | NO_V2_BOUND_PREDICTION_QUANTILE_PATH |
| 03_phenology_offset | eligible | false | C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY |
| 04_yield_parameter | eligible | false | C04_EXHAUSTED_EVIDENCE_INSUFFICIENT |
| 05_marketable_rate | eligible | false | NO_BOUND_CANDIDATE_05_SCORING_PATH |
| 06_weather_response | false | false | C06_WEATHER_OUTSIDE_V2_HISTORICAL_POLICY |
| 07_harvest_efficiency | eligible | false | NO_BOUND_CANDIDATE_07_SCORING_PATH |
| 08_residual_feature | false | false | V2_HISTORICAL_ONLY_FEATURE_MANIFEST_REQUIRED |

Thus `NEXT_EXECUTABLE_CANDIDATE=NONE`. This is a readiness result, not a
request to alter the V2 plan or to consume budget.

## 5. Frozen governance and safety facts

The C03 semantic, single allowlisted path, excluded forecast-time adjustment,
four owner-frozen values, and incumbent value remain unchanged. C04's
exhausted-evidence status remains unchanged. No V1/V2/V3/V4 policy hash is
rewritten and no historical evidence is replaced.

The current durable facts remain `4` legacy debit, `4` canonical started,
`8` effective consumed, and `24` remaining. This correction creates no
STARTED or terminal event. TEST remains sealed.

