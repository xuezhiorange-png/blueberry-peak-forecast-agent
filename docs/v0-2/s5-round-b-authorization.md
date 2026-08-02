# V0.2-S5 Round B Authorization Freeze

VERSION=0.2.0
SLICE=V0.2-S5
ROUND=S5_ROUND_B_AUTHORIZATION_FREEZE
REPOSITORY=xuezhiorange-png/blueberry-peak-forecast-agent
BASE_BRANCH=main
BASE_SHA=38043358e8310f3827f7d17329ba44f031a9a81d
DOCUMENT_PATH=docs/v0-2/s5-round-b-authorization.md
AUDIT_DATE=2026-08-02
AUDIT_MODE=READ_ONLY_CLOSEOUT_AND_AUTHORIZATION_DRAFT

S5_ROUND_A1_COMPLETE=true
S5_ROUND_A2_COMPLETE=true
S5_PRE_B_PUBLIC_DTO_HARDENING_COMPLETE=true
SOURCE_TASK_EXECUTION_RESULT=FAIL
SOURCE_TASK_BLOCK_REASON=TRANSIENT_UNAUTHORIZED_WRITE_IN_PROTECTED_WORKTREE_RECOVERED
PROTECTED_WORKTREE_TRANSIENT_WRITE_OCCURRED=true
PROTECTED_WORKTREE_FINAL_STATE_RESTORED=true
PROTECTED_WORKTREE_TRACKED_STATE_CHANGED_AT_END=false
PROTECTED_WORKTREE_PROTECTED_UNTRACKED_CONTENT_PRESERVED=true
NO_UNAUTHORIZED_MUTATION=false
NO_NEW_UNAUTHORIZED_MUTATION_IN_REMEDIATION=true
ROUND_A2_TECHNICAL_CLOSEOUT=PASS
ROUND_B_PRODUCT_READINESS=READY
SOURCE_TASK_PROCESS_INTEGRITY=FAIL
ROUND_B_READINESS=READY
ROUND_B_AUTHORIZATION_DRAFTED=true
ROUND_B_AUTHORIZATION_ACCEPTED=false
ROUND_B_IMPLEMENTATION_AUTHORIZED=false

BACKEND_CODE_AUTHORIZED=false
FRONTEND_CODE_AUTHORIZED=false
TEST_CODE_AUTHORIZED=false
DEPENDENCY_CHANGE_AUTHORIZED=false
WORKFLOW_CHANGE_AUTHORIZED=false
MIGRATION_CHANGE_AUTHORIZED=false
COMMIT_AUTHORIZED_FOR_DOCUMENT_ONLY=true
PUSH_AUTHORIZED_FOR_DOCUMENT_ONLY=true
DRAFT_PR_AUTHORIZED_FOR_DOCUMENT_ONLY=true
READY_AUTHORIZED=false
MERGE_AUTHORIZED=false
ROUND_C_AUTHORIZED=false
V0_2_RELEASE_AUTHORIZED=false
NO_STEP_IMPLIES_THE_NEXT=true
MANDATORY_STOP=true

## 1. Document identity and governance

This is an audit result and authorization draft, not an implementation
authorization. The only repository mutation allowed by this task is this
document, on a documentation branch and in a Draft PR.

The audit used live origin/main:

BASELINE_EXPECTED_SHA=38043358e8310f3827f7d17329ba44f031a9a81d
BASELINE_ACTUAL_SHA=38043358e8310f3827f7d17329ba44f031a9a81d
BASELINE_DRIFT=none
PR154_IS_ANCESTOR_OF_MAIN=true

During the source task, the authorization document was initially written to
the protected original worktree by mistake. The file was removed immediately,
and the protected worktree was restored to its original branch, HEAD, tracked
state, and protected untracked contents before the source task ended.

The transient write did not enter the Round B authorization branch and did not
change the final PR path set. It was nevertheless an unauthorized write during
execution. The source task therefore correctly reported FAIL and preserved
NO_UNAUTHORIZED_MUTATION=false. No backend, frontend, test, migration,
workflow, manifest, dependency, or lockfile change is authorized here.

The final state being restored does not erase the execution event.

## Execution-integrity disclosure

1. What happened: the new authorization document was first applied in the
   protected source worktree instead of the isolated documentation worktree.
2. Write target: the protected original worktree at
   /Users/charles/Documents/智能agent开发.
3. Discovery: the issue was found immediately when the intended isolated
   worktree did not contain the new document and the original worktree showed
   an unexpected untracked docs file.
4. Recovery: the accidental document file was removed immediately. No
   protected untracked file was removed, moved, overwritten, or staged.
5. Final state: the original branch, HEAD, tracked state, and protected
   untracked contents were restored. The protected worktree ended with the
   same final state as its start snapshot.
6. Branch and PR integrity: the transient file was never committed to the
   Round B authorization branch. The PR contains only
   docs/v0-2/s5-round-b-authorization.md.
7. Process result: recovery produced no remaining file delta, but it did not
   make the source execution compliant. The source task remains FAIL with
   NO_UNAUTHORIZED_MUTATION=false.
8. Product result: the independent Round A2 technical evidence and product
   readiness conclusions remain separately reviewable. They do not override
   the process failure.
9. Correction method: this disclosure is being added as a new ordinary
   commit. Existing commits are not amended, removed, or rewritten.
10. Governance boundary: Ready, Merge, Round B implementation, Round C, and
    V0.2 release remain unauthorized.

This event is retained as an execution violation. It is not described as
harmless, irrelevant, compliant, or absent.

Execution and product conclusions are intentionally separate:

ROUND_A2_TECHNICAL_CLOSEOUT=PASS
ROUND_B_PRODUCT_READINESS=READY
SOURCE_TASK_PROCESS_INTEGRITY=FAIL
ROUND_B_AUTHORIZATION_ACCEPTED=false
ROUND_B_IMPLEMENTATION_AUTHORIZED=false

ROUND_B_READINESS=READY is a product and technology audit conclusion. The
source task execution result is a governance/process conclusion. Neither
conclusion overwrites the other. This corrective document does not accept
Round B authorization and does not authorize Round B implementation.

## 2. Round A1 and Round A2 closeout evidence

### 2.1 Live merged PR facts

| PR | Title | State | Merged | Merge SHA | Merged at | Base | Final PR head |
| ---: | --- | --- | --- | --- | --- | --- | --- |
| 143 | feat(v0.2-s5): add Trial import API foundation | MERGED | true | 96fd95b8fdf03040329b1294ab7fbad9371dc3b3 | 2026-07-30T14:12:14Z | main | 03e4ca53ab939f362c76f238c9baeccac434db53 |
| 145 | feat(v0.2-s5): add A2 schema authority persistence | MERGED | true | e496adbc5edb741191e2d50946d3e9a29ab38755 | 2026-07-31T17:10:58Z | main | 7b27788096dc83ecbcdffcec933e9142b0028651 |
| 149 | feat(v0.2-s5): add A2 Forecast authority and adapters | MERGED | true | c6ecf13348bfcbdd1d6c8e6636262fb4e85e4d52 | 2026-08-01T09:29:48Z | main | 4a7104ba5606ab7fb0beda76749aed923e36289e |
| 150 | fix(v0.2-s5): persist immutable Trial Forecast evidence | MERGED | true | 63000a98de47f7d261c876ddf9a18c32a3d49c53 | 2026-08-01T03:11:10Z | main | 502a907941dedf0c5a4acde2a139d6b9a6afa735 |
| 151 | test(v0.2-s5): harden A2 Forecast public contracts | MERGED | true | 5dded261850de5f1d1edaa826ffda99a129efc0d | 2026-08-01T11:01:33Z | main | 73f2a8d618c9ab2fe0c4c41ac3518e4bd397b755 |
| 152 | feat(v0.2-s5): add A2 Quality adapters and typed metrics | MERGED | true | c24d91719b03ecd213db568a22653376edecf8ae | 2026-08-02T12:59:09Z | main | 7cb4d917400454d5ce6650c9a74ae5bd9ac8c99a |
| 153 | fix(v0.2-s2): persist I7 snapshot scope as canonical JSON | MERGED | true | a53ff7fa7a935597f4ee68606c808cba62c63c30 | 2026-08-02T02:10:47Z | main | 505ce0c44255ba9f95169e54def7d4386df310b3 |
| 154 | fix(v0.2-s5): type Forecast public summary contracts | MERGED | true | 38043358e8310f3827f7d17329ba44f031a9a81d | 2026-08-02T14:43:28Z | main | 7a942528bae1bfabb5d7cc2b4c2cdb4c39ba2767 |

The merge commits, states, base branches, merge timestamps, and complete final
PR-head SHA values above were read from GitHub; the audited main is exactly
the PR154 merge commit.

PR143_MERGED=true
PR145_MERGED=true
PR149_MERGED=true
PR150_MERGED=true
PR151_MERGED=true
PR152_MERGED=true
PR153_MERGED=true
PR154_MERGED=true
MAIN_CONTAINS_PR154=true

### 2.2 Post-merge main acceptance

POST_MERGE_CI_RUN_ID=30752739540
POST_MERGE_CI_URL=https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/30752739540
POST_MERGE_CI_EVENT=push
POST_MERGE_CI_HEAD_SHA=38043358e8310f3827f7d17329ba44f031a9a81d
POST_MERGE_CI_STATUS=completed
POST_MERGE_CI_CONCLUSION=success
REQUIRED_CHECK_CONFIGURATION=NONE_OR_NOT_PROVEN

The push full-suite-canary succeeded. PR-only jobs were skipped by the
existing event condition; they are not represented as passed.

| Job | Status | Conclusion | Meaning |
| --- | --- | --- | --- |
| full-suite-canary | completed | success | main push acceptance |
| static | completed | skipped | PR-only |
| unit-contract-golden | completed | skipped | PR-only |
| postgres-migration | completed | skipped | PR-only |
| postgres-domain-1 | completed | skipped | PR-only |
| postgres-domain-2 | completed | skipped | PR-only |
| postgres-task11 | completed | skipped | PR-only |
| postgres-concurrency | completed | skipped | PR-only |
| compose-smoke | completed | skipped | PR-only |

The successful canary completed PostgreSQL service readiness, isolated
database creation and identity validation, Alembic upgrade head, full pytest,
JUnit upload, database drop, and container cleanup. It identified PostgreSQL
16.14 and ended with:

FULL_PYTEST_RESULT=3399 passed, 3 skipped, 646275 warnings in 1031.09s
POST_MERGE_POSTGRESQL16=PASS
POST_MERGE_FULL_SUITE_CANARY=PASS

Warnings are recorded and are not failures. The current audited command also
returned:

ALEMBIC_HEAD_COUNT=1
ALEMBIC_HEAD=0027_s5_a2_forecast_evidence_persistence

Round B adds no migration.

## 3. Current Trial API inventory

backend/tests/trial/test_api.py::test_openapi_schema_acceptance asserts
fourteen current paths. The inventory below is derived from
backend/app/api/trial.py and the DefaultTrialApplicationService methods.

| Method and route | Request DTO | Response / success | Permission | Public identity | Error family | Production adapter | Round B browser owner | Round C owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GET /api/v1/trial/forecast-input-authority | none | TrialForecastInputAuthorityResponse / 200 | may_read_forecast_authority | authority hash and business keys | RESOURCE_NOT_FOUND, TRIAL_AUTHORITY_UNAVAILABLE | READY | ForecastPage / forecastApi | none |
| POST /api/v1/trial/forecasts | TrialForecastCreateRequest | TrialForecastSummaryResponse / 200 | may_create_forecast | public request hash run_id | TRIAL_REQUEST_INVALID, TRIAL_INPUT_NOT_SUPPORTED, RESOURCE_NOT_FOUND, policy missing/conflict, CONFLICTING_REPLAY, CONCURRENCY_CONFLICT | READY | ForecastPage / forecastApi | none |
| GET /api/v1/trial/forecasts/{run_id} | path run_id | TrialForecastSummaryResponse / 200 | may_read_forecast | lowercase public run_id | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, CONCURRENCY_CONFLICT | READY | ForecastPage / forecastApi | none |
| GET /api/v1/trial/forecasts/{run_id}/daily-curve | path run_id | TrialForecastDailyCurveResponse / 200 | may_read_forecast | lowercase public run_id | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, CONCURRENCY_CONFLICT | READY | ForecastPage / DailyCurve | none |
| GET /api/v1/trial/forecasts/{run_id}/export.csv | path run_id | text/csv / 200 | may_export_forecast | public run_id and server filename | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, CONCURRENCY_CONFLICT | READY | ForecastPage / ExportButton | none |
| POST /api/v1/trial/actual-harvest/imports | TrialActualHarvestImportCreateRequest | TrialActualHarvestImportCreateResponse / 200 | may_create | public import_id | TRIAL_REQUEST_INVALID, RESOURCE_NOT_FOUND, CONFLICTING_REPLAY, authorization-unavailable mapping | READY | QualityPage / importApi | none |
| GET /api/v1/trial/actual-harvest/imports/{import_id} | path import_id | TrialActualHarvestImportStatusResponse / 200 | may_preview | public import_id | RESOURCE_NOT_FOUND and safe lifecycle mapping | READY | QualityPage / importApi | none |
| POST /api/v1/trial/actual-harvest/imports/{import_id}/upload | raw bytes plus content-type, x-file-name, optional x-file-sha256 | TrialActualHarvestUploadResponse / 200 | may_append | public import_id | 413 size, 415 MIME, unsafe name, hash, parse and validation errors | READY | QualityPage / importApi | none |
| GET /api/v1/trial/actual-harvest/imports/{import_id}/errors | page_size and opaque page_token | TrialActualHarvestInvalidRowsResponse / 200 | may_validate | public import_id | RESOURCE_NOT_FOUND and validation mapping | READY | QualityPage / importApi | none |
| POST /api/v1/trial/actual-harvest/imports/{import_id}/commit | ActualHarvestApiCommitRequest | TrialActualHarvestCommitResponse / 200 | may_commit | public import_id and validation identity | IMPORT_NOT_READY_FOR_COMMIT, CONFLICTING_REPLAY, CONCURRENCY_CONFLICT, RESOURCE_NOT_FOUND | READY | QualityPage / importApi | none |
| POST /api/v1/trial/quality-reports | TrialQualityReportCreateRequest | TrialQualityReportResponse / 200 | may_create_quality | evaluation_instance_hash report_id | TRIAL_REQUEST_INVALID, RESOURCE_NOT_FOUND, CONFLICTING_REPLAY, EVIDENCE_CONFLICT, QUALITY_AUTHORITY_UNAVAILABLE, QUALITY_PERSISTENCE_UNAVAILABLE | READY | QualityPage / qualityApi | none |
| GET /api/v1/trial/quality-reports/{report_id} | path report_id | TrialQualityReportResponse / 200 | may_read_quality | public evaluation instance hash | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, QUALITY_PERSISTENCE_UNAVAILABLE | READY | QualityPage / qualityApi | none |
| GET /api/v1/trial/quality-reports/{report_id}/comparison | path report_id | TrialQualityComparisonResponse / 200 | may_read_quality_comparison | public evaluation instance hash | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, QUALITY_PERSISTENCE_UNAVAILABLE | READY | QualityPage / qualityApi | none |
| GET /api/v1/trial/quality-reports/{report_id}/export.csv | path report_id | text/csv / 200 | may_export_quality | public evaluation instance hash and server filename | RESOURCE_NOT_FOUND, EVIDENCE_CONFLICT, QUALITY_PERSISTENCE_UNAVAILABLE | READY | QualityPage / qualityApi | none |

Every JSON error uses TrialErrorResponse with request_id, status, code,
message_template_id, retryable, and sanitized details. CSV is server-produced
text/csv. Decimal values stay canonical strings; dates and timezone-aware
timestamps remain distinct. No internal integer ID is a browser identity.

## 4. Current backend production capability matrix

READY below means a public production entry, persisted authority, public DTO,
and evidence beyond a synthetic double. PostgreSQL evidence refers to the
successful post-merge full suite unless a targeted node is named.

### 4.1 Actual Harvest

| Capability | Status | PRODUCTION_ENTRY | PERSISTENCE_AUTHORITY | PUBLIC_DTO | PUBLIC_ENDPOINT | TEST_EVIDENCE | POSTGRESQL_EVIDENCE | REMAINING_GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Raw-byte CSV upload | READY | upload_import and _upload_metadata | import batch, records, seal and validation | TrialActualHarvestUploadResponse | POST .../upload | test_xlsx_upload_reuses_parser_and_lifecycle plus CSV upload tests | 30752739540 | UI not connected |
| Raw-byte XLSX upload | READY | upload_import parse_xlsx branch | same lifecycle persistence | TrialActualHarvestUploadResponse | POST .../upload | test_xlsx_upload_reuses_parser_and_lifecycle | 30752739540 | UI not connected |
| Safe filename/MIME/size/hash checks | READY | _upload_metadata and _read_bounded_upload | source-file metadata and validation hash | TrialErrorResponse / upload response | POST .../upload | invalid MIME/name/hash/size tests | 30752739540 | Browser must send exact headers |
| Append, seal and validate lifecycle | READY | upload_import orchestrates all three | append/seal/validation persistence | upload and status DTOs | POST upload and GET status | lifecycle and validation contract tests | 30752739540 | No separate public append/seal route; upload is the public lifecycle |
| Invalid-row readback | READY | get_import_errors | persisted validation rows/result identity | TrialActualHarvestInvalidRowsResponse | GET .../errors | invalid-row pagination/readback tests | 30752739540 | UI must not revalidate locally |
| Status polling | READY | get_import | persisted batch status and validation summary | TrialActualHarvestImportStatusResponse | GET .../{import_id} | import status API tests | 30752739540 | Polling UI not wired |
| Commit | READY | commit_import and commit_batch | committed import and commit manifest | TrialActualHarvestCommitResponse | POST .../commit | commit/replay/not-ready tests | 30752739540 | Commit UI disabled |
| Owner/source/channel authorization | READY | shared get_actual_harvest_actor and require_actor_scope | scoped import ownership | sanitized TrialErrorResponse | all import routes | actor/source/channel tests | 30752739540 | No browser auth parser |
| Concealed cross-scope access | READY | _load_scoped_import_batch | owner/source binding | RESOURCE_NOT_FOUND | resource routes | cross-scope tests | 30752739540 | UI must not reveal existence |

### 4.2 Forecast

| Capability | Status | PRODUCTION_ENTRY | PERSISTENCE_AUTHORITY | PUBLIC_DTO | PUBLIC_ENDPOINT | TEST_EVIDENCE | POSTGRESQL_EVIDENCE | REMAINING_GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Input authority read | READY | get_forecast_input_authority | authority snapshot, plan and policy evidence | TrialForecastInputAuthorityResponse | GET authority | authority and OpenAPI tests | Forecast PostgreSQL nodes in 30752739540 | selectors not wired |
| Business-key resolution | READY | _resolve_create_authority | plan/policy business-key hashes | create/authority DTOs | GET authority, POST forecasts | authority/mismatch tests | 30752739540 | no internal IDs |
| Destination factory authority | READY | _resolve_create_authority | authoritative factory membership and policy | business-key fields | GET/POST | factory/policy tests | 30752739540 | UI not wired |
| Planting-area comparison | READY | authority resolution before Core | authoritative Decimal area | summary/error DTO | POST forecasts | mismatch and zero-write tests | 30752739540 | confirmation UI absent |
| Retention-policy selection | READY | _select_retention_policy | immutable policy version/row hash | policy_versions | authority/create | missing/conflict tests | 30752739540 | no client policy lookup |
| Core Forecast create | READY | create_forecast -> execute_core_forecast_run | Core run plus evidence/binding transaction | TrialForecastSummaryResponse | POST forecasts | create/replay/rollback tests | 30752739540 | form disabled |
| Immutable Forecast evidence | READY | create_forecast_evidence_and_binding_in_result_boundary | trial_forecast_evidence and FORECAST binding | persisted summary | create/read | evidence integrity tests | 30752739540 | browser read only |
| Actor-scoped read | READY | _load_verified_forecast | scoped binding/evidence/Core run | TrialForecastSummaryResponse | GET forecast | owner/half-state tests | 30752739540 | read UI absent |
| Daily curve | READY | _project_daily_curve | persisted Core daily rows | TrialForecastDailyCurveResponse | GET daily-curve | daily stability tests | 30752739540 | chart placeholder |
| Typed summary/peaks/inventory/backlog | READY | _project_forecast_summary | P50 metric, last P50 row, policy version | typed nested Forecast DTOs | create/GET | PR154 contract and parity tests | 30752739540 | schemas/display not wired |
| Provenance | READY | persisted Core/evidence projection | model/parameter/policy authority | summary provenance | create/GET | contract/readback tests | 30752739540 | version panel placeholder |
| Canonical CSV | READY | _project_forecast_csv | persisted Core rows/evidence | opaque text/csv | GET export | header/decimal/order/stability tests | 30752739540 | button disabled |
| Exact replay | READY | canonical create/evidence replay | unique request/evidence identity | same public run_id | POST | zero-write replay tests | 30752739540 | browser retry lifecycle |
| Conflicting replay | READY | typed conflict mapping | immutable evidence cannot be overwritten | CONFLICTING_REPLAY | POST | conflict/fail-closed tests | 30752739540 | browser conflict state |

### 4.3 Quality

| Capability | Status | PRODUCTION_ENTRY | PERSISTENCE_AUTHORITY | PUBLIC_DTO | PUBLIC_ENDPOINT | TEST_EVIDENCE | POSTGRESQL_EVIDENCE | REMAINING_GAP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Create from committed import | READY | create_quality_report | committed import, Forecast, I7, S2 and Quality persistence | TrialQualityReportCreateRequest/Response | POST quality-reports | Default service create/replay tests | test_default_trial_quality_service_postgres_create_replay_and_status_readback; 30752739540 | page not wired |
| Point-in-time S2 authority | READY | _create_quality_label_snapshot and _build_quality_s2_candidates | I7 AS_OF_EVALUATION plus S2 run/manifest/rows | horizon DTOs | create/read | historical binding tests | 30752739540 | no browser cutoff flow |
| Persisted readback | READY | load_quality_evaluation_by_instance_hash | sealed run/manifest/child hashes | TrialQualityReportResponse | GET | missing/hash drift tests | 30752739540 | passthrough frontend schema |
| Daily forecast/actual overlay | READY | _project_quality_report | persisted S2 rows and label authority | TrialQualityDailyOverlayRow | GET | overlay/status tests | 30752739540 | placeholder component |
| Typed daily metrics | READY | Quality readback | quality_metric_result | TrialQualityMetric | GET | typed metric tests | 30752739540 | no UI projection |
| Typed cumulative metrics | READY | Quality readback | persisted metric evidence | TrialQualityHorizonMetrics | GET | horizon tests | 30752739540 | no UI projection |
| Typed peak metrics | READY | persisted metric projection | Quality status/result evidence | TrialQualityPeakMetric | GET | frozen status tests | 30752739540 | no UI projection |
| Typed 7/14/21 horizons | READY | verified Quality read model | complete horizon result sets | TrialQualityHorizonMetrics | GET | completeness tests | 30752739540 | report page unavailable |
| Typed P80/P90 coverage | READY | persisted status evidence | quality_metric_result rows | TrialQualityCoverageMetric | GET | 30-record status tests | 30752739540 | browser must not calculate |
| Typed interval metrics | READY | persisted interval evidence | quality_metric_result rows | TrialQualityIntervalMetric | GET | lower-bound/null tests | 30752739540 | browser must not derive width |
| Persisted baseline comparison | READY | verified comparison readback | comparison rows and hashes | TrialQualityComparisonResponse | GET comparison | comparison/tamper tests | 30752739540 | component placeholder |
| Quality CSV | READY | _project_quality_csv | same verified readback as GET | opaque text/csv | GET export | deterministic/stability tests | 30752739540 | export not connected |
| Actor-scoped ownership | READY | _require_quality_permission and binding query | QUALITY_REPORT owner/parent binding | concealed RESOURCE_NOT_FOUND | create/read/comparison/export | channel/owner tests | 30752739540 | UI must not expose actor |
| Evidence fail closed | READY | Quality/S2 complete loaders | manifests, hashes, child sets | EVIDENCE_CONFLICT or QUALITY_PERSISTENCE_UNAVAILABLE | create/read/export | rollback/readback/cross-run tests | 30752739540 | stable UI catalog needed |

Capability conclusion:

ACTUAL_HARVEST_PRODUCTION_READINESS=READY
FORECAST_PRODUCTION_READINESS=READY
QUALITY_PRODUCTION_READINESS=READY
BACKEND_CHANGED_PATH_COUNT_FOR_ROUND_B=0
MIGRATION_CHANGED=false
FORECAST_ALGORITHM_CHANGED=false
QUALITY_ALGORITHM_CHANGED=false

## 5. Current frontend action matrix

The old document declares 42 actions but groups them in ten table rows. To
preserve its count, this matrix keeps P50/P80/P90 as one display action and
farm/variety/season Quality selection as one grouped action. This produces
exactly 42 legacy actions.

| # | Page | Action | Current evidence | Classification | Round B owner |
| ---: | --- | --- | --- | --- | --- |
| 1 | Forecast | enter farm | disabled form; authority/business-key contract exists | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 2 | Forecast | enter variety | disabled form; business-key contract exists | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 3 | Forecast | enter planting area | disabled form; Decimal comparison exists | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 4 | Forecast | optional flowering date | server accepts only null unsupported option | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 5 | Forecast | optional maturity stage | server accepts only null unsupported option | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 6 | Forecast | optional already-picked quantity | server accepts only null unsupported option | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 7 | Forecast | enter season | authority/create contract exists; control disabled | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 8 | Forecast | enter forecast cutoff/date | aware cutoff exists; no live submit | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastForm |
| 9 | Forecast | create forecast | adapter has stale request names and page does not call it | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastPage / forecastApi |
| 10 | Forecast | read summary | adapter exists; result is unavailable placeholder | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult |
| 11 | Forecast | read daily curve | adapter exists; chart is placeholder | BACKEND_READY_FRONTEND_NOT_WIRED | DailyCurve |
| 12 | Forecast | view P50/P80/P90 | typed backend response exists; no live projection | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult / DailyCurve |
| 13 | Forecast | view single-day peak | PR154 DTO exists; PeakSummary shows dash | BACKEND_READY_FRONTEND_NOT_WIRED | PeakSummary |
| 14 | Forecast | view cumulative | persisted summary/daily evidence exists; no binding | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult |
| 15 | Forecast | view mature inventory | typed DTO exists; no binding | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult |
| 16 | Forecast | view backlog | typed DTO exists; no binding | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult |
| 17 | Forecast | view gaps/blockers | server evidence/error fields exist; UI unavailable | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult / ErrorState |
| 18 | Forecast | view model/parameter versions | persisted provenance exists; UI placeholder | BACKEND_READY_FRONTEND_NOT_WIRED | ForecastResult |
| 19 | Forecast | export CSV | adapter exists; button disabled | BACKEND_READY_FRONTEND_NOT_WIRED | ExportButton |
| 20 | Forecast | view sustained seven-day peak | typed DTO and PostgreSQL parity exist; no UI projection | BACKEND_READY_FRONTEND_NOT_WIRED | PeakSummary |
| 21 | Quality | choose CSV | local file selection and hash only | FRONTEND_ADAPTER_ONLY | QualityPage |
| 22 | Quality | choose XLSX | local file selection only | FRONTEND_ADAPTER_ONLY | QualityPage |
| 23 | Quality | create import | importApi exists; importChainAvailable=false | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage / importApi |
| 24 | Quality | choose historical cutoff | request DTO exists; no live control | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage |
| 25 | Quality | upload bytes | postBytes exists; UI disabled | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage / importApi |
| 26 | Quality | append file content | server upload orchestrates append; UI absent | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage |
| 27 | Quality | trigger validation | server upload validates; UI absent | BACKEND_READY_FRONTEND_NOT_WIRED | ImportLifecycle |
| 28 | Quality | view invalid-record result | errors DTO exists; result grid is dash | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage |
| 29 | Quality | create quality report | qualityApi exists; no committed-import flow | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage / qualityApi |
| 30 | Quality | read quality report | QualityReport placeholder | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 31 | Quality | read comparison | adapter/typed backend response exists; not wired | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 32 | Quality | view daily overlay | typed persisted overlay exists; placeholder | BACKEND_READY_FRONTEND_NOT_WIRED | QualityOverlay |
| 33 | Quality | view 7/14/21 metrics | typed horizon exists; not wired | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 34 | Quality | poll import status | endpoint exists; lifecycle component static | BACKEND_READY_FRONTEND_NOT_WIRED | ImportLifecycle |
| 35 | Quality | commit import | endpoint exists; button disabled | BACKEND_READY_FRONTEND_NOT_WIRED | QualityPage / importApi |
| 36 | Quality | view excluded/not-computable reasons | persisted reason codes exist; not rendered | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport / QualityOverlay |
| 37 | Quality | export Quality CSV | adapter exists; button absent/disabled | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 38 | Quality | choose farm/variety/season | Quality scope is inherited from Forecast/Import; no independent DTO fields | OUT_OF_ROUND_B_SCOPE | inherited scope display only |
| 39 | Quality | view daily metrics | persisted typed metrics; no read binding | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 40 | Quality | view peak metrics | persisted typed peaks; no read binding | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 41 | Quality | view P80/P90 coverage | persisted typed coverage; no read binding | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |
| 42 | Quality | view interval metrics | persisted typed interval; no read binding | BACKEND_READY_FRONTEND_NOT_WIRED | QualityReport |

S5_BROWSER_ACTION_COUNT=42
ALREADY_PRODUCTION_WIRED_COUNT=0
FRONTEND_ADAPTER_ONLY_COUNT=2
BACKEND_READY_FRONTEND_NOT_WIRED_COUNT=39
BACKEND_CONTRACT_AMBIGUOUS_COUNT=0
BACKEND_CAPABILITY_MISSING_COUNT=0
OUT_OF_ROUND_B_SCOPE_COUNT=1

The old counts of 12 supported, 8 adapter-only, 16 missing and 6 ambiguous
are stale. They described the pre-A2/pre-foundation repository and are not
current readiness evidence.

## 6. Delta from the previous frontend authorization audit

The old docs/v0-2/s5-frontend-implementation-authorization.md is stale:

- It says no package, lockfile, Vite, router, or Playwright exists; the
  current frontend has all of these.
- It says there are eleven Trial endpoints; the current OpenAPI test proves
  fourteen, including authority and raw upload/error routes.
- It says Forecast authority, Forecast evidence/read/daily/export, Quality
  readback/comparison, and Trial file transport are missing; the merged A2
  production adapters now provide them.
- It records TypeScript 7.0.2 and an uncreated package; the live package pins
  TypeScript 6.0.3 and exact React/Vite/Zod/Vitest/Playwright dependencies.
- It calls the old ten backend blockers current; each requested backend
  capability is READY in the current matrix.
- Current frontend tests still assert unavailable/disabled behavior and
  zero production requests. They are foundation evidence, not integration
  acceptance.

docs/v0-2/s5-round-a2-backend-gap-authorization.md is also an historical
pre-A2 ledger. Its migration and adapter gaps are closed by PR143/145/149/150/
151/152/153/154 and the post-merge full suite. Neither old document is copied
as current authorization.

## 7. Round B product and technical boundary

ROUND_B_SCOPE=FRONTEND_PRODUCTION_INTEGRATION_AND_BROWSER_ACCEPTANCE
ROUND_B_READINESS=READY
ROUND_B_BLOCKER_COUNT=0

Round B delivers:

- the current Forecast page against authority, create, GET, daily and export;
- the current Quality page against actual-harvest create/upload/status/errors/
  commit and Quality create/read/comparison/export;
- strict transport schemas and the centralized error catalog;
- stable Decimal/date/time display and idempotency behavior;
- real desktop/mobile browser acceptance.

Round B does not deliver:

- any backend or database code;
- any Forecast formula, model, metric, policy, or parameter change;
- any Quality/S2/S3 calculator or evidence change;
- any client-side forecast/actual join or metric calculation;
- any new API endpoint;
- admin, dashboard expansion, LLM/chat, operational recommendations, or
  release packaging.

No backend blocker is hidden in a frontend workaround:

BACKEND_CHANGED_PATH_COUNT=0
MIGRATION_CHANGED=false
FORECAST_ALGORITHM_CHANGED=false
QUALITY_ALGORITHM_CHANGED=false
CLIENT_SIDE_RECOMPUTATION=false

## 8. API ownership and transport rules

FRONTEND_CALLS_ONLY=/api/v1/trial/*
INTERNAL_API_CALLS_FORBIDDEN=true
DATABASE_IDS_IN_BROWSER_FORBIDDEN=true
CLIENT_SIDE_METRIC_RECOMPUTATION_FORBIDDEN=true
CLIENT_SIDE_FORECAST_ACTUAL_JOIN_FORBIDDEN=true
SYNTHETIC_PRODUCTION_DATA_FORBIDDEN=true
IN_MEMORY_PRODUCTION_FALLBACK_FORBIDDEN=true
RAW_EXCEPTION_TEXT_IN_UI_FORBIDDEN=true
TRANSPORT_DECIMAL=canonical decimal string
NATIVE_FLOAT_FOR_BUSINESS_QUANTITIES_FORBIDDEN=true
BUSINESS_DATE=ISO-8601 date
EVENT_TIMESTAMP=timezone-aware RFC3339
DATE_TIMESTAMP_INTERCHANGE_FORBIDDEN=true
FORECAST_RUN_ID=public lowercase SHA-256
QUALITY_REPORT_ID=public lowercase SHA-256
INTERNAL_INTEGER_ID_EXPOSURE_FORBIDDEN=true

Zod schemas must be strict and reject unknown keys. They must validate public
SHA-256 identities, Decimal strings, ISO dates, and aware timestamps. Browser
formatting must not turn business quantities into floating-point calculations.

## 9. Error catalog and UI-state rules

The future error catalog must cover RESOURCE_NOT_FOUND,
TRIAL_REQUEST_INVALID, TRIAL_INPUT_NOT_SUPPORTED,
MARKETABLE_RETENTION_POLICY_MISSING, MARKETABLE_RETENTION_POLICY_CONFLICT,
TRIAL_AUTHORITY_UNAVAILABLE, QUALITY_AUTHORITY_UNAVAILABLE,
QUALITY_PERSISTENCE_UNAVAILABLE, EVIDENCE_CONFLICT, CONFLICTING_REPLAY,
CONCURRENCY_CONFLICT, and all actual-harvest upload/parse/validation/commit
codes.

| Server result | UI state | Rule |
| --- | --- | --- |
| 404 RESOURCE_NOT_FOUND | concealed not-found/empty | Do not reveal existence, owner or scope |
| 422 request invalid | form error | Preserve input; no automatic retry |
| 422 unsupported input | unsupported | Explain server contract; no local workaround |
| 409 conflicting replay | conflict | Do not overwrite or retry with a new identity |
| 409 evidence conflict | integrity error | Stop presentation and offer safe reload |
| 409 concurrency conflict | stale | Reload the public resource |
| 503 authority/persistence | retryable unavailable | Bounded retry or explicit user action only |
| upload 413/415/422 | upload validation | Do not claim acceptance |
| network/unknown | safe unavailable | Never show raw exception text |

Actor identity, permission parsing, allowed source scope and API channel stay
server-owned and fail closed. Cross-owner operations stay concealed 404.

## 10. Idempotency and file lifecycle

Use the existing frontend idempotency helper without making it a new identity
authority:

- Quality sends the full public request plus request_idempotency_key.
- Forecast uses the server's canonical request/replay identity.
- Actual import uses the server's Trial create replay identity.
- A retry after an unknown network result reuses the same key.
- x-request-id is correlation only.

Quality flow:

1. create import metadata;
2. send raw CSV/XLSX bytes to the Trial upload route with validated
   content-type, x-file-name and optional x-file-sha256;
3. poll status;
4. read invalid rows;
5. commit with the server validation identity;
6. create and read Quality using committed import plus exact cutoffs.

The browser must not call internal actual-harvest routes, parse files as a
replacement for the server, append rows locally, or fabricate COMMITTED.

## 11. Forecast and Quality page contracts

ForecastPage must load authority, select returned business keys, display and
confirm authoritative Decimal area, submit exact current request names, keep
unsupported optional inputs null/disabled, retain replay identity, render the
persisted summary and daily curve, display typed P50/P80/P90/peaks/inventory/
backlog/provenance/blockers, and export server CSV bytes.

QualityPage must require a same-owner Forecast and committed import, execute
create/upload/poll/errors/commit through Trial routes, submit exact cutoffs and
7/14/21 horizons, render persisted overlay, daily/cumulative/peak/coverage/
interval/reason fields, render persisted comparison, and use the same verified
readback source for GET/comparison/CSV.

Quality has no independent farm/variety/season authority selector. Its scope
comes from the persisted Forecast and committed Import evidence.

## 12. Browser E2E and nonfunctional acceptance

Real happy-path E2E must run against an isolated backend/PostgreSQL 16
identity. Frontend API mocks are not allowed for production acceptance.
Network-fault injection is allowed only in separate negative tests.

Forecast scenarios:

- authority success and unavailable;
- valid create, exact replay, conflicting replay;
- unsupported optional input and planting-area mismatch;
- concealed 404;
- daily curve, single-day peak, sustained-seven-day peak;
- inventory/backlog, CSV export;
- desktop/mobile and no horizontal overflow.

Actual Harvest/Quality scenarios:

- CSV/XLSX happy path;
- invalid filename/MIME and oversized upload;
- validation error and invalid-row display;
- status polling, commit and commit conflict;
- Quality create/read, overlay, 7/14/21 metrics;
- coverage, interval null/unavailable, baseline comparison;
- Quality CSV export, concealed 404;
- desktop/mobile and no horizontal overflow.

Accessibility and security:

- keyboard reachable controls, visible focus and associated labels;
- live-region status/error changes and no color-only meaning;
- duplicate mutation prevention while submitting;
- no owner identity, database ID, stack trace, SQL, secret or environment
  value in DOM;
- server remains authoritative for filename, MIME and upload size.

## 13. Exact future changed-path allowlist

This is a future ceiling, not current implementation authorization.

ROUND_B_CREATE_PATHS=none
ROUND_B_CREATE_PATH_COUNT=0

ROUND_B_MODIFY_PATHS=
frontend/src/app/App.tsx
frontend/src/app/app.css
frontend/src/pages/ForecastPage.tsx
frontend/src/pages/QualityPage.tsx
frontend/src/features/forecast/ForecastForm.tsx
frontend/src/features/forecast/ForecastResult.tsx
frontend/src/features/forecast/forecastApi.ts
frontend/src/features/forecast/forecastSchemas.ts
frontend/src/features/actualHarvest/ImportLifecycle.tsx
frontend/src/features/actualHarvest/importApi.ts
frontend/src/features/quality/QualityReport.tsx
frontend/src/features/quality/QualityOverlay.tsx
frontend/src/features/quality/qualityApi.ts
frontend/src/features/quality/qualitySchemas.ts
frontend/src/components/DailyCurve.tsx
frontend/src/components/PeakSummary.tsx
frontend/src/components/ExportButton.tsx
frontend/src/api/trialClient.ts
frontend/src/api/errorCatalog.ts
frontend/src/lib/formatters.ts
frontend/src/test/ForecastPage.test.tsx
frontend/src/test/QualityPage.test.tsx
frontend/src/test/trialClient.test.ts
frontend/e2e/forecast-flow.spec.ts
frontend/e2e/quality-flow.spec.ts
frontend/vite.config.ts
.github/workflows/ci.yml

ROUND_B_MODIFY_PATH_COUNT=26
ROUND_B_CHANGED_FILE_CEILING=26
ROUND_B_FRONTEND_PATH_CEILING=25
ROUND_B_BACKEND_PATH_CEILING=0
ROUND_B_TEST_PATH_CEILING=5
ROUND_B_WORKFLOW_PATH_CEILING=1
ROUND_B_DEPENDENCY_PATH_CEILING=0

Forbidden:

backend/**
backend/alembic/**
backend/app/models/**
backend/app/core_forecast/**
backend/app/forecast_quality/**
backend/app/rolling_backtest/**
backend/app/actual_harvest_labels/**
backend/app/actual_harvest_import/**
ci-shard-manifest.yml
pyproject.toml
uv.lock
frontend/package.json
frontend/package-lock.json
frontend/playwright.config.ts
frontend/src/app/routes.tsx
frontend/src/lib/idempotency.ts
frontend/src/components/AsyncState.tsx
frontend/src/components/ErrorState.tsx
frontend/src/components/StatusBadge.tsx
frontend/src/main.tsx
frontend/index.html
docs/**
Issue #102

The package and lockfile already exist and are exact-pinned. The existing
Playwright configuration and idempotency helper are reused. The CI manifest
remains unchanged because no Python tests are added or reassigned.

## 14. Dependency decision

DEPENDENCY_CHANGE=false
LOCKFILE_CHANGE=false
NPM_INSTALL_IN_AUDIT=false
NPM_CI_REQUIRED_FOR_FUTURE_FRONTEND_CI=true
NODE_VERSION=24.15.0
NPM_VERSION=11.12.1
FRONTEND_DEPENDENCY_PINS=package.json_and_package-lock.json

These Node/npm values are the exact versions observed during this audit.
Current package pins are React 19.2.8, React DOM 19.2.8, Router 7.18.1,
Vite 8.1.5, TypeScript 6.0.3, Zod 4.4.3, Vitest 4.1.10, Testing Library
16.3.2, JSDOM 30.0.1, Playwright 1.62.0, ESLint 10.8.0 and Prettier 3.9.6.
No new dependency is necessary. A different runtime pair requires new
governance evidence.

## 15. CI and shard ownership

The existing Python/PostgreSQL workflow and ci-shard-manifest.yml remain
unchanged. Future frontend checks are additive:

| Job | Trigger | Command responsibility | Output |
| --- | --- | --- | --- |
| frontend-static | pull_request, push main | setup exact Node/npm; npm ci; lint; format check; typecheck; build | frontend/dist artifact |
| frontend-unit | pull_request, push main | Vitest unit/DOM suite, no production happy-path API mock | frontend/reports/test-results/frontend-unit.xml |
| frontend-e2e | pull_request, push main | real Chromium desktop/mobile Trial API scenarios on isolated PostgreSQL | frontend/reports/test-results/frontend-e2e.xml and failure traces |

FRONTEND_CHANGED_PATH_FILTER=false
PYTHON_PYTEST_OWNERSHIP_CHANGED=false
CI_SHARD_MANIFEST_CHANGED=false
FULL_SUITE_CANARY_REPLACED=false
FULL_SUITE_CANARY_ON_MAIN_RETAINED=true

The future E2E job may start an isolated backend/PostgreSQL 16 service and
provide a Vite proxy target. It may not use a browser API mock for happy-path
acceptance. Existing pytest owners and the main full-suite-canary remain
unchanged.

## 16. Test and acceptance commands

Future local frontend gates:

    npm ci --prefix frontend
    npm --prefix frontend run lint
    npm --prefix frontend run format:check
    npm --prefix frontend run typecheck
    npm --prefix frontend run build
    npm --prefix frontend run test:unit -- --run
    npm --prefix frontend run test:e2e

The real E2E command requires PostgreSQL 16 and a live Trial service. Existing
backend regression ownership remains:

    uv run pytest -q backend/tests/trial
    uv run pytest -q backend/tests/forecast_quality
    uv run pytest -q backend/tests/integration/test_core_forecast_persistence_postgres.py
    uv run pytest -q

These backend commands are not copied into a new frontend shard; the existing
workflow owns them. Acceptance requires strict frontend schemas, all listed
browser scenarios, unchanged Python ownership, and successful main
full-suite-canary.

## 17. Delivery, rollback and Round C stop condition

Future delivery order:

1. strict transport schemas and error catalog;
2. Trial client, idempotency and display wiring;
3. Forecast page;
4. Actual Harvest and Quality page;
5. real browser E2E and frontend CI;
6. exact-head PR CI;
7. independent review stop.

Rollback is frontend-only: revert the Round B frontend commits and the one
frontend CI workflow addition. Do not revert A1/A2, evidence, models,
algorithms, data, bindings or migrations. If frontend CI alone is defective,
revert only its added workflow block.

Round C requires separate explicit authorization after Round B review/merge,
exact-head CI, post-merge main full-suite-canary, and real desktop/mobile E2E
success. Round C is the later scope for admin, dashboards, operational
recommendations, LLM/chat, broader Quality exploration and release packaging.
No Round C action is authorized here.

## 18. Governance stop block

Stop if any Round B implementation needs a backend, migration, model,
algorithm, calculator, evidence, internal API, database ID, browser-side
calculation, synthetic happy-path E2E, unknown public shape, passthrough
schema, dependency/lockfile change, ci-shard-manifest change, existing
pytest ownership change, Ready, Merge, release, Issue #102 mutation, or
Round C action.

ROUND_B_BLOCKER_COUNT=0
ROUND_B_READINESS=READY
ROUND_B_IMPLEMENTATION_AUTHORIZED=false
ROUND_B_AUTHORIZATION_ACCEPTED=false
MANDATORY_STOP=true

This document freezes a future frontend-only boundary. It does not authorize
implementation, Ready, Merge, Round C, or V0.2 release.
