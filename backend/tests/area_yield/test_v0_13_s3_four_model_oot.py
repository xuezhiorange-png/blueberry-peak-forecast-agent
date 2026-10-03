"""Public synthetic acceptance; never opens operator private sources."""

import json
from copy import deepcopy
from decimal import Decimal

import pytest

from backend.app.area_yield import v013_feature_value_experiment as e
from backend.app.area_yield.data import digest

pytestmark = pytest.mark.contract


def test_frozen_four_model_matrix() -> None:
    e.validate_contract(e.CONTRACT)
    assert [len(e.FEATURES[m]) for m in e.MODELS] == [10, 28, 13, 31]
    assert e.FEATURES["M3"] == e.FEATURES["M1"] + ("gdd_w7", "gdd_w14", "gdd_w30")


@pytest.mark.parametrize(
    "field,value",
    [
        ("alpha", "5"),
        ("solver", "lstsq"),
        ("standardization", "VALIDATION_SCALER"),
        ("clip", False),
        ("tbase", "5"),
        ("tbase", "10"),
        ("windows", [7, 14, 21]),
        ("upper_cap", "30"),
        ("lead_feature", True),
        ("impute", True),
        ("refit_leave_top", True),
        ("combined", "ARITHMETIC_MEAN"),
        ("primary_metric", "CUMULATIVE_WAPE"),
        ("comparisons", ["SIXTH"]),
        ("feature_search", True),
        ("features", {"M0": ["extra"]}),
    ],
)
def test_failure_contract_mutation(field, value) -> None:
    c = deepcopy(e.CONTRACT)
    c[field] = value
    with pytest.raises(e.ExperimentError):
        e.validate_contract(c)


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "order"])
def test_failure_row_authority(change) -> None:
    keys = ["a", "b"]
    changed = {
        "missing": ["a"],
        "extra": ["a", "b", "c"],
        "changed": ["a", "c"],
        "order": ["b", "a"],
    }[change]
    with pytest.raises(e.ExperimentError):
        e.verify_keys(changed, 2, digest(keys))


@pytest.mark.parametrize("change", ["hash", "standardization", "coefficient", "feature_order"])
def test_failure_artifact_self_integrity(change) -> None:
    a = e.synthetic_artifact()
    assert e.verify_artifact(a) is None
    if change == "hash":
        a["artifact_hash"] = "0" * 64
    elif change == "standardization":
        del a["standardization"]
    elif change == "coefficient":
        a["coefficients"][0] = "99"
    else:
        a["feature_names"] = list(reversed(a["feature_names"]))
    with pytest.raises(e.ExperimentError):
        e.verify_artifact(a)


@pytest.mark.parametrize("season", ["2024-2025", "2025-2026"])
def test_failure_validation_open_before_seal(tmp_path, season) -> None:
    guard = e.ExecutionGuard(tmp_path)
    with pytest.raises(e.ExperimentError):
        guard.allow_label_read(season)


def test_failure_score_before_both_seals_and_post_score_fit(tmp_path) -> None:
    guard = e.ExecutionGuard(tmp_path)
    with pytest.raises(e.ExperimentError):
        guard.begin_score()
    guard.scoring_started = True
    with pytest.raises(e.ExperimentError):
        guard.allow_fit()


def sample_rows():
    return [
        dict(
            base_id=base,
            season="synthetic",
            forecast_origin="2028-07-01T00:00:00+08:00",
            target_date="2028-07-01",
            lead_day=0,
            actual_daily_kg="10",
            M0="12",
            M1=pred,
            M2="11",
            M3="10",
        )
        for base, pred in [("a", "10"), ("b", "13"), ("c", "11")]
    ]


def test_daily_vs_cumulative_and_breadth_leave_top() -> None:
    r = sample_rows()
    result = e.compare(r, "M0", "M1", all_base_ids=["a", "b", "c", "missing"])
    assert result["breadth"]["improved_base_count"] == 2
    assert result["breadth"]["not_computable_base_count"] == 1
    assert result["leave_top2"]["removed_base_ids"] == ["a", "c"]
    assert Decimal(result["leave_top2"]["delta"]) > 0
    assert result["leave_top2"]["refit"] is False
    r = [dict(r[0], lead_day=0, M0="12"), dict(r[0], lead_day=1, M0="8")]
    assert e.metric(r, "M0")["pooled_wape"] == "0.2"
    assert e.cumulative_metric(r, "M0", 2)["pooled_wape"] == "0"


def test_combined_removes_same_base_across_folds() -> None:
    r = sample_rows()
    r += [dict(r[0], season="other")]
    result = e.compare(r, "M0", "M1")
    assert result["leave_top1"]["removed_base_ids"] == ["a"]
    assert result["leave_top1"]["sample_count"] == 2


def test_supported_gate_requires_every_condition() -> None:
    scopes = {
        s: {
            h: {
                "delta": "-0.01",
                "leave_top2": {"delta": "-0.005"},
                "breadth": {"improved_actual_kg_share": "0.6"},
            }
            for h in ("H1", "H7", "H15")
        }
        for s in ("fold_a", "fold_b", "combined")
    }
    assert e.predictive_gate(scopes)["status"] == "MEETS_SUPPORTED_CRITERIA"
    scopes["fold_b"]["H7"]["breadth"]["improved_actual_kg_share"] = "0.50"
    assert e.predictive_gate(scopes)["status"] == "INCONCLUSIVE_BY_FROZEN_RULE"


def test_zero_denominator_is_not_a_win() -> None:
    r = sample_rows()
    for row in r:
        row["actual_daily_kg"] = "0"
    assert e.compare(r, "M0", "M1")["delta"] is None


def durable_seal(root, fold):
    from backend.app.area_yield.gdd_features import sha256

    directory = root / fold
    directory.mkdir()
    files = ["predictions-before-scoring.jsonl", *(f"{m.lower()}-artifact.json" for m in e.MODELS)]
    for name in files:
        (directory / name).write_text("synthetic")
    seal = dict(
        fold_id=fold.upper(),
        sealed_before_validation_label_read=True,
        model_ids=list(e.MODELS.values()),
        file_hashes={n: sha256(directory / n) for n in files},
    )
    seal["seal_hash"] = digest(seal)
    (directory / "prediction-seal.json").write_text(json.dumps(seal))
    return seal


@pytest.mark.parametrize(
    "mutation", ["prediction", "artifact", "seal", "missing", "extra_inventory", "model"]
)
def test_failure_durable_seal_tamper(tmp_path, mutation):
    seal = durable_seal(tmp_path, "fold_a")
    directory = tmp_path / "fold_a"
    if mutation in ("prediction", "artifact"):
        name = (
            "predictions-before-scoring.jsonl" if mutation == "prediction" else "m0-artifact.json"
        )
        (directory / name).write_text("tampered")
    elif mutation == "missing":
        (directory / "prediction-seal.json").unlink()
    else:
        if mutation == "model":
            seal["model_ids"][0] = "unknown"
        elif mutation == "extra_inventory":
            seal["file_hashes"]["../other"] = "0" * 64
        else:
            seal["seal_hash"] = "0" * 64
        if mutation != "seal":
            seal["seal_hash"] = digest({k: v for k, v in seal.items() if k != "seal_hash"})
        (directory / "prediction-seal.json").write_text(json.dumps(seal))
    with pytest.raises(e.ExperimentError):
        e.ExecutionGuard(tmp_path).allow_label_read("2024-2025")


def test_durable_staged_sequence_and_no_refit(tmp_path):
    guard = e.ExecutionGuard(tmp_path)
    guard.allow_label_read("2023-2024")
    durable_seal(tmp_path, "fold_a")
    guard.allow_label_read("2024-2025")
    with pytest.raises(e.ExperimentError):
        guard.begin_score()
    durable_seal(tmp_path, "fold_b")
    guard.allow_label_read("2025-2026")
    guard.begin_score()
    with pytest.raises(e.ExperimentError):
        guard.allow_fit()


@pytest.mark.parametrize(
    "condition", ["no_contract_violation", "no_leakage", "no_post_result_tuning"]
)
def test_invalid_experiment_never_classified(condition):
    with pytest.raises(e.ExperimentError):
        e.predictive_gate({}, **{condition: False})


def test_four_model_synthetic_ridge_fit_and_prediction():
    from datetime import date

    from backend.app.area_yield.weather_aware_backtest import RollingTargetRow, fit_ridge_artifact
    from scripts.run_v07_s3_weather_aware_backtest import _training_input_hash

    rows = [
        RollingTargetRow(
            key=str(i),
            base_id="SYNTHETIC",
            base_name="Synthetic",
            season="2023-2024",
            forecast_origin="2023-09-01T00:00:00+08:00",
            target_date=date(2023, 9, 1),
            lead_day=0,
            reference_area_mu=Decimal(100),
            feature_values=tuple((name, str(i)) for name in e.FEATURES["M3"]),
            weather_feature_hash="0" * 64,
        )
        for i in range(4)
    ]
    labels = [(r, Decimal(i + 1)) for i, r in enumerate(rows)]
    for name in e.MODELS:
        input_hash = _training_input_hash(
            fold_id="FOLD_A",
            training_rows=labels,
            feature_names=e.FEATURES[name],
            training_seasons=["2023-2024"],
            weather_source_hash="0" * 64,
        )
        artifact = fit_ridge_artifact(
            model_id=e.MODELS[name],
            fold_id="FOLD_A",
            rows=labels,
            feature_names=e.FEATURES[name],
            training_input_hash=input_hash,
        )
        assert len(artifact.coefficients) == len(e.FEATURES[name])
        assert artifact.predict(rows[0]) >= 0


@pytest.mark.parametrize("status", ["MISSING", "UNKNOWN", "UNMAPPED", "PARTIAL"])
def test_failure_missing_or_unknown_cannot_be_zero(status):
    from types import SimpleNamespace

    assert e.authoritative_actual(SimpleNamespace(status=status, quantity_kg=Decimal(0))) is None


@pytest.mark.parametrize("quantity", ["NaN", "Infinity", "-1"])
def test_failure_invalid_actual(quantity):
    from types import SimpleNamespace

    with pytest.raises(e.ExperimentError):
        e.authoritative_actual(
            SimpleNamespace(status="KNOWN_MAPPED_SUBTOTAL", quantity_kg=Decimal(quantity))
        )


@pytest.mark.parametrize("model", ["M0", "M1", "M2", "M3"])
def test_failure_feature_order_and_extra_feature(model):
    contract = deepcopy(e.CONTRACT)
    contract["features"][model] = list(reversed(contract["features"][model]))
    with pytest.raises(e.ExperimentError):
        e.validate_contract(contract)


def test_incomplete_primary_evidence_cannot_be_not_supported():
    scopes = {
        scope: {
            h: dict(
                delta="0.01",
                leave_top2={"delta": "0.01"},
                breadth={"improved_actual_kg_share": "0.1"},
            )
            for h in ("H7", "H15")
        }
        for scope in ("fold_a", "fold_b", "combined")
    }
    scopes["fold_a"]["H15"]["delta"] = None
    assert e.predictive_gate(scopes)["status"] == "INCONCLUSIVE_BY_FROZEN_RULE"


def test_pooled_not_arithmetic_mean():
    rows = sample_rows()[:2]
    rows[0].update(actual_daily_kg="1", M0="2")
    rows[1].update(actual_daily_kg="9", M0="9")
    assert e.metric(rows, "M0")["pooled_wape"] == "0.1"


def test_model_specific_cohort_rejected():
    from backend.app.area_yield.gdd_features import GDDError, require_common_models

    with pytest.raises(GDDError):
        require_common_models({"M0": ["a"], "M1": ["a"], "M2": [], "M3": ["a"]})


@pytest.mark.parametrize("mutation", ["source", "weather", "registry", "identity"])
def test_failure_operator_identity_preflight(tmp_path, monkeypatch, mutation):
    from argparse import Namespace

    from scripts import run_v0_13_s3_four_model_oot as runner

    args = Namespace(
        output=tmp_path / "output",
        source23=tmp_path / "23",
        source24=tmp_path / "24",
        source25=tmp_path / "25",
        weather=tmp_path / "weather",
        registry=tmp_path / "registry",
        identity=tmp_path / "identity",
        members=tmp_path / "members",
        gdd=tmp_path / "gdd",
    )
    hashes = {
        args.source23: runner.EXPECTED_SOURCE_HASHES["2023-2024"],
        args.source24: runner.EXPECTED_SOURCE_HASHES["2024-2025"],
        args.source25: runner.EXPECTED_SOURCE_HASHES["2025-2026"],
        args.weather: runner.WEATHER_DATASET_HASH,
    }
    if mutation == "source":
        hashes[args.source23] = "0" * 64
    if mutation == "weather":
        hashes[args.weather] = "0" * 64
    monkeypatch.setattr(runner, "file_identity", lambda p: dict(sha256=hashes.get(p, "0" * 64)))
    monkeypatch.setattr(
        runner,
        "load_registry",
        lambda p: ({}, "0" * 64 if mutation == "registry" else runner.REGISTRY_HASH),
    )
    monkeypatch.setattr(runner, "load_identity_mapping", lambda *a: ({}, {}, "0" * 64, {}))
    monkeypatch.setattr(
        runner, "load_source", lambda *a: pytest.fail("Preflight must not parse labels")
    )
    with pytest.raises(e.ExperimentError, match="MISMATCH"):
        runner.run(args)
    assert not args.output.exists()
