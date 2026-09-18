from __future__ import annotations

import json
from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest

from backend.app.area_yield.base_product import (
    AreaForecastProductRequest,
    forecast_base_area,
    reload_base_forecast_result,
    save_base_forecast_result,
)
from backend.app.area_yield.base_product_authority import (
    BaseAreaForecastPersistenceError,
    BaseAreaForecastUnsupportedError,
    BaseProductAuthority,
    load_base_product_authority,
)
from backend.app.area_yield.data import digest
from backend.app.cli import run_cli


def _experimental_request(**updates: str) -> AreaForecastProductRequest:
    payload: dict[str, str] = {
        "base_name": "保山杨柳基地",
        "target_area_mu": "394.000000",
        "target_season": "2026-2027",
        "forecast_mode": "EXPERIMENTAL",
    }
    payload.update(updates)
    return AreaForecastProductRequest.model_validate(payload)


@pytest.fixture(scope="module")
def authority() -> BaseProductAuthority:
    return load_base_product_authority()


def test_strict_mode_blocks_incomplete_immediate_prior(authority: BaseProductAuthority) -> None:
    request = _experimental_request(forecast_mode="STRICT")
    with pytest.raises(BaseAreaForecastUnsupportedError) as error:
        forecast_base_area(request, authority)
    assert error.value.reason == "PRIOR_SEASON_HISTORY_MISSING"


def test_experimental_mode_allows_incomplete_prior_with_required_warning(
    authority: BaseProductAuthority,
) -> None:
    result = forecast_base_area(_experimental_request(), authority)
    assert result.target_season == "2026-2027"
    assert result.metadata["forecast_mode"] == "EXPERIMENTAL"
    assert result.metadata["forecast_status"] == "EXPERIMENTAL_DATA_COVERAGE_LIMITED"
    assert result.metadata["forecast_warning"] == ("PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE")
    assert result.metadata["prior_history_season"] == "2025-2026"
    assert result.metadata["prior_history_coverage_status"] == "INCOMPLETE"
    assert result.metadata["prior_history_unknown_date_count"] == 40
    assert result.metadata["prior_history_source_start_gap"] is True
    assert result.metadata["prior_history_source_hash"] == (
        "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
    )
    assert result.metadata["prior_history_identity_mapping_hash"] == (
        "6fb7212cc1edd090cf63ff2d938fc5e7b7a0c4b9020b7fdca14e499119b2496e"
    )


def test_experimental_prior_does_not_zero_fill_or_fallback(
    authority: BaseProductAuthority,
) -> None:
    result = forecast_base_area(_experimental_request(), authority)
    assert result.metadata["prior_history_quantity_kg"] == "484802.056000"
    assert result.metadata["history_quantity_semantics"] == "MAPPED_RECORDED_SUBTOTAL"
    assert result.metadata["history_source_season"] == "2025-2026"
    assert result.metadata["history_source_season"] != "2024-2025"


def test_coverage_metadata_is_in_canonical_input_and_changes_result_hash(
    authority: BaseProductAuthority,
) -> None:
    result = forecast_base_area(_experimental_request(), authority)
    snapshot = result.metadata["forecast_input_snapshot"]
    assert snapshot["prior_history"]["coverage_status"] == "INCOMPLETE"
    assert snapshot["prior_history"]["unknown_global_no_record_date_count"] == 40
    mutated = result.model_copy(deep=True)
    mutated.metadata["prior_history_unknown_date_count"] = 39
    assert digest(mutated.model_dump(mode="json", exclude={"result_hash"})) != result.result_hash
    with pytest.raises(BaseAreaForecastPersistenceError) as error:
        reload_base_forecast_result(mutated.model_dump(mode="json"))
    assert error.value.reason == "EXPERIMENTAL_PRIOR_COVERAGE_METADATA_INVALID"


def test_experimental_future_inference_is_deterministic_and_reloads(
    authority: BaseProductAuthority, tmp_path: Path
) -> None:
    request = _experimental_request()
    first = forecast_base_area(request, authority)
    second = forecast_base_area(request, authority)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.forecast_start_date.isoformat() == "2026-07-01"
    assert first.forecast_end_date.isoformat() == "2027-04-15"
    assert all(
        first.forecast_start_date <= row.date <= first.forecast_end_date
        for row in first.daily_curve
    )
    assert abs(
        sum(Decimal(row.predicted_quantity_kg) for row in first.daily_curve)
        - Decimal(first.predicted_season_total_kg)
    ) <= Decimal("0.0005")
    path = tmp_path / "experimental-future.json"
    save_base_forecast_result(path, first)
    assert json.loads(path.read_text(encoding="utf-8"))["result_hash"] == first.result_hash


def test_cli_executes_experimental_future_season() -> None:
    stdout, stderr = StringIO(), StringIO()
    exit_code = run_cli(
        [
            "area-forecast",
            "--base",
            "保山杨柳基地",
            "--area-mu",
            "394.000000",
            "--season",
            "2026-2027",
            "--forecast-mode",
            "EXPERIMENTAL",
        ],
        stdout=stdout,
        stderr=stderr,
    )
    assert exit_code == 0, stderr.getvalue()
    payload = json.loads(stdout.getvalue())
    assert payload["target_season"] == "2026-2027"
    assert payload["metadata"]["forecast_warning"] == ("PRIOR_SEASON_HISTORY_COVERAGE_INCOMPLETE")
    assert payload["metadata"]["prior_history_season"] == "2025-2026"
