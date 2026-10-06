"""Synthetic-only S5 boundary and classification acceptance tests."""

from decimal import Decimal

import pytest

from backend.app.area_yield.v015_base10_benchmark import normalize_predictions, score
from backend.app.area_yield.v015_harvest_incremental import (
    breadth,
    classify,
    deltas,
    target_rows,
)
from backend.app.area_yield.v015_harvest_state import FEATURES
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

pytestmark = pytest.mark.unit


def row():
    return {
        "row_key": "test",
        "base_id": "synthetic",
        "season": "2023-2024",
        "split": "TRAIN",
        "forecast_origin": "2024-01-01T17:00:00+08:00",
        "target_dates": [f"2024-01-{i:02}" for i in range(2, 17)],
        "base10": [{k: "1" for k in BASE_FEATURES} for _ in range(15)],
        "missing_mask": [False] * 15,
    }


@pytest.mark.parametrize("model,n", [("M0", 10), ("M1", 14)])
def test_schema_and_replication(model, n):
    state = {k: str(i + 1) for i, k in enumerate(FEATURES)}
    rows = target_rows([row()], {"test": state}, model)
    assert len(rows) == 15
    assert all(len(r.features) == n for r in rows)
    if model == "M1":
        assert all({k: r.features[k] for k in FEATURES} == state for r in rows)


def test_unknown_model_rejected():
    with pytest.raises(ValueError):
        target_rows([row()], {}, "CATBOOST")


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1"])
def test_state_invalid(value):
    with pytest.raises(ValueError):
        target_rows([row()], {"test": {k: value for k in FEATURES}}, "M1")


def test_current_actual_rejected():
    r = row()
    r["season"] = "2026-2027"
    with pytest.raises(ValueError):
        target_rows([r], {}, "M0")


def test_no_extra_features():
    r = row()
    r["base10"][0]["weather8"] = "1"
    with pytest.raises(ValueError):
        target_rows([r], {}, "M0")


def test_deltas():
    d = deltas({"H7_DAILY_WAPE": "2"}, {"H7_DAILY_WAPE": "1"})
    assert Decimal(d["H7_DAILY_WAPE"]["absolute_delta"]) == -1
    assert Decimal(d["H7_DAILY_WAPE"]["relative_delta"]) == Decimal("-.5")
    assert (
        deltas({"H7_DAILY_WAPE": "0"}, {"H7_DAILY_WAPE": "1"})["H7_DAILY_WAPE"]["relative_delta"]
        == "NOT_COMPUTABLE"
    )


@pytest.mark.parametrize(
    "direction,shares,robust,expected",
    [
        ([-1] * 4, "0.8", [-1, -1], "SUPPORTED"),
        ([-1, 1, -1, -1], "0.8", [-1, -1], "INCONCLUSIVE"),
        ([-1] * 4, "0.5", [-1, -1], "INCONCLUSIVE"),
        ([-1] * 4, "0.8", [-1, 1], "INCONCLUSIVE"),
        ([1] * 4, "0.8", [1, 1], "NOT_SUPPORTED"),
        ([1] * 4, "0.8", [-1, -1], "INCONCLUSIVE"),
    ],
)
def test_classification(direction, shares, robust, expected):
    assert classify(list(map(str, direction)), [shares] * 4, list(map(str, robust))) == expected


def test_missing_required_evidence_inconclusive():
    assert classify([None] * 4, ["1"] * 4, ["-1"] * 2) == "INCONCLUSIVE"


def test_breadth_zero_denominator():
    b = {"a": {"error7": "0", "error15": "0", "actual7": "0", "actual15": "0"}}
    assert breadth(b, b)["H7"]["improved_actual_kg_share"] is None


def test_scoring_inherited_zero_shape_and_ties():
    m, _ = score([row()], [["0"] * 15], [["0"] * 15])
    assert m["CURVE_SHAPE_ERROR"] is None
    assert m["curve_shape_undefined_origin_count"] == 1
    assert m["SINGLE_DAY_PEAK_DATE_MAE_DAYS"] == "0"
    assert m["ROLLING7_PEAK_START_DATE_MAE_DAYS"] == "0"


def test_12dp_clip():
    assert normalize_predictions([-1, 1]) == ["0.000000000000", "1.000000000000"]


def test_exact_frozen_accounting():
    from backend.app.area_yield.v015_harvest_incremental import COUNTS

    assert COUNTS == {"TRAIN": 3705, "VALIDATION": 5412, "EXPOSED_OOT": 8775}
    assert [n * 15 for n in COUNTS.values()] == [55575, 81180, 131625]
    assert (COUNTS["TRAIN"] + COUNTS["VALIDATION"]) * 15 == 136755


def test_authoritative_ridge_pin_and_train_only_scaler():
    import numpy as np

    from backend.app.area_yield.v015_harvest_incremental import fit_predict
    from backend.app.area_yield.v015_research_cohort import digest

    r = row()
    r["base10"] = [{k: str(i + j) for j, k in enumerate(BASE_FEATURES)} for i in range(15)]
    state = {k: "1" for k in FEATURES}
    artifact, p = fit_predict("M1", [r], {"test": state}, [["2"] * 15], [r], {"test": state})
    assert Decimal(artifact.alpha) == 10
    assert artifact.intercept_unpenalized
    assert artifact.solver == "numpy.linalg.solve"
    assert len(artifact.feature_names) == 14
    assert float(artifact.feature_means[0]) == np.mean(range(15))
    assert float(artifact.feature_scales[0]) == np.std(range(15))
    assert list(artifact.feature_scales[10:]) == ["1"] * 4
    _, p2 = fit_predict("M1", [r], {"test": state}, [["2"] * 15], [r], {"test": state})
    assert digest(p) == digest(p2)
    r2 = row()
    r2["base10"] = [{k: "999999" for k in BASE_FEATURES} for _ in range(15)]
    other, _ = fit_predict("M1", [r], {"test": state}, [["2"] * 15], [r2], {"test": state})
    assert artifact.feature_means == other.feature_means
    assert artifact.feature_scales == other.feature_scales


@pytest.mark.parametrize("split,phase", [("VALIDATION", "A"), ("EXPOSED_OOT", "FINAL")])
def test_label_preseal_denied(tmp_path, split, phase):
    from backend.app.area_yield.v015_benchmark_custody import FrozenDataset

    data = FrozenDataset.__new__(FrozenDataset)
    data.root = tmp_path
    data.phase = phase
    data.label_gate = None
    data.label_reads = []
    with pytest.raises(ValueError, match="LABEL_PHASE_OR_SEAL_DENIED"):
        data.labels(split, [])
    assert data.label_reads == []


def test_seal_tamper_rejected(tmp_path):
    from backend.app.area_yield.v015_benchmark_custody import check_files, save, seal_files

    save(tmp_path / "p.json", {"synthetic": True})
    seal = seal_files(tmp_path, phase="A", names=["p.json"], rowset_hash="key", contract_hash="c")
    permit = check_files(tmp_path, seal, expected_names=["p.json"], contract_hash="c", phase="A")
    assert permit.split == "VALIDATION"
    seal["labels_read"] = True
    with pytest.raises(ValueError):
        check_files(tmp_path, seal, expected_names=["p.json"], contract_hash="c", phase="A")


@pytest.mark.parametrize(
    "key", ["base_id", "coefficients", "daily", "password", "prediction_values"]
)
def test_privacy(key):
    from backend.app.area_yield.v015_benchmark_custody import validate_public

    with pytest.raises(ValueError, match="PUBLIC_PRIVACY"):
        validate_public({key: "private"})


@pytest.mark.parametrize("part", ["manifest", "policy", "rowset"])
def test_s4_input_drift(tmp_path, part, monkeypatch):
    import backend.app.area_yield.v015_harvest_incremental as module
    from backend.app.area_yield.v015_benchmark_custody import save
    from backend.app.area_yield.v015_research_cohort import digest

    manifest = {"policy_hash": module.POLICY, "private_members": {}}
    manifest["manifest_hash"] = digest(manifest)
    if part != "manifest":
        monkeypatch.setattr(module, "MANIFEST", manifest["manifest_hash"])
    if part == "policy":
        monkeypatch.setattr(module, "policy", lambda: {"changed": True})
    save(tmp_path / "manifest.json", manifest)
    save(tmp_path / "audit/harvest-state-common-rowset.json", [])
    with pytest.raises(ValueError, match="BLOCKED_INPUT_DRIFT"):
        module.HarvestCustody(tmp_path)


def test_leave_top_entire_base():
    from backend.app.area_yield.v015_harvest_incremental import robustness

    rows = [
        {**row(), "base_id": b, "row_key": str(i)} for i, b in enumerate(["a", "a", "b", "c", "d"])
    ]
    y = [["10"] * 15 for _ in rows]
    p0 = [["30"] * 15, ["30"] * 15, ["20"] * 15, ["15"] * 15, ["15"] * 15]
    p1 = [["10"] * 15 for _ in rows]
    result = robustness(rows, p0, p1, y)
    assert result["LEAVE_TOP1"]["remaining_origin_count"] == 3
    assert result["LEAVE_TOP2"]["remaining_origin_count"] == 2
    assert Decimal(result["LEAVE_TOP2"]["H7_delta"]) < 0


def test_s5_contract_no_search_or_weather():
    from scripts.run_v0_15_s5_harvest_incremental import contract

    c = contract()
    assert list(c["models"]) == ["M0", "M1"]
    assert c["weather_files_opened"] is False
    assert c["catboost_trained"] is False and c["lightgbm_trained"] is False
    assert c["classification"]["minimum_percent_improvement_threshold"] is None
    assert c["s3_metrics_direct_comparison_allowed"] is False


def test_contract_drift_and_invalidated_run_stop(tmp_path):
    from backend.app.area_yield.v015_benchmark_custody import save
    from scripts.run_v0_15_s5_harvest_incremental import contract, verify

    c = contract()
    c["ridge"]["alpha"] = "20"
    save(tmp_path / "contract.json", c)
    with pytest.raises(ValueError, match="CONTRACT_DRIFT"):
        verify(tmp_path)
    other = tmp_path / "other"
    save(other / "contract.json", contract())
    save(other / "invalidated.json", {"invalidated": True})
    with pytest.raises(ValueError, match="OWNER_REAUTHORIZATION"):
        verify(other)


def test_s2_manifest_drift_rejected(tmp_path):
    from backend.app.area_yield.v015_benchmark_custody import FrozenDataset, save

    save(tmp_path / "manifest.json", {"manifest_hash": "wrong"})
    with pytest.raises(ValueError, match="DATASET_DRIFT"):
        FrozenDataset(tmp_path, "A")


def test_decimal_metrics_exact():
    m, _ = score([row()], [["2"] * 15], [["1"] * 15])
    assert Decimal(m["H7_DAILY_WAPE"]) == 1
    assert Decimal(m["H15_CUMULATIVE_WAPE"]) == 1
    assert Decimal(m["H7_CUMULATIVE_WAPE"]) == 1
    assert len(m["lead_day_metrics"]) == 15
    assert all(Decimal(v["MAE_KG"]) == 1 for v in m["lead_day_metrics"])


def test_no_tree_import_in_s5_operator():
    import ast
    from pathlib import Path

    from scripts.run_v0_15_s5_harvest_incremental import REPOSITORY

    files = [
        REPOSITORY / "backend/app/area_yield/v015_harvest_incremental.py",
        REPOSITORY / "scripts/run_v0_15_s5_harvest_incremental.py",
    ]
    for path in files:
        tree = ast.parse(Path(path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in ("catboost", "lightgbm", "sklearn")
            if isinstance(node, ast.Import):
                assert not {n.name for n in node.names} & {"catboost", "lightgbm", "sklearn"}


def test_fresh_process_synthetic_replay(tmp_path):
    import os
    import subprocess
    import sys

    code = """
from backend.tests.area_yield.test_v0_15_s5_incremental import row
from backend.app.area_yield.v015_harvest_incremental import fit_predict
from backend.app.area_yield.v015_harvest_state import FEATURES
from backend.app.area_yield.v015_research_cohort import digest
states={'test':{k:'2' for k in FEATURES}}
for model in ('M0','M1'):
 _,p=fit_predict(model,[row()],states,[['3']*15],[row()],states)
 print(digest(p))
"""
    env = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    a = subprocess.check_output([sys.executable, "-c", code], env=env)
    b = subprocess.check_output([sys.executable, "-c", code], env=env)
    assert a == b
