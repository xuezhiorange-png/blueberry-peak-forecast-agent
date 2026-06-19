from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.base import Base


async def create_record[ModelT: Base](
    session: AsyncSession, model: type[ModelT], values: dict[str, Any]
) -> ModelT:
    record = model()
    for key, value in values.items():
        setattr(record, key, value)
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def get_record[ModelT: Base](
    session: AsyncSession, model: type[ModelT], record_id: int
) -> ModelT | None:
    return await session.get(model, record_id)


async def list_records[ModelT: Base](
    session: AsyncSession,
    model: type[ModelT],
    *,
    filters: list[Any],
    limit: int,
    offset: int,
) -> tuple[list[ModelT], int]:
    id_column = model.id  # type: ignore[attr-defined]
    list_statement: Select[tuple[ModelT]] = (
        select(model).where(*filters).order_by(id_column.asc()).limit(limit).offset(offset)
    )
    count_statement = select(func.count()).select_from(model).where(*filters)
    records = list((await session.scalars(list_statement)).all())
    total = int((await session.execute(count_statement)).scalar_one())
    return records, total


async def delete_record(session: AsyncSession, record: Base) -> None:
    await session.delete(record)
    await session.flush()
