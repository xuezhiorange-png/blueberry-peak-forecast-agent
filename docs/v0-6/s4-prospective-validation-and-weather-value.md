# V0.6-S4 Prospective Validation and Weather Value

`TASK_ID=V0_6_S4_PROSPECTIVE_VALIDATION_AND_WEATHER_VALUE_ASSESSMENT_R1`

## Scope

S4 consumes the immutable S1/S2 forecast snapshots and the immutable S3
evaluation authorities. It builds an auditable prospective-eligibility
registry, separates forecast-quality metrics from weather-incremental-value
diagnostics, and persists an immutable assessment. It does not train, tune,
replace, or promote a weather-aware model.

The existing actual-harvest import/commit authority remains the only source of
actual harvest facts. S4 accepts actual records through that adapter and never
creates a second actual-harvest store.

## Frozen Model A

```ini
MODEL_A=AREA_PLUS_HISTORICAL_HARVEST
TOTAL_MODEL=BASE_AWARE_BASELINE_R1
TEMPORAL_REFERENCE_MODEL=AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE
MODEL_STATUS=EXPERIMENTAL
MODEL_A_RETRAINED=false
MODEL_A_TUNED=false
```

The application validates every persisted forecast snapshot against these
identities. The assessment model hash also binds the snapshot-level artifact
hash mapping, so a model-authority change produces a different assessment
identity rather than silently mixing evidence.

## Prospective eligibility

A forecast run is eligible only when all of the following are proven:

- it is an immutable `SHADOW` forecast with input and result hashes;
- the persisted area revision is Base-bound, visible at the forecast cutoff,
  and season-compatible for non-reference area types;
- every referenced ECMWF forecast snapshot is Base-bound and satisfies the S1
  as-issued visibility rule;
- referenced phenology observations are for the same Base and target season
  and were known no later than forecast creation;
- actual harvest observations are known by the evaluation cutoff and were
  observed strictly after forecast creation.

Missing matured actuals produce an explicit `ACTUAL_NOT_MATURED` reason. A
historical-looking fixture or retrospective reconstruction is never promoted
to prospective evidence.

## Weather boundary

Only the persisted S2 forecast-time ECMWF snapshots are used for S4 weather
diagnostics. Realized weather is never a Model B input. Forecast quality and
incremental value are separate outputs:

- quality is read from the S3 forecast-versus-realized-weather evaluation;
- incremental value is descriptive residual association by D1/D3/D7/D15,
  with deterministic per-Base ordering and cross-Base direction reporting.

`GDD_INCREMENTAL_VALUE_STATUS` remains
`NOT_EVALUATED_DEFINITION_NOT_FROZEN`; S4 does not invent a base temperature or
GDD policy.

## Evidence sufficiency

No minimum business sample threshold is frozen in V0.6. The persisted
assessment reports run count, Base count, daily-row count, complete/partial
season counts, horizon sample counts, coverage groups, and an explicit
recommendation. When the current authority has not matured actual harvest,
the result is:

```ini
REAL_PROSPECTIVE_VALIDATION_STATUS=INSUFFICIENT_MATURED_PIT_EVIDENCE
WEATHER_INCREMENTAL_VALUE=INCONCLUSIVE
V0_7_WEATHER_MODEL_RECOMMENDATION=INSUFFICIENT_EVIDENCE
```

This state is distinct from fixture acceptance. Fixtures prove the contracts
and deterministic calculations only; they are not prospective business
evidence.

## Persistence and determinism

`prospective_validation_run` stores the eligibility registry, S3 evaluation
identities, Model A identity/hash, weather authority hashes, sample scope,
coverage summary, separated metrics, evidence sufficiency, conclusion,
recommendation, warnings, and canonical payload/result hashes.

`weather_incremental_value_assessment` is an immutable projection of the same
S4 assessment. Both tables use database immutability guards. Replaying the
same authority and policy returns the same hashes; a changed authority, policy,
weather identity, or eligibility decision produces a new identity or fails
closed on conflict. The repositories are flush-only and leave transaction
ownership with the caller.

## Out of scope

S4 does not implement weather-model training, ablation-driven promotion,
prospective production deployment, V0.7, UI, MCP, model tuning, or forecast
release authorization.
