"""Real PostgreSQL session evidence for the Slice B orchestration boundary."""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from backend.tests.agent.test_orchestration import _orchestrator, _request


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL evidence",
)
async def test_slice_b_orchestration_uses_real_postgres_session(transactional_pg_session) -> None:
    result = await transactional_pg_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1

    output = await _orchestrator([]).execute(
        transactional_pg_session,
        request=_request(),
        request_received_at=datetime(2026, 3, 1, tzinfo=UTC),
    )
    assert output.provenance["scenario_config_hash"] is not None
    assert len(output.provenance["agent_forecast_output_hash"]) == 64
