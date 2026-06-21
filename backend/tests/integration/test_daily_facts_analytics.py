from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from backend.app.analytics.config import load_analytics_config
from backend.app.analytics.daily_facts import (
    build_daily_facts_for_season,
    dry_run_daily_facts_for_season,
)
from backend.app.db.session import AsyncSessionMaker
from backend.app.models.analytics import (
    AnalyticsBuildRun,
    FactorySeasonPeakMetric,
    FactReceiptDaily,
)
from backend.app.models.historical_import import FactReceiptRaw, IngestFile
from backend.app.models.master_data import Factory, Grade, Holiday, Season, Variety

pytestmark = pytest.mark.integration


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _write_analytics_rules(path: Path, *, stream_batch_size: int = 2) -> None:
    path.write_text(
        f"""
version: "task3-v1"
analysis_months: [1]
rolling_window_days: 3
stable_peak_method: "median"
mean_peak_method: "mean"
peak_concentration_definition: "stable_median_3d_peak_over_total"
spring_festival_codes:
  - "spring_festival"
unknown_farm_key: "__UNKNOWN_FARM__"
unknown_subfarm_key: "__UNKNOWN_SUBFARM__"
stream_batch_size: {stream_batch_size}
""",
        encoding="utf-8",
    )


async def _seed_master_data() -> tuple[int, int]:
    async with AsyncSessionMaker() as session:
        season = Season(
            code="2025-2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
        )
        factory = Factory(code="factory-a", name="工厂A", region_name="RegionA", active=True)
        variety = Variety(code="DX", name="Dx")
        grade = Grade(code="优果", is_analysis_eligible_default=True)
        session.add_all([season, factory, variety, grade])
        await session.flush()
        session.add_all(
            [
                Holiday(
                    season_id=season.id,
                    code="spring_festival",
                    name="春节",
                    start_date=date(2026, 1, 3),
                    end_date=date(2026, 1, 4),
                    region_name=None,
                    active=True,
                ),
                Holiday(
                    season_id=season.id,
                    code="region_holiday",
                    name="区域节日",
                    start_date=date(2026, 1, 4),
                    end_date=date(2026, 1, 4),
                    region_name="RegionA",
                    active=True,
                ),
            ]
        )
        await session.commit()
        return season.id, factory.id


async def _create_ingest_file(season_id: int, file_sha256: str = "sha-a") -> int:
    async with AsyncSessionMaker() as session:
        ingest = IngestFile(
            file_name="fixture.xls",
            source_path="fixture.xls",
            file_sha256=file_sha256,
            season_id=season_id,
            status="completed",
            sheet_count=1,
            row_count=1,
            inserted_row_count=1,
            suspected_duplicate_count=0,
            config_hash="import-hash",
            config_snapshot={"version": "task2"},
            quality_report={},
        )
        session.add(ingest)
        await session.commit()
        return ingest.id


async def _insert_raw_rows(
    *,
    ingest_file_id: int,
    season_id: int,
    factory_id: int | None,
    variety_id: int | None,
    rows: list[dict[str, object]],
) -> None:
    async with AsyncSessionMaker() as session:
        for offset, row in enumerate(rows, start=1):
            session.add(
                FactReceiptRaw(
                    ingest_file_id=ingest_file_id,
                    season_id=season_id,
                    source_sheet="SheetA",
                    source_row_number=offset,
                    raw_payload={},
                    receipt_date_raw=str(row.get("receipt_date")),
                    link_name_raw=None,
                    farm_raw=row.get("farm_raw"),
                    subfarm_raw=row.get("subfarm_raw"),
                    variety_raw="Dx",
                    grade_raw="优果",
                    weight_kg_raw=str(row.get("weight_kg")),
                    factory_raw="工厂A",
                    receipt_date=row.get("receipt_date"),
                    weight_kg=row.get("weight_kg"),
                    factory_normalized="工厂A" if factory_id is not None else None,
                    variety_normalized="Dx" if variety_id is not None else None,
                    factory_id=factory_id,
                    variety_id=variety_id,
                    grade_id=None,
                    is_date_valid=row.get("receipt_date") is not None,
                    is_weight_valid=row.get("weight_kg") is not None,
                    is_factory_known=factory_id is not None,
                    is_variety_known=variety_id is not None,
                    is_suspected_duplicate=False,
                    is_analysis_eligible=bool(row.get("eligible", True)),
                    exclusion_reasons=[],
                    parse_errors=[],
                    source_row_fingerprint=f"fp-{ingest_file_id}-{offset}-{row.get('weight_kg')}",
                    business_fingerprint=f"business-{ingest_file_id}-{offset}-{row.get('weight_kg')}",
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_daily_fact_tables_constraints_and_indexes_exist(tmp_path: Path) -> None:
    _require_postgres()
    rules_path = tmp_path / "analytics_rules.yaml"
    _write_analytics_rules(rules_path)
    _ = load_analytics_config(rules_path)

    async with AsyncSessionMaker() as session:
        tables = {
            row[0]
            for row in (
                await session.execute(
                    text(
                        """
                        select tablename
                        from pg_tables
                        where schemaname = 'public'
                        and tablename in (
                            'analytics_build_run',
                            'fact_receipt_daily',
                            'factory_season_peak_metric'
                        )
                        """
                    )
                )
            ).all()
        }
        assert {
            "analytics_build_run",
            "fact_receipt_daily",
            "factory_season_peak_metric",
        } == tables


@pytest.mark.asyncio
async def test_build_daily_facts_success_skips_same_cutoff_and_creates_new_run_for_new_raw(
    tmp_path: Path,
) -> None:
    _require_postgres()
    season_id, factory_id = await _seed_master_data()
    ingest_id = await _create_ingest_file(season_id)
    await _insert_raw_rows(
        ingest_file_id=ingest_id,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=1,
        rows=[
            {
                "receipt_date": date(2026, 1, 2),
                "weight_kg": Decimal("10"),
                "farm_raw": " Farm A ",
                "subfarm_raw": "Block A",
                "eligible": True,
            },
            {
                "receipt_date": date(2026, 1, 3),
                "weight_kg": Decimal("30"),
                "farm_raw": None,
                "subfarm_raw": None,
                "eligible": True,
            },
            {
                "receipt_date": date(2026, 1, 4),
                "weight_kg": Decimal("50"),
                "farm_raw": "Farm A",
                "subfarm_raw": "Block A",
                "eligible": False,
            },
            {
                "receipt_date": date(2026, 1, 4),
                "weight_kg": Decimal("20"),
                "farm_raw": "Farm A",
                "subfarm_raw": None,
                "eligible": True,
            },
        ],
    )
    rules_path = tmp_path / "analytics_rules.yaml"
    _write_analytics_rules(rules_path, stream_batch_size=2)
    config = load_analytics_config(rules_path)

    async with AsyncSessionMaker() as session:
        dry_run = await dry_run_daily_facts_for_season(session, "2025-2026", config)
        first = await build_daily_facts_for_season(session, "2025-2026", config)
        skipped = await build_daily_facts_for_season(session, "2025-2026", config)

        daily_rows = (
            await session.scalars(
                select(FactReceiptDaily).order_by(
                    FactReceiptDaily.receipt_date,
                    FactReceiptDaily.id,
                )
            )
        ).all()
        metric = await session.scalar(select(FactorySeasonPeakMetric))
        build_runs = (
            await session.scalars(select(AnalyticsBuildRun).order_by(AnalyticsBuildRun.id))
        ).all()

    assert dry_run.status == "dry_run"
    assert dry_run.source_eligible_row_count == 3
    assert dry_run.daily_fact_row_count == 3
    assert first.status == "completed"
    assert first.source_eligible_row_count == 3
    assert first.source_eligible_weight_kg == Decimal("60.000000")
    assert first.daily_fact_row_count == 3
    assert skipped.status == "skipped"
    assert len(build_runs) == 1
    assert len(daily_rows) == 3
    assert daily_rows[1].holiday_codes == ["spring_festival"]
    assert daily_rows[1].is_spring_festival is True
    assert sorted(daily_rows[2].holiday_codes) == ["region_holiday", "spring_festival"]
    assert metric is not None
    assert metric.total_weight_kg == Decimal("60.000000")
    assert metric.single_day_peak_kg == Decimal("30.000000")
    assert metric.single_day_peak_date == date(2026, 1, 3)
    assert metric.stable_median_3d_peak_kg == Decimal("20.000000")
    assert metric.stable_median_3d_peak_date == date(2026, 1, 3)
    assert metric.mean_3d_peak_kg == Decimal("20.000000")
    assert metric.mean_3d_peak_date == date(2026, 1, 3)
    assert metric.peak_concentration == Decimal("0.3333333333")
    assert metric.variety_hhi == Decimal("1.0000000000")
    assert metric.unknown_farm_weight_share == Decimal("0.5000000000")
    assert metric.unknown_subfarm_weight_share == Decimal("0.8333333333")

    second_ingest = await _create_ingest_file(season_id, file_sha256="sha-b")
    await _insert_raw_rows(
        ingest_file_id=second_ingest,
        season_id=season_id,
        factory_id=factory_id,
        variety_id=1,
        rows=[
            {
                "receipt_date": date(2026, 1, 5),
                "weight_kg": Decimal("5"),
                "farm_raw": "Farm A",
                "subfarm_raw": "Block B",
                "eligible": True,
            }
        ],
    )

    async with AsyncSessionMaker() as session:
        rebuilt = await build_daily_facts_for_season(session, "2025-2026", config)
        all_runs = (
            await session.scalars(select(AnalyticsBuildRun).order_by(AnalyticsBuildRun.id))
        ).all()
        latest_metric = (
            await session.scalars(
                select(FactorySeasonPeakMetric).order_by(FactorySeasonPeakMetric.id)
            )
        ).all()[-1]

    assert rebuilt.status == "completed"
    assert len(all_runs) == 2
    assert all_runs[1].source_max_raw_id > all_runs[0].source_max_raw_id
    assert latest_metric.total_weight_kg == Decimal("65.000000")


@pytest.mark.asyncio
async def test_build_daily_facts_fails_on_consistency_error_and_can_retry(tmp_path: Path) -> None:
    _require_postgres()
    season_id, _factory_id = await _seed_master_data()
    ingest_id = await _create_ingest_file(season_id)
    await _insert_raw_rows(
        ingest_file_id=ingest_id,
        season_id=season_id,
        factory_id=None,
        variety_id=1,
        rows=[
            {
                "receipt_date": date(2026, 1, 2),
                "weight_kg": Decimal("10"),
                "farm_raw": "Farm A",
                "subfarm_raw": "Block A",
                "eligible": True,
            }
        ],
    )
    rules_path = tmp_path / "analytics_rules.yaml"
    _write_analytics_rules(rules_path)
    config = load_analytics_config(rules_path)

    async with AsyncSessionMaker() as session:
        failed = await build_daily_facts_for_season(session, "2025-2026", config)
        build_runs = (
            await session.scalars(select(AnalyticsBuildRun).order_by(AnalyticsBuildRun.id))
        ).all()
        assert failed.status == "failed"
        assert len(build_runs) == 1
        assert build_runs[0].status == "failed"
        assert build_runs[0].error_message
        assert await session.scalar(select(func.count()).select_from(FactReceiptDaily)) == 0

    async with AsyncSessionMaker() as session:
        bad_row = (await session.scalars(select(FactReceiptRaw))).one()
        bad_row.factory_id = 1
        bad_row.factory_normalized = "工厂A"
        bad_row.is_factory_known = True
        await session.commit()

    async with AsyncSessionMaker() as session:
        retried = await build_daily_facts_for_season(session, "2025-2026", config)
        build_runs = (
            await session.scalars(select(AnalyticsBuildRun).order_by(AnalyticsBuildRun.id))
        ).all()
        metrics = (await session.scalars(select(FactorySeasonPeakMetric))).all()

    assert retried.status == "completed"
    assert len(build_runs) == 2
    assert build_runs[0].status == "failed"
    assert build_runs[1].status == "completed"
    assert len(metrics) == 1
