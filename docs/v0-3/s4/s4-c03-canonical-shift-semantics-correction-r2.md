# S4 C03 canonical shift semantics correction R2

## Current disposition

This append-only correction supersedes the R1 readiness conclusion for current
execution. The C03 parameter semantic remains the training-time learned shift
model bound, but the existing C03 historical implementation is not the
production canonical shift algorithm. It is therefore retained only as a
non-canonical experimental prototype and cannot authorize or perform S4
execution.

The current terminal result is:

```text
RESULT=BLOCKED_AND_PUSHED
C03_CURRENTLY_RUNNABLE_UNDER_V4=false
C03_READY_FOR_REAL_VALIDATION=false
C03_BLOCKER=C03_CANONICAL_TRAINING_SHIFT_MODEL_NOT_SEPARABLE_FROM_FORWARD_LOOKING_AUTHORITY
NEXT_EXECUTABLE_CANDIDATE=NONE
```

No validation data was reread, no scorer was called, no durable execution was
requested, and no TEST data was accessed.

## Canonical production algorithm audited

The authoritative production path is the following sequence:

```text
backend.app.maturity.service.train_maturity_curve
  -> backend.app.maturity.service._build_shift_model
  -> backend.app.maturity.service._predict_shift_days
  -> backend.app.maturity.service.forecast_natural_maturity
```

`_build_shift_model` learns the target
`observed_peak_day - parent_curve_artifact.peak_day`. Its canonical training
features are `altitude_m`, `tree_age_years`, `pruning_offset_days`,
`flowering_peak_offset_days`, `first_pick_offset_days`, and `facility_type`.
The implementation applies its established imputation, scaling, categorical
encoding, and Ridge fit before emitting `ShiftModelArtifact`; the configured
`offset.maximum_abs_shift_days` becomes the symmetric artifact bound. The
predictor then evaluates the learned feature vector and clamps the learned
shift to those bounds.

The training samples are produced by `_resolve_training_sample`, not by the
SOURCE-002 materialized row alone. That resolution reads production
analytics/build authority, production-plan authority, location reference,
base-temperature search authority, and weather mapping/observation authority.
The current SOURCE-002 historical materialization supplies the historical
business grain, dates, actuals, and lineage identities, but does not supply
the canonical resolved sample inputs or parent curve artifacts needed by this
production shift model.

No lawful alias was accepted for those missing inputs. In particular, a first
harvest date is not substituted for a production anchor, business identities
are not substituted for Ridge features, canonical features are not removed,
and the observed group-peak delta is not substituted for the canonical learned
target.

## C03 disposition

The owner decision remains unchanged:

```text
C03_SEMANTIC=TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND
C03_ALLOWED_PARAMETER_PATH=offset.maximum_abs_shift_days
C03_EXCLUDED_PARAMETER_PATH=forecast.observed_phase_adjustment_max_days
C03_RUN_VALUES=14,18,24,28
C03_INCUMBENT_VALUE=21
```

The R1 V2 manifest remains available for audit and replay of its governance
contents, but it is not an execution authority. A V2-bound manifest may be
prepared for future use; it is marked unusable until a scorer using the
canonical production shift path and lawful historical inputs exists.

The former `C03HistoricalPhenologyScorer` group/variety peak-delta model is
explicitly classified as:

```text
C03_NON_CANONICAL_PROTOTYPE_STATUS=NON_CANONICAL_EXPERIMENTAL_PROTOTYPE
C03_NON_CANONICAL_PROTOTYPE_IS_EXECUTION_AUTHORITY=false
```

Its authority-bound construction now fails closed with the canonical blocker.
Synthetic prediction-identity tests are retained only as unit-level evidence
about the prototype and are not readiness proof.

## V2 candidate audit interpretation

The V2 plan eligibility overlay is distinct from current executable runnability.
Candidates 01, 02, 03, 04, 05, and 07 remain registered and historically
eligible under the V2 plan where their plan overlay says so; that does not
authorize a run. Candidate 01 remains permanently forbidden to rerun. Candidate
04 remains plan-eligible but currently unrunnable because its existing evidence
is exhausted and insufficient for selection. Candidates 06 and 08 remain
ineligible under historical-only V2 because they require forward-looking
weather/Task9 features.

For C03 specifically, the canonical production path is identified, but the
SOURCE-002-only input contract is not satisfied. Consequently both historical
only input compatibility and current V4 runnability are false. No candidate is
selected as the next executable candidate.

## Invariants

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
C03_CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=8
REMAINING=24
BUDGET_DELTA=0
NEW_VALIDATION_EXECUTION=false
NEW_VALIDATION_SCORING=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The historical C04 closure remains unchanged:

```text
C04_PLAN_EXECUTION_ELIGIBLE=true
C04_CURRENTLY_RUNNABLE_UNDER_V4=false
C04_RUNNABILITY_REASON=C04_EXHAUSTED_EVIDENCE_INSUFFICIENT
```

See the machine-readable [R2 evidence](evidence/s4-c03-canonical-shift-semantics-correction-r2.json)
for the complete audit payload.

