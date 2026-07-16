from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from backend.app.actual_harvest_import.models import (
    ActualHarvestImportBatchModel,
    ActualHarvestImportRecordModel,
)
from backend.app.actual_harvest_import.persistence import (
    ActualHarvestImportRepository,
    ActualHarvestPersistenceConflict,
)
from backend.app.db.session import AsyncSessionMaker
from backend.tests.actual_harvest_import.test_persistence import _batch, _record
from backend.tests.postgres_test_support import assert_safe_postgres_test_identity

pytestmark = [pytest.mark.postgres, pytest.mark.integration]


def _require_postgres() -> None:
    if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set RUN_POSTGRES_INTEGRATION=1 when PostgreSQL is available")
    assert_safe_postgres_test_identity(env=None)


def _batch_for(suffix: str):
    return _batch(import_id=f"q2a-i2-pg-{suffix}").model_copy(
        update={
            "external_batch_id": f"q2a-i2-batch-{suffix}",
            "idempotency_key": f"q2a-i2-idempotency-{suffix}",
        }
    )


def _record_for(
    suffix: str,
    *,
    logical_id: str | None = None,
    revision_id: str | None = None,
    revision_number: int = 1,
    source_row_number: int | None = 1,
):
    return _record(
        logical_id=logical_id or f"q2a-i2-logical-{suffix}",
        revision_id=revision_id or f"q2a-i2-revision-{suffix}",
        revision_number=revision_number,
        source_row_number=source_row_number,
    ).model_copy(update={"external_batch_id": f"q2a-i2-batch-{suffix}"})


@pytest.mark.asyncio
async def test_postgres_staging_round_trip_and_constraints() -> None:
    _require_postgres()
    repository = ActualHarvestImportRepository()
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch = await session.run_sync(
                lambda sync_session: repository.create_batch(sync_session, _batch())
            )
            records = await session.run_sync(
                lambda sync_session: repository.insert_records(
                    sync_session,
                    import_id=batch.import_id,
                    records=[_record()],
                )
            )
            assert batch.import_id == "opaque-import-1"
            assert records[0].actual_harvest_quantity_kg == _record().actual_harvest_quantity_kg
            assert records[0].source_recorded_at is not None
            assert records[0].source_recorded_at.utcoffset() is not None

            columns = (
                await session.execute(
                    sa.text(
                        "SELECT column_name, data_type "
                        "FROM information_schema.columns "
                        "WHERE table_name IN "
                        "('actual_harvest_import_batch', 'actual_harvest_import_record')"
                    )
                )
            ).all()
            assert not any(data_type in {"json", "jsonb"} for _, data_type in columns)
            quantity_type = next(
                data_type
                for column_name, data_type in columns
                if column_name == "actual_harvest_quantity_kg"
            )
            assert quantity_type == "numeric"

            assert (
                await session.scalar(
                    sa.text(
                        "SELECT COUNT(*) FROM actual_harvest_import_record "
                        "WHERE actual_harvest_quantity_kg = CAST('0.000001' AS NUMERIC)"
                    )
                )
                == 1
            )


@pytest.mark.asyncio
async def test_postgres_unique_constraints_and_conflict_mapping() -> None:
    _require_postgres()
    repository = ActualHarvestImportRepository()
    batch = _batch_for("unique")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: repository.create_batch(sync_session, batch)
            )

    duplicate_batches = (
        batch.model_copy(
            update={
                "idempotency_key": "q2a-i2-idempotency-unique-import-duplicate",
            }
        ),
        batch.model_copy(
            update={
                "import_id": "q2a-i2-pg-unique-external-duplicate",
                "idempotency_key": "q2a-i2-idempotency-unique-external",
            }
        ),
        batch.model_copy(
            update={
                "import_id": "q2a-i2-pg-unique-idempotency-duplicate",
                "external_batch_id": "q2a-i2-batch-unique-idempotency",
            }
        ),
    )
    for duplicate in duplicate_batches:
        async with AsyncSessionMaker() as session:
            with pytest.raises(ActualHarvestPersistenceConflict) as exc_info:
                await session.run_sync(
                    lambda sync_session, value=duplicate: repository.create_batch(
                        sync_session, value
                    )
                )
            assert str(exc_info.value) == (
                "actual harvest import batch identity conflicts with existing data"
            )
            assert isinstance(exc_info.value.__cause__, IntegrityError)
            await session.rollback()

    record = _record_for("records")
    record_batch = _batch_for("records")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            batch_result = await session.run_sync(
                lambda sync_session: repository.create_batch(sync_session, record_batch)
            )
            await session.run_sync(
                lambda sync_session: repository.insert_records(
                    sync_session,
                    import_id=batch_result.import_id,
                    records=[record],
                )
            )

    duplicate_records = (
        _record_for(
            "records",
            logical_id="q2a-i2-logical-revision-duplicate",
            revision_id=record.external_revision_id,
            source_row_number=2,
        ),
        _record_for(
            "records",
            logical_id=record.external_logical_record_id,
            revision_id="q2a-i2-revision-logical-duplicate",
            source_row_number=3,
        ),
    )
    for duplicate in duplicate_records:
        async with AsyncSessionMaker() as session:
            with pytest.raises(ActualHarvestPersistenceConflict) as exc_info:
                await session.run_sync(
                    lambda sync_session, value=duplicate: repository.insert_records(
                        sync_session,
                        import_id=record_batch.import_id,
                        records=[value],
                    )
                )
            assert str(exc_info.value) == (
                "actual harvest import record identity conflicts with existing data"
            )
            assert isinstance(exc_info.value.__cause__, IntegrityError)
            await session.rollback()


@pytest.mark.asyncio
async def test_postgres_composite_fk_and_on_delete_restrict_are_database_enforced() -> None:
    _require_postgres()
    repository = ActualHarvestImportRepository()
    batch = _batch_for("foreign-key")
    record = _record_for("foreign-key")
    async with AsyncSessionMaker() as session:
        async with session.begin():
            await session.run_sync(
                lambda sync_session: repository.create_batch(sync_session, batch)
            )
            await session.run_sync(
                lambda sync_session: repository.insert_records(
                    sync_session,
                    import_id=batch.import_id,
                    records=[record],
                )
            )

    async with AsyncSessionMaker() as session:
        batch_id = await session.scalar(
            sa.select(ActualHarvestImportBatchModel.id).where(
                ActualHarvestImportBatchModel.import_id == batch.import_id
            )
        )
        assert batch_id is not None
        mismatched = record.model_copy(
            update={
                "external_logical_record_id": "q2a-i2-fk-mismatch-logical",
                "external_revision_id": "q2a-i2-fk-mismatch-revision",
                "source_row_number": 2,
                "source_system": "q2a-i2-mismatched-source",
            }
        )
        session.add(
            ActualHarvestImportRecordModel(
                batch_id=batch_id,
                **mismatched.model_dump(mode="python"),
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async with AsyncSessionMaker() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                sa.delete(ActualHarvestImportBatchModel).where(
                    ActualHarvestImportBatchModel.import_id == batch.import_id
                )
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_postgres_repository_does_not_commit_and_caller_rollback_removes_rows() -> None:
    _require_postgres()
    repository = ActualHarvestImportRepository()
    batch = _batch_for("rollback")
    record = _record_for("rollback")
    async with AsyncSessionMaker() as session:
        await session.run_sync(lambda sync_session: repository.create_batch(sync_session, batch))
        await session.run_sync(
            lambda sync_session: repository.insert_records(
                sync_session,
                import_id=batch.import_id,
                records=[record],
            )
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count()).select_from(ActualHarvestImportBatchModel)
            )
            >= 1
        )
        async with AsyncSessionMaker() as other_session:
            assert (
                await other_session.scalar(
                    sa.select(sa.func.count())
                    .select_from(ActualHarvestImportBatchModel)
                    .where(ActualHarvestImportBatchModel.import_id == batch.import_id)
                )
                == 0
            )

        await session.rollback()

    async with AsyncSessionMaker() as session:
        assert (
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestImportBatchModel)
                .where(ActualHarvestImportBatchModel.import_id == batch.import_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(ActualHarvestImportRecordModel)
                .where(
                    ActualHarvestImportRecordModel.external_revision_id
                    == record.external_revision_id
                )
            )
            == 0
        )
