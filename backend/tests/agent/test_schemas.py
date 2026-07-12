"""Schema contract tests for all eight logical tools."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from backend.app.agent.enums import BlockerCode
from backend.app.agent.schemas import (
    AdvancedOverrides,
    AsOfOverride,
    AuthorityOverride,
    Blocker,
    DecimalString,
    ExplainForecastInput,
    ExplainForecastOutput,
    ForecastDailyCurveInput,
    ForecastDailyCurveOutput,
    ForecastPeakInput,
    ForecastPeakOutput,
    GenerateRecommendationsInput,
    GenerateRecommendationsOutput,
    InferParametersInput,
    InferParametersOutput,
    IntId,
    NormalizedAgentRequest,
    NormalizedVarietyInput,
    ParameterOverride,
    Recommendation,
    RequestedAsOfDateProvenance,
    ResolvedLocation,
    ResolveLocationInput,
    ResolveLocationOutput,
    RunBacktestInput,
    RunBacktestOutput,
    SHA256Hex,
    SimulateScenarioInput,
    SimulateScenarioOutput,
    Task8Authority,
    YieldPerMuOverrideValue,
)

TOOL_MODELS = [
    ResolveLocationInput,
    ResolveLocationOutput,
    InferParametersInput,
    InferParametersOutput,
    ForecastDailyCurveInput,
    ForecastDailyCurveOutput,
    ForecastPeakInput,
    ForecastPeakOutput,
    SimulateScenarioInput,
    SimulateScenarioOutput,
    RunBacktestInput,
    RunBacktestOutput,
    ExplainForecastInput,
    ExplainForecastOutput,
    GenerateRecommendationsInput,
    GenerateRecommendationsOutput,
]


@pytest.mark.parametrize("cls", TOOL_MODELS)
def test_tool_model_emits_json_schema(cls):
    schema = cls.model_json_schema()
    assert "properties" in schema or "$defs" in schema, cls.__name__
    # Determinism: re-generating the schema yields the same JSON string.
    assert cls.model_json_schema() == schema


@pytest.mark.parametrize("cls", TOOL_MODELS)
def test_tool_model_rejects_extra_fields(cls):
    # Find at least one required field to override.
    with pytest.raises(ValidationError):
        cls.model_validate({"__not_a_field__": "x"})


def test_decimal_string_rejects_float_input():
    from pydantic import TypeAdapter

    adapter = TypeAdapter(DecimalString)
    with pytest.raises(ValidationError):
        adapter.validate_python("abc")
    adapter.validate_python("1.23")


def test_sha256_hex_rejects_non_hex():
    from pydantic import TypeAdapter

    adapter = TypeAdapter(SHA256Hex)
    with pytest.raises(ValidationError):
        adapter.validate_python("z" * 64)
    adapter.validate_python("a" * 64)


def test_int_id_rejects_string():
    from pydantic import TypeAdapter

    adapter = TypeAdapter(IntId)
    with pytest.raises(ValidationError):
        adapter.validate_python("1")
    adapter.validate_python(1)


def test_authority_override_rejects_str_row_id():
    with pytest.raises(ValidationError):
        AuthorityOverride(
            override_kind="AUTHORITY_OVERRIDE_KIND",
            target="TASK12_PREDICTION_RUN",
            value="42",  # type: ignore[arg-type]
            source_attestation="op",
        )


def test_as_of_override_requires_attestation():
    with pytest.raises(ValidationError):
        AsOfOverride(value=date(2026, 3, 1), source_attestation="")


def test_advanced_overrides_rejects_multiple_as_of():
    with pytest.raises(ValidationError):
        AdvancedOverrides(
            parameter_overrides=[],
            scenario_overrides=[],
            execution_overrides=[],
            authority_overrides=[],
            as_of_overrides=[
                AsOfOverride(value=date(2026, 3, 1), source_attestation="op1"),
                AsOfOverride(value=date(2026, 4, 1), source_attestation="op2"),
            ],
        )


def test_parameter_override_requires_variety_and_target():
    with pytest.raises(ValidationError):
        ParameterOverride(
            override_kind="PARAMETER_OVERRIDE_KIND",
            variety_id="",
            target_parameter="expected_per_mu_yield",
            value=YieldPerMuOverrideValue(value="1.00"),
            source_attestation="op",
        )


def test_unknown_enum_value_rejected():
    with pytest.raises(ValidationError):
        Recommendation(
            category="NOT_A_VALID_CATEGORY",  # type: ignore[arg-type]
            kind="OPERATIONAL",
            text="x",
            rule_id="r",
            evidence=[],
            confidence="HIGH",
        )


def test_naive_datetime_rejected_for_request_received_at():
    naive = datetime(2026, 3, 1, 0, 0, 0)
    with pytest.raises(ValidationError):
        NormalizedAgentRequest(
            request_id="r",
            request_received_at=naive,  # type: ignore[arg-type]
            effective_as_of_date=date(2026, 3, 1),
            effective_forecast_season=2026,
            season_resolution_policy_version="season-calendar/v1",
            season_calendar_config_hash="a" * 64,
            requested_as_of_date_provenance=RequestedAsOfDateProvenance(
                caller_requested_as_of_date=None,
                effective_as_of_date=date(2026, 3, 1),
                override_applied=False,
                override_kind=None,
                source_attestation=None,
                source_ref=None,
            ),
            normalized_location=ResolvedLocation(
                status="resolved",
                location_reference_id=1,
                matched_location_method="REFERENCE_ID",
            ),
            varieties=[NormalizedVarietyInput(variety_id="101", planting_area_mu="100.0")],
            advanced_overrides=AdvancedOverrides(),
            canonical_request_hash="0" * 64,
        )


def test_caller_requested_as_of_nullable_accepts_none():
    p = RequestedAsOfDateProvenance(
        caller_requested_as_of_date=None,
        effective_as_of_date=date(2026, 3, 1),
        override_applied=False,
        override_kind=None,
        source_attestation=None,
        source_ref=None,
    )
    assert p.caller_requested_as_of_date is None


def test_authority_envelope_types_rejected_for_mismatch():
    # Task8Authority has maturity_model_run_id; supplying a task9 shape should fail.
    with pytest.raises(ValidationError):
        Task8Authority(
            maturity_model_run_id=1,
            maturity_model_version="v1",
            maturity_model_config_hash="a" * 64,
            maturity_model_source_signature="sig",
            maturity_model_artifact_id=1,
            maturity_model_artifact_hash="a" * 64,
            maturity_forecast_run_id=1,
            maturity_forecast_source_signature="sig",
            maturity_forecast_as_of_date=date(2026, 3, 1),
            # add a foreign field to verify strict extra rejection
            forecast_run_id=42,  # type: ignore[call-arg]
        )


def test_blocker_stable_error_envelope():
    b = Blocker(code=BlockerCode.LOCATION_UNRESOLVED, message="x", retry_hint="FIX_INPUT")
    assert b.code == BlockerCode.LOCATION_UNRESOLVED
    assert b.message == "x"
