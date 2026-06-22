from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

from backend.app.api.planning import _response_payload
from backend.app.planning.config import (
    ConfidenceRules,
    FallbackRule,
    FallbackRules,
    ParameterInferenceConfig,
    ParameterInferenceRules,
    ResolverRules,
    SimilarityRules,
    UncertaintyRules,
)
from backend.app.planning.schemas import ParameterInferenceValue
from backend.app.planning.service import (
    _execution_result,
    _parameter_row,
    _variety_payload,
)


def test_variety_payload_hides_internal_storage_keys_from_public_parameter_payloads() -> None:
    inferred = ParameterInferenceValue(
        parameter_type="yield_kg_per_mu",
        status="available",
        p50_value=Decimal("1000.000000"),
        p80_lower=Decimal("900.000000"),
        p80_upper=Decimal("1100.000000"),
        source_level="same_farm_variety",
        confidence_level="medium",
        confidence_score=Decimal("0.70"),
        sample_count=2,
        season_count=2,
        farm_count=1,
        source_observation_ids=(1, 2),
        fallback_below_minimum=False,
        missing_evidence=(),
    )
    row = _parameter_row(
        variety_id=1,
        parameter_type="yield_kg_per_mu",
        inferred=inferred,
    )
    unavailable = ParameterInferenceValue(
        parameter_type="marketable_rate",
        status="unavailable",
        p50_value=None,
        p80_lower=None,
        p80_upper=None,
        source_level=None,
        confidence_level=None,
        confidence_score=None,
        sample_count=0,
        season_count=0,
        farm_count=0,
        source_observation_ids=(),
        fallback_below_minimum=False,
        missing_evidence=("no_historical_observations",),
    )
    rate_row = _parameter_row(
        variety_id=1,
        parameter_type="marketable_rate",
        inferred=unavailable,
    )

    payload = _variety_payload(
        variety={
            "variety_id": 1,
            "variety_code": "DX",
            "variety_name": "Dx",
            "planted_area_mu": Decimal("700"),
        },
        inferred_rows={
            "yield_kg_per_mu": row,
            "marketable_rate": rate_row,
            "first_harvest_offset_days": rate_row,
            "maturity_peak_offset_days": rate_row,
            "maturity_width_days": rate_row,
            "maturity_skewness": rate_row,
            "harvest_realization_rate": rate_row,
        },
    )

    assert "variety_id" not in payload["yield_kg_per_mu"]
    assert "parameter_type" not in payload["yield_kg_per_mu"]


def test_completed_and_rehydrated_variety_payloads_match_exactly() -> None:
    base = ParameterInferenceValue(
        parameter_type="yield_kg_per_mu",
        status="available",
        p50_value=Decimal("1000.000000"),
        p80_lower=Decimal("900.000000"),
        p80_upper=Decimal("1100.000000"),
        source_level="same_farm_variety",
        confidence_level="medium",
        confidence_score=Decimal("0.70"),
        sample_count=2,
        season_count=2,
        farm_count=1,
        source_observation_ids=(1, 2),
        fallback_below_minimum=False,
        missing_evidence=(),
    )
    rate = replace(
        base,
        parameter_type="marketable_rate",
        p50_value=Decimal("0.8000000000"),
        p80_lower=Decimal("0.7000000000"),
        p80_upper=Decimal("0.9000000000"),
    )
    inferred_rows = {
        "yield_kg_per_mu": _parameter_row(
            variety_id=1,
            parameter_type="yield_kg_per_mu",
            inferred=base,
        ),
        "marketable_rate": _parameter_row(
            variety_id=1,
            parameter_type="marketable_rate",
            inferred=rate,
        ),
        "first_harvest_offset_days": _parameter_row(
            variety_id=1,
            parameter_type="first_harvest_offset_days",
            inferred=replace(base, parameter_type="first_harvest_offset_days"),
        ),
        "maturity_peak_offset_days": _parameter_row(
            variety_id=1,
            parameter_type="maturity_peak_offset_days",
            inferred=replace(base, parameter_type="maturity_peak_offset_days"),
        ),
        "maturity_width_days": _parameter_row(
            variety_id=1,
            parameter_type="maturity_width_days",
            inferred=replace(base, parameter_type="maturity_width_days"),
        ),
        "maturity_skewness": _parameter_row(
            variety_id=1,
            parameter_type="maturity_skewness",
            inferred=replace(base, parameter_type="maturity_skewness"),
        ),
        "harvest_realization_rate": _parameter_row(
            variety_id=1,
            parameter_type="harvest_realization_rate",
            inferred=replace(rate, parameter_type="harvest_realization_rate"),
        ),
    }
    first = _variety_payload(
        variety={
            "variety_id": 1,
            "variety_code": "DX",
            "variety_name": "Dx",
            "planted_area_mu": Decimal("700"),
        },
        inferred_rows=inferred_rows,
    )

    rehydrated_rows = {
        parameter_type: {
            "status": row["status"],
            "p50_value": row["p50_value"],
            "p80_lower": row["p80_lower"],
            "p80_upper": row["p80_upper"],
            "unit": row["unit"],
            "source_level": row["source_level"],
            "confidence_level": row["confidence_level"],
            "confidence_score": row["confidence_score"],
            "sample_count": row["sample_count"],
            "season_count": row["season_count"],
            "farm_count": row["farm_count"],
            "source_observation_ids": list(row["source_observation_ids"]),
            "source_metadata": row["source_metadata"],
            "uncertainty_metadata": row["uncertainty_metadata"],
        }
        for parameter_type, row in inferred_rows.items()
    }
    second = _variety_payload(
        variety={
            "variety_id": 1,
            "variety_code": "DX",
            "variety_name": "Dx",
            "planted_area_mu": Decimal("700"),
        },
        inferred_rows=rehydrated_rows,
    )

    assert first == second


def test_api_response_payload_accepts_execution_result_dataclass() -> None:
    config = ParameterInferenceConfig(
        rules=ParameterInferenceRules(
            resolver_version="task5-v1",
            resolver=ResolverRules(
                address_fuzzy_match_min_score=Decimal("0.75"),
                nearest_reference_distance_km=Decimal("20"),
                climate_zone_radius_km=Decimal("80"),
            ),
            similarity=SimilarityRules(
                max_distance_km=Decimal("300"),
                max_altitude_difference_m=Decimal("800"),
                township_bonus=Decimal("0.30"),
                county_bonus=Decimal("0.20"),
                climate_zone_bonus=Decimal("0.25"),
                same_farm_bonus=Decimal("1.00"),
                distance_weight=Decimal("0.25"),
                altitude_weight=Decimal("0.20"),
                recency_weight=Decimal("0.10"),
                ambiguity_margin=Decimal("0.05"),
            ),
            fallback=FallbackRules(
                same_farm_variety=FallbackRule(2, 2, Decimal("0.20")),
                same_township_altitude_variety=FallbackRule(3, 2, Decimal("0.25")),
                same_county_climate_zone_variety=FallbackRule(
                    4, 2, Decimal("0.30")
                ),
                same_province_variety=FallbackRule(1, 1, Decimal("0.35")),
                literature_variety_prior=FallbackRule(1, 0, None),
            ),
            uncertainty=UncertaintyRules(
                widen_low_confidence_factor=Decimal("1.50"),
                widen_below_minimum_factor=Decimal("1.25"),
            ),
            confidence=ConfidenceRules(
                high_min_score=Decimal("0.80"),
                medium_min_score=Decimal("0.50"),
                same_farm_high_min_seasons=2,
                high_max_historical_mape=Decimal("0.20"),
                medium_max_historical_mape=Decimal("0.30"),
                missing_error_penalty=Decimal("0.15"),
                fallback_below_minimum_penalty=Decimal("0.20"),
                unresolved_location_penalty=Decimal("0.20"),
            ),
        ),
        config_hash="cfg",
        snapshot={},
    )
    result = _execution_result(
        status="completed",
        task_id=1,
        run_id=2,
        input_hash="hash",
        as_of_date=date(2026, 1, 1),
        config=config,
        library_version="lib-v1",
        source_signature_value="sig",
        resolved_location_value={"status": "resolved"},
        similar_historical_samples=[],
        variety_parameters=[],
        warnings=(),
        missing_data=(),
        reproducibility_snapshot={"library_version": "lib-v1"},
    )

    response = _response_payload(result)

    assert response.status == "completed"
    assert response.task_id == 1
    assert response.run_id == 2
    assert response.library_version == "lib-v1"
