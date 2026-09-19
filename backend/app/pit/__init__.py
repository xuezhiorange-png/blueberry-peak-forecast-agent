"""V0.6 point-in-time forecast data foundation.

This package owns the small, append-only data foundation needed to answer
what was visible when a forecast was created.  It deliberately does not run
models, call weather providers, or score forecasts.
"""

from backend.app.pit.canonical import build_input_snapshot, hash_payload
from backend.app.pit.evaluation import (
    EVALUATION_POLICY_VERSION,
    ActualCoverageStatus,
    ActualDailyRecord,
    ActualDailyStatus,
    EvaluationComputation,
    EvaluationConflictError,
    EvaluationError,
    EvaluationIntegrityError,
    ForecastDailyPoint,
    RealizedWeatherPoint,
    align_forecast_actual,
    compute_forecast_actual_evaluation,
    evaluate_weather_forecast,
)
from backend.app.pit.evaluation_application import evaluate_forecast_run
from backend.app.pit.evaluation_models import ForecastEvaluation, ForecastEvaluationDaily
from backend.app.pit.evaluation_persistence import ForecastEvaluationRepository
from backend.app.pit.persistence import (
    PITConflictError,
    PITDataFoundationError,
    PITDataFoundationRepository,
    PITIntegrityError,
    PITNotFoundError,
    PITVisibilityRejected,
    PITWriteFailure,
)
from backend.app.pit.schemas import (
    AreaRevisionInput,
    ForecastDailySnapshotInput,
    ForecastRunSnapshot,
    ForecastRunSnapshotInput,
    PhenologyObservationInput,
    RealizedWeatherObservationInput,
    WeatherCaptureStatus,
    WeatherForecastSnapshotInput,
)
from backend.app.pit.visibility import (
    record_visible_at,
    weather_forecast_visible_at,
)

__all__ = [
    "AreaRevisionInput",
    "ActualCoverageStatus",
    "ActualDailyRecord",
    "ActualDailyStatus",
    "ForecastDailySnapshotInput",
    "ForecastRunSnapshot",
    "ForecastRunSnapshotInput",
    "ForecastDailyPoint",
    "ForecastEvaluation",
    "ForecastEvaluationDaily",
    "ForecastEvaluationRepository",
    "EvaluationComputation",
    "EvaluationConflictError",
    "EvaluationError",
    "EvaluationIntegrityError",
    "EVALUATION_POLICY_VERSION",
    "PITDataFoundationRepository",
    "PITConflictError",
    "PITDataFoundationError",
    "PITIntegrityError",
    "PITNotFoundError",
    "PITVisibilityRejected",
    "PITWriteFailure",
    "PhenologyObservationInput",
    "RealizedWeatherObservationInput",
    "RealizedWeatherPoint",
    "WeatherForecastSnapshotInput",
    "WeatherCaptureStatus",
    "build_input_snapshot",
    "align_forecast_actual",
    "compute_forecast_actual_evaluation",
    "evaluate_forecast_actual",
    "evaluate_forecast_run",
    "evaluate_weather_forecast",
    "hash_payload",
    "record_visible_at",
    "weather_forecast_visible_at",
]
