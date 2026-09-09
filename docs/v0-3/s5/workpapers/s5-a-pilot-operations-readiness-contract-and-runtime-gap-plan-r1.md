# Workpaper — S5-A Pilot Operations Readiness Contract and Runtime Gap Plan

TASK_ID=V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_AND_RUNTIME_GAP_PLAN_R1
TASK_CLASS=DOCUMENTATION_ONLY_PROPOSED_S5_EXECUTION_CONTRACT_FREEZE
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
AUDIT_BASE=origin/main
BASE_MAIN_SHA=49388438c0fb287068b3f0bb803f7c03bd00a81a
PR593_MERGE_IN_BASE=true
READ_ONLY_AUDIT=true

## 1. Purpose and method

This workpaper records a current-main, read-only review for a proposed S5-A
contract. It uses the current V0.3 plan as the authority and treats nearby
implementation as evidence only when the code path, persistence boundary, or
test evidence proves the stated capability. It does not promote the PR #593
planning names into formal S5 subtasks.

Audited areas included:

- `docs/v0-3/development-plan.md` §§4.7–4.8 and the append-only PR #593
  inventory pointer;
- `backend/app/trial.py`, `backend/app/api/trial.py`,
  `backend/app/api/health.py`;
- `backend/app/forecast_authority/retention.py`,
  `backend/app/models/forecast_authority.py`;
- `backend/app/core_forecast/application.py` and related repository/
  persistence paths;
- `backend/app/actual_harvest_imports.py`-related route/service paths and
  `backend/app/actual_harvest_labels/`;
- `backend/app/forecast_quality/`, `backend/app/models/forecast_quality.py`,
  and the relevant migrations;
- `frontend/src/pages/ForecastPage.tsx`, `frontend/src/pages/QualityPage.tsx`,
  `frontend/src/features/forecast/`, and `frontend/src/features/quality/`;
- `docker-compose.yml`, `docker-compose.test.yml`, Alembic inventory, API
  tests, browser tests, and scoped runtime documentation.

No production database, secret, TEST partition, prospective authority store,
or external runtime was accessed by this workpaper.

## 2. Current authority and isolation

Current S5 is a slice definition, not a frozen formal subtask decomposition:

```text
CURRENT_V0_3_S5_SLICE_DEFINITION_EXISTS=true
CURRENT_V0_3_S5_FORMAL_SUBTASK_DECOMPOSITION_EXISTS=false
V0_3_S5_CURRENT_DEFINITION_EXISTS=true
V0_3_S6_CURRENT_DEFINITION_EXISTS=true
PROPOSED_S5_EXECUTION_DECOMPOSITION_SOURCE=PR593_PLANNING_PROPOSAL
PROPOSED_S5_EXECUTION_DECOMPOSITION_AUTHORIZED=false
PROPOSED_S5_EXECUTION_DECOMPOSITION_IMPLEMENTED=false
```

The S5-A, S5-B, and S5-C labels are therefore proposal vocabulary. The
current §4.7 slice remains authoritative for the required capabilities; §4.8
remains authoritative for the real-season pilot and acceptance boundary.

The S4 boundary is unchanged:

```text
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

S5-A planning is not a reason to reopen historical S3-C, discover a new
authority store, run a prospective scan, execute a candidate, or change the
S4 plan.

## 3. What current main actually provides

### Forecast and immutable authority

`DefaultTrialApplicationService.create_forecast` resolves the current
forecast input authority, executes `execute_core_forecast_run`, and captures
the production base forecast authority immediately after a completed forecast
and before later Task10 work (`backend/app/trial.py`). The retention module
stores the immutable parent envelope and complete daily P50/P80/P90 rows,
cutoff, business grain, plan/Task8/Task9/Core lineage, and hashes. Its
`load_pit_visible_forecast_authority` path rechecks scope, status, cutoff,
identity, hash, lineage, and complete daily-row invariants.

This is a strong reusable foundation for S5-A. It does not itself provide a
pilot operations list, previous-run comparison, approved-model registry, or
adoption record.

### Actual-harvest and quality evidence

The actual-harvest API supports create, append/upload, preview, seal, validate,
error listing, commit, and scoped reads. The label-snapshot service creates
immutable snapshot headers and child rows with request identity, visibility
mode, winner/label/exclusion hashes, and zero-write replay for the same
identity. `AS_OF_EVALUATION` is enforced by the existing snapshot contract.

The trial quality flow binds a persisted forecast to a committed actual import,
creates a label snapshot, runs the existing S2 binding, persists quality
metrics/breakdowns/baseline/comparison evidence, and exposes report,
comparison, and CSV export routes. The existing comparison surface is a
model-versus-baseline comparison; it is not evidence of all §4.7 versioned
comparisons.

### API and browser surface

The trial API exposes forecast authority, forecast create/read, daily curve,
forecast export, actual-harvest lifecycle, quality-report read/create,
quality comparison, and quality export endpoints. `ForecastPage` reloads the
persisted forecast summary and daily curve and displays model/parameter/policy
versions, data-gap/blocker summaries, and hashes. `QualityPage` reloads the
persisted quality report and comparison and displays forecast/actual overlays,
metrics, coverage, reasons, and baseline comparison.

These pages demonstrate an engineering workflow. They do not prove the S5
comparison/warning/explanation/adoption workflow or the S6 business pilot.

### Runtime surface

`docker-compose.yml` is a local PostgreSQL 16 development composition using
port 5432 and local default credentials. `docker-compose.test.yml` is an
explicit TEST-only composition using a separate port/volume and must not be
read as production runtime evidence. `backend/app/api/health.py` provides
`/live` and `/ready`; `/ready` verifies `SELECT 1` but does not verify
migrations, forecast retention authority, backup, or pilot dependencies.

`backend/app/core/config.py` has local defaults (`localhost`, port 5432,
`blueberry_peak`, and a placeholder local password) with environment-file
support. This proves a configurable local engineering path, not a production
binding or secret-management decision. No current-main scoped production
runbook, backup/restore rehearsal, dashboard/alert policy, or named
operations/deployment/security owner was proven.

## 4. S5-A contract decisions

### 4.1 Run identity

The future run record must be derived from existing forecast and retention
identities wherever possible: public run ID, cutoff, created/available time,
model and parameter versions/identities, source/input authority hash, capture
identity, grain, lineage hashes, and status. Actor/operator identity is
available at the API authorization boundary but was not proven as a persisted
pilot-run field; it is therefore a `PROPOSED_FIELD`, not an existing field.
Likewise, a separate pilot-operation ID is a future `PROPOSED_FIELD`.

### 4.2 History and immutability

S5-A must retain the existing append-only forecast-authority semantics. A new
forecast is an additional version. Comparison and history must reference the
persisted identities and use verified readback; no client-side reconstruction
may become a second authority. Current main proves read-by-known-ID and
immutable capture validation, but not a complete operator history query.

### 4.3 Server-owned comparison

Comparison is a server contract, not a UI calculation. Each result must bind
the compared forecast/model/parameter members, common scope, cutoff and
actual-label authority, metric/policy identity, availability, reason codes,
and a canonical hash. The existing forecast/actual and naive-baseline paths
are reusable inputs. Current/previous forecast, previous pilot-approved model,
and before/after calibration comparison authority remain gaps.

```text
CLIENT_SIDE_BUSINESS_METRIC_RECOMPUTATION_ALLOWED=false
```

### 4.4 Notices and explanations

Existing forecast summaries and quality cells carry data-gap, blocker, and
reason strings. S5-A must turn these evidence references into a typed,
server-owned notice/explanation contract with code, source, affected run or
grain, severity/classification, and observed fact. It may not add a causal
claim that is absent from persisted evidence.

### 4.5 Adoption boundary

S5-A may expose the hook and persistence contract for an operational adoption
event and manual-adjustment reason. Those records are not acceptance. S5-C
may later own recurring adoption/non-adoption evaluation, and S6 owns
real-season business acceptance.

```text
BUSINESS_ADOPTION_IS_BUSINESS_ACCEPTANCE=false
```

## 5. Runtime checks and gap interpretation

The runtime review intentionally uses `NOT_PROVEN` where the repository
contains no production evidence. It does not infer a missing deployment from a
local compose file, and it does not convert a local/test database into a
production authority. The resulting seven runtime gaps are:

1. production PostgreSQL binding;
2. secret/config externalization;
3. migration and deployment procedure;
4. authority-aware readiness beyond `SELECT 1`;
5. backup and restore;
6. telemetry, logging, and alerting;
7. incident, rollback, and operating runbook.

The detailed fields and acceptance proofs are in the machine-readable evidence
file. They are pilot-readiness requirements, not reasons to modify runtime in
this documentation task.

## 6. Authorization gate and disposition

The future implementation gate is:

```text
MODEL_APPROVED_FOR_PILOT=true
CURRENT_V0_3_S4_COMPLETE=true
PROPOSED_S5_A_CONTRACT_ACCEPTED=true
S5_A_IMPLEMENTATION_SEPARATELY_AUTHORIZED=true
ALL_REQUIRED_EXTERNAL_PREREQUISITES_HAVE_EXPLICIT_DISPOSITION=true
```

Current disposition:

```text
S5_A_CONTRACT_PROPOSAL_COMPLETE=true
PROPOSED_S5_A_CONTRACT_FROZEN=true
S5_A_CURRENT_IMPLEMENTATION_READINESS=BLOCKED_BY_IDENTIFIED_PREREQUISITES
S5_A_IMPLEMENTATION_READY=false
S5_A_CODE_GAP_COUNT=3
S5_A_RUNTIME_GAP_COUNT=7
S5_A_EXTERNAL_DECISION_GAP_COUNT=2
V0_3_S5_AUTHORIZED=false
S5_IMPLEMENTATION_STARTED=false
S5_A_IMPLEMENTATION_AUTHORIZED=false
S5_A_PRODUCTION_CODE_CHANGED=false
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
FINAL_STOP_GATE=COORDINATOR_V0_3_S5_A_PILOT_OPERATIONS_READINESS_CONTRACT_REVIEW
```

The proposal is complete for review. It is not a claim that S5-A can be
accepted today; the identified prerequisites must be resolved in their proper
governance/implementation tasks first.
