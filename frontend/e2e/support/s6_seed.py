"""SYNTHETIC=true R2 seed derived from S5 literals, no production data access.

Literal saved curves are inserted into a fresh isolated SQLite database before
serving. Real repositories, canonical reload, S1/S2 services and HTTP routers run
unchanged. No model inference, actual reader or monkeypatched business service.
"""

import importlib
import tempfile
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.actual_harvest_import.api_auth import (
    ActualHarvestActorContext,
    get_actual_harvest_actor,
)
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.api.forecast_intelligence_decision import router as decision_router
from backend.app.api.forecast_intelligence_read import router as read_router
from backend.app.area_yield.data import digest
from backend.app.db.session import get_db_session
from backend.app.forecast_intelligence.hierarchy import COMPANY_ID, build_hierarchy
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository, source_mapping
from backend.app.forecast_intelligence.read_schemas import ForecastReadQuery
from backend.app.forecast_intelligence.read_service import ForecastIntelligenceReadService
from backend.app.forecast_intelligence.reconciliation import reconcile
from backend.app.forecast_intelligence.schemas import CreateHierarchicalRun
from backend.app.forecast_quality.operational_peak import (
    DailyForecast,
    OperationalPeakForecastResult,
    PeakWindowForecast,
    canonical_result_hash,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
)

POINT = (
    "80",
    "100",
    "120",
    "160",
    "200",
    "180",
    "140",
    "100",
    "80",
    "120",
    "160",
    "140",
    "100",
    "80",
    "60",
)
STATE = {"identities": [], "read_dml_count": 0}


def tables(connection):
    with Operations.context(MigrationContext.configure(connection)):
        for module in ("0035_operational_peak_forecast_runs", "0040_hierarchical_forecast"):
            importlib.import_module("backend.alembic.versions." + module).upgrade()


def saved_fixture(base: str):
    # All values are predeclared fixtures; this is not a forecast generator.
    rows = tuple(
        DailyForecast(date(2026, 1, i + 2), Decimal(v), Decimal(v), i + 185, 26)
        for i, v in enumerate(POINT)
    )
    w7 = PeakWindowForecast(
        7,
        "COMPUTABLE_FULL_WINDOW",
        date(2026, 1, 2),
        date(2026, 1, 8),
        Decimal("980"),
        date(2026, 1, 6),
        Decimal("200"),
        7,
    )
    w15 = PeakWindowForecast(
        15,
        "COMPUTABLE_FULL_WINDOW",
        date(2026, 1, 2),
        date(2026, 1, 16),
        Decimal("1820"),
        date(2026, 1, 6),
        Decimal("200"),
        15,
    )
    result = OperationalPeakForecastResult(
        base,
        base,
        Decimal("1"),
        "SYNTHETIC_TEST_ONLY",
        "2025-2026",
        date(2026, 1, 1),
        date(2025, 7, 1),
        date(2026, 4, 15),
        rows,
        w7,
        w15,
        replace(w15, window_days=None, status="COMPUTABLE_REMAINING_WINDOW"),
    )
    return replace(result, result_hash=canonical_result_hash(result))


@asynccontextmanager
async def lifespan(app):
    with tempfile.TemporaryDirectory(prefix="dashboard-synthetic-") as directory:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{Path(directory) / 'saved.db'}",
            connect_args={"autocommit": False},
        )
        async with engine.begin() as connection:
            await connection.run_sync(tables)
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        registry = {
            "bases": [
                {
                    "base_id": f"SYNTHETIC_BASE_{i}",
                    "canonical_base_name": f"SYNTHETIC_BASE_{i}",
                    "region_scope": "SYNTHETIC_REGION",
                }
                for i in (1, 2)
            ]
        }
        authority = digest(registry)
        async with factory() as session, session.begin():
            repository = OperationalPeakRunRepository(session)
            saved = []
            for base in registry["bases"]:
                result = saved_fixture(base["base_id"])
                snapshot = {
                    "base_id": result.base_id,
                    "target_season": result.target_season,
                    "origin_date": result.origin_date.isoformat(),
                }
                saved.append(
                    await repository.save(
                        snapshot,
                        result,
                        execution_hash(snapshot, authority, result.policy_version),
                        authority,
                        None,
                    )
                )
            identities = [
                ForecastReadQuery(
                    source_kind="OPERATIONAL_PEAK",
                    forecast_family="OPERATIONAL_PEAK_FORECAST_RUN_V1",
                    run_id=s.run.run_id,
                    hierarchy_level="BASE",
                    entity_id=s.run.base_id,
                    target_season="2025-2026",
                    origin_date=date(2026, 1, 1),
                    baseline_id=s.run.baseline_id,
                    policy_version=s.run.policy_version,
                    expected_source_result_hash=s.run.result_hash,
                )
                for s in saved
            ]
            hierarchy = build_hierarchy(registry, authority, digest(registry))
            sources = [source_mapping(s) for s in saved]
            for level, entity in (("REGION", "SYNTHETIC_REGION"), ("COMPANY", COMPANY_ID)):
                request = CreateHierarchicalRun(
                    target_entity_type=level,
                    target_entity_id=entity,
                    source_run_ids=[s.run.run_id for s in saved],
                )
                value = reconcile(hierarchy, request, sources)
                aggregate = await HierarchicalRunRepository(session).save(
                    hierarchy, request, value, sources
                )
                identities.append(
                    ForecastReadQuery(
                        source_kind="HIERARCHICAL",
                        forecast_family="OPERATIONAL_PEAK_FORECAST_RUN_V1",
                        run_id=aggregate.run.run_id,
                        hierarchy_level=level,
                        entity_id=entity,
                        target_season="2025-2026",
                        origin_date=date(2026, 1, 1),
                        baseline_id=saved[0].run.baseline_id,
                        policy_version=saved[0].run.policy_version,
                        expected_source_result_hash=aggregate.run.result_hash,
                    )
                )
            # Additional literal authorities are seeded BEFORE the read-only DML guard.
            original = saved_fixture("SYNTHETIC_BASE_1")
            rerun = await repository.save(
                saved[0].request_snapshot,
                original,
                execution_hash(saved[0].request_snapshot, "c" * 64, original.policy_version),
                "c" * 64,
                saved[0].run.run_id,
            )
            identities.append(identities[0].model_copy(update={"run_id": rerun.run.run_id}))
            short_day = DailyForecast(date(2026, 4, 15), Decimal("80"), Decimal("80"), 288, 41)
            short_window = PeakWindowForecast(
                7,
                "NOT_COMPUTABLE_FULL_WINDOW",
                date(2026, 4, 15),
                date(2026, 4, 21),
                None,
                None,
                None,
                1,
                "BUSINESS_SEASON_WINDOW_EXCEEDED",
            )
            short_result = replace(
                original,
                origin_date=date(2026, 4, 14),
                daily_forecast=(short_day,),
                forecast_7d=short_window,
                forecast_15d=replace(short_window, window_days=15, end_date=date(2026, 4, 29)),
                remaining_business_window=PeakWindowForecast(
                    None,
                    "COMPUTABLE_REMAINING_WINDOW",
                    date(2026, 4, 15),
                    date(2026, 4, 15),
                    Decimal("80"),
                    date(2026, 4, 15),
                    Decimal("80"),
                    1,
                ),
            )
            short_result = replace(short_result, result_hash=canonical_result_hash(short_result))
            short_snapshot = {
                "base_id": short_result.base_id,
                "target_season": short_result.target_season,
                "origin_date": short_result.origin_date.isoformat(),
            }
            short_saved = await repository.save(
                short_snapshot,
                short_result,
                execution_hash(short_snapshot, authority, short_result.policy_version),
                authority,
                None,
            )
            identities.append(
                identities[0].model_copy(
                    update={
                        "run_id": short_saved.run.run_id,
                        "origin_date": short_result.origin_date,
                        "expected_source_result_hash": short_saved.run.result_hash,
                    }
                )
            )
            incomplete_request = CreateHierarchicalRun(
                target_entity_type="REGION",
                target_entity_id="SYNTHETIC_REGION",
                source_run_ids=[saved[0].run.run_id],
            )
            incomplete_sources = [source_mapping(saved[0])]
            incomplete_value = reconcile(hierarchy, incomplete_request, incomplete_sources)
            incomplete = await HierarchicalRunRepository(session).save(
                hierarchy, incomplete_request, incomplete_value, incomplete_sources
            )
            identities.append(
                identities[2].model_copy(
                    update={
                        "run_id": incomplete.run.run_id,
                        "expected_source_result_hash": incomplete.run.result_hash,
                    }
                )
            )
            STATE["identities"] = [q.model_dump(mode="json") for q in identities]
            STATE["canonical_curves"] = [
                (await ForecastIntelligenceReadService(session).curve(q)).model_dump(mode="json")
                for q in identities
            ]

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def no_read_mutation(connection, cursor, statement, parameters, context, executemany):
            if (
                statement.lstrip()
                .upper()
                .startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER"))
            ):
                STATE["read_dml_count"] += 1
                raise AssertionError("READ_MUTATION_FORBIDDEN")

        async def sessions():
            async with factory() as session:
                yield session

        async def actor():
            return ActualHarvestActorContext(
                identity="SYNTHETIC_FRONTEND_INTEGRATION",
                allowed_source_systems=frozenset({"synthetic"}),
                allowed_channels=frozenset({ActualHarvestImportChannel.API}),
                may_read_forecast=True,
                may_read_quality=True,
            )

        app.dependency_overrides[get_db_session] = sessions
        app.dependency_overrides[get_actual_harvest_actor] = actor
        yield
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(read_router, prefix="/api/v1/forecast-intelligence")
app.include_router(decision_router, prefix="/api/v1/decision-support")


@app.get("/__dashboard_test__/authority")
async def test_authority():
    return {"SYNTHETIC": True, **STATE}
