"""Actual synthetic arithmetic, seals, policy separation and executable CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_retrospective_engine as engine
from backend.research import v019_retrospective_scoring as scoring
from backend.research import v019_synthetic_validation as strict

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def admitted(fixture: str = "DEFAULT") -> engine.AdmittedC0:
    c0 = engine.nominate(engine.Experiment(fixture=fixture))
    return engine.admit(c0, permit=engine.SimulationPermit("C0", c0.sha256))


def generated(fixture: str = "DEFAULT") -> engine.PhaseASeal:
    c0 = admitted(fixture)
    return engine.generate(c0, permit=engine.SimulationPermit("A", c0.sha256))


def evaluated(fixture: str = "DEFAULT") -> dict[str, Any]:
    seal = generated(fixture)
    return scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))


def test_full_numerical_end_to_end() -> None:
    seal = generated()
    report = scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))
    assert report["full_synthetic_end_to_end"] == "PASS"
    assert len(seal.c0.candidates.samples) == 20
    assert len(seal.failures) == 5
    h15 = report["groups"]["RETROSPECTIVE_REPLAY:H15_LOCAL"]["metrics"]
    assert set(h15) == set(strict.METRICS)
    assert h15["DAILY_MAE"]["common_count"] == 6
    assert h15["DAILY_MAE"]["sample_coverage"] == "0.75"
    assert h15["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"] == 4
    assert h15["SEASON_TOTAL_WAPE"]["baseline"]["value"] is None
    assert Decimal(h15["DAILY_MAE"]["baseline"]["value"]) > 0
    control = report["groups"]["SYNTHETIC_COMPLETE_CALENDAR_CONTROL:FULL_SEASON"]["metrics"]
    assert control["SEASON_TOTAL_WAPE"]["baseline"]["value"] is not None
    delta = h15["BASE_BREADTH"]["per_base_delta"]
    assert Decimal(delta["SYNTHETIC-BASE-A"]) < 0
    assert Decimal(delta["SYNTHETIC-BASE-B"]) > 0
    assert report["real_boundaries"]["formally_admitted_c0_count"] == 0


def test_failures_and_profile_are_registered_before_predictions() -> None:
    c0 = engine.nominate(engine.Experiment())
    registration = json.loads(c0.raw)
    assert registration["input_availability"]["SYNTHETIC-BASE-D"] is False
    bad = engine.nominate(engine.Experiment(fixture="INVALID_PROFILE"))
    profiles = json.loads(bad.raw)["registered_profiles"]
    assert profiles["SYNTHETIC-BASE-D"]["validation_labels_used"] is True
    assert profiles["SYNTHETIC-BASE-A"]["validation_labels_used"] is False
    assert {s.profile_sha256 for s in bad.samples if s.base_id.endswith("D")} == {
        strict.digest(profiles["SYNTHETIC-BASE-D"])
    }


def test_report_has_semantic_tables_and_escapes_text() -> None:
    report = evaluated()
    report["report_scope"] = "<script>SYNTHETIC_UNTRUSTED</script>"
    page = scoring.render(report)["report.html"].decode()
    assert "<table>" in page and "<th>" in page and "<td>" in page
    assert "<script>" not in page
    assert "&lt;script&gt;SYNTHETIC_UNTRUSTED&lt;/script&gt;" in page


def test_committed_example_bundle_is_internally_consistent_not_worktree_bound() -> None:
    folder = Path(__file__).resolve().parents[3] / "docs/v0-19/s3/examples/retrospective-engine-r1"
    manifest = json.loads((folder / "manifest.json").read_bytes())
    for name, expected in manifest["file_sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    a = json.loads((folder / "phase-a.json").read_bytes())
    assert strict.digest(a["payload"]) == a["sha256"]
    report = json.loads((folder / "report.json").read_bytes())
    report_hash = report.pop("report_sha256")
    assert strict.digest(report) == report_hash
    assert report["phase_a_sha256"] == a["sha256"]
    assert report["full_synthetic_end_to_end"] == "PASS"
    assert report["real_boundaries"]["formally_admitted_c0_count"] == 0
    # Historical sample code hashes are retained in the artifact, not compared
    # with a future worktree. Current code is exercised by the other CLI tests.


def test_repeated_inputs_all_seals_and_reports_identical() -> None:
    a, b = generated(), generated()
    assert a.raw == b.raw and a.sha256 == b.sha256
    assert evaluated() == evaluated()
    assert a.c0.candidates.raw == admitted().candidates.raw


def test_phase_a_no_label_loader_or_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("LABELS_OR_SCORING_TOUCHED")

    monkeypatch.setattr(scoring, "_labels", forbidden)
    monkeypatch.setattr(scoring, "score", forbidden)
    assert generated().failures


@pytest.mark.parametrize("phase", ["C0", "A", "B"])
@pytest.mark.parametrize("permit", [None, True, {"owner_approved": True}])
def test_no_forged_permissions(phase: str, permit: object) -> None:
    if phase == "C0":
        with pytest.raises(PermissionError):
            engine.admit(engine.nominate(engine.Experiment()), permit=permit)
    elif phase == "A":
        with pytest.raises(PermissionError):
            engine.generate(admitted(), permit=permit)
    else:
        with pytest.raises(PermissionError):
            scoring.score(generated(), permit=permit)


def test_seal_tamper_rejected_before_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    seal = generated()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("LABELS_OPENED")

    monkeypatch.setattr(scoring, "_labels", forbidden)
    bad = replace(seal, sha256="0" * 64)
    with pytest.raises(ValueError, match="SEAL"):
        scoring.score(bad, permit=engine.SimulationPermit("B", bad.sha256))


def test_admission_and_window_integrity() -> None:
    c0 = admitted()
    bad = replace(c0.candidates, samples=c0.candidates.samples[:-1])
    with pytest.raises(ValueError, match="C0"):
        engine.admit(bad, permit=engine.SimulationPermit("C0", bad.sha256))
    seal = generated()
    assert len(seal.full_curves) == 3
    for s, p in zip(seal.predictions.samples, seal.predictions.pairs, strict=True):
        if p.candidate is None:
            assert p.failure and s.base_id == "SYNTHETIC-BASE-D"
            continue
        full = {r.day: r for r in seal.full_curves[s.base_id]["candidate"]}
        assert p.candidate.rows == tuple(full[d] for d in s.dates)
        assert s.issued_at.year == 2002  # NOT backdated to origin in 2000.
    for curves in seal.full_curves.values():
        for start in range(0, 21, 7):
            assert sum(r.kg for r in curves["baseline"][start : start + 7]) == sum(
                r.kg for r in curves["candidate"][start : start + 7]
            )


def test_strict_gate_still_refuses_late_replay() -> None:
    seal = generated("CLEAN")
    labels = scoring._labels(seal)
    result = strict.evaluate_synthetic(
        seal.predictions,
        labels,
        as_of=datetime.fromisoformat("2003-01-01T00:00:00Z"),
        synthetic_authorized=True,
    )
    assert all(g["metrics"]["DAILY_MAE"]["common_count"] == 0 for g in result["groups"].values())
    research = scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))
    assert (
        research["groups"]["RETROSPECTIVE_REPLAY:H15_LOCAL"]["metrics"]["DAILY_MAE"]["common_count"]
        == 8
    )
    assert all(s.issued_at.year == 2002 for s in seal.predictions.samples)


def test_ten_metrics_identical_to_independent_as_issued_arithmetic_control() -> None:
    """Separate fictional oracle ONLY in this test; engine never rewrites clocks."""
    seal = generated()
    labs = {lab.sample_id: lab for lab in scoring._labels(seal)}
    controls = tuple(replace(s, issued_at=s.origin) for s in seal.predictions.samples)
    by_id = {s.sample_id: s for s in controls}
    pairs = tuple(
        replace(
            p,
            baseline=replace(p.baseline, sample_identity_sha256=by_id[p.sample_id].identity_sha256)
            if p.baseline
            else None,
            candidate=replace(
                p.candidate, sample_identity_sha256=by_id[p.sample_id].identity_sha256
            )
            if p.candidate
            else None,
        )
        for p in seal.predictions.pairs
    )
    labels = tuple(
        replace(lab, sample_identity_sha256=by_id[key].identity_sha256) for key, lab in labs.items()
    )
    control = strict.evaluate_synthetic(
        strict.freeze_predictions(controls, pairs, synthetic_authorized=True),
        labels,
        as_of=datetime.fromisoformat("2003-01-01T00:00:00Z"),
        synthetic_authorized=True,
    )
    actual = scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))
    for key, group in actual["groups"].items():
        assert group["metrics"] == control["groups"][key]["metrics"]
        assert group["diagnostics"] == control["groups"][key]["diagnostics"]
        assert (
            group["h15_whole_base_sensitivity"]
            == control["groups"][key]["h15_whole_base_sensitivity"]
        )
    assert all(s.issued_at.year == 2002 for s in seal.predictions.samples)


def test_full_baseline_matches_existing_operational_service() -> None:
    from backend.app.forecast_quality.operational_peak import (
        OperationalPeakForecastRequest,
        forecast_operational_peak,
    )

    seal = generated()
    for s, pair in zip(seal.predictions.samples, seal.predictions.pairs, strict=True):
        if s.window != "H15_LOCAL" or pair.baseline is None:
            continue
        baseline = forecast_operational_peak(
            OperationalPeakForecastRequest(s.base_id, "2000-2001", s.origin.date()),
            {
                "bases": [
                    {
                        "base_id": b.base_id,
                        "canonical_base_name": b.canonical_base_name,
                        "productive_area_mu": str(b.productive_area_mu),
                    }
                    for b in engine._bases()
                ]
            },
            engine._profile()["profile_kg_per_mu_by_7_day_bin"],
        )
        assert [(r.day, r.kg) for r in pair.baseline.rows] == [
            (r.date, r.predicted_kg) for r in baseline.daily_forecast
        ]


def test_context_precision_does_not_change_numerical_report() -> None:
    reference = evaluated()
    with localcontext() as ctx:
        ctx.prec = 5
        assert evaluated() == reference


def test_changed_source_hash_fails_before_label_access(monkeypatch: pytest.MonkeyPatch) -> None:
    seal = generated()
    monkeypatch.setattr(engine, "_source_identity", lambda: {"SYNTHETIC_CHANGED_SOURCE": "0" * 64})

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("LABEL_OPEN_BEFORE_SEAL_VALIDATION")

    monkeypatch.setattr(scoring, "_labels", forbidden)
    with pytest.raises(ValueError, match="C0"):
        scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))


def test_label_payload_drift_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.research import v019_retrospective_labels as labels

    seal = generated()
    original = labels.fixture_payload()
    original["SYNTHETIC-BASE-A"][0] = "999"
    monkeypatch.setattr(labels, "fixture_payload", lambda: original)
    with pytest.raises(ValueError, match="LABEL_FIXTURE_IDENTITY"):
        scoring.score(seal, permit=engine.SimulationPermit("B", seal.sha256))


def test_phase_a_fresh_process_does_not_import_label_fixture() -> None:
    command = """
import sys
from backend.research import v019_retrospective_engine as e
c=e.nominate(e.Experiment())
a=e.admit(c,permit=e.SimulationPermit("C0",c.sha256))
e.generate(a,permit=e.SimulationPermit("A",a.sha256))
assert "backend.research.v019_retrospective_labels" not in sys.modules
assert "backend.research.v019_retrospective_scoring" not in sys.modules
"""
    subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[3],
    )


def test_real_paths_never_enabled() -> None:
    with pytest.raises(PermissionError):
        engine.nominate(engine.Experiment(data_class="REAL"))
    with pytest.raises(PermissionError):
        engine.generate_real_predictions(owner_approved=True, formal_c0=True)
    with pytest.raises(PermissionError):
        engine.nominate(engine.Experiment(fixture="/private/business.xlsx"))


@pytest.mark.parametrize(
    "fixture", ["ZERO_ACTUAL", "MISSING_LABEL", "INVALID_LABEL", "INVALID_PROFILE"]
)
def test_noncomputable_cases_preserve_members(fixture: str) -> None:
    report = evaluated(fixture)
    assert report["registered_count"] == 20
    m = report["groups"]["RETROSPECTIVE_REPLAY:H15_LOCAL"]["metrics"]
    if fixture == "ZERO_ACTUAL":
        assert m["DAILY_WAPE"]["baseline"]["value"] is None
        assert m["DAILY_MAE"]["baseline"]["value"] is not None
        assert m["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"] == 0
    else:
        assert m["NOT_COMPUTABLE_COUNT"]["DAILY_MAE"] > 0


def test_independent_cli_processes_and_reports(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    command = [sys.executable, "-m", "backend.research.v019_retrospective_engine"]
    subprocess.run(
        command + ["stage-a", "--output", str(tmp_path / "a")],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        command
        + ["stage-b", "--seal", str(tmp_path / "a/phase-a.json"), "--output", str(tmp_path / "b")],
        cwd=root,
        check=True,
        capture_output=True,
    )
    report = json.loads((tmp_path / "b/report.json").read_bytes())
    assert report["full_synthetic_end_to_end"] == "PASS"
    for suffix in ("md", "html"):
        text = (tmp_path / f"b/report.{suffix}").read_text()
        assert "DAILY_WAPE" in text and "SYNTHETIC" in text
        assert "baseline" in text and "candidate" in text
    bad = json.loads((tmp_path / "a/phase-a.json").read_bytes())
    bad["sha256"] = "0" * 64
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    result = subprocess.run(
        command
        + ["stage-b", "--seal", str(tmp_path / "bad.json"), "--output", str(tmp_path / "bad-out")],
        cwd=root,
        capture_output=True,
    )
    assert result.returncode != 0 and not (tmp_path / "bad-out").exists()
