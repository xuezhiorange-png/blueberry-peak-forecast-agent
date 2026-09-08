# S4-C03 phenology-offset execution-ready workpaper R1

## Scope and decision

This workpaper records the control-plane preparation for
`03_phenology_offset`. It does not record a candidate result. The owner
decision `V0_3_S4_C03_PHENOLOGY_OFFSET_SEMANTIC_DECISION_R1` resolves the
previous semantic ambiguity:

```text
C03_SEMANTIC=TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND
C03_ALLOWED_PARAMETER_PATH=offset.maximum_abs_shift_days
C03_EXCLUDED_PARAMETER_PATH=forecast.observed_phase_adjustment_max_days
```

The production maturity implementation uses `offset.maximum_abs_shift_days`
when constructing the learned shift model bounds. The
`forecast.observed_phase_adjustment_max_days` setting is a distinct
forecast-time observed-phase adjustment bound. It is not part of C03 and any
change to it is rejected as an unauthorized parameter path.

## Incumbent authority

The manifest binds the complete current `configs/maturity_curve.yaml` snapshot,
its file SHA256, and the existing configuration hash. The bound values are:

```text
offset.maximum_abs_shift_days=21
offset.minimum_training_samples=3
forecast.observed_phase_adjustment_max_days=14
```

The candidate builder deep-copies the incumbent snapshot and constructs an
immutable in-memory `MaturityCurveConfig`; it never writes the incumbent YAML.
Full snapshot comparison proves that the only changed path in each candidate
run is the owner-selected offset bound.

## Frozen four-run manifest

The run order and values are owner-frozen before any validation execution:

```text
RUN_1=14
RUN_2=18
RUN_3=24
RUN_4=28
PLANNED_RUN_COUNT=4
ADAPTIVE_SEARCH_ALLOWED=false
POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED=false
RANDOM_SEED_POLICY=FIXED_AND_RECORDED_PER_RUN
RANDOM_SEED=20260624
```

The incumbent value `21` is not included as a candidate run. C01 historical
metrics remain audit-only and were not used to select or tune these values.
Each run has a candidate configuration hash and a run-level parameter manifest
hash. The whole manifest hash also binds the owner decision, registry entry,
allowlist, exclusions, snapshot, run order, and policy flags.

## Durable authority and preflight

The C03 request builder reuses the frozen S4-A registry and S4-B gate. It
requires real canonical identities for the TRAIN dataset, VALIDATION dataset,
actual labels, exclusion policy, cutoff policy, forecast horizons, business
grain, common comparable set, and metric contract. Placeholder identities are
rejected.

The future execution seam is bound to
`S4CandidateExecutionAuthority`:

```text
verified PostgreSQL state
  -> S4-B gate
  -> EVALUATION_STARTED append with expected CAS state
  -> transaction commit
  -> fresh verified readback
  -> scorer/model callback
  -> terminal append
```

The global gate count is PostgreSQL `effective_consumed`, not the canonical
STARTED row count. At this freeze point:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
C03_CANDIDATE_STARTED_COUNT=0
C03_NEXT_RUN_ORDINAL=1
NEXT_CANONICAL_GLOBAL_ORDINAL=1
```

No event was created and no budget was consumed by this task.

## Fail-closed runner

`scripts/run_v03_s4_c03_phenology_offset.py` is a readiness shell only. Its
normal CLI path returns:

```text
EXECUTION_STATUS=BLOCKED
REASON_CODE=CANDIDATE_EXECUTION_NOT_AUTHORIZED
VALIDATION_STARTED_CREATED=false
SCORER_CALLED=false
```

The internal execution seam still requires an explicit application-layer
authorization boolean and uses the shared durable authority. There is no CLI
`--authorize`, `--force`, `--skip-gate`, or equivalent bypass. The runner has
no replay/scoring import and cannot directly load validation data.

## Verification boundary

Focused tests cover registry binding, semantic decision binding, exact
allowlist and hostile mutations, full snapshot immutability, Decimal-only
canonical hashing, fixed run order, gate identity requirements, and default
runner blocking. The PostgreSQL acceptance tests are placed in the existing
`postgres-concurrency` test file so CI executes real commit, readback, CAS,
STARTED-before-fake-scorer, and failed-fake-scorer durability checks for C03.

No C03 validation scorer was called. C01 was not rerun. C02 was not executed.
TEST remains sealed. No migration, production model, production parameter, or
incumbent configuration file was changed.

## Evidence identity

The machine-readable evidence is:

`docs/v0-3/s4/evidence/s4-c03-phenology-offset-execution-ready-r1.json`

It records the deterministic manifest/run hashes and the unchanged 4-of-32
durable budget state. The status is:

```text
C03_CONTRACT=PASS
C03_MANIFEST=FROZEN
C03_RUNNER=READY
C03_DURABLE_AUTHORITY_BINDING=PASS
C03_EXECUTION_READY=true
C03_EXECUTION_AUTHORIZED=false
```
