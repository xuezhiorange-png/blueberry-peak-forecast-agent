from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import numpy as np
import pytest

from backend.app.baseline.json_types import canonical_json_value, canonicalize_result_row
from backend.app.baseline.schemas import BacktestResultRow
from backend.app.baseline.service import _sort_result_rows


def _result_row() -> BacktestResultRow:
    return BacktestResultRow(
        baseline_name="ridge_structure",
        target_season_id=1,
        target_season_code="2025-2026",
        factory_id=10,
        factory_name="Factory A",
        previous_season_id=2,
        previous_season_code="2024-2025",
        fold_key="season:2025-2026",
        status="evaluated",
        actual_stable_peak_kg=Decimal("100.000000"),
        predicted_stable_peak_kg=Decimal("95.500000"),
        absolute_error_kg=Decimal("4.500000"),
        signed_error_kg=Decimal("-4.500000"),
        ape=Decimal("0.0450000000"),
        input_features={
            "previous_season_stable_peak_kg": Decimal("100.000000"),
            "oracle_total_weight_kg": Decimal("1200.000000"),
        },
        training_season_codes=["2024-2025", "2026-2027"],
        model_metadata={
            "feature_names": [
                "total_weight_kg",
                "variety_hhi",
                "farm_hhi",
                "subfarm_hhi",
            ],
            "scaler_mean": [np.float64(1.25), np.float64(2.5)],
            "enabled": np.bool_(True),
            "as_of": date(2026, 1, 1),
        },
    )


def test_canonical_json_value_formats_decimal_as_fixed_point_string() -> None:
    assert canonical_json_value(Decimal("100.000000")) == "100.000000"


def test_canonical_json_value_preserves_high_precision_decimal() -> None:
    assert canonical_json_value(Decimal("0.1234567890")) == "0.1234567890"


def test_canonical_json_value_converts_numpy_scalar_to_python_scalar() -> None:
    value = canonical_json_value(np.float64(1.25))
    assert value == 1.25
    assert type(value) is float


def test_canonical_json_value_recursively_normalizes_nested_structures() -> None:
    value = canonical_json_value(
        {
            "weight": Decimal("100.000000"),
            "scaler": [np.float64(1.25), np.float64(2.50)],
            "metadata": {
                "enabled": np.bool_(True),
            },
        }
    )
    assert value == {
        "weight": "100.000000",
        "scaler": [1.25, 2.5],
        "metadata": {"enabled": True},
    }


def test_canonical_json_value_rejects_unsupported_types() -> None:
    class Unsupported:
        pass

    with pytest.raises(TypeError):
        canonical_json_value(Unsupported())


def test_canonicalize_result_row_round_trips_json_fields_stably() -> None:
    canonical_row = canonicalize_result_row(_result_row())
    assert canonical_row.input_features == {
        "previous_season_stable_peak_kg": "100.000000",
        "oracle_total_weight_kg": "1200.000000",
    }
    assert canonical_row.model_metadata["scaler_mean"] == [1.25, 2.5]
    assert canonical_row.model_metadata["enabled"] is True
    assert canonical_row.model_metadata["as_of"] == "2026-01-01"

    persisted_input = json.loads(json.dumps(canonical_row.input_features))
    persisted_metadata = json.loads(json.dumps(canonical_row.model_metadata))
    persisted_training_codes = json.loads(json.dumps(canonical_row.training_season_codes))
    reloaded_row = BacktestResultRow(
        **{
            **canonical_row.__dict__,
            "input_features": persisted_input,
            "model_metadata": persisted_metadata,
            "training_season_codes": persisted_training_codes,
        }
    )

    assert reloaded_row == canonical_row


def test_sort_result_rows_matches_repository_reload_order() -> None:
    season_order = {
        "2024-2025": 0,
        "2025-2026": 1,
    }
    later_baseline = _result_row()
    earlier_baseline = BacktestResultRow(
        **{
            **later_baseline.__dict__,
            "baseline_name": "previous_season_peak",
            "target_season_code": "2024-2025",
            "factory_id": 2,
            "factory_name": "Factory B",
        }
    )
    middle_baseline = BacktestResultRow(
        **{
            **later_baseline.__dict__,
            "baseline_name": "previous_season_peak",
            "target_season_code": "2025-2026",
            "factory_id": 1,
            "factory_name": "Factory A",
        }
    )

    ordered = _sort_result_rows(
        [later_baseline, middle_baseline, earlier_baseline],
        season_order=season_order,
    )

    assert ordered == [
        earlier_baseline,
        middle_baseline,
        later_baseline,
    ]
