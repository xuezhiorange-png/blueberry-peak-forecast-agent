from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from backend.app.forecast_quality.baseline import resolve_baseline_point_forecast
from backend.app.forecast_quality.enums import (
    ComparisonAvailability,
    FrozenVersion,
    MetricStatus,
    ReasonCode,
)
from backend.app.forecast_quality.schemas import BaselineRequest, BaselineSourceSnapshot


def _request(target: date, quantile: str = "P50", **overrides: Any) -> BaselineRequest:
    values: dict[str, Any] = {
        "current_target_date": target,
        "current_season_start": date(target.year, 1, 1),
        "current_season_end": date(target.year, 3, 31),
        "prior_season_start": date(target.year - 1, 1, 1),
        "prior_season_end": date(target.year - 1, 3, 31),
        "prior_season_identity": "prior-season",
        "current_forecast_cutoff_at": datetime(2025, 2, 15, tzinfo=UTC),
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
        "requested_quantile": quantile,
        "metric_policy_version": FrozenVersion.METRIC_INPUT_MASK_V1,
        "baseline_policy_version": FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    }
    values.update(overrides)
    return BaselineRequest(**values)


def _snapshot(rows: list[dict[str, Any]]) -> BaselineSourceSnapshot:
    return BaselineSourceSnapshot(
        "snapshot-a",
        "hash-a",
        "rows-a",
        "visibility-a",
        datetime(2025, 2, 15, tzinfo=UTC),
        FrozenVersion.SEASON_ANALOG_MAPPING_V1,
        rows,
    )


def _row(
    target: date,
    value: str = "4",
    visibility: datetime | None = None,
    source: str = "FARM_PICK",
) -> dict[str, Any]:
    return {
        "target_date": target,
        "actual_value_kg": Decimal(value),
        "physical_key": f"physical-{target}",
        "stable_actual_identity": f"actual-{target}",
        "visibility_timestamp": visibility or datetime(2025, 2, 1, tzinfo=UTC),
        "source_kind": source,
        "farm_business_key": "farm-a",
        "subfarm_business_key": "subfarm-a",
        "variety_business_key": "variety-a",
    }


def test_six_baseline_fixtures_and_point_only_quantiles() -> None:
    normal = resolve_baseline_point_forecast(
        _request(date(2025, 2, 10)), _snapshot([_row(date(2024, 2, 10))])
    )
    assert normal.metric_status is MetricStatus.COMPUTED
    assert normal.reason_code is ReasonCode.NONE
    leap = resolve_baseline_point_forecast(
        _request(date(2024, 2, 29)), _snapshot([_row(date(2023, 2, 28))])
    )
    assert leap.baseline_point_forecast_kg == Decimal("4")
    no_day = resolve_baseline_point_forecast(
        _request(
            date(2025, 3, 31),
            current_season_start=date(2025, 1, 1),
            current_season_end=date(2025, 3, 31),
            prior_season_start=date(2024, 1, 1),
            prior_season_end=date(2024, 3, 1),
        ),
        _snapshot([]),
    )
    assert no_day.reason_code is ReasonCode.NO_PRIOR_SEASON_ANALOG_DAY
    no_actual = resolve_baseline_point_forecast(_request(date(2025, 2, 10)), _snapshot([]))
    assert no_actual.reason_code is ReasonCode.NO_PRIOR_SEASON_ANALOG_ACTUAL
    late = resolve_baseline_point_forecast(
        _request(date(2025, 2, 10)),
        _snapshot([_row(date(2024, 2, 10), visibility=datetime(2025, 2, 20, tzinfo=UTC))]),
    )
    assert late.reason_code is ReasonCode.BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF
    for quantile in ("P80", "P90"):
        blocked = resolve_baseline_point_forecast(
            _request(date(2025, 2, 10), quantile), _snapshot([_row(date(2024, 2, 10))])
        )
        assert blocked.comparison_availability is ComparisonAvailability.BLOCKED
        assert blocked.metric_status is MetricStatus.NOT_COMPUTABLE
        assert blocked.reason_code is ReasonCode.BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED
        assert blocked.baseline_point_forecast_kg is None


def test_red_sources_never_become_baseline_actuals() -> None:
    sources = (
        "latest_actual_fallback",
        "post_cutoff_revision",
        "model_forecast_proxy",
        "receipt_arrival_proxy",
        "implicit_zero_fallback",
        "s2_row_set_reuse",
    )
    for source in sources:
        result = resolve_baseline_point_forecast(
            _request(date(2025, 2, 10)), _snapshot([_row(date(2024, 2, 10), source=source)])
        )
        assert result.metric_status is MetricStatus.NOT_COMPUTABLE
