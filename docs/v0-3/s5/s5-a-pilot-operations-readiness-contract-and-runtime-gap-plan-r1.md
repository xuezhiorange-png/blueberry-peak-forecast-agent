# V0.3-S5-A Pilot Operations Readiness Contract and Runtime Gap Plan

TASK_ID=V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_AND_RUNTIME_GAP_PLAN_R1
TASK_CLASS=DOCUMENTATION_ONLY_PROPOSED_S5_EXECUTION_CONTRACT_FREEZE
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_MAIN_SHA=49388438c0fb287068b3f0bb803f7c03bd00a81a
PR593_MERGE_IN_BASE=true

## Decision summary

This document freezes a reviewable S5-A contract proposal. It is not a
current formal S5-A subtask authority and it does not authorize production
implementation. The current V0.3 S5 slice authority is
`docs/v0-3/development-plan.md` §4.7. That slice is current and formal; the
S5-A/S5-B/S5-C decomposition remains the proposal recorded by PR #593.

The proposal is complete as a contract and gap inventory, but S5-A is not
implementation-ready. The blocking conditions are explicit: S4 has not
completed its prospective authority-dependent path, no pilot model has been
approved, several server-owned operations records are not implemented, and
production runtime/ownership evidence is not present in current main.

```text
PROPOSED_S5_A_CONTRACT_VERSION=v0.3-s5-a-pilot-operations-readiness-contract-v1
PROPOSED_S5_A_CONTRACT_STATUS=FROZEN_PROPOSAL_NOT_AUTHORIZED
S5_A_CONTRACT_PROPOSAL_COMPLETE=true
S5_A_CURRENT_IMPLEMENTATION_READINESS=BLOCKED_BY_IDENTIFIED_PREREQUISITES
PROPOSED_S5_A_CONTRACT_ACCEPTED=false
V0_3_S5_AUTHORIZED=false
S5_IMPLEMENTATION_STARTED=false
S5_A_IMPLEMENTATION_AUTHORIZED=false
S5_A_PRODUCTION_CODE_CHANGED=false
```

## 1. Current governance boundary

The current-main baseline contains the PR #593 merge commit. The following
facts are carried forward without reopening S4 recovery or changing the S4
plan:

```text
CURRENT_V0_3_S1_COMPLETE=true
CURRENT_V0_3_S2_COMPLETE=true
CURRENT_V0_3_S3_COMPLETE=true
CURRENT_V0_3_S4_COMPLETE=false
CURRENT_S4_EXECUTION_STATUS=WAITING_FOR_REAL_PROSPECTIVE_FORECAST_AUTHORITY
CURRENT_S4_BLOCKER=REAL_PROSPECTIVE_FORECAST_AUTHORITY_NOT_YET_AVAILABLE
FURTHER_PROSPECTIVE_AUTHORITY_STORE_DISCOVERY_REQUIRED=false
FURTHER_POSTGRES_RECONNECT_REQUIRED=false
FURTHER_DOCKER_VOLUME_RECOVERY_REQUIRED=false
FURTHER_DSN_SEARCH_REQUIRED=false
PROSPECTIVE_SCAN_BEFORE_TRIGGER=false
CANDIDATE_EXECUTION_BEFORE_TRIGGER=false
VALIDATION_SCORING_BEFORE_TRIGGER=false
LEGACY_RECONCILED_VALIDATION_DEBIT=4
CANONICAL_STARTED_COUNT=0
EFFECTIVE_CONSUMED=4
REMAINING=28
BUDGET_DELTA=0
TEST_REMAINS_SEALED=true
```

The historical S3-C result remains terminal `NOT_COMPUTABLE`; no S5-A
document changes that result. This task performed no scan, database recovery,
authority-store discovery, candidate execution, validation scoring, TEST
access, seed, backfill, S1 split change, or S4 plan change.

### S5 authority and proposal status

```text
CURRENT_V0_3_S5_SLICE_DEFINITION_EXISTS=true
CURRENT_V0_3_S5_FORMAL_SUBTASK_DECOMPOSITION_EXISTS=false
V0_3_S5_CURRENT_DEFINITION_EXISTS=true
V0_3_S6_CURRENT_DEFINITION_EXISTS=true
PROPOSED_S5_EXECUTION_DECOMPOSITION_SOURCE=PR593_PLANNING_PROPOSAL
PROPOSED_S5_EXECUTION_DECOMPOSITION_AUTHORIZED=false
PROPOSED_S5_EXECUTION_DECOMPOSITION_IMPLEMENTED=false
```

The proposal names are retained for planning only:

```text
PROPOSED_S5_EXECUTION_DECOMPOSITION=[
  S5-A PILOT OPERATIONS READINESS,
  S5-B FRONTEND COMPARISON WARNINGS AND STRUCTURED EXPLANATION,
  S5-C CONTINUOUS EVALUATION AND ADOPTION RECORDS
]
```

The older freeze-time S5-A/B/C records remain historical snapshots. This
document does not rewrite them or promote them into formal current subtasks.

## 2. Proposed S5-A scope

S5-A is proposed to own the server-side and operational contract needed to
run an approved forecast repeatedly and auditably in a pilot. It covers:

- versioned forecast-run identity and lineage;
- immutable forecast history and verified reload;
- server-owned comparison data and comparison availability/reason codes;
- forecast-to-actual and naive-baseline result retrieval using existing
  quality evidence where available;
- server-owned data-gap/data-quality notices derived from recorded evidence;
- version-aware history and export;
- a minimal operational feedback hook for adoption and manual-adjustment
  reasons, without making a business-acceptance decision;
- runtime readiness evidence, ownership, recovery, and operating controls.

S5-A does not own frontend presentation, explanation UI, recurring evaluation
scheduling, long-term adoption/non-adoption analytics, model changes,
parameter changes, S4 validation, TEST, pilot success, or production release.

## 3. §4.7 traceability matrix

The source authority for every row is the current V0.3 plan, §4.7. The
implementation status is deliberately evidence-based; an adjacent API or UI
does not make an unimplemented S5 capability `IMPLEMENTED_REUSABLE`.

| Requirement ID | Source authority | Current implementation status | Current implementation paths | Proven by current main | Missing capability | Proposed S5 owner | Implementation prerequisite | Acceptance evidence required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S5-REQ-001 | development-plan.md §4.7 Required capabilities | PARTIALLY_IMPLEMENTED | `backend/app/trial.py`; `backend/app/forecast_authority/retention.py`; `GET /api/v1/trial/forecasts/{run_id}` | Yes for immutable ID-scoped read; no prior-run comparison | Persisted current/previous forecast comparison authority and history selection | S5-A | Approved model and a versioned comparison contract | Two persisted forecast versions, same-scope comparison payload, hashes, and reload proof |
| S5-REQ-002 | development-plan.md §4.7 Required capabilities | NOT_IMPLEMENTED | `model_identity`/`model_version` fields only in `backend/app/trial.py` | No | Current model versus previous pilot-approved model record and comparison | S5-A | `MODEL_APPROVED_FOR_PILOT=true`; approved-model registry decision | Approved-model identities, comparison result, and owner review |
| S5-REQ-003 | development-plan.md §4.7 Required capabilities | NOT_IMPLEMENTED | C03/S4 manifests are validation artifacts, not S5 operations records | No | Persisted before/after calibration comparison for pilot runs | S5-A | Accepted S4 result and explicit calibration comparison authority | Paired pre/post records with parameter manifests and server-derived deltas |
| S5-REQ-004 | development-plan.md §4.7 Required capabilities | PARTIALLY_IMPLEMENTED | `backend/app/forecast_authority/retention.py`; `backend/app/trial.py`; `frontend/src/features/forecast/ForecastResult.tsx`; `frontend/src/features/quality/QualityReport.tsx` | Yes for persisted P50/P80/P90 curves and single-report overlay | Cross-version/quantile comparison payload owned by the server | S5-A | Comparison schema and complete persisted members | P50/P80/P90 comparison rows, identity binding, and exact readback |
| S5-REQ-005 | development-plan.md §4.7 Required capabilities | IMPLEMENTED_REUSABLE | `backend/app/actual_harvest_labels/service.py`; `backend/app/trial.py`; `/quality-reports` API | Yes for a persisted forecast plus committed actual import/report | Pilot-operational run linkage and broader history workflow | S5-A | Committed actual evidence and approved operational scope | Forecast/actual report, AS_OF_EVALUATION visibility, reason codes, and export |
| S5-REQ-006 | development-plan.md §4.7 Required capabilities | IMPLEMENTED_REUSABLE | `backend/app/forecast_quality/comparison.py`; `backend/app/models/forecast_quality.py`; quality API/UI | Yes for the existing model/baseline comparison result surface | Explicit S5 naming/lineage and use in the pilot run contract | S5-A | Existing comparison policy bound to S5 run identity | Persisted baseline member set, comparison hash, availability, and reload proof |
| S5-REQ-007 | development-plan.md §4.7 Required capabilities | PARTIALLY_IMPLEMENTED | `TrialForecastSummaryResponse.data_gap_summaries`; forecast result UI; quality reason codes | Yes for string summaries/reasons attached to current results | Typed notice envelope with evidence source, scope, severity, and affected run | S5-A | Notice vocabulary and evidence mapping | Notice code/source/scope/severity/observed fact plus negative unsupported-cause test |
| S5-REQ-008 | development-plan.md §4.7 Required capabilities | PARTIALLY_IMPLEMENTED | `TrialForecastSummaryResponse.blocker_summaries`; quality status/reason codes; S2 quality findings | Yes for recorded blockers/reasons | A server-owned data-quality risk notice contract separate from ad hoc strings | S5-A | Data-quality classification/owner decision | Persisted notice evidence and no unsupported cause inference |
| S5-REQ-009 | development-plan.md §4.7 Required capabilities | IMPLEMENTED_REUSABLE | `TrialForecastSummaryResponse.model_version`; `model_identity`; `ForecastResult.tsx` | Yes | Pilot-approved/current model status display and history filter | S5-A | Approved model identity | Version display bound to run identity and persisted record |
| S5-REQ-010 | development-plan.md §4.7 Required capabilities | IMPLEMENTED_REUSABLE | `TrialForecastSummaryResponse.parameter_version`; `parameter_identity`; `ForecastResult.tsx` | Yes | Version history and comparison binding | S5-A | Immutable parameter manifest identity | Parameter version/hash present in every operational run |
| S5-REQ-011 | development-plan.md §4.7 Required capabilities | PARTIALLY_IMPLEMENTED | `GET /api/v1/trial/forecasts/{run_id}`; daily-curve endpoint; retention PIT reader | Yes for read by known public run ID | Operator-facing historical list/filter/query contract and pagination | S5-A | History query contract and access policy | Multiple immutable runs queryable after fresh-session reload |
| S5-REQ-012 | development-plan.md §4.7 Required capabilities | IMPLEMENTED_REUSABLE | Forecast and quality CSV export routes in `backend/app/api/trial.py`; frontend export buttons | Yes for current forecast/quality exports | Version-aware operational export manifest and audit linkage | S5-A | Export schema and access policy | Export identity, source hashes, version fields, and deterministic output |
| S5-REQ-013 | development-plan.md §4.7 Required capabilities | NOT_IMPLEMENTED | No current S5 adoption record model/API found in scoped current main | No | Business adoption event/hook with actor, run, timestamp, and observed action | S5-A hook; S5-C ledger | Business owner decision and persistence contract | Append-only adoption record with actor/run lineage; no acceptance inference |
| S5-REQ-014 | development-plan.md §4.7 Required capabilities | NOT_IMPLEMENTED | No current manual-adjustment reason model/API found in scoped current main | No | Adjustment event and mandatory reason linked to the immutable forecast | S5-A hook; S5-C audit loop | Business/data owner decision and authorization policy | Immutable adjustment record, reason vocabulary, actor, and parent run |
| S5-REQ-015 | development-plan.md §4.7 Explanation rule | PARTIALLY_IMPLEMENTED | Forecast `data_gap_summaries`/`blocker_summaries`; quality reason codes; no standalone explanation contract | Only raw evidence reasons, not structured explanation | Evidence-derived explanation payload and persisted provenance | S5-A server contract; S5-B presentation | Evidence-to-explanation mapping; no invented causes | Explanation references input/version/result differences and passes unsupported-cause negative tests |
| S5-REQ-016 | development-plan.md §4.7 immutability rule | IMPLEMENTED_REUSABLE | `backend/app/forecast_authority/retention.py`; forecast authority migrations; readback APIs | Yes for append-only retention envelope and verified daily rows | S5 history/index/access surface over the retained records | S5-A | Operational access policy | New run does not overwrite prior run; hashes and daily P50/P80/P90 survive reload |

`IMPLEMENTED_REUSABLE` means a current path can be reused by S5-A with
contract-level binding; it does not mean S5-A acceptance has already passed.

## 4. S5-A domain contracts

### 4.1 Pilot forecast run identity

The future S5-A run envelope must bind, at minimum, the following values to
one immutable forecast identity:

| Authority element | Current-main evidence | S5-A disposition |
| --- | --- | --- |
| Public forecast identity | `run_id`, `canonical_public_hash` in `backend/app/trial.py` and Core Forecast persistence | Reuse and require |
| Forecast cutoff and execution time | `forecast_cutoff_at`, persisted created/available timestamps in Core Forecast and forecast-authority retention | Reuse; verify timezone and cutoff visibility |
| Model and parameter identity | `model_version`, `model_identity`, `parameter_version`, `parameter_identity`, policy identities | Reuse and require |
| Input/source authority | `forecast_input_authority_hash`, persisted source/lineage snapshots | Reuse and require |
| Forecast-authority capture identity | production retention capture and PIT reader in `backend/app/forecast_authority/retention.py` | Reuse and require |
| Business grain | season/farm/subfarm/variety/factory fields and canonical business-grain hashes in persisted authority | Reuse and require |
| Lineage/hash identity | code, Task8, Task9, result, curve, metrics, source-lineage hashes | Reuse and require |
| Run status | persisted Core Forecast/retention status | Reuse; define S5 operational status vocabulary |
| Actor/operator identity | request actor exists in API authorization, but a persisted pilot-run actor field was not proven | `PROPOSED_FIELD`; do not claim implemented |
| Pilot operation identity | no separate S5 pilot-operation record was proven | `PROPOSED_FIELD`; requires S5-A implementation |

No field absent from current main is presented as an existing database field.
The proposed fields require a future schema/API decision and migration under a
separately authorized task.

### 4.2 Immutable forecast history

The existing retention contract is the base. A new forecast is an additional
versioned result; it cannot update or delete a previous forecast. The future
S5-A history surface must query persisted public identities, use the verified
PIT/readback path, and preserve the same values and hashes after a fresh
session. Current main proves read-by-known-ID and immutable authority behavior;
it does not yet prove a pilot history list/filter or comparison index.

### 4.3 Operational comparison contract

S5-A freezes the server-owned data requirement, not a frontend layout. Each
comparison response must identify its two persisted members, common scope,
cutoff/actual-label authority, model and parameter versions, metric contract,
availability, reason codes, and canonical hash. Required comparison families
are current/previous forecast, current/prior pilot-approved model,
before/after calibration, forecast/actual, current/naive baseline, and
P50/P80/P90. The existing quality path supplies forecast/actual and baseline
building blocks; the other versioned comparison authorities are gaps.

```text
CLIENT_SIDE_BUSINESS_METRIC_RECOMPUTATION_ALLOWED=false
```

### 4.4 History, readback, and export

Reusable paths currently include forecast summary read, complete daily-curve
read, forecast CSV export, quality report read, persisted comparison read, and
quality CSV export. S5-A must add the version-aware operational contract and
access policy; S5-B may later decide how to present it. Browser rendering must
remain a projection of server-owned evidence, not a second metric authority.

### 4.5 Data-gap and data-quality notices

The future notice envelope must include `notice_code`, `evidence_source`,
`affected_forecast_run_id`, optional affected grain/scope, severity or
classification, and the observed fact. A notice may link existing
`data_gap_summaries`, blocker/reason codes, S2 quality findings, or persisted
quality evidence. It must not infer an unsupported weather, maturity,
capacity, or data-quality cause:

```text
UNSUPPORTED_CAUSE_INFERENCE=true
```

is forbidden. The current strings/reason codes are useful evidence inputs but
are not yet the complete S5-A notice contract.

### 4.6 Feedback and adoption boundary

S5-A may define a minimal operational feedback hook and persistence
requirements for `BUSINESS_ADOPTION_RECORD` and `MANUAL_ADJUSTMENT_REASON`.
It must not convert either into `BUSINESS_ACCEPTANCE_RECORD`:

```text
BUSINESS_ADOPTION_IS_BUSINESS_ACCEPTANCE=false
```

The recurring adoption/non-adoption ledger, scheduler, and longitudinal
evaluation belong to the proposed S5-C boundary. S6 remains the authority for
real-season business acceptance.

## 5. Current capability inventory

| Domain | Current status | Proven on current main | Remaining qualification |
| --- | --- | --- | --- |
| Real business source | AVAILABLE_FOR_ACCEPTED_S1_S2_BASELINE | SOURCE-002 and accepted TRAIN/VALIDATION materialization | No current real-season pilot feed/owner/cadence is proven |
| Actual-harvest pipeline | IMPLEMENTED | Import, validation, seal/commit, immutable label snapshots, AS_OF_EVALUATION | Future post-TEST labels for a prospective cohort are not proven |
| Forecast execution | IMPLEMENTED_ENGINEERING_PATH | Trial/Core execution and persisted daily result | No model-approved pilot operation is active |
| Forecast authority retention | IMPLEMENTED_AND_VERIFIED | Base capture before Task10, immutable daily P50/P80/P90, PIT readback and hashes | Production operational binding is not proven in this environment |
| Persistence/query | IMPLEMENTED_ENGINEERING_PATH | PostgreSQL-backed forecast authority and read/export endpoints | Production DB binding and SLO evidence are not proven |
| Quality comparison | PARTIALLY_IMPLEMENTED | Forecast/actual report and model/naive-baseline comparison | Versioned current/previous/approved-model/calibration comparisons are missing |
| API | IMPLEMENTED_ENGINEERING_SURFACE | Forecast, daily curve, export, actual-harvest, quality report/comparison/export routes | S5 operational contract and pilot authorization are not implemented |
| Frontend/browser workflow | ENGINEERING_FLOW_PRESENT | Forecast and Quality pages render persisted values and reasons | S5 comparison/warning/explanation/adoption UX is outside this task and not present |
| Business pilot operation | NOT_STARTED | §4.7/§4.8 definitions and dependency order | Operating cadence, roles, adoption record, real-season evidence |
| Deployment/runtime | PARTIAL_LOCAL_ENGINEERING_ONLY | Local `docker-compose.yml`, TEST-only `docker-compose.test.yml`, `/live`, `/ready` | Production binding, secret management, backup/restore, deployment owner |
| Observability/audit | PARTIAL_AUDITABILITY | Request/idempotency IDs, lineage, hashes, persisted evidence | Production telemetry, dashboards, alerting, incident review |
| Release/acceptance | NOT_STARTED | S6 acceptance contract; production release explicitly outside V0.3 | Model approval, pilot acceptance, rollback decision |

## 6. Runtime gap matrix

`BLOCKS_S5_A_IMPLEMENTATION` means the gap prevents the future implementation
authorization gate from being satisfied. `BLOCKS_S5_A_ACCEPTANCE` means code
could be developed, but pilot-readiness acceptance cannot pass until the gap
is resolved and evidenced.

| Gap ID | Domain | Current state | Evidence path | Why it matters for pilot | Blocks S5-A implementation | Blocks S5-A acceptance | Resolution class | External decision required | Proposed future owner | Acceptance proof |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S5A-CODE-001 | Server comparison/history | PARTIAL | `backend/app/trial.py`; `backend/app/forecast_quality/comparison.py`; `backend/app/models/forecast_quality.py` | Operators need comparable, versioned server-owned views without client recalculation | true | true | CODE_IMPLEMENTATION | false | S5-A backend owner | Persisted comparison members, scope/hash binding, fresh-session readback |
| S5A-CODE-002 | Notices/explanation | PARTIAL | `backend/app/trial.py`; `backend/app/s2_materialized_dataset/lane_b/schemas.py`; `frontend/src/features/forecast/ForecastResult.tsx` | Operators need actionable, evidence-backed data-gap and quality-risk status | true | true | CODE_IMPLEMENTATION | false | S5-A backend owner | Typed notice/explanation payload, evidence links, unsupported-cause negative test |
| S5A-CODE-003 | Feedback persistence | NOT_PROVEN | Scoped `backend/app` search found no S5 adoption/manual-adjustment record model/API | Adoption and adjustment actions must be auditable and separate from business acceptance | true | true | DATABASE_SCHEMA | true | S5-A/S5-C owner with business/data owner | Append-only record, actor/run linkage, reason vocabulary, replay/readback |
| S5A-RUNTIME-001 | PostgreSQL production binding | NOT_PROVEN | `backend/app/core/config.py`; `docker-compose.yml`; PR #592 terminal prospective dependency | Pilot data must persist in an identified production authority, not local/task-isolated DB | false | true | DEPLOYMENT_CONFIGURATION | true | Deployment owner | Sanitized binding record, migration head, connection/readiness evidence |
| S5A-RUNTIME-002 | Secret/config externalization | NOT_PROVEN | `backend/app/core/config.py`; `docker-compose.yml` uses local defaults | Credentials and environment-specific authority must not rely on repository defaults | false | true | SECURITY_CONFIGURATION | true | Security/deployment owner | Secret-manager/config-provider evidence with no secret in git |
| S5A-RUNTIME-003 | Migration/deployment procedure | PARTIAL | `backend/alembic/`; `docker-compose.yml`; `docker-compose.test.yml` | Schema/runtime drift can invalidate immutable authority and API behavior | false | true | DEPLOYMENT_CONFIGURATION | true | Deployment owner | Rehearsed upgrade, unique head, rollback policy, release record |
| S5A-RUNTIME-004 | Health/readiness/authority readiness | PARTIAL | `backend/app/api/health.py`; `backend/app/schemas/health.py` | `/live` and `/ready` exist, but readiness only proves `SELECT 1`, not forecast authority readiness | false | true | OBSERVABILITY | true | S5-A/deployment owner | Health contract covers DB, migrations, authority retention and dependency state |
| S5A-RUNTIME-005 | Backup and restore | NOT_PROVEN | No current-main production backup/restore procedure or evidence artifact found in scoped runtime docs | Immutable pilot history is not operationally safe without recoverability proof | false | true | OPERATIONS_PROCESS | true | Operations/data owner | Successful restore rehearsal, integrity/hash comparison, RPO/RTO record |
| S5A-RUNTIME-006 | Telemetry/logging/alerting | PARTIAL | `backend/app/core/config.py` has log level; request IDs/evidence hashes exist in API paths; no production dashboard/alert evidence found | Operators must detect failed runs, stale authority, data gaps, and persistence failures | false | true | OBSERVABILITY | true | Operations owner | Metrics/log correlation, alerts, dashboard, and tested notification path |
| S5A-RUNTIME-007 | Incident/rollback/runbook | NOT_PROVEN | No dedicated current-main pilot incident/runbook/rollback artifact found in scoped runtime docs | A failed or disputed forecast needs a safe, accountable response | false | true | OPERATIONS_PROCESS | true | Operations/deployment owner | Reviewed runbook, rollback procedure, incident roles, and tabletop evidence |
| S5A-EXT-001 | Model/S4 governance | NOT_SATISFIED | `docs/v0-3/development-plan.md` §4.7 and current S4 terminal pointer | S5-A must operate an explicitly approved model, not an unselected candidate | true | true | BUSINESS_OWNER_DECISION | true | Coordinator/model-validation owner | `CURRENT_V0_3_S4_COMPLETE=true`, `MODEL_APPROVED_FOR_PILOT=true`, review record |
| S5A-EXT-002 | Pilot scope/owners/cadence | NOT_PROVEN | `docs/v0-3/development-plan.md` §4.8; current-main planning inventory | Roles, farms/varieties, cadence, data/security ownership, and feedback boundary define safe pilot operation | true | true | BUSINESS_OWNER_DECISION | true | Business/data/security/operations owners | Signed scope/roles/cadence/feedback disposition and S6 linkage |

The runtime matrix distinguishes local engineering capability from production
readiness. In particular, `docker-compose.yml` is local/dev evidence,
`docker-compose.test.yml` is TEST-only evidence, and any task-isolated S4
database is not a production authority:

```text
TASK_ISOLATED_DATABASE_IS_PRODUCTION=false
```

The gap counters have separate, non-interchangeable meanings. The legacy
`S5_A_EXTERNAL_DECISION_GAP_COUNT` is retained only as the dedicated
`S5A-EXT-*` prefix count; it is not the count of every gap that requires an
external decision.

```text
S5_A_CODE_GAP_COUNT=3
S5_A_CODE_GAP_COUNT_SEMANTICS=COUNT(GAP_ID starts with S5A-CODE-)
S5_A_RUNTIME_GAP_COUNT=7
S5_A_RUNTIME_GAP_COUNT_SEMANTICS=COUNT(GAP_ID starts with S5A-RUNTIME-)
S5_A_EXTERNAL_DECISION_GAP_COUNT=2
S5_A_EXTERNAL_DECISION_GAP_COUNT_SEMANTICS=COUNT_DEDICATED_S5A_EXT_PREFIX_GAPS_ONLY
S5_A_DEDICATED_EXTERNAL_GOVERNANCE_GAP_COUNT=2
S5_A_DEDICATED_EXTERNAL_GOVERNANCE_GAP_COUNT_SEMANTICS=COUNT(GAP_ID starts with S5A-EXT-)
S5_A_EXTERNAL_DECISION_REQUIRED_GAP_COUNT=10
S5_A_EXTERNAL_DECISION_REQUIRED_GAP_COUNT_SEMANTICS=COUNT(RUNTIME_GAP_MATRIX rows WHERE EXTERNAL_DECISION_REQUIRED=true)
S5_A_EXTERNAL_DECISION_RECORD_COUNT=5
S5_A_EXTERNAL_DECISION_RECORD_COUNT_SEMANTICS=COUNT(EXTERNAL_DECISION_MATRIX)
```

## 7. External decision matrix

| Decision ID | Decision needed | Current status | Owner | REQUIRED_BEFORE_IMPLEMENTATION | REQUIRED_BEFORE_ACCEPTANCE | Required evidence |
| --- | --- | --- | --- | --- | --- | --- |
| S5A-DEC-001 | Approve the S5-A proposal and its server-owned comparison/notice/feedback scope | NOT_ISSUED | Coordinator plus business/data owner | true | true | Explicit contract acceptance and separately scoped implementation authorization |
| S5A-DEC-002 | Confirm model and S4 disposition | NOT_SATISFIED | Coordinator/model-validation owner | true | true | `MODEL_APPROVED_FOR_PILOT=true` and `CURRENT_V0_3_S4_COMPLETE=true` |
| S5A-DEC-003 | Confirm pilot farms/varieties, cadence, data owner, security owner, operating owner, and deployment owner | NOT_PROVEN | Business/operations/security/data owners | true | true | Signed role/scope/cadence/handling record |
| S5A-DEC-004 | Decide backup/restore, alerting, incident response, and rollback obligations | NOT_PROVEN | Operations/deployment owner | false | true | Runbook, rehearsal, RPO/RTO and alert evidence |
| S5A-DEC-005 | Decide whether adoption/manual-adjustment hooks are S5-A interfaces or S5-C ledger work | NOT_ISSUED | Coordinator and business owner | true | true | Boundary decision preserving `BUSINESS_ADOPTION_IS_BUSINESS_ACCEPTANCE=false` |

## 8. Future implementation authorization gate

S5-A implementation may start only after all of the following are true and
independently evidenced:

```text
MODEL_APPROVED_FOR_PILOT=true
CURRENT_V0_3_S4_COMPLETE=true
PROPOSED_S5_A_CONTRACT_ACCEPTED=true
S5_A_IMPLEMENTATION_SEPARATELY_AUTHORIZED=true
IMPLEMENTATION_EXTERNAL_PREREQUISITE_RULE=ALL_EXTERNAL_DECISIONS_WITH_REQUIRED_BEFORE_IMPLEMENTATION_TRUE_HAVE_EXPLICIT_ACCEPTED_DISPOSITION
ACCEPTANCE_EXTERNAL_PREREQUISITE_RULE=ALL_EXTERNAL_DECISIONS_WITH_REQUIRED_BEFORE_ACCEPTANCE_TRUE_HAVE_ACCEPTED_EVIDENCE
```

The current task establishes none of those authorizations. The contract is
frozen for coordinator review only:

```text
PROPOSED_S5_A_CONTRACT_FROZEN=true
V0_3_S5_AUTHORIZED=false
S5_IMPLEMENTATION_STARTED=false
S5_A_IMPLEMENTATION_AUTHORIZED=false
S5_A_PRODUCTION_CODE_CHANGED=false
```

## 9. Acceptance evidence contract

A future S5-A implementation review must provide, at minimum:

1. A versioned pilot-run record binding public forecast identity, cutoff,
   model/parameter versions, input and retention authority, grain, lineage,
   actor (if enabled), status, and canonical hashes.
2. Two or more immutable forecast versions that survive fresh-session
   readback, with no overwrite/delete path.
3. Server-owned current/previous, approved-model, calibration,
   forecast/actual, naive-baseline, and P50/P80/P90 comparison results, with
   explicit unavailable/not-computable reasons where a comparison cannot be
   formed.
4. Typed data-gap/data-quality notices and evidence-derived explanations;
   tests must prove unsupported causes are not invented.
5. History query and deterministic exports with identity and source hashes.
6. Adoption and manual-adjustment hooks, if accepted into S5-A, with
   append-only lineage and an explicit non-acceptance boundary.
7. Production runtime binding, secret/config handling, migration procedure,
   authority-aware readiness, backup/restore, telemetry/alerting, incident
   and rollback evidence, and named owners.
8. Regression proof that S4 state remains isolated: no candidate execution,
   no validation budget delta, no TEST access, no S1 split change, and no S4
   plan amendment.

## 10. S5-B and S5-C boundaries

### S5-B — proposal only

S5-B may later own frontend comparison/warning presentation and structured
explanation UI. It is not implemented or authorized here. It must consume
server-owned S5-A evidence and must not recalculate business metrics or infer
causes in the browser.

### S5-C — proposal only

S5-C may later own recurring evaluation scheduling, long-term
adoption/non-adoption records, and continuous metric pipelines. It is not
implemented or authorized here. It must not turn an adoption record into a
business-acceptance record; S6 retains real-season acceptance authority.

## 11. Final disposition for this task

```text
S5_A_CONTRACT_PROPOSAL_COMPLETE=true
S5_A_CURRENT_IMPLEMENTATION_READINESS=BLOCKED_BY_IDENTIFIED_PREREQUISITES
S5_A_IMPLEMENTATION_READY=false
S5_A_CODE_GAP_COUNT=3
S5_A_RUNTIME_GAP_COUNT=7
S5_A_EXTERNAL_DECISION_GAP_COUNT=2
S5_A_EXTERNAL_DECISION_GAP_COUNT_SEMANTICS=COUNT_DEDICATED_S5A_EXT_PREFIX_GAPS_ONLY
S5_A_DEDICATED_EXTERNAL_GOVERNANCE_GAP_COUNT=2
S5_A_EXTERNAL_DECISION_REQUIRED_GAP_COUNT=10
S5_A_EXTERNAL_DECISION_RECORD_COUNT=5
S5_A_BLOCKING_GAP_IDS=
S5A-CODE-001,S5A-CODE-002,S5A-CODE-003,
S5A-RUNTIME-001,S5A-RUNTIME-002,S5A-RUNTIME-003,S5A-RUNTIME-004,
S5A-RUNTIME-005,S5A-RUNTIME-006,S5A-RUNTIME-007,
S5A-EXT-001,S5A-EXT-002
```

The only next action is coordinator review of this proposal. It does not
authorize S5 implementation, S4 continuation, TEST, model change, parameter
change, Ready, Merge, or release.

```text
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_REVIEW
```
