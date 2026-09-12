import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from backend.app.area_yield import single_season_r2 as app
from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, write_csv, write_json
from backend.app.area_yield.single_season_r2 import select_kind, split_windows
from backend.app.area_yield.spline_r2 import fit, position


def test_rolling_windows_train_strictly_before_targets_and_exclude_benchmark():
    config = json.loads(Path("configs/area_yield_experiment_r2.json").read_text())
    windows = split_windows(config)
    assert len(windows) == 9
    for w in windows:
        assert w["cutoff"] < w["start"] <= w["end"] <= date(2025, 3, 15)
        assert (w["end"] - w["start"]).days + 1 in (14, 28, 42)


def test_selection_peak_first_and_quantity_nonregression():
    config = json.loads(Path("configs/area_yield_experiment_r2.json").read_text())

    def metric(shift, peak, wape):
        return {
            "rolling_7day_window_shift_days": shift,
            "single_day_peak_date_error_days": peak,
            "daily_wape": str(wape),
            "daily_mae_kg": "10",
            "window_total_absolute_error_kg": "10",
            "single_day_peak_absolute_error_kg": "10",
        }

    results = [
        {
            "metrics": {
                "ridge": metric(10, 10, 0.5),
                "baseline": metric(15, 15, 0.9),
                "spline": metric(5, 5, 0.6),
            }
        }
    ]
    assert select_kind(results, config)["selected"] == "ridge"
    results[0]["metrics"]["spline"] = metric(5, 5, 0.5)
    assert select_kind(results, config)["selected"] == "spline"


def test_rolling_loader_never_parses_final_labels_and_fits_obey_cutoff(tmp_path, monkeypatch):
    config = json.loads(Path("configs/area_yield_experiment_r2.json").read_text())
    r1 = tmp_path / "r1"
    r1.mkdir()
    rows = [
        {
            "scope_id": config["scope_id"],
            "season_id": "2024-2025",
            "area_mu": "736.000000",
            "area_basis": "AUTHORIZED_CALIBRATION",
            "date": (date(2024, 10, 15) + timedelta(days=i)).isoformat(),
            "actual_kg": str(i + 10),
            "observation_status": "OBSERVED",
        }
        for i in range(152)
    ]
    for name, subset in (("train", rows[:109]), ("development", rows[109:])):
        write_csv(r1 / f"{name}.csv", subset)
        config[f"r1_{name}_sha256"] = file_hash(r1 / f"{name}.csv")
    original_load, original_fit = app.source_rows, app.fit_kind

    def checked_load(path, name, cfg):
        assert name != "final"
        return original_load(path, name, cfg)

    def checked_fit(subset, kind, cutoff, scope):
        assert all(date.fromisoformat(r["date"]) <= cutoff for r in subset)
        return original_fit(subset, kind, cutoff, scope)

    monkeypatch.setattr(app, "source_rows", checked_load)
    monkeypatch.setattr(app, "fit_kind", checked_fit)
    result = app.rolling(tmp_path / "r2", r1, config, "synthetic")
    assert result["rolling_window_count"] == 9
    assert result["benchmark_used_for_selection"] is False


def test_fresh_process_spline_load_and_area_scaling(tmp_path):
    config = json.loads(Path("configs/area_yield_experiment_r2.json").read_text())
    rows = [
        {
            "scope_id": config["scope_id"],
            "date": (date(2024, 10, 15) + timedelta(days=i)).isoformat(),
            "actual_kg": str(i + 10),
            "area_mu": "736.000000",
        }
        for i in range(207)
    ]
    model = fit(rows, date(2025, 5, 9), config["scope_id"])
    wrapper = {
        "predictor": model,
        "support_min": position(date(2024, 10, 15)),
        "support_max": position(date(2025, 5, 9)),
    }
    wrapper["model_version"] = digest(wrapper)
    write_json(tmp_path / "selected_model_r2.json", wrapper)
    write_json(tmp_path / "model_config_r2.json", config)
    write_json(tmp_path / "selection_freeze_r2.json", {"config_hash": digest(config)})
    write_json(
        tmp_path / "training_manifest_r2.json",
        {"selected_model_sha256": file_hash(tmp_path / "selected_model_r2.json")},
    )
    code = """
from pathlib import Path
import sys
from backend.app.area_yield import single_season_r2 as a
def forbidden(*args, **kwargs):
    raise AssertionError('fresh-process fit forbidden')
a.fit_kind = forbidden
a.spline_r2.fit = forbidden
a.r1_model.fit_model = forbidden
r = a.forecast(Path(sys.argv[1]))
assert r['area_scaling_software_test'] == 'PASS'
assert r['daily_rows_per_area'] == 207
assert not r['fit_called']
assert not r['area_scaling_validated']
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True, capture_output=True)
