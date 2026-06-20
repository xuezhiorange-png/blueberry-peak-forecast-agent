from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ListResponse[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class DateRangeMixin(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class OptionalDateRangeMixin(BaseModel):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_optional_date_range(self) -> Self:
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class CoordinatesMixin(BaseModel):
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    altitude_m: Decimal | None = None


class SeasonCreate(DateRangeMixin):
    code: str = Field(min_length=1)


class SeasonUpdate(OptionalDateRangeMixin):
    code: str | None = Field(default=None, min_length=1)


class SeasonRead(SeasonCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SeasonList(ListResponse[SeasonRead]):
    pass


class FactoryCreate(CoordinatesMixin):
    code: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    region_name: str | None = None
    active: bool = True


class FactoryUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    region_name: str | None = None
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    altitude_m: Decimal | None = None
    active: bool | None = None


class FactoryRead(FactoryCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FactoryList(ListResponse[FactoryRead]):
    pass


class FarmCreate(CoordinatesMixin):
    name: str = Field(min_length=1)


class FarmUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    latitude: Decimal | None = Field(default=None, ge=Decimal("-90"), le=Decimal("90"))
    longitude: Decimal | None = Field(default=None, ge=Decimal("-180"), le=Decimal("180"))
    altitude_m: Decimal | None = None


class FarmRead(FarmCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FarmList(ListResponse[FarmRead]):
    pass


class SubfarmCreate(BaseModel):
    farm_id: int
    name: str = Field(min_length=1)
    altitude_m: Decimal | None = None


class SubfarmUpdate(BaseModel):
    farm_id: int | None = None
    name: str | None = Field(default=None, min_length=1)
    altitude_m: Decimal | None = None


class SubfarmRead(SubfarmCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class SubfarmList(ListResponse[SubfarmRead]):
    pass


class VarietyCreate(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)


class VarietyUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)


class VarietyRead(VarietyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class VarietyList(ListResponse[VarietyRead]):
    pass


class GradeCreate(BaseModel):
    code: str = Field(min_length=1)
    is_analysis_eligible_default: bool = True


class GradeUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    is_analysis_eligible_default: bool | None = None


class GradeRead(GradeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int


class GradeList(ListResponse[GradeRead]):
    pass


class HolidayCreate(DateRangeMixin):
    season_id: int
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    region_name: str | None = None
    active: bool = True


class HolidayUpdate(OptionalDateRangeMixin):
    season_id: int | None = None
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    region_name: str | None = None
    active: bool | None = None


class HolidayRead(HolidayCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class HolidayList(ListResponse[HolidayRead]):
    pass
