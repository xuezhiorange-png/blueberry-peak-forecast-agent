from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from backend.app.baseline.config import load_baseline_config
from backend.app.baseline.reporting import write_execution_reports
from backend.app.baseline.service import execute_baseline_backtest, load_backtest_run_result
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.baseline_backtest import BaselineBacktestResult, BaselineBacktestRun
from backend.app.models.master_data import Factory, Season

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _write_baseline_config(path: Path, *, minimum_training_rows: int = 2) -> None:
    path.write_text(
        f"""
model:
  version: task4-baseline-v1
  target: stable_median_3d_peak_kg
  ridge:
    alpha: 1.0
    fit_intercept: true
  features:
    - total_weight_kg
    - variety_hhi
    - farm_hhi
    - subfarm_hhi
evaluation:
  primary_scheme: leave_one_season_out
  minimum_training_rows: {minimum_training_rows}
  mape_zero_policy: exclude
  unit: kg
random_seed: 20260621
""",
        encoding="utf-8",
    )


def _metric(
    *,
    factory_id: int,
    total_weight_kg: str,
    stable_peak_kg: str,
    peak_concentration: str | None = None,
    variety_hhi: str = "0.3000000000",
    farm_hhi: str = "0.4000000000",
    subfarm_hhi: str = "0.5000000000",
) -> dict[str, object]:
    metric: dict[str, object] = {
        "factory_id": factory_id,
        "total_weight_kg": Decimal(total_weight_kg),
        "stable_peak_kg": Decimal(stable_peak_kg),
        "variety_hhi": Decimal(variety_hhi),
        "farm_hhi": Decimal(farm_hhi),
        "subfarm_hhi": Decimal(subfarm_hhi),
    }
    if peak_concentration is not None:
        metric["peak_concentration"] = Decimal(peak_concentration)
    return metric


def _all_paths_exist(paths: tuple[str, ...]) -> bool:
    return all(Path(path).exists() for path in paths)


async def _seed_seasons_and_factories() -> tuple[dict[str, int], dict[str, int]]:
    async with AsyncSessionMaker() as session:
        seasons = {
            "2024-2025": Season(
                code="2024-2025",
                start_date=date(2025, 1, 1),
                end_date=date(2025, 4, 30),
            ),
            "2025-2026": Season(
                code="2025-2026",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 4, 30),
            ),
            "2026-2027": Season(
                code="2026-2027",
                start_date=date(2027, 1, 1),
                end_date=date(2027, 4, 30),
            ),
        }
        factories = {
            "A": Factory(code="factory-a", name="Factory A", active=True),
            "B": Factory(code="factory-b", name="Factory B", active=True),
            "C": Factory(code="factory-c", name="Factory C", active=True),
        }
        session.add_all([*seasons.values(), *factories.values()])
        await session.commit()
        return (
            {code: season.id for code, season in seasons.items()},
            {code: factory.id for code, factory in factories.items()},
        )


async def _seed_task3_build_run(
    *,
    season_id: int,
    season_start: date,
    factory_metrics: list[dict[str, object]],
    aggregation_version: str = "task3-v1",
    config_hash: str = "task3-cfg",
    source_max_raw_id: int = 100,
) -> int:
    async with AsyncSessionMaker() as session:
        run = AnalyticsBuildRun(
            season_id=season_id,
            aggregation_version=aggregation_version,
            source_max_raw_id=source_max_raw_id,
            config_hash=config_hash,
            config_snapshot={"version": aggregation_version},
            status="completed",
            source_eligible_row_count=len(factory_metrics),
            source_eligible_weight_kg=sum(
                (metric["total_weight_kg"] for metric in factory_metrics),
                Decimal("0"),
            ),
            daily_fact_row_count=len(factory_metrics),
        )
        session.add(run)
        await session.flush()
        for metric in factory_metrics:
            total_weight = Decimal(str(metric["total_weight_kg"]))
            peak = Decimal(str(metric["stable_peak_kg"]))
            session.add(
                FactorySeasonPeakMetric(
                    build_run_id=run.id,
                    season_id=season_id,
                    factory_id=int(metric["factory_id"]),
                    analysis_start_date=season_start,
                    analysis_end_date=season_start,
                    calendar_day_count=120,
                    observed_day_count=80,
                    total_weight_kg=total_weight,
                    single_day_peak_kg=Decimal(str(metric.get("single_day_peak_kg", peak))),
                    single_day_peak_date=season_start,
                    stable_median_3d_peak_kg=peak,
                    stable_median_3d_peak_date=season_start,
                    mean_3d_peak_kg=Decimal(str(metric.get("mean_peak_kg", peak))),
                    mean_3d_peak_date=season_start,
                    peak_concentration=Decimal(
                        str(metric.get("peak_concentration", peak / total_weight))
                    ),
                    variety_hhi=Decimal(str(metric.get("variety_hhi", "0.3000000000"))),
                    farm_hhi=Decimal(str(metric.get("farm_hhi", "0.4000000000"))),
                    subfarm_hhi=Decimal(str(metric.get("subfarm_hhi", "0.5000000000"))),
                    unknown_farm_weight_share=Decimal("0.1000000000"),
                    unknown_subfarm_weight_share=Decimal("0.2000000000"),
                    spring_festival_day_count=5,
                )
            )
        await session.commit()
        return run.id


async def _count_task3_tables() -> tuple[int, int, int]:
    async with AsyncSessionMaker() as session:
        build_run_count = int(
            await session.scalar(select(func.count()).select_from(AnalyticsBuildRun)) or 0
        )
        daily_count = int(
            await session.scalar(select(func.count()).select_from(FactReceiptDaily)) or 0
        )
        metric_count = int(
            await session.scalar(select(func.count()).select_from(FactorySeasonPeakMetric)) or 0
        )
        return build_run_count, daily_count, metric_count


@pytest.mark.asyncio
async def test_baseline_backtest_dry_run_does_not_write_and_selects_latest_build_runs(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        source_max_raw_id=100,
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="900", stable_peak_kg="90"),
        ],
    )
    newer_run_id = await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        source_max_raw_id=150,
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1100", stable_peak_kg="110"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1000", stable_peak_kg="100"),
        ],
    )
    same_cutoff_lower_id = await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        source_max_raw_id=200,
        config_hash="task3-old-cfg",
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1200", stable_peak_kg="120"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1100", stable_peak_kg="110"),
        ],
    )
    same_cutoff_higher_id = await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        source_max_raw_id=200,
        config_hash="task3-cfg",
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1190", stable_peak_kg="119"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1090", stable_peak_kg="109"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2026-2027"],
        season_start=date(2027, 1, 1),
        source_max_raw_id=300,
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1300", stable_peak_kg="130"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1250", stable_peak_kg="125"),
        ],
    )
    before_counts = await _count_task3_tables()
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        result = await execute_baseline_backtest(session, config=config, dry_run=True)
        run_count = int(
            await session.scalar(select(func.count()).select_from(BaselineBacktestRun)) or 0
        )
        result_count = int(
            await session.scalar(select(func.count()).select_from(BaselineBacktestResult)) or 0
        )

    assert result.status == "dry_run"
    assert run_count == 0
    assert result_count == 0
    assert same_cutoff_higher_id > same_cutoff_lower_id
    assert result.source_build_runs[0]["build_run_id"] == newer_run_id
    assert result.source_build_runs[1]["build_run_id"] == same_cutoff_higher_id
    assert result.source_build_runs[1]["config_hash"] == "task3-cfg"
    assert await _count_task3_tables() == before_counts


@pytest.mark.asyncio
async def test_baseline_backtest_explicit_build_run_override_and_skip_rehydrates_results(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    older_run_id = await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        source_max_raw_id=100,
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="1000",
                stable_peak_kg="100",
                peak_concentration="0.1000000000",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="900",
                stable_peak_kg="90",
                peak_concentration="0.1000000000",
            ),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        source_max_raw_id=150,
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1100", stable_peak_kg="110"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1000", stable_peak_kg="100"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        source_max_raw_id=200,
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="1200",
                stable_peak_kg="120",
                peak_concentration="0.1100000000",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="1100",
                stable_peak_kg="110",
                peak_concentration="0.1000000000",
            ),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2026-2027"],
        season_start=date(2027, 1, 1),
        source_max_raw_id=300,
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="1300",
                stable_peak_kg="130",
                peak_concentration="0.1000000000",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="1250",
                stable_peak_kg="125",
                peak_concentration="0.1000000000",
            ),
        ],
    )
    before_task3_counts = await _count_task3_tables()
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        first = await execute_baseline_backtest(
            session,
            config=config,
            explicit_build_run_ids={"2024-2025": older_run_id},
        )
        skipped = await execute_baseline_backtest(
            session,
            config=config,
            explicit_build_run_ids={"2024-2025": older_run_id},
        )

    assert first.status == "completed"
    assert skipped.status == "skipped"
    assert first.source_build_runs[0]["build_run_id"] == older_run_id
    assert skipped.source_build_runs == first.source_build_runs
    assert skipped.results == first.results
    assert skipped.model_summaries == first.model_summaries
    assert skipped.season_summaries == first.season_summaries
    assert skipped.factory_summaries == first.factory_summaries
    assert await _count_task3_tables() == before_task3_counts


@pytest.mark.asyncio
async def test_baseline_backtest_rejects_mixed_task3_versions_or_hashes(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        aggregation_version="task3-v1",
        config_hash="cfg-a",
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        aggregation_version="task3-v2",
        config_hash="cfg-b",
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1200", stable_peak_kg="120"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        result = await execute_baseline_backtest(session, config=config, dry_run=True)

    assert result.status == "failed"
    assert result.error_message is not None
    assert "aggregation_version" in result.error_message or "config_hash" in result.error_message


@pytest.mark.asyncio
async def test_baseline_backtest_single_season_completes_with_excluded_rows(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path, minimum_training_rows=4)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        result = await execute_baseline_backtest(
            session,
            config=config,
            season_codes=("2024-2025",),
        )

    assert result.status == "completed"
    assert result.excluded_rows
    assert all(row.target_season_code == "2024-2025" for row in result.results)
    assert any(row.baseline_name == "previous_season_peak" for row in result.excluded_rows)
    assert any(row.baseline_name == "ridge_structure" for row in result.excluded_rows)


@pytest.mark.asyncio
async def test_baseline_backtest_ridge_metadata_uses_training_only_and_no_peak_concentration(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="10",
                stable_peak_kg="10",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="20",
                stable_peak_kg="20",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="30",
                stable_peak_kg="30",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="40",
                stable_peak_kg="40",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2026-2027"],
        season_start=date(2027, 1, 1),
        factory_metrics=[
            _metric(
                factory_id=factory_ids["A"],
                total_weight_kg="50",
                stable_peak_kg="50",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
            _metric(
                factory_id=factory_ids["B"],
                total_weight_kg="60",
                stable_peak_kg="60",
                variety_hhi="0.10",
                farm_hhi="0.20",
                subfarm_hhi="0.30",
            ),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        result = await execute_baseline_backtest(session, config=config)

    ridge_row = next(
        row
        for row in result.results
        if row.baseline_name == "ridge_structure" and row.target_season_code == "2026-2027"
    )
    holdout_row = next(
        row
        for row in result.results
        if (
            row.baseline_name == "ridge_structure_factory_holdout"
            and row.factory_id == factory_ids["A"]
        )
    )
    assert ridge_row.status == "evaluated"
    assert "2026-2027" not in ridge_row.training_season_codes
    assert ridge_row.model_metadata["scaler_mean"][0] == 25.0
    assert ridge_row.model_metadata["feature_names"] == [
        "total_weight_kg",
        "variety_hhi",
        "farm_hhi",
        "subfarm_hhi",
    ]
    assert "peak_concentration" not in ridge_row.input_features
    assert factory_ids["A"] not in holdout_row.model_metadata["training_factories"]


@pytest.mark.asyncio
async def test_baseline_backtest_report_generation_failure_does_not_flip_completed_run(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path, minimum_training_rows=4)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        result = await execute_baseline_backtest(
            session,
            config=config,
            season_codes=("2024-2025",),
        )

    occupied = tmp_path / "occupied"
    occupied.write_text("file", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_execution_reports(result, output_dir=occupied)

    async with AsyncSessionMaker() as session:
        persisted = await session.get(BaselineBacktestRun, int(result.run_id))
        assert persisted is not None
        assert persisted.status == "completed"


@pytest.mark.asyncio
async def test_baseline_backtest_failed_run_can_retry_after_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="900", stable_peak_kg="90"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1200", stable_peak_kg="120"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1100", stable_peak_kg="110"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async def fail_once(*args: object, **kwargs: object) -> list[object]:
        raise RuntimeError("synthetic task4 failure")

    monkeypatch.setattr("backend.app.baseline.service._compute_rows", fail_once)
    async with AsyncSessionMaker() as session:
        failed = await execute_baseline_backtest(session, config=config)
    assert failed.status == "failed"

    async with AsyncSessionMaker() as session:
        persisted_failed = (
            await session.scalars(select(BaselineBacktestRun).order_by(BaselineBacktestRun.id))
        ).all()
        assert len(persisted_failed) == 1
        assert persisted_failed[0].status == "failed"
        assert persisted_failed[0].error_message

    monkeypatch.undo()
    async with AsyncSessionMaker() as session:
        completed = await execute_baseline_backtest(session, config=config)

    assert completed.status == "completed"
    async with AsyncSessionMaker() as session:
        runs = (
            await session.scalars(select(BaselineBacktestRun).order_by(BaselineBacktestRun.id))
        ).all()
        assert [run.status for run in runs] == ["failed", "completed"]


@pytest.mark.asyncio
async def test_baseline_backtest_report_run_id_regenerates_reports(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="900", stable_peak_kg="90"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1200", stable_peak_kg="120"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1100", stable_peak_kg="110"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        first = await execute_baseline_backtest(session, config=config)
    async with AsyncSessionMaker() as session:
        loaded = await load_backtest_run_result(session, run_id=int(first.run_id))

    regenerated = write_execution_reports(loaded, output_dir=tmp_path / "reports")
    assert regenerated.report_paths
    assert _all_paths_exist(regenerated.report_paths)


@pytest.mark.postgres_real_commit
@pytest.mark.asyncio
async def test_baseline_backtest_running_conflict_returns_existing_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_postgres()
    season_ids, factory_ids = await _seed_seasons_and_factories()
    await _seed_task3_build_run(
        season_id=season_ids["2024-2025"],
        season_start=date(2025, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1000", stable_peak_kg="100"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="900", stable_peak_kg="90"),
        ],
    )
    await _seed_task3_build_run(
        season_id=season_ids["2025-2026"],
        season_start=date(2026, 1, 1),
        factory_metrics=[
            _metric(factory_id=factory_ids["A"], total_weight_kg="1200", stable_peak_kg="120"),
            _metric(factory_id=factory_ids["B"], total_weight_kg="1100", stable_peak_kg="110"),
        ],
    )
    config_path = tmp_path / "baseline_model.yaml"
    _write_baseline_config(config_path)
    config = load_baseline_config(config_path)

    async with AsyncSessionMaker() as session:
        original_commit = session.commit
        injected_conflict = False

        async def commit_with_conflict() -> None:
            nonlocal injected_conflict
            pending = next(
                (obj for obj in session.new if isinstance(obj, BaselineBacktestRun)),
                None,
            )
            if not injected_conflict and pending is not None:
                injected_conflict = True
                async with AsyncSessionMaker() as conflict_session:
                    conflict_session.add(
                        BaselineBacktestRun(
                            model_version=pending.model_version,
                            config_hash=pending.config_hash,
                            config_snapshot=pending.config_snapshot,
                            source_signature=pending.source_signature,
                            source_build_runs=pending.source_build_runs,
                            evaluation_scheme=pending.evaluation_scheme,
                            status="running",
                            random_seed=pending.random_seed,
                            result_row_count=0,
                        )
                    )
                    await conflict_session.commit()
            await original_commit()

        monkeypatch.setattr(session, "commit", commit_with_conflict)
        result = await execute_baseline_backtest(session, config=config)

    assert result.status in {"running", "skipped"}
    async with AsyncSessionMaker() as session:
        run_count = int(
            await session.scalar(select(func.count()).select_from(BaselineBacktestRun)) or 0
        )
        result_count = int(
            await session.scalar(select(func.count()).select_from(BaselineBacktestResult)) or 0
        )
    assert run_count == 1
    assert result_count == 0
