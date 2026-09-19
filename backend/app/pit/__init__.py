"""V0.6 point-in-time forecast data foundation.

This package owns the small, append-only data foundation needed to answer
what was visible when a forecast was created.  It deliberately does not run
models, call weather providers, or score forecasts.
"""

from backend.app.pit.canonical import build_input_snapshot, hash_payload
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
    "ForecastDailySnapshotInput",
    "ForecastRunSnapshot",
    "ForecastRunSnapshotInput",
    "PITDataFoundationRepository",
    "PITConflictError",
    "PITDataFoundationError",
    "PITIntegrityError",
    "PITNotFoundError",
    "PITVisibilityRejected",
    "PITWriteFailure",
    "PhenologyObservationInput",
    "RealizedWeatherObservationInput",
    "WeatherForecastSnapshotInput",
    "WeatherCaptureStatus",
    "build_input_snapshot",
    "hash_payload",
    "record_visible_at",
    "weather_forecast_visible_at",
]
