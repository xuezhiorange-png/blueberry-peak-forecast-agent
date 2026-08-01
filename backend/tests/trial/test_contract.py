from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.app.trial import (
    TrialActualHarvestImportCreateRequest,
    TrialForecastCreateRequest,
    TrialForecastDailyCurveResponse,
    TrialForecastDailyRow,
    TrialForecastInputAuthorityResponse,
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
    with pytest.raises(ValidationError):
        TrialQualityReportCreateRequest(
            forecast_run_id="run",
            actual_label_snapshot_identity="snapshot",
            forecast_cutoff_at=datetime(2026, 7, 29, tzinfo=UTC),
            label_observation_cutoff_at=datetime(2026, 7, 29),
            forecast_horizon_days=7,
            quality_policy_version="quality-v1",
            baseline_policy_version="baseline-v1",
            request_idempotency_key="key",
        )


def test_csv_formula_injection_is_escaped_and_decimal_format_is_fixed() -> None:
    content = serialize_csv(
        ("label", "quantity"),
        (("=SUM(A1:A2)", Decimal("1.2")), ("safe", Decimal("0.0000005"))),
    ).decode("utf-8")
    assert "'=SUM(A1:A2),1.200000" in content
    assert "safe,0.000000" in content
