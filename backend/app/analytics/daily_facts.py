from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast

from sqlalchemy import Select, and_, extract, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.analytics.config import AnalyticsConfig
from backend.app.analytics.peak_metrics import (
    FactoryPeakMetrics,
    build_analysis_calendar,
    build_dense_daily_series,
    compute_factory_peak_metrics,
)
from backend.app.etl.history.normalizer import normalize_text
from backend.app.etl.history.quality import decimal_json
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.historical_import import FactReceiptRaw
from backend.app.models.master_data import Factory, Holiday, Season

_KG_QUANT = Decimal("0.000001")


def _quantize_kg(value: Decimal) -> Decimal:
    return value.quantize(_KG_QUANT, rounding=ROUND_HALF_UP)


def _now() -> datetime:
    return datetime.now(UTC)


def _sanitize_error_message(message: str) -> str:
    return " ".join(str(message).replace("\r", " ").replace("\n", " ").split())[:500]


class DailyFactsBuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class DailyFactKey:
    receipt_date: date
    factory_id: int
    farm_key: str
    subfarm_key: str
    variety_id: int


@dataclass
class DailyFactAggregate:
    weight_kg: Decimal = Decimal("0")
    source_row_count: int = 0


@dataclass(frozen=True)
class PreparedDailyFact:
    receipt_date: date
    factory_id: int
    farm_key: str
    subfarm_key: str
    variety_id: int
    weight_kg: Decimal
    source_row_count: int
    holiday_codes: list[str]
    is_spring_festival: bool


@dataclass(frozen=True)
class PreparedFactoryMetric:
    factory_id: int
    metrics: FactoryPeakMetrics


@dataclass(frozen=True)
class FactoryMetricSummary:
    factory_id: int
    total_weight_kg: Decimal
    single_day_peak_kg: Decimal
    single_day_peak_date: date
    stable_median_3d_peak_kg: Decimal
    stable_median_3d_peak_date: date | None
    mean_3d_peak_kg: Decimal
    mean_3d_peak_date: date | None
    peak_concentration: Decimal
    variety_hhi: Decimal
    farm_hhi: Decimal
    subfarm_hhi: Decimal
    unknown_farm_weight_share: Decimal
    unknown_subfarm_weight_share: Decimal
    spring_festival_day_count: int


@dataclass(frozen=True)
class DailyFactsComputation:
    season: Season
    aggregation_version: str
    source_max_raw_id: int
    source_eligible_row_count: int
    source_eligible_weight_kg: Decimal
    daily_facts: list[PreparedDailyFact]
    peak_metrics: list[PreparedFactoryMetric]
    factory_summaries: list[FactoryMetricSummary]

    @property
    def daily_fact_row_count(self) -> int:
        return len(self.daily_facts)

    @property
    def factory_count(self) -> int:
        return len(self.factory_summaries)


@dataclass(frozen=True)
class DailyFactsBuildResult:
    status: str
    season_code: str
    aggregation_version: str
    source_max_raw_id: int
    config_hash: str
    source_eligible_row_count: int
    source_eligible_weight_kg: Decimal
    daily_fact_row_count: int
    factory_count: int
    metric_row_count: int
    build_run_id: int | None = None
    error_message: str | None = None
    factory_summaries: tuple[FactoryMetricSummary, ...] = ()


def _result_from_computation(
    *,
    status: str,
    config: AnalyticsConfig,
    computation: DailyFactsComputation,
    build_run_id: int | None = None,
    error_message: str | None = None,
) -> DailyFactsBuildResult:
    return DailyFactsBuildResult(
        status=status,
        season_code=computation.season.code,
        aggregation_version=computation.aggregation_version,
        source_max_raw_id=computation.source_max_raw_id,
        config_hash=config.config_hash,
        source_eligible_row_count=computation.source_eligible_row_count,
        source_eligible_weight_kg=computation.source_eligible_weight_kg,
        daily_fact_row_count=computation.daily_fact_row_count,
        factory_count=computation.factory_count,
        metric_row_count=len(computation.peak_metrics),
        build_run_id=build_run_id,
        error_message=error_message,
        factory_summaries=tuple(computation.factory_summaries),
    )


def _result_from_build_run(
    *,
    status: str,
    config: AnalyticsConfig,
    season_code: str,
    build_run: AnalyticsBuildRun,
    metric_row_count: int,
    factory_summaries: tuple[FactoryMetricSummary, ...] = (),
) -> DailyFactsBuildResult:
    return DailyFactsBuildResult(
        status=status,
        season_code=season_code,
        aggregation_version=build_run.aggregation_version,
        source_max_raw_id=build_run.source_max_raw_id,
        config_hash=config.config_hash,
        source_eligible_row_count=build_run.source_eligible_row_count,
        source_eligible_weight_kg=build_run.source_eligible_weight_kg,
        daily_fact_row_count=build_run.daily_fact_row_count,
        factory_count=metric_row_count,
        metric_row_count=metric_row_count,
        build_run_id=build_run.id,
        error_message=build_run.error_message,
        factory_summaries=factory_summaries,
    )


async def _season_by_code(session: AsyncSession, season_code: str) -> Season:
    season = await session.scalar(select(Season).where(Season.code == season_code))
    if season is None:
        raise DailyFactsBuildError(f"Missing season code: {season_code}")
    return season


async def _current_source_cutoff(session: AsyncSession, *, season_id: int) -> int:
    max_raw_id = await session.scalar(
        select(func.max(FactReceiptRaw.id)).where(FactReceiptRaw.season_id == season_id)
    )
    return int(max_raw_id or 0)


def _analysis_month_filter(statement: Select[Any], analysis_months: tuple[int, ...]) -> Select[Any]:
    return statement.where(extract("month", FactReceiptRaw.receipt_date).in_(analysis_months))


async def _ensure_consistent_source_rows(
    session: AsyncSession,
    *,
    season_id: int,
    source_max_raw_id: int,
    analysis_months: tuple[int, ...],
) -> None:
    inconsistent_rows = (
        await session.execute(
            select(
                FactReceiptRaw.id,
                FactReceiptRaw.factory_id,
                FactReceiptRaw.variety_id,
                FactReceiptRaw.receipt_date,
                FactReceiptRaw.weight_kg,
            )
            .where(
                FactReceiptRaw.season_id == season_id,
                FactReceiptRaw.id <= source_max_raw_id,
                FactReceiptRaw.is_analysis_eligible.is_(True),
                or_(
                    FactReceiptRaw.receipt_date.is_(None),
                    and_(
                        extract("month", FactReceiptRaw.receipt_date).in_(analysis_months),
                        or_(
                            FactReceiptRaw.factory_id.is_(None),
                            FactReceiptRaw.variety_id.is_(None),
                            FactReceiptRaw.weight_kg.is_(None),
                            FactReceiptRaw.weight_kg <= 0,
                        ),
                    ),
                ),
            )
            .order_by(FactReceiptRaw.id)
            .limit(5)
        )
    ).all()
    if inconsistent_rows:
        sample_ids = ", ".join(str(row.id) for row in inconsistent_rows)
        raise DailyFactsBuildError(
            "Analysis-eligible raw rows are inconsistent with Task 3 build requirements: "
            f"raw_ids=[{sample_ids}]"
        )


async def _load_holidays(
    session: AsyncSession,
    *,
    season_id: int,
) -> list[Holiday]:
    return list(
        (
            await session.scalars(
            select(Holiday)
            .where(Holiday.season_id == season_id, Holiday.active.is_(True))
            .order_by(Holiday.start_date, Holiday.id)
        )
        ).all()
    )


async def _load_factory_summaries_for_build_run(
    session: AsyncSession,
    *,
    build_run_id: int,
) -> tuple[FactoryMetricSummary, ...]:
    rows = (
        await session.scalars(
            select(FactorySeasonPeakMetric)
            .where(FactorySeasonPeakMetric.build_run_id == build_run_id)
            .order_by(FactorySeasonPeakMetric.factory_id)
        )
    ).all()
    return tuple(
        FactoryMetricSummary(
            factory_id=row.factory_id,
            total_weight_kg=row.total_weight_kg,
            single_day_peak_kg=row.single_day_peak_kg,
            single_day_peak_date=row.single_day_peak_date,
            stable_median_3d_peak_kg=row.stable_median_3d_peak_kg,
            stable_median_3d_peak_date=row.stable_median_3d_peak_date,
            mean_3d_peak_kg=row.mean_3d_peak_kg,
            mean_3d_peak_date=row.mean_3d_peak_date,
            peak_concentration=row.peak_concentration,
            variety_hhi=row.variety_hhi,
            farm_hhi=row.farm_hhi,
            subfarm_hhi=row.subfarm_hhi,
            unknown_farm_weight_share=row.unknown_farm_weight_share,
            unknown_subfarm_weight_share=row.unknown_subfarm_weight_share,
            spring_festival_day_count=row.spring_festival_day_count,
        )
        for row in rows
    )


def _holiday_codes_by_factory_date(
    *,
    factory_regions: dict[int, str | None],
    holidays: list[Holiday],
) -> dict[int, dict[date, tuple[str, ...]]]:
    codes_by_factory_date: dict[int, dict[date, set[str]]] = {
        factory_id: defaultdict(set) for factory_id in factory_regions
    }
    for holiday in holidays:
        for factory_id, region_name in factory_regions.items():
            if holiday.region_name is not None and holiday.region_name != region_name:
                continue
            current = holiday.start_date
            while current <= holiday.end_date:
                codes_by_factory_date[factory_id][current].add(holiday.code)
                current += timedelta(days=1)
    return {
        factory_id: {
            holiday_date: tuple(sorted(codes))
            for holiday_date, codes in by_date.items()
        }
        for factory_id, by_date in codes_by_factory_date.items()
    }


async def _compute_daily_facts(
    session: AsyncSession,
    *,
    season: Season,
    config: AnalyticsConfig,
    source_max_raw_id: int,
) -> DailyFactsComputation:
    await _ensure_consistent_source_rows(
        session,
        season_id=season.id,
        source_max_raw_id=source_max_raw_id,
        analysis_months=config.rules.analysis_months,
    )

    calendar_dates = build_analysis_calendar(
        start_date=season.start_date,
        end_date=season.end_date,
        analysis_months=config.rules.analysis_months,
    )

    if not calendar_dates:
        return DailyFactsComputation(
            season=season,
            aggregation_version=config.rules.version,
            source_max_raw_id=source_max_raw_id,
            source_eligible_row_count=0,
            source_eligible_weight_kg=Decimal("0.000000"),
            daily_facts=[],
            peak_metrics=[],
            factory_summaries=[],
        )

    statement = (
        select(
            FactReceiptRaw.receipt_date,
            FactReceiptRaw.weight_kg,
            FactReceiptRaw.factory_id,
            FactReceiptRaw.variety_id,
            FactReceiptRaw.farm_raw,
            FactReceiptRaw.subfarm_raw,
            Factory.region_name,
        )
        .join(Factory, Factory.id == FactReceiptRaw.factory_id)
        .where(
            FactReceiptRaw.season_id == season.id,
            FactReceiptRaw.id <= source_max_raw_id,
            FactReceiptRaw.is_analysis_eligible.is_(True),
        )
        .order_by(
            FactReceiptRaw.factory_id,
            FactReceiptRaw.receipt_date,
            FactReceiptRaw.variety_id,
            FactReceiptRaw.id,
        )
        .execution_options(yield_per=config.rules.stream_batch_size)
    )
    statement = _analysis_month_filter(statement, config.rules.analysis_months)

    source_eligible_row_count = 0
    source_eligible_weight_kg = Decimal("0")
    daily_aggregates: dict[DailyFactKey, DailyFactAggregate] = {}
    factory_day_weights: dict[tuple[int, date], Decimal] = defaultdict(lambda: Decimal("0"))
    variety_weights_by_factory: dict[int, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    farm_weights_by_factory: dict[int, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    subfarm_weights_by_factory: dict[int, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(lambda: Decimal("0"))
    )
    factory_regions: dict[int, str | None] = {}

    stream = await session.stream(statement)
    async for row in stream:
        receipt_date, weight_kg, factory_id, variety_id, farm_raw, subfarm_raw, region_name = row
        if receipt_date is None or weight_kg is None or factory_id is None or variety_id is None:
            raise DailyFactsBuildError("Unexpected null value after consistency validation")
        if weight_kg <= 0:
            raise DailyFactsBuildError(
                "Unexpected non-positive weight after consistency validation"
            )

        normalized_weight = _quantize_kg(weight_kg)
        farm_key = normalize_text(farm_raw) or config.rules.unknown_farm_key
        subfarm_key = normalize_text(subfarm_raw) or config.rules.unknown_subfarm_key
        daily_key = DailyFactKey(
            receipt_date=receipt_date,
            factory_id=factory_id,
            farm_key=farm_key,
            subfarm_key=subfarm_key,
            variety_id=variety_id,
        )
        aggregate = daily_aggregates.setdefault(daily_key, DailyFactAggregate())
        aggregate.weight_kg += normalized_weight
        aggregate.source_row_count += 1

        source_eligible_row_count += 1
        source_eligible_weight_kg += normalized_weight
        factory_day_weights[(factory_id, receipt_date)] += normalized_weight
        variety_weights_by_factory[factory_id][str(variety_id)] += normalized_weight
        farm_weights_by_factory[factory_id][farm_key] += normalized_weight
        subfarm_weights_by_factory[factory_id][subfarm_key] += normalized_weight
        factory_regions.setdefault(factory_id, region_name)

    holidays = await _load_holidays(session, season_id=season.id)
    holiday_codes = _holiday_codes_by_factory_date(
        factory_regions=factory_regions,
        holidays=holidays,
    )
    spring_codes = set(config.rules.spring_festival_codes)

    prepared_daily_facts: list[PreparedDailyFact] = []
    for key in sorted(
        daily_aggregates,
        key=lambda item: (
            item.factory_id,
            item.receipt_date,
            item.variety_id,
            item.farm_key,
            item.subfarm_key,
        ),
    ):
        aggregate = daily_aggregates[key]
        codes = list(holiday_codes.get(key.factory_id, {}).get(key.receipt_date, ()))
        prepared_daily_facts.append(
            PreparedDailyFact(
                receipt_date=key.receipt_date,
                factory_id=key.factory_id,
                farm_key=key.farm_key,
                subfarm_key=key.subfarm_key,
                variety_id=key.variety_id,
                weight_kg=_quantize_kg(aggregate.weight_kg),
                source_row_count=aggregate.source_row_count,
                holiday_codes=codes,
                is_spring_festival=bool(spring_codes.intersection(codes)),
            )
        )

    prepared_metrics: list[PreparedFactoryMetric] = []
    factory_summaries: list[FactoryMetricSummary] = []
    for factory_id in sorted(factory_regions):
        total_weight = _quantize_kg(
            sum(
                (
                    weight
                    for (current_factory_id, _current_date), weight in factory_day_weights.items()
                    if current_factory_id == factory_id
                ),
                Decimal("0"),
            )
        )
        if total_weight <= 0:
            continue
        dense_series = build_dense_daily_series(
            calendar_dates=calendar_dates,
            weight_by_date={
                current_date: _quantize_kg(weight)
                for (current_factory_id, current_date), weight in factory_day_weights.items()
                if current_factory_id == factory_id
            },
            holiday_codes_by_date=holiday_codes.get(factory_id, {}),
            spring_festival_codes=config.rules.spring_festival_codes,
        )
        metrics = compute_factory_peak_metrics(
            dense_series=dense_series,
            rules=config.rules,
            total_weight_kg=total_weight,
            variety_weights=dict(variety_weights_by_factory[factory_id]),
            farm_weights=dict(farm_weights_by_factory[factory_id]),
            subfarm_weights=dict(subfarm_weights_by_factory[factory_id]),
        )
        prepared_metrics.append(PreparedFactoryMetric(factory_id=factory_id, metrics=metrics))
        factory_summaries.append(
            FactoryMetricSummary(
                factory_id=factory_id,
                total_weight_kg=metrics.total_weight_kg,
                single_day_peak_kg=metrics.single_day_peak_kg,
                single_day_peak_date=metrics.single_day_peak_date,
                stable_median_3d_peak_kg=metrics.stable_median_3d_peak_kg,
                stable_median_3d_peak_date=metrics.stable_median_3d_peak_date,
                mean_3d_peak_kg=metrics.mean_3d_peak_kg,
                mean_3d_peak_date=metrics.mean_3d_peak_date,
                peak_concentration=metrics.peak_concentration,
                variety_hhi=metrics.variety_hhi,
                farm_hhi=metrics.farm_hhi,
                subfarm_hhi=metrics.subfarm_hhi,
                unknown_farm_weight_share=metrics.unknown_farm_weight_share,
                unknown_subfarm_weight_share=metrics.unknown_subfarm_weight_share,
                spring_festival_day_count=metrics.spring_festival_day_count,
            )
        )

    return DailyFactsComputation(
        season=season,
        aggregation_version=config.rules.version,
        source_max_raw_id=source_max_raw_id,
        source_eligible_row_count=source_eligible_row_count,
        source_eligible_weight_kg=_quantize_kg(source_eligible_weight_kg),
        daily_facts=prepared_daily_facts,
        peak_metrics=prepared_metrics,
        factory_summaries=factory_summaries,
    )


async def dry_run_daily_facts_for_season(
    session: AsyncSession,
    season_code: str,
    config: AnalyticsConfig,
) -> DailyFactsBuildResult:
    season = await _season_by_code(session, season_code)
    source_max_raw_id = await _current_source_cutoff(session, season_id=season.id)
    computation = await _compute_daily_facts(
        session,
        season=season,
        config=config,
        source_max_raw_id=source_max_raw_id,
    )
    return _result_from_computation(status="dry_run", config=config, computation=computation)


async def _existing_build_run(
    session: AsyncSession,
    *,
    season_id: int,
    aggregation_version: str,
    source_max_raw_id: int,
    config_hash: str,
) -> AnalyticsBuildRun | None:
    return cast(
        AnalyticsBuildRun | None,
        await session.scalar(
            select(AnalyticsBuildRun)
            .where(
                AnalyticsBuildRun.season_id == season_id,
                AnalyticsBuildRun.aggregation_version == aggregation_version,
                AnalyticsBuildRun.source_max_raw_id == source_max_raw_id,
                AnalyticsBuildRun.config_hash == config_hash,
                AnalyticsBuildRun.status.in_(("running", "completed")),
            )
            .order_by(AnalyticsBuildRun.id.desc())
        ),
    )


async def _mark_build_failed(
    session: AsyncSession,
    *,
    build_run_id: int,
    source_eligible_row_count: int,
    source_eligible_weight_kg: Decimal,
    error_message: str,
) -> None:
    await session.execute(
        update(AnalyticsBuildRun)
        .where(AnalyticsBuildRun.id == build_run_id)
        .values(
            source_eligible_row_count=source_eligible_row_count,
            source_eligible_weight_kg=source_eligible_weight_kg,
            daily_fact_row_count=0,
            status="failed",
            finished_at=_now(),
            error_message=error_message,
        )
    )
    await session.commit()


async def build_daily_facts_for_season(
    session: AsyncSession,
    season_code: str,
    config: AnalyticsConfig,
) -> DailyFactsBuildResult:
    season = await _season_by_code(session, season_code)
    season_id_value = season.id
    season_code_value = season.code
    source_max_raw_id = await _current_source_cutoff(session, season_id=season_id_value)
    existing = await _existing_build_run(
        session,
        season_id=season_id_value,
        aggregation_version=config.rules.version,
        source_max_raw_id=source_max_raw_id,
        config_hash=config.config_hash,
    )
    if existing is not None:
        metric_row_count = int(
            await session.scalar(
                select(func.count())
                .select_from(FactorySeasonPeakMetric)
                .where(FactorySeasonPeakMetric.build_run_id == existing.id)
            )
            or 0
        )
        factory_summaries = await _load_factory_summaries_for_build_run(
            session,
            build_run_id=existing.id,
        )
        status = "skipped" if existing.status == "completed" else "running"
        return _result_from_build_run(
            status=status,
            config=config,
            season_code=season_code_value,
            build_run=existing,
            metric_row_count=metric_row_count,
            factory_summaries=factory_summaries,
        )

    build_run = AnalyticsBuildRun(
        season_id=season_id_value,
        aggregation_version=config.rules.version,
        source_max_raw_id=source_max_raw_id,
        config_hash=config.config_hash,
        config_snapshot=decimal_json(config.snapshot),
        status="running",
        source_eligible_row_count=0,
        source_eligible_weight_kg=Decimal("0"),
        daily_fact_row_count=0,
    )
    session.add(build_run)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        current = await _existing_build_run(
            session,
            season_id=season_id_value,
            aggregation_version=config.rules.version,
            source_max_raw_id=source_max_raw_id,
            config_hash=config.config_hash,
        )
        if current is None:
            raise
        metric_row_count = int(
            await session.scalar(
                select(func.count())
                .select_from(FactorySeasonPeakMetric)
                .where(FactorySeasonPeakMetric.build_run_id == current.id)
            )
            or 0
        )
        factory_summaries = await _load_factory_summaries_for_build_run(
            session,
            build_run_id=current.id,
        )
        status = "skipped" if current.status == "completed" else "running"
        return _result_from_build_run(
            status=status,
            config=config,
            season_code=season_code_value,
            build_run=current,
            metric_row_count=metric_row_count,
            factory_summaries=factory_summaries,
        )
    build_run_id = build_run.id

    computation: DailyFactsComputation | None = None
    try:
        computation = await _compute_daily_facts(
            session,
            season=season,
            config=config,
            source_max_raw_id=source_max_raw_id,
        )

        session.add_all(
            [
                FactReceiptDaily(
                    build_run_id=build_run_id,
                    season_id=season_id_value,
                    receipt_date=item.receipt_date,
                    factory_id=item.factory_id,
                    farm_key=item.farm_key,
                    subfarm_key=item.subfarm_key,
                    variety_id=item.variety_id,
                    weight_kg=item.weight_kg,
                    source_row_count=item.source_row_count,
                    holiday_codes=item.holiday_codes,
                    is_spring_festival=item.is_spring_festival,
                )
                for item in computation.daily_facts
            ]
        )
        session.add_all(
            [
                FactorySeasonPeakMetric(
                    build_run_id=build_run_id,
                    season_id=season_id_value,
                    factory_id=item.factory_id,
                    analysis_start_date=item.metrics.analysis_start_date,
                    analysis_end_date=item.metrics.analysis_end_date,
                    calendar_day_count=item.metrics.calendar_day_count,
                    observed_day_count=item.metrics.observed_day_count,
                    total_weight_kg=item.metrics.total_weight_kg,
                    single_day_peak_kg=item.metrics.single_day_peak_kg,
                    single_day_peak_date=item.metrics.single_day_peak_date,
                    stable_median_3d_peak_kg=item.metrics.stable_median_3d_peak_kg,
                    stable_median_3d_peak_date=item.metrics.stable_median_3d_peak_date,
                    mean_3d_peak_kg=item.metrics.mean_3d_peak_kg,
                    mean_3d_peak_date=item.metrics.mean_3d_peak_date,
                    peak_concentration=item.metrics.peak_concentration,
                    variety_hhi=item.metrics.variety_hhi,
                    farm_hhi=item.metrics.farm_hhi,
                    subfarm_hhi=item.metrics.subfarm_hhi,
                    unknown_farm_weight_share=item.metrics.unknown_farm_weight_share,
                    unknown_subfarm_weight_share=item.metrics.unknown_subfarm_weight_share,
                    spring_festival_day_count=item.metrics.spring_festival_day_count,
                )
                for item in computation.peak_metrics
            ]
        )
        build_run.source_eligible_row_count = computation.source_eligible_row_count
        build_run.source_eligible_weight_kg = computation.source_eligible_weight_kg
        build_run.daily_fact_row_count = computation.daily_fact_row_count
        build_run.status = "completed"
        build_run.finished_at = _now()
        build_run.error_message = None
        await session.commit()
        return _result_from_computation(
            status="completed",
            config=config,
            computation=computation,
            build_run_id=build_run_id,
        )
    except Exception as exc:
        error_message = _sanitize_error_message(str(exc))
        failed_row_count = computation.source_eligible_row_count if computation is not None else 0
        failed_weight_kg = (
            computation.source_eligible_weight_kg if computation is not None else Decimal("0")
        )
        await session.rollback()
        await _mark_build_failed(
            session,
            build_run_id=build_run_id,
            source_eligible_row_count=failed_row_count,
            source_eligible_weight_kg=failed_weight_kg,
            error_message=error_message,
        )
        if computation is not None:
            return _result_from_computation(
                status="failed",
                config=config,
                computation=computation,
                build_run_id=build_run_id,
                error_message=error_message,
            )
        return DailyFactsBuildResult(
            status="failed",
            season_code=season_code_value,
            aggregation_version=config.rules.version,
            source_max_raw_id=source_max_raw_id,
            config_hash=config.config_hash,
            source_eligible_row_count=failed_row_count,
            source_eligible_weight_kg=failed_weight_kg,
            daily_fact_row_count=0,
            factory_count=0,
            metric_row_count=0,
            build_run_id=build_run_id,
            error_message=error_message,
        )
