"""Isolated synthetic authority and source runs; no business data access."""

import importlib
from datetime import date

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.area_yield.data import digest
from backend.app.forecast_quality import operational_peak_authority as authority_module
from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastRequest,
    forecast_operational_peak,
)
from backend.app.forecast_quality.operational_peak_authority import OperationalPeakAuthoritySnapshot
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakRunRepository,
    execution_hash,
    request_snapshot,
)
from backend.tests.forecast_intelligence.test_reconciliation import registry

MIGRATION = importlib.import_module("backend.alembic.versions.0040_hierarchical_forecast")
SOURCE_MIGRATION = importlib.import_module(
    "backend.alembic.versions.0035_operational_peak_forecast_runs"
)


def create_tables(connection):
    with Operations.context(MigrationContext.configure(connection)):
        SOURCE_MIGRATION.upgrade()
        MIGRATION.upgrade()


@pytest.fixture
def synthetic_authority(monkeypatch):
    values = registry()
    for index, base in enumerate(values["bases"], 1):
        base["productive_area_mu"] = str(index)
    snapshot = OperationalPeakAuthoritySnapshot(
        authority_version="OPERATIONAL_PEAK_AUTHORITY_V1",
        policy_version="OPERATIONAL_PEAK_POLICY_V1",
        baseline_id="AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        authority_hash=digest(values),
        registry=values,
        reference_profile={i: "1.000000000000" for i in range(42)},
        reference_profile_fold="B",
        weather_used=False,
    )
    monkeypatch.setattr(authority_module, "load_operational_peak_authority", lambda: snapshot)
    monkeypatch.setattr(authority_module, "REGISTRY_PAYLOAD_HASH", digest(values))
    return snapshot


async def seed_sources(factory, authority):
    ids = []
    async with factory() as session, session.begin():
        repository = OperationalPeakRunRepository(session)
        for base in authority.registry["bases"]:
            # Synthetic fixtures only. Production S1 never calls the forecast function.
            request = OperationalPeakForecastRequest(base["base_id"], "2025-2026", date(2026, 1, 1))
            result = forecast_operational_peak(
                request, registry=authority.registry, reference_profile=authority.reference_profile
            )
            snapshot = request_snapshot(request)
            saved = await repository.save(
                snapshot=snapshot,
                result=result,
                execution_id=execution_hash(
                    snapshot, authority.authority_hash, authority.policy_version
                ),
                authority_hash=authority.authority_hash,
                rerun_of_run_id=None,
            )
            ids.append(saved.run.run_id)
    return ids


@pytest.fixture
async def hierarchy_factory(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path}/hierarchy.db", connect_args={"autocommit": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(create_tables)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def source_ids(hierarchy_factory, synthetic_authority):
    return await seed_sources(hierarchy_factory, synthetic_authority)
