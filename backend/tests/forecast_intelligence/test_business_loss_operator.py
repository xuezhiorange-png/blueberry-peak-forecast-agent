"""S5 custody/replay/privacy tests use explicit synthetic sources only."""

import ast
import json
import subprocess
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.v015_research_cohort import canonical
from scripts import run_v0_16_s5_business_loss_contract as op


def install_synthetic(monkeypatch, root):
    origin = datetime.fromisoformat("2025-11-01T17:00:00+08:00")
    rows = [
        {
            "row_key": f"SYNTHETIC_{i:02}",
            "base_id": "SYNTHETIC_BASE",
            "season": "2025-2026",
            "forecast_origin": (origin + timedelta(days=i)).isoformat(),
            "target_dates": [
                (origin.date() + timedelta(days=i + d)).isoformat() for d in range(1, 16)
            ],
        }
        for i in range(30)
    ]
    s5, dataset, harvest = (root / n for n in ("s5", "dataset", "harvest"))
    for path in (s5, dataset, harvest):
        path.mkdir(parents=True, exist_ok=True)
    label = dataset / "label_zone/exposed_oot-labels.json"
    label.parent.mkdir(exist_ok=True)
    if not label.exists():
        label.write_bytes(canonical(rows))
    labels = [["20"] * 15 for _ in rows]
    pins = dict(
        op.s2.PINS,
        full_label_file_hash=op.sha(label.read_bytes()),
        filtered_labelset_hash=op.digest(labels),
    )
    monkeypatch.setattr(op.s2, "PINS", pins)
    monkeypatch.setattr(op.s2, "ORIGINS", len(rows))
    monkeypatch.setattr(op.s2, "TARGETS", len(rows) * 15)
    monkeypatch.setattr(
        op,
        "policy",
        lambda: {"SYNTHETIC": True, "cost_contracts": op.cost_contracts(), "source_bindings": pins},
    )

    class Frozen:
        def labels(self, split, features):
            assert split == "EXPOSED_OOT"
            assert label.read_bytes()
            return labels

    predictions = [{"row_key": r["row_key"], "predictions": ["10.000000000000"] * 15} for r in rows]
    monkeypatch.setattr(
        op,
        "sources",
        lambda *args: (Frozen(), rows, rows, predictions, {"synthetic": op.digest(rows)}),
    )
    targets = [
        op.CalibrationTargetRow(
            f"{r['row_key']}#D{d:02}",
            r["base_id"],
            r["season"],
            datetime.fromisoformat(r["forecast_origin"]),
            d,
            datetime.fromisoformat(r["forecast_origin"]).date() + timedelta(days=d),
            Decimal("10.000000000000"),
            Decimal(20),
        )
        for r in rows
        for d in range(1, 16)
    ]
    coverage, leads, _, _ = op.evaluate(op.calibrate(targets))
    monkeypatch.setattr(op.s4, "S2_COVERAGE", op.digest(coverage))
    monkeypatch.setattr(op.s4, "S2_LEADS", op.digest(leads))
    return s5, dataset, harvest


@pytest.fixture
def synthetic_inputs(monkeypatch, tmp_path):
    return install_synthetic(monkeypatch, tmp_path / "sources")


def test_phases_replay_permissions_privacy(synthetic_inputs, monkeypatch, tmp_path):
    primary, replay, public = (tmp_path / n for n in ("primary", "replay", "public"))
    before = {p: p.read_bytes() for r in synthetic_inputs for p in r.rglob("*.json")}
    for pid, out in enumerate((primary, replay), 1):
        monkeypatch.setattr(op.os, "getpid", lambda pid=pid: pid)
        with op.label_access(None):
            op.prepare(*synthetic_inputs, out)
        assert op.load(out / "source-binding-prelabel.json")["label_bytes_read"] is False
        op.run(*synthetic_inputs, out)
        assert out.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in out.iterdir())
    op.publish(primary, replay, public)
    for name in op.OUTPUT_NAMES:
        assert (primary / name).read_bytes() == (replay / name).read_bytes()
    for path in public.glob("*.json"):
        op.privacy(op.load(path))
        assert "SYNTHETIC_BASE" not in path.read_text()
    assert all(p.read_bytes() == raw for p, raw in before.items())
    summary = op.load(primary / op.OUTPUT_NAMES[1])
    for scenario in summary["results"].values():
        for h, value in scenario.items():
            assert value["common_comparable_row_count"] == value["scorable_origin_count"] * int(
                h[1:]
            )
            assert len({c["comparison_rowset_hash"] for c in value["candidates"].values()}) == 1
    with pytest.raises((FileExistsError, ValueError)):
        op.run(*synthetic_inputs, primary)
    (replay / op.OUTPUT_NAMES[1]).write_text("{}")
    with pytest.raises(ValueError, match="DETERMINISTIC_REPLAY_FAILED"):
        op.publish(primary, replay, tmp_path / "bad-public")


def test_contract_source_and_interval_drift(synthetic_inputs, tmp_path, monkeypatch):
    out = tmp_path / "out"
    op.prepare(*synthetic_inputs, out)
    (out / "source-binding-prelabel.json").write_text("{}")
    with pytest.raises(ValueError, match="SOURCE_BINDING_DRIFT"):
        op.run(*synthetic_inputs, out)
    c = op.load(out / "contract.json")
    c["policy"]["cost_contracts"][0]["c_under_per_kg"] = "2"
    (out / "contract.json").write_bytes(canonical(c))
    with pytest.raises(ValueError, match="BUSINESS_LOSS_CONTRACT_DRIFT"):
        op.verify_contract(out)
    other = tmp_path / "interval-drift"
    op.prepare(*synthetic_inputs, other)
    monkeypatch.setattr(op.s4, "S2_COVERAGE", "0" * 64)
    with pytest.raises(ValueError, match="S2_INTERVAL_REPLAY_PARITY_FAILED"):
        op.run(*synthetic_inputs, other)


def test_current_metadata_before_quantity_and_before_filter(synthetic_inputs, tmp_path):
    label = synthetic_inputs[1] / "label_zone/exposed_oot-labels.json"
    rows = op.load(label)
    rows.append(dict(rows[0], season="2026-2027", quantity="NOT_A_NUMBER"))
    label.write_bytes(canonical(rows))
    out = tmp_path / "out"
    op.prepare(*synthetic_inputs, out)
    with pytest.raises(ValueError, match="FAIL_CURRENT_SEASON_ACTUAL_PRESENT"):
        op.run(*synthetic_inputs, out)


@pytest.mark.parametrize(
    "value",
    [
        {"base_id": "private"},
        {"row_key": "private"},
        {"actual_kg": "1"},
        {"forecast_kg": "1"},
        {"candidate_values": []},
        {"secret": "x"},
        {"target": []},
        "/private/forbidden",
        "postgresql://forbidden",
    ],
)
def test_privacy(value):
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_DATA_LEAK"):
        op.privacy(value)


def test_label_guard_and_root_guard(tmp_path):
    label = tmp_path / "label_zone" / "exposed_oot-labels.json"
    label.parent.mkdir()
    label.write_text("[]")
    with op.label_access(None), pytest.raises(ValueError, match="LABEL_ACCESS_FORBIDDEN"):
        label.read_bytes()
    with pytest.raises(ValueError, match="PRIVATE_OUTPUT_LOCATION_INVALID"):
        op.output_guard(op.REPOSITORY / "private-output", [])


def test_public_authority_and_policy_frozen():
    p = op.policy()
    assert (
        p["s4_forecastops_policy_hash"]
        == "6dfe2c1ac684844af636d936b5797d301e80f015c9e3dd880a102127a169ac1c"
    )
    assert p["s2_policy_hash"] == "f35f2700011f440569c9a0140dc9deb482281d60190e8a601b5a503c79013efd"
    assert [c["c_under_per_kg"] for c in p["synthetic_cost_contracts"]] == ["1", "4", "1"]
    assert [c["c_over_per_kg"] for c in p["synthetic_cost_contracts"]] == ["1", "1", "4"]
    op.privacy(p)
    assert (
        op.load(
            op.REPOSITORY / "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json"
        )["S5_IMPLEMENTATION_AUTHORIZED"]
        is False
    )


@pytest.mark.parametrize("drift", ["s4", "s2", "point", "source"])
def test_upstream_authority_drift(monkeypatch, drift):
    if drift == "s4":
        monkeypatch.setattr(op, "S4_POLICY_HASH", "0" * 64)
    elif drift == "s2":
        monkeypatch.setattr(op.s4, "S2_POLICY", "0" * 64)
    elif drift == "point":
        monkeypatch.setitem(op.s2.PINS, "prediction_hash", "0" * 64)
    else:
        monkeypatch.setattr(
            op.s4,
            "public_authority",
            lambda: (_ for _ in ()).throw(ValueError("UPSTREAM_SOURCE_DRIFT")),
        )
    with pytest.raises(ValueError):
        op.public_authority()


def test_forbidden_behavior_and_no_legacy_surface():
    for path in (
        op.REPOSITORY / "backend/app/forecast_intelligence/business_loss.py",
        Path(op.__file__),
    ):
        tree = ast.parse(path.read_text())
        imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(
            any(
                x in name
                for x in (
                    "sqlalchemy",
                    "fastapi",
                    "httpx",
                    "requests",
                    ".mcp",
                    "lightgbm",
                    "catboost",
                )
            )
            for name in imports
        )
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                name = (
                    n.func.attr
                    if isinstance(n.func, ast.Attribute)
                    else n.func.id
                    if isinstance(n.func, ast.Name)
                    else ""
                )
                assert name not in {
                    "fit",
                    "fit_predict",
                    "fit_model",
                    "fit_ridge_artifact",
                    "predict",
                    "connect",
                    "now",
                    "getmtime",
                }
    public = json.dumps(op.policy())
    assert all(x not in public for x in ("forecast_p50", "forecast_p80", "forecast_p90"))


def test_cli_privacy(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        op, "prepare", lambda *a: (_ for _ in ()).throw(RuntimeError("SENSITIVE_VALUE"))
    )
    args = ["PREPARE"]
    for key in ("s5-output-root", "dataset-root", "harvest-state-root", "output"):
        args += ["--" + key, str(tmp_path / key)]
    assert op.main(args) == 1
    assert json.loads(capsys.readouterr().out) == {
        "result": "FAIL",
        "code": "BUSINESS_LOSS_OPERATOR_FAILED",
    }


def test_fresh_process_replay(tmp_path):
    script = """import sys
from pathlib import Path
from pytest import MonkeyPatch
from backend.tests.forecast_intelligence.test_business_loss_operator import install_synthetic
from scripts import run_v0_16_s5_business_loss_contract as op
with MonkeyPatch.context() as mp:
 root=Path(sys.argv[1]); sources=install_synthetic(mp,root/"sources")
 phase=sys.argv[2]
 args=[phase,"--output",str(root/"primary"),"--replay-output",str(root/"replay"),"--public-output",str(root/"public")]
 for key,path in zip(("s5-output-root","dataset-root","harvest-state-root"),sources):
  args.extend(("--"+key,str(path)))
 raise SystemExit(op.main(args))
"""
    for phase in ("PREPARE", "RUN", "REPLAY", "PUBLISH"):
        r = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), phase],
            cwd=op.REPOSITORY,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stdout
    a, b = (
        op.load(tmp_path / n / "process-receipt.json")["process_id"] for n in ("primary", "replay")
    )
    assert a != b


def test_committed_real_evidence_counts_hashes_and_synthetic_accounting():
    from decimal import localcontext

    root = op.REPOSITORY / "docs/v0-16/evidence/business-loss-contract-r1"
    manifest = op.load(root / "manifest-r1.json")
    for name, expected in manifest["files"].items():
        raw = (root / name).read_bytes()
        value = op.load(root / name)
        assert op.sha(raw) == expected
        assert raw == canonical(value)
        op.privacy(value)
    policy = op.load(root / "business-loss-policy-r1.json")
    assert policy["policy"] == op.policy()
    assert (
        policy["policy_hash"] == "740c0a48506b524ea822b88ad9c5b3443cf3356969026e02cff4a6e1a3c446b7"
    )
    assert policy["policy_hash"] == op.digest(policy["policy"])
    assert op.load(root / "synthetic-cost-contracts-r1.json") == op.cost_contracts()
    summary = op.load(root / "historical-synthetic-loss-summary-r1.json")
    assert (summary["origin_count"], summary["target_row_count"]) == (8775, 131625)
    assert summary["result_hash"] == op.digest(
        {k: v for k, v in summary.items() if k != "result_hash"}
    )
    assert manifest["result_hash"] == summary["result_hash"]
    rowsets = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for cost in op.loss.synthetic_contracts():
            for h, group in summary["results"][cost.contract_id].items():
                horizon = int(h[1:])
                assert group["comparison_status"] == "COMPARABLE"
                assert (
                    group["common_comparable_row_count"]
                    == {1: 8697, 3: 25857, 7: 59241, 15: 122265}[horizon]
                )
                assert (
                    group["common_comparable_row_count"]
                    + group["excluded_non_comparable_row_count"]
                    == 8775 * horizon
                )
                assert (
                    group["common_comparable_row_count"] == group["scorable_origin_count"] * horizon
                )
                assert (
                    rowsets.setdefault(h, group["comparison_rowset_hash"])
                    == group["comparison_rowset_hash"]
                )
                point = group["candidates"][op.loss.POINT]
                for candidate in group["candidates"].values():
                    assert candidate["cost_contract_hash"] == cost.contract_hash
                    assert candidate["comparison_rowset_hash"] == rowsets[h]
                    assert Decimal(
                        candidate["underforecast_loss"]
                    ) == cost.c_under_per_kg * Decimal(candidate["underforecast_kg"])
                    assert Decimal(candidate["overforecast_loss"]) == cost.c_over_per_kg * Decimal(
                        candidate["overforecast_kg"]
                    )
                    assert Decimal(candidate["total_business_loss"]) == Decimal(
                        candidate["underforecast_loss"]
                    ) + Decimal(candidate["overforecast_loss"])
                    assert Decimal(candidate["loss_delta_vs_point"]) == Decimal(
                        candidate["total_business_loss"]
                    ) - Decimal(point["total_business_loss"])
