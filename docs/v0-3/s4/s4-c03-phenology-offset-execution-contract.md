# S4-C03 phenology-offset execution contract

This document freezes the C03 control-plane contract before any validation
evaluation is authorized. It is an execution-readiness artifact, not a model
result and not a validation score.

## Owner decision

`OWNER_DECISION_ID=V0_3_S4_C03_PHENOLOGY_OFFSET_SEMANTIC_DECISION_R1` is the
semantic authority for this candidate. C03 means the training-time learned
phenology shift model bound:

`C03_SEMANTIC=TRAINING_TIME_LEARNED_SHIFT_MODEL_BOUND`

The production maturity implementation uses
`offset.maximum_abs_shift_days` as the symmetric bound passed to the learned
shift model. The forecast-time observed-phase adjustment bound is a separate
runtime rule and is explicitly excluded from C03:

`C03_ALLOWED_PARAMETER_PATH=offset.maximum_abs_shift_days`

`C03_EXCLUDED_PARAMETER_PATH=forecast.observed_phase_adjustment_max_days`

The incumbent remains `21` days. C03 may not modify the incumbent YAML file.
Each candidate configuration is an immutable in-memory snapshot derived from
that authority.

## Frozen run neighborhood

The four runs are fixed before validation execution and may not be adaptively
reordered or substituted:

| Candidate run | `offset.maximum_abs_shift_days` |
| ---: | ---: |
| 1 | 14 |
| 2 | 18 |
| 3 | 24 |
| 4 | 28 |

Every run changes exactly one path. `offset.minimum_training_samples`, all
forecast-time phase parameters, curve/pooling/holiday/interval parameters,
`model_family`, and `random_seed` remain equal to the incumbent snapshot.

`ADAPTIVE_SEARCH_ALLOWED=false` and
`POST_VALIDATION_PARAMETER_SUBSTITUTION_ALLOWED=false`.

## Canonical binding

The manifest uses the repository's existing `canonical_json_dumps` and
`sha256_payload` implementation. Decimal values are canonicalized without
native floats. The manifest and each run have deterministic hashes; the
manifest also binds the owner decision, exact registry entry, full incumbent
snapshot, allowlist, exclusions, run order, seed policy, and guardrail-policy
mode.

The live execution request is built with the frozen C03 manifest, the exact
S4-A registry, S4-B policy identities, real paired dataset identities, metric
contract identity, code commit identity, and a fresh evaluation identity.
`S4CandidateExecutionAuthority` then reloads verified PostgreSQL state, binds
the candidate count and effective global count, and supplies the CAS expected
state to the durable STARTED append.

The current durable state remains:

```text
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
```

The effective count is distinct from the next canonical event ordinal. At the
current state the future first C03 run would have candidate ordinal 1 and
canonical global ordinal 1, while the S4-B effective validation count is 4.

## Execution boundary

The C03 command is deliberately fail-closed in this task. Direct invocation
returns a machine-readable `BLOCKED` result with
`REASON_CODE=CANDIDATE_EXECUTION_NOT_AUTHORIZED`, creates no STARTED event,
does not call a scorer, does not load validation data, and cannot self-
authorize through a CLI flag.

The internal application seam is ordered as:

1. load the verified PostgreSQL budget state;
2. build and evaluate the S4-B gate request;
3. append and commit the durable `EVALUATION_STARTED` event with CAS state;
4. read back and verify the committed event;
5. only then release a future scorer callback;
6. append a terminal event without an additional budget debit.

This task exercises only synthetic control-plane callbacks in tests. No C03
validation scoring, C01 rerun, C02 execution, model training, TEST access, or
production parameter change was performed.

## Frozen status

```text
C03_CONTRACT=PASS
C03_MANIFEST=FROZEN
C03_RUNNER=READY
C03_DURABLE_AUTHORITY_BINDING=PASS
C03_EXECUTION_READY=true
C03_EXECUTION_AUTHORIZED=false
C03_EXECUTION_PERFORMED=false
NEW_VALIDATION_SCORING_CALL_COUNT=0
TEST_REMAINS_SEALED=true
```
