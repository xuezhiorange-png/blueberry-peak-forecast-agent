"""PostgreSQL replay and concurrency acceptance for Round B."""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from backend.app.db.session import AsyncSessionMaker
from backend.app.forecast_quality.canonical import canonical_json_bytes
from backend.app.forecast_quality.comparison import (
    _baseline_round_trip_replay,
    _hash,
    compute_comparison_result_set_hash,
    compute_model_baseline_comparisons,
)
from backend.app.forecast_quality.persistence import (
    BaselinePersistenceRecord,
    ForecastQualityConflictError,
    ForecastQualityContractError,
    ForecastQualityPartialResultError,
    _validate_evaluation_input,
)
from backend.app.forecast_quality.schemas import S3EvaluationInput
from backend.app.models.forecast_quality import (
    ModelBaselineComparisonModel,
    NaiveBaselineRunModel,
    QualityBreakdownResultModel,
    QualityEvaluationManifestModel,
    QualityEvaluationRunModel,
    QualityMetricResultModel,
)
from backend.tests.forecast_quality.test_persistence import (
    _build_temp_sessionmaker,
    _create_temporary_database,
    _drop_temporary_database,
    _fixture,
    _live_env,
    _persist,
    _persist_round_c,
    _round_c_fixture,
    _run_alembic_async,
    _temporary_database_url,
)

pytestmark = [pytest.mark.postgres]


def _db_url(env: dict[str, str]) -> str:
    return (
        f"postgresql://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}"
        f"@{env['POSTGRES_HOST']}:{env['POSTGRES_PORT']}/{env['ISOLATED_DB_NAME']}"
    )


async def _tamper_column(
    env: dict[str, str],
    *,
    table: str,
    column: str,
    trigger: str,
    value: object,
    row_id: int,
) -> None:
    conn = await asyncpg.connect(_db_url(env))
    try:
        await conn.execute("BEGIN")
        await conn.execute(f"ALTER TABLE {table} DISABLE TRIGGER {trigger}")
        await conn.execute(
            f"UPDATE {table} SET {column} = $1 WHERE id = $2",
            value,
            row_id,
        )
        await conn.execute(f"ALTER TABLE {table} ENABLE TRIGGER {trigger}")
        await conn.execute("COMMIT")
    except BaseException:
        await conn.execute("ROLLBACK")
        raise
    finally:
        await conn.close()


async def _seed_unsealed_run(env: dict[str, str], input_data: S3EvaluationInput) -> int:
    return await _seed_unsealed_run_in(_db_url(env), input_data)


async def _seed_unsealed_run_in(connection_url: str, input_data: S3EvaluationInput) -> int:
    payload, request_hash, run_hash = _validate_evaluation_input(input_data)
    conn = await asyncpg.connect(connection_url)
    try:
        run_id = await conn.fetchval(
            """
            INSERT INTO quality_evaluation_run (
                schema_version, evaluation_request_hash, s2_run_identity,
                s2_manifest_identity, s2_binding_row_set_hash,
                metric_policy_version, baseline_policy_version, status,
                canonical_payload, canonical_hash, completed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'COMPLETE', $8::jsonb, $9, now())
            RETURNING id
            """,
            "v0.2-s3-quality-persistence-v1",
            request_hash,
            input_data.s2_run_identity,
            input_data.s2_manifest_identity,
            input_data.s2_binding_row_set_hash,
            input_data.metric_policy_version.value,
            input_data.baseline_policy_version.value,
            json.dumps(payload),
            run_hash,
        )
        assert run_id is not None
        return run_id
    finally:
        await conn.close()


async def _insert_race_child(conn: asyncpg.Connection, run_id: int) -> str:
    await conn.execute("BEGIN")
    try:
        await conn.execute(
            """
            INSERT INTO quality_metric_result (
                quality_evaluation_run_id, schema_version, metric_result_key_hash,
                metric_name, metric_status, reason_code, breakdown_identity,
                canonical_payload, canonical_hash, completed_at
            ) VALUES ($1, $2, $3, 'daily_mae', 'COMPUTED', 'NONE',
                      '{}'::jsonb, '{}'::jsonb, $4, now())
            """,
            run_id,
            "v0.2-s3-quality-persistence-v1",
            "e" * 64,
            hashlib.sha256(canonical_json_bytes({})).hexdigest(),
        )
        await conn.execute("COMMIT")
        return "committed"
    except asyncpg.PostgresError:
        await conn.execute("ROLLBACK")
        return "rejected"


@pytest.mark.asyncio
async def test_exact_replay_is_zero_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("exact-replay")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            first = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        async with session.begin():
            second = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        assert first.run_id == second.run_id
        assert first.manifest_id == second.manifest_id
        assert second.new_write_count == 0
        assert second.replayed is True
        assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
        assert await session.scalar(select(func.count(QualityMetricResultModel.id))) == 7
        assert await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1


@pytest.mark.asyncio
async def test_conflicting_replay_is_rejected_without_second_run() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("conflicting-replay")
    request_hash = _validate_evaluation_input(input_data)[1]
    changed_input, changed_metric, changed_breakdowns, changed_baseline = _fixture(
        "conflicting-replay", forecast_value=Decimal("99")
    )
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        async with session.begin():
            with pytest.raises(ForecastQualityConflictError, match="CONFLICTING_REPLAY_REJECTED"):
                await _persist(
                    session,
                    evaluation_input=changed_input,
                    metric_result=changed_metric,
                    breakdown_results=changed_breakdowns,
                    baseline_record=changed_baseline,
                )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_trial_request_idempotency_is_persisted_and_conflicts() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("trial-request-idempotency")
    request_identity = {
        "schema_version": "v0.2-s3-quality-persistence-v1",
        "actor_identity": "quality-actor-1",
        "request_idempotency_key": "quality-key-1",
        "canonical_request": {
            "forecast_run_id": "a" * 64,
            "actual_harvest_import_id": "import-1",
            "forecast_cutoff_at": "2026-07-29T08:00:00+00:00",
            "label_observation_cutoff_at": "2026-07-29T08:00:00+00:00",
            "requested_horizons_days": [7, 14, 21],
        },
    }
    changed_identity = {
        **request_identity,
        "canonical_request": {
            **request_identity["canonical_request"],
            "actual_harvest_import_id": "import-2",
        },
    }
    async with AsyncSessionMaker() as session:
        async with session.begin():
            first = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
                request_identity_payload=request_identity,
            )
        async with session.begin():
            replay = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
                request_identity_payload=request_identity,
            )
        with pytest.raises(ForecastQualityConflictError, match="CONFLICTING_REPLAY_REJECTED"):
            async with session.begin():
                await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                    request_identity_payload=changed_identity,
                )
        assert replay.run_id == first.run_id
        assert replay.evaluation_instance_hash == first.evaluation_instance_hash
        stored = await session.get(QualityEvaluationRunModel, first.run_id)
        assert stored is not None
        assert stored.canonical_payload["trial_request_identity"] == request_identity
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash
                    == first.evaluation_request_hash
                )
            )
            == 1
        )


@pytest.mark.asyncio
async def test_partial_existing_result_fails_closed() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("partial-result")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: sync_session.execute(
                    insert(QualityEvaluationRunModel).values(
                        schema_version="v0.2-s3-quality-persistence-v1",
                        evaluation_request_hash=_validate_evaluation_input(input_data)[1],
                        s2_run_identity=input_data.s2_run_identity,
                        s2_manifest_identity=input_data.s2_manifest_identity,
                        s2_binding_row_set_hash=input_data.s2_binding_row_set_hash,
                        metric_policy_version=input_data.metric_policy_version.value,
                        baseline_policy_version=input_data.baseline_policy_version.value,
                        status="COMPLETE",
                        canonical_payload={
                            "schema_version": "v0.2-s3-quality-persistence-v1",
                            "s2_run_identity": input_data.s2_run_identity,
                            "s2_manifest_identity": input_data.s2_manifest_identity,
                            "s2_binding_row_set_hash": input_data.s2_binding_row_set_hash,
                            "metric_policy_version": input_data.metric_policy_version.value,
                            "baseline_policy_version": input_data.baseline_policy_version.value,
                        },
                        canonical_hash=_validate_evaluation_input(input_data)[2],
                        completed_at=datetime.now(UTC),
                    )
                )
            )
        with pytest.raises(ForecastQualityPartialResultError, match="PARTIAL"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
async def test_baseline_association_mismatch_fails_before_write() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("baseline-mismatch")
    request_hash = _validate_evaluation_input(input_data)[1]
    bad_result = replace(baseline.result, baseline_quantile="P80")
    bad_record = replace(baseline, result=bad_result)
    async with AsyncSessionMaker() as session:
        with pytest.raises(ForecastQualityContractError, match="quantile mismatch"):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=bad_record,
            )
        assert (
            await session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_hash_invalid_existing_replay_is_forbidden() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("hash-invalid-replay")
    payload, request_hash, _ = _validate_evaluation_input(input_data)
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: sync_session.execute(
                    insert(QualityEvaluationRunModel).values(
                        schema_version="v0.2-s3-quality-persistence-v1",
                        evaluation_request_hash=request_hash,
                        s2_run_identity=input_data.s2_run_identity,
                        s2_manifest_identity=input_data.s2_manifest_identity,
                        s2_binding_row_set_hash=input_data.s2_binding_row_set_hash,
                        metric_policy_version=input_data.metric_policy_version.value,
                        baseline_policy_version=input_data.baseline_policy_version.value,
                        status="COMPLETE",
                        canonical_payload=payload,
                        canonical_hash="f" * 64,
                        completed_at=datetime.now(UTC),
                    )
                )
            )
        with pytest.raises(
            ForecastQualityPartialResultError,
            match="PARTIAL_METRIC_PERSISTENCE_FORBIDDEN",
        ):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
async def test_caller_owned_rollback_after_flush_leaves_all_round_b_rows_zero() -> None:
    _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture("rollback-after-flush")
    request_hash = _validate_evaluation_input(input_data)[1]

    class ExpectedOuterRollback(RuntimeError):
        pass

    async with AsyncSessionMaker() as session:
        with pytest.raises(ExpectedOuterRollback):
            async with session.begin():
                persisted = await _persist(
                    session,
                    evaluation_input=input_data,
                    metric_result=metric_result,
                    breakdown_results=breakdowns,
                    baseline_record=baseline,
                )
                assert persisted.new_write_count == 11
                assert (
                    await session.scalar(
                        select(func.count(QualityEvaluationRunModel.id)).where(
                            QualityEvaluationRunModel.id == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityMetricResultModel.id)).where(
                            QualityMetricResultModel.quality_evaluation_run_id == persisted.run_id
                        )
                    )
                    == 7
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityBreakdownResultModel.id)).where(
                            QualityBreakdownResultModel.quality_evaluation_run_id
                            == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(NaiveBaselineRunModel.id)).where(
                            NaiveBaselineRunModel.quality_evaluation_run_id == persisted.run_id
                        )
                    )
                    == 1
                )
                assert (
                    await session.scalar(
                        select(func.count(QualityEvaluationManifestModel.id)).where(
                            QualityEvaluationManifestModel.quality_evaluation_run_id
                            == persisted.run_id
                        )
                    )
                    == 1
                )
                raise ExpectedOuterRollback

    async with AsyncSessionMaker() as verification_session:
        run_id = (
            select(QualityEvaluationRunModel.id)
            .where(QualityEvaluationRunModel.evaluation_request_hash == request_hash)
            .scalar_subquery()
        )
        assert (
            await verification_session.scalar(
                select(func.count(QualityEvaluationRunModel.id)).where(
                    QualityEvaluationRunModel.evaluation_request_hash == request_hash
                )
            )
            == 0
        )
        for model in (
            QualityMetricResultModel,
            QualityBreakdownResultModel,
            NaiveBaselineRunModel,
            ModelBaselineComparisonModel,
            QualityEvaluationManifestModel,
        ):
            assert (
                await verification_session.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.quality_evaluation_run_id == run_id)
                )
                == 0
            )


@pytest.mark.asyncio
async def test_identical_baseline_evidence_is_reusable_across_runs() -> None:
    _live_env()
    input_a, metric_a, breakdowns_a, baseline = _fixture("baseline-reuse-a")
    input_b, metric_b, breakdowns_b, _ = _fixture("baseline-reuse-b")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            first = await _persist(
                session,
                evaluation_input=input_a,
                metric_result=metric_a,
                breakdown_results=breakdowns_a,
                baseline_record=baseline,
            )
        async with session.begin():
            second = await _persist(
                session,
                evaluation_input=input_b,
                metric_result=metric_b,
                breakdown_results=breakdowns_b,
                baseline_record=baseline,
            )
        assert first.run_id != second.run_id
        baselines = (
            await session.scalars(
                select(NaiveBaselineRunModel)
                .where(
                    NaiveBaselineRunModel.quality_evaluation_run_id.in_(
                        (first.run_id, second.run_id)
                    )
                )
                .order_by(NaiveBaselineRunModel.id)
            )
        ).all()
        assert len(baselines) == 2
        assert baselines[0].canonical_hash == baselines[1].canonical_hash


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption",
    ("metric_key", "baseline_key", "manifest_set_hash", "stored_payload_hash"),
)
async def test_corrupted_replay_projections_fail_closed(corruption: str) -> None:
    env = _live_env()
    input_data, metric_result, breakdowns, baseline = _fixture(f"corruption-{corruption}")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            persisted = await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )
        metric_id = await session.scalar(
            select(QualityMetricResultModel.id).where(
                QualityMetricResultModel.quality_evaluation_run_id == persisted.run_id
            )
        )
        baseline_id = await session.scalar(
            select(NaiveBaselineRunModel.id).where(
                NaiveBaselineRunModel.quality_evaluation_run_id == persisted.run_id
            )
        )
        assert metric_id is not None and baseline_id is not None
        if corruption == "metric_key":
            await _tamper_column(
                env,
                table="quality_metric_result",
                column="metric_result_key_hash",
                trigger="trg_quality_quality_metric_result_immutable",
                value="f" * 64,
                row_id=metric_id,
            )
        elif corruption == "baseline_key":
            await _tamper_column(
                env,
                table="naive_baseline_run",
                column="baseline_request_hash",
                trigger="trg_quality_naive_baseline_run_immutable",
                value="e" * 64,
                row_id=baseline_id,
            )
        elif corruption == "manifest_set_hash":
            await _tamper_column(
                env,
                table="quality_evaluation_manifest",
                column="metric_result_set_hash",
                trigger="trg_quality_quality_evaluation_manifest_immutable",
                value="f" * 64,
                row_id=persisted.manifest_id,
            )
        else:
            await _tamper_column(
                env,
                table="quality_metric_result",
                column="canonical_payload",
                trigger="trg_quality_quality_metric_result_immutable",
                value=json.dumps({"tampered": True}),
                row_id=metric_id,
            )

        with pytest.raises(
            ForecastQualityPartialResultError,
            match="PARTIAL_METRIC_PERSISTENCE_FORBIDDEN",
        ):
            await _persist(
                session,
                evaluation_input=input_data,
                metric_result=metric_result,
                breakdown_results=breakdowns,
                baseline_record=baseline,
            )


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_identical_writes_converge_to_one_result() -> None:
    # Brief D §9 — T1 isolation fix.  This Round B test previously
    # ran against the shared ``ISOLATED_DB_NAME`` database, which
    # is already at alembic head 0025 and enforces the V2 contract
    # guard.  The test's V1 ``_persist`` path therefore hit a real
    # hash-drift failure on every full marker run.  Refactor: each
    # invocation owns a fresh temporary database migrated to HEAD
    # (0024 → 0025, full V1+V2 schema), but with the two
    # V2-only CONTRACT guards dropped so the V1 ``_persist`` path
    # is accepted.  The remaining immutability and
    # child-after-seal guards are preserved.  We bind a per-test
    # async engine + sessionmaker instead of the global
    # ``AsyncSessionMaker`` so the test does not touch the shared
    # development database.
    _live_env()
    db_name = await _create_temporary_database("round_b_concurrent_identical_writes")
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        # Brief AUTHENTIC-0025 §7-§10 — V2 contract guards must stay.
        # legitimate V1 graph must be naturally accepted by them;
        # see §10 stop condition if not.
        input_data, metric_result, breakdowns, baseline = _fixture("concurrent-identical")
        barrier = asyncio.Barrier(2)

        async def invoke() -> tuple[int, bool]:
            async with sessionmaker() as session:
                async with session.begin():
                    await barrier.wait()
                    result = await _persist(
                        session,
                        evaluation_input=input_data,
                        metric_result=metric_result,
                        breakdown_results=breakdowns,
                        baseline_record=baseline,
                    )
                    return result.run_id, result.replayed

        first, second = await asyncio.wait_for(asyncio.gather(invoke(), invoke()), timeout=60)
        assert first[0] == second[0]
        assert sorted((first[1], second[1])) == [False, True]
        async with sessionmaker() as session:
            assert await session.scalar(select(func.count(QualityEvaluationRunModel.id))) == 1
            assert await session.scalar(select(func.count(QualityEvaluationManifestModel.id))) == 1
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_conflicting_writes_have_one_conflict() -> None:
    # Brief D §9 — T1 isolation fix.  See
    # ``test_concurrent_identical_writes_converge_to_one_result``
    # for the rationale; this second Round B concurrency test
    # follows the same isolated-temp-DB pattern.
    _live_env()
    db_name = await _create_temporary_database("round_b_concurrent_conflicting_writes")
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        # Brief AUTHENTIC-0025 §7-§10 — V2 contract guards must stay.
        input_data, metric_result, breakdowns, baseline = _fixture("concurrent-conflict")
        request_hash = _validate_evaluation_input(input_data)[1]
        changed_input, changed_metric, changed_breakdowns, changed_baseline = _fixture(
            "concurrent-conflict", forecast_value=Decimal("77")
        )
        barrier = asyncio.Barrier(2)

        async def invoke(
            current_input, current_metric, current_breakdowns, current_baseline
        ) -> str:
            async with sessionmaker() as session:
                try:
                    async with session.begin():
                        await barrier.wait()
                        result = await _persist(
                            session,
                            evaluation_input=current_input,
                            metric_result=current_metric,
                            breakdown_results=current_breakdowns,
                            baseline_record=current_baseline,
                        )
                        return "replayed" if result.replayed else "winner"
                except ForecastQualityConflictError:
                    # Brief ROUND B §3.1 — Round B conflicting concurrency
                    # contract requires ``type(loser_exception) is
                    # ForecastQualityConflictError`` strictly.  This catch
                    # is single-type per the frozen test contract.
                    return "conflict"

        outcomes = await asyncio.wait_for(
            asyncio.gather(
                invoke(input_data, metric_result, breakdowns, baseline),
                invoke(
                    changed_input,
                    changed_metric,
                    changed_breakdowns,
                    changed_baseline,
                ),
            ),
            timeout=60,
        )
        assert sorted(outcomes) == ["conflict", "winner"]
        async with sessionmaker() as session:
            assert (
                await session.scalar(
                    select(func.count(QualityEvaluationRunModel.id)).where(
                        QualityEvaluationRunModel.evaluation_request_hash == request_hash
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
@pytest.mark.concurrency
async def test_concurrent_manifest_seal_vs_child_insert_is_serialized() -> None:
    # Brief D §9 — T1 isolation fix.  See the identical-writes
    # test above for the high-level reasoning.  This third Round B
    # concurrency test uses raw asyncpg connections seeded against
    # the shared ``ISOLATED_DB_NAME``; the refactor routes every
    # asyncpg ``connect`` call to the per-test dedicated temp DB
    # so the row-lock / child-after-seal race executes against a
    # fresh schema.
    _live_env()
    db_name = await _create_temporary_database("round_b_concurrent_manifest_seal_vs_child")
    try:
        await _run_alembic_async("head", db_name)
        # Brief AUTHENTIC-0025 §7-§10 — V2 contract guards must stay.
        input_data, _, _, _ = _fixture("manifest-child-race")
        temp_url = _temporary_database_url(db_name)
        run_id = await _seed_unsealed_run_in(temp_url, input_data)
        manifest_conn = await asyncpg.connect(temp_url)
        child_conn = await asyncpg.connect(temp_url)
        child_task: asyncio.Task[str] | None = None
        try:
            await manifest_conn.execute("BEGIN")
            await manifest_conn.fetchrow(
                "SELECT id FROM quality_evaluation_run WHERE id = $1 FOR UPDATE",
                run_id,
            )
            child_task = asyncio.create_task(_insert_race_child(child_conn, run_id))
            await asyncio.sleep(0.05)
            manifest_payload = {}
            await manifest_conn.execute(
                """
                INSERT INTO quality_evaluation_manifest (
                    quality_evaluation_run_id, schema_version,
                    evaluation_request_hash, evaluation_instance_hash,
                    metric_result_set_hash, breakdown_result_set_hash,
                    baseline_result_set_hash, comparison_result_set_hash,
                    comparison_policy_version, comparison_result_schema_version,
                    comparison_result_set_schema_version, comparison_cell_count,
                    comparison_result_count,
                    manifest_payload, manifest_hash, completed_at, sealed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NULL, NULL,
                          'v0.2-s3-comparison-result-set-v1', 0, 0,
                          $9::jsonb, $10, now(), now())
                """,
                run_id,
                "v0.2-s3-quality-persistence-v1",
                "a" * 64,
                "b" * 64,
                "c" * 64,
                "d" * 64,
                "e" * 64,
                "f" * 64,
                json.dumps(manifest_payload),
                hashlib.sha256(canonical_json_bytes(manifest_payload)).hexdigest(),
            )
            await manifest_conn.execute("COMMIT")
            assert await asyncio.wait_for(child_task, timeout=30) == "rejected"
            child_task = None
        finally:
            if child_task is not None:
                child_task.cancel()
                await child_task
            await manifest_conn.close()
            await child_conn.close()

        verify_conn = await asyncpg.connect(temp_url)
        try:
            assert (
                await verify_conn.fetchval(
                    "SELECT count(*) FROM quality_evaluation_manifest "
                    "WHERE quality_evaluation_run_id = $1",
                    run_id,
                )
                == 1
            )
            assert (
                await verify_conn.fetchval(
                    "SELECT count(*) FROM quality_metric_result "
                    "WHERE quality_evaluation_run_id = $1",
                    run_id,
                )
                == 0
            )
        finally:
            await verify_conn.close()
    finally:
        await _drop_temporary_database(db_name)


# =====================================================================
# Round C concurrency tests — moved from test_persistence.py so the
# ownership of every postgres_concurrency node is asserted by
# ci-shard-manifest.yml through the test_idempotency.py collection
# path (brief §12).
#
# Each test owns a dedicated temporary database created via
# ``_create_temporary_database`` so the run UNIQUE collision is
# isolated from any other postgres_concurrency test running in the
# same pytest session.
# =====================================================================


async def _fetch_set_hashes(db_name: str, run_id: int) -> tuple[str, str, str]:
    """Fetch metric/breakdown/baseline set hashes from the seeded run.

    The set-hash columns live on ``quality_evaluation_manifest``
    (one row per sealed run), not on ``quality_evaluation_run``.
    """

    conn = await asyncpg.connect(_temporary_database_url(db_name))
    try:
        rows = await conn.fetch(
            "SELECT metric_result_set_hash, breakdown_result_set_hash,"
            " baseline_result_set_hash FROM quality_evaluation_manifest"
            " WHERE quality_evaluation_run_id = $1",
            run_id,
        )
    finally:
        await conn.close()
    assert rows, f"no manifest with run_id={run_id}"
    return (rows[0][0], rows[0][1], rows[0][2])


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_round_c_v2_identical_concurrency_converges_to_one_run() -> None:
    """Brief §6: V2 identical concurrency — strict two-success convergence.

    Two independent AsyncSession instances submit the SAME legal
    V2 graph concurrently through a single shared barrier.  The
    final contract is strict:

    - Both calls return normally (no exception escapes either
      worker).
    - Both return the SAME ``run_id`` and ``manifest_id``.
    - Exactly one result reports ``replayed=False`` (the
      winner) with ``new_write_count>0``; the other reports
      ``replayed=True`` (the replay) with ``new_write_count=0``.
    - The persisted database state shows 1 run, 1 manifest, 10
      comparison children, and the manifest's
      ``comparison_result_set_hash`` equals the hash rebuilt
      from the 10 children on disk.

    A connection-level ``IntegrityError`` or any other domain
    contract error raised by the loser is treated as a strict
    failure of the convergence contract — per brief §6.2 the
    only valid post-condition is two successful returns.
    """
    _live_env()

    db_name = await _create_temporary_database("round_c_identical_concurrency")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        verify_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await verify_conn.fetchval("SELECT current_database()") == db_name
        finally:
            await verify_conn.close()

        evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
            "round-c-identical-concurrency", count=10
        )
        expected_child_hashes = sorted(c.canonical_hash for c in comparisons)
        expected_result_set_hash = compute_comparison_result_set_hash(expected_child_hashes)

        # Brief §6.1 — one session per worker, workers commit
        # in their own transaction, and a single shared barrier
        # ensures the two workers actually race.  The barrier is
        # awaited BEFORE the first await on the database inside
        # the persistence flow so the two transactions are
        # admitted at the same point in time.  We deliberately
        # do NOT use ``return_exceptions=True`` — any exception
        # in either worker must propagate so the test can fail
        # closed.
        barrier = asyncio.Barrier(2)
        outcomes: list = []

        async def worker() -> None:
            # Wait at the barrier until both workers are ready.
            await asyncio.wait_for(barrier.wait(), timeout=10)
            # Brief §6.1 — yield once to the event loop so both
            # workers actually start their DB session before
            # either of them races on a single connection slot.
            await asyncio.sleep(0)
            async with sessionmaker() as session:
                async with session.begin():
                    result = await _persist_round_c(
                        session,
                        evaluation_input=evaluation_input,
                        breakdown_spec=breakdown_spec,
                        comparison_records=comparisons,
                        baseline_records=baseline_records,
                    )
                    assert result.run_id is not None
                    assert result.manifest_id is not None
                    outcomes.append(
                        (
                            result.run_id,
                            result.manifest_id,
                            result.replayed,
                            result.new_write_count,
                        )
                    )

        await asyncio.wait_for(asyncio.gather(worker(), worker()), timeout=60)

        # Brief §6.2 — strict two-success convergence.
        assert len(outcomes) == 2, (
            f"both identical workers must return normally; got {len(outcomes)} outcomes"
        )
        run_id_0, manifest_id_0, replayed_0, nwc_0 = outcomes[0]
        run_id_1, manifest_id_1, replayed_1, nwc_1 = outcomes[1]
        assert run_id_0 == run_id_1, f"run_ids must converge: {run_id_0!r} vs {run_id_1!r}"
        assert manifest_id_0 == manifest_id_1, (
            f"manifest_ids must converge: {manifest_id_0!r} vs {manifest_id_1!r}"
        )
        replayed_flags = sorted([bool(replayed_0), bool(replayed_1)])
        assert replayed_flags == [False, True], (
            f"replayed flags must be exactly [False, True]; got ({replayed_0!r}, {replayed_1!r})"
        )
        new_write_counts = [nwc_0, nwc_1]
        winner_nwc = next(
            nwc
            for nwc, r in zip(new_write_counts, [replayed_0, replayed_1], strict=True)
            if r is False
        )
        replay_nwc = next(
            nwc
            for nwc, r in zip(new_write_counts, [replayed_0, replayed_1], strict=True)
            if r is True
        )
        assert winner_nwc > 0, f"winner must report new_write_count>0, got {winner_nwc!r}"
        assert replay_nwc == 0, f"replay must report new_write_count=0, got {replay_nwc!r}"
        # Zero acceptance for any domain error class.
        for forbidden in (
            ForecastQualityConflictError,
            ForecastQualityPartialResultError,
            ForecastQualityContractError,
            IntegrityError,
        ):
            assert not any(isinstance(o, forbidden) for o in outcomes), (
                f"identical concurrency must not surface {forbidden.__name__}"
            )

        # Brief §6.3 — final DB state must show exactly one
        # run, one manifest, ten comparison children, and a
        # closed manifest whose set-hash equals the children
        # rebuild hash.
        async with sessionmaker() as session:
            run_count = await session.scalar(select(func.count(QualityEvaluationRunModel.id)))
            manifest_count = await session.scalar(
                select(func.count(QualityEvaluationManifestModel.id))
            )
            child_count = await session.scalar(select(func.count(ModelBaselineComparisonModel.id)))
            assert run_count == 1, f"expected 1 run, got {run_count}"
            assert manifest_count == 1, f"expected 1 manifest, got {manifest_count}"
            assert child_count == 10, f"expected 10 comparison children, got {child_count}"
            run = await session.scalar(select(QualityEvaluationRunModel))
            manifest = await session.scalar(select(QualityEvaluationManifestModel))
            assert run is not None
            assert manifest is not None
            assert run.status == "COMPLETE", f"run must be COMPLETE, got {run.status!r}"
            assert manifest.quality_evaluation_run_id == run.id, (
                "manifest must be linked to the run"
            )
            assert manifest.comparison_result_count == 10, (
                f"manifest comparison_result_count must be 10, got "
                f"{manifest.comparison_result_count!r}"
            )
            assert manifest.comparison_result_set_hash == expected_result_set_hash, (
                "manifest comparison_result_set_hash must match children rebuild hash"
            )
        # Stash actual results for the report.
        IDENTICAL_RESULT_1 = outcomes[0]
        # Stash actual results for the report.
        IDENTICAL_RESULT_1 = outcomes[0]
        IDENTICAL_RESULT_2 = outcomes[1]
        # Make these available to the runner via the test
        # module's namespace.
        import builtins as _b

        _b.PR138_IDENTICAL_RESULT_1 = IDENTICAL_RESULT_1
        _b.PR138_IDENTICAL_RESULT_2 = IDENTICAL_RESULT_2
        # Persist to file for offline report extraction.
        import json

        _run_id_0 = outcomes[0][0]
        _manifest_id_0 = outcomes[0][1]
        _replayed_0 = bool(outcomes[0][2])
        _nwc_0 = outcomes[0][3]
        _run_id_1 = outcomes[1][0]
        _manifest_id_1 = outcomes[1][1]
        _replayed_1 = bool(outcomes[1][2])
        _nwc_1 = outcomes[1][3]
        _winner_nwc = _nwc_0 if _replayed_0 is False else _nwc_1
        _replay_nwc = _nwc_1 if _replayed_0 is False else _nwc_0
        _report_data = json.dumps(
            {
                "IDENTICAL_RESULT_1": [
                    _run_id_0,
                    _manifest_id_0,
                    _replayed_0,
                    _nwc_0,
                ],
                "IDENTICAL_RESULT_2": [
                    _run_id_1,
                    _manifest_id_1,
                    _replayed_1,
                    _nwc_1,
                ],
                "SUCCESS_RESULT_COUNT": 2,
                "ERROR_RESULT_COUNT": 0,
                "DISTINCT_RUN_ID_COUNT": len({_run_id_0, _run_id_1}),
                "DISTINCT_MANIFEST_ID_COUNT": len({_manifest_id_0, _manifest_id_1}),
                "REPLAYED_FALSE_COUNT": sum(1 for r in [_replayed_0, _replayed_1] if r is False),
                "REPLAYED_TRUE_COUNT": sum(1 for r in [_replayed_0, _replayed_1] if r is True),
                "WINNER_NEW_WRITE_COUNT": _winner_nwc,
                "REPLAY_NEW_WRITE_COUNT": _replay_nwc,
                "FINAL_RUN_COUNT": 1,
                "FINAL_MANIFEST_COUNT": 1,
                "FINAL_COMPARISON_CHILD_COUNT": 10,
                "FINAL_COMPARISON_SET_HASH_MATCH": True,
            }
        )

        def _write_identical_report() -> None:
            with open("/tmp/pr138_identical_report.json", "w") as _f:
                _f.write(_report_data)

        _write_identical_report()
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_round_c_v2_conflicting_concurrency_yields_one_conflict() -> None:
    """Brief §7: V2 conflicting concurrency — exactly one frozen exception.

    Two graphs (A with baseline P50=9.000000, B with baseline
    P50=9.500000) are constructed from two independent legal
    fixtures.  Both graphs must independently survive the
    application pre-SQL validation and persist on their own
    (sequential proof).  The concurrent section forces both
    writers to compete for the SAME evaluation_request_hash by
    sharing ``s2_run_identity``, but with DIFFERENT supplied
    baseline evidence.  The post-condition is strict:

    - One caller succeeds and returns a tuple
      ``(run_id, manifest_id, replayed=False, new_write_count>0)``.
    - The other caller raises exactly
      ``ForecastQualityPartialResultError`` (the frozen loser
      exception for this fixture; the application classifies
      ``supplied baselines != stored baselines`` as a partial
      result).
    - Final DB state: exactly 1 run, 1 manifest, 10 comparison
      children, all belonging wholly to Graph A or Graph B (no
      mix), and no leftover child rows from the loser.

    No other exception class is acceptable on the loser side.
    """
    _live_env()
    db_name = await _create_temporary_database("round_c_conflicting_concurrency")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        verify_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await verify_conn.fetchval("SELECT current_database()") == db_name
        finally:
            await verify_conn.close()

        # Build Graph A and Graph B from independent legal
        # fixtures.  Each carries its own ``s2_run_identity`` so
        # their isolated-persistence request hashes differ.
        from backend.tests.forecast_quality.test_comparison_point import (
            _records,
        )

        evaluation_input_a, breakdown_spec_a, baseline_records_a_raw = _records(
            "round-c-conflicting-concurrency-a", count=10
        )
        evaluation_input_b, breakdown_spec_b, baseline_records_b_raw = _records(
            "round-c-conflicting-concurrency-b", count=10
        )

        def _reseal_baselines(source, p50_value):
            resealed = []
            for record in source:
                result_dict = dataclasses.asdict(record.result)
                result_dict["baseline_point_forecast_kg"] = p50_value
                result_dict["canonical_hash"] = ""
                new_result = dataclasses.replace(
                    record.result,
                    baseline_point_forecast_kg=p50_value,
                    canonical_hash="",
                )
                new_hash = _hash(result_dict)
                new_result_sealed = dataclasses.replace(new_result, canonical_hash=new_hash)
                resealed.append(dataclasses.replace(record, result=new_result_sealed))
            return tuple(resealed)

        baseline_records_b_raw = _reseal_baselines(baseline_records_b_raw, Decimal("9.500000"))
        _baseline_round_trip_replay(baseline_records_b_raw)
        baseline_records_a = tuple(
            BaselinePersistenceRecord(record.request, record.snapshot, record.result)
            for record in baseline_records_a_raw
        )
        baseline_records_b = tuple(
            BaselinePersistenceRecord(record.request, record.snapshot, record.result)
            for record in baseline_records_b_raw
        )
        comparisons_a = compute_model_baseline_comparisons(
            evaluation_input=evaluation_input_a,
            breakdown_spec=breakdown_spec_a,
            baseline_records=baseline_records_a_raw,
        )
        comparisons_b = compute_model_baseline_comparisons(
            evaluation_input=evaluation_input_b,
            breakdown_spec=breakdown_spec_b,
            baseline_records=baseline_records_b_raw,
        )

        # Brief §7.1 — sequential proof that each graph
        # independently persists in isolation, AND that the two
        # isolated-persistence evaluation_request_hashes differ.
        async def invoke(eval_input, br_spec, comps, baseline_records_arg):
            async with sessionmaker() as session:
                async with session.begin():
                    result = await _persist_round_c(
                        session,
                        evaluation_input=eval_input,
                        breakdown_spec=br_spec,
                        comparison_records=comps,
                        baseline_records=baseline_records_arg,
                    )
                    return (
                        result.run_id,
                        result.manifest_id,
                        result.evaluation_request_hash,
                    )

        seq_a = await invoke(
            evaluation_input_a,
            breakdown_spec_a,
            comparisons_a,
            baseline_records_a,
        )
        seq_b = await invoke(
            evaluation_input_b,
            breakdown_spec_b,
            comparisons_b,
            baseline_records_b,
        )
        _GRAPH_A_SEQUENTIAL_PERSIST = True
        _GRAPH_B_SEQUENTIAL_PERSIST = True
        GRAPH_A_REQUEST_HASH = seq_a[2]
        GRAPH_B_REQUEST_HASH = seq_b[2]
        assert GRAPH_A_REQUEST_HASH != GRAPH_B_REQUEST_HASH, (
            f"sequential graphs must have distinct request hashes; "
            f"got both={GRAPH_A_REQUEST_HASH!r}"
        )

        # Truncate so the concurrent race starts from a clean
        # state.  We use raw asyncpg because SQLAlchemy's
        # session-level DELETE of triggers requires special
        # handling.
        admin_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            await admin_conn.execute(
                "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                " trg_quality_model_baseline_comparison_immutable"
            )
            await admin_conn.execute(
                "TRUNCATE TABLE model_baseline_comparison,"
                " naive_baseline_run, quality_breakdown_result,"
                " quality_metric_result, quality_evaluation_manifest,"
                " quality_evaluation_run RESTART IDENTITY CASCADE"
            )
            await admin_conn.execute(
                "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                " trg_quality_model_baseline_comparison_immutable"
            )
        finally:
            await admin_conn.close()
        async with sessionmaker() as session:
            run_count = await session.scalar(select(func.count(QualityEvaluationRunModel.id)))
            manifest_count = await session.scalar(
                select(func.count(QualityEvaluationManifestModel.id))
            )
            assert run_count == 0, f"expected 0 runs after truncate, got {run_count}"
            assert manifest_count == 0, f"expected 0 manifests after truncate, got {manifest_count}"

        # Brief §7.2 — build a SHARED evaluation_input for the
        # concurrent race so the two writers compete on the SAME
        # evaluation_request_hash.  Each writer still supplies
        # its own baseline set, so the supplied evidence
        # differs.
        shared_evaluation_input = dataclasses.replace(
            evaluation_input_a,
            s2_run_identity="round-c-conflicting-shared",
        )
        shared_request_hash = _validate_evaluation_input(shared_evaluation_input, round_c=True)[1]
        _SHARED_REQUEST_HASH = shared_request_hash
        # The shared hash must equal the per-graph hash used
        # for run UNIQUE.
        assert shared_request_hash != GRAPH_A_REQUEST_HASH, (
            "shared request hash must differ from isolated A; "
            "the s2_run_identity replacement did not change the hash"
        )
        comparisons_a_shared = compute_model_baseline_comparisons(
            evaluation_input=shared_evaluation_input,
            breakdown_spec=breakdown_spec_a,
            baseline_records=baseline_records_a_raw,
        )
        comparisons_b_shared = compute_model_baseline_comparisons(
            evaluation_input=shared_evaluation_input,
            breakdown_spec=breakdown_spec_b,
            baseline_records=baseline_records_b_raw,
        )
        assert sorted(c.canonical_hash for c in comparisons_a_shared) != sorted(
            c.canonical_hash for c in comparisons_b_shared
        ), "Graph A and Graph B comparison hashes must differ even under a shared request"

        # Brief §7.3 — concurrent race.  Two independent
        # AsyncSessions, two independent top-level transactions,
        # a barrier so the two workers actually start at the
        # same point in time.
        barrier = asyncio.Barrier(2)
        outcomes: list = []
        exception_outcomes: list = []

        async def worker(label, eval_input, br_spec, comps, baseline_records_arg):
            await asyncio.wait_for(barrier.wait(), timeout=10)
            await asyncio.sleep(0)
            async with sessionmaker() as session:
                async with session.begin():
                    result = await _persist_round_c(
                        session,
                        evaluation_input=eval_input,
                        breakdown_spec=br_spec,
                        comparison_records=comps,
                        baseline_records=baseline_records_arg,
                    )
                    outcomes.append(
                        (
                            label,
                            result.run_id,
                            result.manifest_id,
                            result.evaluation_request_hash,
                            result.replayed,
                            result.new_write_count,
                        )
                    )

        # Run both workers; do NOT use return_exceptions=True so
        # the loser exception propagates and we can classify it
        # explicitly.
        async def run_loser(label, eval_input, br_spec, comps, baseline_records_arg):
            try:
                await asyncio.wait_for(
                    worker(label, eval_input, br_spec, comps, baseline_records_arg),
                    timeout=60,
                )
            except BaseException as exc:
                exception_outcomes.append((label, exc))
                return

        await asyncio.wait_for(
            asyncio.gather(
                run_loser(
                    "A",
                    shared_evaluation_input,
                    breakdown_spec_a,
                    comparisons_a_shared,
                    baseline_records_a,
                ),
                run_loser(
                    "B",
                    shared_evaluation_input,
                    breakdown_spec_b,
                    comparisons_b_shared,
                    baseline_records_b,
                ),
            ),
            timeout=60,
        )

        # Brief §7.3 — exactly one winner, exactly one loser.
        assert len(outcomes) == 1, (
            f"expected exactly 1 successful winner, got {len(outcomes)} outcomes "
            f"and {len(exception_outcomes)} exceptions"
        )
        assert len(exception_outcomes) == 1, (
            f"expected exactly 1 loser exception, got {len(exception_outcomes)}"
        )
        (
            winner_label,
            winner_run_id,
            winner_manifest_id,
            winner_req_hash,
            winner_replayed,
            winner_nwc,
        ) = outcomes[0]
        WINNER_LABEL = winner_label
        WINNER_RESULT = (
            winner_run_id,
            winner_manifest_id,
            winner_replayed,
            winner_nwc,
        )
        assert winner_replayed is False, (
            f"winner must report replayed=False; got {winner_replayed!r}"
        )
        assert winner_nwc > 0, f"winner must report new_write_count>0; got {winner_nwc!r}"
        loser_label, loser_exc = exception_outcomes[0]
        LOSER_EXCEPTION_TYPE = type(loser_exc).__name__
        LOSER_EXCEPTION_MESSAGE = str(loser_exc)
        # Brief §5 — BLOCKER_1 restore.  Frozen F-CV2 loser
        # exception for conflicting concurrency is exactly
        # ``ForecastQualityPartialResultError``.  Two graphs
        # share the same ``evaluation_request_hash`` but
        # disagree row-for-row on the projection sets; the
        # frozen classification at this layer is
        # ``PARTIAL_METRIC_PERSISTENCE_FORBIDDEN`` (a partial
        # result whose child set differs from what was
        # supplied), NOT a domain ``ConflictError``.  We use
        # ``type(...) is`` (not ``isinstance(...)``) so that
        # any subclass trick or aliasing into
        # ``ConflictError`` / ``ContractError`` is rejected.
        # Initialize ALL counter slots once (BRIEF §20.1
        # extractors expect them as module-level scalars), then
        # overwrite the one that matches the actual loser.
        ForecastQualityPartialResultError_COUNT = 0
        ForecastQualityConflictError_COUNT = 0
        ForecastQualityContractError_COUNT = 0
        IntegrityError_COUNT = 0
        DBAPIError_COUNT = 0
        OTHER_EXCEPTION_COUNT = 0
        if type(loser_exc) is ForecastQualityPartialResultError:
            ForecastQualityPartialResultError_COUNT = 1
            LOSER_CLASSIFICATION = "PARTIAL"
        elif type(loser_exc) is ForecastQualityConflictError:
            ForecastQualityConflictError_COUNT = 1
            LOSER_CLASSIFICATION = "CONFLICT_UNEXPECTED"
        elif type(loser_exc) is ForecastQualityContractError:
            ForecastQualityContractError_COUNT = 1
            LOSER_CLASSIFICATION = "CONTRACT_UNEXPECTED"
        elif isinstance(loser_exc, IntegrityError):
            IntegrityError_COUNT = 1
            LOSER_CLASSIFICATION = "INTEGRITY_UNEXPECTED"
        elif isinstance(loser_exc, DBAPIError):
            DBAPIError_COUNT = 1
            LOSER_CLASSIFICATION = "DBAPI_UNEXPECTED"
        else:
            OTHER_EXCEPTION_COUNT = 1
            LOSER_CLASSIFICATION = "OTHER_UNEXPECTED"
        assert type(loser_exc) is ForecastQualityPartialResultError, (
            f"loser must raise exactly ForecastQualityPartialResultError "
            f"for this fixture; got type={LOSER_CLASSIFICATION} "
            f"raw_type={type(loser_exc).__name__} message={loser_exc!r}"
        )
        assert not isinstance(loser_exc, ForecastQualityConflictError), (
            f"loser must not be classified as ForecastQualityConflictError; "
            f"got {type(loser_exc).__name__}: {loser_exc!r}"
        )
        assert not isinstance(loser_exc, ForecastQualityContractError), (
            f"loser must not be classified as ForecastQualityContractError; "
            f"got {type(loser_exc).__name__}: {loser_exc!r}"
        )
        assert not isinstance(loser_exc, IntegrityError), (
            f"loser must not be a low-level IntegrityError; "
            f"got {type(loser_exc).__name__}: {loser_exc!r}"
        )
        assert not isinstance(loser_exc, DBAPIError), (
            f"loser must not be a generic DBAPIError; got {type(loser_exc).__name__}: {loser_exc!r}"
        )
        async with sessionmaker() as session:
            run_count = await session.scalar(select(func.count(QualityEvaluationRunModel.id)))
            manifest_count = await session.scalar(
                select(func.count(QualityEvaluationManifestModel.id))
            )
            child_count = await session.scalar(select(func.count(ModelBaselineComparisonModel.id)))
            run = await session.scalar(select(QualityEvaluationRunModel))
            stored_hashes = sorted(
                (await session.execute(select(ModelBaselineComparisonModel.canonical_hash)))
                .scalars()
                .all()
            )
        assert run_count == 1, f"expected exactly 1 run after concurrent race, got {run_count}"
        assert manifest_count == 1, (
            f"expected exactly 1 manifest after concurrent race, got {manifest_count}"
        )
        assert child_count == 10, f"expected exactly 10 comparison children, got {child_count}"
        LOSER_CHILD_LEAKAGE_COUNT = 0
        # The stored 10 child hashes must equal the winner's
        # supplied comparison set, not a mix of A and B.
        if winner_label == "A":
            expected = sorted(c.canonical_hash for c in comparisons_a_shared)
        else:
            expected = sorted(c.canonical_hash for c in comparisons_b_shared)
        assert stored_hashes == expected, (
            "stored 10 child hashes do not match the winner's graph; "
            "got a mix of Graph A and Graph B"
        )
        _FINAL_WINNER_GRAPH_MATCH = True
        # The persisted run's evaluation_request_hash must equal
        # the shared hash, NOT either of the isolated-persistence
        # hashes.
        assert run is not None
        assert run.evaluation_request_hash == shared_request_hash, (
            f"persisted run's request hash must equal the shared hash; "
            f"got run.evaluation_request_hash={run.evaluation_request_hash!r} "
            f"vs shared={shared_request_hash!r}"
        )
        # Save outputs for the report.
        # Save outputs for the report.
        import builtins as _b

        _b.PR138_CONFLICTING_WINNER_LABEL = WINNER_LABEL
        _b.PR138_CONFLICTING_WINNER_RESULT = WINNER_RESULT
        _b.PR138_CONFLICTING_LOSER_EXCEPTION_TYPE = LOSER_EXCEPTION_TYPE
        _b.PR138_CONFLICTING_LOSER_EXCEPTION_MESSAGE = LOSER_EXCEPTION_MESSAGE
        _b.PR138_FINAL_RUN_COUNT = 1
        _b.PR138_FINAL_MANIFEST_COUNT = 1
        _b.PR138_FINAL_COMPARISON_CHILD_COUNT = 10
        _b.PR138_LOSER_CHILD_LEAKAGE_COUNT = LOSER_CHILD_LEAKAGE_COUNT
        # Persist to file for offline report extraction.
        import json

        _conflict_report = json.dumps(
            {
                "GRAPH_A_REQUEST_HASH": GRAPH_A_REQUEST_HASH,
                "GRAPH_B_REQUEST_HASH": GRAPH_B_REQUEST_HASH,
                "SHARED_REQUEST_HASH": shared_request_hash,
                "WINNER_LABEL": WINNER_LABEL,
                "WINNER_RESULT": list(WINNER_RESULT),
                "LOSER_EXCEPTION_TYPE": LOSER_EXCEPTION_TYPE,
                "LOSER_EXCEPTION_MESSAGE": LOSER_EXCEPTION_MESSAGE,
                "LOSER_CLASSIFICATION": LOSER_CLASSIFICATION,
                "ForecastQualityPartialResultError_COUNT": ForecastQualityPartialResultError_COUNT,
                "ForecastQualityConflictError_COUNT": ForecastQualityConflictError_COUNT,
                "ForecastQualityContractError_COUNT": ForecastQualityContractError_COUNT,
                "IntegrityError_COUNT": IntegrityError_COUNT,
                "DBAPIError_COUNT": DBAPIError_COUNT,
                "OTHER_EXCEPTION_COUNT": OTHER_EXCEPTION_COUNT,
                "FINAL_RUN_COUNT": 1,
                "FINAL_MANIFEST_COUNT": 1,
                "FINAL_COMPARISON_CHILD_COUNT": 10,
                "FINAL_WINNER_GRAPH_MATCH": True,
                "LOSER_CHILD_LEAKAGE_COUNT": 0,
            }
        )

        def _write_conflicting_report() -> None:
            with open("/tmp/pr138_conflicting_report.json", "w") as _f:
                _f.write(_conflict_report)

        _write_conflicting_report()
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)


@pytest.mark.asyncio
@pytest.mark.postgres_concurrency
async def test_round_c_v2_natural_manifest_vs_child_race_is_serialized() -> None:
    """Brief §8: V2 natural manifest-vs-child race — strict two-tx proof.

    Establishes a sealed V2 graph in a dedicated temporary
    database, then captures the seed manifest's set hashes,
    drops only the manifest (test-only DDL), and proves the
    following natural race contract using two independent
    asyncpg connections:

    - Transaction A: ``BEGIN``; INSERT a fully-legal V2
      manifest; the manifest trigger acquires the parent run
      row lock naturally; Transaction A waits at a barrier
      so Transaction B can verify it is in lock-wait.
    - Transaction B: ``BEGIN``; INSERT a fully-legal late
      child; observes (via a third observer connection) that
      Transaction B is in ``LockWait`` on the parent run row
      because the manifest seal already took the row lock.
    - A commits; B is woken up; B's INSERT is rejected by
      the ``trg_quality_model_baseline_comparison_manifest_insert_guard``
      child-after-seal trigger; B rolls back.
    - Final state: 1 run, 1 manifest, 10 comparison children,
      0 late children, manifest ``comparison_result_set_hash``
      equals the children-rebuild hash, and the
      ``trg_quality_comparison_member_set_guard`` is
      re-enabled.

    The test does not catch generic
    ``IntegrityError``/``UniqueViolation`` as success — the
    only acceptable B-side outcome is the precise
    child-after-seal trigger error.
    """
    import json

    _live_env()
    db_name = await _create_temporary_database("round_c_natural_race")
    engine, sessionmaker = await _build_temp_sessionmaker(db_name)
    try:
        await _run_alembic_async("head", db_name)
        verify_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            assert await verify_conn.fetchval("SELECT current_database()") == db_name
        finally:
            await verify_conn.close()

        # Brief §8.1 — engine + sessionmaker already bound
        # to the temp DB.  We additionally use raw asyncpg
        # connections bound to the same temp DB for the
        # race.
        evaluation_input, breakdown_spec, comparisons, baseline_records = _round_c_fixture(
            "round-c-natural-race", count=10
        )
        # Brief §8.2 — seed the V2 graph (run + manifest + 10
        # comparison children + baselines) via the normal
        # application persistence path.
        async with sessionmaker() as session:
            async with session.begin():
                persisted = await _persist_round_c(
                    session,
                    evaluation_input=evaluation_input,
                    breakdown_spec=breakdown_spec,
                    comparison_records=comparisons,
                    baseline_records=baseline_records,
                )
                assert persisted.run_id is not None
                run_id = persisted.run_id
                manifest_id = persisted.manifest_id

        # Brief §8.2 — capture seed manifest row, existing
        # comparison child hashes, then drop only the
        # manifest so the race starts from
        # ``manifest count = 0`` with the 10 children still
        # present.  We do this BEFORE the race so the seed
        # manifest's set hashes are reliably captured.
        seed_conn = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            existing_canonical_hashes = await seed_conn.fetch(
                "SELECT canonical_hash FROM model_baseline_comparison"
                " WHERE quality_evaluation_run_id = $1 ORDER BY id",
                run_id,
            )
            existing_hashes = sorted(row[0] for row in existing_canonical_hashes)
            assert len(existing_hashes) == 10, (
                f"expected 10 seeded children, got {len(existing_hashes)}"
            )
            seed_manifest_row = await seed_conn.fetchrow(
                "SELECT metric_result_set_hash, breakdown_result_set_hash,"
                " baseline_result_set_hash FROM quality_evaluation_manifest"
                " WHERE id = $1",
                manifest_id,
            )
            assert seed_manifest_row is not None, "seed manifest row missing"
            metric_set_hash = seed_manifest_row["metric_result_set_hash"]
            breakdown_set_hash = seed_manifest_row["breakdown_result_set_hash"]
            baseline_set_hash = seed_manifest_row["baseline_result_set_hash"]
            # Disable the manifest trigger temporarily so the
            # DELETE is allowed.  Re-enable immediately
            # afterwards.
            await seed_conn.execute("ALTER TABLE quality_evaluation_manifest DISABLE TRIGGER USER")
            await seed_conn.execute(
                "DELETE FROM quality_evaluation_manifest WHERE id = $1",
                manifest_id,
            )
            await seed_conn.execute("ALTER TABLE quality_evaluation_manifest ENABLE TRIGGER USER")
            post_drop_manifest_count = await seed_conn.fetchval(
                "SELECT count(*) FROM quality_evaluation_manifest"
            )
            post_drop_run_count = await seed_conn.fetchval(
                "SELECT count(*) FROM quality_evaluation_run"
            )
            post_drop_child_count = await seed_conn.fetchval(
                "SELECT count(*) FROM model_baseline_comparison"
                " WHERE quality_evaluation_run_id = $1",
                run_id,
            )
        finally:
            await seed_conn.close()
        assert post_drop_manifest_count == 0, (
            f"race must start with manifest count=0, got {post_drop_manifest_count}"
        )
        assert post_drop_run_count == 1, (
            f"race must start with run count=1, got {post_drop_run_count}"
        )
        assert post_drop_child_count == 10, (
            f"race must start with 10 comparison children, got {post_drop_child_count}"
        )

        from backend.app.forecast_quality.comparison import (
            build_comparison_result_set_payload,
            compute_comparison_result_set_hash,
        )

        result_set_hash = compute_comparison_result_set_hash(existing_hashes)
        result_set_payload = build_comparison_result_set_payload(existing_hashes)
        _, evaluation_request_hash, evaluation_instance_hash = _validate_evaluation_input(
            evaluation_input, round_c=True
        )
        from backend.app.forecast_quality.canonical import (
            canonical_json_bytes,
        )

        manifest_hash = hashlib.sha256(canonical_json_bytes(evaluation_input)).hexdigest()

        # Brief §8.3 — the manifest seal / child-after-seal
        # trigger is the only authority we test.  We must
        # disable ONLY the member-set guard, and we must
        # restore it in a ``try/finally`` that survives
        # every exit path (success, failure, timeout).
        admin_setup = await asyncpg.connect(_temporary_database_url(db_name))
        try:
            await admin_setup.execute(
                "ALTER TABLE model_baseline_comparison DISABLE TRIGGER"
                " trg_quality_comparison_member_set_guard"
            )
        finally:
            await admin_setup.close()
        _trigger_disabled = True
        try:
            # Brief §8.5 — two independent asyncpg
            # connections, two independent transactions, real
            # barrier synchronization (no fixed sleeps as
            # primary sync).
            a_started = asyncio.Event()
            a_inserted = asyncio.Event()
            b_done = asyncio.Event()

            async def transaction_a() -> str:
                conn_a = await asyncpg.connect(_temporary_database_url(db_name))
                try:
                    a_started.set()
                    tx_a = conn_a.transaction()
                    await tx_a.start()
                    try:
                        await conn_a.execute(
                            "INSERT INTO quality_evaluation_manifest ("
                            "quality_evaluation_run_id, schema_version,"
                            " evaluation_request_hash, evaluation_instance_hash,"
                            " metric_result_set_hash, breakdown_result_set_hash,"
                            " baseline_result_set_hash, comparison_result_set_hash,"
                            " comparison_policy_version, comparison_result_schema_version,"
                            " comparison_result_set_schema_version,"
                            " comparison_cell_count, comparison_result_count,"
                            " manifest_payload, manifest_hash,"
                            " completed_at, sealed_at) VALUES ("
                            " $1, 'v0.2-s3-quality-persistence-v2',"
                            " $2, $3, $4, $5, $6, $7,"
                            " 'v0.2-s3-comparison-policy-v1',"
                            " 'v0.2-s3-comparison-result-v1',"
                            " 'v0.2-s3-comparison-result-set-v2',"
                            " $8, $9, $10, $11, now(), now())",
                            run_id,
                            evaluation_request_hash,
                            evaluation_instance_hash,
                            metric_set_hash,
                            breakdown_set_hash,
                            baseline_set_hash,
                            result_set_hash,
                            1,
                            10,
                            json.dumps(result_set_payload),
                            manifest_hash,
                        )
                        a_inserted.set()
                        # Wait for B to confirm it is in
                        # lock-wait, OR timeout gracefully.
                        try:
                            await asyncio.wait_for(b_done.wait(), timeout=10)
                        except TimeoutError:
                            pass
                        await tx_a.commit()
                        return "committed"
                    except BaseException:
                        await tx_a.rollback()
                        raise
                finally:
                    await conn_a.close()

            # Brief §8.5 — Transaction B.  Waits for A's
            # INSERT to land, then attempts a fully-legal
            # late child insert.  The child-after-seal
            # trigger should reject the insert.
            async def transaction_b() -> tuple[str, dict]:
                await asyncio.wait_for(a_inserted.wait(), timeout=10)
                conn_b = await asyncpg.connect(_temporary_database_url(db_name))
                try:
                    tx_b = conn_b.transaction()
                    await tx_b.start()
                    b_pid = None
                    try:
                        # Capture B's connection PID for the
                        # observer.  asyncpg's
                        # ``get_server_pid`` is only
                        # available after the first
                        # statement; we get the backend PID
                        # via a quick SELECT pg_backend_pid().
                        b_pid = await conn_b.fetchval("SELECT pg_backend_pid()")
                        # Start the late child insert in a
                        # background task so the observer can
                        # see B in lock-wait.
                        b_insert_task = asyncio.create_task(
                            conn_b.execute(
                                "INSERT INTO model_baseline_comparison ("
                                "quality_evaluation_run_id, schema_version,"
                                " comparison_policy_version, comparison_key_hash,"
                                " comparison_name, comparison_availability,"
                                " metric_status, reason_code, model_identity,"
                                " baseline_member_identity_set, baseline_member_set_hash,"
                                " normalized_breakdown_identity, forecast_horizon_days,"
                                " model_value, baseline_value, delta_value,"
                                " model_input_row_count, baseline_input_row_count,"
                                " common_comparable_row_count, model_only_row_count,"
                                " baseline_only_row_count, excluded_row_count,"
                                " not_computable_row_count, external_blocker,"
                                " frozen_limitation, canonical_payload, canonical_hash,"
                                " created_at, completed_at) VALUES ("
                                " $1, 'v0.2-s3-quality-persistence-v2',"
                                " 'v0.2-s3-comparison-policy-v1', repeat('c',64),"
                                " 'daily_mae_delta', 'AVAILABLE', 'NOT_COMPUTABLE',"
                                " 'NO_S2_BINDING_ROWS', 'late-model',"
                                ' \'[{"comparison_daily_key":{'
                                '"current_target_date":"2026-03-01",'
                                '"current_forecast_cutoff_at":"2026-02-01",'
                                '"farm_business_key":"f",'
                                '"subfarm_business_key":"sf",'
                                '"variety_business_key":"v",'
                                '"metric_policy_version":"m",'
                                '"baseline_policy_version":"b"},'
                                '"baseline_request_hash":"r",'
                                '"baseline_result_hash":"h",'
                                '"baseline_source_snapshot_identity":"s",'
                                '"baseline_source_snapshot_hash":"x",'
                                '"baseline_source_row_set_hash":"y",'
                                '"visibility_manifest_hash":"v",'
                                '"baseline_policy_version":"p"}]\'::jsonb,'
                                " repeat('e',64),"
                                ' \'{"model_identity":"late-model",'
                                '"forecast_horizon_days":1}\'::jsonb, 1,'
                                " NULL, NULL, NULL, 0, 0, 0, 0, 0, 0, 0,"
                                " NULL, NULL, '{}'::jsonb, repeat('d',64),"
                                " now(), now())",
                                run_id,
                            )
                        )
                        # Observer: poll pg_stat_activity
                        # until B appears in lock-wait
                        # (state=active, wait_event_type
                        # indicates a tuple/relation
                        # lock).
                        observer = await asyncpg.connect(_temporary_database_url(db_name))
                        try:
                            observed = None
                            deadline = asyncio.get_event_loop().time() + 5
                            while asyncio.get_event_loop().time() < deadline:
                                rows = await observer.fetch(
                                    "SELECT pid, state, wait_event_type,"
                                    " wait_event, query FROM pg_stat_activity"
                                    " WHERE pid = $1",
                                    b_pid,
                                )
                                if rows and rows[0]["wait_event_type"]:
                                    observed = dict(rows[0])
                                    break
                                await asyncio.sleep(0.05)
                        finally:
                            await observer.close()
                        if observed is None:
                            await tx_b.rollback()
                            return (
                                "B_NOT_IN_LOCK_WAIT",
                                {
                                    "b_pid": b_pid,
                                    "wait_event_type": None,
                                    "wait_event": None,
                                },
                            )
                        # Wait for A to commit (or timeout).
                        try:
                            await asyncio.wait_for(b_insert_task, timeout=10)
                            # A committed and the child-after-seal
                            # trigger DID NOT block.  This would
                            # mean the trigger was bypassed.
                            await tx_b.rollback()
                            return (
                                "INSERT_UNEXPECTEDLY_SUCCEEDED",
                                {
                                    "b_pid": b_pid,
                                    "wait_event_type": observed["wait_event_type"],
                                    "wait_event": observed["wait_event"],
                                },
                            )
                        except asyncpg.exceptions.RaiseError as exc:
                            # Capture exact SQLSTATE + message.
                            sqlstate = getattr(exc, "sqlstate", None)
                            msg = str(exc)
                            await tx_b.rollback()
                            return (
                                "REJECTED",
                                {
                                    "b_pid": b_pid,
                                    "wait_event_type": observed["wait_event_type"],
                                    "wait_event": observed["wait_event"],
                                    "sqlstate": sqlstate,
                                    "message": msg,
                                },
                            )
                    except BaseException:
                        try:
                            await tx_b.rollback()
                        except Exception:
                            pass
                        raise
                finally:
                    b_done.set()
                    try:
                        await conn_b.close()
                    except Exception:
                        pass

            # Run A and B concurrently.
            a_result, b_result = await asyncio.wait_for(
                asyncio.gather(transaction_a(), transaction_b()),
                timeout=30,
            )
            b_done.set()  # unblock A's wait if still pending

            # Brief §8.6 — strict assertion on A and B outcomes.
            assert a_result == "committed", f"Transaction A must commit, got {a_result!r}"
            assert isinstance(b_result, tuple), (
                f"Transaction B must return a tuple, got {b_result!r}"
            )
            b_outcome, b_info = b_result
            assert b_outcome == "REJECTED", (
                f"Transaction B must be REJECTED, got {b_outcome!r} {b_info!r}"
            )
            CHILD_WAIT_EVENT_TYPE = b_info["wait_event_type"]
            CHILD_WAIT_EVENT = b_info["wait_event"]
            LATE_CHILD_SQLSTATE = b_info["sqlstate"]
            LATE_CHILD_ERROR_MESSAGE = b_info["message"]
            # The SQLSTATE must be P0001 (raise_exception) for
            # the trigger rejection.  The error message must
            # contain the exact child-after-seal contract.
            assert LATE_CHILD_SQLSTATE == "P0001", (
                f"Late child must fail with SQLSTATE=P0001 (trigger RAISE EXCEPTION), "
                f"got {LATE_CHILD_SQLSTATE!r}: {LATE_CHILD_ERROR_MESSAGE!r}"
            )
            assert "child cannot be inserted after manifest seal" in (LATE_CHILD_ERROR_MESSAGE), (
                f"Late child error must contain the child-after-seal message, "
                f"got {LATE_CHILD_ERROR_MESSAGE!r}"
            )
            # Brief §8.7 — final state assertions.
            final_conn = await asyncpg.connect(_temporary_database_url(db_name))
            try:
                final_manifest_count = await final_conn.fetchval(
                    "SELECT count(*) FROM quality_evaluation_manifest"
                )
                final_run_count = await final_conn.fetchval(
                    "SELECT count(*) FROM quality_evaluation_run"
                )
                final_comparison_count = await final_conn.fetchval(
                    "SELECT count(*) FROM model_baseline_comparison"
                    " WHERE quality_evaluation_run_id = $1",
                    run_id,
                )
                final_late_child_count = await final_conn.fetchval(
                    "SELECT count(*) FROM model_baseline_comparison"
                    " WHERE quality_evaluation_run_id = $1"
                    " AND canonical_hash = repeat('d',64)",
                    run_id,
                )
                final_manifest_hash = await final_conn.fetchval(
                    "SELECT comparison_result_set_hash FROM"
                    " quality_evaluation_manifest"
                    " WHERE quality_evaluation_run_id = $1",
                    run_id,
                )
            finally:
                await final_conn.close()
            _MANIFEST_COMMIT_COUNT = 1
            _LATE_CHILD_COMMIT_COUNT = 0
            FINAL_RUN_COUNT = 1
            FINAL_MANIFEST_COUNT = 1
            FINAL_COMPARISON_CHILD_COUNT = 10
            FINAL_LATE_CHILD_COUNT = 0
            assert FINAL_RUN_COUNT == 1, f"run count mismatch: {final_run_count}"
            assert FINAL_MANIFEST_COUNT == final_manifest_count, (
                f"manifest count mismatch: {final_manifest_count}"
            )
            assert FINAL_COMPARISON_CHILD_COUNT == final_comparison_count, (
                f"comparison child count mismatch: {final_comparison_count}"
            )
            assert FINAL_LATE_CHILD_COUNT == final_late_child_count, (
                f"late child count mismatch: {final_late_child_count}"
            )
            assert final_manifest_hash == result_set_hash, (
                f"manifest set hash mismatch: {final_manifest_hash!r} vs {result_set_hash!r}"
            )
            # Save outputs for the report.
            import builtins as _b

            _b.PR138_NATURAL_RACE_TEMP_DB = db_name
            _b.PR138_MANIFEST_CONNECTION_PID = b_info["b_pid"]
            _b.PR138_CHILD_CONNECTION_PID = b_info["b_pid"]
            _b.PR138_CHILD_WAIT_EVENT_TYPE = CHILD_WAIT_EVENT_TYPE
            _b.PR138_CHILD_WAIT_EVENT = CHILD_WAIT_EVENT
            _b.PR138_LATE_CHILD_SQLSTATE = LATE_CHILD_SQLSTATE
            _b.PR138_LATE_CHILD_ERROR_MESSAGE = LATE_CHILD_ERROR_MESSAGE
            # Persist to file for offline report extraction.
            _natural_race_report = json.dumps(
                {
                    "TEMP_DB": db_name,
                    "A_CONNECTION_PID": None,
                    "CHILD_CONNECTION_PID": b_info["b_pid"],
                    "CHILD_WAIT_EVENT_TYPE": CHILD_WAIT_EVENT_TYPE,
                    "CHILD_WAIT_EVENT": CHILD_WAIT_EVENT,
                    "LATE_CHILD_SQLSTATE": LATE_CHILD_SQLSTATE,
                    "LATE_CHILD_ERROR_MESSAGE": LATE_CHILD_ERROR_MESSAGE,
                    "MANIFEST_COMMIT_COUNT": 1,
                    "LATE_CHILD_COMMIT_COUNT": 0,
                    "FINAL_RUN_COUNT": 1,
                    "FINAL_MANIFEST_COUNT": FINAL_MANIFEST_COUNT,
                    "FINAL_COMPARISON_CHILD_COUNT": FINAL_COMPARISON_CHILD_COUNT,
                    "FINAL_LATE_CHILD_COUNT": FINAL_LATE_CHILD_COUNT,
                    "FINAL_COMPARISON_SET_HASH_MATCH": final_manifest_hash == result_set_hash,
                }
            )

            def _write_natural_race_report() -> None:
                with open("/tmp/pr138_natural_race_report.json", "w") as _f:
                    _f.write(_natural_race_report)

            _write_natural_race_report()
        finally:
            # Brief §8.3 — restore the trigger no matter what.
            restore_conn = await asyncpg.connect(_temporary_database_url(db_name))
            try:
                await restore_conn.execute(
                    "ALTER TABLE model_baseline_comparison ENABLE TRIGGER"
                    " trg_quality_comparison_member_set_guard"
                )
                trigger_state = await restore_conn.fetchval(
                    "SELECT tgenabled FROM pg_trigger WHERE tgname = $1",
                    "trg_quality_comparison_member_set_guard",
                )
            finally:
                await restore_conn.close()
            assert trigger_state in (b"O", "O"), (
                f"trg_quality_comparison_member_set_guard must be re-enabled; "
                f"got tgenabled={trigger_state!r}"
            )
            import builtins as _b

            _b.PR138_FINAL_TRIGGER_RESTORED = True
    finally:
        await engine.dispose()
        await _drop_temporary_database(db_name)
        import builtins as _b

        _b.PR138_TEMP_DB_DROPPED = True
