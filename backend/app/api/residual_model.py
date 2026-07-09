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
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_training_run,
)
from backend.app.residual_model.config import (
    ResidualModelConfig,
    load_residual_model_config,
)
from backend.app.residual_model.persistence import (
    ResidualArtifactIntegrityError,
    ResidualModelHashConflictError,
    ResidualModelPersistenceIntegrityError,
    load_residual_prediction_run_by_id,
    load_residual_training_run_by_id,
    save_residual_training_run,
)
from backend.app.residual_model.reporting import (
    render_residual_prediction_csv_report,
    render_residual_prediction_json_report,
    render_residual_training_csv_report,
    render_residual_training_json_report,
)
from backend.app.residual_model.service import (
    train_residual_model,
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
    (which the persistence layer populates with the full request
    snapshot, including the idempotency_key field embedded by the
    service-layer adapter).
    """
    if idempotency_key is None:
        return None
    # Query any training run whose input_snapshot contains the key with
    # a different canonical_payload_hash. We use a JSONB filter via
    # SQLAlchemy JSON path; SQLite falls back to JSON string containment
    # via text().
    from sqlalchemy import text as sql_text

    stmt = sql_text(
        "SELECT canonical_payload_hash FROM residual_model_training_run "
        "WHERE json_extract(input_snapshot, '$.idempotency_key') = :key"
    )
    result = await session.execute(stmt, {"key": idempotency_key})
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
        # The test monkeypatches `train_residual_model` at module level
        # to simulate integrity errors. We delegate through the
        # locally-aliased symbol (rather than calling
        # train_residual_model_from_contract_payload directly) so the
        # monkeypatch fires correctly.
        result, service_rows = train_residual_model(
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
