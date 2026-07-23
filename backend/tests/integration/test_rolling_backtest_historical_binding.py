"""PostgreSQL acceptance for the V0.2-S2 binding projection."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import AsyncSessionMaker
from backend.app.models.rolling_backtest import (
    RollingBacktestAvailabilityAudit,
    RollingBacktestBindingRow,
    RollingBacktestManifest,
    RollingBacktestNode,
    RollingBacktestResolvedInput,
    RollingBacktestRun,
)
from backend.app.rolling_backtest.canonical import sha256_payload
from backend.app.rolling_backtest.errors import (
    RollingBacktestIdentityConflictError,
    RollingBacktestPersistenceError,
)
from backend.app.rolling_backtest.orchestration import build_s2_binding_rows
from backend.app.rolling_backtest.persistence import (
    load_logical_run_with_integrity,
    persist_s2_historical_binding,
)
from backend.app.rolling_backtest.schemas import (
    S2ActualLabelAuthority,
    S2ForecastAuthorityBundle,
    S2HistoricalBacktestRequest,
    S2HistoricalBindingCandidate,
    s2_business_grain_hash,
)
from backend.app.rolling_backtest.signatures import s2_request_hash

pytestmark = [pytest.mark.integration, pytest.mark.postgres]

_CUTOFF = datetime(2026, 3, 1, 4, 0, tzinfo=UTC)
_LABEL_CUTOFF = datetime(2026, 3, 5, 4, 0, tzinfo=UTC)


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")


def _request(suffix: str = "default") -> S2HistoricalBacktestRequest:
    return S2HistoricalBacktestRequest(
        season_business_keys=(f"season:2026:{suffix}",),
        farm_business_keys=(f"farm:alpha:{suffix}",),
        subfarm_business_keys=(f"subfarm:alpha-1:{suffix}",),
        variety_business_keys=(f"variety:legacy:{suffix}",),
        master_identity_resolver_version="master-v1",
        mapping_policy_version="mapping-v1",
        resolved_identity_snapshot_hash="a" * 64,
        authority_selection_policy_version="authority-v1",
        forecast_cutoff_at=_CUTOFF,
        label_observation_cutoff_at=_LABEL_CUTOFF,
        label_visibility_mode="AS_OF_EVALUATION",
        requested_horizons_days=(7, 14, 21),
    )


def _candidates(
    request: S2HistoricalBacktestRequest,
    *,
    with_labels: bool = True,
) -> tuple[S2HistoricalBindingCandidate, ...]:
    result: list[S2HistoricalBindingCandidate] = []
    for horizon in (7, 14, 21):
        actual = (
            S2ActualLabelAuthority(
                label_snapshot_identity_hash=f"{horizon + 10:064x}",
                label_row_identity_hash=f"{horizon + 30:064x}",
                label_winner_identity_hash=f"{horizon + 40:064x}",
                label_winner_set_identity_hash=f"{horizon + 45:064x}",
                source_identity_hash=f"{horizon + 20:064x}",
                actual_source_identity_hash=f"{horizon + 50:064x}",
                target_date=_CUTOFF.date() + timedelta(days=horizon),
                season_business_key=request.season_business_keys[0],
                farm_business_key=request.farm_business_keys[0],
                subfarm_business_key=request.subfarm_business_keys[0],
                variety_business_key=request.variety_business_keys[0],
                business_grain_hash=s2_business_grain_hash(
                    season_business_key=request.season_business_keys[0],
                    farm_business_key=request.farm_business_keys[0],
                    subfarm_business_key=request.subfarm_business_keys[0],
                    variety_business_key=request.variety_business_keys[0],
                    target_date=_CUTOFF.date() + timedelta(days=horizon),
                ),
                revision_or_winner_evidence={"revision": horizon},
                observed_weight_kg=Decimal("12.500000"),
                visibility_timestamp=_LABEL_CUTOFF,
                physical_alignment_status="VERIFIED",
            )
            if with_labels
            else None
        )
        result.append(
            S2HistoricalBindingCandidate(
                horizon_days=horizon,
                target_date=_CUTOFF.date() + timedelta(days=horizon),
                forecast_cutoff_at=_CUTOFF,
                forecast_value_kg=Decimal(horizon),
                forecast_authority=S2ForecastAuthorityBundle(
                    forecast_run_identity_hash=f"{horizon:064x}",
                    daily_row_identity_hash=f"{horizon + 1:064x}",
                    task9_authority_identity_hash="c" * 64,
                    task9_member_identity_hash="5" * 64,
                    task10_authority_identity_hash="d" * 64,
                    task10_model_identity_hash="6" * 64,
                    task10_replay_identity_hash="7" * 64,
                    task10_prediction_row_identity_hash="8" * 64,
                    forecast_code_identity="code-v1",
                    historical_code_identity="historical-code-v1",
                    model_identity="model-v1",
                    parameter_identity="parameter-v1",
                    data_identity="data-v1",
                    available_at=_CUTOFF,
                    task10_model_available_at=_CUTOFF,
                ),
                actual_label=actual,
                authority_verification="SYNTHETIC_ENGINEERING",
            )
        )
    return tuple(result)


async def _persist_synthetic_fixture(
    session,
    *,
    request: S2HistoricalBacktestRequest,
    candidates: tuple[S2HistoricalBindingCandidate, ...],
    season_id: int,
):
    """Persist repository-owned engineering evidence without bypassing the production adapter."""

    return await persist_s2_historical_binding(
        session,
        request=request,
        rows=build_s2_binding_rows(request, candidates),
        season_id=season_id,
    )


async def _counts(session, request_hash: str | None = None) -> dict[str, int]:
    run_filter = (
        RollingBacktestRun.backtest_request_hash == request_hash
        if request_hash is not None
        else RollingBacktestRun.s2_contract_version.is_not(None)
    )
    return {
        "run": int(
            await session.scalar(
                select(func.count()).select_from(RollingBacktestRun).where(run_filter)
            )
        ),
        "node": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestNode)
                .join(
                    RollingBacktestRun, RollingBacktestRun.id == RollingBacktestNode.rolling_run_id
                )
                .where(run_filter)
                .where(RollingBacktestNode.node_key == "s2-single-node")
            )
        ),
        "binding": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestBindingRow)
                .join(
                    RollingBacktestRun,
                    RollingBacktestRun.id == RollingBacktestBindingRow.rolling_run_id,
                )
                .where(run_filter)
            )
        ),
        "manifest": int(
            await session.scalar(
                select(func.count())
                .select_from(RollingBacktestManifest)
                .join(
                    RollingBacktestRun,
                    RollingBacktestRun.id == RollingBacktestManifest.rolling_run_id,
                )
                .where(run_filter)
            )
        ),
    }


async def test_s2_postgres_persistence_round_trip_and_idempotent_replay() -> None:
    _require_postgres()
    request = _request()
    async with AsyncSessionMaker() as session:
        run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        run_id = run.id
        await session.commit()

    async with AsyncSessionMaker() as fresh_session:
        loaded = await fresh_session.get(RollingBacktestRun, run_id)
        assert loaded is not None
        assert loaded.s2_contract_version == "v0.2-s2-historical-binding-v1"
        assert loaded.s2_node_count == 1
        assert loaded.forecast_cutoff_at == _CUTOFF
        assert loaded.label_observation_cutoff_at == _LABEL_CUTOFF
        assert loaded.backtest_request_hash is not None
        rows = (
            (
                await fresh_session.execute(
                    select(RollingBacktestBindingRow)
                    .where(RollingBacktestBindingRow.rolling_run_id == run_id)
                    .order_by(RollingBacktestBindingRow.horizon_days)
                )
            )
            .scalars()
            .all()
        )
        assert [row.horizon_days for row in rows] == [7, 14, 21]
        assert all(row.actual_value_kg == Decimal("12.500000") for row in rows)
        node = await fresh_session.scalar(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run_id)
        )
        assert node is not None
        assert node.expected_resolved_input_count == 12
        assert node.expected_availability_audit_count == 12
        assert (
            await fresh_session.scalar(
                select(func.count(RollingBacktestResolvedInput.id)).where(
                    RollingBacktestResolvedInput.rolling_node_id == node.id
                )
            )
            == 12
        )
        assert (
            await fresh_session.scalar(
                select(func.count(RollingBacktestAvailabilityAudit.id)).where(
                    RollingBacktestAvailabilityAudit.rolling_node_id == node.id
                )
            )
            == 12
        )
        first_counts = await _counts(fresh_session, s2_request_hash(request))

        await load_logical_run_with_integrity(fresh_session, loaded)
        replay = await _persist_synthetic_fixture(
            fresh_session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        assert replay.id == run_id
        assert await _counts(fresh_session) == first_counts


async def test_s2_missing_labels_are_persisted_as_exclusions_without_zero_fill() -> None:
    _require_postgres()
    request = _request("missing-labels")
    async with AsyncSessionMaker() as session:
        run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request, with_labels=False),
            season_id=2026,
        )
        await session.commit()
        rows = (
            (
                await session.execute(
                    select(RollingBacktestBindingRow).where(
                        RollingBacktestBindingRow.rolling_run_id == run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 3
        assert all(row.row_status == "EXCLUDED" for row in rows)
        assert all(row.actual_value_kg is None for row in rows)
        assert all(row.reason_code == "NO_APPROVED_REAL_DATA" for row in rows)


def _sqlstate(error: DBAPIError) -> str | None:
    original = error.orig
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


async def _assert_immutable(
    statement: str,
    run_id: int,
    *,
    expected_message: str = "rolling-backtest S2 evidence row is immutable",
) -> None:
    async with AsyncSessionMaker() as session:
        try:
            await session.execute(text(statement), {"run_id": run_id})
            await session.commit()
        except DBAPIError as exc:
            assert _sqlstate(exc) == "23514"
            assert expected_message in str(exc)
            await session.rollback()
        else:
            raise AssertionError("immutable evidence mutation unexpectedly succeeded")


async def _persist_sealed_run(suffix: str) -> int:
    request = _request(suffix)
    async with AsyncSessionMaker() as session:
        run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.commit()
        return run.id


async def test_manifest_update_rejected() -> None:
    _require_postgres()
    run_id = await _persist_sealed_run("manifest-update-rejected")
    await _assert_immutable(
        "UPDATE rolling_backtest_manifest SET manifest_schema_version = 'drift' "
        "WHERE rolling_run_id = :run_id",
        run_id,
    )


async def test_manifest_delete_rejected() -> None:
    _require_postgres()
    run_id = await _persist_sealed_run("manifest-delete-rejected")
    await _assert_immutable(
        "DELETE FROM rolling_backtest_manifest WHERE rolling_run_id = :run_id",
        run_id,
    )


async def test_binding_delete_rejected() -> None:
    _require_postgres()
    run_id = await _persist_sealed_run("binding-delete-rejected")
    await _assert_immutable(
        "DELETE FROM rolling_backtest_binding_row WHERE rolling_run_id = :run_id",
        run_id,
    )


async def test_binding_update_rejected() -> None:
    _require_postgres()
    run_id = await _persist_sealed_run("binding-update-rejected")
    await _assert_immutable(
        "UPDATE rolling_backtest_binding_row SET forecast_value_kg = 999 "
        "WHERE rolling_run_id = :run_id",
        run_id,
    )


async def test_post_seal_binding_insert_rejected() -> None:
    _require_postgres()
    run_id = await _persist_sealed_run("post-seal-insert-rejected")
    await _assert_immutable(
        "INSERT INTO rolling_backtest_binding_row ("
        "rolling_run_id, rolling_node_id, horizon_days, target_date, "
        "forecast_cutoff_at, label_observation_cutoff_at, label_visibility_mode, "
        "physical_alignment_status, row_status, reason_code, forecast_row_identity_hash, "
        "actual_label_row_identity_hash, forecast_value_kg, actual_value_kg, canonical_payload, "
        "binding_key_hash, binding_row_hash) "
        "SELECT rolling_run_id, rolling_node_id, horizon_days, target_date, "
        "forecast_cutoff_at, label_observation_cutoff_at, label_visibility_mode, "
        "physical_alignment_status, row_status, reason_code, forecast_row_identity_hash, "
        "actual_label_row_identity_hash, forecast_value_kg, actual_value_kg, canonical_payload, "
        "binding_key_hash, binding_row_hash "
        "FROM rolling_backtest_binding_row WHERE rolling_run_id = :run_id LIMIT 1",
        run_id,
        expected_message="cannot be inserted after manifest seal",
    )


async def test_duplicate_manifest_hash_is_rejected() -> None:
    _require_postgres()
    request = _request("duplicate-manifest-hash")
    async with AsyncSessionMaker() as session:
        source_run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        source_manifest = await session.scalar(
            select(RollingBacktestManifest).where(
                RollingBacktestManifest.rolling_run_id == source_run.id
            )
        )
        assert source_manifest is not None
        owner_hash = sha256_payload({"duplicate_manifest_owner": source_run.id})
        owner = RollingBacktestRun(
            run_signature=owner_hash,
            config_hash=owner_hash,
            execution_mode=source_run.execution_mode,
            rolling_schema_version=source_run.rolling_schema_version,
            canonical_serialization_version=source_run.canonical_serialization_version,
            availability_registry_version=source_run.availability_registry_version,
            node_calendar_version=source_run.node_calendar_version,
            forecast_horizon_policy_version=source_run.forecast_horizon_policy_version,
            upstream_selection_policy_version=source_run.upstream_selection_policy_version,
            metric_policy_version=source_run.metric_policy_version,
            calendar_phase_policy_version=source_run.calendar_phase_policy_version,
            cutoff_policy_version=source_run.cutoff_policy_version,
            cutoff_timezone=source_run.cutoff_timezone,
            cutoff_local_time=source_run.cutoff_local_time,
            status="completed",
            expected_node_count=1,
            canonical_payload={"duplicate_manifest_owner": source_run.id},
            canonical_payload_hash=owner_hash,
        )
        session.add(owner)
        await session.flush()
        try:
            await session.execute(
                text(
                    "INSERT INTO rolling_backtest_manifest ("
                    "rolling_run_id, manifest_schema_version, request_hash, instance_hash, "
                    "coverage_manifest_payload, exclusion_manifest_payload, "
                    "authority_reference_payload, manifest_hash"
                    ") SELECT :owner_id, manifest_schema_version, request_hash, instance_hash, "
                    "coverage_manifest_payload, exclusion_manifest_payload, "
                    "authority_reference_payload, manifest_hash "
                    "FROM rolling_backtest_manifest WHERE id = :source_id"
                ),
                {"owner_id": owner.id, "source_id": source_manifest.id},
            )
            await session.flush()
        except DBAPIError as exc:
            assert _sqlstate(exc) == "23505"
            assert "uq_rolling_backtest_manifest_hash" in str(exc)
            await session.rollback()
        else:
            raise AssertionError("duplicate manifest hash unexpectedly succeeded")


async def test_s2_caller_rollback_leaves_no_final_evidence() -> None:
    _require_postgres()
    request = _request("rollback")
    async with AsyncSessionMaker() as session:
        await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.rollback()

    async with AsyncSessionMaker() as fresh_session:
        assert await _counts(fresh_session, s2_request_hash(request)) == {
            "run": 0,
            "node": 0,
            "binding": 0,
            "manifest": 0,
        }


async def test_s2_replay_rejects_persisted_node_cutoff_drift() -> None:
    _require_postgres()
    request = _request("cutoff-drift")
    async with AsyncSessionMaker() as session:
        run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.commit()
        node = await session.scalar(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        assert node is not None
        node.forecast_cutoff_at = _CUTOFF + timedelta(seconds=1)
        with pytest.raises(RollingBacktestIdentityConflictError, match="cutoff drift"):
            await _persist_synthetic_fixture(
                session,
                request=request,
                candidates=_candidates(request),
                season_id=2026,
            )
        await session.rollback()


@pytest.mark.parametrize(
    "target",
    (
        "run_payload",
        "node_payload",
        "node_signature",
        "binding_payload",
        "manifest_payload",
        "resolved_authority_payload",
        "availability_audit_payload",
    ),
)
async def test_s2_integrity_reload_rejects_canonical_tamper(target: str) -> None:
    _require_postgres()
    request = _request(f"tamper-{target}")
    async with AsyncSessionMaker() as session:
        run = await _persist_synthetic_fixture(
            session,
            request=request,
            candidates=_candidates(request),
            season_id=2026,
        )
        await session.commit()

    async with AsyncSessionMaker() as session:
        loaded = await session.get(RollingBacktestRun, run.id)
        assert loaded is not None
        node = await session.scalar(
            select(RollingBacktestNode).where(RollingBacktestNode.rolling_run_id == run.id)
        )
        assert node is not None
        binding = await session.scalar(
            select(RollingBacktestBindingRow).where(
                RollingBacktestBindingRow.rolling_run_id == run.id
            )
        )
        manifest = await session.scalar(
            select(RollingBacktestManifest).where(RollingBacktestManifest.rolling_run_id == run.id)
        )
        resolved_input = await session.scalar(
            select(RollingBacktestResolvedInput).where(
                RollingBacktestResolvedInput.rolling_node_id == node.id
            )
        )
        availability_audit = await session.scalar(
            select(RollingBacktestAvailabilityAudit).where(
                RollingBacktestAvailabilityAudit.rolling_node_id == node.id
            )
        )
        assert binding is not None
        assert manifest is not None
        assert resolved_input is not None
        assert availability_audit is not None
        if target == "run_payload":
            loaded.canonical_payload = {**loaded.canonical_payload, "tampered": True}
        elif target == "node_payload":
            node.canonical_payload = {**node.canonical_payload, "tampered": True}
        elif target == "node_signature":
            node.node_signature = "f" * 64
        elif target == "binding_payload":
            binding.canonical_payload = {**binding.canonical_payload, "tampered": True}
        elif target == "manifest_payload":
            manifest.authority_reference_payload = {
                **manifest.authority_reference_payload,
                "tampered": True,
            }
        elif target == "resolved_authority_payload":
            resolved_input.canonical_payload = {
                **resolved_input.canonical_payload,
                "tampered": True,
            }
        else:
            availability_audit.canonical_payload = {
                **availability_audit.canonical_payload,
                "tampered": True,
            }
        with session.no_autoflush:
            with pytest.raises(RollingBacktestPersistenceError):
                await load_logical_run_with_integrity(session, loaded)
        await session.rollback()
