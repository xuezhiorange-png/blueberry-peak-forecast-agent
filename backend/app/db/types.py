"""Shared SQLAlchemy scalar types used by model modules without package cycles."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.engine import Dialect
from sqlalchemy.types import Numeric, Text, TypeDecorator


class ExactDecimal(TypeDecorator[Decimal]):
    """PostgreSQL unbounded NUMERIC; SQLite text avoids float round trips."""

    impl = Numeric
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        return dialect.type_descriptor(Text() if dialect.name == "sqlite" else Numeric())

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> Any:
        return str(value) if value is not None and dialect.name == "sqlite" else value

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        del dialect
        return None if value is None else Decimal(str(value))


__all__ = ["ExactDecimal"]
