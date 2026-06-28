from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from backend.app.rolling_backtest.calendar import resolve_default_node_dates
from backend.app.rolling_backtest.schemas import RollingNodeDefinition


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def test_default_nodes_regular_year_match_golden() -> None:
    payload = json.loads(_golden_path("default_nodes.json").read_text(encoding="utf-8"))

    resolved = resolve_default_node_dates(2026)

    assert [item.model_dump(mode="json") for item in resolved] == payload["season_2026"]


def test_default_nodes_leap_year_match_golden() -> None:
    payload = json.loads(_golden_path("default_nodes.json").read_text(encoding="utf-8"))

    resolved = resolve_default_node_dates(2028)

    assert [item.model_dump(mode="json") for item in resolved] == payload["season_2028"]


def test_forecast_start_date_must_be_as_of_plus_one_day() -> None:
    with pytest.raises(ValueError, match="forecast_start_local_date"):
        RollingNodeDefinition(
            season_id=2026,
            node_key="march_15",
            as_of_local_date=date(2026, 3, 15),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            forecast_start_local_date=date(2026, 3, 15),
            forecast_end_local_date=date(2026, 3, 31),
            destination_factory_ids=(101,),
            execution_mode="historical_observed",
            upstream_selection_mode="historical_resolution",
            forecast_horizon_policy_version="task11-horizon-v1",
            timezone="Asia/Shanghai",
        )


def test_duplicate_factories_are_rejected() -> None:
    with pytest.raises(ValueError, match="destination_factory_ids"):
        RollingNodeDefinition(
            season_id=2026,
            node_key="march_15",
            as_of_local_date=date(2026, 3, 15),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            forecast_start_local_date=date(2026, 3, 16),
            forecast_end_local_date=date(2026, 3, 31),
            destination_factory_ids=(101, 101),
            execution_mode="historical_observed",
            upstream_selection_mode="historical_resolution",
            forecast_horizon_policy_version="task11-horizon-v1",
            timezone="Asia/Shanghai",
        )


def test_invalid_date_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="forecast_end_local_date"):
        RollingNodeDefinition(
            season_id=2026,
            node_key="march_15",
            as_of_local_date=date(2026, 3, 15),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0, tzinfo=UTC),
            forecast_start_local_date=date(2026, 3, 16),
            forecast_end_local_date=date(2026, 3, 15),
            destination_factory_ids=(101,),
            execution_mode="historical_observed",
            upstream_selection_mode="historical_resolution",
            forecast_horizon_policy_version="task11-horizon-v1",
            timezone="Asia/Shanghai",
        )


def test_timezone_aware_cutoff_is_required() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RollingNodeDefinition(
            season_id=2026,
            node_key="march_15",
            as_of_local_date=date(2026, 3, 15),
            forecast_cutoff_at=datetime(2026, 3, 15, 12, 0),
            forecast_start_local_date=date(2026, 3, 16),
            forecast_end_local_date=date(2026, 3, 31),
            destination_factory_ids=(101,),
            execution_mode="historical_observed",
            upstream_selection_mode="historical_resolution",
            forecast_horizon_policy_version="task11-horizon-v1",
            timezone="Asia/Shanghai",
        )


def test_node_schema_forbids_extra_fields() -> None:
    with pytest.raises(ValueError, match="extra"):
        RollingNodeDefinition.model_validate(
            {
                "season_id": 2026,
                "node_key": "march_15",
                "as_of_local_date": "2026-03-15",
                "forecast_cutoff_at": "2026-03-15T12:00:00Z",
                "forecast_start_local_date": "2026-03-16",
                "forecast_end_local_date": "2026-03-31",
                "destination_factory_ids": [101],
                "execution_mode": "historical_observed",
                "upstream_selection_mode": "historical_resolution",
                "forecast_horizon_policy_version": "task11-horizon-v1",
                "timezone": "Asia/Shanghai",
                "unexpected": "boom",
            }
        )
