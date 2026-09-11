# Workpaper — C03 historical-only scorer readiness R1

## Scope and authorization

`TASK_ID=V0_3_S4_C03_HISTORICAL_ONLY_SCORER_READINESS_R1`

This workpaper covers implementation and readiness evidence only. It does not
authorize or perform a C03 run.

```text
REAL_VALIDATION_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_AUTHORIZED=false
TEST_AUTHORIZED=false
CANDIDATE_EXECUTION_PERFORMED=false
VALIDATION_SCORING_PERFORMED=false
```

## Frozen binding

```text
OWNER_DECISION_ID=V0_3_S4_C03_PHENOLOGY_OFFSET_SEMANTIC_DECISION_R1
C03_SEMANTIC=TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND
C03_ALLOWED_PARAMETER_PATH=offset.maximum_abs_shift_days
C03_EXCLUDED_PARAMETER_PATH=forecast.observed_phase_adjustment_max_days
C03_RUN_VALUES=14,18,24,28
C03_INCUMBENT_VALUE=21
PLANNED_RUN_COUNT=4
ADAPTIVE_SEARCH_ALLOWED=false
POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED=false
```

The manifest is V2/V4-bound. The prior V1 manifest is rejected by the new
validator and remains available only for historical replay/audit.

## Input and leakage boundary

The exact SOURCE-002 identities are bound in the machine-readable evidence:

```text
MATERIALIZED_DATASET_IDENTITY=f537b0848465437cf9c504387de00bf70797debfe89fb6a85630b6086a484785
TRAIN_ROWS=16224
TRAIN_CONTENT_SHA256=be2d4184434a0f389af21c315945322e9216cd17cc471b772e3fff389d3386d2
VALIDATION_ROWS=8006
VALIDATION_CONTENT_SHA256=4cbf1119f83034464159210ebbbeea5ec87848f92ce044bb328949a8f5331d06
FORECAST_CUTOFF=2026-01-30
EVALUATION_TARGET_ROWS=688
FORECAST_HORIZONS=7,14,21
TEST_REMAINS_SEALED=true
```

Validation target rows may provide dates and business-grain identities for a
future projection surface. Their actual quantity is masked before training
model construction. No validation actual is used for fitting, shift learning,
parameter selection, or prediction. TEST bytes are not loaded.

## Scorer path

The scorer is `C03HistoricalPhenologyScorer` in
`backend/app/s4_candidate_03_historical_phenology.py`.

It fits normalized group/variety maturity curves with the shared
`fit_shared_curve` primitive, learns group peak deltas against the variety
parent curve, stores the learned shift in a `ShiftModelArtifact`-shaped object,
and applies the candidate symmetric bound before shifting/normalizing the
curve. The future projection uses only row identity/date and the immutable
TRAIN-derived model. This is the historical-only form of the shift model;
production `forecast_natural_maturity` is intentionally not used because its
resolver reads forward-looking operational authorities.

The synthetic effect fixture proves:

```text
prediction_identity(14) != prediction_identity(21)
prediction_identity(18) != prediction_identity(21)
prediction_identity(24) != prediction_identity(21)
prediction_identity(28) != prediction_identity(21)
```

The proof is deterministic and does not calculate validation metrics.

## Gate/readiness proof

`build_c03_v4_gate_request` constructs a complete shared-gate request with the
V2 plan, V4 policy, sparse surface, all pairing identities, frozen manifest/run
hashes, registry, fixed seed, and sealed TEST fields. The shared gate accepts a
pure future request. No durable execution method is imported or called by the
C03 readiness module.

Future evidence reuses the merged coverage-quality contract. The synthetic
round trip preserves all six required axes and cell reason codes; missing
`reason_code` is rejected closed by the canonical serializer/parser contract.

## Audit and closure

C03 is now the only current V4 runnable candidate in the compatibility audit.
C04's historical scorer remains visible for audit, but its current execution
eligibility is closed because the four-run budget is exhausted and the original
evidence lacks cell-level provenance. C01 rerun remains permanently forbidden;
C06 and C08 remain historical-policy blocked.

## Durable state and stop gate

The budget PostgreSQL database was read only. Readback was:

```text
AUTHORITY_VERSION=8
ACCEPTED_EVENT_COUNT=8
ACCEPTED_STARTED_COUNT=4
ACCEPTED_LAST_GLOBAL_EVALUATION_ORDINAL=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
C03_CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=8
REMAINING=24
LEDGER_WRITES_PERFORMED=0
```

No candidate execution, validation scoring, TEST access, selection, promotion,
Ready, or Merge was performed. Final stop gate:

```text
COORDINATOR_V0_3_S4_C03_HISTORICAL_ONLY_SCORER_READINESS_REVIEW
```

