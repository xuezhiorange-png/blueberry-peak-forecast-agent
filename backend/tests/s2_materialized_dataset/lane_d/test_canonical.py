"""Lane D canonical serialization tests."""

from __future__ import annotations

from datetime import date

from backend.app.s2_materialized_dataset.lane_d.canonical import (
    build_partition_bytes,
    build_test_synthetic_bytes,
    row_sort_key,
)
from backend.tests.s2_materialized_dataset.lane_d.conftest import make_row


def test_row_sort_key_orders_by_canonical_grain() -> None:
    rows = (
        make_row(
            season="b",
            farm="a",
            subfarm="a",
            variety="a",
            harvest_business_date=date(2025, 9, 2),
        ),
        make_row(
            season="a",
            farm="z",
            subfarm="a",
            variety="a",
            harvest_business_date=date(2025, 9, 1),
        ),
    )
    ordered = sorted(rows, key=row_sort_key)
    assert ordered[0].season == "a"


def test_partition_bytes_are_order_invariant() -> None:
    row_a = make_row(
        harvest_business_date=date(2025, 9, 1),
        source_row_identity="source-row-a",
        cleaned_row_identity="cleaned-row-a",
    )
    row_b = make_row(
        harvest_business_date=date(2025, 10, 1),
        source_row_identity="source-row-b",
        cleaned_row_identity="cleaned-row-b",
    )
    left = build_partition_bytes((row_b, row_a))
    right = build_partition_bytes((row_a, row_b))
    assert left == right


def test_test_synthetic_bytes_are_deterministic() -> None:
    left = build_test_synthetic_bytes(
        partition_name="TEST",
        partition_start_date="2026-03-10",
        partition_end_date="2026-04-16",
        split_policy_version="v0-3-s1-time-ordered-split-policy-v1",
    )
    right = build_test_synthetic_bytes(
        partition_name="TEST",
        partition_start_date="2026-03-10",
        partition_end_date="2026-04-16",
        split_policy_version="v0-3-s1-time-ordered-split-policy-v1",
    )
    assert left == right
    assert b"s2_test_partition_synthetic" in left
