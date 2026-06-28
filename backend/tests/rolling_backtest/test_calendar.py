from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.rolling_backtest.calendar import resolve_default_node_dates
from backend.app.rolling_backtest.schemas import RollingBacktestConfig, RollingNodeDefinition


def _golden_path(name: str) -> Path:
    return Path(__file__).parent / "golden" / name


def _node_payload(
    *,
    season_id: int = 2026,
    node_key: str = "march_15",
    as_of_local_date: str = "2026-03-15",
    forecast_cutoff_at: str = "2026-03-15T04:00:00Z",
    forecast_start_local_date: str = "2026-03-16",
    forecast_end_local_date: str = "2026-03-31",
    timezone: str = "Asia/Shanghai",
) -> dict[str, object]:
    return {
        "season_id": season_id,
        "node_key": node_key,
        "as_of_local_date": as_of_local_date,
        "forecast_cutoff_at": forecast_cutoff_at,
        "forecast_start_local_date": forecast_start_local_date,
        "forecast_end_local_date": forecast_end_local_date,
        "scope": {
            "destination_factory_ids": {
                "mode": "include_ids",
                "ids": [202, 101],
            },
            "farm_ids": {"mode": "all", "ids": []},
            "subfarm_ids": {"mode": "all", "ids": []},
            "variety_ids": {"mode": "all", "ids": []},
        },
        "upstream_selection_mode": "historical_resolution",
        "forecast_horizon_policy_version": "task11-horizon-v1",
        "timezone": timezone,
    }


def _config_payload(
    *,
    execution_mode: str = "historical_observed",
    nodes: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "rolling_schema_version": "task11-rolling-v1",
        "canonical_serialization_version": "task11-canonical-v1",
        "availability_registry_version": "task11-availability-v1",
        "node_calendar_version": "task11-calendar-v1",
        "forecast_horizon_policy_version": "task11-horizon-v1",
        "upstream_selection_policy_version": "task11-selection-v1",
        "metric_policy_version": "task11-metrics-v1",
        "execution_mode": execution_mode,
        "task10_model_policy": {
            "policy": "historically_available_model",
            "training_run_semantic_identity": "1" * 64,
            "artifact_semantic_identities": ("2" * 64, "3" * 64, "4" * 64),
            "authority_visibility_identity": "5" * 64,
        },
        "calendar_phase_policy_version": "task11-calendar-phase-v1",
        "cutoff_policy_version": "task11-cutoff-v1",
        "cutoff_timezone": "Asia/Shanghai",
        "cutoff_local_time": "12:00:00",
        "nodes": nodes,
    }


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
        RollingNodeDefinition.model_validate(_node_payload(forecast_start_local_date="2026-03-15"))


def test_scope_is_canonical_and_duplicate_free() -> None:
    node = RollingNodeDefinition.model_validate(_node_payload())
    assert node.scope.destination_factory_ids.ids == (101, 202)

    with pytest.raises(ValueError, match="duplicates"):
        RollingNodeDefinition.model_validate(
            _node_payload()
            | {
                "scope": {
                    "destination_factory_ids": {
                        "mode": "include_ids",
                        "ids": [101, 101],
                    },
                    "farm_ids": {"mode": "all", "ids": []},
                    "subfarm_ids": {"mode": "all", "ids": []},
                    "variety_ids": {"mode": "all", "ids": []},
                }
            }
        )


def test_invalid_date_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="forecast_end_local_date"):
        RollingNodeDefinition.model_validate(_node_payload(forecast_end_local_date="2026-03-15"))


def test_timezone_aware_cutoff_is_required() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        RollingNodeDefinition.model_validate(
            _node_payload(forecast_cutoff_at="2026-03-15T12:00:00")
        )


def test_node_key_date_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="node_key must match"):
        RollingNodeDefinition.model_validate(
            _node_payload(
                as_of_local_date="2026-03-16",
                forecast_start_local_date="2026-03-17",
                forecast_cutoff_at="2026-03-16T04:00:00Z",
            )
        )


def test_cutoff_local_date_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="local date must match"):
        RollingBacktestConfig.model_validate(
            _config_payload(nodes=[_node_payload(forecast_cutoff_at="2026-03-14T04:00:00Z")])
        )


def test_cutoff_local_time_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="local time must match"):
        RollingBacktestConfig.model_validate(
            _config_payload(nodes=[_node_payload(forecast_cutoff_at="2026-03-15T05:00:00Z")])
        )


def test_node_timezone_must_match_run_policy() -> None:
    with pytest.raises(ValueError, match="node timezone must match"):
        RollingBacktestConfig.model_validate(_config_payload(nodes=[_node_payload(timezone="UTC")]))


def test_mixed_execution_modes_are_rejected() -> None:
    with pytest.raises(ValueError, match="extra"):
        RollingNodeDefinition.model_validate(
            _node_payload() | {"execution_mode": "retrospective_replay"}
        )


def test_duplicate_node_keys_are_scoped_per_season() -> None:
    config = RollingBacktestConfig.model_validate(
        _config_payload(
            nodes=[
                _node_payload(season_id=2026),
                _node_payload(
                    season_id=2027,
                    as_of_local_date="2027-03-15",
                    forecast_cutoff_at="2027-03-15T04:00:00Z",
                    forecast_start_local_date="2027-03-16",
                    forecast_end_local_date="2027-03-31",
                ),
            ]
        )
    )
    assert [node.season_id for node in config.nodes] == [2026, 2027]


def test_node_schema_forbids_extra_fields() -> None:
    with pytest.raises(ValueError, match="extra"):
        RollingNodeDefinition.model_validate(_node_payload() | {"unexpected": "boom"})
