from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.master_data import Factory, Grade, Season, Variety


class IngestFile(Base):
    __tablename__ = "ingest_file"
    __table_args__ = (
        UniqueConstraint("file_sha256", name="uq_ingest_file_file_sha256"),
        CheckConstraint(
            "status in ('running', 'completed', 'failed', 'skipped')",
            name="ck_ingest_file_status",
        ),
        Index("ix_ingest_file_season_id", "season_id"),
        Index("ix_ingest_file_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    season_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id", name="fk_ingest_file_season_id_dim_season", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    inserted_row_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    suspected_duplicate_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_hash: Mapped[str] = mapped_column(Text, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    quality_report: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    season: Mapped[Season | None] = relationship(lazy="raise")
    raw_rows: Mapped[list["FactReceiptRaw"]] = relationship(
        back_populates="ingest_file", lazy="raise"
    )


class FactReceiptRaw(Base):
    __tablename__ = "fact_receipt_raw"
    __table_args__ = (
        UniqueConstraint("source_row_fingerprint", name="uq_fact_receipt_raw_source_row_fp"),
        Index("ix_fact_receipt_raw_ingest_file_id", "ingest_file_id"),
        Index("ix_fact_receipt_raw_season_id", "season_id"),
        Index("ix_fact_receipt_raw_business_fp", "business_fingerprint"),
        Index("ix_fact_receipt_raw_receipt_date", "receipt_date"),
        Index("ix_fact_receipt_raw_factory_id", "factory_id"),
        Index("ix_fact_receipt_raw_variety_id", "variety_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ingest_file_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "ingest_file.id", name="fk_fact_receipt_raw_ingest_file_id", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_season.id", name="fk_fact_receipt_raw_season_id_dim_season", ondelete="RESTRICT"
        ),
        nullable=False,
    )
    source_sheet: Mapped[str] = mapped_column(Text, nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    receipt_date_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_name_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    farm_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    subfarm_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    variety_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight_kg_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    factory_raw: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    factory_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    variety_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    factory_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_factory.id", name="fk_fact_receipt_raw_factory_id_dim_factory", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    variety_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_variety.id", name="fk_fact_receipt_raw_variety_id_dim_variety", ondelete="RESTRICT"
        ),
        nullable=True,
    )
    grade_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "dim_grade.id", name="fk_fact_receipt_raw_grade_id_dim_grade", ondelete="RESTRICT"
        ),
        nullable=True,
    )

    is_date_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_weight_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_factory_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_variety_known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_suspected_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_analysis_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    parse_errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    source_row_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    business_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)

    ingest_file: Mapped[IngestFile] = relationship(back_populates="raw_rows", lazy="raise")
    season: Mapped[Season] = relationship(lazy="raise")
    factory: Mapped[Factory | None] = relationship(lazy="raise")
    variety: Mapped[Variety | None] = relationship(lazy="raise")
    grade: Mapped[Grade | None] = relationship(lazy="raise")
