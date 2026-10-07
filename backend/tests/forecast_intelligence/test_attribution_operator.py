"""Synthetic operator acceptance; real inputs remain outside Git and CI."""

import ast
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.area_yield.data import digest as model_digest
from backend.app.area_yield.v015_research_cohort import canonical, digest
from backend.app.forecast_intelligence import attribution as a
from backend.tests.forecast_intelligence.test_attribution import model
from scripts import run_v0_16_s3_forecast_attribution as o


def fixture_roots(tmp_path, monkeypatch):
    s5, data, harvest = [tmp_path / n for n in ("s5", "dataset", "harvest")]
    full_model = model()
    legacy = {k: v for k, v in full_model.items() if k != "standardization"}
    monkeypatch.setattr(a, "LEGACY_INTERNAL_HASH", legacy["artifact_hash"])
    monkeypatch.setattr(
        a,
        "LEGACY_RAW_DIGEST",
        model_digest({k: v for k, v in legacy.items() if k != "artifact_hash"}),
    )
    rows = [
        {
            "row_key": "synthetic-origin",
            "base_id": "SYNTHETIC_BASE",
            "season": "2025-2026",
            "split": "EXPOSED_OOT",
            "forecast_origin": "2025-02-01T17:00:00+08:00",
            "target_dates": [f"2025-02-{i:02}" for i in range(2, 17)],
            "missing_mask": [False] * 10,
            "base10": [dict.fromkeys(a.FEATURES[:10], "14") for _ in range(15)],
        }
    ]
    states = {"synthetic-origin": dict.fromkeys(a.FEATURES[10:], "14")}
    contract = {"models": {"M1": list(a.FEATURES)}, "ridge": {"standardization": a.STANDARDIZATION}}
    contract["contract_hash"] = digest(contract)
    predictions = [{"row_key": "synthetic-origin", "predictions": ["85.000000000000"] * 15}]
    seal = {
        "phase": "FINAL",
        "label_scope": "EXPOSED_OOT",
        "labels_read": False,
        "contract_hash": contract["contract_hash"],
        "rowset_hash": digest([f"synthetic-origin#D{i:02}" for i in range(1, 16)]),
        "predictions": {o.PREDICTIONS: digest(predictions)},
    }
    seal["seal_hash"] = digest(seal)
    paths = o.source_paths(s5, data, harvest)
    values = {
        "model": legacy,
        "predictions": predictions,
        "seal": seal,
        "s5_contract": contract,
        "base10": rows,
        "harvest": states,
        "common": ["synthetic-origin"],
        "dataset_manifest": {},
        "harvest_manifest": {},
    }
    pins = {
        "model_artifact_hash": digest(legacy),
        "model_config_hash": digest(list(a.FEATURES)),
        "prediction_hash": digest(predictions),
        "prediction_seal_hash": seal["seal_hash"],
        "target_rowset_hash": seal["rowset_hash"],
        "common_rowset_hash": digest(values["common"]),
        "base10_feature_hash": digest(rows),
        "harvest_state_feature_hash": digest(states),
    }
    values["fit"] = {
        "M1": {k: pins[k] for k in ("model_artifact_hash", "model_config_hash", "prediction_hash")}
    }
    for key, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(canonical(values[key]))
    monkeypatch.setattr(a, "LEGACY_FILE_HASH", pins["model_artifact_hash"])
    monkeypatch.setattr(o, "PINS", pins)
    monkeypatch.setattr(o, "ORIGINS", 1)
    monkeypatch.setattr(o, "TARGETS", 15)
    monkeypatch.setattr(
        o,
        "public_authority",
        lambda: {
            "historical_source": {"source_sha256": a.LEGACY_SOURCE_HASH, "schema_proven": True}
        },
    )

    class Dataset:
        def __init__(self, *args):
            pass

        def features(self, split):
            assert split == "EXPOSED_OOT"
            return rows

    class Harvest:
        def __init__(self, *args):
            pass

        def bind(self, split, full):
            return full, states

    monkeypatch.setattr(o, "FrozenDataset", Dataset)
    monkeypatch.setattr(o, "HarvestCustody", Harvest)
    return s5, data, harvest


def test_all_phases_no_labels_sources_immutable_private_permissions(tmp_path, monkeypatch):
    roots = fixture_roots(tmp_path, monkeypatch)
    before = {k: p.read_bytes() for k, p in o.source_paths(*roots).items()}
    for root in roots:
        (root / "label_zone").mkdir()
        (root / "label_zone/trap").write_text("DO_NOT_READ")
    p, r, public = [tmp_path / n for n in ("primary", "replay", "public")]
    with o.no_labels():
        for output, pid in ((p, 123), (r, 456)):
            monkeypatch.setattr(o.os, "getpid", lambda pid=pid: pid)
            o.prepare(*roots, output)
            o.run(*roots, output)
        o.publish(p, r, public)
        with pytest.raises(ValueError, match="LABEL_ACCESS_FORBIDDEN"):
            (roots[1] / "label_zone/trap").read_bytes()
    assert before == {k: path.read_bytes() for k, path in o.source_paths(*roots).items()}
    for name in o.OUTPUTS:
        assert (p / name).read_bytes() == (r / name).read_bytes()
        assert (p / name).stat().st_mode & 0o777 == 0o600
    assert p.stat().st_mode & 0o777 == 0o700
    for path in public.glob("*.json"):
        o.privacy(o.load(path))
        assert b"SYNTHETIC_BASE" not in path.read_bytes()
    summary = o.load(public / "reconstruction-summary-r1.json")
    assert (
        summary["exact_prediction_match_count"] == 15
        and summary["exact_prediction_mismatch_count"] == 0
    )
    manifest = o.load(public / "manifest-r1.json")
    for name, hashed in manifest["files"].items():
        assert o.sha((public / name).read_bytes()) == hashed
    assert len(o.load(public / "feature-contribution-summary-r1.json")) == 14
    assert len(o.load(public / "family-group-summary-r1.json")["groups"]) == 2
    assert len(o.load(public / "business-semantic-group-summary-r1.json")["groups"]) == 5
    with pytest.raises(FileExistsError):
        o.run(*roots, p)


@pytest.mark.parametrize(
    "key", ["model", "predictions", "base10", "harvest", "common", "fit", "seal", "s5_contract"]
)
def test_source_hash_binding_rejects_changes(tmp_path, monkeypatch, key):
    roots = fixture_roots(tmp_path, monkeypatch)
    path = o.source_paths(*roots)[key]
    value = o.load(path)
    if key in {"model", "fit", "seal", "s5_contract"}:
        value = {**value, "drift": True}
        if key == "fit":
            value["M1"]["model_config_hash"] = "x"
    else:
        value = []
    path.write_bytes(canonical(value))
    with pytest.raises(ValueError):
        o.prepare(*roots, tmp_path / "out")


def test_contract_and_replay_tamper(tmp_path, monkeypatch):
    roots = fixture_roots(tmp_path, monkeypatch)
    p, r = tmp_path / "p", tmp_path / "r"
    for out, pid in ((p, 111), (r, 222)):
        monkeypatch.setattr(o.os, "getpid", lambda pid=pid: pid)
        o.prepare(*roots, out)
        o.run(*roots, out)
    (r / "feature-summary.json").write_text("[]")
    with pytest.raises(ValueError, match="REPLAY_MISMATCH"):
        o.publish(p, r, tmp_path / "public")
    contract = o.load(p / "contract.json")
    contract["policy"]["nonnegative_clip"] = False
    (p / "contract.json").write_bytes(canonical(contract))
    with pytest.raises(ValueError, match="CONTRACT_DRIFT"):
        o.verify_contract(p)


def test_private_output_overlap_and_same_process_refused(tmp_path, monkeypatch):
    roots = fixture_roots(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="PRIVATE_OUTPUT_LOCATION_INVALID"):
        o.prepare(*roots, roots[0] / "output")
    p, r = tmp_path / "p", tmp_path / "r"
    for out in (p, r):
        o.prepare(*roots, out)
        o.run(*roots, out)
    with pytest.raises(ValueError, match="FRESH_PROCESS_REPLAY_REQUIRED"):
        o.publish(p, r, tmp_path / "public")


def test_historical_source_and_public_authority(monkeypatch):
    # PR checkouts can be shallow. Exercise the exact Git-blob request with a
    # hash-identical fixture; real PREPARE independently reads the historical blob.
    raw = (o.REPOSITORY / o.RIDGE_SOURCE).read_bytes()
    assert o.sha(raw) == a.LEGACY_SOURCE_HASH

    def git_blob(command, **kwargs):
        assert command == ["git", "show", f"{o.HISTORICAL_COMMIT}:{o.RIDGE_SOURCE}"]
        return SimpleNamespace(returncode=0, stdout=raw)

    monkeypatch.setattr(o.subprocess, "run", git_blob)
    assert o.historical_source()["source_sha256"] == a.LEGACY_SOURCE_HASH
    assert o.public_authority()["historical_source"]["schema_proven"]
    monkeypatch.setattr(
        o.subprocess, "run", lambda *x, **k: SimpleNamespace(returncode=1, stdout=b"")
    )
    with pytest.raises(ValueError, match="HISTORICAL_RIDGE_AUTHORITY_UNAVAILABLE"):
        o.historical_source()


@pytest.mark.parametrize(
    "value",
    [
        {"base_id": "x"},
        {"intercept": "1"},
        {"coefficients": []},
        {"target_date": "x"},
        {"x": "/private/forbidden"},
        {"actual": "0"},
    ],
)
def test_privacy(value):
    with pytest.raises(ValueError):
        o.privacy(value)


def test_no_training_labels_current_actual_static():
    for module in (a, o):
        tree = ast.parse(Path(module.__file__).read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", "")
                )
                assert name not in {
                    "fit",
                    "fit_predict",
                    "fit_model",
                    "fit_ridge_artifact",
                    "labels",
                    "score",
                    "calibrate",
                }
            if isinstance(node, ast.ImportFrom):
                assert not any(
                    x in (node.module or "")
                    for x in ("prospective", "actual_evaluation", "catboost", "lightgbm")
                )
    assert "standardization" not in o.load(
        o.REPOSITORY / "docs/v0-16/evidence/v0.16-s1-hierarchical-forecast-reconciliation-r1.json"
    ).get("persistence_tables", [])
    s2 = o.load(
        o.REPOSITORY
        / "docs/v0-16/evidence/uncertainty-conformal-calibration-r1/conformal-policy-r1.json"
    )
    assert (
        digest(s2["policy"]) == "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
    )


def test_fresh_process_complete_synthetic_replay(tmp_path):
    code = """import pathlib,sys,pytest
from backend.tests.forecast_intelligence.test_attribution_operator import fixture_roots
from scripts import run_v0_16_s3_forecast_attribution as o
m=pytest.MonkeyPatch(); base=pathlib.Path(sys.argv[1]); roots=fixture_roots(base,m)
out=base/sys.argv[2]; o.prepare(*roots,out); o.run(*roots,out)
"""
    for name in ("p", "r"):
        completed = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path), name], cwd=o.REPOSITORY, capture_output=True
        )
        assert completed.returncode == 0, "SYNTHETIC_PROCESS_FAILED"
    for name in o.OUTPUTS:
        assert (tmp_path / "p" / name).read_bytes() == (tmp_path / "r" / name).read_bytes()
    assert o.load(tmp_path / "p/run-started.json") != o.load(tmp_path / "r/run-started.json")


def test_operator_error_privacy(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["operator", "PREPARE"])
    assert o.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["code"] == "ATTRIBUTION_OPERATOR_FAILED"


def test_frozen_public_s3_evidence_contract_and_privacy():
    root = o.REPOSITORY / "docs/v0-16/evidence/forecast-attribution-r1"
    manifest = o.load(root / "manifest-r1.json")
    for name, hashed in manifest["files"].items():
        raw = (root / name).read_bytes()
        value = json.loads(raw)
        assert o.sha(raw) == hashed and canonical(value) == raw
        o.privacy(value)
    policy = o.load(root / "attribution-policy-r1.json")
    assert digest(policy["policy"]) == policy["policy_hash"] == manifest["policy_hash"]
    assert policy["policy"]["features"] == list(a.FEATURES)
    for path, hashed in policy["policy"]["source_evidence_sha256"].items():
        assert o.sha((o.REPOSITORY / path).read_bytes()) == hashed
    binding = o.load(root / "source-binding-r1.json")
    compat = binding["legacy_compatibility"]
    assert compat["stored_artifact_hash"] == a.LEGACY_INTERNAL_HASH
    assert compat["model_artifact_file_hash"] == a.LEGACY_FILE_HASH
    assert compat["compat_reconstructed_digest_match"] is True
    assert compat["inference_numeric_fields_changed"] is False
    counts = o.load(root / "reconstruction-summary-r1.json")
    assert counts["origin_count"] == 8775
    assert counts["target_row_count"] == counts["exact_prediction_match_count"] == 131625
    assert (
        counts["exact_prediction_mismatch_count"]
        == counts["serialized_accounting_mismatch_count"]
        == 0
    )
    assert (
        counts["serialized_accounting_exact_count"]
        == counts["raw_linear_binary_match_count"]
        == 131625
    )
    assert counts["clipped_target_row_count"] + counts["unclipped_target_row_count"] == 131625
    features = o.load(root / "feature-contribution-summary-r1.json")
    assert len(features) == 14 and all(r["target_row_count"] == 131625 for r in features)
    horizons = o.load(root / "horizon-contribution-summary-r1.json")
    assert all(horizons[f"H{h}"]["exact_reconstruction_count"] == 8775 for h in (7, 15))
    receipt = o.load(root / "v0.16-s3-forecast-attribution-r1.json")
    for flag in (
        "attribution_is_causal_explanation",
        "shap_used",
        "label_bytes_read",
        "model_training_executed",
        "current_season_actual_read",
        "s1_changed",
        "s2_changed",
        "s4_started",
        "ready_authorized",
        "merge_authorized",
    ):
        assert receipt[flag] is False
