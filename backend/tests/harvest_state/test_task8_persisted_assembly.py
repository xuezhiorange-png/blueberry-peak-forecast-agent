from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.app.harvest_state.authority_request_errors import Task9AuthorityRequestAssemblyError
from backend.app.harvest_state.authority_request_loader import (
    bind_task8_daily_prediction_availability_from_persisted_rows,
)
from backend.app.harvest_state.schemas import Task9ARequest
from backend.app.models.maturity import (
    MaturityDailyPredictionModel,
    MaturityForecastRun,
    MaturityModelArtifact,
    MaturityModelRun,
)
from backend.tests.harvest_state.conftest import make_request


class _PersistedTask8Session:
    def __init__(self, *, daily: MaturityDailyPredictionModel) -> None:
        self._rows = {
            (MaturityDailyPredictionModel, daily.id): daily,
            (MaturityForecastRun, daily.forecast_run_id): daily._forecast_run,
            (MaturityModelArtifact, daily._forecast_run.artifact_id): daily._artifact,
            (MaturityModelRun, daily._forecast_run.model_run_id): daily._model_run,
        }

    async def get(self, model: type[object], identifier: int) -> object | None:
        return self._rows.get((model, identifier))


def _request_with_task8_availability(*, available_at: datetime) -> Task9ARequest:
    request = Task9ARequest.model_validate(make_request())
    prediction = request.task8_daily_predictions[0]
    bound_prediction = prediction.model_copy(
        update={
            "source_ref": prediction.source_ref.model_copy(
                update={"maturity_daily_prediction_available_at": available_at}
            ),
            "verification_snapshot": prediction.verification_snapshot.model_copy(
                update={"maturity_daily_prediction_available_at": available_at}
            ),
        }
    )
    return request.model_copy(update={"task8_daily_predictions": [bound_prediction]})


def _persisted_rows_for_request(
    request: Task9ARequest,
) -> MaturityDailyPredictionModel:
    prediction = request.task8_daily_predictions[0]
    source_ref = prediction.source_ref
    verification = prediction.verification_snapshot

    model_run = MaturityModelRun()
    model_run.id = source_ref.maturity_model_run_id
    model_run.model_version = source_ref.maturity_model_version
    model_run.config_hash = source_ref.maturity_model_config_hash
    model_run.source_signature = source_ref.maturity_model_source_signature

    artifact = MaturityModelArtifact()
    artifact.id = source_ref.maturity_model_artifact_id
    artifact.run_id = verification.maturity_model_artifact_run_id
    artifact.artifact_hash = source_ref.maturity_model_artifact_hash

    forecast_run = MaturityForecastRun()
    forecast_run.id = source_ref.maturity_forecast_run_id
    forecast_run.model_run_id = source_ref.maturity_model_run_id
    forecast_run.artifact_id = source_ref.maturity_model_artifact_id
    forecast_run.plan_id = source_ref.plan_id
    forecast_run.location_reference_id = source_ref.location_reference_id
    forecast_run.weather_mapping_id = source_ref.weather_mapping_id
    forecast_run.base_temperature_search_run_id = source_ref.base_temperature_search_run_id
    forecast_run.as_of_date = source_ref.maturity_forecast_as_of_date
    forecast_run.prediction_start_date = verification.maturity_forecast_prediction_start_date
    forecast_run.prediction_end_date = verification.maturity_forecast_prediction_end_date
    forecast_run.source_signature = source_ref.maturity_forecast_source_signature
    forecast_run.status = verification.maturity_forecast_run_status

    available_at = source_ref.maturity_daily_prediction_available_at
    assert available_at is not None
    daily = MaturityDailyPredictionModel()
    daily.id = source_ref.maturity_daily_prediction_id
    daily.forecast_run_id = forecast_run.id
    daily.prediction_date = prediction.prediction_date
    daily.created_at = available_at
    daily._forecast_run = forecast_run
    daily._artifact = artifact
    daily._model_run = model_run
    forecast_run._artifact = artifact
    forecast_run._model_run = model_run
    return daily


@pytest.mark.asyncio
async def test_task8_availability_is_injected_from_persisted_row_and_tamper_rejected() -> None:
    persisted_at = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
    request = _request_with_task8_availability(available_at=persisted_at)
    daily = _persisted_rows_for_request(request)
    session = _PersistedTask8Session(daily=daily)

    assembled = await bind_task8_daily_prediction_availability_from_persisted_rows(session, request)
    assembled_prediction = assembled.task8_daily_predictions[0]
    assert (
        assembled_prediction.source_ref.maturity_daily_prediction_available_at == daily.created_at
    )
    assert (
        assembled_prediction.verification_snapshot.maturity_daily_prediction_available_at
        == daily.created_at
    )
    assert (
        assembled_prediction.source_ref.maturity_daily_prediction_available_at
        == assembled_prediction.verification_snapshot.maturity_daily_prediction_available_at
        == daily.created_at
    )

    tampered = _request_with_task8_availability(available_at=datetime(2026, 3, 1, 3, 0, tzinfo=UTC))
    with pytest.raises(Task9AuthorityRequestAssemblyError) as exc_info:
        await bind_task8_daily_prediction_availability_from_persisted_rows(session, tampered)
    assert exc_info.value.details["reason"] == "task8_daily_prediction_availability_mismatch"
