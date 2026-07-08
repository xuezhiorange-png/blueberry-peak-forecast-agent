"""Residual-model report download API.

Implements TASK-010 API Slice 1. Exposes the existing residual report
renderer (render_residual_training_json_report / render_residual_training_csv_report
/ render_residual_prediction_json_report / render_residual_prediction_csv_report)
as HTTP download endpoints.

This module MUST NOT modify residual_model/service.py, residual_model/reporting.py
semantics, or residual_model/persistence.py semantics. It is a thin adapter
between the renderer + the FastAPI transport.

Stability contract:
- 404 with stable payload (no FastAPI default "detail"):
    {
      "error": {
        "code": "RESIDUAL_MODEL_TRAINING_RUN_NOT_FOUND" |
                "RESIDUAL_MODEL_PREDICTION_RUN_NOT_FOUND",
        "message": "..."
      }
    }
- 500 with stable payload; never leak sqlalchemy / asyncpg / traceback /
  local paths / artifact binary:
    {
      "error": {
        "code": "RESIDUAL_MODEL_REPORT_INTEGRITY_ERROR",
        "message": "Residual-model report could not be generated."
      }
    }
- 200 JSON: media_type = application/json; the renderer embeds
  ``report_schema_version`` at the top level of the payload.
- 200 ZIP: media_type = application/zip, Content-Disposition attachment.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_training_run,
)
from backend.app.residual_model.persistence import (
    ResidualArtifactIntegrityError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
)
from backend.app.residual_model.reporting import (
    render_residual_prediction_csv_report,
    render_residual_prediction_json_report,
    render_residual_training_csv_report,
    render_residual_training_json_report,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Reusable dependency annotations matching the harvest_state / master_data
# style — avoids per-endpoint B008 lint warnings about Depends() in
# argument defaults.
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
RunIdPath = Annotated[int, Path(..., ge=1)]


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
# Training run report endpoints
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
# Prediction run report endpoints
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
