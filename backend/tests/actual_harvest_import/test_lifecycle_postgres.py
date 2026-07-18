from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import delete

from backend.app.actual_harvest_import.api_schemas import ActualHarvestApiCreateImportRequest
from backend.app.actual_harvest_import.lifecycle import create_import
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.db.session import AsyncSessionMaker
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload
from backend.tests.db.profile import assert_safe_postgres_test_identity

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")
    assert_safe_postgres_test_identity(env=None)


async def _create_once(payload: dict[str, object]) -> str:
    request = ActualHarvestApiCreateImportRequest.model_validate(payload)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch, _ = await create_import(session, request)
            return batch.import_id


@pytest.mark.asyncio
async def test_postgres_i4_concurrent_identical_create_has_one_batch() -> None:
    _require_postgres()
    payload = _create_payload()
    suffix = uuid4().hex
    payload["external_batch_id"] = f"i4-pg-{suffix}"
    payload["idempotency_key"] = f"i4-pg-{suffix}"
    try:
        first_id, second_id = await asyncio.gather(
            _create_once(payload.copy()),
            _create_once(payload.copy()),
        )
        assert first_id == second_id
        async with AsyncSessionMaker() as session:
            count = await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestImportBatchModel)
                .where(
                    ActualHarvestImportBatchModel.external_batch_id == payload["external_batch_id"]
                )
            )
            assert count == 1
    finally:
        async with AsyncSessionMaker() as session:
            async with session.begin():
                await session.execute(
                    delete(ActualHarvestImportBatchModel).where(
                        ActualHarvestImportBatchModel.external_batch_id
                        == payload["external_batch_id"]
                    )
                )
