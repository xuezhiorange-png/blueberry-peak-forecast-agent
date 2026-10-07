"""Synthetic file custody, source pinning, replay and public privacy acceptance."""

import ast
import hashlib
import itertools
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.app.area_yield.v015_research_cohort import canonical, digest
from scripts import run_v0_16_s2_uncertainty_calibration as op


@pytest.fixture
def source(tmp_path, monkeypatch):
    process_ids = itertools.count(100)
    monkeypatch.setattr(op, "process_identity", lambda: next(process_ids))
    s5, dataset = tmp_path / "s5", tmp_path / "dataset"
    origins, labels, predictions = [], [], []
    for i in range(25):
        origin = datetime(2025, 9, 1, 17, tzinfo=ZoneInfo("Asia/Shanghai")) + timedelta(days=i)
        key = f"synthetic-{i:02}"
        r = {
            "row_key": key,
            "base_id": "synthetic-base",
            "season": "2025-2026",
            "forecast_origin": origin.isoformat(),
            "split": "EXPOSED_OOT",
            "target_dates": [(origin.date() + timedelta(days=d)).isoformat() for d in range(1, 16)],
            "labels": {"daily": [str(i)] * 15},
        }
        r["label_hash"] = digest(r["labels"])
        r["row_hash"] = digest(r)
        labels.append(r)
        predictions.append({"row_key": key, "predictions": ["10.000000000000"] * 15})
        origins.append(key)
    model, config = {"synthetic": True}, [f"synthetic-feature-{i}" for i in range(14)]
    old = {"models": {"M1": config}, "synthetic": True}
    old["contract_hash"] = digest(old)
    seal = {
        "phase": "FINAL",
        "label_scope": "EXPOSED_OOT",
        "labels_read": False,
        "contract_hash": old["contract_hash"],
        "predictions": {op.PREDICTION_FILE: digest(predictions)},
        "rowset_hash": digest([f"{key}#D{d:02}" for key in origins for d in range(1, 16)]),
    }
    seal["seal_hash"] = digest(seal)
    manifest = {"dataset_hashes": {"EXPOSED_OOT_LABELSET_HASH": digest(labels)}}
    manifest["manifest_hash"] = digest(manifest)
    pins = {
        "model_artifact_hash": digest(model),
        "model_config_hash": digest(config),
        "prediction_hash": digest(predictions),
        "seal_hash": seal["seal_hash"],
        "rowset_hash": seal["rowset_hash"],
        "filtered_labelset_hash": digest([r["labels"]["daily"] for r in labels]),
        "dataset_manifest_hash": manifest["manifest_hash"],
        "full_label_file_hash": digest(labels),
    }
    fit = {
        "M1": {k: pins[k] for k in ("model_artifact_hash", "model_config_hash", "prediction_hash")}
    }
    for path, value in (
        (s5 / "contract.json", old),
        (s5 / op.PREDICTION_FILE, predictions),
        (s5 / "exposed-oot-prediction-seal.json", seal),
        (s5 / "exposed-oot-fit-manifest.json", fit),
        (s5 / "models/exposed-oot-M1.json", model),
        (dataset / "manifest.json", manifest),
        (dataset / "label_zone/exposed_oot-labels.json", labels),
    ):
        op.save(path, value)
    monkeypatch.setattr(op, "PINS", pins)
    monkeypatch.setattr(op, "ORIGINS", 25)
    monkeypatch.setattr(op, "TARGETS", 375)
    monkeypatch.setattr(op, "verify_public", lambda: {"synthetic_fixture": "SYNTHETIC_TRUE"})
    return s5, dataset, tmp_path / "run1", tmp_path / "run2", tmp_path / "public"


def test_prepare_never_opens_label_bytes(source, monkeypatch):
    s5, dataset, output, _, _ = source
    original = Path.read_bytes

    def guarded(path):
        assert "label_zone" not in path.parts
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    op.prepare(s5, dataset, output)
    assert op.load(output / "source-binding-prelabel.json")["label_bytes_read"] is False


def test_end_to_end_replay_privacy_and_source_immutability(source):
    s5, dataset, primary, replay, public = source
    files = [p for root in (s5, dataset) for p in root.rglob("*.json")]
    before = {p: p.read_bytes() for p in files}
    for root in (primary, replay):
        op.prepare(s5, dataset, root)
        op.run(s5, dataset, root)
    op.publish(primary, replay, public)
    assert before == {p: p.read_bytes() for p in files}
    for name in op.OUTPUT_NAMES:
        assert (primary / name).read_bytes() == (replay / name).read_bytes()
        assert (primary / name).stat().st_mode & 0o777 == 0o600
    for p in public.glob("*.json"):
        op.privacy(op.load(p))
        assert "synthetic-base" not in p.read_text()
    assert primary.stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match="RUN_ALREADY_STARTED"):
        op.run(s5, dataset, primary)


@pytest.mark.parametrize(
    "pin",
    [
        "model_artifact_hash",
        "model_config_hash",
        "prediction_hash",
        "seal_hash",
        "rowset_hash",
        "filtered_labelset_hash",
        "full_label_file_hash",
        "dataset_manifest_hash",
    ],
)
def test_source_binding_drift_rejected(source, monkeypatch, pin):
    s5, dataset, output, _, _ = source
    monkeypatch.setattr(op, "PINS", op.PINS | {pin: "0" * 64})
    with pytest.raises(ValueError):
        op.prepare(s5, dataset, output)
        op.run(s5, dataset, output)


def test_contract_tampering_and_no_label_read_on_failure(source, monkeypatch):
    s5, dataset, output, _, _ = source
    op.prepare(s5, dataset, output)
    original = Path.read_bytes

    def guarded(path):
        assert "label_zone" not in path.parts
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    monkeypatch.setattr(op, "PINS", op.PINS | {"seal_hash": "0" * 64})
    with pytest.raises(ValueError, match="CONFORMAL_CONTRACT_DRIFT"):
        op.run(s5, dataset, output)


def test_m0_and_missing_prediction_row_rejected(source):
    s5, dataset, _, _, _ = source
    fit = op.load(s5 / "exposed-oot-fit-manifest.json")
    fit["M1"]["model_config_hash"] = "M0_NOT_ALLOWED"
    # Deliberate synthetic tampering only, never frozen operator inputs.
    (s5 / "exposed-oot-fit-manifest.json").write_bytes(canonical(fit))
    with pytest.raises(ValueError, match="POINT_MODEL_IDENTITY_MISMATCH"):
        op.sources(s5, dataset)


def test_current_season_envelope_rejected_before_filtering(source, monkeypatch):
    s5, dataset, output, _, _ = source
    labels = op.load(dataset / "label_zone/exposed_oot-labels.json")
    labels[-1]["season"] = "2026-2027"
    (dataset / "label_zone/exposed_oot-labels.json").write_bytes(canonical(labels))
    pins = op.PINS | {"full_label_file_hash": digest(labels)}
    manifest = {"dataset_hashes": {"EXPOSED_OOT_LABELSET_HASH": digest(labels)}}
    manifest["manifest_hash"] = digest(manifest)
    (dataset / "manifest.json").write_bytes(canonical(manifest))
    pins["dataset_manifest_hash"] = manifest["manifest_hash"]
    monkeypatch.setattr(op, "PINS", pins)
    op.prepare(s5, dataset, output)
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        op.run(s5, dataset, output)


def test_replay_tamper_and_same_root_rejected(source):
    s5, dataset, primary, replay, public = source
    for root in (primary, replay):
        op.prepare(s5, dataset, root)
        op.run(s5, dataset, root)
    with pytest.raises(ValueError, match="INDEPENDENT_REPLAY_REQUIRED"):
        op.publish(primary, primary, public)
    (replay / "private-interval-rows.json").write_bytes(b"[]\n")
    with pytest.raises(ValueError, match="DETERMINISTIC_REPLAY_FAILED"):
        op.publish(primary, replay, public)
    assert not public.exists()


@pytest.mark.parametrize(
    "bad",
    [
        {"base_id": "secret"},
        {"actual_kg": "1"},
        {"coefficients": []},
        {"message": "/Users/private"},
        {"url": "postgresql://secret"},
    ],
)
def test_privacy_fail_closed(bad):
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_DATA_LEAK"):
        op.privacy(bad)


def test_cli_error_privacy_and_paths_not_echoed(source, monkeypatch, capsys):
    s5, dataset, output, _, _ = source

    def failed(*args):
        raise OSError("/Users/private/credential")

    monkeypatch.setattr(op, "prepare", failed)
    assert (
        op.main(
            [
                "PREPARE",
                "--s5-output-root",
                str(s5),
                "--dataset-root",
                str(dataset),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    text = capsys.readouterr().out
    assert "/Users/" not in text and str(output) not in text
    assert json.loads(text)["code"] == "UNCERTAINTY_OPERATOR_FAILED"


def test_static_no_training_actual_io_and_legacy_schema_isolation():
    module = op.REPOSITORY / "backend/app/forecast_intelligence/uncertainty.py"
    engine = ast.parse(module.read_text())
    assert not any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open"
        for n in ast.walk(engine)
    )
    for p in (module, Path(op.__file__)):
        tree = ast.parse(p.read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        assert not any(
            isinstance(n.func, ast.Attribute) and n.func.attr in {"fit", "predict", "fit_predict"}
            for n in calls
        )
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            any(
                s in name
                for s in ("catboost", "lightgbm", "prospective", "actual_evaluation", "label_vault")
            )
            for name in imports
        )
    assert not {"forecast_p50", "forecast_p80", "forecast_p90"} & set(op.policy())
    assert op.verify_public()  # Also checks the real frozen public authority without private data.
    assert all(
        "uncertainty" not in p.read_text()
        for p in [
            op.REPOSITORY / "backend/app/models/hierarchical_forecast.py",
            op.REPOSITORY / "backend/app/forecast_intelligence/schemas.py",
        ]
    )


def test_fresh_process_domain_replay():
    code = """from backend.tests.forecast_intelligence.test_uncertainty import rows
from backend.app.forecast_intelligence.uncertainty import calibrate,evaluate
from backend.app.area_yield.v015_research_cohort import digest
r=calibrate(rows()); print(digest(r)); print(digest(evaluate(r)))
"""
    env = os.environ | {"PYTHONPATH": str(op.REPOSITORY)}
    a = subprocess.check_output([sys.executable, "-c", code], env=env)
    b = subprocess.check_output([sys.executable, "-c", code], env=env)
    assert a == b
    assert len(hashlib.sha256(a).hexdigest()) == 64


def test_exact_origin_accounting_rejected(source, monkeypatch):
    s5, dataset, output, _, _ = source
    monkeypatch.setattr(op, "ORIGINS", 26)
    with pytest.raises(ValueError, match="ROWSET_ACCOUNTING_FAILED"):
        op.prepare(s5, dataset, output)


def test_s1_frozen_point_hash_unchanged():
    from backend.app.forecast_intelligence.reconciliation import reconcile
    from backend.tests.forecast_intelligence.test_reconciliation import hierarchy, request, sources

    assert reconcile(hierarchy(), request(), sources())["result_hash"] == (
        "156f6319c101cfd73916f7ae80a8434d191f23e4cf51e8a3059698f729352302"
    )


def test_published_evidence_hashes_accounting_and_no_overclaim():
    root = op.REPOSITORY / "docs/v0-16/evidence/uncertainty-conformal-calibration-r1"
    manifest = op.load(root / "manifest-r1.json")
    for name, expected in manifest["files"].items():
        raw = (root / name).read_bytes()
        assert op.sha(raw) == expected
        assert raw == canonical(op.load(root / name))
        op.privacy(op.load(root / name))
    c = op.load(root / "conformal-policy-r1.json")
    assert c["policy"] == op.policy()
    assert c["policy_hash"] == manifest["policy_hash"] == digest(c["policy"])
    m = op.load(root / "coverage-summary-r1.json")
    for horizon, count in (("H7", 61425), ("H15", 131625)):
        for metric in m[horizon].values():
            assert metric["candidate_row_count"] == count
            assert metric["computable_row_count"] + metric["not_computable_row_count"] == count
            assert metric["covered_row_count"] <= metric["computable_row_count"]
    assert [r["lead_day"] for r in op.load(root / "lead-day-coverage-r1.json")] == list(
        range(1, 16)
    )
    evidence = op.load(root / "v0.16-s2-uncertainty-and-conformal-calibration-r1.json")
    for key in (
        "strict_pit",
        "prospective_interval_coverage_validated",
        "production_interval_approval",
        "point_forecast_is_proven_p50",
        "true_quantile_semantics_established",
        "model_training_executed",
        "point_prediction_reexecuted",
        "s1_schema_changed",
        "current_season_actual_read",
        "s3_started",
        "ready_authorized",
        "merge_authorized",
    ):
        assert evidence[key] is False
