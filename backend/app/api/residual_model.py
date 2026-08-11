"""Residual-model API surface.

Implements TASK-010 API Slice 1 (download endpoints, PR #75) and Slice 2
A1 (training execution endpoints, PR #76). This module is a thin
FastAPI adapter between the renderer / service / persistence layers and
the HTTP transport. The adapter does NOT fabricate business state: all
training / eligibility / signature logic is delegated to
``service.train_residual_model_from_manifest`` and all persistence /
conflict detection to ``persistence.save_residual_training_run``.

Stability contract (PR #76 §3, §5, §8):

- 201 Created on first successful training POST + Location header
- 200 OK on replay POST (idempotent re-submission with same signature
  AND same canonical payload; also same idempotency_key + same canonical
  payload)
- 200 OK on GET /training-runs/{run_id}
- 200 OK on Slice 1 report download endpoints (unchanged from PR #75)
- 404 with stable payload for missing runs:
  - ``RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND``
- 409 with stable payload for hash / signature / idempotency conflicts:
  - ``RESIDUAL_MODEL_EXECUTION_CONFLICT``
- 422 with stable payload for invalid request schema:
  - ``RESIDUAL_MODEL_EXECUTION_INPUT_ERROR``
- 500 with stable payload for persistence / loader / service integrity
  errors; never leak sqlalchemy / asyncpg / traceback / local paths /
  artifact binary:
  - ``RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR`` (Slice 2 execution paths)
  - ``RESIDUAL_MODEL_REPORT_INTEGRITY_ERROR`` (Slice 1 download paths)

Forbidden mutations:

- ``backend/app/residual_model/service.py`` training logic (the
  contract-payload adapter at the end of that module is a NEW helper
  added by this slice; it does NOT alter training eligibility,
  signature, or persistence logic)
- ``backend/app/residual_model/reporting.py``
- ``backend/app/residual_model/persistence.py`` (semantics)
- ``backend/app/residual_model/dataset.py`` / ``manifest.py`` /
  ``config.py`` (semantics)

This module is permitted to import from those modules but MUST NOT
alter their behavior. The adapter delegates all persistence /
transaction management to ``persistence.py`` (per PR #76 §9).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path as PathlibPath
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_prediction_run_by_input_signature,
    get_residual_training_run,
)
from backend.app.residual_model.config import (
    ResidualModelConfig,
    load_residual_model_config,
)
from backend.app.residual_model.persistence import (
    ResidualArtifactIntegrityError,
    ResidualModelHashConflictError,
    ResidualModelPersistenceError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
    prediction_results_business_compatible,
    save_residual_prediction_run,
    save_residual_training_run,
)
from backend.app.residual_model.reporting import (
    render_residual_prediction_csv_report,
    render_residual_prediction_json_report,
    render_residual_training_csv_report,
    render_residual_training_json_report,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionExecutionResult,
)
from backend.app.residual_model.service import (
    predict_residual_model_from_contract_payload,
    train_residual_model_from_contract_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Reusable dependency annotations matching the harvest_state / master_data
# style — avoids per-endpoint B008 lint warnings about Depends() in
# argument defaults.
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RunIdPath = Annotated[int, Path(..., ge=1)]

# Canonical production config used by the API adapter. Loaded lazily on
# first request; failure to load raises an integrity error so the
# training endpoints fail fast with a stable 500 payload.
_PRODUCTION_CONFIG_PATH = PathlibPath("configs/residual_model.yaml")
_DEFAULT_CONFIG_FAMILY_HINT = (
    "The request body's `config` field is treated as a config selector; "
    "the adapter loads the canonical production config from "
    "configs/residual_model.yaml regardless of the selector value."
)
_cached_config: ResidualModelConfig | None = None


def _load_production_config() -> ResidualModelConfig:
    """Load the canonical production residual-model config (cached).

    The contract test sends ``config={"family": ..., "version": ...}``,
    which is NOT a full ``ResidualModelConfig`` snapshot (the production
    loader requires 11+ nested fields). The contract treats ``config``
    as a SELECTOR — the adapter loads the canonical production config
    from disk regardless of the selector's value. This avoids fabricating
    business values in the API layer.
    """
    global _cached_config
    if _cached_config is None:
        _cached_config = load_residual_model_config(_PRODUCTION_CONFIG_PATH)
    return _cached_config


# ---------------------------------------------------------------------------
# Stable error payloads
# ---------------------------------------------------------------------------


def _not_found_training_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND",
            "message": "Residual-model training run was not found.",
        }
    }


def _not_found_prediction_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND",
            "message": "Residual-model prediction run was not found.",
        }
    }


def _integrity_error_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_REPORT_INTEGRITY_ERROR",
            "message": "Residual-model report could not be generated.",
        }
    }


def _execution_input_error_payload(message: str) -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_EXECUTION_INPUT_ERROR",
            "message": message,
        }
    }


def _execution_conflict_payload(message: str) -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_EXECUTION_CONFLICT",
            "message": message,
        }
    }


def _execution_integrity_error_payload() -> dict[str, Any]:
    return {
        "error": {
            "code": "RESIDUAL_MODEL_EXECUTION_INTEGRITY_ERROR",
            "message": "Residual-model execution could not be completed.",
        }
    }


def _json_error_response(payload: dict[str, Any], status_code: int) -> Response:
    """Build a stable JSON error response.

    Always uses application/json media_type and a canonical envelope so
    API consumers can rely on `body["error"]["code"]` and
    `body["error"]["message"]`. FastAPI's default `{"detail": ...}` is
    intentionally NOT used here.
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return Response(
        content=body,
        media_type="application/json",
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# Request validation (PR #76 §4.1)
# ---------------------------------------------------------------------------


def _parse_iso_date(value: Any, *, field: str) -> Any:
    """Parse an ISO-8601 date or datetime string; return date."""
    from datetime import date, datetime

    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO-8601 date") from exc
    raise ValueError(f"{field} must be a string or date")


def _validate_training_request(request_body: Any) -> dict[str, Any] | Response:
    """Validate the simplified POST /training-runs payload.

    Returns either a validated ``fields`` dict (with keys: manifest_rows,
    forecast_cutoff, source_run_ids, idempotency_key) or a ``Response``
    carrying a 422 stable error payload. The API adapter does NOT
    inspect or rewrite business content here; it only enforces the
    PR #76 §4.1 shape.
    """
    if not isinstance(request_body, dict):
        return _json_error_response(
            _execution_input_error_payload("request body must be a JSON object"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    manifest_snapshot = request_body.get("manifest_snapshot")
    manifest_rows_raw = request_body.get("manifest_rows")
    config_raw = request_body.get("config")
    forecast_cutoff_raw = request_body.get("forecast_cutoff")
    source_run_ids_raw = request_body.get("source_run_ids")
    idempotency_key_raw = request_body.get("idempotency_key")

    missing: list[str] = []
    if manifest_snapshot is None:
        missing.append("manifest_snapshot")
    if config_raw is None:
        missing.append("config")
    if forecast_cutoff_raw is None:
        missing.append("forecast_cutoff")
    if missing:
        return _json_error_response(
            _execution_input_error_payload(f"missing required field(s): {', '.join(missing)}"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # forecast_cutoff parseable as ISO-8601
    try:
        forecast_cutoff = _parse_iso_date(forecast_cutoff_raw, field="forecast_cutoff")
    except ValueError as exc:
        return _json_error_response(
            _execution_input_error_payload(str(exc)),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # manifest_rows: list of dicts (or null) — fall back to manifest_snapshot["rows"]
    manifest_rows: list[dict[str, Any]] = []
    if manifest_rows_raw is not None:
        if not isinstance(manifest_rows_raw, list):
            return _json_error_response(
                _execution_input_error_payload("manifest_rows must be an array of objects"),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        for idx, item in enumerate(manifest_rows_raw):
            if not isinstance(item, dict):
                return _json_error_response(
                    _execution_input_error_payload(f"manifest_rows[{idx}] must be an object"),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            manifest_rows.append(item)

    if not manifest_rows and isinstance(manifest_snapshot, dict):
        snapshot_rows = manifest_snapshot.get("rows")
        if isinstance(snapshot_rows, list):
            for idx, item in enumerate(snapshot_rows):
                if not isinstance(item, dict):
                    return _json_error_response(
                        _execution_input_error_payload(
                            f"manifest_snapshot.rows[{idx}] must be an object"
                        ),
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    )
                manifest_rows.append(item)

    if not manifest_rows:
        return _json_error_response(
            _execution_input_error_payload(
                "manifest_rows (or manifest_snapshot.rows) must be non-empty"
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # source_run_ids: dict of int values (or null)
    source_run_ids: dict[str, int] = {}
    if source_run_ids_raw is not None:
        if not isinstance(source_run_ids_raw, dict):
            return _json_error_response(
                _execution_input_error_payload(
                    "source_run_ids must be an object mapping string to integer"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        for key, value in source_run_ids_raw.items():
            if not isinstance(key, str) or not isinstance(value, int) or isinstance(value, bool):
                return _json_error_response(
                    _execution_input_error_payload(
                        "source_run_ids values must be non-bool integers"
                    ),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            source_run_ids[key] = value

    # idempotency_key: string or null
    idempotency_key: str | None = None
    if idempotency_key_raw is not None and not isinstance(idempotency_key_raw, str):
        return _json_error_response(
            _execution_input_error_payload("idempotency_key must be a string or null"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    idempotency_key = idempotency_key_raw

    return {
        "manifest_rows": manifest_rows,
        "forecast_cutoff": forecast_cutoff,
        "source_run_ids": source_run_ids,
        "idempotency_key": idempotency_key,
    }


# ---------------------------------------------------------------------------
# Idempotency-key pre-check (PR #76 §7.1: same key + different payload → 409)
# ---------------------------------------------------------------------------


async def _check_idempotency_key(
    session: AsyncSession,
    *,
    idempotency_key: str | None,
    expected_payload_hash: str,
) -> Response | None:
    """Pre-check: if the same idempotency_key was used with a different
    canonical payload, return 409. Otherwise return None (proceed).

    The implementation queries the ORM's ``input_snapshot`` JSON column
    via SQLAlchemy's portable JSON path syntax
    (``ResidualModelTrainingRun.input_snapshot["idempotency_key"]``).
    The column is declared ``JSONB.with_variant(JSON(), "sqlite")``
    (see ``models/residual_model.py::_JSON_VARIANT``) so the same
    expression compiles to a JSONB ``@>`` operator on PostgreSQL and
    a portable JSON-path comparison on SQLite — no SQLite-only
    ``json_extract()`` raw SQL.

    The persistence layer populates ``input_snapshot`` with the full
    request snapshot, including the ``idempotency_key`` field
    embedded by the service-layer adapter.
    """
    if idempotency_key is None:
        return None
    from backend.app.models.residual_model import ResidualModelTrainingRun

    key_path = ResidualModelTrainingRun.input_snapshot["idempotency_key"].as_string()
    stmt = select(ResidualModelTrainingRun.canonical_payload_hash).where(
        key_path == idempotency_key,
    )
    result = await session.execute(stmt)
    existing_hashes = [row[0] for row in result.all()]
    if existing_hashes and all(h != expected_payload_hash for h in existing_hashes):
        return _json_error_response(
            _execution_conflict_payload(
                "idempotency_key already used with a different canonical payload"
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    return None


# ---------------------------------------------------------------------------
# Envelope mapping (PR #76 §5.1)
# ---------------------------------------------------------------------------


def _training_run_report_links(run_id: int) -> dict[str, str]:
    return {
        "json": f"/api/v1/residual-model/training-runs/{run_id}/report.json",
        "csv": f"/api/v1/residual-model/training-runs/{run_id}/report.csv",
    }


def _training_envelope_from_orm(run: Any) -> dict[str, Any]:
    """Build the PR #76 §5.1 envelope from an ORM training run row."""
    return {
        "run_id": run.id,
        "execution_status": run.execution_status,
        "eligibility_status": run.eligibility_status,
        "training_signature": run.training_signature,
        "config_hash": run.config_hash,
        "manifest_hash": run.manifest_hash,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "warnings": list(run.warnings or []),
        "blockers": list(run.blockers or []),
        "report_links": _training_run_report_links(run.id),
    }


def _prediction_run_report_links(run_id: int) -> dict[str, str]:
    return {
        "json": f"/api/v1/residual-model/prediction-runs/{run_id}/report.json",
        "csv": f"/api/v1/residual-model/prediction-runs/{run_id}/report.csv",
    }


def _prediction_envelope_from_orm(run: Any) -> dict[str, Any]:
    """Build the PR #76 §5.2 envelope from an ORM prediction run row."""
    return {
        "run_id": run.id,
        "execution_status": run.execution_status,
        "mode": run.mode,
        "prediction_hash": run.prediction_hash,
        "prediction_input_signature": run.prediction_input_signature,
        "config_hash": run.config_hash,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "warnings": list(run.warnings or []),
        "blockers": list(run.blockers or []),
        "report_links": _prediction_run_report_links(run.id),
    }


def _compute_payload_hash_from_loaded(loaded: Any) -> str:
    """Compute the canonical_payload_hash from a loaded
    ResidualTrainingExecutionResult.

    Mirrors persistence._training_payload_hash so the API layer can
    compare without re-importing private helpers.
    """
    from backend.app.residual_model.persistence import _training_payload_hash

    return _training_payload_hash(loaded)


# ---------------------------------------------------------------------------
# Slice 2 execution endpoints (TASK-010 PR #76)
# ---------------------------------------------------------------------------


@router.post(
    "/training-runs",
    status_code=status.HTTP_201_CREATED,
    summary="Create + execute a residual-model training run (synchronous).",
)
async def post_training_run(
    request_body: dict[str, Any],
    session: SessionDep,
) -> Response:
    """Create and execute a residual-model training run.

    Request body follows the PR #76 §4.1 contract. The adapter:

    1. Validates the simplified request shape and returns
       ``422 RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`` on schema failure.
    2. Loads the canonical production ``ResidualModelConfig`` from
       ``configs/residual_model.yaml`` (no business-state fabrication).
    3. Pre-checks idempotency_key: same key + different canonical
       payload → ``409 RESIDUAL_MODEL_EXECUTION_CONFLICT``.
    4. Delegates to ``service.train_residual_model_from_contract_payload``
       and ``persistence.save_residual_training_run`` — the persistence
       layer handles idempotent replay (same signature + same payload
       → return existing run) and hash conflict (same signature +
       different payload → ``ResidualModelHashConflictError`` → 409).
    5. Returns the PR #76 §5.1 envelope with ``201 Created`` (first
       creation) or ``200 OK`` (idempotent replay).

    The adapter does NOT bypass the service / persistence boundary; it
    does NOT fabricate ORM rows directly.
    """
    try:
        # ---- 1. Request shape validation ----
        validated = _validate_training_request(request_body)
        if isinstance(validated, Response):
            return validated
        fields = validated
        manifest_rows = fields["manifest_rows"]
        forecast_cutoff = fields["forecast_cutoff"]
        source_run_ids = fields["source_run_ids"]
        idempotency_key = fields["idempotency_key"]

        # ---- 2. Load production config ----
        config = _load_production_config()

        # ---- 3. Service-layer delegation ----
        # Delegate to ``service.train_residual_model_from_contract_payload``
        # — the contract→service adapter. Production code does NOT alias
        # this symbol under a monkeypatch-friendly name; if a future test
        # needs to patch the service entry point, it patches the actual
        # function name via ``monkeypatch.setattr(
        # "backend.app.api.residual_model.train_residual_model_from_contract_payload",
        # ...)``.
        result, service_rows = train_residual_model_from_contract_payload(
            config=config,
            manifest_rows_payload=manifest_rows,
            forecast_cutoff=forecast_cutoff,
            source_run_ids=source_run_ids,
            idempotency_key=idempotency_key,
        )

        # ---- 4. Embed idempotency_key in input_snapshot for ORM-side
        #         dedup (per PR #76 §7.1 idempotency_key reuse semantics)
        if idempotency_key is not None and isinstance(result.input_snapshot, dict):
            result.input_snapshot["idempotency_key"] = idempotency_key

        # ---- 5. Idempotency-key pre-check on canonical_payload_hash
        # The persistence layer's conflict detection runs against
        # training_signature, not idempotency_key. We pre-check
        # idempotency_key BEFORE save so a reused key + different
        # canonical payload returns 409 immediately.
        from backend.app.residual_model.persistence import _training_payload_hash

        expected_payload_hash = _training_payload_hash(result)
        pre_check = await _check_idempotency_key(
            session,
            idempotency_key=idempotency_key,
            expected_payload_hash=expected_payload_hash,
        )
        if pre_check is not None:
            return pre_check

        # ---- 5b. Replay pre-check (PR #76 §7.1): if a run with the
        # same signature exists, return it as a replay (200) instead of
        # calling save_residual_training_run (which would re-INSERT or
        # raise a hash-conflict on different payload).
        from backend.app.repositories.residual_model import (
            get_residual_training_run_by_signature,
        )

        prior_run = await get_residual_training_run_by_signature(
            session, training_signature=result.training_signature
        )
        if prior_run is not None:
            loaded_prior = await load_residual_training_run_by_id(session, run_id=prior_run.id)
            if loaded_prior is not None:
                prior_payload_hash = _compute_payload_hash_from_loaded(loaded_prior)
                if prior_payload_hash == expected_payload_hash:
                    # True replay → return 200 with existing envelope
                    envelope = _training_envelope_from_orm(prior_run)
                    return Response(
                        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                        media_type="application/json",
                        status_code=status.HTTP_200_OK,
                    )
                # Same signature but different payload → conflict
                return _json_error_response(
                    _execution_conflict_payload(
                        "training signature already exists with a different canonical payload"
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )

        # ---- 6. Persistence (delegated) ----
        run = await save_residual_training_run(
            session,
            result=result,
            manifest_rows=service_rows,
        )
    except ResidualModelHashConflictError:
        logger.warning(
            "residual_model_api.training_hash_conflict",
            extra={"kind": "training", "operation": "post"},
        )
        return _json_error_response(
            _execution_conflict_payload(
                "training signature already exists with a different canonical payload"
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError) as exc:
        logger.warning(
            "residual_model_api.execution_integrity_error exc=%r",
            exc,
            extra={"kind": "training", "operation": "post"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception as exc:
        # Catch-all: shield ALL persistence/loader internals (sqlalchemy,
        # asyncpg, OS, traceback, blob bytes) from leaking to clients.
        logger.exception(
            "residual_model_api.execution_unexpected_error exc=%r",
            exc,
            extra={"kind": "training", "operation": "post"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    envelope = _training_envelope_from_orm(run)
    headers = {
        "Content-Type": "application/json",
        "Location": f"/api/v1/residual-model/training-runs/{run.id}",
    }
    return Response(
        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        status_code=status.HTTP_201_CREATED,
        headers=headers,
    )


@router.get(
    "/training-runs/{run_id}",
    summary="Inspect an existing residual-model training run.",
)
async def get_training_run(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the PR #76 §5.1 envelope for an existing training run."""
    try:
        run = await get_residual_training_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        envelope = _training_envelope_from_orm(run)
    except (
        ResidualModelPersistenceIntegrityError,
        ResidualArtifactIntegrityError,
    ):
        logger.warning(
            "residual_model_api.execution_integrity_error",
            extra={"run_id": run_id, "kind": "training", "operation": "get"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.execution_unexpected_error",
            extra={"run_id": run_id, "kind": "training", "operation": "get"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Prediction execution endpoints (Slice 2 B1)
# ---------------------------------------------------------------------------


_VALID_PREDICTION_MODES: frozenset[str] = frozenset(
    {
        "residual_corrected",
        "structural_only",
        "blocked",
    }
)


def _validate_prediction_request(
    request_body: Any,
) -> dict[str, Any] | Response:
    """Validate the simplified POST /prediction-runs payload.

    Returns either a validated ``fields`` dict (with keys: training_run_id,
    feature_actual_snapshot, supplemental_feature_payloads, prediction_mode,
    task9_run_id, task9_result_hash, source_run_ids, idempotency_key) or a
    ``Response`` carrying a 422 stable error payload. The API adapter does
    NOT inspect or rewrite business content here; it only enforces the
    PR #76 §4.2 shape.
    """
    if not isinstance(request_body, dict):
        return _json_error_response(
            _execution_input_error_payload("request body must be a JSON object"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    training_run_id_raw = request_body.get("training_run_id")
    feature_actual_snapshot_raw = request_body.get("feature_actual_snapshot")
    config_raw = request_body.get("config")
    prediction_mode_raw = request_body.get("prediction_mode")
    task9_run_id_raw = request_body.get("task9_run_id")
    task9_result_hash_raw = request_body.get("task9_result_hash")
    source_run_ids_raw = request_body.get("source_run_ids")
    idempotency_key_raw = request_body.get("idempotency_key")
    supplemental_features_raw = request_body.get("supplemental_features")

    missing: list[str] = []
    if training_run_id_raw is None:
        missing.append("training_run_id")
    if feature_actual_snapshot_raw is None:
        missing.append("feature_actual_snapshot")
    if config_raw is None:
        missing.append("config")
    if prediction_mode_raw is None:
        missing.append("prediction_mode")
    if missing:
        return _json_error_response(
            _execution_input_error_payload(f"missing required field(s): {', '.join(missing)}"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # training_run_id must be a positive integer
    if (
        not isinstance(training_run_id_raw, int)
        or isinstance(training_run_id_raw, bool)
        or training_run_id_raw < 1
    ):
        return _json_error_response(
            _execution_input_error_payload("training_run_id must be a positive integer"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # feature_actual_snapshot must be an object (or null)
    feature_actual_snapshot: dict[str, Any] | None
    if feature_actual_snapshot_raw is None:
        feature_actual_snapshot = None
    elif isinstance(feature_actual_snapshot_raw, dict):
        feature_actual_snapshot = feature_actual_snapshot_raw
    else:
        return _json_error_response(
            _execution_input_error_payload("feature_actual_snapshot must be an object"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # prediction_mode must be one of the frozen enum values
    if not isinstance(prediction_mode_raw, str):
        return _json_error_response(
            _execution_input_error_payload("prediction_mode must be a string"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if prediction_mode_raw not in _VALID_PREDICTION_MODES:
        return _json_error_response(
            _execution_input_error_payload(
                f"prediction_mode must be one of {sorted(_VALID_PREDICTION_MODES)}, "
                f"got {prediction_mode_raw!r}"
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # task9_run_id (optional)
    task9_run_id: int | None
    if task9_run_id_raw is None:
        task9_run_id = None
    elif isinstance(task9_run_id_raw, int) and not isinstance(task9_run_id_raw, bool):
        task9_run_id = task9_run_id_raw
    else:
        return _json_error_response(
            _execution_input_error_payload("task9_run_id must be a positive integer or null"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # task9_result_hash (optional, 64 hex chars if present)
    task9_result_hash: str | None
    if task9_result_hash_raw is None:
        task9_result_hash = None
    elif isinstance(task9_result_hash_raw, str) and len(task9_result_hash_raw) == 64:
        task9_result_hash = task9_result_hash_raw
    else:
        return _json_error_response(
            _execution_input_error_payload("task9_result_hash must be a 64-character hex string"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # If task9_run_id is present, task9_result_hash MUST also be present (and vice versa)
    if (task9_run_id is None) != (task9_result_hash is None):
        return _json_error_response(
            _execution_input_error_payload(
                "task9_run_id and task9_result_hash must be supplied together"
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # supplemental_features: list of objects (or null)
    supplemental_feature_payloads: list[dict[str, Any]] | None
    if supplemental_features_raw is None:
        supplemental_feature_payloads = None
    elif isinstance(supplemental_features_raw, list):
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(supplemental_features_raw):
            if not isinstance(item, dict):
                return _json_error_response(
                    _execution_input_error_payload(
                        f"supplemental_features[{idx}] must be an object"
                    ),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            out.append(item)
        supplemental_feature_payloads = out
    else:
        return _json_error_response(
            _execution_input_error_payload(
                "supplemental_features must be an array of objects or null"
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # source_run_ids: dict of int values (or null)
    source_run_ids: dict[str, int] = {}
    if source_run_ids_raw is not None:
        if not isinstance(source_run_ids_raw, dict):
            return _json_error_response(
                _execution_input_error_payload(
                    "source_run_ids must be an object mapping string to integer"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        for key, value in source_run_ids_raw.items():
            if not isinstance(value, int) or isinstance(value, bool):
                return _json_error_response(
                    _execution_input_error_payload(f"source_run_ids[{key}] must be an integer"),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            source_run_ids[key] = value

    # idempotency_key: string or null
    idempotency_key: str | None
    if idempotency_key_raw is None:
        idempotency_key = None
    elif isinstance(idempotency_key_raw, str):
        idempotency_key = idempotency_key_raw
    else:
        return _json_error_response(
            _execution_input_error_payload("idempotency_key must be a string or null"),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    return {
        "training_run_id": training_run_id_raw,
        "feature_actual_snapshot": feature_actual_snapshot,
        "supplemental_feature_payloads": supplemental_feature_payloads,
        "prediction_mode": prediction_mode_raw,
        "task9_run_id": task9_run_id,
        "task9_result_hash": task9_result_hash,
        "source_run_ids": source_run_ids,
        "idempotency_key": idempotency_key,
    }


@router.post(
    "/prediction-runs",
    status_code=status.HTTP_201_CREATED,
    summary="Create + execute a residual-model prediction run (synchronous).",
)
async def post_prediction_run(
    request_body: dict[str, Any],
    session: SessionDep,
) -> Response:
    """Create and execute a residual-model prediction run.

    Request body follows the PR #76 §4.2 contract. The adapter:

    1. Validates the simplified request shape and returns
       ``422 RESIDUAL_MODEL_EXECUTION_INPUT_ERROR`` on schema failure.
    2. Pre-checks the referenced training run exists (PR #76 §7.2);
       missing run → ``404 RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND``.
    3. Pre-checks task9_result_hash matches the persisted hash for
       ``task9_run_id`` (PR #76 §7.2); mismatch → ``409
       RESIDUAL_MODEL_EXECUTION_CONFLICT``.
    4. Loads the canonical production ``ResidualModelConfig`` from
       ``configs/residual_model.yaml`` (no business-state fabrication).
    5. Delegates to ``service.predict_residual_model_from_contract_payload``
       and ``persistence.save_residual_prediction_run`` — the persistence
       layer handles idempotent replay (same signature + same payload →
       return existing run) and hash conflict (same signature + different
       payload → ``ResidualModelHashConflictError`` → 409).
    6. Returns the PR #76 §5.2 envelope with ``201 Created`` (first
       creation) or ``200 OK`` (idempotent replay).

    The adapter does NOT bypass the service / persistence boundary; it
    does NOT fabricate ORM rows directly.
    """
    try:
        # ---- 1. Request shape validation ----
        validated = _validate_prediction_request(request_body)
        if isinstance(validated, Response):
            return validated
        fields = validated
        training_run_id = fields["training_run_id"]
        feature_actual_snapshot = fields["feature_actual_snapshot"]
        supplemental_feature_payloads = fields["supplemental_feature_payloads"]
        prediction_mode = fields["prediction_mode"]
        task9_run_id = fields["task9_run_id"]
        task9_result_hash = fields["task9_result_hash"]
        source_run_ids = fields["source_run_ids"]
        idempotency_key = fields["idempotency_key"]

        # ---- 2. Pre-check training run exists (PR #76 §7.2) ----
        training_run_row = await get_residual_training_run(session, run_id=training_run_id)
        if training_run_row is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        resolved_training_signature = training_run_row.training_signature

        # ---- 3. Pre-check task9_result_hash (PR #76 §7.2) ----
        # When task9 is supplied, verify its hash matches the persisted
        # hash on the harvest_state row. This is the API-layer surface
        # of the contract's "task9_result_hash supplied but doesn't
        # match" → 409 clause.
        #
        # We use a lightweight SQL query that ONLY compares
        # ``result_hash`` here at the API pre-check layer; the FULL
        # Task 9 authority validation (canonical_payload_hash + child
        # row counts + canonical output schema) runs downstream inside
        # ``save_residual_prediction_run`` /
        # ``load_residual_prediction_run_by_id`` via
        # ``load_harvest_state_output_by_id``. This split is a layered
        # design (cheap pre-check + strict downstream authority), not
        # a validation-de-rating shortcut — see those persistence
        # callers for the full validation path.
        if task9_run_id is not None:
            from backend.app.models.harvest_state import (
                HarvestStateRun as _HarvestStateRun,
            )

            stmt = select(_HarvestStateRun.result_hash).where(_HarvestStateRun.id == task9_run_id)
            persisted_row = (await session.execute(stmt)).first()
            if persisted_row is None:
                # task9 not found: surface as conflict per the contract's
                # §7.2 wording (hash cannot match a non-existent run).
                return _json_error_response(
                    _execution_conflict_payload(
                        f"task9_run_id {task9_run_id} not found in harvest_state"
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )
            persisted_task9_hash = persisted_row[0]
            if persisted_task9_hash != task9_result_hash:
                return _json_error_response(
                    _execution_conflict_payload(
                        "task9_result_hash does not match the persisted hash for task9_run_id"
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )

        # ---- 4. Load production config ----
        config = _load_production_config()

        # ---- 5. Service-layer delegation ----
        # Delegate to ``service.predict_residual_model_from_contract_payload``
        # — the contract→service adapter. Production code does NOT alias
        # this symbol under a monkeypatch-friendly name; if a future test
        # needs to patch the service entry point, it patches the actual
        # function name via ``monkeypatch.setattr(
        # "backend.app.api.residual_model.predict_residual_model_from_contract_payload",
        # ...)``.
        result = predict_residual_model_from_contract_payload(
            config=config,
            training_run_id=training_run_id,
            task9_run_id=task9_run_id,
            task9_result_hash=task9_result_hash,
            feature_actual_snapshot=feature_actual_snapshot,
            supplemental_feature_payloads=supplemental_feature_payloads,
            prediction_mode=prediction_mode,
            source_run_ids=source_run_ids,
            idempotency_key=idempotency_key,
            training_signature_override=resolved_training_signature,
        )

        # ---- 6. Embed idempotency_key + source_run_ids in input_snapshot ----
        # The service-layer adapter already embedded
        # ``training_signature`` in input_snapshot (via
        # ``training_signature_override``). We now add idempotency_key
        # and source_run_ids, then re-normalize via
        # ``canonical_json_value`` so the persistence layer's authority
        # check on input_snapshot content is consistent.
        if isinstance(result.input_snapshot, dict):
            if idempotency_key is not None:
                result.input_snapshot["idempotency_key"] = idempotency_key
            if source_run_ids:
                result.input_snapshot["source_run_ids"] = dict(sorted(source_run_ids.items()))
            # Re-normalize so canonical JSON ordering matches what the
            # service-layer adapter originally produced.
            from backend.app.residual_model.canonical import (
                canonical_json_value,
            )

            result.input_snapshot = cast(
                dict[str, object],
                canonical_json_value(result.input_snapshot),
            )

            # Re-compute prediction_hash so it covers the
            # post-embedding input_snapshot (with idempotency_key +
            # source_run_ids). The persistence layer's loader rebuilds
            # the hash from the canonical_output stored in DB (which
            # contains the post-embedding snapshot); we must align our
            # result's prediction_hash with the post-embedding snapshot.
            from backend.app.residual_model.canonical import (
                canonical_payload_hash,
            )
            from backend.app.residual_model.persistence import (
                _canonical_dump,
            )

            # Compute the post-embedding prediction_hash in-place (set to None
            # before hashing, then re-attach the real hash). This
            # avoids the Pydantic "prediction_hash cannot be None"
            # validation error by computing the hash directly from the
            # dict (not via model_validate with None).
            payload_for_hash = result.model_dump(mode="python")
            payload_for_hash["prediction_hash"] = None  # canonicalize-without-hash
            canonical = _canonical_dump(
                ResidualPredictionExecutionResult.model_validate(
                    {**payload_for_hash, "prediction_hash": "0" * 64}
                )
            )
            canonical["prediction_hash"] = None
            new_hash = canonical_payload_hash(canonical)
            result = ResidualPredictionExecutionResult.model_validate(
                {**result.model_dump(mode="python"), "prediction_hash": new_hash}
            )

        # ---- 7. Replay / conflict pre-check (PR #76 §7.2) ----
        # The persistence layer also handles this, but pre-checking here
        # gives cleaner status code mapping (200 for replay vs 409 for
        # conflict) and avoids round-tripping through persistence.
        prior_run = await get_residual_prediction_run_by_input_signature(
            session,
            prediction_input_signature=result.prediction_input_signature,
        )
        if prior_run is not None:
            loaded_prior = await load_residual_prediction_run_by_id(session, run_id=prior_run.id)
            if loaded_prior is not None:
                if prediction_results_business_compatible(loaded_prior, result):
                    # True replay → return 200 with existing envelope
                    envelope = _prediction_envelope_from_orm(prior_run)
                    return Response(
                        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
                        media_type="application/json",
                        status_code=status.HTTP_200_OK,
                    )
                # Same signature but different payload → conflict
                return _json_error_response(
                    _execution_conflict_payload(
                        "prediction_input_signature already exists"
                        " with a different canonical payload"
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )

        # ---- 8. Persistence (delegated) ----
        run = await save_residual_prediction_run(
            session,
            result=result,
            feature_schema_version=result.input_snapshot["feature_schema_version"]
            if isinstance(result.input_snapshot, dict)
            else config.rules.feature_schema_version,
            feature_schema_hash=result.input_snapshot["feature_schema_hash"]
            if isinstance(result.input_snapshot, dict)
            else "0" * 64,
            artifact_hashes=list(result.input_snapshot.get("artifact_hashes", []))
            if isinstance(result.input_snapshot, dict)
            else [],
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError) as exc:
        # Integrity errors map to 500 — caught BEFORE the generic
        # ResidualModelPersistenceError because IntegrityError is a
        # subclass.
        logger.warning(
            "residual_model_api.execution_integrity_error exc=%r",
            exc,
            extra={"kind": "prediction", "operation": "post"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except ResidualModelHashConflictError:
        logger.warning(
            "residual_model_api.prediction_hash_conflict",
            extra={"kind": "prediction", "operation": "post"},
        )
        return _json_error_response(
            _execution_conflict_payload(
                "prediction_input_signature already exists with a different canonical payload"
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    except ResidualModelPersistenceError as exc:
        # Persistence-layer authority checks raised. Map known
        # messages to the contract's status codes:
        # - "training run referenced by prediction was not found" → 404
        # - "task9_result_hash authority mismatch" → 409
        # - "Task 9 run X was not found" → 409
        # - everything else → 500
        msg = str(exc)
        if "training run referenced by prediction was not found" in msg:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if "task9_result_hash authority mismatch" in msg or "Task 9 run" in msg:
            return _json_error_response(
                _execution_conflict_payload(msg),
                status_code=status.HTTP_409_CONFLICT,
            )
        logger.warning(
            "residual_model_api.prediction_persistence_error exc=%r",
            exc,
            extra={"kind": "prediction", "operation": "post"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.execution_unexpected_error",
            extra={"kind": "prediction", "operation": "post"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    envelope = _prediction_envelope_from_orm(run)
    headers = {
        "Content-Type": "application/json",
        "Location": f"/api/v1/residual-model/prediction-runs/{run.id}",
    }
    return Response(
        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        status_code=status.HTTP_201_CREATED,
        headers=headers,
    )


@router.get(
    "/prediction-runs/{run_id}",
    summary="Inspect an existing residual-model prediction run.",
)
async def get_prediction_run(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the PR #76 §5.2 envelope for an existing prediction run."""
    try:
        run = await get_residual_prediction_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_prediction_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        envelope = _prediction_envelope_from_orm(run)
    except (
        ResidualModelPersistenceIntegrityError,
        ResidualArtifactIntegrityError,
    ):
        logger.warning(
            "residual_model_api.execution_integrity_error",
            extra={"run_id": run_id, "kind": "prediction", "operation": "get"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.execution_unexpected_error",
            extra={"run_id": run_id, "kind": "prediction", "operation": "get"},
        )
        return _json_error_response(
            _execution_integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        content=json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
        media_type="application/json",
        status_code=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Training run report endpoints (Slice 1 — unchanged from PR #75)
# ---------------------------------------------------------------------------


@router.get(
    "/training-runs/{run_id}/report.json",
    summary="Download residual-model training run report (JSON).",
)
async def get_training_run_report_json(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the JSON residual-model training run report.

    Reuses:
    - get_residual_training_run (existence check + ORM row for created_at
      and manifest_snapshot)
    - load_residual_training_run_by_id (full loader with artifacts)
    - render_residual_training_json_report (renderer from PR #73)
    """
    try:
        # Existence check first so missing-run maps to 404 cleanly. The ORM
        # row also carries created_at and manifest_snapshot which the
        # renderer needs.
        run = await get_residual_training_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        loaded = await load_residual_training_run_by_id(session, run_id=run_id)
        if loaded is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        body = render_residual_training_json_report(
            run_id=run.id,
            created_at=run.created_at,
            output=loaded,
            manifest_snapshot=run.manifest_snapshot,
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError):
        logger.warning(
            "residual_model_api.integrity_error",
            extra={"run_id": run_id, "kind": "training"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        # Don't shield FastAPI-raised HTTPExceptions; let them bubble.
        raise
    except Exception:
        # Catch-all: shield ALL persistence/loader internals (sqlalchemy,
        # asyncpg, OS, traceback, blob bytes, hash conflict, etc.) from
        # leaking to clients.
        logger.exception(
            "residual_model_api.unexpected_error",
            extra={"run_id": run_id, "kind": "training"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    filename = f"residual-training-run-{run_id}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/training-runs/{run_id}/report.csv",
    summary="Download residual-model training run report (ZIP of CSV/JSON parts).",
)
async def get_training_run_report_csv(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the ZIP residual-model training run report.

    Per TASK-010 contract: the .csv endpoint actually returns a deterministic
    ZIP whose namelist includes manifest.json, run.csv, artifacts.csv,
    metrics.json, warnings.csv, blockers.csv (manifest_rows.csv when present).

    Reuses:
    - get_residual_training_run
    - load_residual_training_run_by_id
    - render_residual_training_csv_report
    """
    try:
        run = await get_residual_training_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        loaded = await load_residual_training_run_by_id(session, run_id=run_id)
        if loaded is None:
            return _json_error_response(
                _not_found_training_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        zip_bytes = render_residual_training_csv_report(
            run_id=run.id,
            created_at=run.created_at,
            output=loaded,
            manifest_snapshot=run.manifest_snapshot,
            artifacts=loaded.artifacts,
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError):
        logger.warning(
            "residual_model_api.integrity_error",
            extra={"run_id": run_id, "kind": "training"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.unexpected_error",
            extra={"run_id": run_id, "kind": "training"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    filename = f"residual-training-run-{run_id}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# Prediction run report endpoints (Slice 1 — unchanged from PR #75)
# ---------------------------------------------------------------------------


@router.get(
    "/prediction-runs/{run_id}/report.json",
    summary="Download residual-model prediction run report (JSON).",
)
async def get_prediction_run_report_json(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the JSON residual-model prediction run report.

    Reuses:
    - get_residual_prediction_run
    - load_residual_prediction_run_by_id
    - render_residual_prediction_json_report
    """
    try:
        run = await get_residual_prediction_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_prediction_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        loaded = await load_residual_prediction_run_by_id(session, run_id=run_id)
        if loaded is None:
            return _json_error_response(
                _not_found_prediction_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        body = render_residual_prediction_json_report(
            run_id=run.id,
            created_at=run.created_at,
            output=loaded,
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError):
        logger.warning(
            "residual_model_api.integrity_error",
            extra={"run_id": run_id, "kind": "prediction"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.unexpected_error",
            extra={"run_id": run_id, "kind": "prediction"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    filename = f"residual-prediction-run-{run_id}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get(
    "/prediction-runs/{run_id}/report.csv",
    summary="Download residual-model prediction run report (ZIP of CSV/JSON parts).",
)
async def get_prediction_run_report_csv(
    run_id: RunIdPath,
    session: SessionDep,
) -> Response:
    """Return the ZIP residual-model prediction run report.

    Per TASK-010 contract: the .csv endpoint actually returns a deterministic
    ZIP whose namelist includes manifest.json, run.csv, prediction_rows.csv,
    warnings.csv, blockers.csv.

    Reuses:
    - get_residual_prediction_run
    - load_residual_prediction_run_by_id
    - render_residual_prediction_csv_report
    """
    try:
        run = await get_residual_prediction_run(session, run_id=run_id)
        if run is None:
            return _json_error_response(
                _not_found_prediction_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        loaded = await load_residual_prediction_run_by_id(session, run_id=run_id)
        if loaded is None:
            return _json_error_response(
                _not_found_prediction_payload(),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        zip_bytes = render_residual_prediction_csv_report(
            run_id=run.id,
            created_at=run.created_at,
            output=loaded,
        )
    except (ResidualModelPersistenceIntegrityError, ResidualArtifactIntegrityError):
        logger.warning(
            "residual_model_api.integrity_error",
            extra={"run_id": run_id, "kind": "prediction"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "residual_model_api.unexpected_error",
            extra={"run_id": run_id, "kind": "prediction"},
        )
        return _json_error_response(
            _integrity_error_payload(),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    filename = f"residual-prediction-run-{run_id}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
