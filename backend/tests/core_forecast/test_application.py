from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core_forecast.application import (
    execute_core_forecast_run,
    recalculate_core_forecast_run,
)
from backend.app.core_forecast.canonical import (
    compute_authority_bound_daily_curve_hash,
    compute_authority_bound_retention_policy_hash,
    compute_core_forecast_input_hash,
    compute_core_forecast_request_hash,
    compute_core_forecast_result_hash,
)
from backend.app.core_forecast.persistence import (
    CoreForecastPersistenceIntegrityError,
    CoreForecastRunRepository,
)
from backend.app.core_forecast.repository import SeasonSource
from backend.app.core_forecast.schemas import (
    CoreForecastCodeAuthority,
    ExecuteCoreForecastRunRequest,
    MarketableRetentionPolicySnapshot,
    RegisterCoreForecastCodeAuthority,
    ResolvedCoreForecastIdentity,
    ResolvedCoreForecastScopeIdentity,
)
from backend.app.models.core_forecast import (
    CoreForecastCodeAuthorityModel,
    CoreForecastRunModel,
)
from backend.app.models.harvest_state import HarvestStateRun
from backend.tests.core_forecast.test_complete_daily_curve_service import (
    FixtureRepository,
    _policy,
    _request,
    _sources,
)


class MissingUpstream:
    async def load_task8_authority(self, run_id: int):
        return None

    async def load_task9_authority(self, run_id: int):
        return None

    async def load_season(self, season_id: int):
        return SeasonSource(season_id=season_id, code="2026-DEMO")


async def _register_authority(
    session: AsyncSession,
    *,
    source_commit_sha: str = "a" * 40,
    build_artifact_hash: str = "b" * 64,
):
    await _ensure_code_authority_table(session)
    return await CoreForecastRunRepository(session).register_code_authority(
        RegisterCoreForecastCodeAuthority(
            source_commit_sha=source_commit_sha,
            engine_code_hash="e" * 64,
            build_artifact_hash=build_artifact_hash,
            config_bundle_hash="c" * 64,
            available_at=datetime(2026, 2, 28, tzinfo=UTC),
        )
    )


def _resolved_identity(*, suffix: str = "a") -> ResolvedCoreForecastIdentity:
    scopes = tuple(
        ResolvedCoreForecastScopeIdentity(
            farm_business_key=f"farm-{i}-{suffix}",
            subfarm_business_key=f"subfarm-{i}-{suffix}",
            variety_business_key=f"variety-{i}-{suffix}",
        )
        for i, _ in enumerate(_request().scopes)
    )
    return ResolvedCoreForecastIdentity(
        season_business_key=f"season-{suffix}",
        factory_business_key=f"factory-{suffix}",
        mapping_policy_version="business-key-v1",
        scopes=scopes,
        resolved_identity_snapshot_hash=("d" if suffix == "a" else "e") * 64,
    )


def _canonical_authority() -> CoreForecastCodeAuthority:
    return CoreForecastCodeAuthority(
        authority_id=1,
        authority_schema_version="v0.1-core-forecast-code-authority-v1",
        source_commit_sha="a" * 40,
        engine_code_hash="b" * 64,
        build_artifact_hash="c" * 64,
        config_bundle_hash="d" * 64,
        available_at=datetime(2026, 2, 28, tzinfo=UTC),
        authority_hash="e" * 64,
        created_at=datetime(2026, 2, 27, tzinfo=UTC),
    )


def _authority_input(request, policy, identity):
    return compute_core_forecast_input_hash(
        request,
        policy,
        code_authority=_canonical_authority(),
        task9_authority_result_hash="9" * 64,
        forecast_effective_cutoff_at="2026-03-01T00:00:00+00:00",
        resolved_identity=identity,
    )


class AuthorityFixtureRepository(FixtureRepository):
    async def resolve_business_identity(
        self, *, season_id: int, factory_id: int, scopes: tuple[tuple[int, int, int], ...]
    ):
        return _resolved_identity()


def _authority_upstream() -> AuthorityFixtureRepository:
    task8, task9 = _sources()
    return AuthorityFixtureRepository(
        task8,
        replace(
            task9,
            forecast_effective_cutoff_at=datetime(2026, 3, 1, tzinfo=UTC),
        ),
    )


async def _ensure_code_authority_table(session: AsyncSession) -> None:
    connection = await session.connection()
    await connection.run_sync(
        lambda sync_connection: CoreForecastCodeAuthorityModel.__table__.create(
            sync_connection,
            checkfirst=True,
        )
    )


async def _seed_task9_owner_row(session: AsyncSession) -> None:
    connection = await session.connection()
    await connection.run_sync(
        lambda sync_connection: HarvestStateRun.__table__.create(sync_connection, checkfirst=True)
    )
    if await session.get(HarvestStateRun, 910001) is None:
        _, task9 = _sources()
        session.add(
            HarvestStateRun(
                id=task9.run_id,
                status="completed",
                output_schema_version="fixture-v1",
                result_hash_schema_version="fixture-v1",
                resolved_parameter_snapshot_schema_version="fixture-v1",
                source_ref_schema_version="fixture-v1",
                stable_cohort_key_schema_version="fixture-v1",
                input_snapshot={},
                resolved_parameter_snapshot={},
                source_ref_catalog=[],
                warnings=[],
                blockers=[],
                mass_balance_result={},
                continuity_result={},
                canonical_output={},
                config_hash="1" * 64,
                result_hash=task9.result_hash,
                canonical_payload_hash="2" * 64,
                forecast_start_date=task9.forecast_start_date,
                forecast_end_date=task9.forecast_end_date,
                as_of_date=task9.forecast_start_date,
                destination_factory_id=task9.destination_factory_id,
                forecast_season_id=task9.forecast_season_id,
                pool_row_count=0,
                member_row_count=0,
                cohort_row_count=0,
                future_arrival_row_count=0,
                maturity_model_run_id=None,
                maturity_model_version=None,
                maturity_model_config_hash=None,
                maturity_model_source_signature=None,
                maturity_model_artifact_id=None,
                maturity_model_artifact_hash=task9.maturity_model_artifact_hash,
                maturity_forecast_run_id=task9.maturity_forecast_run_id,
                maturity_forecast_source_signature=None,
                is_replay=True,
                forecast_effective_cutoff_at=datetime(2026, 3, 1, tzinfo=UTC),
                replay_executed_at=datetime(2026, 3, 2, tzinfo=UTC),
                replay_code_version="fixture-v1",
                replay_run_correlation_id="core-forecast-fixture",
            )
        )
        await session.flush()


async def _persist_authority_bound_fixture(session: AsyncSession):
    await _seed_task9_owner_row(session)
    authority = await _register_authority(session)
    result = await execute_core_forecast_run(
        session,
        request=ExecuteCoreForecastRunRequest(
            curve_request=_request(),
            retention_policy=_policy(),
            code_authority_id=authority.authority_id,
        ),
        upstream_repository=_authority_upstream(),
    )
    assert result.status == "COMPLETED" and result.run is not None
    return CoreForecastRunRepository(session), result.run.run_id, authority


@pytest.mark.unit
async def test_f13_t01_missing_task9_owner_rejected_on_reload(sqlite_session: AsyncSession) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(delete(HarvestStateRun).where(HarvestStateRun.id == 910001))
    with pytest.raises(Exception, match="Task 9 authority is missing"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t02_task9_completed_status_required_on_reload(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun).where(HarvestStateRun.id == 910001).values(status="blocked")
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t03_task9_result_hash_drift_rejected_on_reload(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun).where(HarvestStateRun.id == 910001).values(result_hash="f" * 64)
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t04_task9_cutoff_null_rejected_for_authority_reload(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun)
        .where(HarvestStateRun.id == 910001)
        .values(forecast_effective_cutoff_at=None)
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t05_task9_cutoff_tamper_rejected_on_core_forecast_reload(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun)
        .where(HarvestStateRun.id == 910001)
        .values(forecast_effective_cutoff_at=datetime(2026, 3, 1, 0, 0, 1, tzinfo=UTC))
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("forecast_season_id", 9999),
        ("destination_factory_id", 9999),
        ("maturity_forecast_run_id", 9999),
        ("maturity_model_artifact_hash", "f" * 64),
    ],
)
async def test_f13_t06_task9_owner_lineage_drift_rejected(
    sqlite_session: AsyncSession, field: str, value: object
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun).where(HarvestStateRun.id == 910001).values(**{field: value})
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t07_code_authority_after_task9_cutoff_rejected_on_reload(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, authority = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(CoreForecastCodeAuthorityModel)
        .where(CoreForecastCodeAuthorityModel.id == authority.authority_id)
        .values(available_at=datetime(2026, 3, 2, tzinfo=UTC))
    )
    with pytest.raises(CoreForecastPersistenceIntegrityError):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t08_internal_rehash_cannot_mask_task9_lineage_drift(
    sqlite_session: AsyncSession,
) -> None:
    repository, run_id, _ = await _persist_authority_bound_fixture(sqlite_session)
    await sqlite_session.execute(
        update(HarvestStateRun).where(HarvestStateRun.id == 910001).values(result_hash="f" * 64)
    )
    await sqlite_session.execute(
        update(CoreForecastRunModel)
        .where(CoreForecastRunModel.id == run_id)
        .values(forecast_input_hash="1" * 64, request_hash="2" * 64, result_hash="3" * 64)
    )
    with pytest.raises(Exception, match="Task 9 lineage authority mismatch"):
        await repository.load_complete_run(run_id)


@pytest.mark.unit
async def test_f13_t09_legacy_core_forecast_reload_does_not_require_new_authority(
    sqlite_session: AsyncSession,
) -> None:
    result = await execute_core_forecast_run(
        sqlite_session,
        request=ExecuteCoreForecastRunRequest(curve_request=_request(), retention_policy=_policy()),
        upstream_repository=_authority_upstream(),
    )
    assert result.status == "COMPLETED" and result.run is not None
    loaded = await CoreForecastRunRepository(sqlite_session).load_complete_run(result.run.run_id)
    assert loaded is not None and loaded.code_authority is None


@pytest.mark.unit
def test_f12_t01_same_business_scope_numeric_ids_same_authority_hashes() -> None:
    request, policy, identity = _request(), _policy(), _resolved_identity()
    shifted_request = request.model_copy(
        update={
            "forecast_season_id": 1,
            "destination_factory_id": 2,
            "task8_forecast_run_id": 3,
            "task9_harvest_state_run_id": 4,
            "scopes": tuple(
                s.model_copy(
                    update={
                        "farm_id": s.farm_id + 10000,
                        "subfarm_id": s.subfarm_id + 10000,
                        "variety_id": s.variety_id + 10000,
                    }
                )
                for s in request.scopes
            ),
        }
    )
    shifted_policy = policy.model_copy(
        update={
            "entries": tuple(
                e.model_copy(
                    update={
                        "forecast_season_id": 1,
                        "farm_id": e.farm_id + 10000,
                        "subfarm_id": e.subfarm_id + 10000,
                        "variety_id": e.variety_id + 10000,
                    }
                )
                for e in policy.entries
            )
        }
    )
    assert compute_authority_bound_retention_policy_hash(
        policy, identity
    ) == compute_authority_bound_retention_policy_hash(shifted_policy, identity)
    first, second = (
        _authority_input(request, policy, identity),
        _authority_input(shifted_request, shifted_policy, identity),
    )
    assert first == second
    assert compute_core_forecast_request_hash(
        first, None, authority_bound=True
    ) == compute_core_forecast_request_hash(second, None, authority_bound=True)


@pytest.mark.unit
def test_f12_t02_different_business_scope_same_count_different_hashes() -> None:
    first = _authority_input(_request(), _policy(), _resolved_identity())
    second = _authority_input(_request(), _policy(), _resolved_identity(suffix="b"))
    assert first != second
    assert compute_core_forecast_request_hash(
        first, None, authority_bound=True
    ) != compute_core_forecast_request_hash(second, None, authority_bound=True)


@pytest.mark.unit
def test_f12_t03_policy_numeric_ids_do_not_change_authority_hash() -> None:
    policy, identity = _policy(), _resolved_identity()
    shifted = policy.model_copy(
        update={
            "entries": tuple(
                e.model_copy(
                    update={
                        "forecast_season_id": 1,
                        "farm_id": e.farm_id + 1,
                        "subfarm_id": e.subfarm_id + 1,
                        "variety_id": e.variety_id + 1,
                    }
                )
                for e in policy.entries
            )
        }
    )
    assert compute_authority_bound_retention_policy_hash(
        policy, identity
    ) == compute_authority_bound_retention_policy_hash(shifted, identity)


@pytest.mark.unit
def test_f12_t04_policy_business_keys_change_authority_hash() -> None:
    assert compute_authority_bound_retention_policy_hash(
        _policy(), _resolved_identity()
    ) != compute_authority_bound_retention_policy_hash(_policy(), _resolved_identity(suffix="b"))
    assert _authority_input(_request(), _policy(), _resolved_identity()) != _authority_input(
        _request(), _policy(), _resolved_identity(suffix="b")
    )


@pytest.mark.unit
async def test_f12_t05_daily_numeric_ids_do_not_change_authority_curve_hash() -> None:
    from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs

    _, curve, *_ = await fixture_request_and_outputs()
    shifted = tuple(
        row.model_copy(
            update={
                "farm_id": row.farm_id + 10000,
                "subfarm_id": row.subfarm_id + 10000,
                "variety_id": row.variety_id + 10000,
                "destination_factory_id": row.destination_factory_id + 10000,
                "task8_forecast_run_id": row.task8_forecast_run_id + 10000,
                "task9_harvest_state_run_id": row.task9_harvest_state_run_id + 10000,
            }
        )
        for row in curve.rows
    )
    assert compute_authority_bound_daily_curve_hash(
        curve.rows, _resolved_identity()
    ) == compute_authority_bound_daily_curve_hash(shifted, _resolved_identity())


@pytest.mark.unit
async def test_f12_t06_semantic_task8_or_task9_changes_curve_or_result_identity() -> None:
    from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs

    _, curve, metrics, *_ = await fixture_request_and_outputs()
    first = compute_authority_bound_daily_curve_hash(curve.rows, _resolved_identity())
    changed = compute_authority_bound_daily_curve_hash(
        tuple(r.model_copy(update={"task8_artifact_hash": "f" * 64}) for r in curve.rows),
        _resolved_identity(),
    )
    assert first != changed and metrics.metrics_hash is not None
    kwargs = dict(
        request_hash="1" * 64,
        forecast_input_hash="2" * 64,
        metrics_hash=metrics.metrics_hash,
        daily_row_count=len(curve.rows),
        metric_row_count=3,
        authority_bound=True,
        forecast_effective_cutoff_at="2026-03-01",
    )
    assert compute_core_forecast_result_hash(
        curve_hash=first, **kwargs
    ) != compute_core_forecast_result_hash(curve_hash=changed, **kwargs)


@pytest.mark.unit
async def test_f12_t07_legacy_v0_1_exact_hash_fixtures_unchanged() -> None:
    from backend.tests.core_forecast.s4_test_helpers import fixture_request_and_outputs

    (
        _,
        curve,
        _,
        policy_hash,
        input_hash,
        request_hash,
        result_hash,
    ) = await fixture_request_and_outputs()
    assert (
        policy_hash,
        curve.rows[0].row_hash,
        curve.curve_hash,
        input_hash,
        request_hash,
        result_hash,
    ) == (
        "bb11514b59f2476391855fae3a209eb55223e04f28a06d900e38ae7628a06b53",
        "c9376460237e0e1b109c431c997cece4a06fdb6f2b469bfb4930004e58a9cde1",
        "de81bfa3a23efcef0398758e5105199eede9222adb0aff4acda67f3fe9697687",
        "a23d315e719a2dade3d7daf40a2e2c415d2335a21507ba77e4cf1d03dbfc27b1",
        "51f4e362691cb1dad834783c8c63efb4d5befea079bd8c3089e866467a385ba0",
        "802504d0798f6ce1f46978806a4b986eefe2ff733616b60af7143ff3e641535a",
    )


@pytest.mark.unit
async def test_blocked_s2_result_exposes_no_partial_output(sqlite_session: AsyncSession) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    result = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=MissingUpstream(),
    )
    assert result.status == "BLOCKED"
    assert result.run is None
    assert result.daily_curve is None
    assert result.metrics is None
    assert result.reused_existing_run is False
    assert result.blockers[0].code == "TASK8_AUTHORITY_NOT_FOUND"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_missing_pre_registered_code_authority_blocks_before_forecast(
    sqlite_session: AsyncSession,
) -> None:
    await _ensure_code_authority_table(sqlite_session)
    result = await execute_core_forecast_run(
        sqlite_session,
        request=ExecuteCoreForecastRunRequest(
            curve_request=_request(),
            retention_policy=_policy(),
            code_authority_id=999999,
        ),
        upstream_repository=_authority_upstream(),
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_CODE_AUTHORITY_NOT_FOUND"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_authority_bound_run_hashes_code_identity_and_replays_idempotently(
    sqlite_session: AsyncSession,
) -> None:
    upstream = _authority_upstream()
    await _seed_task9_owner_row(sqlite_session)
    legacy = await execute_core_forecast_run(
        sqlite_session,
        request=ExecuteCoreForecastRunRequest(
            curve_request=_request(),
            retention_policy=_policy(),
        ),
        upstream_repository=upstream,
    )
    authority = await _register_authority(sqlite_session)
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
        code_authority_id=authority.authority_id,
    )
    first = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    replay = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert legacy.status == first.status == replay.status == "COMPLETED"
    assert legacy.run is not None and first.run is not None and replay.run is not None
    assert first.run.run_schema_version == "v0.1-core-forecast-run-authority-v2"
    assert first.run.request_schema_version == "v0.1-core-forecast-request-authority-v2"
    assert first.run.code_authority_id == authority.authority_id
    assert first.run.forecast_input_hash != legacy.run.forecast_input_hash
    assert first.run.request_hash != legacy.run.request_hash
    assert first.run.result_hash != legacy.run.result_hash
    assert replay.run.run_id == first.run.run_id
    assert replay.reused_existing_run is True


@pytest.mark.unit
async def test_different_persisted_code_authority_changes_run_identity(
    sqlite_session: AsyncSession,
) -> None:
    upstream = _authority_upstream()
    await _seed_task9_owner_row(sqlite_session)
    first_authority = await _register_authority(sqlite_session)
    second_authority = await _register_authority(
        sqlite_session,
        source_commit_sha="d" * 40,
        build_artifact_hash="e" * 64,
    )
    results = []
    for authority in (first_authority, second_authority):
        results.append(
            await execute_core_forecast_run(
                sqlite_session,
                request=ExecuteCoreForecastRunRequest(
                    curve_request=_request(),
                    retention_policy=_policy(),
                    code_authority_id=authority.authority_id,
                ),
                upstream_repository=upstream,
            )
        )
    assert all(result.status == "COMPLETED" for result in results)
    assert results[0].run is not None and results[1].run is not None
    assert results[0].run.forecast_input_hash != results[1].run.forecast_input_hash
    assert results[0].run.result_hash != results[1].run.result_hash


@pytest.mark.unit
async def test_missing_rerun_parent_blocks_without_writes(sqlite_session: AsyncSession) -> None:
    result = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=999999,
        curve_request=_request(),
        retention_policy=_policy(),
        upstream_repository=MissingUpstream(),
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_PARENT_RUN_NOT_FOUND"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_completed_run_is_reused_and_explicit_rerun_has_parent(
    sqlite_session: AsyncSession,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = _authority_upstream()
    first = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert first.status == "COMPLETED"
    assert first.run is not None
    assert len(first.daily_curve.rows) == 1080  # type: ignore[union-attr]

    reused = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert reused.status == "COMPLETED"
    assert reused.reused_existing_run is True
    assert reused.run is not None
    assert reused.run.run_id == first.run.run_id

    original_policy = _policy()
    changed_policy = MarketableRetentionPolicySnapshot(
        entries=tuple(
            entry.model_copy(update={"postharvest_retention_rate": "0.940000"})
            if index == 0
            else entry
            for index, entry in enumerate(original_policy.entries)
        )
    )
    rerun = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=first.run.run_id,
        curve_request=_request(),
        retention_policy=changed_policy,
        upstream_repository=upstream,
    )
    assert rerun.status == "COMPLETED"
    assert rerun.run is not None
    assert rerun.run.rerun_of_run_id == first.run.run_id
    assert rerun.run.run_id != first.run.run_id

    unchanged = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=first.run.run_id,
        curve_request=_request(),
        retention_policy=original_policy,
        upstream_repository=upstream,
    )
    assert unchanged.status == "BLOCKED"
    assert unchanged.blockers[0].code == "CORE_FORECAST_RERUN_INPUT_UNCHANGED"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 2


@pytest.mark.unit
async def test_blocked_s3_result_writes_no_rows(
    sqlite_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = _authority_upstream()

    from backend.app.core_forecast import application as application_module
    from backend.app.core_forecast.schemas import (
        CompleteCoreForecastMetricsResult,
        CoreForecastBlocker,
    )

    def blocked_metrics(*, daily_curve):
        del daily_curve
        return CompleteCoreForecastMetricsResult(
            status="BLOCKED",
            metrics_schema_version=None,
            date_basis=None,
            source_curve_hash=None,
            metrics=(),
            metrics_hash=None,
            blockers=(CoreForecastBlocker(code="NO_COMPLETE_7DAY_WINDOW", message="blocked"),),
        )

    monkeypatch.setattr(application_module, "compute_core_forecast_metrics", blocked_metrics)
    result = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert result.status == "BLOCKED"
    assert result.run is None
    assert result.daily_curve is None
    assert result.metrics is None
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 0


@pytest.mark.unit
async def test_rerun_scope_mismatch_blocks_without_writing_child(
    sqlite_session: AsyncSession,
) -> None:
    request = ExecuteCoreForecastRunRequest(
        curve_request=_request(),
        retention_policy=_policy(),
    )
    upstream = FixtureRepository(*_sources())
    parent = await execute_core_forecast_run(
        sqlite_session,
        request=request,
        upstream_repository=upstream,
    )
    assert parent.status == "COMPLETED"
    assert parent.run is not None
    mismatched_request = _request().model_copy(update={"destination_factory_id": 9102})
    result = await recalculate_core_forecast_run(
        sqlite_session,
        source_run_id=parent.run.run_id,
        curve_request=mismatched_request,
        retention_policy=_policy(),
        upstream_repository=upstream,
    )
    assert result.status == "BLOCKED"
    assert result.blockers[0].code == "CORE_FORECAST_RERUN_SCOPE_MISMATCH"
    assert await sqlite_session.scalar(select(func.count(CoreForecastRunModel.id))) == 1
