"""Frozen prediction-only phase and immutable artifacts for the boundary correction."""

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import read_json, write_json
from scripts import run_business_boundary_r7b as runner
from scripts.run_frozen_evidence_expansion_r6 import seal


def prepared(out: Path):
    out.mkdir()
    raw = [
        {
            "farm": "f",
            "shapes": {"ridge": [1 / 365] * 365, "prior": [1 / 365] * 365},
            "totals": {
                k: {"predicted_season_total_kg": str(n)}
                for k, n in (("global", 100), ("prior", 200))
            },
        }
    ]
    write_json(out / "raw_predictions.json", {"predictions": raw, "prediction_hash": digest(raw)})
    write_json(out / "implementation_hashes.json", runner.implementation())
    seal(out, "qualification_freeze.json")


def test_fresh_process_window_application_no_labels_no_fit(tmp_path):
    out = tmp_path / "run"
    prepared(out)
    old = (out / "raw_predictions.json").read_bytes()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_business_boundary_r7b",
            "predict",
            "--root",
            str(tmp_path),
            "--output",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    assert (out / "raw_predictions.json").read_bytes() == old
    p = read_json(out / "predictions_before_scoring.json")
    assert digest(p["predictions"]) == p["prediction_hash"]
    c = p["predictions"][0]["composites"]
    assert set(c) == {"A1", "A2", "B1", "B2"}
    assert c["A1"]["total"] == c["A2"]["total"]
    assert c["B1"]["total"] == c["B2"]["total"]
    assert float(sum(map(float, c["B1"]["daily_kg"]))) == pytest.approx(200, abs=0.001)
    assert not (out / "business_labels.json").exists()
    calls = [
        n.func for n in ast.walk(ast.parse(inspect.getsource(runner))) if isinstance(n, ast.Call)
    ]
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in {"fit", "fit_rolling_r7"} for n in calls
    )


def test_raw_prediction_mutation_rejected(tmp_path):
    out = tmp_path / "run"
    prepared(out)
    (out / "raw_predictions.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        runner.predict(out)


def test_evaluation_cannot_precede_prediction(tmp_path):
    out = tmp_path / "run"
    prepared(out)
    with pytest.raises(FileNotFoundError):
        runner.evaluate(tmp_path, out)
    assert not (out / "evaluation_started.json").exists()


def test_no_forced_winner_or_posthoc_ranking():
    rows = [
        {
            "composite": c,
            "total_rel_error": str(t),
            "daily_wape": str(w),
            "peak_date_error_days": 1,
            "seven_day_shift_days": 1,
        }
        for c, t, w in (("A1", 1, 4), ("A2", 2, 3), ("B1", 3, 2), ("B2", 4, 1))
    ]
    assert runner.best(rows) == "NO_CLEAR_WINNER"


def test_tail_observed_values_not_used_in_predict_source():
    source = inspect.getsource(runner.predict)
    assert "business_labels.json" not in source
    assert "total_metrics" not in source
    assert "apply_window" in source


@pytest.mark.parametrize(
    "winners,expected",
    [
        ({"f": "NO_CLEAR_WINNER", "g": "NO_CLEAR_WINNER"}, "NOT_ESTABLISHED"),
        ({"f": "A1", "g": "NO_CLEAR_WINNER"}, "NOT_ESTABLISHED"),
        ({"f": "A1", "g": "B2"}, True),
        ({"f": "B2", "g": "B2"}, False),
    ],
)
def test_heterogeneity_requires_identified_per_farm_winners(winners, expected):
    assert runner.heterogeneity(winners) == expected
