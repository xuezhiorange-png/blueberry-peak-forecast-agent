"""Synthetic-only area matching, training and fresh-process inference contracts."""

import json
import subprocess
import sys
from datetime import date
from decimal import Decimal

import pytest

from backend.app.area_yield.area_size_r1 import audit, fit, predict
from backend.app.area_yield.v08_s8_training_backtest import season_calendar
from scripts.run_next_area_size_r1 import score


def source():
    rows, daily = [], []
    for index, area in enumerate((100, 200, 400)):
        total = Decimal(area) * Decimal(10 + index)
        rows.append(
            {
                "base_id": f"SYNTHETIC_{index}",
                "season": "2023-2024",
                "area_mu": str(area),
                "season_total_quantity_kg": str(total),
                "strict_training_eligible": "true",
                "daily_curve_available": "true",
                "area_authority_id": "SYNTHETIC",
                "quantity_authority_id": "SYNTHETIC",
                "identity_authority_id": "SYNTHETIC",
            }
        )
        days = season_calendar("2023-2024")
        daily.extend(
            {
                "base_id": f"SYNTHETIC_{index}",
                "season": "2023-2024",
                "date": day.isoformat(),
                "new_quantity_kg": str(total if day.month == 3 and day.day == 1 else 0),
                "new_completeness_status": "COMPLETE_MAPPED_MEMBERS",
            }
            for day in days
        )
    return rows, daily


def model(kind="candidate"):
    rows, daily = source()
    return fit(
        rows, daily, kind=kind, identity={"TEST_ONLY": True}, created_at="2026-10-02T00:00:00Z"
    )


def test_deterministic_training_and_serialization():
    assert model() == model()
    assert predict(model(), "200", 2024, "SYNTHETIC_1") == predict(
        json.loads(json.dumps(model())), "200", 2024, "SYNTHETIC_1"
    )


def test_zero_distinct_from_missing_and_matching():
    rows, daily = source()
    assert audit(rows, daily)["ZERO_QUANTITY_ROW_COUNT"] > 0
    assert audit(rows, daily)["AREA_MATCHED_ROWS"] == len(daily)
    daily[0]["new_quantity_kg"] = ""
    with pytest.raises(ValueError):
        audit(rows, daily)


@pytest.mark.parametrize("mutation", ["area", "season", "identity", "coverage"])
def test_invalid_training_authority(mutation):
    rows, daily = source()
    if mutation == "area":
        rows[0]["area_mu"] = "0"
    elif mutation == "season":
        daily[0]["season"] = "2025-2026"
    elif mutation == "identity":
        daily[0]["base_id"] = "UNMATCHED"
    else:
        daily.pop()
    with pytest.raises(ValueError):
        fit(rows, daily, kind="candidate", identity={}, created_at="TEST_ONLY")


def test_fold_training_rejects_holdout():
    rows, daily = source()
    rows[0]["season"] = "2024-2025"
    with pytest.raises(ValueError, match="training"):
        fit(rows, daily, kind="candidate", identity={}, created_at="TEST_ONLY")


@pytest.mark.parametrize("area", ["0", "-1", "NaN", "Infinity"])
def test_invalid_request_area(area):
    with pytest.raises(ValueError):
        predict(model(), area, 2024, "SYNTHETIC_1")


def test_total_continuity_and_peaks():
    result = predict(model(), "200", 2024, "SYNTHETIC_1")
    daily = result["daily_curve"]
    assert sum(Decimal(r["predicted_daily_quantity_kg"]) for r in daily) == Decimal(
        result["predicted_season_total_kg"]
    )
    assert all(
        (date.fromisoformat(b["date"]) - date.fromisoformat(a["date"])).days == 1
        for a, b in zip(daily, daily[1:], strict=False)
    )
    assert result["peaks"]["single_day_peak_date"] == "2025-03-01"
    assert result["peaks"]["rolling7_start_date"] == "2025-02-23"
    assert result["peaks"]["rolling7_peak_quantity_kg"] == result["predicted_season_total_kg"]


def test_area_scaling_id_no_effect_and_extrapolation():
    m = model("baseline")
    first, second = predict(m, "200", 2024, "SYNTHETIC_1"), predict(m, "400", 2024, "SYNTHETIC_1")
    expected = Decimal(m["parameters"]["pooled_yield"])
    assert Decimal(first["predicted_season_total_kg"]) == (200 * expected).quantize(
        Decimal("0.000001")
    )
    assert Decimal(second["predicted_season_total_kg"]) == (400 * expected).quantize(
        Decimal("0.000001")
    )
    assert predict(m, "500", 2024, "UNKNOWN")["area_position"] == "EXTRAPOLATION"
    assert predict(m, "200", 2024, "UNKNOWN")["daily_curve"] == first["daily_curve"]
    assert first["mode"] == "TEST_ONLY"
    assert first["prospective_accuracy_validated"] is False


def test_artifact_tamper_and_past_request():
    m = model()
    m["parameters"]["beta"] = 999
    with pytest.raises(ValueError, match="hash"):
        predict(m, "200", 2024, "SYNTHETIC_1")
    with pytest.raises(ValueError, match="season"):
        predict(model(), "200", 2023, "SYNTHETIC_1")
    with pytest.raises(ValueError, match="unit"):
        predict(model(), "200", 2024, "SYNTHETIC_1", area_unit="ha")


def test_fresh_process(tmp_path):
    m = model()
    path = tmp_path / "model.json"
    path.write_text(json.dumps(m))
    code = (
        "import json,sys; from backend.app.area_yield.area_size_r1 import predict; "
        "print(json.dumps(predict(json.load(open(sys.argv[1])), '200', 2024, "
        "'SYNTHETIC_1'),sort_keys=True))"
    )
    fresh = subprocess.check_output([sys.executable, "-c", code, str(path)], text=True)
    assert json.loads(fresh) == predict(m, "200", 2024, "SYNTHETIC_1")


def test_predict_does_not_read_labels_or_predictions(monkeypatch):
    from pathlib import Path

    m = model()

    def forbidden(*args, **kwargs):
        raise AssertionError("inference may not read any source")

    monkeypatch.setattr(Path, "open", forbidden)
    assert predict(m, "200", 2024, "SYNTHETIC_1")["result_hash"]


def test_same_cohort_and_future_actual_cannot_change_prediction():
    m = model()
    prediction = predict(m, "200", 2024, "SYNTHETIC_1")
    with pytest.raises(ValueError, match="same cohort"):
        score({"SYNTHETIC_1": prediction}, [], [])
    rows, daily = source()
    rows[0]["season_total_quantity_kg"] = "9999"
    daily[0]["new_quantity_kg"] = "9999"
    assert predict(m, "200", 2024, "SYNTHETIC_1") == prediction


def test_learned_area_response_is_not_hardcoded():
    assert model()["parameters"]["beta"] != 0
    assert (
        predict(model(), "200", 2024, "SYNTHETIC_1")["daily_curve"]
        != predict(model(), "400", 2024, "SYNTHETIC_1")["daily_curve"]
    )
