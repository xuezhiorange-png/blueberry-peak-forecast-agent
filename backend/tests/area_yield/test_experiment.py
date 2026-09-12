import json
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield import experiment
from backend.app.area_yield.data import Receipt


def prepared(tmp_path):
    config = json.loads(Path("configs/area_yield_experiment_r1.json").read_text())
    config.update(
        {
            "scope_id": "synthetic",
            "area_mu": "10.000000",
            "coverage_start": "2024-10-01",
            "coverage_end": "2024-12-31",
            "train_end": "2024-10-31",
            "development_end": "2024-11-30",
            "final_end": "2024-12-31",
        }
    )
    rows = [
        Receipt(
            str(i),
            "synthetic",
            config["season_id"],
            date(2024, 10, 1) + timedelta(days=i),
            Decimal(100 + i),
            "DETAIL",
        )
        for i in range(92)
    ]
    root = tmp_path / "experiment"
    experiment.prepare(root, config, rows, "synthetic-unit-test")
    return root


def test_train_cannot_read_holdout_and_final_predictions_precede_labels(tmp_path, monkeypatch):
    root = prepared(tmp_path)
    original = experiment.partition

    def no_final(root, manifest, name):
        assert name != "final"
        return original(root, manifest, name)

    monkeypatch.setattr(experiment, "partition", no_final)
    freeze = experiment.train(root)
    assert freeze["final_labels_opened_by_training"] is False

    def final_after_prediction(root, manifest, name):
        assert (root / "final_predictions_before_labels.json").exists()
        return original(root, manifest, name)

    monkeypatch.setattr(experiment, "partition", final_after_prediction)
    result = experiment.final_evaluate(root)
    assert result["final_phase_count"] == 1
    with pytest.raises(FileExistsError):
        experiment.final_evaluate(root)


def test_fresh_process_load_without_training_or_raw_loader(tmp_path):
    root = prepared(tmp_path)
    experiment.train(root)
    command = [
        sys.executable,
        "-c",
        """
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from backend.app.area_yield import experiment
def forbidden(*args, **kwargs):
    raise AssertionError('fit forbidden in load-only process')
experiment.fit_model = forbidden
result = experiment.forecast(Path(sys.argv[1]), Decimal('10'), 2026, date(2026,9,30), 'synthetic')
assert not result['refit_performed']
assert 'scripts.probe_banna_harvest_baseline_r4' not in sys.modules
assert result['daily_count'] == 365
""",
        str(root),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    rows = experiment.read_csv(root / "forecast_example.csv")
    result = experiment.read_json(root / "forecast_example_summary.json")
    assert sum(Decimal(r["harvest_quantity_kg"]) for r in rows) == Decimal(result["total_kg"])
    assert all(r["harvest_quantity_kg"] == r["arrival_quantity_kg"] for r in rows)


def test_final_label_mutation_cannot_change_selection_or_training(tmp_path):
    root = prepared(tmp_path)
    (root / "final.csv").write_text("not accessible final labels")
    # Train uses stored final hash as provenance, never opens final label bytes.
    experiment.train(root)
    with pytest.raises(ValueError, match="partition drift"):
        experiment.final_evaluate(root)


def test_repeat_training_is_not_unrecorded_search(tmp_path):
    root = prepared(tmp_path)
    experiment.train(root)
    with pytest.raises(FileExistsError):
        experiment.train(root)


def test_no_legacy_dataset_or_database_dependency():
    import inspect

    import backend.app.area_yield.model as model

    source = inspect.getsource(model) + inspect.getsource(experiment)
    for forbidden in (
        "s4_candidate",
        "load_pit",
        "sqlalchemy",
        "test.content",
        "2025_2026_receipts",
    ):
        # The latter is exclusion-only inventory text, never an opener.
        if forbidden == "2025_2026_receipts":
            assert '"decision": "NOT_OPENED"' in source
        else:
            assert forbidden not in source
