"""Real PostgreSQL transaction/locking coverage for the S4 budget authority."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from backend.app.models.s4_validation_budget import S4ValidationEvent
from backend.app.s4_validation_budget import (
    S4ValidationBudgetRepository,
    StartedEventCommand,
    ValidationBudgetError,
)
from backend.app.s4_validation_budget.canonical import canonical_event_body, validation_event_hash

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


async def _insert_direct_started(
    session: AsyncSession,
    command: StartedEventCommand,
    *,
    event_sequence: int,
    previous_event_hash: str,
) -> None:
    payload = canonical_event_body(command.body())
    session.add(
        S4ValidationEvent(
            authority_key="V0_3_S4_VALIDATION_BUDGET",
            event_sequence=event_sequence,
            event_type="EVALUATION_STARTED",
            evaluation_id=payload["evaluation_id"],
            candidate_id=payload["candidate_id"],
            candidate_run_ordinal=payload["candidate_run_ordinal"],
            global_evaluation_ordinal=payload["global_evaluation_ordinal"],
            invocation_type=payload["invocation_type"],
            counted_toward_budget=payload["counted_toward_budget"],
            budget_count_reason=payload["budget_count_reason"],
            event_payload=payload,
            previous_event_hash=previous_event_hash,
            event_hash=validation_event_hash(
                event_type="EVALUATION_STARTED",
                event_payload=payload,
                previous_event_hash=previous_event_hash,
            ),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await session.flush()


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


async def test_postgres_event_update_is_rejected(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        event = await S4ValidationBudgetRepository(session).append_started(
            _command("pg-immutable-update", "candidate-a")
        )
        with pytest.raises(SQLAlchemyError) as captured:
            await session.execute(
                update(S4ValidationEvent)
                .where(S4ValidationEvent.event_sequence == event.event_sequence)
                .values(candidate_id="hostile-update")
            )
        assert "immutable" in str(captured.value).lower()
        await session.rollback()
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_started_count == 1


async def test_postgres_event_delete_is_rejected(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        event = await S4ValidationBudgetRepository(session).append_started(
            _command("pg-immutable-delete", "candidate-a")
        )
        with pytest.raises(SQLAlchemyError) as captured:
            await session.execute(
                text("DELETE FROM s4_validation_event WHERE event_sequence = :sequence"),
                {"sequence": event.event_sequence},
            )
        assert "immutable" in str(captured.value).lower()
        await session.rollback()
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_started_count == 1


async def test_postgres_candidate_run_partial_unique_is_enforced(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        first = await S4ValidationBudgetRepository(session).append_started(
            _command("pg-candidate-run-1", "candidate-a")
        )
        with pytest.raises(IntegrityError):
            await _insert_direct_started(
                session,
                _command("pg-candidate-run-duplicate", "candidate-a"),
                event_sequence=2,
                previous_event_hash=first.event_hash,
            )
        await session.rollback()
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_started_count == 1


async def test_postgres_global_ordinal_partial_unique_is_enforced(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        first = await S4ValidationBudgetRepository(session).append_started(
            _command("pg-global-1", "candidate-a")
        )
        duplicate_global = StartedEventCommand(
            evaluation_id="pg-global-duplicate",
            experiment_plan_version="v0.3-experiment-plan-v1",
            candidate_id="candidate-b",
            candidate_run_ordinal=1,
            global_evaluation_ordinal=1,
            invocation_type="NORMAL_RUN",
            trigger_source="postgres-unique-test",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            dataset_hash="a" * 64,
            validation_split_hash="b" * 64,
            code_commit_sha="c" * 40,
            parameter_manifest_hash="d" * 64,
            random_seed=2,
        )
        with pytest.raises(IntegrityError):
            await _insert_direct_started(
                session,
                duplicate_global,
                event_sequence=2,
                previous_event_hash=first.event_hash,
            )
        await session.rollback()
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_started_count == 1


async def test_postgres_rollback_atomicity_leaves_no_orphan_event(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:

        def fail(_: AsyncSession) -> None:
            raise RuntimeError("simulated head advance failure")

        with pytest.raises(RuntimeError, match="simulated head advance failure"):
            await S4ValidationBudgetRepository(
                session,
                before_head_advance_hook=fail,
            ).append_started(_command("pg-rollback", "candidate-a"))
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_event_count == 0
        assert state.accepted_started_count == 0
        assert state.authority_version == 0
        assert state.effective_consumed == 4
        assert state.remaining == 28


async def test_postgres_committed_started_survives_fresh_session_readback(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        await S4ValidationBudgetRepository(session).append_started(
            _command("pg-durable", "candidate-a")
        )
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as fresh_session:
        state = await S4ValidationBudgetRepository(fresh_session).load_verified_state()
        assert state.accepted_started_count == 1
        assert state.effective_consumed == 5
        assert state.remaining == 27
