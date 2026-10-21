"""Hermetic research entry: no business data, loaders, or temporal exemptions."""

import hashlib
import inspect
import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.research import v019_retrospective_entry as entry
from backend.research.v019_daily_curve import DailyKg
from backend.research.v019_synthetic_validation import METRICS

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def registered(kind="RETROSPECTIVE_REPLAY", fixture="PAIR"):
    return entry.register_synthetic(entry.Registration("SYNTHETIC-EXPERIMENT-R1", kind, fixture))


def generated(kind="RETROSPECTIVE_REPLAY", fixture="PAIR"):
    return entry.generate_synthetic(registered(kind, fixture), permit=entry.SyntheticPermit("A"))


def test_repeatable_c0_prediction_report_and_ordered_membership():
    for kind in entry.KINDS:
        first, second = generated(kind), generated(kind)
        assert first == second
        assert first.c0.sha256 == registered(kind).sha256
        report = entry.score_synthetic(first, permit=entry.SyntheticPermit("B"))
        assert report == entry.score_synthetic(second, permit=entry.SyntheticPermit("B"))
        assert json.loads(first.raw)["c0_sha256"] == first.c0.sha256
        assert json.loads(first.c0.raw)["member_identity_sha256"]


def test_phase_a_never_opens_labels(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("PHASE_A_OPENED_LABELS")

    monkeypatch.setattr(entry, "demo_labels", forbidden)
    assert generated().preparation.predictions.pairs
    assert "labels" not in inspect.signature(entry.generate_synthetic).parameters
    assert "labels" not in inspect.signature(entry.register_synthetic).parameters


@pytest.mark.parametrize("field", ["raw", "sha256", "preparation", "c0"])
def test_tampered_seal_rejected_before_label_access(field, monkeypatch):
    seal = generated()
    changes = {
        "raw": seal.raw + b" ",
        "sha256": "0" * 64,
        "preparation": replace(seal.preparation, sha256="0" * 64),
        "c0": replace(seal.c0, sha256="0" * 64),
    }

    def forbidden(*args, **kwargs):
        raise AssertionError("LABELS_OPENED_BEFORE_SEAL_VALIDATION")

    monkeypatch.setattr(entry, "demo_labels", forbidden)
    with pytest.raises(ValueError):
        entry.score_synthetic(
            replace(seal, **{field: changes[field]}), permit=entry.SyntheticPermit("B")
        )


def test_unsealed_c0_is_not_a_prediction_seal():
    with pytest.raises(ValueError, match="PREDICTION_SEAL_REQUIRED"):
        entry.score_synthetic(registered(), permit=entry.SyntheticPermit("B"))


def test_source_nomination_does_not_grant_c0_or_resolve_nine_farms():
    scope = entry.CandidateScope()
    scope.validate()
    assert scope.unresolved_farms == 9
    assert scope.matched_farms == 75
    assert scope.candidate_bases == 39
    assert scope.h7_structural_max == 9672
    assert scope.h15_structural_max == 9360
    assert scope.full_season_admitted == 0
    body = json.loads(registered().raw)
    assert body["real_candidate_admission"] == "BLOCKED_NOT_FORMAL_C0"
    assert "UNRESOLVED_FARM_IMPACT" in body["real_blockers"]
    assert "PHYSICAL_BASIS_NOT_VERIFIED" in body["real_blockers"]
    for field, value in [
        ("unresolved_farms", 0),
        ("matched_farms", 84),
        ("full_season_admitted", 39),
        ("source_sha256", "0" * 64),
    ]:
        with pytest.raises(ValueError, match="SOURCE_NOMINATION_CHANGED"):
            replace(scope, **{field: value}).validate()


def test_actual_late_computation_time_kept_and_never_scored_as_as_issued():
    seal = generated()
    for unit in seal.c0.units:
        assert unit.sample.issued_at == unit.computed_at
        assert unit.computed_at.date() > unit.sample.dates[-1]
    report = entry.score_synthetic(seal, permit=entry.SyntheticPermit("B"))
    assert report["experiment_type"] == "RETROSPECTIVE_REPLAY"
    assert report["clock_provenance"] == "EXPLICIT_SIMULATED_CLOCK"
    for group in report["result"]["evaluation"]["groups"].values():
        assert set(group["metrics"]) == set(METRICS)
        assert group["metrics"]["DAILY_MAE"]["common_count"] == 0
        assert group["metrics"]["DAILY_MAE"]["reasons"] == {"UNVERIFIED_AUTHORITY": 2}


def test_separate_positive_control_preserves_improvement_and_degradation():
    report = entry.score_synthetic(
        generated("AS_ISSUED_FORECAST"), permit=entry.SyntheticPermit("B")
    )
    assert report["historical_status"] == "SYNTHETIC_POSITIVE_CONTROL_NOT_REAL_ISSUANCE"
    for group in report["result"]["evaluation"]["groups"].values():
        assert group["metrics"]["BASE_BREADTH"]["improved"] == 1
        assert group["metrics"]["BASE_BREADTH"]["worsened"] == 1
        assert set(group["metrics"]) == set(METRICS)
        assert group["metrics"]["SEASON_TOTAL_WAPE"]["candidate"]["value"] is None


def test_physical_basis_mismatch_and_missing_input_are_retained():
    for fixture, reason in [
        ("UNVERIFIED_PHYSICAL_BASIS", "PHYSICAL_BASIS_MISMATCH"),
        ("MISSING_INPUT", None),
    ]:
        seal = generated("AS_ISSUED_FORECAST", fixture)
        report = entry.score_synthetic(seal, permit=entry.SyntheticPermit("B"))
        assert len(seal.c0.units) == 4
        for group in report["result"]["evaluation"]["groups"].values():
            assert group["metrics"]["DAILY_MAE"]["candidate_count"] == 2
            assert group["metrics"]["DAILY_MAE"]["common_count"] < 2
            if reason:
                assert group["metrics"]["DAILY_MAE"]["reasons"] == {reason: 2}
        if fixture == "MISSING_INPUT":
            assert any(pair.failure for pair in seal.preparation.predictions.pairs)


def test_horizons_slice_same_support_without_full_season_admission():
    c0 = registered()
    for unit in c0.units:
        assert unit.sample.window in {"H7_PREFIX", "H15_LOCAL"}
        assert len(unit.sample.dates) == (7 if unit.sample.window == "H7_PREFIX" else 15)
        assert unit.sample.dates[0] == unit.sample.origin.date() + timedelta(days=1)
        assert not unit.sample.full_season_registered
        assert unit.curve.support_end == unit.curve.baseline[-1].day
    assert len({unit.curve for unit in c0.units}) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"data_class": "REAL"},
        {"protocol_status": "APPROVED"},
        {"strict_pit": True},
        {"production_eligible": True},
        {"synthetic_clock": False},
        {"experiment_id": "REAL-EXPERIMENT"},
        {"fixture": "/tmp/private.csv"},
        {"kind": "OTHER"},
    ],
)
def test_real_data_and_identity_switches_fail_closed(changes):
    with pytest.raises((ValueError, PermissionError)):
        entry.register_synthetic(replace(entry.Registration("SYNTHETIC-EXPERIMENT-R1"), **changes))


@pytest.mark.parametrize(
    "permit",
    [
        None,
        True,
        {"phase": "B"},
        entry.SyntheticPermit("A"),
        entry.SyntheticPermit("B", enabled=False),
        entry.SyntheticPermit("B", enabled="yes"),
        entry.SyntheticPermit("B", data_class="REAL"),
    ],
)
def test_separate_scoring_permission_before_labels(permit, monkeypatch):
    seal = generated()

    def forbidden(*args, **kwargs):
        raise AssertionError("PERMISSION_FAILURE_OPENED_LABELS")

    monkeypatch.setattr(entry, "demo_labels", forbidden)
    with pytest.raises(PermissionError):
        entry.score_synthetic(seal, permit=permit)


def test_renamed_real_curve_cannot_be_injected_even_with_recomputed_digest():
    c0 = registered()
    unit = c0.units[0]
    curve = replace(
        unit.curve,
        baseline=(DailyKg(unit.curve.support_start, Decimal("123.456")),) + unit.curve.baseline[1:],
    )
    tampered = replace(c0, units=(replace(unit, curve=curve),) + c0.units[1:])
    body = json.loads(c0.raw)
    body["registered_inputs_sha256"] = entry.digest(tampered.units)
    raw = entry.canonical_bytes(body)
    tampered = replace(tampered, raw=raw, sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError, match="C0_SEAL_MISMATCH"):
        entry.generate_synthetic(tampered, permit=entry.SyntheticPermit("A"))
    with pytest.raises(ValueError):
        entry.generate_synthetic(
            replace(c0, units=tuple(reversed(c0.units))), permit=entry.SyntheticPermit("A")
        )


def test_cli_is_demo_only_and_has_no_real_data_loader():
    run = subprocess.run(
        [sys.executable, "-m", "backend.research.v019_retrospective_entry", "--demo"],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(run.stdout)
    assert result["real_scoring_performed"] is False
    assert result["reports"]["RETROSPECTIVE_REPLAY"]["strict_pit"] is False
    rejected = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.research.v019_retrospective_entry",
            "--input",
            "/tmp/private.xls",
        ],
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0


def test_protocol_evidence_canonical_and_sources_are_historical_git_blobs():
    from backend.tests.historical_source import historical_bytes

    root = Path(__file__).resolve().parents[3]
    path = root / "docs/v0-19/evidence/v0.19-s3-retrospective-research-entry-r1.json"
    evidence = json.loads(path.read_bytes())
    assert path.read_bytes() == entry.canonical_bytes(evidence)
    for source, expected in evidence["historical_sources"].items():
        raw = historical_bytes(source, commit=evidence["base_main_sha"])
        assert hashlib.sha256(raw).hexdigest() == expected
    assert evidence["real_scoring_authorized"] is False
    assert evidence["protocol_status"] == "PROPOSED_NOT_EFFECTIVE"


def test_phase_a_permission_and_phase_b_source_drift_fail_closed(monkeypatch):
    c0 = registered()
    for permit in (None, True, entry.SyntheticPermit("B"), entry.SyntheticPermit("A", False)):
        with pytest.raises(PermissionError):
            entry.generate_synthetic(c0, permit=permit)
    seal = generated()
    monkeypatch.setattr(entry, "_source_identity", lambda: {"changed.py": "0" * 64})
    with pytest.raises(ValueError, match="C0_SEAL_MISMATCH"):
        entry.score_synthetic(seal, permit=entry.SyntheticPermit("B"))


def test_backdating_and_profile_hash_drift_cannot_enter_registered_c0():
    c0 = registered()
    unit = c0.units[0]
    for sample in (
        replace(unit.sample, issued_at=unit.sample.origin),
        replace(unit.sample, profile_sha256="0" * 64),
        replace(unit.sample, data_class="REAL"),
    ):
        with pytest.raises(ValueError, match="C0_SEAL_MISMATCH"):
            entry.generate_synthetic(
                replace(c0, units=(replace(unit, sample=sample),) + c0.units[1:]),
                permit=entry.SyntheticPermit("A"),
            )
