from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.actual_harvest_import.enums import (
    ActualHarvestBatchSealStatus,
    ActualHarvestImportBatchStatus,
    ActualHarvestImportChannel,
    ActualHarvestMissingRecordSemantics,
    ActualHarvestPhysicalEvent,
    ActualHarvestQuantityBasis,
    ActualHarvestQuantityUnit,
)
from backend.app.actual_harvest_import.models import ActualHarvestImportBatchModel
from backend.app.models.trial import TrialResourceBindingModel
from backend.app.repositories.trial_resource_binding import (
    TrialResourceBindingConflictError,
    TrialResourceBindingInputError,
    TrialResourceKind,
    TrialResourceNotFoundError,
    authorize_trial_resource,
    create_forecast_binding_in_result_boundary,
    create_quality_binding_in_result_boundary,
)

OWNER = "actor:one"
FORECAST_ID = "a" * 64
QUALITY_ID = "b" * 64
SCOPE_HASH = "c" * 64
IMPORT_ID = "import-1"


@pytest.fixture
async def sqlite_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(ActualHarvestImportBatchModel.__table__.create)
        await connection.run_sync(TrialResourceBindingModel.__table__.create)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def _batch(*, owner: str = OWNER, status: str = ActualHarvestImportBatchStatus.COMMITTED.value):
    now = datetime.now(UTC)
    return ActualHarvestImportBatchModel(
        import_id=IMPORT_ID,
        import_channel=ActualHarvestImportChannel.CSV.value,
        source_system="trial-source",
        source_dataset="harvest",
        source_version="v1",
        external_batch_id="external-1",
        idempotency_key="idem-1",
        submitted_at=now,
        import_received_at=now,
        ingested_at=now,
        submitted_by_identity=owner,
        expected_record_count_or_null=1,
        uploaded_record_count=1,
        sealed_record_count_or_null=1,
        sealed_at_or_null=now,
        sealed_by_identity_or_null=owner,
        seal_status=ActualHarvestBatchSealStatus.SEALED.value,
        server_raw_payload_hash_or_null=None,
        canonical_batch_hash_or_null=None,
        seal_manifest_hash_or_null=None,
        source_file_name_or_null="harvest.csv",
        source_file_hash_or_null=None,
        raw_payload_hash="d" * 64,
        schema_version="v1",
        mapping_policy_version="v1",
        validation_policy_version="v1",
        source_semantics_attestation_version="v1",
        source_semantics_physical_event=ActualHarvestPhysicalEvent.FARM_PICK.value,
        source_semantics_quantity_basis=ActualHarvestQuantityBasis.OBSERVED_WEIGHT.value,
        source_semantics_quantity_unit=ActualHarvestQuantityUnit.KG.value,
        source_semantics_missing_record_semantics=ActualHarvestMissingRecordSemantics.UNKNOWN_NOT_ZERO.value,
        source_semantics_attestation_hash="e" * 64,
        status=status,
        record_count=1,
        valid_record_count=1,
        invalid_record_count=0,
        committed_record_count=1,
        validated_at_or_null=now,
        committed_at_or_null=(
            now if status == ActualHarvestImportBatchStatus.COMMITTED.value else None
        ),
    )


async def test_forecast_create_exact_replay_and_conflict(sqlite_session: AsyncSession) -> None:
    first = await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    replay = await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    assert replay == first
    assert not hasattr(first, "id")
    with pytest.raises(TrialResourceBindingConflictError):
        await create_forecast_binding_in_result_boundary(
            sqlite_session,
            public_forecast_id=FORECAST_ID,
            owner_identity="actor:two",
            business_scope_hash=SCOPE_HASH,
        )


async def test_quality_create_requires_committed_same_owner_import(
    sqlite_session: AsyncSession,
) -> None:
    sqlite_session.add(_batch())
    await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    quality = await create_quality_binding_in_result_boundary(
        sqlite_session,
        public_quality_report_id=QUALITY_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
        parent_forecast_public_id=FORECAST_ID,
        parent_import_id=IMPORT_ID,
    )
    assert quality.parent_forecast_public_id_or_null == FORECAST_ID
    assert quality.parent_import_id_or_null == IMPORT_ID


@pytest.mark.parametrize(
    ("owner", "status"),
    [
        ("actor:two", ActualHarvestImportBatchStatus.COMMITTED.value),
        (OWNER, ActualHarvestImportBatchStatus.RECEIVED.value),
    ],
)
async def test_quality_parent_mismatch_is_concealed(
    sqlite_session: AsyncSession,
    owner: str,
    status: str,
) -> None:
    sqlite_session.add(_batch(owner=owner, status=status))
    await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    with pytest.raises(TrialResourceNotFoundError):
        await create_quality_binding_in_result_boundary(
            sqlite_session,
            public_quality_report_id=QUALITY_ID,
            owner_identity=OWNER,
            business_scope_hash=SCOPE_HASH,
            parent_forecast_public_id=FORECAST_ID,
            parent_import_id=IMPORT_ID,
        )


async def test_authorization_is_single_scoped_resource_lookup(
    sqlite_session: AsyncSession,
) -> None:
    await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    authorized = await authorize_trial_resource(
        sqlite_session,
        resource_kind=TrialResourceKind.FORECAST,
        public_resource_id=FORECAST_ID,
        owner_identity=OWNER,
    )
    assert authorized.public_resource_id == FORECAST_ID
    for kind, owner in ((TrialResourceKind.FORECAST, "actor:two"), ("QUALITY_REPORT", OWNER)):
        with pytest.raises(TrialResourceNotFoundError):
            await authorize_trial_resource(
                sqlite_session,
                resource_kind=kind,
                public_resource_id=FORECAST_ID,
                owner_identity=owner,
            )


async def test_invalid_input_and_rollback_do_not_commit(sqlite_session: AsyncSession) -> None:
    with pytest.raises(TrialResourceBindingInputError):
        await create_forecast_binding_in_result_boundary(
            sqlite_session,
            public_forecast_id="not-a-hash",
            owner_identity=OWNER,
            business_scope_hash=SCOPE_HASH,
        )
    await create_forecast_binding_in_result_boundary(
        sqlite_session,
        public_forecast_id=FORECAST_ID,
        owner_identity=OWNER,
        business_scope_hash=SCOPE_HASH,
    )
    await sqlite_session.rollback()
    assert (
        await sqlite_session.scalar(
            select(TrialResourceBindingModel.id).where(
                TrialResourceBindingModel.public_resource_id == FORECAST_ID
            )
        )
        is None
    )
