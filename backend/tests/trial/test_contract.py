from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.forecast_quality.enums import FrozenVersion
from backend.app.forecast_quality.persistence import _validate_evaluation_input
from backend.app.forecast_quality.schemas import S3EvaluationInput
from backend.app.trial import (
    TrialActualHarvestImportCreateRequest,
    TrialForecastBacklogSummaryResponse,
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastDailyRow,
    TrialForecastInputAuthorityResponse,
    TrialForecastInventorySummaryResponse,
    TrialForecastPolicyVersionsResponse,
    TrialForecastSingleDayPeakResponse,
    TrialForecastSummaryResponse,
    TrialForecastSustainedSevenDayPeakResponse,
    TrialQualityReportCreateRequest,
    serialize_csv,
)


def _actual_import_create_payload() -> dict[str, object]:
    return {
        "source_system": "farm-system",
        "source_dataset": "actual-harvest",
        "source_version": "2026-07",
        "external_batch_id": "batch-1",
        "expected_record_count_or_null": 1,
        "request_idempotency_key": "key-1",
    }


def test_actual_import_create_dto_has_only_browser_fields() -> None:
    request = TrialActualHarvestImportCreateRequest.model_validate(
        {**_actual_import_create_payload(), "source_system": " farm-system "}
    )
    assert set(request.model_dump()) == {
        "source_system",
        "source_dataset",
        "source_version",
        "external_batch_id",
        "expected_record_count_or_null",
        "request_idempotency_key",
    }
    assert request.source_system == "farm-system"


@pytest.mark.parametrize(
    "field",
    [
        "import_channel",
        "submitted_at",
        "submitted_by_identity",
        "idempotency_key",
        "schema_version",
        "mapping_policy_version",
        "validation_policy_version",
        "raw_payload_hash",
        "source_semantics_attestation",
        "source_semantics_attestation_hash",
        "attestation_version",
        "permissions",
        "actor_identity",
        "internal_id",
        "database_id",
        "file_name",
        "file_hash",
    ],
)
def test_actual_import_create_dto_rejects_server_owned_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        TrialActualHarvestImportCreateRequest.model_validate(
            {**_actual_import_create_payload(), field: "forbidden"}
        )


def test_actual_import_create_dto_enforces_bounds() -> None:
    with pytest.raises(ValidationError):
        TrialActualHarvestImportCreateRequest.model_validate(
            {**_actual_import_create_payload(), "expected_record_count_or_null": -1}
        )
    with pytest.raises(ValidationError):
        TrialActualHarvestImportCreateRequest.model_validate(
            {**_actual_import_create_payload(), "source_system": " "}
        )
    with pytest.raises(ValidationError):
        TrialActualHarvestImportCreateRequest.model_validate(
            {**_actual_import_create_payload(), "source_version": "v" * 129}
        )


def test_page_dto_extra_fields_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        TrialForecastCreateRequest.model_validate(
            {
                "farm_business_key": "farm",
                "subfarm_business_key_or_null": "farm/subfarm",
                "variety_business_key": "variety",
                "season_business_key": "season",
                "destination_factory_business_key": "factory",
                "forecast_cutoff_at": "2026-07-29T08:00:00Z",
                "forecast_input_authority_hash": "a" * 64,
                "plan_row_hash": "b" * 64,
                "planting_area_mu": "10.000000",
                "flowering_date_or_null": None,
                "maturity_stage_or_null": None,
                "already_picked_quantity_kg_or_null": None,
                "database_id": 1,
            }
        )


def test_forecast_create_dto_exposes_only_public_a2f_fields() -> None:
    request = TrialForecastCreateRequest.model_validate(
        {
            "farm_business_key": " farm ",
            "subfarm_business_key_or_null": "farm/subfarm",
            "variety_business_key": "variety",
            "season_business_key": "season",
            "destination_factory_business_key": "factory",
            "forecast_cutoff_at": "2026-07-29T08:00:00Z",
            "forecast_input_authority_hash": "a" * 64,
            "plan_row_hash": "b" * 64,
            "planting_area_mu": "10.000000",
            "flowering_date_or_null": None,
            "maturity_stage_or_null": None,
            "already_picked_quantity_kg_or_null": None,
        }
    )
    assert set(request.model_dump()) == {
        "farm_business_key",
        "subfarm_business_key_or_null",
        "variety_business_key",
        "season_business_key",
        "destination_factory_business_key",
        "forecast_cutoff_at",
        "forecast_input_authority_hash",
        "plan_row_hash",
        "planting_area_mu",
        "flowering_date_or_null",
        "maturity_stage_or_null",
        "already_picked_quantity_kg_or_null",
    }
    assert request.farm_business_key == "farm"
    assert request.planting_area_mu == Decimal("10.000000")


def test_forecast_authority_dto_contains_no_internal_ids() -> None:
    response = TrialForecastInputAuthorityResponse.model_validate(
        {
            "forecast_input_authority_hash": "a" * 64,
            "authority_available_at": "2026-07-29T08:00:00Z",
            "items": [
                {
                    "farm_business_key": "farm",
                    "subfarm_business_key_or_null": "farm/subfarm",
                    "season_business_key": "season",
                    "variety_business_key": "variety",
                    "destination_factory_business_key": "factory",
                    "plan_version": "1",
                    "plan_row_hash": "b" * 64,
                    "planting_area_mu": "10.000000",
                }
            ],
        }
    )
    dumped = response.model_dump(mode="json")
    assert "farm_id" not in str(dumped)
    assert "factory_id" not in str(dumped)
    assert "season_id" not in str(dumped)


def test_native_float_is_not_accepted_for_canonical_forecast_quantity() -> None:
    with pytest.raises(ValidationError):
        TrialForecastDailyRow(
            target_date=datetime(2026, 1, 1, tzinfo=UTC).date(),
            p50_value_kg=1.25,
            p80_value_kg=Decimal("2"),
            p90_value_kg=Decimal("3"),
            row_status="COMPLETED",
        )


def test_timezone_aware_timestamps_are_required() -> None:
    with pytest.raises(ValidationError):
        TrialForecastDailyCurveResponse(
            run_id="run",
            forecast_cutoff_at=datetime(2026, 7, 29),
            rows=(),
        )


def test_quality_request_freezes_public_fields_and_exact_horizons() -> None:
    payload = {
        "forecast_run_id": "a" * 64,
        "actual_harvest_import_id": "import-1",
        "forecast_cutoff_at": datetime(2026, 7, 29, tzinfo=UTC),
        "label_observation_cutoff_at": datetime(2026, 7, 29, tzinfo=UTC),
        "requested_horizons_days": (7, 14, 21),
        "request_idempotency_key": "quality-key",
    }
    request = TrialQualityReportCreateRequest(**payload)
    assert set(request.model_dump()) == set(payload)
    for forbidden in (
        "actual_label_snapshot_identity",
        "forecast_horizon_days",
        "quality_policy_version",
        "baseline_policy_version",
        "database_id",
    ):
        with pytest.raises(ValidationError):
            TrialQualityReportCreateRequest(**{**payload, forbidden: "forbidden"})
    for horizons in ((7, 14), (7, 14, 21, 28), (7, 7, 14), (7.0, 14, 21)):
        with pytest.raises(ValidationError):
            TrialQualityReportCreateRequest(**{**payload, "requested_horizons_days": horizons})
    with pytest.raises(ValidationError):
        TrialQualityReportCreateRequest(**{**payload, "forecast_run_id": "A" * 64})


def test_quality_request_identity_is_persisted_for_replay_contract() -> None:
    evaluation_input = S3EvaluationInput(
        rows=(),
        s2_run_identity="b" * 64,
        s2_manifest_identity="c" * 64,
        s2_binding_row_set_hash="d" * 64,
        metric_policy_version=FrozenVersion.METRIC_INPUT_MASK_V1,
        baseline_policy_version=FrozenVersion.NAIVE_BASELINE_POLICY_V1,
    )
    identity = {
        "schema_version": "v0.2-s3-quality-persistence-v1",
        "actor_identity": "quality-actor",
        "request_idempotency_key": "key-1",
        "canonical_request": {"forecast_run_id": "a" * 64},
    }
    same = _validate_evaluation_input(
        evaluation_input,
        request_identity_payload=identity,
    )
    replay = _validate_evaluation_input(
        evaluation_input,
        request_identity_payload=identity,
    )
    conflict = _validate_evaluation_input(
        evaluation_input,
        request_identity_payload={
            **identity,
            "canonical_request": {"forecast_run_id": "e" * 64},
        },
    )
    assert same[1] == replay[1]
    assert same[2] == replay[2]
    assert same[1] == conflict[1]
    assert same[2] != conflict[2]
    assert same[0]["trial_request_identity"] == identity
    with pytest.raises(ValidationError):
        TrialQualityReportCreateRequest(
            forecast_run_id="a" * 64,
            actual_harvest_import_id="import-1",
            forecast_cutoff_at=datetime(2026, 7, 29, tzinfo=UTC),
            label_observation_cutoff_at=datetime(2026, 7, 29),
            requested_horizons_days=(7, 14, 21),
            request_idempotency_key="key",
        )


def test_csv_formula_injection_is_escaped_and_decimal_format_is_fixed() -> None:
    content = serialize_csv(
        ("label", "quantity"),
        (("=SUM(A1:A2)", Decimal("1.2")), ("safe", Decimal("0.0000005"))),
    ).decode("utf-8")
    assert "'=SUM(A1:A2),1.200000" in content
    assert "safe,0.000000" in content


def _single_day_peak_payload() -> dict[str, object]:
    return {
        "date": "2026-01-02",
        "quantity_kg": "14.000000",
        "tie_break": "EARLIEST_DATE",
    }


def _sustained_peak_payload() -> dict[str, object]:
    return {
        "start_date": "2026-01-02",
        "end_date": "2026-01-08",
        "cumulative_quantity_kg": "98.000000",
        "daily_average_kg_per_day": "14.000000",
        "window_days": 7,
        "metric": "ROLLING_CUMULATIVE",
        "date_continuity": "STRICT_CALENDAR_DAYS",
        "tie_break": "EARLIEST_START_DATE",
    }


def _inventory_payload() -> dict[str, object]:
    return {
        "opening_quantity_kg": "3.000000",
        "closing_quantity_kg": "2.000000",
    }


def _backlog_payload() -> dict[str, object]:
    return {"quantity_kg": "0.000000"}


def _summary_payload() -> dict[str, object]:
    daily_row = {
        "target_date": "2026-01-02",
        "p50_value_kg": "10.000000",
        "p80_value_kg": "11.000000",
        "p90_value_kg": "12.000000",
        "row_status": "COMPLETED",
    }
    return {
        "run_id": "forecast-public-1",
        "status": "COMPLETED",
        "daily_p50_series": [daily_row],
        "daily_p80_series": [daily_row],
        "daily_p90_series": [daily_row],
        "single_day_peak": _single_day_peak_payload(),
        "sustained_seven_day_peak": _sustained_peak_payload(),
        "season_cumulative_quantity": "22.000000",
        "mature_inventory_summary": _inventory_payload(),
        "backlog_summary": _backlog_payload(),
        "model_version": "model-v1",
        "parameter_version": "parameter-v1",
        "policy_versions": {"forecast": "policy-v1"},
        "canonical_public_hash": "a" * 64,
    }


def test_forecast_public_nested_fields_are_typed_openapi_refs() -> None:
    schema = TrialForecastSummaryResponse.model_json_schema()
    properties = schema["properties"]
    definitions = schema["$defs"]
    targets = {
        "single_day_peak": "TrialForecastSingleDayPeakResponse",
        "sustained_seven_day_peak": "TrialForecastSustainedSevenDayPeakResponse",
        "mature_inventory_summary": "TrialForecastInventorySummaryResponse",
        "backlog_summary": "TrialForecastBacklogSummaryResponse",
        "policy_versions": "TrialForecastPolicyVersionsResponse",
    }
    assert set(targets).issubset(set(schema["required"]))
    for field_name, definition_name in targets.items():
        assert properties[field_name] == {"$ref": f"#/$defs/{definition_name}"}
        assert definitions[definition_name]["additionalProperties"] is False
    assert schema["additionalProperties"] is False


def test_forecast_public_nested_dtos_are_frozen_and_extra_forbid() -> None:
    dto_types = (
        TrialForecastSingleDayPeakResponse,
        TrialForecastSustainedSevenDayPeakResponse,
        TrialForecastInventorySummaryResponse,
        TrialForecastBacklogSummaryResponse,
        TrialForecastPolicyVersionsResponse,
    )
    for dto_type in dto_types:
        assert dto_type.model_config["extra"] == "forbid"
        assert dto_type.model_config["frozen"] is True
        assert dto_type.model_json_schema()["additionalProperties"] is False

    with pytest.raises(ValidationError):
        TrialForecastSummaryResponse.model_validate({**_summary_payload(), "single_day_peak": None})
    with pytest.raises(ValidationError):
        TrialForecastSummaryResponse.model_validate(
            {**_summary_payload(), "sustained_seven_day_peak": None}
        )
    with pytest.raises(ValidationError):
        TrialForecastSummaryResponse.model_validate(
            {**_summary_payload(), "mature_inventory_summary": None}
        )
    with pytest.raises(ValidationError):
        TrialForecastSummaryResponse.model_validate({**_summary_payload(), "backlog_summary": None})
    with pytest.raises(ValidationError):
        TrialForecastSummaryResponse.model_validate({**_summary_payload(), "policy_versions": None})


def test_single_day_peak_contract_rejects_legacy_shape_and_tie_break() -> None:
    with pytest.raises(ValidationError):
        TrialForecastSingleDayPeakResponse.model_validate(
            {**_single_day_peak_payload(), "target_date": "2026-01-02"}
        )
    with pytest.raises(ValidationError):
        TrialForecastSingleDayPeakResponse.model_validate(
            {**_single_day_peak_payload(), "tie_break": "LATEST_DATE"}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("window_days", 6),
        ("metric", "SUM"),
        ("date_continuity", "ALLOW_GAPS"),
        ("tie_break", "LATEST_START_DATE"),
        ("end_date", "2026-01-09"),
    ),
)
def test_sustained_peak_contract_rejects_invalid_window_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        TrialForecastSustainedSevenDayPeakResponse.model_validate(
            {**_sustained_peak_payload(), field: value}
        )


def test_inventory_and_policy_contracts_reject_legacy_or_open_shapes() -> None:
    with pytest.raises(ValidationError):
        TrialForecastInventorySummaryResponse.model_validate({"quantity_kg": "3.000000"})
    with pytest.raises(ValidationError):
        TrialForecastPolicyVersionsResponse.model_validate({})
    with pytest.raises(ValidationError):
        TrialForecastPolicyVersionsResponse.model_validate(
            {"forecast": "policy-v1", "quality": "quality-v1"}
        )
    with pytest.raises(ValidationError):
        TrialForecastPolicyVersionsResponse.model_validate({"forecast": " "})


def test_forecast_nested_quantities_reject_float_negative_and_excess_precision() -> None:
    with pytest.raises(ValidationError):
        TrialForecastSingleDayPeakResponse.model_validate(
            {**_single_day_peak_payload(), "quantity_kg": 14.0}
        )
    with pytest.raises(ValidationError):
        TrialForecastBacklogSummaryResponse.model_validate({"quantity_kg": "-0.000001"})
    with pytest.raises(ValidationError):
        TrialForecastInventorySummaryResponse.model_validate(
            {"opening_quantity_kg": "3.0000001", "closing_quantity_kg": "2.000000"}
        )


def test_forecast_nested_values_have_canonical_json_decimal_and_date_serialization() -> None:
    summary = TrialForecastSummaryResponse.model_validate(_summary_payload())
    dumped = summary.model_dump(mode="json")
    assert dumped["single_day_peak"] == {
        "date": "2026-01-02",
        "quantity_kg": "14.000000",
        "tie_break": "EARLIEST_DATE",
    }
    assert dumped["sustained_seven_day_peak"]["start_date"] == "2026-01-02"
    assert dumped["sustained_seven_day_peak"]["end_date"] == "2026-01-08"
    assert dumped["sustained_seven_day_peak"]["cumulative_quantity_kg"] == "98.000000"
    assert dumped["sustained_seven_day_peak"]["daily_average_kg_per_day"] == "14.000000"
    assert dumped["mature_inventory_summary"] == {
        "opening_quantity_kg": "3.000000",
        "closing_quantity_kg": "2.000000",
    }
    assert dumped["backlog_summary"] == {"quantity_kg": "0.000000"}
    assert dumped["policy_versions"] == {"forecast": "policy-v1"}
