"""Flush-only persistence for the V0.6-S3 evaluation authority."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.pit.canonical import hash_payload
from backend.app.pit.evaluation import (
    EvaluationComputation,
    EvaluationConflictError,
    EvaluationIntegrityError,
)
from backend.app.pit.evaluation_models import ForecastEvaluation, ForecastEvaluationDaily


def _json_payload(value: object) -> dict[str, Any]:
    # Keep the shared rolling-backtest canonicalizer behind a function boundary.
    # The ORM registry imports this module while rolling_backtest.canonical is
    # still being initialized; a module-level import would recreate that cycle.
    from backend.app.rolling_backtest.canonical import canonical_json_value

    normalized = canonical_json_value(value)
    if not isinstance(normalized, dict):
        raise EvaluationIntegrityError("EVALUATION_PAYLOAD_NOT_OBJECT")
    return cast(dict[str, Any], normalized)


def _sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _row_payload(row: Any) -> dict[str, Any]:
    return {
        "date": row.evaluation_date,
        "predicted_quantity_kg": row.predicted_quantity_kg,
        "actual_quantity_kg": row.actual_quantity_kg,
        "actual_status": row.actual_status,
        "actual_revision_id": row.actual_revision_id,
        "actual_source_hash": row.actual_source_hash,
        "error_kg": row.error_kg,
        "absolute_error_kg": row.absolute_error_kg,
        "evaluation_as_of": row.evaluation_as_of,
    }


class ForecastEvaluationRepository:
    """Append-only repository; transaction ownership remains with the caller."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, computation: EvaluationComputation) -> ForecastEvaluation:
        expected_identity = hash_payload(computation.identity_payload())
        expected_result = hash_payload(computation.result_payload())
        expected_payload = hash_payload(computation.payload())
        if computation.evaluation_identity_hash != expected_identity:
            raise EvaluationIntegrityError("EVALUATION_IDENTITY_HASH_MISMATCH")
        if computation.evaluation_result_hash != expected_result:
            raise EvaluationIntegrityError("EVALUATION_RESULT_HASH_MISMATCH")
        if computation.evaluation_payload_hash != expected_payload:
            raise EvaluationIntegrityError("EVALUATION_PAYLOAD_HASH_MISMATCH")
        if not all(
            _sha256(value) for value in (expected_identity, expected_result, expected_payload)
        ):
            raise EvaluationIntegrityError("EVALUATION_HASH_INVALID")

        existing = await self.session.get(ForecastEvaluation, computation.evaluation_id)
        if existing is not None:
            if (
                existing.evaluation_identity_hash == computation.evaluation_identity_hash
                and existing.evaluation_payload_hash == computation.evaluation_payload_hash
                and existing.evaluation_result_hash == computation.evaluation_result_hash
            ):
                return await self.get_evaluation(computation.evaluation_id)
            raise EvaluationConflictError("FORECAST_EVALUATION_CONFLICT")

        payload = _json_payload(computation.payload())
        model = ForecastEvaluation(
            evaluation_id=computation.evaluation_id,
            forecast_run_id=computation.forecast_run_id,
            base_id=computation.base_id,
            target_season=computation.target_season,
            evaluation_mode=computation.evaluation_mode,
            as_of_date=computation.as_of_date,
            evaluation_created_at=computation.evaluation_created_at,
            forecast_input_hash=computation.forecast_input_hash,
            forecast_result_hash=computation.forecast_result_hash,
            actual_authority_ids=list(computation.actual_authority_ids),
            actual_authority_hashes=list(computation.actual_authority_hashes),
            realized_weather_authority_ids=list(computation.realized_weather_authority_ids),
            realized_weather_authority_hashes=list(computation.realized_weather_authority_hashes),
            evaluated_start_date=computation.evaluated_start_date,
            evaluated_end_date=computation.evaluated_end_date,
            actual_coverage_status=computation.actual_coverage_status.value,
            season_total_metrics=_json_payload(computation.season_total_metrics),
            daily_metrics=_json_payload(computation.daily_metrics),
            single_day_peak_metrics=_json_payload(computation.single_day_peak_metrics),
            rolling_7day_peak_metrics=_json_payload(computation.rolling_7day_peak_metrics),
            weather_metrics=_json_payload(computation.weather_metrics),
            warnings=list(computation.warnings),
            evaluation_payload_json=payload,
            evaluation_identity_hash=computation.evaluation_identity_hash,
            evaluation_payload_hash=computation.evaluation_payload_hash,
            evaluation_result_hash=computation.evaluation_result_hash,
            daily_row_count=len(computation.rows),
            created_at=datetime.now(UTC),
        )
        self.session.add(model)
        for index, row in enumerate(computation.rows):
            row_payload = _json_payload(row.payload())
            self.session.add(
                ForecastEvaluationDaily(
                    evaluation_id=computation.evaluation_id,
                    row_index=index,
                    evaluation_date=row.evaluation_date,
                    predicted_quantity_kg=row.predicted_quantity_kg,
                    actual_quantity_kg=row.actual_quantity_kg,
                    actual_status=row.actual_status.value,
                    actual_revision_id=row.actual_revision_id,
                    actual_source_hash=row.actual_source_hash,
                    error_kg=row.error_kg,
                    absolute_error_kg=row.absolute_error_kg,
                    evaluation_as_of=row.evaluation_as_of,
                    row_hash=hash_payload(row_payload),
                )
            )
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise EvaluationConflictError("FORECAST_EVALUATION_INSERT_CONFLICT") from exc
        except SQLAlchemyError as exc:
            raise EvaluationIntegrityError("FORECAST_EVALUATION_INSERT_FAILED") from exc
        return await self.get_evaluation(computation.evaluation_id)

    async def get_evaluation(self, evaluation_id: str) -> ForecastEvaluation:
        model = await self.session.get(ForecastEvaluation, evaluation_id)
        if model is None:
            raise EvaluationIntegrityError("FORECAST_EVALUATION_NOT_FOUND")
        payload = model.evaluation_payload_json
        if hash_payload(payload) != model.evaluation_payload_hash:
            raise EvaluationIntegrityError("EVALUATION_PAYLOAD_CORRUPTED")
        identity = payload.get("identity")
        result = payload.get("result")
        if not isinstance(identity, Mapping) or not isinstance(result, Mapping):
            raise EvaluationIntegrityError("EVALUATION_PAYLOAD_INVALID")
        if hash_payload(identity) != model.evaluation_identity_hash:
            raise EvaluationIntegrityError("EVALUATION_IDENTITY_CORRUPTED")
        if hash_payload(result) != model.evaluation_result_hash:
            raise EvaluationIntegrityError("EVALUATION_RESULT_CORRUPTED")
        rows = list(
            await self.session.scalars(
                select(ForecastEvaluationDaily)
                .where(ForecastEvaluationDaily.evaluation_id == evaluation_id)
                .order_by(ForecastEvaluationDaily.row_index)
            )
        )
        stored_rows = result.get("aligned_daily_rows")
        if not isinstance(stored_rows, list) or len(stored_rows) != len(rows):
            raise EvaluationIntegrityError("EVALUATION_DAILY_COUNT_MISMATCH")
        for row, expected in zip(rows, stored_rows, strict=True):
            if hash_payload(_json_payload(_row_payload(row))) != row.row_hash:
                raise EvaluationIntegrityError("EVALUATION_DAILY_ROW_CORRUPTED")
            if _json_payload(_row_payload(row)) != expected:
                raise EvaluationIntegrityError("EVALUATION_DAILY_ROW_PARITY_MISMATCH")
        if model.daily_row_count != len(rows):
            raise EvaluationIntegrityError("EVALUATION_DAILY_ROW_COUNT_MISMATCH")
        return model


__all__ = ["ForecastEvaluationRepository"]
