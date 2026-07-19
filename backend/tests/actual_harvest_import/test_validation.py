from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from backend.app.actual_harvest_import.api_auth import get_actual_harvest_actor
from backend.app.actual_harvest_import.api_schemas import ActualHarvestApiRecordInput
from backend.app.actual_harvest_import.canonical_hashes import compute_canonical_record_hash
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.actual_harvest_import.validation_hashes import (
    ACTUAL_HARVEST_SEASON_RESOLVER_VERSION,
    compute_validation_result_hash,
    digest,
)
from backend.app.actual_harvest_import.validation_models import (
    ActualHarvestMappingSnapshotModel,
    ActualHarvestValidationAttemptModel,
    ActualHarvestValidationMappingEvidenceModel,
    ActualHarvestValidationResultModel,
    ActualHarvestValidationRunModel,
)
from backend.app.actual_harvest_import.validation_service import (
    ValidationErrorValue,
    _lineage_evidence,
    _sorted_errors,
    begin_validation,
    build_validation_evidence,
    create_mapping_registry,
    finalize_validation,
    seal_mapping_registry,
)
from backend.app.models.master_data import Farm, Season, Subfarm, Variety
from backend.tests.actual_harvest_import.test_api_schemas import _create_payload, _record_payload

NOW = datetime(2026, 7, 18, 8, tzinfo=UTC)


def test_lineage_collision_authority_is_not_sort_order_dependent() -> None:
    current = _record_payload()
    current.update(
        {
            "external_logical_record_id": "a-current-record",
            "external_revision_id": "revision-shared",
            "revision_number": 1,
        }
    )
    committed = dict(current)
    committed.update(
        {
            "external_logical_record_id": "z-committed-record",
            "external_batch_id": "committed-batch",
            "revision_number": 1,
        }
    )
    current_record = ActualHarvestApiRecordInput.model_validate(current)
    committed_record = ActualHarvestApiRecordInput.model_validate(committed)
    committed_hash = compute_canonical_record_hash(committed_record)

    nodes, _edges, errors = _lineage_evidence(
        (current_record,),
        (
            {
                "source_system": committed_record.source_system,
                "external_logical_record_id": committed_record.external_logical_record_id,
                "external_revision_id": committed_record.external_revision_id,
                "revision_number": committed_record.revision_number,
                "record_status": committed_record.record_status.value,
                "predecessor_revision_id": committed_record.supersedes_external_revision_id,
                "canonical_record_hash": committed_hash,
                "source_recorded_at": committed_record.source_recorded_at,
                "source_recorded_at_authority_status": (
                    committed_record.source_recorded_at_authority_status.value
                ),
                "committed_batch_ref": committed_record.external_batch_id,
            },
        ),
    )

    collision_errors = [error for error in errors if error.code == "REVISION_IDENTITY_CONFLICT"]
    assert len(collision_errors) == 1
    assert collision_errors[0].record_index == 1
    assert collision_errors[0].logical_id == current_record.external_logical_record_id
    assert collision_errors[0].revision_id == current_record.external_revision_id
    assert collision_errors[0].field_path == "external_revision_id"
    assert collision_errors[0].details == {"authority": "COMMITTED_SOURCE_REVISION_HISTORY"}
    assert [node["external_logical_record_id"] for node in nodes] == [
        committed_record.external_logical_record_id
    ]


def test_sorted_errors_deduplicates_only_canonical_error_identity() -> None:
    def make_error(**changes: object) -> ValidationErrorValue:
        values: dict[str, object] = {
            "severity": "ERROR",
            "code": "IDENTITY_MAPPING_NOT_FOUND",
            "record_index": 1,
            "logical_id": "logical-1",
            "revision_id": "revision-1",
            "field_path": "farm_code",
            "details": {"reason": "missing"},
        }
        values.update(changes)
        return ValidationErrorValue(**values)  # type: ignore[arg-type]

    candidates = (
        make_error(),
        make_error(),
        make_error(record_index=2, logical_id="logical-2", revision_id="revision-2"),
        make_error(field_path="variety_code"),
        make_error(code="REVISION_IDENTITY_CONFLICT"),
        make_error(details={"reason": "ambiguous"}),
    )
    forward = _sorted_errors(list(candidates))
    reverse = _sorted_errors(list(reversed(candidates)))
    forward_payloads = tuple(error.payload() for error in forward)
    reverse_payloads = tuple(error.payload() for error in reverse)

    assert forward_payloads == reverse_payloads
    assert len(forward_payloads) == 5
    assert len({digest(payload) for payload in forward_payloads}) == 5

    def result_hash(errors: tuple[dict[str, object], ...]) -> str:
        return compute_validation_result_hash(
            seal_manifest_hash="a" * 64,
            mapping_snapshot_hash="b" * 64,
            mapping_policy_version="mapping-v1",
            validation_policy_version="validation-v1",
            record_hashes=(),
            mapping_outcomes=(),
            nodes=(),
            edges=(),
            errors=errors,
            warnings=(),
            counts={
                "valid_count": 0,
                "invalid_count": 2,
                "error_count": len(errors),
                "warning_count": 0,
            },
            committed_lineage_basis_hash="c" * 64,
            lineage_graph_hash="d" * 64,
        )

    assert result_hash(forward_payloads) == result_hash(reverse_payloads)


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
    assert validation["resolved_identity_snapshot_hash"]
    assert validation["season_resolver_version"] == ACTUAL_HARVEST_SEASON_RESOLVER_VERSION

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
        mappings = (
            await session.scalars(
                select(ActualHarvestValidationMappingEvidenceModel).order_by(
                    ActualHarvestValidationMappingEvidenceModel.source_field
                )
            )
        ).all()
        assert {mapping.target_type for mapping in mappings} == {
            "SEASON",
            "FARM",
            "SUBFARM",
            "VARIETY",
        }
        assert all(mapping.resolved_master_record_hash for mapping in mappings)
        assert all(
            mapping.resolver_version == ACTUAL_HARVEST_SEASON_RESOLVER_VERSION
            for mapping in mappings
        )
        run = await session.scalar(
            select(ActualHarvestValidationRunModel).where(
                ActualHarvestValidationRunModel.batch_id == batch.id,
                ActualHarvestValidationRunModel.is_current.is_(True),
            )
        )
        assert run is not None
        snapshot = await session.scalar(
            select(ActualHarvestMappingSnapshotModel).where(
                ActualHarvestMappingSnapshotModel.validation_run_id == run.id
            )
        )
        result = await session.scalar(
            select(ActualHarvestValidationResultModel).where(
                ActualHarvestValidationResultModel.validation_run_id == run.id
            )
        )
        assert snapshot is not None and result is not None
        assert snapshot.season_resolver_version == ACTUAL_HARVEST_SEASON_RESOLVER_VERSION
        assert result.season_resolver_version == ACTUAL_HARVEST_SEASON_RESOLVER_VERSION
        assert ACTUAL_HARVEST_SEASON_RESOLVER_VERSION in result.result_payload


@pytest.mark.asyncio
async def test_missing_season_code_uses_unique_date_range_resolver(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    payload = _create_payload()
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=payload,
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    record = _record_payload()
    record["season_code"] = None
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
    assert validated.json()["data_or_null"]["validation"]["validation_status"] == "VALIDATED"


@pytest.mark.asyncio
async def test_season_date_mismatch_is_validation_error(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    async with sqlite_session_maker() as session:
        async with session.begin():
            season = await session.scalar(select(Season).where(Season.code == "2026"))
            assert season is not None
            season.start_date = datetime(2027, 1, 1).date()
            season.end_date = datetime(2027, 12, 31).date()
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
    validated = await api_client.post(
        f"/api/v1/actual-harvest/imports/{import_id}/validate",
        json={},
        headers={"content-type": "application/json"},
    )
    assert validated.status_code == 200
    assert validated.json()["data_or_null"]["validation"]["validation_status"] == (
        "VALIDATION_FAILED"
    )
    errors = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}/errors")
    assert errors.status_code == 200
    assert errors.json()["data_or_null"]["errors"][0]["error_code"] == (
        "SEASON_BUSINESS_DATE_MISMATCH"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("start_date", "end_date", "harvest_date"),
    [
        ("2026-07-17", "2026-12-31", "2026-07-17"),
        ("2026-01-01", "2026-07-17", "2026-07-17"),
    ],
)
async def test_missing_season_code_accepts_inclusive_date_boundaries(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
    start_date: str,
    end_date: str,
    harvest_date: str,
) -> None:
    await _seed_registry(sqlite_session_maker)
    async with sqlite_session_maker() as session:
        async with session.begin():
            season = await session.scalar(select(Season).where(Season.code == "2026"))
            assert season is not None
            season.start_date = datetime.fromisoformat(start_date).date()
            season.end_date = datetime.fromisoformat(end_date).date()
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    record = _record_payload()
    record["season_code"] = None
    record["harvest_business_date"] = harvest_date
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
    assert validated.json()["data_or_null"]["validation"]["validation_status"] == "VALIDATED"


@pytest.mark.asyncio
async def test_missing_season_code_rejects_ambiguous_overlapping_ranges(
    api_client: AsyncClient,
    sqlite_session_maker: async_sessionmaker[AsyncSession],
    authorized_actor,
) -> None:
    await _seed_registry(sqlite_session_maker)
    async with sqlite_session_maker() as session:
        async with session.begin():
            session.add(
                Season(
                    id=2,
                    code="2026-overlap",
                    start_date=datetime(2026, 7, 1).date(),
                    end_date=datetime(2026, 7, 31).date(),
                )
            )
    app = api_client._transport.app  # type: ignore[attr-defined]
    app.dependency_overrides[get_actual_harvest_actor] = lambda: authorized_actor
    created = await api_client.post(
        "/api/v1/actual-harvest/imports",
        json=_create_payload(),
        headers={"content-type": "application/json"},
    )
    import_id = created.json()["data_or_null"]["batch"]["import_id"]
    record = _record_payload()
    record["season_code"] = None
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
    assert validated.json()["data_or_null"]["validation"]["validation_status"] == (
        "VALIDATION_FAILED"
    )
    errors = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}/errors")
    assert errors.status_code == 200
    assert errors.json()["data_or_null"]["errors"][0]["error_code"] == (
        "SEASON_RESOLUTION_AMBIGUOUS"
    )


@pytest.mark.asyncio
async def test_missing_season_code_rejects_when_no_date_range_matches(
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
    record["season_code"] = None
    record["harvest_business_date"] = "2030-07-17"
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
    assert validated.json()["data_or_null"]["validation"]["validation_status"] == (
        "VALIDATION_FAILED"
    )
    errors = await api_client.get(f"/api/v1/actual-harvest/imports/{import_id}/errors")
    assert errors.status_code == 200
    assert errors.json()["data_or_null"]["errors"][0]["error_code"] == (
        "SEASON_RESOLUTION_NOT_FOUND"
    )


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


@pytest.mark.asyncio
async def test_master_identity_drift_blocks_validation_finalization_without_evidence(
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
            start = await session.run_sync(
                lambda sync_session: begin_validation(sync_session, import_id=import_id, now=NOW)
            )
        assert start.run_id is not None and start.attempt_id is not None
        evidence = await session.run_sync(
            lambda sync_session: build_validation_evidence(
                sync_session,
                run_id=start.run_id,
                attempt_id=start.attempt_id,
            )
        )
        await session.rollback()
        async with session.begin():
            farm = await session.scalar(select(Farm).where(Farm.name == "farm-master"))
            assert farm is not None
            farm.name = "farm-master-renamed"
        async with session.begin():
            result = await session.run_sync(
                lambda sync_session: finalize_validation(
                    sync_session,
                    evidence=evidence,
                    now=NOW,
                )
            )
        assert result == "STALE"
        batch = await session.scalar(
            select(ActualHarvestImportBatchModel).where(
                ActualHarvestImportBatchModel.import_id == import_id
            )
        )
        assert batch is not None and batch.status == "SEALED"
        result_count = await session.scalar(
            select(func.count()).select_from(ActualHarvestValidationResultModel)
        )
        assert result_count == 0


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
