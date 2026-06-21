from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from backend.app.baseline.json_types import canonical_json_value, canonicalize_result_row
from backend.app.baseline.schemas import BacktestResultRow, SelectedBuildRun
from backend.app.models.analytics import AnalyticsBuildRun, FactorySeasonPeakMetric
from backend.app.models.baseline_backtest import BaselineBacktestResult, BaselineBacktestRun
from backend.app.models.master_data import Factory, Season


def _now() -> datetime:
    return datetime.now(UTC)


async def list_completed_source_build_runs(
    session: AsyncSession,
    *,
    season_codes: tuple[str, ...] | None,
) -> list[SelectedBuildRun]:
    statement: Select[tuple[Any, ...]] = (
        select(
            Season.id,
            Season.code,
            Season.start_date,
            AnalyticsBuildRun.id,
            AnalyticsBuildRun.aggregation_version,
            AnalyticsBuildRun.source_max_raw_id,
            AnalyticsBuildRun.config_hash,
        )
        .join(AnalyticsBuildRun, AnalyticsBuildRun.season_id == Season.id)
        .where(AnalyticsBuildRun.status == "completed")
        .order_by(
            Season.start_date,
            Season.code,
            AnalyticsBuildRun.source_max_raw_id.desc(),
            AnalyticsBuildRun.id.desc(),
        )
    )
    if season_codes is not None:
        statement = statement.where(Season.code.in_(season_codes))
    rows = (await session.execute(statement)).all()
    return [
        SelectedBuildRun(
            season_id=season_id,
            season_code=season_code,
            season_start_date=season_start_date,
            build_run_id=build_run_id,
            aggregation_version=aggregation_version,
            source_max_raw_id=source_max_raw_id,
            config_hash=config_hash,
        )
        for (
            season_id,
            season_code,
            season_start_date,
            build_run_id,
            aggregation_version,
            source_max_raw_id,
            config_hash,
        ) in rows
    ]


async def load_samples_for_build_runs(
    session: AsyncSession,
    *,
    build_run_ids: tuple[int, ...],
) -> list[dict[str, Any]]:
    if not build_run_ids:
        return []
    rows = (
        await session.execute(
            select(
                FactorySeasonPeakMetric.season_id.label("season_id"),
                Season.code.label("season_code"),
                Season.start_date.label("season_start_date"),
                FactorySeasonPeakMetric.factory_id.label("factory_id"),
                Factory.name.label("factory_name"),
                FactorySeasonPeakMetric.build_run_id.label("build_run_id"),
                FactorySeasonPeakMetric.total_weight_kg.label("total_weight_kg"),
                FactorySeasonPeakMetric.stable_median_3d_peak_kg.label("stable_median_3d_peak_kg"),
                FactorySeasonPeakMetric.peak_concentration.label("peak_concentration"),
                FactorySeasonPeakMetric.variety_hhi.label("variety_hhi"),
                FactorySeasonPeakMetric.farm_hhi.label("farm_hhi"),
                FactorySeasonPeakMetric.subfarm_hhi.label("subfarm_hhi"),
                FactorySeasonPeakMetric.single_day_peak_kg.label("single_day_peak_kg"),
            )
            .join(
                AnalyticsBuildRun,
                AnalyticsBuildRun.id == FactorySeasonPeakMetric.build_run_id,
            )
            .join(Season, Season.id == FactorySeasonPeakMetric.season_id)
            .join(Factory, Factory.id == FactorySeasonPeakMetric.factory_id)
            .where(FactorySeasonPeakMetric.build_run_id.in_(build_run_ids))
            .order_by(Season.start_date, Factory.name, Factory.id)
        )
    ).mappings()
    return [dict(row) for row in rows]


async def find_existing_run(
    session: AsyncSession,
    *,
    model_version: str,
    config_hash: str,
    source_signature: str,
    evaluation_scheme: str,
) -> BaselineBacktestRun | None:
    return cast(
        BaselineBacktestRun | None,
        await session.scalar(
            select(BaselineBacktestRun)
            .where(
                BaselineBacktestRun.model_version == model_version,
                BaselineBacktestRun.config_hash == config_hash,
                BaselineBacktestRun.source_signature == source_signature,
                BaselineBacktestRun.evaluation_scheme == evaluation_scheme,
                BaselineBacktestRun.status.in_(("running", "completed")),
            )
            .order_by(BaselineBacktestRun.id.desc())
        ),
    )


async def create_running_run(
    session: AsyncSession,
    *,
    model_version: str,
    config_hash: str,
    config_snapshot: dict[str, Any],
    source_signature: str,
    source_build_runs: tuple[dict[str, Any], ...],
    evaluation_scheme: str,
    random_seed: int,
) -> BaselineBacktestRun:
    run = BaselineBacktestRun(
        model_version=model_version,
        config_hash=config_hash,
        config_snapshot=canonical_json_value(config_snapshot),
        source_signature=source_signature,
        source_build_runs=cast(list[dict[str, Any]], canonical_json_value(list(source_build_runs))),
        evaluation_scheme=evaluation_scheme,
        status="running",
        random_seed=random_seed,
        result_row_count=0,
    )
    session.add(run)
    await session.commit()
    return run


async def insert_result_rows(
    session: AsyncSession,
    *,
    run_id: int,
    rows: list[BacktestResultRow],
) -> None:
    canonical_rows = [canonicalize_result_row(row) for row in rows]
    session.add_all(
        [
            BaselineBacktestResult(
                run_id=run_id,
                baseline_name=row.baseline_name,
                target_season_id=row.target_season_id,
                factory_id=row.factory_id,
                previous_season_id=row.previous_season_id,
                fold_key=row.fold_key,
                status=row.status,
                actual_stable_peak_kg=row.actual_stable_peak_kg,
                predicted_stable_peak_kg=row.predicted_stable_peak_kg,
                absolute_error_kg=row.absolute_error_kg,
                signed_error_kg=row.signed_error_kg,
                ape=row.ape,
                input_features=canonical_json_value(row.input_features),
                training_season_codes=row.training_season_codes,
                model_metadata=canonical_json_value(row.model_metadata),
                exclusion_reason=row.exclusion_reason,
            )
            for row in canonical_rows
        ]
    )


async def mark_run_completed(
    session: AsyncSession,
    *,
    run_id: int,
    result_row_count: int,
) -> None:
    await session.execute(
        update(BaselineBacktestRun)
        .where(BaselineBacktestRun.id == run_id)
        .values(
            status="completed",
            result_row_count=result_row_count,
            finished_at=_now(),
            error_message=None,
        )
    )
    await session.commit()


async def mark_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    error_message: str,
) -> None:
    await session.execute(
        update(BaselineBacktestRun)
        .where(BaselineBacktestRun.id == run_id)
        .values(
            status="failed",
            finished_at=_now(),
            error_message=error_message,
        )
    )
    await session.commit()


async def get_run_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> BaselineBacktestRun | None:
    return cast(
        BaselineBacktestRun | None,
        await session.scalar(
            select(BaselineBacktestRun).where(BaselineBacktestRun.id == run_id)
        ),
    )


async def load_result_rows_for_run(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[BacktestResultRow]:
    previous_season = aliased(Season)
    rows = (
        await session.execute(
            select(
                BaselineBacktestResult.baseline_name,
                BaselineBacktestResult.target_season_id,
                Season.code,
                BaselineBacktestResult.factory_id,
                Factory.name,
                BaselineBacktestResult.previous_season_id,
                previous_season.code,
                BaselineBacktestResult.fold_key,
                BaselineBacktestResult.status,
                BaselineBacktestResult.actual_stable_peak_kg,
                BaselineBacktestResult.predicted_stable_peak_kg,
                BaselineBacktestResult.absolute_error_kg,
                BaselineBacktestResult.signed_error_kg,
                BaselineBacktestResult.ape,
                BaselineBacktestResult.input_features,
                BaselineBacktestResult.training_season_codes,
                BaselineBacktestResult.model_metadata,
                BaselineBacktestResult.exclusion_reason,
            )
            .join(Season, Season.id == BaselineBacktestResult.target_season_id)
            .join(Factory, Factory.id == BaselineBacktestResult.factory_id)
            .outerjoin(
                previous_season,
                previous_season.id == BaselineBacktestResult.previous_season_id,
            )
            .where(BaselineBacktestResult.run_id == run_id)
            .order_by(
                BaselineBacktestResult.baseline_name,
                Season.start_date,
                Factory.name,
                Factory.id,
                BaselineBacktestResult.id,
            )
        )
    ).all()
    return [
        canonicalize_result_row(
            BacktestResultRow(
                baseline_name=baseline_name,
                target_season_id=target_season_id,
                target_season_code=target_season_code,
            factory_id=factory_id,
            factory_name=factory_name,
            previous_season_id=previous_season_id,
            previous_season_code=previous_season_code,
            fold_key=fold_key,
            status=status,
            actual_stable_peak_kg=actual_stable_peak_kg,
            predicted_stable_peak_kg=predicted_stable_peak_kg,
            absolute_error_kg=absolute_error_kg,
            signed_error_kg=signed_error_kg,
            ape=ape,
            input_features=input_features,
            training_season_codes=training_season_codes,
            model_metadata=model_metadata,
                exclusion_reason=exclusion_reason,
            )
        )
        for (
            baseline_name,
            target_season_id,
            target_season_code,
            factory_id,
            factory_name,
            previous_season_id,
            previous_season_code,
            fold_key,
            status,
            actual_stable_peak_kg,
            predicted_stable_peak_kg,
            absolute_error_kg,
            signed_error_kg,
            ape,
            input_features,
            training_season_codes,
            model_metadata,
            exclusion_reason,
        ) in rows
    ]


async def count_runs(session: AsyncSession) -> int:
    value = await session.scalar(select(func.count()).select_from(BaselineBacktestRun))
    return int(value or 0)


async def count_results(session: AsyncSession) -> int:
    value = await session.scalar(select(func.count()).select_from(BaselineBacktestResult))
    return int(value or 0)
