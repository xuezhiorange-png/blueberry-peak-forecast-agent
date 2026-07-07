from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.master_data import Farm, Season, Variety
from backend.app.models.planning import (
    MinimalForecastTask,
    ParameterInferenceResult,
    ParameterInferenceRun,
    ParameterLibraryVersion,
)
from backend.app.planning.json_types import canonical_json_value


def _now() -> datetime:
    return datetime.now(UTC)


async def get_variety_by_lookup(
    session: AsyncSession,
    *,
    variety_id: int | None,
    variety_code: str | None,
    variety_name: str | None,
) -> Variety | None:
    if variety_id is not None:
        return await session.get(Variety, variety_id)

    statement = select(Variety)
    if variety_code is not None:
        statement = statement.where(func.lower(Variety.code) == variety_code.lower())
    elif variety_name is not None:
        statement = statement.where(func.lower(Variety.name) == variety_name.lower())
    else:
        return None
    return cast(Variety | None, await session.scalar(statement))


async def get_farm_by_name(session: AsyncSession, *, farm_name: str) -> Farm | None:
    return cast(Farm | None, await session.scalar(select(Farm).where(Farm.name == farm_name)))


async def get_season_by_code(session: AsyncSession, *, season_code: str) -> Season | None:
    return cast(
        Season | None,
        await session.scalar(select(Season).where(Season.code == season_code)),
    )


async def get_active_library_version(
    session: AsyncSession,
    *,
    as_of_date: date | None = None,
) -> ParameterLibraryVersion | None:
    statement = select(ParameterLibraryVersion).where(ParameterLibraryVersion.status == "active")
    if as_of_date is not None:
        statement = statement.where(ParameterLibraryVersion.effective_from <= as_of_date)
    return cast(
        ParameterLibraryVersion | None,
        await session.scalar(
            statement.order_by(
                ParameterLibraryVersion.effective_from.desc(),
                ParameterLibraryVersion.id.desc(),
            )
        ),
    )


async def get_latest_effective_library_version(
    session: AsyncSession,
    *,
    as_of_date: date,
) -> ParameterLibraryVersion | None:
    return cast(
        ParameterLibraryVersion | None,
        await session.scalar(
            select(ParameterLibraryVersion)
            .where(
                ParameterLibraryVersion.status.in_(("active", "retired")),
                ParameterLibraryVersion.effective_from <= as_of_date,
            )
            .order_by(
                ParameterLibraryVersion.effective_from.desc(),
                ParameterLibraryVersion.id.desc(),
            )
        ),
    )


async def get_library_version_by_code(
    session: AsyncSession,
    *,
    version_code: str,
) -> ParameterLibraryVersion | None:
    return cast(
        ParameterLibraryVersion | None,
        await session.scalar(
            select(ParameterLibraryVersion).where(
                ParameterLibraryVersion.version_code == version_code
            )
        ),
    )


async def get_library_version_by_id(
    session: AsyncSession,
    *,
    library_version_id: int,
) -> ParameterLibraryVersion | None:
    return cast(
        ParameterLibraryVersion | None,
        await session.scalar(
            select(ParameterLibraryVersion).where(ParameterLibraryVersion.id == library_version_id)
        ),
    )


async def get_task_by_hash(
    session: AsyncSession,
    *,
    input_hash: str,
    as_of_date: date,
) -> MinimalForecastTask | None:
    return cast(
        MinimalForecastTask | None,
        await session.scalar(
            select(MinimalForecastTask).where(
                MinimalForecastTask.input_hash == input_hash,
                MinimalForecastTask.as_of_date == as_of_date,
            )
        ),
    )


async def get_task(session: AsyncSession, *, task_id: int) -> MinimalForecastTask | None:
    return await session.get(MinimalForecastTask, task_id)


async def find_existing_run(
    session: AsyncSession,
    *,
    input_hash: str,
    as_of_date: date,
    resolver_version: str,
    library_version_id: int,
    config_hash: str,
) -> ParameterInferenceRun | None:
    return cast(
        ParameterInferenceRun | None,
        await session.scalar(
            select(ParameterInferenceRun)
            .where(
                ParameterInferenceRun.input_hash == input_hash,
                ParameterInferenceRun.as_of_date == as_of_date,
                ParameterInferenceRun.resolver_version == resolver_version,
                ParameterInferenceRun.library_version_id == library_version_id,
                ParameterInferenceRun.config_hash == config_hash,
                ParameterInferenceRun.status.in_(("running", "completed")),
            )
            .order_by(ParameterInferenceRun.id.desc())
        ),
    )


async def get_run_by_task(
    session: AsyncSession,
    *,
    task_id: int,
) -> ParameterInferenceRun | None:
    return cast(
        ParameterInferenceRun | None,
        await session.scalar(
            select(ParameterInferenceRun)
            .where(ParameterInferenceRun.task_id == task_id)
            .order_by(ParameterInferenceRun.id.desc())
        ),
    )


async def get_run_by_id(
    session: AsyncSession,
    *,
    run_id: int,
) -> ParameterInferenceRun | None:
    return cast(
        ParameterInferenceRun | None,
        await session.scalar(
            select(ParameterInferenceRun).where(ParameterInferenceRun.id == run_id)
        ),
    )


async def create_task(
    session: AsyncSession,
    *,
    input_payload: dict[str, Any],
    normalized_input: dict[str, Any],
    input_hash: str,
    as_of_date: date,
    status: str,
) -> MinimalForecastTask:
    task = MinimalForecastTask(
        input_payload=cast(dict[str, Any], canonical_json_value(input_payload)),
        normalized_input=cast(dict[str, Any], canonical_json_value(normalized_input)),
        input_hash=input_hash,
        as_of_date=as_of_date,
        status=status,
    )
    session.add(task)
    await session.commit()
    return task


async def create_running_run(
    session: AsyncSession,
    *,
    task_id: int,
    input_hash: str,
    as_of_date: date,
    resolver_version: str,
    library_version_id: int,
    config_hash: str,
    source_signature: str,
) -> ParameterInferenceRun:
    run = ParameterInferenceRun(
        task_id=task_id,
        input_hash=input_hash,
        as_of_date=as_of_date,
        resolver_version=resolver_version,
        library_version_id=library_version_id,
        config_hash=config_hash,
        source_signature=source_signature,
        status="running",
    )
    session.add(run)
    await session.commit()
    return run


async def replace_results(
    session: AsyncSession,
    *,
    run_id: int,
    rows: list[dict[str, Any]],
) -> None:
    await session.execute(
        delete(ParameterInferenceResult).where(ParameterInferenceResult.run_id == run_id)
    )
    session.add_all(
        [
            ParameterInferenceResult(
                run_id=run_id,
                variety_id=int(row["variety_id"]),
                parameter_type=str(row["parameter_type"]),
                status=str(row["status"]),
                p50_value=row["p50_value"],
                p80_lower=row["p80_lower"],
                p80_upper=row["p80_upper"],
                unit=str(row["unit"]),
                source_level=cast(str | None, row.get("source_level")),
                confidence_level=cast(str | None, row.get("confidence_level")),
                confidence_score=row.get("confidence_score"),
                sample_count=int(row["sample_count"]),
                season_count=int(row["season_count"]),
                farm_count=int(row["farm_count"]),
                source_observation_ids=cast(
                    list[int],
                    canonical_json_value(row["source_observation_ids"]),
                ),
                source_metadata=cast(
                    dict[str, Any],
                    canonical_json_value(row["source_metadata"]),
                ),
                uncertainty_metadata=cast(
                    dict[str, Any],
                    canonical_json_value(row["uncertainty_metadata"]),
                ),
            )
            for row in rows
        ]
    )


async def mark_task_status(
    session: AsyncSession,
    *,
    task_id: int,
    status: str,
    error_message: str | None = None,
) -> None:
    await session.execute(
        update(MinimalForecastTask)
        .where(MinimalForecastTask.id == task_id)
        .values(
            status=status,
            error_message=error_message,
            updated_at=_now(),
        )
    )
    await session.commit()


async def mark_run_completed(session: AsyncSession, *, run_id: int) -> None:
    await session.execute(
        update(ParameterInferenceRun)
        .where(ParameterInferenceRun.id == run_id)
        .values(
            status="completed",
            finished_at=_now(),
            error_message=None,
        )
    )
    await session.commit()


async def mark_run_failed(
    session: AsyncSession,
    *,
    run_id: int,
    error_message: str,
) -> None:
    await session.execute(
        update(ParameterInferenceRun)
        .where(ParameterInferenceRun.id == run_id)
        .values(
            status="failed",
            finished_at=_now(),
            error_message=error_message,
        )
    )
    await session.commit()


async def load_result_rows(
    session: AsyncSession,
    *,
    run_id: int,
) -> list[ParameterInferenceResult]:
    return list(
        (
            await session.scalars(
                select(ParameterInferenceResult)
                .where(ParameterInferenceResult.run_id == run_id)
                .order_by(
                    ParameterInferenceResult.variety_id.asc(),
                    ParameterInferenceResult.parameter_type.asc(),
                )
            )
        ).all()
    )
