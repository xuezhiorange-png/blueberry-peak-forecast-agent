from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from backend.app.forecast_quality.enums import SupportedQuantile
from backend.app.forecast_quality.schemas import S3BindingRow
from backend.app.forecast_quality.status_evidence import (
    _validate_cell,
    build_frozen_quality_status_evidence,
)


def _rows() -> tuple[S3BindingRow, ...]:
    return tuple(
        S3BindingRow(
            forecast_business_key=f"forecast-{horizon}-{quantile.value}",
            actual_physical_key=f"actual-{horizon}-{quantile.value}",
            stable_actual_identity=f"actual-{horizon}-{quantile.value}",
            forecast_value_kg=Decimal("10.000000"),
            actual_value_kg=Decimal("9.000000"),
            forecast_quantile=quantile,
            forecast_horizon_days=horizon,
            forecast_target_date=date(2026, 3, 1) + timedelta(days=horizon),
            forecast_cutoff_at=datetime(2026, 3, 1, tzinfo=UTC),
            s2_status="COMPARABLE",
            season_business_key="season:2026",
            farm_business_key="farm:alpha",
            subfarm_business_key="subfarm:alpha-1",
            variety_business_key="variety:legacy",
            model_identity="model-v1",
            actual_visibility_timestamp=datetime(2026, 3, 2, tzinfo=UTC),
        )
        for horizon in (7, 14, 21)
        for quantile in SupportedQuantile
    )


def _evidence():
    return build_frozen_quality_status_evidence(
        requested_horizons_days=(7, 14, 21),
        rows=_rows(),
        source_s2_run_identity="a" * 64,
        source_s2_manifest_identity="b" * 64,
        source_s2_binding_row_set_hash="c" * 64,
    )


def test_status_evidence_has_exact_30_records_and_stable_hashes() -> None:
    first = _evidence()
    second = _evidence()

    assert len(first) == 30
    assert first == second
    assert [cell.metric_result_key_hash for cell in first] == [
        cell.metric_result_key_hash for cell in second
    ]
    assert [cell.canonical_hash for cell in first] == [cell.canonical_hash for cell in second]
    assert {(cell.scope.forecast_horizon_days, cell.forecast_quantile) for cell in first} == {
        (horizon, quantile) for horizon in (7, 14, 21) for quantile in ("P50", "P80", "P90")
    }


def test_status_evidence_preserves_frozen_nullability_and_reasons() -> None:
    evidence = _evidence()

    coverage = [cell for cell in evidence if cell.metric_name.endswith("upper_coverage")]
    assert len(coverage) == 6
    assert all(cell.metric_status == "NOT_VERIFIED" for cell in coverage)
    assert all(cell.reason_code == "QUANTILE_SEMANTICS_NOT_VERIFIED" for cell in coverage)
    assert all(cell.covered_count_or_null is None for cell in coverage)
    assert all(cell.metric_value is None for cell in coverage)

    peaks = [cell for cell in evidence if cell.metric_name.endswith("peak")]
    assert len(peaks) == 18
    assert all(cell.metric_status == "NOT_COMPUTABLE" for cell in peaks)
    assert all(cell.business_date_or_null is None for cell in peaks)
    assert all(
        cell.reason_code == "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING" for cell in peaks
    )

    intervals = [cell for cell in evidence if cell.metric_name == "prediction_interval"]
    assert len(intervals) == 6
    assert all(cell.lower_bound_available_or_null is False for cell in intervals)
    assert all(cell.lower_bound_value_or_null is None for cell in intervals)


def test_status_evidence_rejects_contradictory_non_null_values() -> None:
    coverage = next(cell for cell in _evidence() if cell.metric_name == "p80_upper_coverage")
    with pytest.raises(ValueError, match="numeric values must be null"):
        _validate_cell(replace(coverage, metric_value=Decimal("1.000000")))
    with pytest.raises(ValueError, match="finite Decimal"):
        _validate_cell(replace(coverage, metric_value=1.0))

    peak = next(cell for cell in _evidence() if cell.metric_name == "single_day_peak")
    with pytest.raises(ValueError, match="numeric values must be null"):
        _validate_cell(replace(peak, metric_value=Decimal("1.000000")))

    interval = next(cell for cell in _evidence() if cell.metric_name == "prediction_interval")
    with pytest.raises(ValueError, match="unavailable interval bounds must be null"):
        _validate_cell(replace(interval, lower_bound_value_or_null=Decimal("1.000000")))


def test_status_evidence_rejects_native_float_in_persisted_rows() -> None:
    rows = list(_rows())
    rows[0] = replace(rows[0], forecast_value_kg=1.0)
    with pytest.raises(ValueError, match="finite Decimal"):
        build_frozen_quality_status_evidence(
            requested_horizons_days=(7, 14, 21),
            rows=rows,
            source_s2_run_identity="a" * 64,
            source_s2_manifest_identity="b" * 64,
            source_s2_binding_row_set_hash="c" * 64,
        )
