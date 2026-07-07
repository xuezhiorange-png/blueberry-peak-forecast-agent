from __future__ import annotations


def test_allowlisted_features_include_structural_and_actual_lags() -> None:
    from backend.app.residual_model.feature_registry import build_feature_registry

    names = {item.feature_name for item in build_feature_registry()}
    assert "structural_arrival_p50_kg" in names
    assert "actual_receipt_lag_1d_kg" in names
    assert "weather_7d_rainfall" in names


def test_blocklisted_features_include_target_and_future_actuals() -> None:
    from backend.app.residual_model.feature_registry import blocklisted_features

    blocklist = blocklisted_features()
    assert "target_date_actual_receipt_kg" in blocklist
    assert "future_actual_receipt_kg" in blocklist
