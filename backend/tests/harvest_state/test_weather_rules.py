from __future__ import annotations

from decimal import Decimal

from backend.tests.harvest_state.conftest import make_request


def test_weather_identity_config_returns_one() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.weather import compute_weather_efficiency_ratio

    payload = make_request()
    payload["weather_rule_config"]["required_feature_ids"] = ["daily_precipitation_mm"]
    payload["weather_rule_config"]["feature_rules"] = [
        {
            "feature_id": "daily_precipitation_mm",
            "bands": [
                {
                    "lower_bound": "0",
                    "lower_inclusive": True,
                    "upper_bound": "1000",
                    "upper_inclusive": True,
                    "multiplier": "1",
                }
            ],
        }
    ]
    request = Task9ARequest.model_validate(payload)
    ratio = compute_weather_efficiency_ratio(
        config=request.weather_rule_config,
        feature_values={"daily_precipitation_mm": Decimal("5")},
    )

    assert ratio == Decimal("1")


def test_weather_config_overlap_is_blocker() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest

    payload = make_request()
    payload["weather_rule_config"]["feature_rules"][0]["bands"] = [
        {
            "lower_bound": "0",
            "lower_inclusive": True,
            "upper_bound": "10",
            "upper_inclusive": True,
            "multiplier": "1",
        },
        {
            "lower_bound": "10",
            "lower_inclusive": True,
            "upper_bound": "20",
            "upper_inclusive": True,
            "multiplier": "0.5",
        },
    ]
    request = Task9ARequest.model_validate(payload)

    result = __import__(
        "backend.app.harvest_state.service", fromlist=["run_harvest_state_model"]
    ).run_harvest_state_model(request)

    assert result.status == "blocked"
    assert "UNKNOWN_PARAMETER_CODE" not in result.blockers
    assert any("overlap" in item.lower() or "band" in item.lower() for item in result.blockers)


def test_weather_config_gap_is_blocker() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["weather_rule_config"]["feature_rules"][0]["bands"] = [
        {
            "lower_bound": "0",
            "lower_inclusive": True,
            "upper_bound": "0",
            "upper_inclusive": True,
            "multiplier": "1",
        }
    ]
    request = Task9ARequest.model_validate(payload)
    result = run_harvest_state_model(request)

    assert result.status == "blocked"
    assert any("band" in item.lower() for item in result.blockers)


def test_missing_required_weather_feature_blocks_without_fallback() -> None:
    from backend.app.harvest_state.schemas import Task9ARequest
    from backend.app.harvest_state.service import run_harvest_state_model

    payload = make_request()
    payload["daily_weather_features"] = []
    request = Task9ARequest.model_validate(payload)
    result = run_harvest_state_model(request)

    assert result.status == "blocked"
    assert result.daily_pool_state_rows == []
