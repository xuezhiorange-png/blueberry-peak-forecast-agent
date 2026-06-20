from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base


class Season(Base):
    __tablename__ = "dim_season"
    __table_args__ = (
        UniqueConstraint("code", name="uq_dim_season_code"),
        CheckConstraint("end_date >= start_date", name="ck_dim_season_date_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    holidays: Mapped[list["Holiday"]] = relationship(back_populates="season", lazy="raise")


class Factory(Base):
    __tablename__ = "dim_factory"
    __table_args__ = (
        UniqueConstraint("code", name="uq_dim_factory_code"),
        UniqueConstraint("name", name="uq_dim_factory_name"),
        Index("ix_dim_factory_active", "active"),
        CheckConstraint(
            "latitude is null or (latitude >= -90 and latitude <= 90)",
            name="ck_dim_factory_latitude_range",
        ),
        CheckConstraint(
            "longitude is null or (longitude >= -180 and longitude <= 180)",
            name="ck_dim_factory_longitude_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Farm(Base):
    __tablename__ = "dim_farm"
    __table_args__ = (
        UniqueConstraint("name", name="uq_dim_farm_name"),
        CheckConstraint(
            "latitude is null or (latitude >= -90 and latitude <= 90)",
            name="ck_dim_farm_latitude_range",
        ),
        CheckConstraint(
            "longitude is null or (longitude >= -180 and longitude <= 180)",
            name="ck_dim_farm_longitude_range",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    subfarms: Mapped[list["Subfarm"]] = relationship(back_populates="farm", lazy="raise")


class Subfarm(Base):
    __tablename__ = "dim_subfarm"
    __table_args__ = (
        UniqueConstraint("farm_id", "name", name="uq_dim_subfarm_farm_id_name"),
        Index("ix_dim_subfarm_farm_id", "farm_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    farm_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("dim_farm.id", name="fk_dim_subfarm_farm_id_dim_farm", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    altitude_m: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)

    farm: Mapped[Farm] = relationship(back_populates="subfarms", lazy="raise")


class Variety(Base):
    __tablename__ = "dim_variety"
    __table_args__ = (UniqueConstraint("code", name="uq_dim_variety_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Grade(Base):
    __tablename__ = "dim_grade"
    __table_args__ = (UniqueConstraint("code", name="uq_dim_grade_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    is_analysis_eligible_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )


class Holiday(Base):
    __tablename__ = "dim_holiday"
    __table_args__ = (
        UniqueConstraint("season_id", "code", name="uq_dim_holiday_season_id_code"),
        Index("ix_dim_holiday_season_id", "season_id"),
        Index("ix_dim_holiday_region_name", "region_name"),
        Index("ix_dim_holiday_active", "active"),
        CheckConstraint("end_date >= start_date", name="ck_dim_holiday_date_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id", name="fk_dim_holiday_season_id_dim_season", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    region_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    season: Mapped[Season] = relationship(back_populates="holidays", lazy="raise")
