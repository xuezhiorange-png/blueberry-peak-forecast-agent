from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.actual_harvest_import.api_auth import ActualHarvestActorContext
from backend.app.actual_harvest_import.enums import ActualHarvestImportChannel
from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingPolicyRegistryModel,
    ActualHarvestMappingRegistryEntryModel,
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationAttemptModel,
    ActualHarvestValidationErrorModel,
    ActualHarvestValidationLineageBasisMemberModel,
    ActualHarvestValidationLineageBasisModel,
    ActualHarvestValidationLineageEdgeModel,
    ActualHarvestValidationLineageNodeModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationRecordModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.db.base import Base
from backend.app.db.session import get_db_session
from backend.app.main import create_app
from backend.app.models.master_data import Farm, Season, Subfarm, Variety

NOW = datetime(2026, 7, 18, 8, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def sqlite_session_maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[
                ActualHarvestImportBatchModel.__table__,
                ActualHarvestImportRecordModel.__table__,
                ActualHarvestMappingPolicyRegistryModel.__table__,
                ActualHarvestMappingRegistryEntryModel.__table__,
                ActualHarvestValidationRunModel.__table__,
                ActualHarvestValidationAttemptModel.__table__,
                ActualHarvestMappingSnapshotModel.__table__,
                ActualHarvestValidationResultModel.__table__,
                ActualHarvestValidationRecordModel.__table__,
                ActualHarvestValidationMappingEvidenceModel.__table__,
                ActualHarvestValidationErrorModel.__table__,
                ActualHarvestValidationLineageNodeModel.__table__,
                ActualHarvestValidationLineageEdgeModel.__table__,
                ActualHarvestValidationLineageBasisModel.__table__,
                ActualHarvestValidationLineageBasisMemberModel.__table__,
                Season.__table__,
                Farm.__table__,
                Subfarm.__table__,
                Variety.__table__,
            ],
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def api_client(
    sqlite_session_maker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sqlite_session_maker() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def authorized_actor() -> ActualHarvestActorContext:
    return ActualHarvestActorContext(
        identity="operator-1",
        allowed_source_systems=frozenset({"farm-system"}),
        allowed_channels=frozenset({ActualHarvestImportChannel.API}),
        may_create=True,
        may_append=True,
        may_preview=True,
        may_seal=True,
        may_cancel=True,
        may_validate=True,
        may_commit=True,  # v0.2-S1
    )
