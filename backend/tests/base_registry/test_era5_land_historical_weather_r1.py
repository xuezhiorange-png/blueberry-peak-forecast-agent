"""Synthetic weather fixtures test software, never establish real source completeness."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
CONFIG = Path("configs/era5_land_historical_weather_r1.json")


def test_crs_authorization_is_query_assumption_not_authority_upgrade():
    c = json.loads(CONFIG.read_text())
    assert c["location_crs_authorization"] == "GRANTED_WITH_WGS84_QUERY_ASSUMPTION"
    assert c["query_crs_assumption"] == "WGS84"
    assert c["crs_verification_status"] == "NOT_ESTABLISHED"
    assert c["source_coordinate_status"] == "RANGE_VALID_CRS_UNCONFIRMED"
    for key in (
        "base_coordinate_authority_changed",
        "base_crs_authority_changed",
        "crs_authority_upgrade_authorized",
        "climate_zone_authority_used",
        "weather_model_training",
        "weather_incremental_value_scoring",
        "weather_source_authority_frozen",
        "live_weather_forecast_authority_frozen",
    ):
        assert c[key] is False
    assert c["strict_operational_forecast_replay_blocked"] is True
    assert c["expected_base_count"] == 38
    assert len(c["variables"]) == 6
