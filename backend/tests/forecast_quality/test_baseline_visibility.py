from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.enums import FrozenVersion, MetricStatus, ReasonCode
from backend.app.forecast_quality.schemas import BaselineRequest, BaselineSourceSnapshot


def _request() -> BaselineRequest:
    return BaselineRequest(
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


def _snapshot(visibility: datetime) -> BaselineSourceSnapshot:
    row: dict[str, Any] = {
        "target_date": date(2024, 2, 10),
        "actual_value_kg": Decimal("4"),
        "physical_key": "physical",
        "stable_actual_identity": "actual",
        "visibility_timestamp": visibility,
        "source_kind": "FARM_PICK",
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
    }
    return BaselineSourceSnapshot(
        "snapshot",
        "snapshot-hash",
        "rows-hash",
        "visibility-hash",
        datetime(2025, 2, 15, tzinfo=UTC),
        FrozenVersion.SEASON_ANALOG_MAPPING_V1,
        [row],
    )


def test_visibility_cutoff_is_point_in_time() -> None:
    visible = resolve_baseline_point_forecast(
        _request(), _snapshot(datetime(2025, 2, 1, tzinfo=UTC))
    )
    late = resolve_baseline_point_forecast(_request(), _snapshot(datetime(2025, 2, 20, tzinfo=UTC)))
    assert visible.metric_status is MetricStatus.COMPUTED
    assert late.reason_code is ReasonCode.BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF
