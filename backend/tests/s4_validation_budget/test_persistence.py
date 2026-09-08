"""SQLite contract tests for the S4 persistence primitive.

These tests use the real Alembic migration and synthetic event commands only;
they never execute a candidate, score validation data, or access TEST.
PostgreSQL locking/concurrency coverage lives in the separately marked live
test module.
"""

from __future__ import annotations

import importlib.util
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.models.s4_validation_budget import (
    S4ValidationBudgetAuthority,
    S4ValidationEvent,
)
from backend.app.s4_validation_budget import (
    S4ValidationBudgetRepository,
    StartedEventCommand,
    TerminalEventCommand,
    ValidationBudgetError,
)
from backend.app.s4_validation_budget.canonical import validation_event_hash

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def _migration_module() -> Any:
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "0032_s4_validation_budget_durable_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0032_s4_validation_budget", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _upgrade(connection: Any) -> None:
    migration = _migration_module()

    def apply(sync_connection: Any) -> None:
        migration.op = Operations(MigrationContext.configure(sync_connection))
        migration.upgrade()

    await connection.run_sync(apply)


@pytest.fixture
async def sqlite_db() -> AsyncIterator[tuple[AsyncSession, AsyncEngine]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await _upgrade(connection)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session, engine
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _command(
    ordinal: int,
    *,
    candidate_id: str = "01_parameter_calibration",
    candidate_run_ordinal: int | None = None,
    evaluation_id: str | None = None,
    expected_authority_version: int | None = None,
    expected_event_count: int | None = None,
    expected_started_count: int | None = None,
    expected_head_event_hash: str | None = None,
    expected_last_global_evaluation_ordinal: int | None = None,
) -> StartedEventCommand:
    return StartedEventCommand(
        evaluation_id=evaluation_id or f"evaluation-{ordinal}-{candidate_id}",
        experiment_plan_version="v0.3-experiment-plan-v1",
        candidate_id=candidate_id,
        candidate_run_ordinal=(ordinal if candidate_run_ordinal is None else candidate_run_ordinal),
        global_evaluation_ordinal=ordinal,
        invocation_type="NORMAL_RUN",
        trigger_source="synthetic-contract-test",
        started_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=ordinal),
        dataset_hash="a" * 64,
        validation_split_hash="b" * 64,
        code_commit_sha="c" * 40,
        parameter_manifest_hash="d" * 64,
        random_seed=ordinal,
        expected_authority_version=expected_authority_version,
        expected_event_count=expected_event_count,
        expected_started_count=expected_started_count,
        expected_head_event_hash=expected_head_event_hash,
        expected_last_global_evaluation_ordinal=expected_last_global_evaluation_ordinal,
    )


async def _start(
    session: AsyncSession,
    ordinal: int,
    *,
    candidate_id: str = "01_parameter_calibration",
    candidate_run_ordinal: int | None = None,
    evaluation_id: str | None = None,
) -> None:
    await S4ValidationBudgetRepository(session).append_started(
        _command(
            ordinal,
            candidate_id=candidate_id,
            candidate_run_ordinal=candidate_run_ordinal,
            evaluation_id=evaluation_id,
        )
    )


async def _expect_reason(awaitable: Any, reason: str) -> None:
    with pytest.raises(ValidationBudgetError) as captured:
        await awaitable
    assert captured.value.reason_code == reason


async def _drop_event_guards(session: AsyncSession) -> None:
    await session.execute(text("DROP TRIGGER IF EXISTS s4_validation_event_immutable_update"))
    await session.execute(text("DROP TRIGGER IF EXISTS s4_validation_event_immutable_delete"))
    await session.commit()


async def test_bootstrap_is_zero_canonical_plus_four_legacy(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.authority_version == 0
    assert state.accepted_event_count == 0
    assert state.accepted_started_count == 0
    assert state.effective_consumed == 4
    assert state.remaining == 28
    assert len(state.events) == 0


async def test_first_started_commits_five_of_thirty_two(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.effective_consumed == 5
    assert state.remaining == 27


async def test_second_started_commits_six_of_thirty_two(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _start(session, 2, candidate_run_ordinal=2)
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.effective_consumed == 6
    assert state.remaining == 26


async def test_started_commit_precedes_model_execution(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    committed = False
    await _start(session, 1, candidate_run_ordinal=1)
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    committed = state.accepted_started_count == 1
    assert committed is True


async def test_committed_started_survives_process_failure(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, engine = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await session.close()
    async with AsyncSession(engine, expire_on_commit=False) as fresh_session:
        state = await S4ValidationBudgetRepository(fresh_session).load_verified_state()
        assert state.accepted_started_count == 1
        assert state.effective_consumed == 5
        assert state.remaining == 27


async def test_failed_scoring_does_not_refund_started_budget(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_started_count == 1
    assert state.remaining == 27


async def test_terminal_does_not_increment_budget(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await S4ValidationBudgetRepository(session).append_terminal(
        TerminalEventCommand(
            evaluation_id="evaluation-1-01_parameter_calibration",
            candidate_id="01_parameter_calibration",
            finished_at=datetime(2026, 1, 2, tzinfo=UTC),
            execution_status="COMPLETED",
            metric_result_status="COMPUTED",
        )
    )
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_event_count == 2
    assert state.accepted_started_count == 1
    assert state.remaining == 27


async def test_delete_last_started_is_detected(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _drop_event_guards(session)
    await session.execute(delete(S4ValidationEvent).where(S4ValidationEvent.event_sequence == 1))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED",
    )


async def test_delete_last_started_and_terminal_suffix_is_detected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await S4ValidationBudgetRepository(session).append_terminal(
        TerminalEventCommand(
            "evaluation-1-01_parameter_calibration",
            "01_parameter_calibration",
            datetime(2026, 1, 2, tzinfo=UTC),
            "FAILED",
            "NOT_COMPUTABLE",
        )
    )
    await _drop_event_guards(session)
    await session.execute(delete(S4ValidationEvent))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_LEDGER_TAIL_TRUNCATION_DETECTED",
    )


async def test_head_hash_regression_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await session.execute(
        update(S4ValidationBudgetAuthority).values(accepted_head_event_hash="f" * 64)
    )
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_LEDGER_HEAD_MISMATCH",
    )


async def test_event_count_regression_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    with pytest.raises(SQLAlchemyError):
        await session.execute(update(S4ValidationBudgetAuthority).values(accepted_event_count=0))
    await session.rollback()
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_event_count == 1


async def test_started_count_regression_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await session.execute(update(S4ValidationBudgetAuthority).values(accepted_started_count=0))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_LEDGER_STARTED_COUNT_MISMATCH",
    )


async def test_global_ordinal_regression_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await session.execute(
        update(S4ValidationBudgetAuthority).values(accepted_last_global_evaluation_ordinal=0)
    )
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_GLOBAL_ORDINAL_REGRESSION",
    )


async def test_stale_cas_writer_is_rejected(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    stale = _command(
        2,
        candidate_id="02_quantile_calibration",
        candidate_run_ordinal=1,
        evaluation_id="stale-evaluation",
        expected_authority_version=0,
        expected_event_count=0,
        expected_started_count=0,
        expected_head_event_hash="0" * 64,
        expected_last_global_evaluation_ordinal=0,
    )
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(stale),
        "VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT",
    )


async def test_two_concurrent_runners_cannot_consume_same_ordinal(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    _, engine = sqlite_db
    first = AsyncSession(engine, expire_on_commit=False)
    second = AsyncSession(engine, expire_on_commit=False)
    try:
        await _start(first, 1, candidate_run_ordinal=1)
        await _expect_reason(
            S4ValidationBudgetRepository(second).append_started(
                _command(
                    1,
                    candidate_id="02_quantile_calibration",
                    candidate_run_ordinal=1,
                    evaluation_id="different-evaluation",
                )
            ),
            "VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT",
        )
    finally:
        await first.close()
        await second.close()


async def test_budget_32_blocks_next_started(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    for ordinal in range(1, 29):
        candidate_number = ((ordinal - 1) % 8) + 1
        candidate_id = f"candidate-{candidate_number}"
        await _start(
            session,
            ordinal,
            candidate_id=candidate_id,
            candidate_run_ordinal=((ordinal - 1) // 8) + 1,
        )
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.effective_consumed == 32
    assert state.remaining == 0
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(
            _command(29, candidate_id="candidate-1", candidate_run_ordinal=5)
        ),
        "VALIDATION_BUDGET_EXHAUSTED",
    )


async def test_candidate_fifth_run_is_rejected(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    for ordinal in range(1, 5):
        await _start(session, ordinal, candidate_run_ordinal=ordinal)
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(_command(5, candidate_run_ordinal=5)),
        "VALIDATION_CANDIDATE_RUN_LIMIT_EXCEEDED",
    )


async def test_duplicate_started_candidate_run_ordinal_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(
            _command(2, candidate_run_ordinal=1, evaluation_id="duplicate-run")
        ),
        "VALIDATION_CANDIDATE_RUN_ORDINAL_DUPLICATE",
    )


async def test_started_candidate_run_ordinal_zero_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(_command(1, candidate_run_ordinal=0)),
        "VALIDATION_CANDIDATE_RUN_ORDINAL_INVALID",
    )


async def test_started_candidate_run_ordinal_five_is_rejected(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_started(_command(1, candidate_run_ordinal=5)),
        "VALIDATION_CANDIDATE_RUN_ORDINAL_INVALID",
    )


async def test_same_run_ordinal_is_allowed_for_different_candidates(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_id="candidate-a", candidate_run_ordinal=1)
    await _start(session, 2, candidate_id="candidate-b", candidate_run_ordinal=1)
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_started_count == 2


async def test_orphan_terminal_is_rejected(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_terminal(
            TerminalEventCommand(
                "missing",
                "candidate-a",
                datetime(2026, 1, 2, tzinfo=UTC),
                "FAILED",
                "NOT_COMPUTABLE",
            )
        ),
        "VALIDATION_TERMINAL_WITHOUT_STARTED",
    )


async def test_terminal_candidate_id_must_match_started(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _expect_reason(
        S4ValidationBudgetRepository(session).append_terminal(
            TerminalEventCommand(
                "evaluation-1-01_parameter_calibration",
                "wrong-candidate",
                datetime(2026, 1, 2, tzinfo=UTC),
                "FAILED",
                "NOT_COMPUTABLE",
            )
        ),
        "VALIDATION_TERMINAL_CANDIDATE_MISMATCH",
    )


async def test_duplicate_terminal_is_rejected(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    terminal = TerminalEventCommand(
        "evaluation-1-01_parameter_calibration",
        "01_parameter_calibration",
        datetime(2026, 1, 2, tzinfo=UTC),
        "FAILED",
        "NOT_COMPUTABLE",
    )
    repository = S4ValidationBudgetRepository(session)
    await repository.append_terminal(terminal)
    await _expect_reason(repository.append_terminal(terminal), "VALIDATION_DUPLICATE_TERMINAL")


async def test_terminal_same_authority_and_evaluation_binds_exact_started(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    event = await S4ValidationBudgetRepository(session).append_terminal(
        TerminalEventCommand(
            "evaluation-1-01_parameter_calibration",
            "01_parameter_calibration",
            datetime(2026, 1, 2, tzinfo=UTC),
            "COMPLETED",
            "COMPUTED",
        )
    )
    assert event.event_type == "EVALUATION_TERMINAL"
    assert event.event_payload["counted_toward_budget"] is False
    assert event.counted_toward_budget is False
    assert event.previous_event_hash != "0" * 64


async def test_terminal_does_not_increment_started_count_or_budget(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    await test_terminal_does_not_increment_budget(sqlite_db)


async def test_started_typed_columns_must_match_hashed_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _drop_event_guards(session)
    await session.execute(update(S4ValidationEvent).values(candidate_id="different-candidate"))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_EVENT_PROJECTION_MISMATCH",
    )


async def test_terminal_typed_columns_must_match_hashed_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await S4ValidationBudgetRepository(session).append_terminal(
        TerminalEventCommand(
            "evaluation-1-01_parameter_calibration",
            "01_parameter_calibration",
            datetime(2026, 1, 2, tzinfo=UTC),
            "COMPLETED",
            "COMPUTED",
        )
    )
    await _drop_event_guards(session)
    await session.execute(
        update(S4ValidationEvent)
        .where(S4ValidationEvent.event_type == "EVALUATION_TERMINAL")
        .values(execution_status="FAILED")
    )
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_EVENT_PROJECTION_MISMATCH",
    )


async def test_candidate_id_cannot_diverge_between_column_and_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    await test_started_typed_columns_must_match_hashed_event_body(sqlite_db)


async def test_candidate_run_ordinal_cannot_diverge_between_column_and_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _drop_event_guards(session)
    await session.execute(update(S4ValidationEvent).values(candidate_run_ordinal=2))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_EVENT_PROJECTION_MISMATCH",
    )


async def test_global_evaluation_ordinal_cannot_diverge_between_column_and_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _drop_event_guards(session)
    await session.execute(update(S4ValidationEvent).values(global_evaluation_ordinal=2))
    await session.commit()
    await _expect_reason(
        S4ValidationBudgetRepository(session).load_verified_state(),
        "VALIDATION_EVENT_PROJECTION_MISMATCH",
    )


async def test_evaluation_id_cannot_diverge_between_column_and_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    await test_started_typed_columns_must_match_hashed_event_body(sqlite_db)


async def test_counted_toward_budget_cannot_diverge_between_column_and_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    await _drop_event_guards(session)
    with pytest.raises(SQLAlchemyError):
        await session.execute(update(S4ValidationEvent).values(counted_toward_budget=False))
    await session.rollback()
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_started_count == 1


async def test_budget_reconciliation_blocks_on_projection_mismatch(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    await test_started_typed_columns_must_match_hashed_event_body(sqlite_db)


async def test_hash_replay_uses_stored_canonical_event_body(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    repository = S4ValidationBudgetRepository(session)
    event = await repository.append_started(_command(1, candidate_run_ordinal=1))
    assert event.event_hash == validation_event_hash(
        event_type=event.event_type,
        event_payload=event.event_payload,
        previous_event_hash=event.previous_event_hash,
    )
    await _drop_event_guards(session)
    await session.execute(update(S4ValidationEvent).values(candidate_id="tampered"))
    await session.commit()
    await _expect_reason(repository.load_verified_state(), "VALIDATION_EVENT_PROJECTION_MISMATCH")


async def test_no_legacy_fake_events_are_created(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db
    assert await session.scalar(select(func.count()).select_from(S4ValidationEvent)) == 0


async def test_jsonl_is_not_budget_authority(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_started_count == 0
    assert state.effective_consumed == 4


async def test_atomic_started_rollback_leaves_no_orphan_event(
    sqlite_db: tuple[AsyncSession, AsyncEngine],
) -> None:
    session, _ = sqlite_db

    def fail(_: AsyncSession) -> None:
        raise RuntimeError("simulated head advance failure")

    repository = S4ValidationBudgetRepository(session, before_head_advance_hook=fail)
    with pytest.raises(RuntimeError, match="simulated head advance failure"):
        await repository.append_started(_command(1, candidate_run_ordinal=1))
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_event_count == 0
    assert state.accepted_started_count == 0
    assert state.remaining == 28


async def test_event_immutability(sqlite_db: tuple[AsyncSession, AsyncEngine]) -> None:
    session, _ = sqlite_db
    await _start(session, 1, candidate_run_ordinal=1)
    with pytest.raises(SQLAlchemyError):
        await session.execute(update(S4ValidationEvent).values(candidate_id="hostile-update"))
    await session.rollback()
    with pytest.raises(SQLAlchemyError):
        await session.execute(delete(S4ValidationEvent))
    await session.rollback()
    state = await S4ValidationBudgetRepository(session).load_verified_state()
    assert state.accepted_started_count == 1
