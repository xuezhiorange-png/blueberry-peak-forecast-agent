from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.analytics.config import AnalyticsConfig, AnalyticsRules
from backend.app.analytics.daily_facts import (
    FactoryMetricSummary,
    _compute_daily_facts,
    _mark_build_failed,
    build_daily_facts_for_season,
)


def _config(*, months: tuple[int, ...] = (1,)) -> AnalyticsConfig:
    rules = AnalyticsRules(
        version="task3-v1",
        analysis_months=months,
        rolling_window_days=3,
        stable_peak_method="median",
        mean_peak_method="mean",
        peak_concentration_definition="stable_median_3d_peak_over_total",
        spring_festival_codes=("spring_festival",),
        unknown_farm_key="__UNKNOWN_FARM__",
        unknown_subfarm_key="__UNKNOWN_SUBFARM__",
        stream_batch_size=5000,
    )
    return AnalyticsConfig(
        rules=rules,
        config_hash="config-hash",
        snapshot={"version": "task3-v1", "analysis_months": list(months)},
    )


@pytest.mark.asyncio
async def test_build_daily_facts_skipped_result_keeps_factory_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config()
    season = SimpleNamespace(id=1, code="2025-2026")
    summary = FactoryMetricSummary(
        factory_id=7,
        total_weight_kg=Decimal("60.000000"),
        single_day_peak_kg=Decimal("30.000000"),
        single_day_peak_date=date(2026, 1, 3),
        stable_median_3d_peak_kg=Decimal("20.000000"),
        stable_median_3d_peak_date=date(2026, 1, 3),
        mean_3d_peak_kg=Decimal("20.000000"),
        mean_3d_peak_date=date(2026, 1, 3),
        peak_concentration=Decimal("0.3333333333"),
        variety_hhi=Decimal("1.0000000000"),
        farm_hhi=Decimal("0.5000000000"),
        subfarm_hhi=Decimal("0.5000000000"),
        unknown_farm_weight_share=Decimal("0.2000000000"),
        unknown_subfarm_weight_share=Decimal("0.1000000000"),
        spring_festival_day_count=2,
    )
    build_run = SimpleNamespace(
        id=11,
        aggregation_version="task3-v1",
        source_max_raw_id=99,
        source_eligible_row_count=3,
        source_eligible_weight_kg=Decimal("60.000000"),
        daily_fact_row_count=3,
        error_message=None,
        status="completed",
    )

    async def fake_season_by_code(_session: object, _season_code: str) -> SimpleNamespace:
        return season

    async def fake_current_cutoff(_session: object, *, season_id: int) -> int:
        assert season_id == 1
        return 99

    async def fake_existing_build_run(_session: object, **_: object) -> SimpleNamespace:
        return build_run

    async def fake_load_factory_summaries(
        _session: object,
        *,
        build_run_id: int,
    ) -> tuple[FactoryMetricSummary, ...]:
        assert build_run_id == 11
        return (summary,)

    class _Session:
        async def scalar(self, _statement: object) -> int:
            return 1

    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._season_by_code",
        fake_season_by_code,
    )
    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._current_source_cutoff",
        fake_current_cutoff,
    )
    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._existing_build_run",
        fake_existing_build_run,
    )
    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._load_factory_summaries_for_build_run",
        fake_load_factory_summaries,
        raising=False,
    )

    result = await build_daily_facts_for_season(_Session(), "2025-2026", config)

    assert result.status == "skipped"
    assert result.factory_summaries == (summary,)


@pytest.mark.asyncio
async def test_build_daily_facts_allows_empty_analysis_calendar_without_global_raw_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _config(months=(1,))
    season = SimpleNamespace(
        id=1,
        code="2025-2026",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )

    class _Session:
        async def stream(self, _statement: object) -> object:
            class _EmptyStream:
                def __aiter__(self) -> _EmptyStream:
                    return self

                async def __anext__(self) -> object:
                    raise StopAsyncIteration

            return _EmptyStream()

    async def fake_ensure_consistent_source_rows(*args: object, **kwargs: object) -> None:
        return None

    async def fake_load_holidays(*args: object, **kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._ensure_consistent_source_rows",
        fake_ensure_consistent_source_rows,
    )
    monkeypatch.setattr(
        "backend.app.analytics.daily_facts._load_holidays",
        fake_load_holidays,
    )

    result = await _compute_daily_facts(
        _Session(),
        season=season,
        config=config,
        source_max_raw_id=123,
    )

    assert result.daily_fact_row_count == 0
    assert result.factory_count == 0


@pytest.mark.asyncio
async def test_mark_build_failed_updates_by_id_without_orm_instance() -> None:
    statements: list[object] = []
    commit_count = 0

    class _Session:
        async def execute(self, statement: object) -> None:
            statements.append(statement)

        async def commit(self) -> None:
            nonlocal commit_count
            commit_count += 1

    await _mark_build_failed(
        _Session(),
        build_run_id=42,
        source_eligible_row_count=3,
        source_eligible_weight_kg=Decimal("60.000000"),
        error_message="sanitized error",
    )

    assert len(statements) == 1
    statement = statements[0]
    assert statement.table.name == "analytics_build_run"
    assert statement.compile().params["id_1"] == 42
    assert statement.compile().params["status"] == "failed"
    assert statement.compile().params["source_eligible_row_count"] == 3
    assert statement.compile().params["source_eligible_weight_kg"] == Decimal("60.000000")
    assert statement.compile().params["daily_fact_row_count"] == 0
    assert statement.compile().params["error_message"] == "sanitized error"
    assert commit_count == 1
