# V0.3 S5 post-S4 closure authority realignment R1

```text
TASK_ID=V0_3_S5_POST_S4_CLOSURE_AUTHORITY_REALIGNMENT_R1
TASK_CLASS=GOVERNANCE_AND_S5_ENTRY_CRITERIA_REALIGNMENT
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_MAIN_SHA=2026424daf267ab292eee49166002dde3b936ffa
PR603_MERGE_IN_BASE=true
DOCUMENT_SCOPE_ONLY=true
```

## 1. Decision summary

The current main branch contains PR #603's canonical S4 final closure. The
frozen S4 plan ended with no admissible replacement selected:

```text
S4_FINAL_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
SELECTED_CANDIDATE_ID=NOT_ISSUED
SELECTED_CANDIDATE_COUNT=0
INCUMBENT_MODEL_ID=V0_2_CURRENT_MODEL
INCUMBENT_RETAINED=true
INCUMBENT_IS_S4_SELECTED_CANDIDATE=false
INCUMBENT_DECLARED_VALIDATION_WINNER=false
MODEL_APPROVED_FOR_PILOT=false
TEST_REMAINS_SEALED=true
NEW_EXPERIMENT_PLAN_AUTHORIZED=false
```

The formal V0.3 S5 slice remains `docs/v0-3/development-plan.md §4.7`.
Its objective says that S5 operates the selected pilot-approved model in the
pilot workflow. Section 4.8's lifecycle separately places
`MODEL_APPROVED_FOR_PILOT` before `PILOT_OPERATIONS_READY`. Retaining the V0.2
incumbent is not a selected-candidate decision and does not satisfy that
approval state.

Therefore this realignment records the terminal current entry result:

```text
DOES_S5_REQUIRE_MODEL_APPROVED_FOR_PILOT=true
CAN_INCUMBENT_RETAINED_SATISFY_MODEL_APPROVED_FOR_PILOT=false
S5_ENTRY_STATUS=BLOCKED_NO_PILOT_APPROVED_MODEL
NEXT_S5_ACTION=NO_S5_IMPLEMENTATION
V0_3_NEXT_DECISION_REQUIRED=COORDINATOR_VERSION_CLOSEOUT_OR_NEW_MODEL_EXPERIMENT_AUTHORIZATION
```

Current-main capabilities that are already implemented remain reusable
engineering foundations. They are not a new authorization to implement S5,
run a pilot, open TEST, or promote the incumbent. No pre-approval S5
foundation lane is issued because §4.7 does not formally define one.

## 2. Authority and artifact interpretation

The formal source is the S5 slice in §4.7. The S5-A/S5-B/S5-C names remain a
proposal decomposition from PR #593 and the merged S5-A contract is still a
proposal, not a formal subtask authorization. PR #603 is the current source
for the S4 terminal state. Earlier artifacts are preserved and interpreted by
subject; their historical claims are not rewritten.

| Artifact | Current disposition | Interpretation in this task |
| --- | --- | --- |
| PR #593 and its post-S4 inventory | `PROPOSAL_ONLY_NOT_AUTHORIZED` | S5 decomposition and inventory provenance only; its old prospective-S4 wait is not current |
| PR #594 S5-A contract | `PROPOSAL_ONLY_NOT_AUTHORIZED` | Frozen proposal and gap inventory; no implementation authorization |
| PR #595 pilot-runtime evidence | `HISTORICAL_STILL_VALID` | Reusable runtime engineering evidence; live persistence is not re-proven here, and it authorizes neither S5 nor pilot |
| PR #596 historical-only realignment | `HISTORICAL_STILL_VALID` | Historical-only S4 input policy remains evidence; it does not reopen S4 |
| PR #597 V2 execution adapter | `HISTORICAL_STILL_VALID` | V2 control-plane implementation remains historical engineering evidence |
| PR #598 C04 scorer readiness | `HISTORICAL_STILL_VALID` | Scorer/manifest engineering evidence remains auditable; no candidate is selected |
| PR #599 sparse guardrail alignment | `HISTORICAL_STILL_VALID` | V3/V4 guardrail lineage remains auditable |
| PR #600 C04 validation and closure evidence | `HISTORICAL_STILL_VALID` | Four-run and evidence-hardening history remains immutable; no new adjudication is issued |
| PR #601 C03 readiness | `HISTORICAL_STILL_VALID` | Readiness evidence remains auditable; C03 is not selected or authorized |
| PR #602 remaining-candidate viability | `SUPERSEDED_BY_PR603_FINAL_CLOSURE` | Its `NEXT_EXECUTABLE_CANDIDATE=NONE` audit is consumed by the final closure |
| PR #603 S4 incumbent-retention closure | `CURRENT` | Canonical current S4 status and incumbent-retention decision |
| Post-S4 business-pilot planning document | `HISTORICAL_STILL_VALID` | S5/S6 inventory remains useful planning provenance; its pre-closure S4 wait wording is superseded |
| S5-A contract documents | `PROPOSAL_ONLY_NOT_AUTHORIZED` | Proposal-only S5-A scope and acceptance contract |
| Pilot-runtime evidence | `HISTORICAL_STILL_VALID` | Runtime artifact is reusable infrastructure evidence only; no current live runtime check is performed |
| S4 final-closure evidence | `CURRENT` | Current no-selection closure authority |

The historical prospective wait in PR #595 and the prospective dependency
wording in earlier planning documents are not copied into the current S4
state. They are replaced for current interpretation by PR #603's closed
S4/no-selection state.

## 3. S5 entry-condition resolution

The conclusion follows three independent facts:

1. §4.7 defines S5 as operating a selected pilot-approved model in the pilot
   workflow, rather than merely exposing generic engineering primitives.
2. §4.8 identifies `MODEL_APPROVED_FOR_PILOT` and then
   `PILOT_OPERATIONS_READY` as distinct lifecycle states. It also reserves
   real-season acceptance for S6.
3. PR #603 proves the current S4 has no selected candidate and explicitly
   keeps `MODEL_APPROVED_FOR_PILOT=false`.

The retained incumbent can be used as the current product baseline, but the
following implication is forbidden:

```text
V0_2_CURRENT_MODEL retained
    -> selected candidate
    -> pilot-approved model
```

The implementation result is consequently Outcome B from the task contract:

```text
S5_ENTRY_STATUS=BLOCKED_NO_PILOT_APPROVED_MODEL
NEXT_S5_ACTION=NO_S5_IMPLEMENTATION
```

This is not a new S4 runtime blocker. It is the formal S5 entry disposition.
The coordinator must separately choose either version closeout or a new
model/experiment authorization before S5 can be reconsidered.

## 4. Sixteen-requirement re-audit

The table below reuses the sixteen requirement identities from the merged
S5-A proposal but changes no requirement meaning. `ALREADY_IMPLEMENTED_REUSABLE`
and `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` describe existing engineering
capability that can be carried forward; neither status authorizes a new S5
implementation in this task.

| ID | Formal source | Current main implementation path | Current state | Pilot approval required for new S5 operation | Business-owner decision required | Runtime required | Disposition | Next allowed action | Blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S5-REQ-001 | §4.7 current vs previous forecast | `backend/app/trial.py`; Core Forecast persistence; retention readback | PARTIALLY_IMPLEMENTED | true | false | true | `BLOCKED_REQUIRES_PILOT_APPROVED_MODEL` | Reconsider only after approval and separate S5 authorization | No selected pilot-approved model and no versioned comparison contract |
| S5-REQ-002 | §4.7 current vs previous pilot-approved model | `model_identity`/`model_version` fields only; no approved-model registry | NOT_IMPLEMENTED | true | true | true | `BLOCKED_REQUIRES_PILOT_APPROVED_MODEL` | Obtain explicit approval/registry decision; then separately authorize implementation | `MODEL_APPROVED_FOR_PILOT=false` |
| S5-REQ-003 | §4.7 before/after calibration | S4 manifests are validation evidence, not S5 operation records | NOT_IMPLEMENTED | true | true | true | `BLOCKED_REQUIRES_PILOT_APPROVED_MODEL` | Reconsider after a selected/approved model and comparison authority exist | No selected calibration result is authorized by PR #603 |
| S5-REQ-004 | §4.7 P50/P80/P90 comparison | Retained curves and single-report UI overlay in `backend/app/forecast_quality`; `frontend/src/features/quality` | PARTIALLY_IMPLEMENTED | true | false | true | `BLOCKED_REQUIRES_PILOT_APPROVED_MODEL` | Define server-owned cross-run comparison after entry authorization | Current surface is not the complete operational comparison authority |
| S5-REQ-005 | §4.7 forecast versus actual | `backend/app/actual_harvest_labels`; `backend/app/trial.py`; quality-report API | ALREADY_IMPLEMENTED_REUSABLE | false | false | true | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve as a reusable read/report capability; no S5 implementation start | A live operational scope is not authorized |
| S5-REQ-006 | §4.7 current model versus naive baseline | `backend/app/forecast_quality/comparison.py`; persisted quality models and API | ALREADY_IMPLEMENTED_REUSABLE | false | false | true | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve existing comparison building block for a future authorized run | No current pilot approval/operation is issued |
| S5-REQ-007 | §4.7 data-gap notices | `TrialForecastSummaryResponse.data_gap_summaries`; forecast UI and quality reasons | PARTIALLY_IMPLEMENTED | false | true | true | `BLOCKED_REQUIRES_OTHER_AUTHORITY` | Freeze notice vocabulary and scope only after a separately authorized S5 task | Typed operational notice ownership and scope are not decided |
| S5-REQ-008 | §4.7 data-quality risk notices | `blocker_summaries`, quality reason codes, and S2 findings | PARTIALLY_IMPLEMENTED | false | true | true | `BLOCKED_REQUIRES_OTHER_AUTHORITY` | Obtain notice classification/owner disposition before implementation | Current strings are not a complete S5 notice authority |
| S5-REQ-009 | §4.7 model version display | `TrialForecastSummaryResponse.model_version`; `ForecastResult.tsx` | ALREADY_IMPLEMENTED_REUSABLE | false | false | false | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve version display; do not infer approval from it | Displayed version is not an approval record |
| S5-REQ-010 | §4.7 parameter version display | `TrialForecastSummaryResponse.parameter_version`; `ForecastResult.tsx` | ALREADY_IMPLEMENTED_REUSABLE | false | false | false | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve parameter identity display; do not change parameters | Displayed parameter identity is not model selection |
| S5-REQ-011 | §4.7 historical forecast query | `GET /api/v1/trial/forecasts/{run_id}`; daily-curve endpoint; PIT reader | PARTIALLY_IMPLEMENTED | false | true | true | `BLOCKED_REQUIRES_OTHER_AUTHORITY` | Define list/filter/access policy under a future authorized S5 scope | Current main proves known-ID read, not the complete operational history surface |
| S5-REQ-012 | §4.7 result export | Trial forecast and quality CSV export routes and frontend export controls | ALREADY_IMPLEMENTED_REUSABLE | false | false | false | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve server export paths; no new S5 operation starts | Version-aware pilot export policy is not accepted |
| S5-REQ-013 | §4.7 business adoption record | No S5 adoption record model/API found in current-main scoped audit | NOT_IMPLEMENTED | true | true | true | `BLOCKED_REQUIRES_OTHER_AUTHORITY` | Decide adoption-record boundary and authorize implementation later | Business adoption is not business acceptance; owner and persistence contract absent |
| S5-REQ-014 | §4.7 manual-adjustment reason | No manual-adjustment reason model/API found in current-main scoped audit | NOT_IMPLEMENTED | true | true | true | `BLOCKED_REQUIRES_OTHER_AUTHORITY` | Decide reason vocabulary, actor, and audit boundary later | Business/data owner policy and immutable hook absent |
| S5-REQ-015 | §4.7 explanation rule | Data-gap/blocker summaries and quality reason codes; no standalone explanation contract | PARTIALLY_IMPLEMENTED | true | true | true | `BLOCKED_REQUIRES_PILOT_APPROVED_MODEL` | Reconsider evidence-derived explanation after S5 entry and comparison authority | No approved operational comparison/evidence envelope exists |
| S5-REQ-016 | §4.7 immutability rule | `backend/app/forecast_authority/retention.py`; retention migrations; readback APIs | ALREADY_IMPLEMENTED_REUSABLE | false | false | true | `REUSABLE_WITHOUT_PILOT_MODEL_APPROVAL` | Preserve append-only retention and readback behavior | Production operating binding remains unapproved |

The reusable list is deliberately limited to capabilities already present on
current main. It does not create a formal pre-approval implementation lane:

```text
S5_REQUIREMENT_COUNT=16
S5_REQUIREMENTS_REUSABLE_WITHOUT_PILOT_APPROVAL=S5-REQ-005,S5-REQ-006,S5-REQ-009,S5-REQ-010,S5-REQ-012,S5-REQ-016
S5_REQUISITE_BUCKETS_MAY_OVERLAP=true
S5_REQUIREMENTS_BLOCKED_BY_PILOT_APPROVAL=S5-REQ-001,S5-REQ-002,S5-REQ-003,S5-REQ-004,S5-REQ-013,S5-REQ-014,S5-REQ-015
S5_REQUIREMENTS_BLOCKED_BY_OTHER_AUTHORITY=S5-REQ-007,S5-REQ-008,S5-REQ-011,S5-REQ-013,S5-REQ-014
```

## 5. PR #595 runtime disposition

PR #595's checked-in evidence documents a persistent pilot-runtime binding,
but this task performs no runtime connection or recovery. The artifact is
therefore reusable evidence, while current live existence is not proven:

```text
PR595_RUNTIME_STILL_EXISTS_AS_REUSABLE_INFRASTRUCTURE=NOT_PROVEN
PR595_S4_STATUS_IS_CURRENT=false
PR595_PROSPECTIVE_S4_WAIT_STATE_SUPERSEDED=true
PR595_RUNTIME_AUTHORIZES_S5_IMPLEMENTATION=false
PR595_RUNTIME_AUTHORIZES_PILOT=false
TASK_ISOLATED_DATABASE_IS_PRODUCTION=false
```

The old runtime evidence must not be used to reinterpret a task-isolated or
local database as current production authority. No reconnect, DSN search,
Docker recovery, seed, backfill, or forecast execution is part of this task.

## 6. S4, TEST, and side-effect boundary

The realignment is read-only and does not reopen or mutate S4:

```text
CURRENT_S4_EXECUTION_STATUS=CLOSED_NO_ADMISSIBLE_REPLACEMENT_SELECTED
CURRENT_S4_BLOCKER=NONE_CURRENT_PLAN_TERMINAL
S4_REOPEN_AUTHORIZED=false
NEW_EXPERIMENT_PLAN_AUTHORIZED=false
NEW_CANDIDATE_AUTHORIZED=false
VALIDATION_EXECUTION_AUTHORIZED=false
VALIDATION_SCORING_AUTHORIZED=false
PROSPECTIVE_SCAN_PERFORMED=false
DATABASE_WRITE=false
MIGRATION=false
PILOT_RUNTIME_START=false
FORECAST_EXECUTION=false
FORECAST_AUTHORITY_CAPTURE=false
ACTUAL_LABEL_IMPORT=false
ADOPTION_RECORD_WRITE=false
SCHEDULER_START=false
```

The accepted historical budget snapshot remains unchanged and is not read back
from a live database in this documentation-only task:

```text
DURABLE_BUDGET_READBACK_AVAILABLE=false
BUDGET_STATE_CLASS=LAST_ACCEPTED_DURABLE_BUDGET_SNAPSHOT
VALUES_ARE_CURRENT_DATABASE_READBACK=false
VALUES_ARE_LAST_ACCEPTED_DURABLE_SNAPSHOT=true
LEGACY_RECONCILED_VALIDATION_DEBIT=4
LAST_ACCEPTED_CANONICAL_STARTED_COUNT=4
LAST_ACCEPTED_EFFECTIVE_CONSUMED=8
LAST_ACCEPTED_REMAINING=24
REMAINING_VALIDATION_BUDGET_UNUSED=24
BUDGET_DELTA=0
BUDGET_PROVENANCE=docs/v0-3/s4/evidence/s4-c04-controlled-real-validation-r1.json
BUDGET_PROVENANCE_SHA256=78b1489b28fe0056e1c7fd88165f927c04d16bf1083926048ba4c36e3c1498b3
```

TEST remains sealed, and no candidate or model state is issued:

```text
TEST_AUTHORIZED=false
TEST_ACCESS_REQUESTED=false
TEST_BYTES_READ=false
TEST_EVALUATION_PERFORMED=false
TEST_REMAINS_SEALED=true
SELECTED_CANDIDATE_ID=NOT_ISSUED
MODEL_APPROVED_FOR_PILOT=false
S5_IMPLEMENTATION_STARTED=false
S6_IMPLEMENTATION_STARTED=false
PILOT_DEPLOYMENT_AUTHORIZED=false
PRODUCTION_MODEL_CHANGE_AUTHORIZED=false
PRODUCTION_PARAMETER_CHANGE_AUTHORIZED=false
```

## 7. Final disposition

```text
S5_A_CONTRACT_PROPOSAL_COMPLETE=true
PROPOSED_S5_A_CONTRACT_FROZEN=true
PROPOSED_S5_ABC_DECOMPOSITION_AUTHORIZED=false
S5_ENTRY_STATUS=BLOCKED_NO_PILOT_APPROVED_MODEL
NEXT_S5_ACTION=NO_S5_IMPLEMENTATION
V0_3_NEXT_DECISION_REQUIRED=COORDINATOR_VERSION_CLOSEOUT_OR_NEW_MODEL_EXPERIMENT_AUTHORIZATION
S4_REOPEN_AUTHORIZED=false
NEW_EXPERIMENT_PLAN_AUTHORIZED=false
TEST_AUTHORIZED=false
TEST_REMAINS_SEALED=true
S5_IMPLEMENTATION_STARTED=false
PILOT_DEPLOYMENT_AUTHORIZED=false
PRODUCTION_MODEL_CHANGE_AUTHORIZED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S5_POST_S4_ENTRY_REALIGNMENT_REVIEW
```

The only legitimate future route to S5 is a separately authorized decision
that first establishes a pilot-approved model (or explicitly changes the
formal authority), then authorizes a bounded S5 implementation. Passing
engineering tests or retaining the incumbent does not issue either decision.
