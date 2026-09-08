"""Real PostgreSQL transaction/locking coverage for the S4 budget authority."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from backend.app.models.s4_validation_budget import S4ValidationEvent
from backend.app.s4_candidate_03_execution import (
    C03PairingIdentities,
    build_candidate_03_gate_request,
    build_candidate_03_manifest,
    execute_authorized_candidate_03,
    preflight_candidate_03,
)
from backend.app.s4_candidate_execution_authority import S4CandidateExecutionAuthority
from backend.app.s4_experiment import (
    EXPERIMENT_PLAN_VERSION,
    FROZEN_CANDIDATE_REGISTRY,
    GUARDRAIL_POLICY_HASH,
    GUARDRAIL_POLICY_VERSION,
    METRIC_CONTRACT_IDENTITY,
    METRIC_CONTRACT_VERSION,
    S4_A_EXPERIMENT_PLAN_HASH_BOUND,
    CandidateExecutionGateRequest,
)
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


def _durable_gate_request(
    *,
    evaluation_id: str,
    candidate_id: str = "02_quantile_calibration",
) -> CandidateExecutionGateRequest:
    identity = "a" * 64
    return CandidateExecutionGateRequest(
        experiment_plan_version=EXPERIMENT_PLAN_VERSION,
        experiment_plan_hash=S4_A_EXPERIMENT_PLAN_HASH_BOUND,
        guardrail_policy_version=GUARDRAIL_POLICY_VERSION,
        guardrail_policy_hash=GUARDRAIL_POLICY_HASH,
        candidate_id=candidate_id,
        candidate_run_ordinal=1,
        candidate_planned_run_count=4,
        candidate_actual_run_count=0,
        global_actual_evaluation_count=0,
        train_dataset_identity=identity,
        validation_dataset_identity=identity,
        actual_label_set_identity=identity,
        exclusion_policy_identity=identity,
        cutoff_policy_identity=identity,
        forecast_horizon_set_identity=identity,
        metric_contract_identity=METRIC_CONTRACT_IDENTITY,
        business_grain_set_identity=identity,
        common_comparable_set_identity=identity,
        metric_contract_version=METRIC_CONTRACT_VERSION,
        test_access_requested=False,
        test_sealed=True,
        parameter_manifest_hash=identity,
        code_commit_sha="c" * 40,
        random_seed=20260908,
        evaluation_id=evaluation_id,
        candidate_execution_manifest_frozen=True,
        candidate_registry=FROZEN_CANDIDATE_REGISTRY,
    )


async def test_postgres_execution_started_commits_before_fake_scorer(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        observed: list[int] = []

        async def fake_scorer() -> str:
            state = await S4ValidationBudgetRepository(session).load_verified_state()
            observed.append(state.effective_consumed)
            return "COMPUTED"

        result = await S4CandidateExecutionAuthority(session).execute(
            _durable_gate_request(evaluation_id="pg-integration-order"),
            scorer=fake_scorer,
            execution_authorized=True,
            trigger_source="postgres-integration-order",
        )
        assert result.status == "COMPLETED"
        assert result.started_persisted is True
        assert observed == [5]


async def test_postgres_execution_cas_conflict_never_calls_second_scorer(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    first_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    second_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    try:
        first_authority = S4CandidateExecutionAuthority(first_session)
        second_authority = S4CandidateExecutionAuthority(second_session)
        first_preflight = await first_authority.preflight(
            _durable_gate_request(evaluation_id="pg-cas-first")
        )
        second_preflight = await second_authority.preflight(
            _durable_gate_request(evaluation_id="pg-cas-second")
        )
        assert first_preflight.allowed is True
        assert second_preflight.allowed is True
        second_scorer_called = False

        def second_scorer() -> str:
            nonlocal second_scorer_called
            second_scorer_called = True
            return "COMPUTED"

        first_result, second_result = await asyncio.gather(
            first_authority.execute_preflight(
                first_preflight,
                scorer=lambda: "COMPUTED",
                execution_authorized=True,
                trigger_source="postgres-cas-first",
            ),
            second_authority.execute_preflight(
                second_preflight,
                scorer=second_scorer,
                execution_authorized=True,
                trigger_source="postgres-cas-second",
            ),
        )
        assert first_result.status == "COMPLETED"
        assert second_result.reason_code == "VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT"
        assert second_result.scorer_called is False
        assert second_scorer_called is False
    finally:
        await first_session.close()
        await second_session.close()

    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        state = await S4ValidationBudgetRepository(session).load_verified_state()
        assert state.accepted_started_count == 1
        assert state.effective_consumed == 5


async def test_postgres_failed_fake_scorer_keeps_started_debit(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:

        def fake_scorer() -> str:
            raise RuntimeError("synthetic scorer failure")

        result = await S4CandidateExecutionAuthority(session).execute(
            _durable_gate_request(evaluation_id="pg-failed-scorer"),
            scorer=fake_scorer,
            execution_authorized=True,
            trigger_source="postgres-failed-scorer",
        )
        assert result.status == "FAILED"
        assert result.started_persisted is True
        assert result.terminal_persisted is True
        assert result.state_after_terminal is not None
        assert result.state_after_terminal.effective_consumed == 5
        assert result.state_after_terminal.remaining == 27


async def test_postgres_terminal_does_not_add_budget(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        result = await S4CandidateExecutionAuthority(session).execute(
            _durable_gate_request(evaluation_id="pg-terminal-no-budget"),
            scorer=lambda: "COMPUTED",
            execution_authorized=True,
            trigger_source="postgres-terminal-no-budget",
        )
        assert result.status == "COMPLETED"
        assert result.state_after_terminal is not None
        state = result.state_after_terminal
        assert state.accepted_event_count == 2
        assert state.accepted_started_count == 1
        assert state.effective_consumed == 5
        assert state.remaining == 27


def _c03_context():
    repo_root = Path(__file__).resolve().parents[3]
    manifest = build_candidate_03_manifest(repo_root / "configs/maturity_curve.yaml")

    def identity(label: str) -> str:
        return hashlib.sha256(label.encode("utf-8")).hexdigest()

    pairing = C03PairingIdentities(
        train_dataset_identity=identity("pg-c03-train"),
        validation_dataset_identity=identity("pg-c03-validation"),
        actual_label_set_identity=identity("pg-c03-labels"),
        exclusion_policy_identity=identity("pg-c03-exclusion"),
        cutoff_policy_identity=identity("pg-c03-cutoff"),
        forecast_horizon_set_identity=identity("pg-c03-horizons"),
        business_grain_set_identity=identity("pg-c03-grains"),
        common_comparable_set_identity=identity("pg-c03-comparable"),
    )
    return manifest, pairing


def _c03_request(evaluation_id: str) -> CandidateExecutionGateRequest:
    manifest, pairing = _c03_context()
    return build_candidate_03_gate_request(
        manifest=manifest,
        run=manifest.run(1),
        pairing_identities=pairing,
        code_commit_sha="c" * 40,
        evaluation_id=evaluation_id,
    )


async def test_postgres_c03_preflight_observes_4_of_32(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    manifest, pairing = _c03_context()
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        preflight = await preflight_candidate_03(
            session,
            manifest=manifest,
            candidate_run_ordinal=1,
            pairing_identities=pairing,
            code_commit_sha="c" * 40,
            evaluation_id="pg-c03-preflight",
        )
    assert preflight.allowed is True
    assert preflight.candidate_actual_run_count == 0
    assert preflight.global_actual_evaluation_count == 4
    assert preflight.gate_request is not None
    assert preflight.gate_request.candidate_run_ordinal == 1
    assert preflight.gate_request.global_actual_evaluation_count == 4


async def test_postgres_c03_started_commits_before_fake_scorer(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    manifest, pairing = _c03_context()
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:
        observed: list[int] = []

        async def fake_scorer() -> str:
            state = await S4ValidationBudgetRepository(session).load_verified_state()
            observed.append(state.effective_consumed)
            return "COMPUTED"

        result = await execute_authorized_candidate_03(
            session,
            manifest=manifest,
            candidate_run_ordinal=1,
            pairing_identities=pairing,
            code_commit_sha="c" * 40,
            evaluation_id="pg-c03-order",
            scorer=fake_scorer,
            execution_authorized=True,
            trigger_source="postgres-c03-order",
        )
    assert result.status == "COMPLETED"
    assert result.started_persisted is True
    assert observed == [5]


async def test_postgres_c03_cas_conflict_blocks_second_execution(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    manifest, pairing = _c03_context()
    first_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    second_session = AsyncSession(isolated_postgres_engine, expire_on_commit=False)
    try:
        first_authority = S4CandidateExecutionAuthority(first_session)
        second_authority = S4CandidateExecutionAuthority(second_session)
        first_preflight = await preflight_candidate_03(
            first_session,
            manifest=manifest,
            candidate_run_ordinal=1,
            pairing_identities=pairing,
            code_commit_sha="c" * 40,
            evaluation_id="pg-c03-cas-first",
        )
        second_preflight = await preflight_candidate_03(
            second_session,
            manifest=manifest,
            candidate_run_ordinal=1,
            pairing_identities=pairing,
            code_commit_sha="c" * 40,
            evaluation_id="pg-c03-cas-second",
        )
        assert first_preflight.allowed is True
        assert second_preflight.allowed is True
        second_scorer_called = False

        def second_scorer() -> str:
            nonlocal second_scorer_called
            second_scorer_called = True
            return "COMPUTED"

        first_result, second_result = await asyncio.gather(
            first_authority.execute_preflight(
                first_preflight,
                scorer=lambda: "COMPUTED",
                execution_authorized=True,
                trigger_source="postgres-c03-cas-first",
            ),
            second_authority.execute_preflight(
                second_preflight,
                scorer=second_scorer,
                execution_authorized=True,
                trigger_source="postgres-c03-cas-second",
            ),
        )
        assert first_result.status == "COMPLETED"
        assert second_result.reason_code == "VALIDATION_BUDGET_AUTHORITY_CAS_CONFLICT"
        assert second_result.scorer_called is False
        assert second_scorer_called is False
    finally:
        await first_session.close()
        await second_session.close()


async def test_postgres_c03_failed_fake_scorer_keeps_debit(
    isolated_postgres_engine: AsyncEngine,
) -> None:
    manifest, pairing = _c03_context()
    async with AsyncSession(isolated_postgres_engine, expire_on_commit=False) as session:

        def fake_scorer() -> str:
            raise RuntimeError("synthetic C03 scorer failure")

        result = await execute_authorized_candidate_03(
            session,
            manifest=manifest,
            candidate_run_ordinal=1,
            pairing_identities=pairing,
            code_commit_sha="c" * 40,
            evaluation_id="pg-c03-failed-scorer",
            scorer=fake_scorer,
            execution_authorized=True,
            trigger_source="postgres-c03-failed-scorer",
        )
    assert result.status == "FAILED"
    assert result.started_persisted is True
    assert result.terminal_persisted is True
    assert result.state_after_terminal is not None
    assert result.state_after_terminal.effective_consumed == 5
    assert result.state_after_terminal.remaining == 27
