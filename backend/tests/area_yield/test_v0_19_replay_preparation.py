"""Synthetic replay rehearsal, with the existing issuance gate left intact."""

import hashlib
import inspect
import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import localcontext
from pathlib import Path

import pytest

from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_replay_preparation import (
    demo,
    demo_labels,
    demo_units,
    evaluate_preparation,
    prepare_predictions,
)
from backend.research.v019_synthetic_validation import METRICS, evaluate_synthetic
from backend.tests.historical_source import historical_bytes

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]


def test_phase_a_has_no_label_argument_and_reuses_frozen_generator():
    assert "labels" not in inspect.signature(prepare_predictions).parameters
    units = demo_units()
    seal = prepare_predictions(units, synthetic_authorized=True)
    assert seal.predictions.pairs[0].baseline.model_id.startswith("OPERATIONAL_PEAK:")
    assert seal.predictions.pairs[0].candidate.model_id == "BIN_CENTER_LINEAR_PER_BIN_MASS_V1"
    for unit, pair in zip(seal.units, seal.predictions.pairs, strict=True):
        assert pair.baseline.rows == tuple(
            r for r in unit.curve.baseline if r.day in unit.sample.dates
        )
    assert json.loads(seal.raw)["labels_read"] is False


def test_ten_metrics_are_exactly_the_existing_evaluator_not_new_arithmetic():
    units = demo_units()
    seal = prepare_predictions(units, synthetic_authorized=True)
    labels = demo_labels(seal)
    at = units[0].computed_at + timedelta(days=400)
    report = evaluate_preparation(seal, labels, as_of=at, synthetic_authorized=True)
    expected = evaluate_synthetic(seal.predictions, labels, as_of=at, synthetic_authorized=True)
    assert report["evaluation"] == expected
    for group in expected["groups"].values():
        assert set(group["metrics"]) == set(METRICS)
        assert group["metrics"]["DAILY_MAE"]["candidate_count"] == 2
        assert group["metrics"]["BASE_BREADTH"]["improved"] == 1
        assert group["metrics"]["BASE_BREADTH"]["worsened"] == 1
    assert len(report["curves_and_peaks"]) == 6


def test_late_replay_keeps_real_computation_clock_and_is_not_scored():
    units = demo_units("RETROSPECTIVE_REPLAY")
    seal = prepare_predictions(units, synthetic_authorized=True)
    for unit in seal.units:
        assert unit.sample.issued_at == unit.computed_at
        assert unit.sample.issued_at.date() > unit.sample.dates[-1]
    report = evaluate_preparation(
        seal,
        demo_labels(seal),
        as_of=units[0].computed_at + timedelta(days=400),
        synthetic_authorized=True,
    )
    for group in report["evaluation"]["groups"].values():
        for metric in METRICS[:7]:
            assert group["metrics"][metric]["common_count"] == 0
            assert group["metrics"][metric]["candidate"]["value"] is None
            assert group["metrics"][metric]["reasons"] == {"UNVERIFIED_AUTHORITY": 2}
    assert report["real_replay_protocol_status"] == "PROPOSED_NOT_EFFECTIVE"
    assert report["strict_pit"] is False


def test_replay_backdating_and_mixed_kinds_are_rejected():
    replay = demo_units("RETROSPECTIVE_REPLAY")
    with pytest.raises(ValueError, match="COMPUTATION_ISSUANCE"):
        prepare_predictions(
            (
                replace(
                    replay[0], sample=replace(replay[0].sample, issued_at=replay[0].sample.origin)
                ),
            ),
            synthetic_authorized=True,
        )
    with pytest.raises(ValueError, match="SEPARATE_REPORTS"):
        prepare_predictions((demo_units()[0], replay[1]), synthetic_authorized=True)


@pytest.mark.parametrize("field", ["raw", "sha256", "units", "predictions"])
def test_corrupt_seal_fails_before_labels_are_touched(field):
    seal = prepare_predictions(demo_units(), synthetic_authorized=True)
    changes = {
        "raw": seal.raw + b" ",
        "sha256": "0" * 64,
        "units": (
            replace(seal.units[0], computed_at=seal.units[0].computed_at + timedelta(seconds=1)),
        ),
        "predictions": replace(seal.predictions, sha256="0" * 64),
    }

    def forbidden_labels():
        raise AssertionError("LABELS_OPENED_BEFORE_SEAL_VALIDATION")
        yield

    with pytest.raises(ValueError):
        evaluate_preparation(
            replace(seal, **{field: changes[field]}),
            forbidden_labels(),
            as_of=seal.units[0].computed_at + timedelta(days=400),
            synthetic_authorized=True,
        )


def test_missing_inputs_and_labels_stay_in_c0_and_missing_is_not_zero():
    units = demo_units()[:2]
    seal = prepare_predictions((units[0], replace(units[1], curve=None)), synthetic_authorized=True)
    assert len(seal.predictions.samples) == 2
    assert seal.predictions.pairs[1].failure == "MISSING_REGISTERED_INPUT"
    report = evaluate_preparation(
        seal,
        (),
        as_of=units[0].computed_at + timedelta(days=400),
        synthetic_authorized=True,
    )
    group = next(iter(report["evaluation"]["groups"].values()))
    assert group["metrics"]["DAILY_MAE"]["candidate_count"] == 2
    assert group["metrics"]["DAILY_MAE"]["not_computable_count"] == 2


def test_zero_labels_preserve_quantity_error_and_no_false_peak_hit():
    seal = prepare_predictions(demo_units()[:1], synthetic_authorized=True)
    lab = demo_labels(seal)[0]
    lab = replace(lab, rows=tuple(replace(row, kg=row.kg * 0) for row in lab.rows))
    report = evaluate_preparation(
        seal,
        (lab,),
        as_of=seal.units[0].computed_at + timedelta(days=400),
        synthetic_authorized=True,
    )
    metrics = next(iter(report["evaluation"]["groups"].values()))["metrics"]
    assert metrics["DAILY_MAE"]["common_count"] == 1
    assert metrics["SINGLE_DAY_PEAK_DATE_MAE"]["reasons"] == {"NO_POSITIVE_ACTUAL_PEAK": 1}


@pytest.mark.parametrize("authorized", [False, True])
def test_real_identity_or_missing_permission_is_denied(authorized):
    unit = demo_units()[0]
    if authorized:
        unit = replace(unit, sample=replace(unit.sample, data_class="REAL"))
    with pytest.raises(PermissionError):
        prepare_predictions((unit,), synthetic_authorized=authorized)


def test_repeat_determinism_order_and_no_input_mutation():
    units = demo_units()
    before = repr(units)
    first = prepare_predictions(units, synthetic_authorized=True)
    second = prepare_predictions(tuple(reversed(units)), synthetic_authorized=True)
    assert first == second
    assert repr(units) == before
    assert demo() == demo()
    assert hashlib.sha256(first.raw).hexdigest() == first.sha256


def test_cli_is_runnable_and_has_no_real_file_loader():
    process = subprocess.run(
        [sys.executable, "-m", "backend.research.v019_replay_preparation", "--demo"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=20,
    )
    assert process.stdout == canonical_bytes(demo())
    bad = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.research.v019_replay_preparation",
            "--input",
            "private.csv",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert bad.returncode == 2


@pytest.mark.parametrize("kind", ["UNKNOWN", "", "AS_ISSUED_FORECAST "])
def test_unknown_prediction_kind_fails(kind):
    with pytest.raises(ValueError, match="UNKNOWN_PREDICTION_KIND"):
        prepare_predictions(
            (replace(demo_units()[0], prediction_kind=kind),), synthetic_authorized=True
        )


def test_missing_timezone_and_empty_registration_fail():
    with pytest.raises(ValueError, match="REGISTERED_C0"):
        prepare_predictions((), synthetic_authorized=True)
    unit = demo_units()[0]
    with pytest.raises(ValueError, match="COMPUTATION_TIMEZONE"):
        prepare_predictions(
            (replace(unit, computed_at=unit.computed_at.replace(tzinfo=None)),),
            synthetic_authorized=True,
        )


def test_renaming_late_replay_as_issued_does_not_bypass_temporal_gate():
    late = replace(demo_units("RETROSPECTIVE_REPLAY")[0], prediction_kind="AS_ISSUED_FORECAST")
    seal = prepare_predictions((late,), synthetic_authorized=True)
    result = evaluate_preparation(
        seal,
        demo_labels(seal),
        as_of=late.computed_at + timedelta(days=400),
        synthetic_authorized=True,
    )
    metrics = next(iter(result["evaluation"]["groups"].values()))["metrics"]
    assert metrics["DAILY_MAE"]["common_count"] == 0
    assert metrics["DAILY_MAE"]["reasons"] == {"UNVERIFIED_AUTHORITY": 1}


@pytest.mark.parametrize("change", ["incomplete", "duplicate", "late", "immature", "wrong_hash"])
def test_invalid_labels_are_retained_as_not_computable(change):
    seal = prepare_predictions(demo_units()[:1], synthetic_authorized=True)
    lab = demo_labels(seal)[0]
    at = seal.units[0].computed_at + timedelta(days=400)
    changes = {
        "incomplete": {"rows": lab.rows[:-1]},
        "duplicate": {"rows": (lab.rows[0],) * len(lab.rows)},
        "late": {"available_at": at + timedelta(seconds=1)},
        "immature": {"mature": False},
        "wrong_hash": {"authority_sha256": "0" * 64},
    }
    report = evaluate_preparation(
        seal, (replace(lab, **changes[change]),), as_of=at, synthetic_authorized=True
    )
    m = next(iter(report["evaluation"]["groups"].values()))["metrics"]["DAILY_MAE"]
    assert m["candidate_count"] == 1
    assert m["not_computable_count"] == 1
    assert m["candidate"]["value"] is None


def test_empty_target_window_is_not_a_crash_or_success():
    unit = demo_units()[0]
    unit = replace(unit, sample=replace(unit.sample, dates=()))
    seal = prepare_predictions((unit,), synthetic_authorized=True)
    report = evaluate_preparation(
        seal,
        demo_labels(seal),
        as_of=unit.computed_at + timedelta(days=400),
        synthetic_authorized=True,
    )
    assert (
        report["curves_and_peaks"][unit.sample.sample_id]["baseline"]["status"] == "NOT_COMPUTABLE"
    )


def test_ambient_decimal_context_does_not_change_demo_bytes():
    expected = canonical_bytes(demo())
    with localcontext() as context:
        context.prec = 6
        assert canonical_bytes(demo()) == expected


def test_duplicate_cohort_and_incompatible_population_fail_before_labels():
    unit = demo_units()[0]
    with pytest.raises(ValueError, match="C0_EXACT_MEMBERSHIP"):
        prepare_predictions((unit, unit), synthetic_authorized=True)
    other = demo_units()[1]
    other = replace(other, sample=replace(other.sample, comparison_family="SYNTHETIC-OTHER"))
    with pytest.raises(ValueError, match="COMPARISON_COHORT_ISOLATION"):
        prepare_predictions((unit, other), synthetic_authorized=True)


def test_machine_evidence_canonical_sources_demo_and_authorization_boundaries():
    path = ROOT / "docs/v0-19/evidence/v0.19-s3-replay-preparation-r1.json"
    raw = path.read_bytes()
    manifest = json.loads(raw)
    assert raw == canonical_bytes(manifest)
    payload = dict(manifest)
    expected = payload.pop("payload_sha256")
    assert hashlib.sha256(canonical_bytes(payload)).hexdigest() == expected
    base = "32602ac7f111a6ad49fd40467d012cc56acf106e"
    assert manifest["base_main_sha"] == base
    for name, pin in manifest["historical_sources"].items():
        assert pin["commit"] == base
        blob = historical_bytes(name, base, root=ROOT)
        assert hashlib.sha256(blob).hexdigest() == pin["sha256"]
        if name.startswith("docs/"):
            assert (ROOT / name).read_bytes() == blob
    for name, sha in manifest["documents_sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha
    assert manifest["synthetic_demo_sha256"] == hashlib.sha256(canonical_bytes(demo())).hexdigest()
    assert manifest["real_authorities"] == "NOT_VERIFIED"
    assert manifest["real_replay_protocol_status"] == "PROPOSED_NOT_EFFECTIVE"
    assert not any(manifest["prohibited_operations"].values())


def test_required_historical_commit_and_hash_fail_closed():
    name = "backend/research/v019_daily_curve.py"
    with pytest.raises(AssertionError, match="commit unavailable"):
        historical_bytes(name, "0" * 40, root=ROOT)
    blob = historical_bytes(name, "32602ac7f111a6ad49fd40467d012cc56acf106e", root=ROOT)
    with pytest.raises(AssertionError):
        assert hashlib.sha256(blob).hexdigest() == "0" * 64
