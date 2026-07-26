from datetime import UTC, date, datetime

from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.enums import FrozenVersion, ReasonCode
from backend.app.forecast_quality.schemas import BaselineRequest, BaselineSourceSnapshot


def test_missing_prior_analog_actual_is_not_zero() -> None:
    request = BaselineRequest(
        date(2025, 2, 10),
        date(2025, 1, 1),
        date(2025, 3, 31),
        date(2024, 1, 1),
        date(2024, 3, 31),
        "prior",
        datetime(2025, 2, 15, tzinfo=UTC),
        "farm-a",
        "subfarm-a",
        "variety-a",
        "P50",
        FrozenVersion.METRIC_INPUT_MASK_V1,
        FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    snapshot = BaselineSourceSnapshot(
        "snapshot",
        "snapshot-hash",
        "rows-hash",
        "visibility-hash",
        datetime(2025, 2, 15, tzinfo=UTC),
        FrozenVersion.SEASON_ANALOG_MAPPING_V1,
        [],
    )
    result = resolve_baseline_point_forecast(request, snapshot)
    assert result.baseline_point_forecast_kg is None
    assert result.reason_code is ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL
