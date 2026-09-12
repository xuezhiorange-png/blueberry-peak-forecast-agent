"""Synthetic orchestration fixtures, never real business authority."""

from pathlib import Path

import pytest

from backend.app.area_yield.data import digest
from backend.app.area_yield.experiment import file_hash, read_json, write_json
from backend.app.area_yield.shape_r3 import season_calendar
from scripts import run_frozen_evidence_expansion_r6 as runner


@pytest.fixture
def run_input(tmp_path, monkeypatch):
    root, out = tmp_path / "root", tmp_path / "run"
    root.mkdir()
    total = {
        "model_version": "synthetic",
        "training_season": "2023-2024",
        "global_yield": "10",
        "farm_yields": {},
    }
    total["hash"] = digest(total)
    shape = {
        "kind": "ridge",
        "training_season": "2023-2024",
        "mean": [0] * 4,
        "scale": [1] * 4,
        "coefficients": [0] * 4,
        "intercept": 1,
    }
    shape["hash"] = digest(shape)
    for k, name in runner.COMPONENTS.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        write_json(path, {"model": total} if k in {"total", "prior_total"} else {"ridge": shape})
    sources = [
        {
            "season": s,
            "source_hash": str(i + 1) * 64,
            "complete_export": True,
            "ledger_zero_semantics_authorized": True,
            "mode": "synthetic",
            "authorization_reference": "SYNTHETIC_UNIT_FIXTURE_ONLY",
            "legacy_sealed_test": False,
            "coverage_start": str(season_calendar(s)[0]),
            "coverage_end": str(season_calendar(s)[-1]),
        }
        for i, s in enumerate(("2023-2024", "2024-2025"))
    ]
    config = {
        "sources": sources,
        "train_season": "2023-2024",
        "validation_season": "2024-2025",
        "bindings": [
            {
                "farm": f,
                "value": "10",
                "basis": "BUSINESS_CONFIRMED",
                "source_reference": "synthetic unit fixture only",
                "source_hash": "a" * 64,
                "scope": "FARM",
                "productive_semantics_confirmed": True,
            }
            for f in ("farm_a", "farm_b", "farm_c")
        ],
        "component_hashes": {k: file_hash(root / n) for k, n in runner.COMPONENTS.items()},
        "preserve_directories": ["total-yield-r4-confirmed", "shape-r3a-confirmed"],
    }
    cp = tmp_path / "config.json"
    write_json(cp, config)

    def intake(root, spec):
        rows = [
            {
                "canonical_farm_id": f,
                "date": str(d),
                "daily_harvest_kg": "10" if 30 <= i <= 100 else "0",
            }
            for f in ("farm_a", "farm_b", "farm_c")
            for i, d in enumerate(season_calendar(spec["season"]))
        ]
        return rows, {"source_hash": spec["source_hash"]}

    monkeypatch.setattr(runner, "intake", intake)
    runner.qualify(root, out, cp)
    return root, out, cp


def test_predict_never_opens_validation_and_never_fits(run_input, monkeypatch):
    from backend.app.area_yield import confirmed_shape_r3a, total_yield_r4

    root, out, cp = run_input
    original = runner.read_json

    def guarded(path):
        assert Path(path).name != "validation_labels.json"
        return original(path)

    def forbidden(*args, **kwargs):
        pytest.fail("fit called")

    monkeypatch.setattr(runner, "read_json", guarded)
    monkeypatch.setattr(confirmed_shape_r3a, "fit", forbidden)
    monkeypatch.setattr(total_yield_r4, "fit", forbidden)
    result = runner.predict(root, out, cp)
    assert not result["validation_labels_read"] and not result["fit_called"]


def test_evaluation_requires_frozen_prediction(run_input):
    with pytest.raises(FileNotFoundError):
        runner.evaluate(*run_input)
    assert not (run_input[1] / "evaluation_started.json").exists()


def test_frozen_hash_mismatch_fails_before_predictions(run_input):
    root, out, cp = run_input
    (root / runner.COMPONENTS["total"]).write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        runner.predict(root, out, cp)
    assert not (out / "frozen_prediction_manifest.json").exists()


def test_three_farm_unlock_no_new_fit_and_mass_balance(run_input):
    root, out, cp = run_input
    before = {str(p): file_hash(p) for p in root.rglob("*.json")}
    runner.predict(root, out, cp)
    result = runner.evaluate(root, out, cp)
    assert result["total_farm_count"] == 3
    assert result["total_research_reopen_ready"]
    assert not result["model_research_started"]
    full = read_json(out / "evaluation_manifest.json")
    assert len(full["composites"]) == 12
    assert all(r["mass_balance_pass"] for r in full["composites"])
    assert before == {str(p): file_hash(p) for p in root.rglob("*.json")}


def test_predict_is_exclusive_and_deterministic(run_input):
    root, out, cp = run_input
    runner.predict(root, out, cp)
    before = file_hash(out / "frozen_prediction_manifest.json")
    with pytest.raises(FileExistsError):
        runner.predict(root, out, cp)
    assert before == file_hash(out / "frozen_prediction_manifest.json")


def test_validation_change_does_not_change_prediction_identity(run_input, monkeypatch):
    root, out, cp = run_input
    first = runner.predict(root, out, cp)
    # Test-only disposable replay directory; production artifacts are exclusive.
    import shutil

    other = out.parent / "other"
    shutil.copytree(out, other)
    (other / "frozen_prediction_manifest.json").unlink()
    (other / "prediction_freeze.json").unlink()
    (other / "validation_labels.json").write_text("changed labels must never be opened")
    second = runner.predict(root, other, cp)
    assert first["prediction_hash"] == second["prediction_hash"]
    with pytest.raises(ValueError, match="hash"):
        runner.evaluate(root, other, cp)
