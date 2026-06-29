from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.rolling_backtest.enums import AvailabilitySourceType
from backend.app.rolling_backtest.orchestration import (
    _build_task9a_request,
    _load_capacity_inputs_typed,
    _load_task8_inputs_typed,
    _load_task9_run_parameters_typed,
)
from backend.app.rolling_backtest.schemas import PersistentUpstreamReference


class _FakeScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value

    def scalars(self) -> _FakeScalarResult:
        return self

    def all(self) -> object:
        return self._value


class _FakeSession:
    def __init__(self, values: list[object]) -> None:
        self._values = list(values)

    async def execute(self, _statement: object) -> _FakeScalarResult:
        if not self._values:
            raise AssertionError("unexpected execute call")
        return _FakeScalarResult(self._values.pop(0))


def _resolved_map() -> dict[str, object]:
    return {
        AvailabilitySourceType.TASK8_FORECAST_RUN.value: SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=33,
                )
            )
        ),
        AvailabilitySourceType.TASK7_WEATHER_OBSERVATION.value: SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=77,
                )
            )
        ),
        AvailabilitySourceType.TASK6_PLAN_VERSION.value: SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=55,
                )
            )
        ),
        "task8_forecast_run": SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=33,
                )
            )
        ),
        "task7_weather_observation": SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=77,
                )
            )
        ),
        "task6_plan_version": SimpleNamespace(
            resolved=SimpleNamespace(
                persistent_reference=PersistentUpstreamReference(
                    reference_type="database_run_id",
                    reference_value=55,
                )
            )
        ),
    }


def _node() -> SimpleNamespace:
    return SimpleNamespace(
        season_id=2026,
        as_of_local_date=date(2026, 3, 15),
        forecast_start_local_date=date(2026, 3, 16),
        forecast_end_local_date=date(2026, 3, 31),
        timezone="Asia/Shanghai",
        scope=SimpleNamespace(destination_factory_ids=SimpleNamespace(ids=(101,))),
    )


@pytest.mark.asyncio
async def test_task8_loader_builds_all_quantiles_without_placeholders() -> None:
    session = _FakeSession(
        [
            SimpleNamespace(
                id=33,
                model_run_id=11,
                artifact_id=22,
                plan_id=55,
                location_reference_id=66,
                weather_mapping_id=77,
                base_temperature_search_run_id=88,
                source_signature="d" * 64,
                as_of_date=date(2026, 3, 15),
                prediction_start_date=date(2026, 3, 16),
                prediction_end_date=date(2026, 3, 31),
                status="completed",
            ),
            SimpleNamespace(
                id=11,
                model_version="task8-v1",
                config_hash="a" * 64,
                source_signature="b" * 64,
            ),
            SimpleNamespace(id=22, run_id=11, artifact_hash="c" * 64),
            SimpleNamespace(id=55, farm_id=101, subfarm_id=202, variety_id=303),
            SimpleNamespace(id=66),
            SimpleNamespace(id=77),
            SimpleNamespace(id=88),
            [
                SimpleNamespace(
                    id=44,
                    forecast_run_id=33,
                    prediction_date=date(2026, 3, 16),
                    p50_kg=Decimal("10"),
                    p80_kg=Decimal("12"),
                    p90_kg=Decimal("14"),
                )
            ],
        ]
    )

    result = await _load_task8_inputs_typed(
        session,
        _node(),
        _resolved_map(),
    )  # type: ignore[arg-type]

    assert result.blocked is False
    predictions = result.request
    assert isinstance(predictions, list)
    assert [item.source_ref.forecast_quantile.value for item in predictions] == [
        "P50",
        "P80",
        "P90",
    ]
    assert [item.source_ref.source_quantity_kg for item in predictions] == [
        Decimal("10"),
        Decimal("12"),
        Decimal("14"),
    ]
    assert all(item.farm_id == 101 for item in predictions)
    assert all(item.source_ref.maturity_model_config_hash != "0" * 64 for item in predictions)
    assert all(item.source_ref.maturity_model_version != "unknown" for item in predictions)


@pytest.mark.asyncio
async def test_capacity_loader_blocks_instead_of_substituting_plan_totals() -> None:
    session = _FakeSession(
        [
            [
                SimpleNamespace(
                    id=55,
                    farm_id=101,
                    subfarm_id=None,
                    variety_id=303,
                    expected_total_marketable_kg=Decimal("70000"),
                )
            ]
        ]
    )

    result = await _load_capacity_inputs_typed(
        session,
        _node(),
        _resolved_map(),
    )  # type: ignore[arg-type]

    assert result.blocked is True
    assert result.blocker_code == "task9_replay_input_incomplete"
    assert "direct nominal capacity" in str(result.diagnostics["reason"])


@pytest.mark.asyncio
async def test_build_task9_request_propagates_missing_run_parameter_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _ok_task8(_session: object, _node: object, _resolved_map: object) -> object:
        return SimpleNamespace(blocked=False, request=[], blocker_code=None, diagnostics={})

    async def _ok_weather(_session: object, _node: object, _resolved_map: object) -> object:
        return SimpleNamespace(blocked=False, request=[], blocker_code=None, diagnostics={})

    async def _blocked_capacity(_session: object, _node: object, _resolved_map: object) -> object:
        return SimpleNamespace(
            blocked=True,
            request=None,
            blocker_code="task9_replay_input_incomplete",
            diagnostics={"reason": "real capacity authority sources are not yet wired"},
        )

    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_task8_inputs_typed",
        _ok_task8,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_weather_inputs_typed",
        _ok_weather,
    )
    monkeypatch.setattr(
        "backend.app.rolling_backtest.orchestration._load_capacity_inputs_typed",
        _blocked_capacity,
    )

    result = await _build_task9a_request(
        session=object(),  # type: ignore[arg-type]
        node=_node(),  # type: ignore[arg-type]
        resolutions=[
            SimpleNamespace(
                source_role="task8_daily_prediction",
                source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
                resolved=SimpleNamespace(),
            ),
            SimpleNamespace(
                source_role="task7_weather_observation",
                source_type=AvailabilitySourceType.TASK7_WEATHER_OBSERVATION,
                resolved=SimpleNamespace(),
            ),
            SimpleNamespace(
                source_role="task6_plan_version",
                source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
                resolved=SimpleNamespace(),
            ),
        ],
    )

    assert result.blocked is True
    assert result.blocker_code == "task9_replay_input_incomplete"
    assert "capacity authority" in str(result.diagnostics["reason"])


@pytest.mark.asyncio
async def test_run_parameter_loader_blocks_without_historical_authority() -> None:
    result = await _load_task9_run_parameters_typed(
        object(),  # type: ignore[arg-type]
        _node(),  # type: ignore[arg-type]
        _resolved_map(),  # type: ignore[arg-type]
    )

    assert result.blocked is True
    assert result.blocker_code == "task9_replay_input_incomplete"
    assert "historical authority sources" in str(result.diagnostics["reason"])
