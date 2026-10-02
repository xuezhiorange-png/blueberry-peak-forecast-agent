"""Engineering invariants, not acceptance of forecast accuracy."""

import json
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import m0_baseline
from backend.app.area_yield.base_product import AreaForecastProductRequest
from backend.app.area_yield.evaluation import summaries


def test_fresh_process_inference_uses_artifact_and_request_only(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    m0_baseline.save_model(model, fitted())
    payload = tmp_path / "request.json"
    payload.write_text(request().model_dump_json())
    root = Path(__file__).resolve().parents[3]
    results = []
    for index in range(2):
        output = tmp_path / f"response-{index}.json"
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.app.cli",
                "m0-baseline",
                "predict",
                "--model",
                str(model),
                "--input",
                str(payload),
                "--output",
                str(output),
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        assert json.loads(result.stdout)["inference_data_read_guard_active"] is True
        results.append(output.read_bytes())
    assert results[0] == results[1]
    assert json.loads(results[0]) == m0_baseline.predict(fitted(), request())


def test_inference_guard_rejects_target_csv_read(tmp_path: Path) -> None:
    model = tmp_path / "model.json"
    m0_baseline.save_model(model, fitted())
    payload = tmp_path / "request.json"
    payload.write_text(request().model_dump_json())
    label = tmp_path / "labels.csv"
    label.write_text("actual_kg\n100\n")
    code = (
        "import sys; from pathlib import Path; from argparse import Namespace; "
        "from backend.app.area_yield import m0_baseline; "
        "from backend.app.area_yield.m0_baseline_cli import dispatch_m0; "
        "m0_baseline.predict=lambda *a: Path(sys.argv[3]).read_text(); "
        "dispatch_m0(Namespace(command='predict',model=sys.argv[1],input=sys.argv[2],"
        "output=sys.argv[4]),sys.stdout)"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(model),
            str(payload),
            str(label),
            str(tmp_path / "forbidden-response.json"),
        ],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "M0_INFERENCE_FORBIDDEN_DATA_READ" in result.stderr
    assert not (tmp_path / "forbidden-response.json").exists()


def samples() -> list[dict[str, Any]]:
    dates = [date(2023, 7, 1) + timedelta(days=i) for i in range(14)]
    values = [float(i + 1) for i in range(14)]
    return [
        {
            "base_id": "base_" + "a" * 24,
            "season": "2023-2024",
            "group_id": "base_" + "a" * 24 + "|2023-2024",
            "area": 10.0,
            "dates": dates,
            "quantities": values,
            "total": sum(values),
        }
    ]


def request(area: str = "10") -> AreaForecastProductRequest:
    return AreaForecastProductRequest(
        base_id="base_" + "a" * 24,
        target_area_mu=area,
        target_season="2024-2025",
        forecast_start_date=date(2024, 7, 1),
        forecast_end_date=date(2025, 4, 15),
        forecast_mode="EXPERIMENTAL",
    )


def fitted() -> dict[str, Any]:
    return m0_baseline.fit(
        samples(), training_input_sha256="a" * 64, training_manifest_sha256="b" * 64
    )


def test_real_fit_and_serialization(tmp_path: Path) -> None:
    model = fitted()
    path = tmp_path / "model.json"
    m0_baseline.save_model(path, model)
    loaded = m0_baseline.load_model(path)
    assert m0_baseline.predict(model, request()) == m0_baseline.predict(loaded, request())
    assert len(model["shared_shape"]) == 290
    assert model["training_base_season_count"] == 1
    before = path.read_bytes()
    m0_baseline.save_model(path, model)
    assert path.read_bytes() == before
    changed = json.loads(before)
    changed["pooled_yield_kg_per_mu"] = 999
    with pytest.raises(ValueError, match="INTEGRITY"):
        m0_baseline.validate_model(changed)


def test_replay_mass_peaks_dates_and_area_scaling() -> None:
    model = fitted()
    first = m0_baseline.predict(model, request())
    assert first == m0_baseline.predict(model, request())
    second = m0_baseline.predict(model, request("20"))
    daily = first["daily_curve"]
    dates = [date.fromisoformat(r["date"]) for r in daily]
    kg = [Decimal(r["predicted_quantity_kg"]) for r in daily]
    assert all(v >= 0 and v.is_finite() for v in kg)
    assert all((b - a).days == 1 for a, b in zip(dates, dates[1:], strict=False))
    assert sum(kg) == Decimal(first["predicted_window_total_kg"])
    canonical = summaries(dates, kg)
    assert first["single_day_peak"] == canonical["single_day_peak"]
    assert first["rolling_7day_peak"] == canonical["rolling_7day_peak"]
    assert Decimal(second["predicted_window_total_kg"]) == 2 * sum(kg)
    assert max(
        abs(Decimal(b["predicted_quantity_kg"]) - 2 * a)
        for a, b in zip(kg, second["daily_curve"], strict=True)
    ) <= Decimal("0.00001")
    assert first["metadata"]["BASE_SPECIFIC_TIMING_MODE"] == "SHARED"
    assert first["metadata"]["PRODUCTION_ACCURACY_APPROVED"] is False


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area(area: str) -> None:
    with pytest.raises(ValueError):
        request(area)


def test_invalid_dates_and_training_overlap() -> None:
    model = fitted()
    for start, end in [
        ("2024-08-02", "2024-08-01"),
        ("2024-06-01", "2024-06-10"),
        ("2025-04-14", "2025-04-20"),
    ]:
        payload = request().model_dump(mode="json")
        payload.update(forecast_start_date=start, forecast_end_date=end)
        with pytest.raises(ValueError):
            m0_baseline.predict(model, AreaForecastProductRequest.model_validate(payload))
    payload = request().model_dump(mode="json")
    payload.update(
        target_season="2023-2024", forecast_start_date="2023-07-01", forecast_end_date="2024-04-15"
    )
    with pytest.raises(ValueError, match="TRAINING"):
        m0_baseline.predict(model, AreaForecastProductRequest.model_validate(payload))


def test_labels_and_weather_not_in_request() -> None:
    payload = request().model_dump(mode="json")
    for field in ("actual_kg", "actual_total", "weather", "cultivar_mix"):
        with pytest.raises(ValueError):
            AreaForecastProductRequest.model_validate({**payload, field: 10})


def test_shared_timing_and_boundary_warning() -> None:
    model = fitted()
    one = m0_baseline.predict(model, request())
    payload = request().model_dump(mode="json")
    payload["base_id"] = "base_" + "b" * 24
    two = m0_baseline.predict(model, AreaForecastProductRequest.model_validate(payload))
    assert one["daily_curve"] == two["daily_curve"]
    assert one["single_day_peak"] == two["single_day_peak"]
    forced = dict(model, shared_shape=[1 / 290] * 289 + [1 / 290], artifact_hash="")
    forced["shared_shape"][-1] += 0.01
    total = sum(forced["shared_shape"])
    forced["shared_shape"] = [v / total for v in forced["shared_shape"]]
    forced = m0_baseline.seal_model(forced)
    # A legal shorter request ends on the largest retained cell.
    short = request().model_dump(mode="json")
    short.update(forecast_start_date="2024-07-01", forecast_end_date="2024-07-07")
    out = m0_baseline.predict(forced, AreaForecastProductRequest.model_validate(short))
    assert "SINGLE_PEAK_AT_OUTPUT_BOUNDARY" in out["warnings"]
