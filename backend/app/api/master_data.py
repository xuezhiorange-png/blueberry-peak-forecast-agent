from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.session import get_db_session
from backend.app.models.master_data import Factory, Farm, Grade, Holiday, Season, Subfarm, Variety
from backend.app.schemas.master_data import (
    FactoryCreate,
    FactoryList,
    FactoryRead,
    FactoryUpdate,
    FarmCreate,
    FarmList,
    FarmRead,
    FarmUpdate,
    GradeCreate,
    GradeList,
    GradeRead,
    GradeUpdate,
    HolidayCreate,
    HolidayList,
    HolidayRead,
    HolidayUpdate,
    SeasonCreate,
    SeasonList,
    SeasonRead,
    SeasonUpdate,
    SubfarmCreate,
    SubfarmList,
    SubfarmRead,
    SubfarmUpdate,
    VarietyCreate,
    VarietyList,
    VarietyRead,
    VarietyUpdate,
)
from backend.app.services.master_data import (
    create_master_data,
    delete_master_data,
    get_master_data,
    list_master_data,
    update_master_data,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
LimitParam = Annotated[int, Query(ge=1, le=100)]
OffsetParam = Annotated[int, Query(ge=0)]


def _read[ReadT: BaseModel](schema: type[ReadT], record: object) -> ReadT:
    return schema.model_validate(record)


def _validate_merged_date_range(record: Season | Holiday, values: dict[str, Any]) -> None:
    start_date = values.get("start_date", record.start_date)
    end_date = values.get("end_date", record.end_date)
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return
    if end_date < start_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_date must be greater than or equal to start_date",
        )


@router.post("/seasons", response_model=SeasonRead, status_code=status.HTTP_201_CREATED)
async def create_season(payload: SeasonCreate, session: SessionDep) -> SeasonRead:
    record = await create_master_data(session, Season, payload.model_dump())
    return _read(SeasonRead, record)


@router.get("/seasons", response_model=SeasonList)
async def list_seasons(
    session: SessionDep, limit: LimitParam = 50, offset: OffsetParam = 0
) -> SeasonList:
    records, total = await list_master_data(session, Season, filters=[], limit=limit, offset=offset)
    return SeasonList(
        items=[_read(SeasonRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/seasons/{record_id}", response_model=SeasonRead)
async def get_season(record_id: int, session: SessionDep) -> SeasonRead:
    return _read(SeasonRead, await get_master_data(session, Season, record_id, "season"))


@router.patch("/seasons/{record_id}", response_model=SeasonRead)
async def update_season(record_id: int, payload: SeasonUpdate, session: SessionDep) -> SeasonRead:
    values = payload.model_dump(exclude_unset=True)
    existing = await get_master_data(session, Season, record_id, "season")
    _validate_merged_date_range(existing, values)
    record = await update_master_data(
        session,
        Season,
        record_id,
        "season",
        values,
    )
    return _read(SeasonRead, record)


@router.delete("/seasons/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_season(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Season, record_id, "season")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/factories", response_model=FactoryRead, status_code=status.HTTP_201_CREATED)
async def create_factory(payload: FactoryCreate, session: SessionDep) -> FactoryRead:
    record = await create_master_data(session, Factory, payload.model_dump())
    return _read(FactoryRead, record)


@router.get("/factories", response_model=FactoryList)
async def list_factories(
    session: SessionDep,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
    active: bool | None = None,
) -> FactoryList:
    filters = [] if active is None else [Factory.active.is_(active)]
    records, total = await list_master_data(
        session, Factory, filters=filters, limit=limit, offset=offset
    )
    return FactoryList(
        items=[_read(FactoryRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/factories/{record_id}", response_model=FactoryRead)
async def get_factory(record_id: int, session: SessionDep) -> FactoryRead:
    return _read(FactoryRead, await get_master_data(session, Factory, record_id, "factory"))


@router.patch("/factories/{record_id}", response_model=FactoryRead)
async def update_factory(
    record_id: int, payload: FactoryUpdate, session: SessionDep
) -> FactoryRead:
    record = await update_master_data(
        session, Factory, record_id, "factory", payload.model_dump(exclude_unset=True)
    )
    return _read(FactoryRead, record)


@router.delete("/factories/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_factory(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Factory, record_id, "factory")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/farms", response_model=FarmRead, status_code=status.HTTP_201_CREATED)
async def create_farm(payload: FarmCreate, session: SessionDep) -> FarmRead:
    record = await create_master_data(session, Farm, payload.model_dump())
    return _read(FarmRead, record)


@router.get("/farms", response_model=FarmList)
async def list_farms(
    session: SessionDep, limit: LimitParam = 50, offset: OffsetParam = 0
) -> FarmList:
    records, total = await list_master_data(session, Farm, filters=[], limit=limit, offset=offset)
    return FarmList(
        items=[_read(FarmRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/farms/{record_id}", response_model=FarmRead)
async def get_farm(record_id: int, session: SessionDep) -> FarmRead:
    return _read(FarmRead, await get_master_data(session, Farm, record_id, "farm"))


@router.patch("/farms/{record_id}", response_model=FarmRead)
async def update_farm(record_id: int, payload: FarmUpdate, session: SessionDep) -> FarmRead:
    record = await update_master_data(
        session, Farm, record_id, "farm", payload.model_dump(exclude_unset=True)
    )
    return _read(FarmRead, record)


@router.delete("/farms/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_farm(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Farm, record_id, "farm")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/subfarms", response_model=SubfarmRead, status_code=status.HTTP_201_CREATED)
async def create_subfarm(payload: SubfarmCreate, session: SessionDep) -> SubfarmRead:
    record = await create_master_data(session, Subfarm, payload.model_dump())
    return _read(SubfarmRead, record)


@router.get("/subfarms", response_model=SubfarmList)
async def list_subfarms(
    session: SessionDep,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
    farm_id: int | None = None,
) -> SubfarmList:
    filters = [] if farm_id is None else [Subfarm.farm_id == farm_id]
    records, total = await list_master_data(
        session, Subfarm, filters=filters, limit=limit, offset=offset
    )
    return SubfarmList(
        items=[_read(SubfarmRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/subfarms/{record_id}", response_model=SubfarmRead)
async def get_subfarm(record_id: int, session: SessionDep) -> SubfarmRead:
    return _read(SubfarmRead, await get_master_data(session, Subfarm, record_id, "subfarm"))


@router.patch("/subfarms/{record_id}", response_model=SubfarmRead)
async def update_subfarm(
    record_id: int, payload: SubfarmUpdate, session: SessionDep
) -> SubfarmRead:
    record = await update_master_data(
        session, Subfarm, record_id, "subfarm", payload.model_dump(exclude_unset=True)
    )
    return _read(SubfarmRead, record)


@router.delete("/subfarms/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subfarm(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Subfarm, record_id, "subfarm")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/varieties", response_model=VarietyRead, status_code=status.HTTP_201_CREATED)
async def create_variety(payload: VarietyCreate, session: SessionDep) -> VarietyRead:
    record = await create_master_data(session, Variety, payload.model_dump())
    return _read(VarietyRead, record)


@router.get("/varieties", response_model=VarietyList)
async def list_varieties(
    session: SessionDep, limit: LimitParam = 50, offset: OffsetParam = 0
) -> VarietyList:
    records, total = await list_master_data(
        session, Variety, filters=[], limit=limit, offset=offset
    )
    return VarietyList(
        items=[_read(VarietyRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/varieties/{record_id}", response_model=VarietyRead)
async def get_variety(record_id: int, session: SessionDep) -> VarietyRead:
    return _read(VarietyRead, await get_master_data(session, Variety, record_id, "variety"))


@router.patch("/varieties/{record_id}", response_model=VarietyRead)
async def update_variety(
    record_id: int, payload: VarietyUpdate, session: SessionDep
) -> VarietyRead:
    record = await update_master_data(
        session, Variety, record_id, "variety", payload.model_dump(exclude_unset=True)
    )
    return _read(VarietyRead, record)


@router.delete("/varieties/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variety(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Variety, record_id, "variety")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/grades", response_model=GradeRead, status_code=status.HTTP_201_CREATED)
async def create_grade(payload: GradeCreate, session: SessionDep) -> GradeRead:
    record = await create_master_data(session, Grade, payload.model_dump())
    return _read(GradeRead, record)


@router.get("/grades", response_model=GradeList)
async def list_grades(
    session: SessionDep, limit: LimitParam = 50, offset: OffsetParam = 0
) -> GradeList:
    records, total = await list_master_data(session, Grade, filters=[], limit=limit, offset=offset)
    return GradeList(
        items=[_read(GradeRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/grades/{record_id}", response_model=GradeRead)
async def get_grade(record_id: int, session: SessionDep) -> GradeRead:
    return _read(GradeRead, await get_master_data(session, Grade, record_id, "grade"))


@router.patch("/grades/{record_id}", response_model=GradeRead)
async def update_grade(record_id: int, payload: GradeUpdate, session: SessionDep) -> GradeRead:
    record = await update_master_data(
        session, Grade, record_id, "grade", payload.model_dump(exclude_unset=True)
    )
    return _read(GradeRead, record)


@router.delete("/grades/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grade(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Grade, record_id, "grade")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/holidays", response_model=HolidayRead, status_code=status.HTTP_201_CREATED)
async def create_holiday(payload: HolidayCreate, session: SessionDep) -> HolidayRead:
    record = await create_master_data(session, Holiday, payload.model_dump())
    return _read(HolidayRead, record)


@router.get("/holidays", response_model=HolidayList)
async def list_holidays(
    session: SessionDep,
    limit: LimitParam = 50,
    offset: OffsetParam = 0,
    season_id: int | None = None,
    region_name: str | None = None,
    active: bool | None = None,
) -> HolidayList:
    filters = []
    if season_id is not None:
        filters.append(Holiday.season_id == season_id)
    if region_name is not None:
        filters.append(Holiday.region_name == region_name)
    if active is not None:
        filters.append(Holiday.active.is_(active))
    records, total = await list_master_data(
        session, Holiday, filters=filters, limit=limit, offset=offset
    )
    return HolidayList(
        items=[_read(HolidayRead, record) for record in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/holidays/{record_id}", response_model=HolidayRead)
async def get_holiday(record_id: int, session: SessionDep) -> HolidayRead:
    return _read(HolidayRead, await get_master_data(session, Holiday, record_id, "holiday"))


@router.patch("/holidays/{record_id}", response_model=HolidayRead)
async def update_holiday(
    record_id: int, payload: HolidayUpdate, session: SessionDep
) -> HolidayRead:
    values = payload.model_dump(exclude_unset=True)
    existing = await get_master_data(session, Holiday, record_id, "holiday")
    _validate_merged_date_range(existing, values)
    record = await update_master_data(
        session,
        Holiday,
        record_id,
        "holiday",
        values,
    )
    return _read(HolidayRead, record)


@router.delete("/holidays/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(record_id: int, session: SessionDep) -> Response:
    await delete_master_data(session, Holiday, record_id, "holiday")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
