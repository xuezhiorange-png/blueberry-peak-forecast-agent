import dataclasses

from backend.app.forecast_quality import enums, exceptions, schemas


def test_public_enum_sets_and_exception_hierarchy() -> None:
    assert {item.name for item in enums.ReasonCode} == {
        "NONE",
        "NO_MAPE_ELIGIBLE_ROWS",
        "MAPE_DENOMINATOR_ZERO",
        "WAPE_DENOMINATOR_ZERO",
        "RELATIVE_BIAS_DENOMINATOR_ZERO",
        "NO_COMPLETE_7DAY_WINDOW",
        "QUANTILE_SEMANTICS_NOT_VERIFIED",
        "BELOW_MINIMUM",
        "BASELINE_QUANTILE_DISTRIBUTION_NOT_DEFINED",
        "COMPLETE_DAILY_ROW_SET_NOT_AVAILABLE_FROM_S2_BINDING",
        "SIGNED_DIRECTION_ONLY",
        "PREDICTION_INTERVAL_LOWER_BOUND_UNAVAILABLE",
        "NO_PRIOR_SEASON_ANALOG_DAY",
        "NO_PRIOR_SEASON_ANALOG_ACTUAL",
        "BASELINE_SOURCE_NOT_VISIBLE_AT_CURRENT_FORECAST_CUTOFF",
        "NO_S2_BINDING_ROWS",
    }
    assert issubclass(exceptions.S3StructuralDuplicateError, exceptions.ForecastQualityError)
    assert not hasattr(enums, "InternalReasonCode")


def test_public_schema_field_contract_is_explicit() -> None:
    assert [field.name for field in dataclasses.fields(schemas.ActualPhysicalRecord)] == [
        "physical_key",
        "stable_actual_identity",
        "actual_value_kg",
    ]
    assert len(dataclasses.fields(schemas.DailyMetricResult)) == 21
    assert len(dataclasses.fields(schemas.BreakdownSpec)) == 6
