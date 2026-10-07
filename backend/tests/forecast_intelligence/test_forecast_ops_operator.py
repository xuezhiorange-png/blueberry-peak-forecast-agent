"""Offline operator custody, replay and privacy contracts; synthetic inputs only."""

import ast
import json
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.v015_research_cohort import canonical
from scripts import run_v0_16_s4_forecastops_monitoring as op


@pytest.fixture
def synthetic_operator(monkeypatch, tmp_path):
    origin = datetime.fromisoformat("2025-11-01T17:00:00+08:00")
    row = {
        "row_key": "SYNTHETIC_ROW",
        "base_id": "SYNTHETIC_BASE",
        "season": "2025-2026",
        "forecast_origin": origin.isoformat(),
        "target_dates": [(origin.date() + timedelta(days=d)).isoformat() for d in range(1, 16)],
    }
    s5, dataset, harvest = (tmp_path / n for n in ("s5", "dataset", "harvest"))
    s5.mkdir()
    harvest.mkdir()
    label = dataset / "label_zone/exposed_oot-labels.json"
    label.parent.mkdir(parents=True)
    label.write_bytes(canonical([row]))
    labels = [["5"] * 15]
    pins = dict(
        op.s2.PINS,
        full_label_file_hash=op.sha(label.read_bytes()),
        filtered_labelset_hash=op.digest(labels),
    )
    monkeypatch.setattr(op.s2, "PINS", pins)
    monkeypatch.setattr(op.s2, "ORIGINS", 1)
    monkeypatch.setattr(op.s2, "TARGETS", 15)
    monkeypatch.setattr(op, "policy", lambda: {"SYNTHETIC": True, "source_bindings": pins})

    class Frozen:
        def labels(self, split, features):
            assert label.read_bytes()
            return labels

    binding = {"synthetic": op.sha(canonical(row))}
    monkeypatch.setattr(
        op,
        "sources",
        lambda *args: (
            Frozen(),
            [row],
            [row],
            [{"row_key": row["row_key"], "predictions": ["10.000000000000"] * 15}],
            binding,
        ),
    )
    monkeypatch.setattr(op, "point_parity", lambda snapshot: None)
    targets = [
        op.CalibrationTargetRow(
            f"{row['row_key']}#D{d:02}",
            row["base_id"],
            row["season"],
            origin,
            d,
            origin.date() + timedelta(days=d),
            Decimal(10),
            Decimal(5),
        )
        for d in range(1, 16)
    ]
    summary, leads, _, _ = op.evaluate(op.calibrate(targets))
    monkeypatch.setattr(op, "S2_COVERAGE", op.digest(summary))
    monkeypatch.setattr(op, "S2_LEADS", op.digest(leads))
    return s5, dataset, harvest


def test_all_phases_replay_and_custody(synthetic_operator, tmp_path, monkeypatch):
    roots = synthetic_operator
    first, second, public = (tmp_path / n for n in ("primary", "replay", "public"))
    for pid, output in enumerate((first, second), 1):
        monkeypatch.setattr(op.os, "getpid", lambda pid=pid: pid)
        op.prepare(*roots, output)
        assert op.load(output / "source-binding-prelabel.json")["label_bytes_read"] is False
        op.run(*roots, output)
    op.publish(first, second, public)
    for name in op.OUTPUT_NAMES:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    for path in public.glob("*.json"):
        op.privacy(op.load(path))
        assert "SYNTHETIC_BASE" not in path.read_text()
    assert (
        op.load(public / "v0.16-s4-forecastops-monitoring-r1.json")["s4_formal_complete"] is False
    )
    with pytest.raises(FileExistsError):
        op.run(*roots, first)
    (second / "monitoring-snapshot.json").write_text("{}")
    with pytest.raises(ValueError, match="DETERMINISTIC_REPLAY_FAILED"):
        op.publish(first, second, tmp_path / "tampered")


def test_contract_and_source_binding_drift(synthetic_operator, tmp_path):
    roots = synthetic_operator
    out = tmp_path / "out"
    op.prepare(*roots, out)
    (out / "source-binding-prelabel.json").write_text("{}")
    with pytest.raises(ValueError, match="SOURCE_BINDING_DRIFT"):
        op.run(*roots, out)
    c = op.load(out / "contract.json")
    c["policy_hash"] = "0" * 64
    (out / "contract.json").write_bytes(canonical(c))
    with pytest.raises(ValueError, match="FORECASTOPS_CONTRACT_DRIFT"):
        op.verify_contract(out)


def test_s2_replay_drift_stops(synthetic_operator, tmp_path, monkeypatch):
    out = tmp_path / "out"
    op.prepare(*synthetic_operator, out)
    monkeypatch.setattr(op, "S2_COVERAGE", "0" * 64)
    with pytest.raises(ValueError, match="S2_INTERVAL_REPLAY_PARITY_FAILED"):
        op.run(*synthetic_operator, out)


def test_current_season_before_filter(synthetic_operator, tmp_path, monkeypatch):
    label = synthetic_operator[1] / "label_zone/exposed_oot-labels.json"
    rows = op.load(label)
    rows.append(dict(rows[0], season="2026-2027"))
    label.write_bytes(canonical(rows))
    monkeypatch.setitem(op.s2.PINS, "full_label_file_hash", op.sha(label.read_bytes()))
    out = tmp_path / "out"
    op.prepare(*synthetic_operator, out)
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        op.run(*synthetic_operator, out)


def test_public_frozen_authority():
    p = op.policy()
    assert p["s2_policy_hash"] == "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
    assert p["s3_policy_hash"] == "950d7d4885c4a96b43bba5ad6b586ee7a424ae86482618a8be22ed272039a422"
    assert p["production_alert_thresholds_established"] is False
    assert p["source_bindings"]["full_label_file_hash"] == op.s2.PINS["full_label_file_hash"]


@pytest.mark.parametrize(
    "value",
    [
        {"base_id": "private"},
        {"row_key": "private"},
        {"actual_kg": "1"},
        {"predictions": ["1"]},
        {"secret": "x"},
        "/private/forbidden",
        "postgresql://forbidden",
    ],
)
def test_privacy(value):
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_DATA_LEAK"):
        op.privacy(value)


def test_label_access_guard(tmp_path):
    path = tmp_path / "label_zone" / "exposed_oot-labels.json"
    path.parent.mkdir()
    path.write_text("[]")
    with op.label_access(None), pytest.raises(ValueError, match="LABEL_ACCESS_FORBIDDEN"):
        path.read_bytes()
    with op.label_access(path):
        assert path.read_bytes() == b"[]"
        with pytest.raises(ValueError, match="LABEL_ACCESS_FORBIDDEN"):
            (path.parent / "train-labels.json").read_bytes()


def test_exclusive_owner_only_output(tmp_path):
    root = tmp_path / "out"
    op.save(root / "x.json", {"x": 1})
    assert (root / "x.json").stat().st_mode & 0o777 == 0o600
    assert root.stat().st_mode & 0o777 == 0o700
    with pytest.raises(FileExistsError):
        op.save(root / "x.json", {"x": 2})
    with pytest.raises(ValueError, match="PRIVATE_OUTPUT_LOCATION_INVALID"):
        op.output_guard(op.REPOSITORY / "output", [])


def test_source_authority_mutation_rejected(monkeypatch):
    original = op.s2.verify_public

    def changed():
        result = original()
        result[next(iter(result))] = "0" * 64
        return result

    monkeypatch.setattr(op.s2, "verify_public", changed)
    with pytest.raises(ValueError):
        op.policy()


def test_no_training_network_db_or_surface():
    for path in (
        op.REPOSITORY / "backend/app/forecast_intelligence/forecast_ops.py",
        Path(op.__file__),
    ):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                assert name not in {
                    "fit",
                    "fit_predict",
                    "fit_model",
                    "fit_ridge_artifact",
                    "predict",
                    "stat",
                    "now",
                    "getmtime",
                }
            if isinstance(node, ast.ImportFrom):
                assert not any(
                    x in (node.module or "")
                    for x in ("sqlalchemy", "fastapi", "mcp", "prospective", "requests")
                )
    assert (
        "forecast_p80"
        not in (op.REPOSITORY / "backend/app/forecast_intelligence/forecast_ops.py").read_text()
    )


def test_cli_error_does_not_leak_paths(capsys, tmp_path):
    assert (
        op.main(
            [
                "PREPARE",
                "--s5-output-root",
                str(tmp_path),
                "--dataset-root",
                str(tmp_path),
                "--harvest-state-root",
                str(tmp_path),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 1
    )
    text = capsys.readouterr().out
    assert str(tmp_path) not in text
    assert json.loads(text)["result"] == "FAIL"


def test_fresh_process_replay(synthetic_operator, tmp_path):
    roots = synthetic_operator
    outputs = []
    for name in ("process_a", "process_b"):
        root = tmp_path / name
        root.mkdir()
        code = (
            "from pathlib import Path; import sys,pytest; "
            "from backend.tests.forecast_intelligence.test_forecast_ops_operator "
            "import synthetic_operator; "
            "from scripts import run_v0_16_s4_forecastops_monitoring as op; "
            "root=Path(sys.argv[1]); mp=pytest.MonkeyPatch(); "
            "roots=synthetic_operator.__wrapped__(mp,root); "
            "op.prepare(*roots,root/'output'); op.run(*roots,root/'output')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(root)], cwd=op.REPOSITORY, capture_output=True
        )
        assert result.returncode == 0
        outputs.append(root / "output")
    op.publish(*outputs, tmp_path / "public")
    assert op.load(outputs[0] / "process-receipt.json") != op.load(
        outputs[1] / "process-receipt.json"
    )
    assert roots


def test_all_locked_metric_parities():
    expected = op.load(op.REPOSITORY / op.s2.EVIDENCE / "exposed-oot-metrics.json")["M1"]
    point = {
        f"H{h}": {
            "daily_wape": expected[f"H{h}_DAILY_WAPE"],
            "cumulative_wape": expected[f"H{h}_CUMULATIVE_WAPE"],
        }
        for h in (7, 15)
    }
    point["H15"].update(daily_mae_kg=expected["DAILY_MAE_KG"], daily_bias_kg=expected["BIAS_KG"])
    op.point_parity({"point_quality": point})
    for horizon, values in point.items():
        for key in values:
            changed = {h: dict(v) for h, v in point.items()}
            changed[horizon][key] = "0"
            with pytest.raises(ValueError, match="LOCKED_SCORING_PARITY_FAILED"):
                op.point_parity({"point_quality": changed})


def test_committed_real_evidence_and_canonical_manifest():
    root = op.REPOSITORY / "docs/v0-16/evidence/forecastops-monitoring-r1"
    manifest = op.load(root / "manifest-r1.json")
    for name, expected in manifest["files"].items():
        raw = (root / name).read_bytes()
        assert op.sha(raw) == expected
        value = op.load(root / name)
        assert raw == canonical(value)
        op.privacy(value)
    evidence = op.load(root / "v0.16-s4-forecastops-monitoring-r1.json")
    assert (evidence["base_count"], evidence["origin_count"], evidence["target_row_count"]) == (
        39,
        8775,
        131625,
    )
    assert evidence["s2_replay_parity"] == evidence["v0_15_metric_parity"] == "PASS"
    assert evidence["s4_formal_complete"] is False
    assert evidence["current_season_actual_read"] is False
    contract = op.load(root / "monitoring-policy-r1.json")
    assert contract["policy"] == op.policy()
    assert contract["policy_hash"] == op.digest(op.policy())
    quality = op.load(root / "point-quality-summary-r1.json")
    op.point_parity({"point_quality": quality["horizons"]})
    complete = op.load(root / "completeness-summary-r1.json")
    for h in (1, 3, 7, 15):
        c = complete[f"H{h}"]
        assert c["matured_origin_count"] == c["scorable_origin_count"] == 8775
        assert c["actual_partial_origin_count"] == c["actual_empty_origin_count"] == 0
        assert c["present_actual_target_row_count"] == 8775 * h
    interval = op.load(root / "interval-quality-summary-r1.json")
    frozen = op.load(op.REPOSITORY / op.S2_ROOT / "coverage-summary-r1.json")
    for h in (7, 15):
        for name, metrics in frozen[f"H{h}"].items():
            assert interval[f"H{h}"][name]["empirical_coverage"] == metrics["empirical_coverage"]
