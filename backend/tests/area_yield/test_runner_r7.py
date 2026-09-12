"""Synthetic software fixtures never become business authority."""

import ast
import inspect
import json
import subprocess
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import pytest

from backend.app.area_yield import confirmed_shape_r3a as shape
from backend.app.area_yield.data import digest
from backend.app.area_yield.evidence_expansion_r6 import build_qualifications
from backend.app.area_yield.experiment import read_json, write_json
from backend.app.area_yield.shape_r3 import season_calendar
from scripts import run_three_season_r7 as runner
from scripts.run_frozen_evidence_expansion_r6 import seal


def setup_phase(out: Path):
    out.mkdir()
    history = [
        {"farm": "f", "date": str(d), "quantity": str(i % 31 + 1)}
        for i, d in enumerate(season_calendar("2024-2025"))
    ]
    q = {
        "prediction_farms": ["f"],
        "training_farms": ["f"],
        "train": {"f": {"productive_area_mu": "10", "total_evaluable": True}},
    }
    write_json(out / "qualification.json", q)
    write_json(out / "origin_2_training_input.json", {"f": history})
    write_json(out / "implementation_hashes.json", runner.code_hashes())
    seal(out, "qualification_freeze.json")


def test_prediction_fresh_process_without_validation_labels(tmp_path):
    out = tmp_path / "artifacts"
    setup_phase(out)
    runner.build(out)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_three_season_r7",
            "predict",
            "--root",
            str(tmp_path),
            "--output",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    p = read_json(out / "origin_2_predictions_before_scoring.json")
    assert p["prediction_hash"] == digest(p["predictions"])
    assert not (out / "validation_labels.json").exists()
    assert set(p["predictions"][0]["composites"]) == {"A1", "A2", "B1", "B2"}
    calls = [
        n.func
        for n in ast.walk(ast.parse(inspect.getsource(runner.predict)))
        if isinstance(n, ast.Call)
    ]
    assert not any(isinstance(n, ast.Attribute) and "fit" in n.attr for n in calls)


def test_frozen_model_hash_rejects_mutation(tmp_path):
    out = tmp_path / "artifacts"
    setup_phase(out)
    runner.build(out)
    p = out / "origin_2_global_shape_model.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        runner.predict(out)


def test_evaluation_requires_prediction_freeze(tmp_path):
    out = tmp_path / "artifacts"
    setup_phase(out)
    with pytest.raises(FileNotFoundError):
        runner.evaluate(tmp_path, out)
    assert not (out / "evaluation_started.json").exists()


def test_global_unknown_not_zero_and_area_only_excludes_total():
    rows = [
        {"canonical_farm_id": "f", "date": str(d), "daily_harvest_kg": "1"}
        for d in season_calendar("2025-2026")[20:70]
        if d != date(2025, 8, 1)
    ]
    qs, curves, _ = build_qualifications(
        rows, "2025-2026", "a" * 64, date(2025, 7, 1), date(2026, 6, 30), True, True, {"f"}, {}
    )
    assert qs[0].season_completeness_status == "GLOBAL_UNKNOWN_BLOCKED"
    assert next(r for r in curves["f"] if r["date"] == "2025-08-01")["quantity"] == ""
    assert "AREA_MISSING" in asdict(qs[0])["exclusion_reasons"]


def test_active_source_farm_absence_zero():
    rows = [
        {"canonical_farm_id": "f", "date": "2025-08-01", "daily_harvest_kg": "1"},
        {"canonical_farm_id": "g", "date": "2025-08-02", "daily_harvest_kg": "1"},
    ]
    _, curves, _ = build_qualifications(
        rows, "2025-2026", "a" * 64, date(2025, 7, 1), date(2026, 6, 30), True, True, {"f", "g"}, {}
    )
    assert next(r for r in curves["f"] if r["date"] == "2025-08-02")["quantity"] == "0"


def test_censor_aware_partial_support():
    days = season_calendar("2025-2026")
    rows = [
        {"farm": "f", "date": str(d), "quantity": "1" if i < 100 else ""}
        for i, d in enumerate(days)
    ]
    shares = [0.0] * len(days)
    shares[150] = 1.0
    m = runner.shape_score(
        rows,
        shares,
        {"coverage_start": str(days[0]), "coverage_end": str(days[99]), "shape_evaluable": False},
    )
    assert m["peak_evaluation_status"] == "RIGHT_CENSORED"
    assert m["peak_date_error_days"] is None
    assert m["known_support_wape"] is None


def test_source_hash_config_and_fixed_rules():
    config = json.loads(Path("configs/three_season_r7.json").read_text())
    assert (
        config["source"]["source_hash"]
        == "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
    )
    assert config["alpha"] == 10 and config["annual_harmonics"] == 2
    assert not config["tuning_allowed"]


def test_original_fit_and_refactored_core_parity():
    rows = [
        {"farm": "f", "date": str(d), "quantity": str(i % 30 + 1)}
        for i, d in enumerate(season_calendar("2023-2024"))
    ]
    assert shape.fit({"f": rows}, "2023-2024", "ridge") == shape._fit(
        {"f": rows}, "2023-2024", "ridge"
    )
