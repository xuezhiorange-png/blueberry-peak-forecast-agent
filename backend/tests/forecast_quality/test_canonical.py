from decimal import Decimal

from backend.app.forecast_quality.canonical import (
    BASELINE_CANONICAL_CELL_FIELDS,
    BASELINE_CANONICAL_ROOT_FIELDS,
    canonical_json_bytes,
    compute_metric_input_mask_hash,
    emit_s3_decimal,
)


def test_canonical_json_and_mask_are_byte_stable() -> None:
    assert canonical_json_bytes({"b": 1, "a": 2}) == canonical_json_bytes({"a": 2, "b": 1})
    payload = {"metric": "P50", "rows": ["a", "b"]}
    assert compute_metric_input_mask_hash(payload) == compute_metric_input_mask_hash(dict(payload))
    assert emit_s3_decimal(Decimal("2.5")) == "2.500000"


def test_baseline_canonical_field_sets_are_frozen() -> None:
    assert len(BASELINE_CANONICAL_ROOT_FIELDS) == 26
    assert len(BASELINE_CANONICAL_CELL_FIELDS) == 15
    assert BASELINE_CANONICAL_ROOT_FIELDS[-1] == "per_breakdown_cell"
