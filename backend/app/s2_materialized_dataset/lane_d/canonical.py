"""S2 canonical serialization helpers for Lane D partition bytes."""

from __future__ import annotations

import json
from datetime import date

from backend.app.harvest_state.canonical import parse_decimal
from backend.app.rolling_backtest.canonical import canonical_json_dumps, canonical_json_value
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow


class MalformedPartitionBytesError(ValueError):
    """Raised when NDJSON partition bytes cannot be parsed into MaterializableRow."""


def canonical_row_payload(row: MaterializableRow) -> dict[str, object]:
    return {
        "actual_harvest_quantity_kg": row.actual_harvest_quantity_kg,
        "cleaned_row_identity": row.cleaned_row_identity,
        "farm": row.farm,
        "harvest_business_date": row.harvest_business_date,
        "pit_visibility_identity": row.pit_visibility_identity,
        "revision_winner_identity": row.revision_winner_identity,
        "season": row.season,
        "source_row_identity": row.source_row_identity,
        "subfarm": row.subfarm,
        "variety": row.variety,
    }


def row_sort_key(row: MaterializableRow) -> tuple[str, str, str, str, str]:
    return (
        row.season,
        row.farm,
        row.subfarm,
        row.variety,
        row.harvest_business_date.isoformat(),
    )


def build_partition_bytes(rows: tuple[MaterializableRow, ...]) -> bytes:
    """Build deterministic NDJSON partition bytes sorted by canonical grain."""
    ordered = sorted(rows, key=row_sort_key)
    lines = [canonical_json_dumps(canonical_row_payload(row)) for row in ordered]
    if not lines:
        return b""
    return ("\n".join(lines) + "\n").encode("utf-8")


_REQUIRED_ROW_FIELDS = (
    "actual_harvest_quantity_kg",
    "cleaned_row_identity",
    "farm",
    "harvest_business_date",
    "pit_visibility_identity",
    "revision_winner_identity",
    "season",
    "source_row_identity",
    "subfarm",
    "variety",
)


def _parse_row_payload(payload: object) -> MaterializableRow:
    if not isinstance(payload, dict):
        raise MalformedPartitionBytesError("partition row must be a JSON object")
    missing = [field for field in _REQUIRED_ROW_FIELDS if field not in payload]
    if missing:
        raise MalformedPartitionBytesError(f"partition row missing fields: {', '.join(missing)}")
    extra = set(payload) - set(_REQUIRED_ROW_FIELDS)
    if extra:
        raise MalformedPartitionBytesError(
            f"partition row has unexpected fields: {', '.join(sorted(extra))}"
        )
    harvest_date_raw = payload["harvest_business_date"]
    if not isinstance(harvest_date_raw, str):
        raise MalformedPartitionBytesError("harvest_business_date must be an ISO date string")
    try:
        harvest_business_date = date.fromisoformat(harvest_date_raw)
    except ValueError as exc:
        raise MalformedPartitionBytesError("harvest_business_date is not ISO format") from exc
    kg_raw = payload["actual_harvest_quantity_kg"]
    if isinstance(kg_raw, bool) or not isinstance(kg_raw, str):
        raise MalformedPartitionBytesError(
            "actual_harvest_quantity_kg must be a canonical decimal string"
        )
    try:
        actual_harvest_quantity_kg = parse_decimal(kg_raw)
    except ValueError as exc:
        raise MalformedPartitionBytesError("actual_harvest_quantity_kg is not canonical") from exc
    identity_fields = (
        "season",
        "farm",
        "subfarm",
        "variety",
        "source_row_identity",
        "cleaned_row_identity",
        "pit_visibility_identity",
        "revision_winner_identity",
    )
    for field in identity_fields:
        value = payload[field]
        if not isinstance(value, str) or not value:
            raise MalformedPartitionBytesError(f"{field} must be a non-empty string")
    return MaterializableRow(
        season=payload["season"],
        farm=payload["farm"],
        subfarm=payload["subfarm"],
        variety=payload["variety"],
        harvest_business_date=harvest_business_date,
        actual_harvest_quantity_kg=actual_harvest_quantity_kg,
        source_row_identity=payload["source_row_identity"],
        cleaned_row_identity=payload["cleaned_row_identity"],
        pit_visibility_identity=payload["pit_visibility_identity"],
        revision_winner_identity=payload["revision_winner_identity"],
    )


def parse_partition_bytes(content: bytes) -> tuple[MaterializableRow, ...]:
    """Parse deterministic NDJSON partition bytes into canonical-order rows."""
    if not content:
        return ()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MalformedPartitionBytesError("partition bytes are not valid UTF-8") from exc
    if not text.endswith("\n"):
        raise MalformedPartitionBytesError("partition bytes must end with a trailing newline")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if not lines:
        return ()
    rows: list[MaterializableRow] = []
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise MalformedPartitionBytesError(f"empty NDJSON line at position {line_number}")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MalformedPartitionBytesError(f"malformed NDJSON at line {line_number}") from exc
        rows.append(_parse_row_payload(payload))
    return tuple(sorted(rows, key=row_sort_key))


def build_test_synthetic_bytes(
    *,
    partition_name: str,
    partition_start_date: str,
    partition_end_date: str,
    split_policy_version: str,
) -> bytes:
    """Synthetic TEST partition bytes without row-level Source002 access."""
    payload = canonical_json_value(
        {
            "partition_date_field": "HARVEST_BUSINESS_DATE",
            "partition_end_date": partition_end_date,
            "partition_name": partition_name,
            "partition_start_date": partition_start_date,
            "s2_test_partition_synthetic": True,
            "split_policy_version": split_policy_version,
        }
    )
    return (canonical_json_dumps(payload) + "\n").encode("utf-8")
