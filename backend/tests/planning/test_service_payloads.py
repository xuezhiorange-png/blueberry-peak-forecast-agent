from __future__ import annotations

from decimal import Decimal

from backend.app.planning.schemas import ParameterInferenceValue
from backend.app.planning.service import (
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
