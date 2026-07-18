from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestValidationAttemptModel,
)
from backend.app.actual_harvest_import.validation_service import (
    begin_validation,
    create_mapping_registry,
    seal_mapping_registry,
)
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload, _record_payload

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


async def _seed_registry(maker: async_sessionmaker[AsyncSession]) -> None:
    async with maker() as session:
        async with session.begin():
            await session.run_sync(lambda sync_session: _seed_registry_sync(sync_session))


def _seed_registry_sync(sync_session: Session) -> None:
    farm = Farm(id=1, name="farm-master")
    sync_session.add_all(
        [
            Season(
                id=1,
                code="2026",
                start_date=datetime(2026, 1, 1).date(),
                end_date=datetime(2026, 12, 31).date(),
            ),
            farm,
            Variety(id=1, code="variety-master", name="Variety Master"),
        ]
    )
    sync_session.flush()
    sync_session.add(Subfarm(id=1, farm_id=farm.id, name="subfarm-master"))
    registry = create_mapping_registry(
        sync_session,
        registry_version="registry-2026-v1",
        source_system="farm-system",
        mapping_policy_version="mapping-v1",
        entries=(
            {
                "source_field": "season_code",
                "source_code": "2026",
                "target_type": "SEASON",
                "target_business_key": "2026",
            },
            {
                "source_field": "farm_code",
                "source_code": "farm-1",
                "target_type": "FARM",
                "target_business_key": "farm-master",
            },
            {
                "source_field": "subfarm_or_plot_code",
                "source_code": "plot-1",
                "target_type": "SUBFARM",
                "target_business_key": "subfarm-master",
                "target_parent_business_key": "farm-master",
            },
            {
                "source_field": "variety_code",
                "source_code": "variety-1",
                "target_type": "VARIETY",
                "target_business_key": "variety-master",
            },
        ),
        now=NOW,
    )
    assert registry.status == "DRAFT"
    seal_mapping_registry(sync_session, mapping_policy_version="mapping-v1", now=NOW)


@pytest.mark.asyncio
async def test_validate_persists_immutable_lineage_evidence(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    create = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = create.json()["data_or_null"]["batch"]["import_id"]
    record = _record_payload()
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [record]},
        headers={"content-type": "application/json"},
    )
    sealed = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/seal",
        json={},
        headers={"content-type": "application/json"},
    )
    assert sealed.status_code == 200
    validated = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/validate",
        json={},
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == 200, validated.text
    validation = validated.json()["data_or_null"]["validation"]
    assert validation["validation_status"] == "VALIDATED"
    assert validation["lineage_graph_hash"]
    assert validation["validation_result_hash"]
    assert validation["committed_lineage_basis_hash"]

    replay = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/validate",
        json={},
        headers={"content-type": "application/json"},
    )
    assert replay.status_code == 200
    assert (
        replay.json()["data_or_null"]["validation"]["validation_result_hash"]
        == validation["validation_result_hash"]
    )
    errors = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/errors",
        params={"page_size": 1},
    )
    assert errors.status_code == 200
    assert errors.json()["data_or_null"]["errors"] == []

    async with sqlite_session_maker() as session:
        batch = await session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == import_id
            )
        )
        assert batch is not None
        assert batch.status == "VALIDATED"


@pytest.mark.asyncio
async def test_validate_rejects_unsealed_mapping_registry_and_preserves_batch(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    async with sqlite_session_maker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: _seed_registry_sync_without_seal(sync_session)
            )
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    create_payload = _create_payload()
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=create_payload,
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [_record_payload()]},
        headers={"content-type": "application/json"},
    )
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/seal",
        json={},
        headers={"content-type": "application/json"},
    )
    response = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/validate",
        json={},
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "IDENTITY_MAPPING_REGISTRY_NOT_SEALED"


@pytest.mark.asyncio
async def test_validation_failed_errors_are_bounded_and_cancel_preserves_evidence(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    record = _record_payload()
    record["farm_code"] = "unknown-farm-code"
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [record]},
        headers={"content-type": "application/json"},
    )
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/seal",
        json={},
        headers={"content-type": "application/json"},
    )
    validated = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/validate",
        json={},
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == 200
    validation = validated.json()["data_or_null"]["validation"]
    assert validation["validation_status"] == "VALIDATION_FAILED"
    assert validation["error_count"] >= 1
    result_hash = validation["validation_result_hash"]

    errors = await api_client.get(
        f"/api/v1/actual-harvest/imports/{import_id}/errors",
        params={"page_size": 1},
    )
    assert errors.status_code == 200
    error_payload = errors.json()["data_or_null"]
    assert len(error_payload["errors"]) == 1
    assert error_payload["errors"][0]["error_code"] == "IDENTITY_MAPPING_NOT_FOUND"
    assert error_payload["validation"]["validation_result_hash"] == result_hash

    cancelled = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/cancel",
        json={},
        headers={"content-type": "application/json"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data_or_null"]["batch"]["status"] == "CANCELLED"
    preview = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["data_or_null"]["validation_result_hash"] == result_hash


@pytest.mark.asyncio
async def test_stale_validation_attempt_is_reclaimed_with_new_fencing_identity(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/records",
        json={"records": [_record_payload()]},
        headers={"content-type": "application/json"},
    )
    await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/seal",
        json={},
        headers={"content-type": "application/json"},
    )

    async with sqlite_session_maker() as session:
        async with session.begin():
            first = await session.run_sync(
                lambda sync_session: begin_validation(sync_session, import_id=import_id, now=NOW)
            )
        assert first.kind == "execute"
        assert first.attempt_id is not None

        async with session.begin():

            def reclaim(sync_session: Session):
                attempt = sync_session.scalar(
                    select(ActualHarvestValidationAttemptModel).where(
                        ActualHarvestValidationAttemptModel.attempt_id == first.attempt_id
                    )
                )
                assert attempt is not None
                attempt.lease_expires_at = NOW - timedelta(seconds=1)
                sync_session.flush()
                return begin_validation(sync_session, import_id=import_id, now=NOW)

            second = await session.run_sync(reclaim)
        assert second.kind == "execute"
        assert second.attempt_id is not None
        assert second.attempt_id != first.attempt_id

        async with session.begin():
            attempts = await session.scalars(
                select(ActualHarvestValidationAttemptModel).order_by(
                    ActualHarvestValidationAttemptModel.attempt_generation
                )
            )
            rows = attempts.all()
        assert [row.status for row in rows] == ["ABANDONED", "ACTIVE"]


def _seed_registry_sync_without_seal(sync_session: Session) -> None:
    farm = Farm(id=1, name="farm-master")
    sync_session.add_all(
        [
            Season(
                id=1,
                code="2026",
                start_date=datetime(2026, 1, 1).date(),
                end_date=datetime(2026, 12, 31).date(),
            ),
            farm,
            Variety(id=1, code="variety-master", name="Variety Master"),
        ]
    )
    sync_session.flush()
    sync_session.add(Subfarm(id=1, farm_id=farm.id, name="subfarm-master"))
    create_mapping_registry(
        sync_session,
        registry_version="registry-2026-v1",
        source_system="farm-system",
        mapping_policy_version="mapping-v1",
        entries=(
            {
                "source_field": "season_code",
                "source_code": "2026",
                "target_type": "SEASON",
                "target_business_key": "2026",
            },
            {
                "source_field": "farm_code",
                "source_code": "farm-1",
                "target_type": "FARM",
                "target_business_key": "farm-master",
            },
            {
                "source_field": "subfarm_or_plot_code",
                "source_code": "plot-1",
                "target_type": "SUBFARM",
                "target_business_key": "subfarm-master",
                "target_parent_business_key": "farm-master",
            },
            {
                "source_field": "variety_code",
                "source_code": "variety-1",
                "target_type": "VARIETY",
                "target_business_key": "variety-master",
            },
        ),
        now=NOW,
    )
