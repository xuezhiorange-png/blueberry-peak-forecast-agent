# Workpaper — S5 post-S4 closure authority realignment R1

```text
TASK_ID=V0_3_S5_POST_S4_CLOSURE_AUTHORITY_REALIGNMENT_R1
BASE_MAIN_SHA=2026424daf267ab292eee49166002dde3b936ffa
METHOD=READ_ONLY_AUTHORITY_AND_IMPLEMENTATION_AUDIT
```

## Audit inputs

The audit was performed against the clean current-main tree containing PR
#603 merge commit `2026424daf267ab292eee49166002dde3b936ffa`. The primary
inputs were:

- `backend/app/s4_final_closure.py` and
  `docs/v0-3/s4/evidence/s4-incumbent-retention-final-closure-r1.json` for
  the canonical no-selection closure;
- `docs/v0-3/development-plan.md §4.7` and §4.8 for formal S5/S6 authority;
- `docs/v0-3/s5/s5-a-pilot-operations-readiness-contract-and-runtime-gap-plan-r1.md`
  and its evidence for the proposal-only sixteen-requirement inventory;
- the PR #593–#603 merge lineage and current-main planning/evidence files;
- the current Trial, Core Forecast, retention, quality, API, frontend,
  migration, and compose paths listed in the final report.

No runtime database was connected. No forecast, label import, scheduler,
authority capture, S4 scan, validation scorer, TEST read, or application
write was performed.

## Authority reasoning

The decisive sentence in formal §4.7 is that S5 operates the selected
pilot-approved model in the pilot workflow. Formal §4.8 separately lists the
lifecycle state `MODEL_APPROVED_FOR_PILOT` before `PILOT_OPERATIONS_READY` and
reserves real-season acceptance for S6. PR #603's canonical projection says:

```text
S4_FINAL_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
SELECTED_CANDIDATE_ID=NOT_ISSUED
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
INCUMBENT_RETAINED=true
INCUMBENT_IS_S4_SELECTED_CANDIDATE=false
MODEL_APPROVED_FOR_PILOT=false
```

There is no authority statement that makes incumbent retention equivalent to
pilot approval. The correct result is therefore:

```text
DOES_S5_REQUIRE_MODEL_APPROVED_FOR_PILOT=true
CAN_INCUMBENT_RETAINED_SATISFY_MODEL_APPROVED_FOR_PILOT=false
S5_ENTRY_STATUS=BLOCKED_NO_PILOT_APPROVED_MODEL
NEXT_S5_ACTION=NO_S5_IMPLEMENTATION
```

This blocks the current S5 entry, not the continued reuse of existing code
paths as engineering evidence. It also does not authorize a new S4 plan or
candidate.

## Requirement disposition method

The sixteen identities `S5-REQ-001` through `S5-REQ-016` are retained from
the merged S5-A proposal. Each was checked against current-main source paths
and assigned one of the task's dispositions. “Reusable without approval” is
only used where current main already proves a reusable capability; it is not
an implementation authorization.

```text
S5_REQUIREMENT_COUNT=16
S5_REQUIREMENTS_REUSABLE_WITHOUT_PILOT_APPROVAL=005,006,009,010,012,016
S5_REQUISITE_BUCKETS_MAY_OVERLAP=true
S5_REQUIREMENTS_BLOCKED_BY_PILOT_APPROVAL=001,002,003,004,013,014,015
S5_REQUIREMENTS_BLOCKED_BY_OTHER_AUTHORITY=007,008,011,013,014
```

The reusable paths are forecast-versus-actual reporting, naive-baseline
comparison, model/parameter version display, export, and immutable retention.
They remain bounded engineering capabilities, not proof of a pilot-approved
model. Current/previous approved-model and calibration comparison, structured
pilot explanations, adoption, and manual-adjustment operations still require
the future S5 entry and/or owner decisions.

## Runtime and historical artifacts

The current code audit confirms that `/live` and `/ready`, Trial/Core forecast
paths, retention/readback, actual-harvest, quality, and export surfaces exist
in engineering form. `docker-compose.yml` is local/dev evidence;
`docker-compose.test.yml` is TEST-only evidence. The PR #595 runtime artifact
is retained as historical infrastructure evidence, but its live existence was
not verified because reconnect/recovery is outside this task:

```text
PR595_RUNTIME_STILL_EXISTS_AS_REUSABLE_INFRASTRUCTURE=NOT_PROVEN
PR595_S4_STATUS_IS_CURRENT=false
PR595_PROSPECTIVE_S4_WAIT_STATE_SUPERSEDED=true
PR595_RUNTIME_AUTHORIZES_S5_IMPLEMENTATION=false
PR595_RUNTIME_AUTHORIZES_PILOT=false
```

PR #602's “no remaining executable candidate” audit is consumed by PR #603;
PR #603 is the current S4 closure. PR #593/594 S5 decomposition and contract
documents remain proposal-only. No historical document is deleted or rewritten.

## Side-effect and terminal checks

```text
DOCUMENT_SCOPE_ONLY=true
PRODUCTION_CODE_CHANGED=false
DATABASE_WRITE=false
MIGRATION=false
PILOT_RUNTIME_START=false
FORECAST_EXECUTION=false
FORECAST_AUTHORITY_CAPTURE=false
ACTUAL_LABEL_IMPORT=false
ADOPTION_RECORD_WRITE=false
S4_REOPEN_AUTHORIZED=false
NEW_EXPERIMENT_PLAN_AUTHORIZED=false
NEW_CANDIDATE_AUTHORIZED=false
VALIDATION_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_AUTHORIZED=false
TEST_AUTHORIZED=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=4
EFFECTIVE_CONSUMED=8
REMAINING=24
BUDGET_DELTA=0
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
```

The machine-readable evidence is the authoritative projection of this
workpaper. Validation is limited to JSON parsing, documentation consistency,
allowlist checking, and `git diff --check`; no Python or production runtime
surface was changed.

```text
FINAL_STOP_GATE=COORDINATOR_V0_3_S5_POST_S4_ENTRY_REALIGNMENT_REVIEW
```
