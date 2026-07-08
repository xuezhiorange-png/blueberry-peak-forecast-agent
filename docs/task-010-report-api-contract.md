# TASK-010 Report and API Contract — Residual Model

Status: design-only contract / no implementation mutation  
Base commit: `b66388df8a87e3f4449027553ba91263094ad6a6`  
Branch: `codex/task-010-report-api-contract-design`

## 1. Purpose

TASK-010 freezes the residual-model report and API boundary after TASK-009A design ratification and TASK-011-INFRA closeout.

Current `main` already contains substantial residual-model code and tests. This document does not create a residual model from zero. It defines the report/API contract that future slices must obey before any UI, agent workflow, or external API expansion.

This PR is design-only. It does not authorize production code changes, test changes, Alembic changes, frontend work, agent workflow work, or issue closeout.

## 2. Current repository facts

Current `main` contains residual-model surfaces including:

- `backend/app/residual_model/model.py`
- `backend/app/residual_model/dataset.py`
- `backend/app/residual_model/manifest.py`
- `backend/app/residual_model/encoding.py`
- `backend/app/residual_model/visibility.py`
- `backend/app/residual_model/projection.py`
- `backend/app/residual_model/cli_support.py`
- `backend/app/residual_model/application.py`
- `backend/app/residual_model/config.py`
- `backend/app/residual_model/artifact.py`
- `backend/app/residual_model/service.py`
- `backend/app/residual_model/feature_registry.py`
- `backend/app/residual_model/prediction_features.py`
- `backend/app/residual_model/schemas.py`
- `backend/app/residual_model/reporting.py`
- `backend/app/residual_model/training_manifest.py`
- `backend/app/residual_model/persistence.py`
- `backend/app/models/residual_model.py`
- `backend/app/repositories/residual_model.py`
- `backend/alembic/versions/0011_residual_model.py`
- `backend/tests/residual_model/**`
- `backend/tests/integration/test_residual_model_*.py`

The repository already has deterministic report rendering helpers in `backend/app/residual_model/reporting.py`.

## 3. Existing report schema versions

The current report renderer defines four report schema version constants:

```text
TRAINING_JSON_REPORT_SCHEMA_VERSION = task10-residual-training-report-v1
TRAINING_CSV_REPORT_SCHEMA_VERSION = task10-residual-training-csv-report-v1
PREDICTION_JSON_REPORT_SCHEMA_VERSION = task10-residual-prediction-report-v1
PREDICTION_CSV_REPORT_SCHEMA_VERSION = task10-residual-prediction-csv-report-v1
```

These schema version strings are part of the frozen TASK-010 report contract. Future changes must create new version strings instead of mutating the semantic meaning of existing versions.

## 4. Training JSON report contract

The training JSON report is produced by `render_residual_training_json_report`.

It must emit canonical JSON bytes with a trailing newline and include:

- `report_schema_version`
- `run.run_id`
- `run.execution_status`
- `run.eligibility_status`
- `run.training_signature`
- `run.config_hash`
- `run.manifest_hash`
- `run.created_at`
- `manifest_snapshot`
- `output`
- artifact metadata summary for each trained quantile artifact

The JSON report must not embed raw artifact binary payloads.

## 5. Training CSV/ZIP report contract

The training CSV report is produced by `render_residual_training_csv_report` and is a deterministic ZIP archive.

The ZIP must contain `manifest.json` plus deterministic entries derived from available data. Expected logical entries include:

- `manifest.json`
- `manifest_rows.csv` when manifest rows are present
- `run.csv`
- `artifacts.csv`
- `metrics.json`
- `warnings.csv`
- `blockers.csv`

The ZIP contract must remain deterministic:

- stable entry order;
- stable CSV column order;
- stable newline behavior;
- stable ZIP timestamp;
- stable ZIP permissions / create_system metadata;
- no compression variability when deterministic storage is required.

## 6. Prediction JSON report contract

The prediction JSON report is produced by `render_residual_prediction_json_report`.

It must emit canonical JSON bytes with a trailing newline and include:

- `report_schema_version`
- `run.run_id`
- `run.execution_status`
- `run.mode`
- `run.prediction_hash`
- `run.config_hash`
- `run.created_at`
- `output`

The prediction JSON report must preserve the versioned prediction output schema and must not silently drop warnings or blockers.

## 7. Prediction CSV/ZIP report contract

The prediction CSV report is produced by `render_residual_prediction_csv_report` and is a deterministic ZIP archive.

The ZIP must contain:

- `manifest.json`
- `run.csv`
- `prediction_rows.csv`
- `warnings.csv`
- `blockers.csv`

`prediction_rows.csv` must use the field order defined by `ResidualPredictionRow.model_fields.keys()` unless a future schema version explicitly freezes a different field order.

## 8. Scalar serialization contract

Report scalar rendering must preserve deterministic text conversion:

- `None` becomes an empty string in CSV context;
- `Decimal` uses canonical decimal string rendering;
- mappings and sequences use canonical JSON;
- datetime-like values use ISO-8601 text;
- enums render by their value.

Future report extensions must preserve this scalar contract or introduce a new schema version.

## 9. API boundary

Current TASK-010 does not authorize public HTTP API endpoints.

For this design contract, report rendering remains a backend service / CLI / persistence-facing capability unless a later explicit implementation slice freezes API routes.

A future API slice must separately define:

- route paths;
- request schemas;
- response schemas;
- authorization / exposure boundary;
- whether reports are streamed, downloaded, or stored as artifacts;
- pagination and filtering behavior;
- error codes for missing run, unavailable report type, invalid format, and unauthorized access.

No frontend dependency is authorized by this design PR.

## 10. Security and data-governance boundary

TASK-010 report/API work must not leak training data or binary artifacts beyond approved report fields.

The following are not authorized unless a later design amendment explicitly allows them:

- raw training dataset export;
- raw model binary export through an API;
- unversioned report payloads;
- report fields that expose hidden authority data not already present in approved manifest/output structures;
- arbitrary file-path access;
- user-supplied ZIP entry names;
- wall-clock nondeterminism beyond persisted `created_at` values.

## 11. Determinism requirements

Report generation must be deterministic for the same persisted inputs:

- canonical JSON serialization;
- deterministic CSV headers and row ordering;
- deterministic ZIP entry ordering;
- deterministic ZIP metadata;
- stable schema version strings;
- stable warning/blocker rendering;
- no runtime randomness;
- no locale-dependent number/date formatting.

## 12. Acceptance gates for a future implementation slice

A future implementation slice may proceed only after this design contract is merged.

Minimum acceptance gates for any implementation slice:

- report schema-version tests;
- deterministic JSON byte snapshot tests;
- deterministic ZIP file list and metadata tests;
- CSV header ordering tests;
- warnings/blockers preservation tests;
- no frontend changes unless a later frontend task is explicitly authorized;
- no TASK-009A / TASK-011 / TASK-012 mutation;
- no Alembic changes unless the implementation slice explicitly requires new persisted report metadata;
- PR CI green;
- post-merge `main` CI green before closeout.

## 13. Allowed files for this design PR

This design PR is restricted to:

- `docs/task-010-report-api-contract.md`

## 14. Forbidden files for this design PR

This design PR must not touch:

- `backend/app/residual_model/**`
- `backend/tests/**`
- `backend/alembic/versions/**`
- `frontend/**`
- `.github/workflows/**`
- dependency files
- TASK-009A implementation files
- TASK-011 infrastructure files
- TASK-012 agent/replay files

## 15. Governance

This PR is design-only and may be created as Draft.

Ready transition requires separate Charles authorization.
Merge requires separate Charles authorization.
Post-merge `main` CI must be green before any cleanup or downstream implementation authorization.

Because direct Issue creation was blocked by tool safety checks, this PR carries the TASK-010 task definition and design freeze in repository history. If a GitHub Issue is later created manually, it should reference this document and PR instead of redefining the contract.
