import json
import subprocess
import sys
from decimal import Decimal

import pytest

from backend.app.area_yield.total_yield_r4 import Area, fit, predict_total, sample


def authority():
    return Area("A", "100", "BUSINESS_REPORTED", "synthetic-unit-fixture", "a" * 64, "FARM", True)


def test_same_farm_area_no_season_specific_area_required():
    area = authority()
    a = sample(area, "A", "2023-2024", "1000", "STRICT_ELIGIBLE")
    b = sample(area, "A", "2024-2025", "2000", "STRICT_ELIGIBLE")
    assert a["area_mu"] == b["area_mu"] == "100"
    assert a["yield_kg_per_mu"] == "10.000000"


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_area_positive_finite(value):
    with pytest.raises(ValueError):
        sample(
            Area("A", value, "MEASURED", "fixture", "b" * 64, "FARM", True),
            "A",
            "2023-2024",
            "10",
            "STRICT_ELIGIBLE",
        )


@pytest.mark.parametrize(
    "basis", ["INFERRED_FROM_YIELD", "TEMPLATE_DEFAULT", "PREVIOUS_SEASON_PROXY", "GUESSED"]
)
def test_unapproved_area_basis_rejected(basis):
    with pytest.raises(ValueError):
        sample(
            Area("A", "100", basis, "fixture", "b" * 64, "FARM", True),
            "A",
            "2023-2024",
            "10",
            "STRICT_ELIGIBLE",
        )


def test_wrong_scope_and_partial_rejected():
    with pytest.raises(ValueError):
        sample(authority(), "B", "2023-2024", "100", "STRICT_ELIGIBLE")
    for status in ("PARTIAL", "RIGHT_CENSORED", "UNKNOWN"):
        with pytest.raises(ValueError):
            sample(authority(), "A", "2023-2024", "100", status)


def test_train_only_serialization_scaling_and_unknown_farm():
    row = sample(authority(), "A", "2023-2024", "1000", "STRICT_ELIGIBLE")
    model = fit([row])
    assert model == fit([row])
    values = [
        Decimal(predict_total(model, str(a), "A", "prior")["predicted_season_total_kg"])
        for a in (100, 500, 1000)
    ]
    assert values[1] == 5 * values[0]
    assert values[2] == 2 * values[1]
    with pytest.raises(ValueError):
        predict_total(model, "100", "unknown", "prior")
    with pytest.raises(ValueError):
        fit([{**row, "season": "2024-2025"}])
    model["global_yield"] = "999"
    with pytest.raises(ValueError):
        predict_total(model, "100", "A", "global")


def test_fresh_process_load_no_fit(tmp_path):
    model = fit([sample(authority(), "A", "2023-2024", "1000", "COMPLETE")])
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model))
    command = (
        "import json,sys; from backend.app.area_yield.total_yield_r4 import predict_total; "
        "print(json.dumps(predict_total(json.load(open(sys.argv[1])), '100', 'A', 'prior')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", command, str(path)], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout)["predicted_season_total_kg"] == "1000.000000"
