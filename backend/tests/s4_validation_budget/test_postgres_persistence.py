"""Real PostgreSQL transaction/locking coverage for the S4 budget authority."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from backend.app.s4_validation_budget import (
    S4ValidationBudgetRepository,
    StartedEventCommand,
    ValidationBudgetError,
)

pytestmark = [pytest.mark.postgres, pytest.mark.postgres_concurrency, pytest.mark.concurrency]


def _command(evaluation_id: str, candidate_id: str) -> StartedEventCommand:
    return StartedEventCommand(
        evaluation_id=evaluation_id,
        experiment_plan_version="v0.3-experiment-plan-v1",
        candidate_id=candidate_id,
        candidate_run_ordinal=1,
        global_evaluation_ordinal=1,
        invocation_type="NORMAL_RUN",
        trigger_source="postgres-concurrency-test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        dataset_hash="a" * 64,
        validation_split_hash="b" * 64,
        code_commit_sha="c" * 40,
        parameter_manifest_hash="d" * 64,
        random_seed=1,
    )


@pytest.fixture
async def isolated_postgres_engine() -> AsyncIterator[AsyncEngine]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL must point at the isolated PostgreSQL test database")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE s4_validation_event, "
                "s4_validation_budget_authority RESTART IDENTITY CASCADE"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO s4_validation_budget_authority "
                "(authority_key, authority_version, accepted_event_count, "
                "accepted_started_count, accepted_head_event_hash, "
                "accepted_last_global_evaluation_ordinal, "
                "legacy_reconciled_validation_debit) "
                "VALUES ('V0_3_S4_VALIDATION_BUDGET', 0, 0, 0, :genesis, 0, 4)"
            ),
            {"genesis": "0" * 64},
        )
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_postgres_two_sessions_serialize_started_commit(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    first_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    second_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    first_inserted = asyncio.Event()
    release_first = asyncio.Event()

    async def pause_after_insert(_: AsyncSession) -> None:
        first_inserted.set()
        await release_first.wait()

    try:
        first_repository = S4ValidationBudgetRepository(
            first_session,
            before_head_advance_hook=pause_after_insert,
        )
        second_repository = S4ValidationBudgetRepository(second_session)
        first_task = asyncio.create_task(
            first_repository.append_started(_command("pg-evaluation-1", "candidate-a"))
        )
        await asyncio.wait_for(first_inserted.wait(), timeout=10)
        second_task = asyncio.create_task(
            second_repository.append_started(_command("pg-evaluation-2", "candidate-b"))
        )
        await asyncio.sleep(0.1)
        release_first.set()
        await first_task
        with pytest.raises(ValidationBudgetError) as captured:
            await second_task
        assert captured.value.reason_code == "VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT"
    finally:
        await first_session.close()
        await second_session.close()

    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_event_count == 1
        assert state.accepted_started_count == 1
        assert state.effective_consumed == 5
        assert state.remaining == 27
