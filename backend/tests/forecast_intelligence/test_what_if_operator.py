"""S6 fixed synthetic custody, source isolation and fresh-process replay."""

import ast
import builtins
import io
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.area_yield.v015_research_cohort import canonical, digest
from scripts import run_v0_16_s6_what_if_decision_simulator as op


def test_policy_and_frozen_costs():
    policy = op.policy()
    assert policy["s5_business_loss_policy_hash"] == op.S5_POLICY
    assert tuple(c.contract_hash for c in op.synthetic_contracts()) == op.COST_HASHES
    assert policy["authoritative_kg_inexact_allowed"] is False
    assert policy["authoritative_loss_inexact_allowed"] is False
    assert policy["rounded_utilization_used_for_ranking"] is False
    assert (
        policy["utilization_inexact_exception_scope"]
        == "DAILY_AND_AGGREGATE_CAPACITY_UTILIZATION_ONLY"
    )
    assert policy["initial_backlog_kg"] == "0"
    assert policy["source_evidence_sha256"]


def test_complete_matrix_and_conditional_ranking(tmp_path, monkeypatch):
    primary, replay, public = (tmp_path / n for n in ("primary", "replay", "public"))
    before = op.upstream()
    for pid, out in enumerate((primary, replay), 1):
        monkeypatch.setattr(op.os, "getpid", lambda pid=pid: pid)
        op.prepare(out)
        op.run(out)
        assert out.stat().st_mode & 0o777 == 0o700
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in out.iterdir())
    assert op.upstream() == before
    op.publish(primary, replay, public)
    for name in op.OUTPUT_NAMES:
        assert (primary / name).read_bytes() == (replay / name).read_bytes()
    results = op.load(public / "synthetic-scenario-results-r1.json")["results"]
    groups = op.load(public / "scenario-ranking-summary-r1.json")["comparison_groups"]
    assert len(groups) == 9
    assert sum(len(v) for v in results.values()) == 27
    first_ranks = {}
    for key, rows in results.items():
        assert len(rows) == 3
        assert op.operational(rows[1]) == op.operational(rows[2])
        assert len({r["saved_forecast_hash"] for r in rows}) == 1
        assert len({r["cost_contract_hash"] for r in rows}) == 1
        assert len({r["planning_level"] for r in rows}) == 1
        assert groups[key]["scenario_comparison_status"] == "COMPARABLE"
        assert [r["scenario_rank"] for r in groups[key]["rankings"]] == [1, 2, 3]
        first_ranks[key] = groups[key]["rankings"][0]["scenario_id"]
        for r in rows:
            assert len(r["daily_rows"]) == 15
            assert digest({k: v for k, v in r.items() if k != "result_hash"}) == r["result_hash"]
            assert sum(Decimal(d["scenario_business_loss"]) for d in r["daily_rows"]) == Decimal(
                r["total_business_loss"]
            )
    # The fixture naturally demonstrates conditional rank, not 'more capacity always wins'.
    assert len(set(first_ranks.values())) > 1
    for path in public.glob("*.json"):
        op.privacy(op.load(path))
    with pytest.raises((ValueError, FileExistsError)):
        op.run(primary)
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        op.prepare(primary)
    with pytest.raises(ValueError, match="PUBLIC_OUTPUT_ALREADY_EXISTS"):
        op.publish(primary, replay, public)
    (replay / op.OUTPUT_NAMES[0]).write_bytes(b"{}")
    with pytest.raises(ValueError, match="DETERMINISTIC_REPLAY_FAILED"):
        op.publish(primary, replay, tmp_path / "bad")


def test_no_label_or_private_data_access(tmp_path, monkeypatch):
    original_io, original_builtin = io.open, builtins.open
    opened = []

    def checked(original):
        def guarded(path, *args, **kwargs):
            if isinstance(path, (str, Path)):
                p = str(path)
                assert "label_zone" not in p
                assert "prospective" not in p or str(op.REPOSITORY) in p
                opened.append(p)
            return original(path, *args, **kwargs)

        return guarded

    monkeypatch.setattr(io, "open", checked(original_io))
    monkeypatch.setattr(builtins, "open", checked(original_builtin))
    primary, replay, public = (tmp_path / n for n in ("a", "b", "c"))
    for pid, out in enumerate((primary, replay), 1):
        monkeypatch.setattr(op.os, "getpid", lambda pid=pid: pid)
        op.prepare(out)
        op.run(out)
    op.publish(primary, replay, public)
    assert opened


def test_source_and_contract_drift(tmp_path, monkeypatch):
    out = tmp_path / "out"
    op.prepare(out)
    c = op.load(out / "contract.json")
    c["policy"]["initial_backlog_kg"] = "1"
    (out / "contract.json").write_bytes(canonical(c))
    with pytest.raises(ValueError, match="WHAT_IF_CONTRACT_DRIFT"):
        op.run(out)
    monkeypatch.setattr(op, "S5_POLICY", "0" * 64)
    with pytest.raises(ValueError, match="UPSTREAM_POLICY_DRIFT"):
        op.upstream()


@pytest.mark.parametrize("source", ["cost", "code", "manifest", "s2_policy", "fixture"])
def test_upstream_binding_tamper(source, monkeypatch, tmp_path):
    original = op.load

    def changed(path):
        value = original(path)
        if source == "s2_policy" and path.name == "conformal-policy-r1.json":
            value["policy_hash"] = "0" * 64
        if source == "manifest" and path == op.REPOSITORY / op.S5_ROOT / "manifest-r1.json":
            first = next(iter(value["files"]))
            value["files"][first] = "0" * 64
        if source == "code" and path.name == "business-loss-policy-r1.json":
            # Rehashing an upstream policy does not evade its frozen identity pin.
            value["policy"]["source_evidence_sha256"][
                "backend/app/forecast_intelligence/business_loss.py"
            ] = "0" * 64
        if source == "fixture" and path == op.REPOSITORY / op.FIXTURE:
            value["daily_rows"][0]["point_forecast_kg"] = "81"
        return value

    if source == "fixture":
        out = tmp_path / "out"
        op.prepare(out)
        monkeypatch.setattr(op, "load", changed)
        # Parser altered without changing bound bytes must still be caught by result tests;
        # physical byte drift is simulated by the source hashing layer below.
        original_sha = op.sha
        expected = original_sha((op.REPOSITORY / op.FIXTURE).read_bytes())
        monkeypatch.setattr(
            op, "sha", lambda raw: "0" * 64 if original_sha(raw) == expected else original_sha(raw)
        )
        with pytest.raises(ValueError, match="WHAT_IF_CONTRACT_DRIFT"):
            op.run(out)
    elif source == "cost":
        costs = op.synthetic_contracts()
        monkeypatch.setattr(
            op,
            "synthetic_contracts",
            lambda: (replace(costs[0], c_under_per_kg=Decimal(2)), *costs[1:]),
        )
        with pytest.raises(ValueError, match="UPSTREAM_S5_AUTHORITY_DRIFT"):
            op.upstream()
    else:
        monkeypatch.setattr(op, "load", changed)
        with pytest.raises(ValueError, match="UPSTREAM"):
            op.upstream()


@pytest.mark.parametrize(
    "value",
    [
        {"base_id": "REAL"},
        {"row_key": "x"},
        {"actual_kg": "0"},
        {"secret": "x"},
        {"hierarchy_entity_id": "REAL_COMPANY"},
        "/private/forbidden",
        "postgresql://forbidden",
        "Bearer forbidden",
    ],
)
def test_public_privacy_reject(value):
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_DATA_LEAK"):
        op.privacy(value)


def test_forbidden_dependencies_and_operations():
    for module in (op, op.w):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [a.name for a in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                assert not any(
                    any(
                        token in name.lower()
                        for token in (
                            "sqlalchemy",
                            "fastapi",
                            "mcp",
                            "requests",
                            "httpx",
                            "scipy",
                            "pulp",
                            "ortools",
                            "cvxpy",
                            "catboost",
                            "lightgbm",
                            "label",
                            "forecast_ops",
                            "uncertainty",
                            "run_v0_16_s5",
                        )
                    )
                    for name in names
                )
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
                    "fit_ridge_artifact",
                    "predict",
                    "connect",
                    "register_tool",
                    "add_api_route",
                    "stat",
                    "now",
                }
        assert "forecast_p50" not in Path(module.__file__).read_text()
        assert "forecast_p80" not in Path(module.__file__).read_text()
        assert "forecast_p90" not in Path(module.__file__).read_text()
    assert "initial_backlog_kg" not in op.w.DecisionScenario.__dataclass_fields__
    assert "utilization" not in str(op.policy()["ranking_key"])


def test_fresh_process_phases(tmp_path):
    primary, replay, public = (tmp_path / n for n in ("primary", "replay", "public"))
    for phase in ("PREPARE", "RUN", "REPLAY", "PUBLISH"):
        command = [
            sys.executable,
            "-m",
            "scripts.run_v0_16_s6_what_if_decision_simulator",
            phase,
            "--output",
            str(primary),
            "--replay-output",
            str(replay),
            "--public-output",
            str(public),
        ]
        result = subprocess.run(
            command, cwd=op.REPOSITORY, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["result"] == "PASS"
        assert str(tmp_path) not in result.stdout
    assert op.load(primary / "process-receipt.json") != op.load(replay / "process-receipt.json")
    assert len(op.load(public / "manifest-r1.json")["files"]) == 9


def test_cli_error_and_output_guard(tmp_path, capsys):
    assert op.main(["RUN", "--output", str(tmp_path / "missing")]) == 1
    assert str(tmp_path) not in capsys.readouterr().out
    with pytest.raises(ValueError, match="OUTPUT_LOCATION_INVALID"):
        op.output_guard(op.REPOSITORY / "output")
    with pytest.raises(ValueError, match="OUTPUT_LOCATION_INVALID"):
        op.output_guard(tmp_path, (tmp_path / "inside",))


def test_identical_tampered_copies_cannot_publish_pass(tmp_path, monkeypatch):
    a, b, public = (tmp_path / n for n in ("a", "b", "public"))
    for pid, out in enumerate((a, b), 1):
        monkeypatch.setattr(op.os, "getpid", lambda pid=pid: pid)
        op.prepare(out)
        op.run(out)
    with pytest.raises(ValueError, match="FRESH_PROCESS_REPLAY_REQUIRED"):
        op.publish(a, a, public)
    for out in (a, b):
        result = op.load(out / op.OUTPUT_NAMES[0])
        first = next(iter(result["results"].values()))[0]
        first["total_business_loss"] = "0"
        (out / op.OUTPUT_NAMES[0]).write_bytes(canonical(result))
        receipt = op.load(out / "execution-receipt.json")
        receipt["artifact_hashes"][op.OUTPUT_NAMES[0]] = op.sha(canonical(result))
        (out / "execution-receipt.json").write_bytes(canonical(receipt))
    with pytest.raises(ValueError, match="SYNTHETIC_RESULT_DRIFT"):
        op.publish(a, b, public)
    assert not public.exists()


def test_source_mutation_detected_after_run(tmp_path, monkeypatch):
    out = tmp_path / "out"
    op.prepare(out)
    original = op.acceptance_matrix
    original_upstream = op.upstream

    def altered():
        result = original()
        monkeypatch.setattr(
            op, "upstream", lambda: original_upstream() | {"synthetic_drift": "0" * 64}
        )
        return result

    monkeypatch.setattr(op, "acceptance_matrix", altered)
    with pytest.raises(ValueError, match="SOURCE_ARTIFACT_MUTATION"):
        op.run(out)


def test_committed_evidence_matches_frozen_engine():
    root = op.REPOSITORY / "docs/v0-16/evidence/what-if-decision-simulator-r1"
    manifest = op.load(root / "manifest-r1.json")
    contract = op.load(root / "what-if-policy-r1.json")
    assert contract["policy"] == op.policy()
    assert (
        contract["policy_hash"]
        == digest(op.policy())
        == "c1712c6596a813816eefbcb8d51c7088304549cfcc1899a637dff1b150be6463"
    )
    for name, expected in manifest["files"].items():
        raw = (root / name).read_bytes()
        assert op.sha(raw) == expected
        assert raw == canonical(op.load(root / name))
        op.privacy(op.load(root / name))
    results, groups = op.acceptance_matrix()
    assert op.load(root / "synthetic-scenario-results-r1.json") == {
        "synthetic": True,
        "results": results,
    }
    assert op.load(root / "scenario-ranking-summary-r1.json") == {
        "synthetic": True,
        "comparison_groups": groups,
    }
    evidence = op.load(root / "v0.16-s6-what-if-decision-simulator-r1.json")
    assert evidence["s6_formal_complete"] is False
    assert evidence["version_closeout_started"] is False
    assert evidence["s5_formal_prerequisite_verified"] is True
    s5 = op.load(op.REPOSITORY / op.S5_ROOT / "v0.16-s5-business-loss-contract-r1.json")
    s0 = op.load(
        op.REPOSITORY / "docs/v0-16/evidence/v0.16.0-version-plan-and-scope-freeze-r1.json"
    )
    assert s5["s5_formal_complete"] is False
    assert s0["S6_IMPLEMENTATION_AUTHORIZED"] is False
