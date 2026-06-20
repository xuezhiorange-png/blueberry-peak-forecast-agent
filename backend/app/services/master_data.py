from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import Base
from backend.app.repositories.master_data import (
    create_record,
    delete_record,
    get_record,
    list_records,
)


def _conflict_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="master data constraint conflict",
    )


def _not_found_error(resource_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource_name} not found",
    )


async def create_master_data[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    values: dict[str, Any],
) -> ModelT:
    try:
        record = await create_record(session, model, values)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict_error() from exc
    return record


async def get_master_data[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    record_id: int,
    resource_name: str,
) -> ModelT:
    record = await get_record(session, model, record_id)
    if record is None:
        raise _not_found_error(resource_name)
    return record


async def list_master_data[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    *,
    filters: list[Any],
    limit: int,
    offset: int,
) -> tuple[list[ModelT], int]:
    return await list_records(session, model, filters=filters, limit=limit, offset=offset)


async def update_master_data[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    record_id: int,
    resource_name: str,
    values: dict[str, Any],
) -> ModelT:
    record = await get_master_data(session, model, record_id, resource_name)
    for key, value in values.items():
        setattr(record, key, value)
    try:
        await session.flush()
        await session.refresh(record)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict_error() from exc
    return record


async def delete_master_data[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    record_id: int,
    resource_name: str,
) -> None:
    record = await get_master_data(session, model, record_id, resource_name)
    try:
        await delete_record(session, record)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _conflict_error() from exc
