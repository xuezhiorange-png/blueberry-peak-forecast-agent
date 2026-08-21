"""S2 canonical serialization helpers for Lane D partition bytes."""

from __future__ import annotations

from backend.app.rolling_backtest.canonical import canonical_json_dumps, canonical_json_value
from backend.app.s2_materialized_dataset.shared.contracts import MaterializableRow


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
