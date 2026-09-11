# Workpaper: V0.3 S4 incumbent-retention final closure

## Scope and authority

Task: `V0_3_S4_INCUMBENT_RETENTION_FINAL_CLOSURE_R1`.

The work is a pure terminal governance projection from the merged #602
remaining-candidate audit. The base is `ef15039e85e07d0115b7dde0f3ddee9d03a9763a`,
the #602 merge commit. No candidate, validation scorer, TEST reader, or budget
repository write path is used.

## Closure derivation

`build_s4_final_closure()` consumes
`build_frozen_s4_closure()` from
`backend.app.s4_remaining_candidate_viability`. It checks all three terminal
conditions before constructing the result:

1. `next_executable_candidate` is exactly `NONE`;
2. `current_frozen_plan_has_no_remaining_executable_candidate` is true;
3. every canonical candidate-runnability flag is false.

If any check fails, the function raises `S4FinalClosureBlocked`. A supplied
selected candidate other than `NOT_ISSUED` raises
`S4SelectionStateConflict`. These checks prevent closure from overriding a
newly available candidate or an independently issued selection.

The eight dispositions and reason codes are therefore inherited from the
canonical #602 closure, not manually re-created in this module. The frozen
registry remains a separate selection-eligibility authority; this closure only
projects current V4 runnability.

## Incumbent meaning

The result is `CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED`. It is intentionally
not an incumbent validation win, candidate ranking, final S4 winner, selected
TEST model, or pilot approval. `V0_2_CURRENT_MODEL` is retained because no
admissible replacement was selected under the frozen plan.

The retained status means the existing model authority is unchanged. It does
not perform a redeployment or a new model mutation.

## No-selection and TEST controls

There is no selected candidate and no multiple-comparison output:

```text
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
MULTIPLE_COMPARISON_FINAL_SELECTION_PERFORMED=false
HOLM_ADJUSTMENT_PERFORMED=false
```

TEST remains sealed, with no row selection, label load, byte read, or scoring.
The closure also leaves model, parameter, and pilot authorization false.

## Plan and budget

The closure references the existing V2 experiment plan and V4 guardrail policy
identities. It marks the current plan execution status `CLOSED`, but issues no
new plan or policy and does not mutate either frozen identity.

The budget values are explicitly classified as the last accepted durable
snapshot rather than a new live database read:

```text
DURABLE_BUDGET_READBACK_AVAILABLE=false
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
REMAINING_VALIDATION_BUDGET_UNUSED=24
BUDGET_CARRY_FORWARD_AUTHORIZED=false
BUDGET_DELTA=0
```

Provenance is the immutable C04 R1 execution evidence at
`docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json`, SHA-256
`78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3`.
No ledger event is created by this task.

## Evidence and verification

`s4-incumbent-retention-final-closure-r1.json` stores the exact payload returned
by `build_s4_final_closure_payload()`. The contract test loads that JSON and
compares its `MACHINE_DERIVED_CLOSURE_PAYLOAD` byte-for-byte at the parsed JSON
object level with the canonical payload. The same test suite covers the
nonterminal-closure and selected-candidate conflict fail-closed paths.

Historical evidence is not edited. The development plan receives only an
append-only current-live pointer.

Final stop gate:

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S4_FINAL_CLOSURE_REVIEW
```
