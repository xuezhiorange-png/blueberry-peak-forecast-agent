from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.app.actual_harvest_import.enums import SourceRecordedAtAuthorityStatus


class TrustedSourceTimestampRecord(Protocol):
    source_recorded_at: datetime | None
    source_recorded_at_authority_status: SourceRecordedAtAuthorityStatus


def validate_non_empty_identifier(value: object, *, field_name: str = "identifier") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def validate_sha256_hex(value: object, *, field_name: str = "hash") -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex")
    return value


def validate_timezone_aware_datetime(value: object, *, field_name: str = "datetime") -> datetime:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def validate_iana_timezone(value: object, *, field_name: str = "timezone") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty IANA timezone")
    normalized = value.strip()
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"{field_name} must be a valid IANA timezone") from exc
    return normalized


def validate_non_negative_finite_decimal(
    value: object,
    *,
    field_name: str = "quantity",
) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field_name} must not be bool or float")
    if not isinstance(value, (Decimal, int, str)):
        raise ValueError(f"{field_name} must be a Decimal, integer, or decimal string")
    try:
        decimal_value = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal") from exc
    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if decimal_value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return decimal_value


def validate_revision_local_shape(
    *,
    revision_number: object,
    external_revision_id: object,
    supersedes_external_revision_id: object,
) -> None:
    if isinstance(revision_number, bool) or not isinstance(revision_number, int):
        raise ValueError("revision_number must be a strict integer")
    if revision_number < 1:
        raise ValueError("revision_number must be at least one")
    revision_id = validate_non_empty_identifier(
        external_revision_id,
        field_name="external_revision_id",
    )
    if revision_number == 1:
        if supersedes_external_revision_id is not None:
            raise ValueError("revision one must not have a predecessor")
        return
    predecessor = validate_non_empty_identifier(
        supersedes_external_revision_id,
        field_name="supersedes_external_revision_id",
    )
    if predecessor == revision_id:
        raise ValueError("a revision must not supersede itself")


def validate_source_recorded_at_authority_shape(
    *,
    status: SourceRecordedAtAuthorityStatus,
    source_recorded_at: datetime | None,
    authority_reference: object,
) -> None:
    reference = None
    if authority_reference is not None:
        reference = validate_non_empty_identifier(
            authority_reference,
            field_name="source_recorded_at_authority_reference_or_null",
        )
    if status == SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP:
        if source_recorded_at is None:
            raise ValueError("trusted source timestamps require source_recorded_at")
        validate_timezone_aware_datetime(source_recorded_at, field_name="source_recorded_at")
        if reference is None:
            raise ValueError("trusted source timestamps require an authority reference")
    elif status == SourceRecordedAtAuthorityStatus.USER_ASSERTED_UNVERIFIED:
        if source_recorded_at is None:
            raise ValueError("user asserted timestamps require source_recorded_at")
        validate_timezone_aware_datetime(source_recorded_at, field_name="source_recorded_at")
    elif status == SourceRecordedAtAuthorityStatus.MISSING:
        if source_recorded_at is not None or reference is not None:
            raise ValueError("missing source time must not carry timestamp or reference")
    elif status == SourceRecordedAtAuthorityStatus.CONFLICTING:
        if source_recorded_at is not None:
            validate_timezone_aware_datetime(source_recorded_at, field_name="source_recorded_at")
        if reference is None:
            raise ValueError("conflicting source time requires an authority reference")


def has_trusted_source_timestamp(record: TrustedSourceTimestampRecord) -> bool:
    return (
        record.source_recorded_at_authority_status
        == SourceRecordedAtAuthorityStatus.TRUSTED_SOURCE_TIMESTAMP
        and record.source_recorded_at is not None
    )


def validate_non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a strict integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value
