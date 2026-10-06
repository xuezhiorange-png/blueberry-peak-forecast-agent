"""Synthetic-only S3 contracts; real libraries, never private business data."""

from copy import deepcopy

import numpy as np
import pytest

from backend.app.area_yield.v015_base10_benchmark import (
    CANDIDATES,
    EXPECTED_COUNTS,
    RIDGE_CONFIG,
    SEED,
    access_allowed,
    direction,
    fit_model,
    flatten_features,
    normalize_predictions,
    score,
    select_candidate,
    verify_seal,
)
from backend.app.area_yield.v015_research_cohort import digest
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES

pytestmark = pytest.mark.unit


def feature_rows(n=3):
    return [
        {
            "row_key": str(i),
            "base_id": "synthetic-base",
            "season": "2023-2024",
            "split": "TRAIN",
            "forecast_origin": "2024-01-01T17:00:00+08:00",
            "target_dates": [f"2024-01-{d:02}" for d in range(2, 17)],
            "base10": [
                dict(zip(BASE_FEATURES, map(str, range(d, d + 10)), strict=True)) for d in range(15)
            ],
            "missing_mask": [False] * 10,
        }
        for i in range(n)
    ]


def test_exact_origin_target_accounting():
    assert EXPECTED_COUNTS == {"TRAIN": 4125, "VALIDATION": 6028, "EXPOSED_OOT": 9867}
    assert {k: v * 15 for k, v in EXPECTED_COUNTS.items()} == {
        "TRAIN": 61875,
        "VALIDATION": 90420,
        "EXPOSED_OOT": 148005,
    }
    assert (EXPECTED_COUNTS["TRAIN"] + EXPECTED_COUNTS["VALIDATION"]) * 15 == 152295
    matrix, keys = flatten_features(feature_rows())
    assert matrix.shape == (45, 10) and len(set(keys)) == 45


@pytest.mark.parametrize("extra", ["weather8", "base_id", "past_harvest", "future_h15"])
def test_extra_feature_rejected(extra):
    rows = feature_rows()
    rows[0]["base10"][0][extra] = "1"
    with pytest.raises(ValueError, match="BASE10_SCHEMA"):
        flatten_features(rows)


@pytest.mark.parametrize("bad", ["NaN", "Infinity"])
def test_nonfinite_feature_rejected(bad):
    rows = feature_rows()
    rows[0]["base10"][0][BASE_FEATURES[0]] = bad
    with pytest.raises(ValueError, match="NONFINITE"):
        flatten_features(rows)


def test_current_season_rejected():
    rows = feature_rows()
    rows[0]["season"] = "2026-2027"
    with pytest.raises(ValueError, match="UNAUTHORIZED_SEASON"):
        flatten_features(rows)


@pytest.mark.parametrize(
    "phase,split",
    [("A", "VALIDATION"), ("A", "EXPOSED_OOT"), ("B", "EXPOSED_OOT"), ("FINAL", "EXPOSED_OOT")],
)
def test_labels_denied_before_seal(phase, split):
    assert not access_allowed(phase, split, labels=True)


def test_access_contract():
    assert access_allowed("A", "TRAIN", labels=True)
    assert access_allowed("A", "VALIDATION", labels=False)
    assert access_allowed("B", "VALIDATION", labels=True)
    assert access_allowed("SCORE", "EXPOSED_OOT", labels=True)


def test_candidate_freeze():
    assert list(CANDIDATES) == ["RIDGE", "CB1", "CB2", "CB3", "LGB1", "LGB2", "LGB3"]
    assert RIDGE_CONFIG["alpha"] == "10.000000"
    for name, config in CANDIDATES.items():
        if name.startswith("CB"):
            assert config["random_seed"] == SEED == 15015
            assert config["thread_count"] == 1 and config["bootstrap_type"] == "No"
            assert config["random_strength"] == 0 and config["allow_writing_files"] is False
            assert "eval_set" not in config and "early_stopping_rounds" not in config
        elif name.startswith("LGB"):
            assert config["n_jobs"] == 1 and config["deterministic"] is True
            assert config["force_col_wise"] is True
            assert all(value == SEED for key, value in config.items() if key.endswith("seed"))


def test_postprocessing():
    assert normalize_predictions([-1, 0.12345678901234]) == ["0.000000000000", "0.123456789012"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_prediction_fails(bad):
    with pytest.raises(ValueError, match="MODEL_OUTPUT_INVALID"):
        normalize_predictions([bad])


def test_decimal_metrics_and_peak_ties():
    rows = feature_rows(1)
    predictions = [["1"] * 15]
    labels = [["2"] * 15]
    metrics, detail = score(rows, predictions, labels)
    assert metrics["H7_DAILY_WAPE"] == metrics["H15_DAILY_WAPE"] == "0.5"
    assert metrics["H7_CUMULATIVE_WAPE"] == metrics["H15_CUMULATIVE_WAPE"] == "0.5"
    assert metrics["DAILY_MAE_KG"] == "1"
    assert metrics["BIAS_KG"] == "-1"
    assert metrics["TOTAL_SIGNED_BIAS_KG"] == "-15"
    assert metrics["SINGLE_DAY_PEAK_DATE_MAE_DAYS"] == "0"
    assert metrics["ROLLING7_PEAK_START_DATE_MAE_DAYS"] == "0"
    assert metrics["CURVE_SHAPE_ERROR"] == "0"
    assert len(metrics["lead_day_metrics"]) == 15 and len(detail) == 1


def test_peak_earliest_wins_and_rolling_windows():
    values = ["0"] * 15
    values[2] = values[10] = "10"
    predicted = values.copy()
    predicted[2] = "0"
    metrics, _ = score(feature_rows(1), [predicted], [values])
    assert metrics["SINGLE_DAY_PEAK_DATE_MAE_DAYS"] == "8"
    assert metrics["ROLLING7_PEAK_START_DATE_MAE_DAYS"] == "4"


def test_missing_prediction_denominator_rejected():
    with pytest.raises(ValueError, match="COMMON_ROWSET"):
        score(feature_rows(1), [["0"] * 14], [["0"] * 15])


def test_validation_selection_tie_break():
    metric = {"H15_DAILY_WAPE": "0.1", "H7_DAILY_WAPE": "0.2", "DAILY_MAE_KG": "3"}
    assert select_candidate({name: metric for name in ("CB1", "CB2", "CB3")}) == "CB1"
    better = deepcopy(metric)
    better["H15_DAILY_WAPE"] = "0.09"
    assert select_candidate({"CB1": metric, "CB2": better, "CB3": metric}) == "CB2"


def test_oot_never_input_to_config_selection():
    with pytest.raises(ValueError, match="VALIDATION_ONLY"):
        select_candidate({"CB1": {}}, split="EXPOSED_OOT")


def test_seal_tamper_rejected():
    seal = {"phase": "A", "labels_read": False, "predictions": {"RIDGE": "a" * 64}}
    seal["seal_hash"] = digest(seal)
    verify_seal(seal)
    seal["labels_read"] = True
    with pytest.raises(ValueError, match="SEAL"):
        verify_seal(seal)


def test_direction_requires_both_periods_and_horizons():
    ridge = {"H7_DAILY_WAPE": "0.5", "H15_DAILY_WAPE": "0.5"}
    tree = {"H7_DAILY_WAPE": "0.4", "H15_DAILY_WAPE": "0.4"}
    assert direction(tree, ridge, tree, ridge) == "SUPPORTED_DIRECTION"
    assert direction(tree, ridge, ridge, ridge) == "MIXED"
    assert direction(ridge, tree, ridge, tree) == "NOT_SUPPORTED_DIRECTION"


@pytest.mark.parametrize("candidate", ["RIDGE", "CB1", "LGB1"])
def test_real_library_smoke_and_prediction_replay(candidate):
    rows = feature_rows(3)
    x, _ = flatten_features(rows)
    y = np.arange(len(x), dtype=float) % 15
    first = fit_model(candidate, rows, y.tolist())
    second = fit_model(candidate, rows, y.tolist())
    assert first.predict(rows) == second.predict(rows)
    assert len(first.predict(rows)) == 45
    if candidate == "RIDGE":
        assert first.artifact.alpha == "10.000000"
        assert first.artifact.feature_means == tuple(format(v, ".17g") for v in x.mean(axis=0))


@pytest.fixture
def synthetic_dataset(tmp_path, monkeypatch):
    from backend.app.area_yield import v015_base10_benchmark as benchmark
    from backend.app.area_yield import v015_benchmark_custody as custody
    from scripts import run_v0_15_s3_base10_benchmark as operator

    root = tmp_path / "dataset"
    fh, lh = {}, {}
    for split in EXPECTED_COUNTS:
        rows = feature_rows(2)
        for i, row in enumerate(rows):
            row["row_key"] = split + str(i)
            row["split"] = split
            row["season"] = benchmark.SEASONS[split]
            row["feature_hash"] = digest(row["base10"])
            row["row_hash"] = digest(row)
        labels = []
        for row in rows:
            label = {"daily": [str(i + 1) for i in range(15)], "source_hashes": ["a" * 64]}
            value = {
                "row_key": row["row_key"],
                "split": split,
                "season": row["season"],
                "base_id": row["base_id"],
                "target_dates": row["target_dates"],
                "feature_hash": row["feature_hash"],
                "labels": label,
                "label_hash": digest(label),
            }
            value["row_hash"] = digest(value)
            labels.append(value)
        custody.save(root / "feature_zone" / f"{split.lower()}-base10.json", rows)
        custody.save(root / "label_zone" / f"{split.lower()}-labels.json", labels)
        fh[split], lh[split] = digest(rows), digest(labels)
    manifest = {
        "dataset_hashes": {
            **{k + "_FEATURESET_HASH": v for k, v in fh.items()},
            **{k + "_LABELSET_HASH": v for k, v in lh.items()},
        }
    }
    manifest["manifest_hash"] = digest(manifest)
    custody.save(root / "manifest.json", manifest)
    for module in (benchmark, custody, operator):
        monkeypatch.setattr(module, "EXPECTED_COUNTS", {k: 2 for k in EXPECTED_COUNTS})
    for module in (custody, operator):
        monkeypatch.setattr(module, "DATASET_MANIFEST_HASH", manifest["manifest_hash"])
        monkeypatch.setattr(module, "FEATURE_HASHES", fh)
        monkeypatch.setattr(module, "LABEL_HASHES", lh)
    return root


def test_dataset_drift_rejected_before_label_open(synthetic_dataset):
    from backend.app.area_yield.v015_benchmark_custody import FrozenDataset

    path = synthetic_dataset / "manifest.json"
    path.write_text("{}")
    with pytest.raises(ValueError, match="DATASET_DRIFT"):
        FrozenDataset(synthetic_dataset, "A")


def test_label_denial_precedes_file_open(synthetic_dataset, monkeypatch):
    from pathlib import Path

    from backend.app.area_yield.v015_benchmark_custody import FrozenDataset

    data = FrozenDataset(synthetic_dataset, "A")
    prior = Path.read_bytes

    def no_labels(path):
        assert path.parent.name != "label_zone", "UNAUTHORIZED_LABEL_FILE_OPEN"
        return prior(path)

    monkeypatch.setattr(Path, "read_bytes", no_labels)
    for split in ("VALIDATION", "EXPOSED_OOT"):
        with pytest.raises(ValueError, match="LABEL_PHASE_OR_SEAL_DENIED"):
            data.labels(split, [])


def test_prediction_file_tamper_denies_unlock(tmp_path):
    from backend.app.area_yield.v015_benchmark_custody import check_files, save, seal_files

    save(tmp_path / "pred.json", ["1"])
    seal = seal_files(tmp_path, phase="A", names=["pred.json"], rowset_hash="a", contract_hash="b")
    (tmp_path / "pred.json").write_text("[]")
    with pytest.raises(ValueError, match="SEALED_PREDICTION_DRIFT"):
        check_files(tmp_path, seal, expected_names=["pred.json"], contract_hash="b", phase="A")


@pytest.mark.parametrize(
    "value",
    [{"daily": ["1"]}, {"base_id": "private"}, {"coefficients": []}, {"source": "/Users/private"}],
)
def test_public_privacy_rejects_private_values(value):
    from backend.app.area_yield.v015_benchmark_custody import validate_public

    with pytest.raises(ValueError, match="PUBLIC"):
        validate_public(value)


def test_four_stage_real_library_replay_and_custody(synthetic_dataset, tmp_path):
    from pathlib import Path

    from backend.app.area_yield.v015_benchmark_custody import load
    from scripts.run_v0_15_s3_base10_benchmark import final_fit, phase_a, phase_b, score_oot

    outputs = []
    for i in (1, 2):
        output, public = tmp_path / f"run{i}", tmp_path / f"public{i}"
        phase_a(synthetic_dataset, output, Path("."))
        assert load(output / "phase-a-custody.json")["label_reads"] == ["TRAIN"]
        assert load(output / "validation-prediction-seal.json")["labels_read"] is False
        phase_b(synthetic_dataset, output, Path("."))
        selected_before = load(output / "selection.json")
        final_fit(synthetic_dataset, output, Path("."))
        assert load(output / "final-custody.json")["label_reads"] == ["TRAIN", "VALIDATION"]
        assert load(output / "oot-prediction-seal.json")["labels_read"] is False
        score_oot(synthetic_dataset, output, Path("."), public)
        assert load(output / "selection.json") == selected_before
        with pytest.raises(ValueError, match="OOT_ALREADY_CONSUMED"):
            score_oot(synthetic_dataset, output, Path("."), public)
        with pytest.raises(ValueError, match="FINAL_FIT_ALREADY"):
            final_fit(synthetic_dataset, output, Path("."))
        outputs.append(output)
    for path in outputs[0].glob("*-predictions.json"):
        assert path.read_bytes() == (outputs[1] / path.name).read_bytes()
    for name in ("validation-metrics.json", "oot-metrics.json"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    assert (
        load(outputs[0] / "selection.json")["selected"]
        == load(outputs[1] / "selection.json")["selected"]
    )
    from scripts.verify_v0_15_s3_benchmark_replay import replay_report

    assert replay_report(*outputs)["result"] == "PASS"


def test_ridge_scaler_train_only_zero_std_and_base_id_not_feature():
    rows = feature_rows(2)
    for row in rows:
        for v in row["base10"]:
            v[BASE_FEATURES[0]] = "0.5"
    model = fit_model("RIDGE", rows, ["1"] * 30)
    assert model.artifact.feature_scales[0] == "1"
    before = model.artifact.payload()
    changed = deepcopy(rows)
    for row in changed:
        row["base_id"] = "another-synthetic-base"
        for v in row["base10"]:
            v[BASE_FEATURES[1]] = "999999"
    model.predict(changed)
    assert model.artifact.payload() == before
    renamed = deepcopy(rows)
    for row in renamed:
        row["base_id"] = "another-synthetic-base"
    assert model.predict(renamed) == model.predict(rows)


def test_duplicate_target_rows_not_silently_deduplicated():
    rows = feature_rows(1)
    rows.append(deepcopy(rows[0]))
    with pytest.raises(ValueError, match="COMMON_ROWSET"):
        flatten_features(rows)


def test_candidate_expansion_forbidden():
    with pytest.raises(ValueError, match="CANDIDATE_NOT_FROZEN"):
        fit_model("CB4", feature_rows(1), ["1"] * 15)


def test_undefined_zero_actual_wape_no_partial_denominator():
    metrics, _ = score(feature_rows(1), [["0"] * 15], [["0"] * 15])
    assert metrics["H15_DAILY_WAPE"] is None
    assert metrics["CURVE_SHAPE_ERROR"] is None
    assert metrics["curve_shape_undefined_origin_count"] == 1
    assert metrics["target_row_count"] == 15


def test_robustness_removes_entire_base_and_does_not_tune():
    from scripts.run_v0_15_s3_base10_benchmark import breadth, robustness

    ridge = {
        b: {"error7": "10", "error15": "10", "actual7": "100", "actual15": "100"}
        for b in ("a", "b", "c")
    }
    tree = deepcopy(ridge)
    tree["a"]["error7"] = tree["a"]["error15"] = "0"
    report = robustness({"RIDGE": ridge, "CATBOOST": tree, "LIGHTGBM": tree})
    assert report["CATBOOST"]["LEAVE_TOP1"]["metrics"]["CATBOOST"]["H15_DAILY_WAPE"] == "0.1"
    assert report["CATBOOST"]["LEAVE_TOP2"]["removed_base_count"] == 2
    assert breadth(tree, ridge, 15)["improved_base_count"] == 1


def test_validation_and_oot_opposite_direction_no_leader():
    from scripts.run_v0_15_s3_base10_benchmark import comparison

    metric = {
        "H7_DAILY_WAPE": "0.5",
        "H15_DAILY_WAPE": "0.5",
        "H15_CUMULATIVE_WAPE": "0.5",
        "SINGLE_DAY_PEAK_DATE_MAE_DAYS": "1",
    }
    validation = {k: deepcopy(metric) for k in ("RIDGE", "CATBOOST", "LIGHTGBM")}
    oot = deepcopy(validation)
    oot["CATBOOST"]["H7_DAILY_WAPE"] = oot["CATBOOST"]["H15_DAILY_WAPE"] = "0.4"
    assert comparison(validation, oot)["BASE10_RESEARCH_LEADER"] == "NO_CLEAR_LEADER"
