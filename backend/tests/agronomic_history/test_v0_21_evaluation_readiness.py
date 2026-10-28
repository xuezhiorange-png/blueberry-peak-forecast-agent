"""S3 synthetic arithmetic, immutable scopes, shared cohorts, and label isolation."""

import copy
import hashlib
import inspect
import json
import subprocess
import sys
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from backend.research import v019_synthetic_validation as legacy
from backend.research import v021_cycle_features as cycle
from backend.research.v021_evaluation_readiness import register, score, seal_predictions
from backend.tests.agronomic_history.v0_21_evaluation_fixture import (
    FAMILIES,
    example,
    inputs,
    payloads,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]
AS_OF = "2025-04-04T08:00:00+08:00"


def run(scenario="COMPLETE"):
    s1, s2, p, r, pred, lab = example(scenario)
    return score(seal_predictions(r, pred), lab, as_of=AS_OF)


def group(result, family):
    return result["groups"]["SYNTHETIC_VALIDATION:" + family]


def member(result, family, day=1):
    return next(
        c
        for c in result["member_ledger"]
        if c["evaluation_family"] == family and c["origin"]["origin_date"] == f"2025-03-{day:02}"
    )


def test_complete_season_peaks_have_independent_dates_quantities_and_vectors():
    r = run()
    c = member(r, FAMILIES[0])
    assert c["actual_peaks"]["single_day"]["date"] == "2025-03-10"
    assert c["actual_peaks"]["rolling7"]["quantity_kg"] == "70.000000"
    assert c["actual_peaks"]["rolling15"]["quantity_kg"] == "92.000000"
    assert c["actual_peaks"]["rolling15"]["start_date"] == "2025-03-02"
    assert c["baseline_peaks"]["rolling15"]["quantity_kg"] == "72.000000"
    assert c["baseline_peaks"]["rolling15"]["start_date"] == "2025-03-09"
    assert c["candidate_peaks"]["rolling15"]["quantity_kg"] == "85.000000"
    assert len(c["actual_peaks"]["rolling15"]["daily"]) == 15
    m = group(r, FAMILIES[0])["metrics"]
    assert m["V0_21_ROLLING_15DAY_PEAK_START_MAE"]["baseline"]["value"] == "7"
    assert m["V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE"]["baseline"]["value"] == "20.000000"
    assert m["V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE"]["candidate"]["value"] == "7.000000"
    assert group(r, FAMILIES[0])["diagnosis"] == "MIXED"


def test_declared_remaining_range_is_distinct_and_reaches_frozen_end():
    r = run()
    c = member(r, FAMILIES[1], 10)
    assert c["dates"][0] == "2025-03-12" and c["dates"][-1] == "2025-04-01"
    assert c["actual_peaks"]["rolling7"]["quantity_kg"] == "52.000000"
    assert c["actual_peaks"]["rolling15"]["quantity_kg"] == "60.000000"
    assert group(r, FAMILIES[1])["metrics"]["SEASON_TOTAL_WAPE"]["common_count"] == 0
    bad = run("INVALID_REMAINING")
    assert group(bad, FAMILIES[1])["metrics"]["DAILY_MAE"]["common_count"] == 0


def test_h7_is_prefix_of_same_h15_version_and_daily_rows_are_aligned():
    _, _, _, registration, predictions, labels = example()
    seal = seal_predictions(registration, predictions)
    r = score(seal, labels, as_of=AS_OF)
    h7 = member(r, FAMILIES[2], 10)
    h15 = member(r, FAMILIES[3], 10)
    assert h7["daily"] == h15["daily"][:7]
    assert h7["totals"]["actual_kg"] == "61.000000"
    assert h15["totals"]["actual_kg"] == "69.000000"
    assert h7["totals"]["baseline_kg"] == "20.000000"
    assert h15["totals"]["baseline_kg"] == "72.000000"
    assert sum(Decimal(d["baseline_signed_error_kg"]) for d in h7["daily"]) == Decimal("-41")


def test_no_relabel_of_h15_as_remaining_or_alternate_h7_version():
    s1, s2, p = inputs()
    p["cases"][2]["evaluation_family"] = FAMILIES[1]
    p["cases"][2]["remaining_start"] = "2025-03-11"
    p["cases"][2]["case_id"] = "SYN-NEW-SCOPE"
    r = register(s1, s2, p)
    c = next(c for c in r["cases"] if c["case_id"] == "SYN-NEW-SCOPE")
    assert c["dates"][0] == "2025-03-11" and c["dates"][-1] == "2025-04-01"
    assert len(c["dates"]) == 22  # A declared remaining scope cannot retain H7 support.
    predictions, _ = payloads(r)
    changed = copy.deepcopy(r)
    next(c for c in changed["cases"] if c["case_id"] == "SYN-NEW-SCOPE")["dates"] = c["dates"][:7]
    with pytest.raises(ValueError, match="REGISTRATION_SEAL_MISMATCH"):
        seal_predictions(changed, predictions)
    with pytest.raises(ValueError):
        example("PREFIX_MISMATCH")


@pytest.mark.parametrize("scenario,length,valid7", [("SHORT_5", 5, False), ("SHORT_10", 10, True)])
def test_short_complete_scope_keeps_independently_computable_metrics(scenario, length, valid7):
    r = run(scenario)
    g = group(r, FAMILIES[0])
    c = member(r, FAMILIES[0])
    assert len(c["daily"]) == length
    assert g["metrics"]["DAILY_MAE"]["common_count"] == 1
    assert g["metrics"]["ROLLING_7DAY_PEAK_QUANTITY_MAE"]["common_count"] == int(valid7)
    assert c["actual_peaks"]["rolling15"]["reason"] == "NO_COMPLETE_15DAY_WINDOW"
    assert g["metrics"]["V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE"]["common_count"] == 0


def test_tied_windows_use_earliest_start_and_vectors_remain_exact():
    r = run("PEAK_TIE")
    c = member(r, FAMILIES[0])
    assert c["actual_peaks"]["single_day"]["date"] == "2025-03-02"
    assert c["actual_peaks"]["rolling7"]["start_date"] == "2025-03-02"
    assert c["actual_peaks"]["rolling15"]["start_date"] == "2025-03-02"
    assert c["actual_peaks"]["rolling15"]["quantity_kg"] == "60.000000"


@pytest.mark.parametrize(
    "scenario",
    [
        "MISSING_DAY",
        "DUPLICATE_DAY",
        "NEGATIVE_KG",
        "INVALID_KG",
        "IMMATURE_LABELS",
        "LATE_SOURCE",
        "LATE_ISSUANCE",
        "BASIS_MISMATCH",
        "MEMBER_MISMATCH",
        "LABEL_CONFLICT",
        "UNKNOWN_CALENDAR_END",
    ],
)
def test_invalid_sources_are_preserved_as_failures_and_never_filled(scenario):
    r = run(scenario)
    all_metrics = [
        v for g in r["groups"].values() for k, v in g["metrics"].items() if k == "DAILY_MAE"
    ]
    assert any(m["not_computable_count"] > 0 for m in all_metrics)
    assert r["candidate_count"] == 6
    assert all(
        m["candidate_count"] - m["common_count"] == m["not_computable_count"] for m in all_metrics
    )


def test_zero_actual_has_quantities_but_no_false_timing_hits():
    r = run("ZERO_ACTUAL")
    for g in r["groups"].values():
        assert g["metrics"]["DAILY_MAE"]["common_count"] == g["candidate_count"]
        assert g["metrics"]["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"] == 0
        assert g["metrics"]["DAILY_WAPE"]["baseline"]["value"] is None
    c = member(r, FAMILIES[0])
    assert c["actual_peaks"]["single_day"]["date"] is None
    assert c["actual_peaks"]["single_day"]["quantity_kg"] == "0.000000"


def test_daily_errors_cannot_be_hidden_by_total_error_cancellation():
    r = run("DAILY_TOTAL_CANCELLATION")
    c = member(r, FAMILIES[2], 10)
    assert [d["baseline_signed_error_kg"] for d in c["daily"][:2]] == ["10.000000", "-10.000000"]
    assert c["totals"]["baseline_absolute_error_kg"] == "0.000000"
    g = group(r, FAMILIES[2])["metrics"]
    assert Decimal(g["DAILY_MAE"]["baseline"]["value"]) > 0
    # The next origin drops the +10 day: its -10 remains. Each origin is retained.
    assert member(r, FAMILIES[2], 11)["totals"]["baseline_absolute_error_kg"] == "10.000000"
    assert g["V0_21_ORIGIN_WINDOW_TOTAL_MAE"]["baseline"]["value"] == "5.000000"
    with localcontext() as ctx:
        ctx.prec = 50
        assert Decimal(g["DAILY_MAE"]["baseline"]["value"]) == Decimal(30) / Decimal(14)


def test_micro_pooled_totals_use_shared_members_and_original_denominators():
    r = run()
    m = group(r, FAMILIES[2])["metrics"]
    daily = m["DAILY_WAPE"]
    total = m["V0_21_ORIGIN_WINDOW_TOTAL_WAPE"]
    assert daily["common_member_ids"] == total["common_member_ids"]
    assert Decimal(daily["baseline"]["numerator"]) == 109
    assert Decimal(total["baseline"]["numerator"]) == 67
    assert Decimal(total["baseline"]["denominator"]) == 113
    assert total["common_count"] == 2 and total["candidate_count"] == 2


def test_different_coverage_retains_full_c0_without_claiming_a_winner():
    r = run("COMMON_COHORT_FAILURES")
    g = group(r, FAMILIES[3])
    m = g["metrics"]["DAILY_MAE"]
    assert m["candidate_count"] == 3 and m["common_count"] == 2
    assert m["baseline_available_count"] == 3 and m["candidate_available_count"] == 2
    assert m["not_computable_count"] == 1 and len(m["exclusions"]) == 1
    assert g["diagnosis"] == "INCONCLUSIVE"


def test_structural_zero_keeps_original_samples_and_is_not_timing_skill():
    r = run()
    c = member(r, FAMILIES[2], 10)
    assert c["actual_peaks"]["rolling7"]["candidate_window_count"] == 1
    assert c["actual_peaks"]["rolling7"]["timing_skill_interpretable"] is False
    assert (
        member(r, FAMILIES[3], 10)["actual_peaks"]["rolling15"]["timing_skill_interpretable"]
        is False
    )
    m = group(r, FAMILIES[2])["metrics"]["ROLLING_7DAY_PEAK_START_MAE"]
    assert m["common_count"] == 2 and Decimal(m["baseline"]["value"]) == 0
    assert m["timing_skill_interpretable"] is False


def test_phase_a_has_no_label_input_and_phase_b_cannot_mutate_prediction_identity():
    *_, registration, predictions, labels = example()
    before = seal_predictions(registration, predictions)
    original = copy.deepcopy(before)
    labels["labels"][0]["rows"][0]["kg"] = "999.000000"
    result = score(before, labels, as_of=AS_OF)
    assert before == original
    assert before == seal_predictions(registration, copy.deepcopy(predictions))
    assert result["prediction_seal_sha256"] == before["seal_sha256"]
    assert "labels" not in inspect.signature(seal_predictions).parameters
    injected = dict(predictions, labels=labels)
    with pytest.raises(ValueError):
        seal_predictions(registration, injected)


def test_seal_tampering_and_real_markers_are_rejected():
    *_, r, p, labels = example()
    seal = seal_predictions(r, p)
    broken = copy.deepcopy(seal)
    broken["registration"]["cases"][0]["dates"][0] = "2025-03-01"
    with pytest.raises(ValueError):
        score(broken, labels, as_of=AS_OF)
    labels["data_class"] = "REAL"
    with pytest.raises(ValueError):
        score(seal, labels, as_of=AS_OF)


@pytest.mark.parametrize(
    "field,value",
    [("season", "2023-2024"), ("variety", "SYN-OTHER"), ("production_system", "EVERGREEN")],
)
def test_individually_distinct_populations_cannot_be_pooled(field, value):
    s1, s2, p = inputs()
    p["cases"][0]["scope"][field] = value
    with pytest.raises(ValueError, match="COHORT_ISOLATION"):
        register(s1, s2, p)


@pytest.mark.parametrize("scenario,diagnosis", [("IMPROVED", "IMPROVED"), ("WORSENED", "WORSENED")])
def test_predeclared_improvement_and_degradation_are_reported_honestly(scenario, diagnosis):
    assert group(run(scenario), FAMILIES[0])["diagnosis"] == diagnosis


def test_old_arithmetic_and_metric_finish_are_actually_reused(monkeypatch):
    from backend.research import v019_research_evaluation as old

    calls = {"errors": 0, "finish": 0}
    oe, of = legacy._errors, old._finish

    def errors(*args, **kwargs):
        calls["errors"] += 1
        return oe(*args, **kwargs)

    def finish(*args, **kwargs):
        calls["finish"] += 1
        return of(*args, **kwargs)

    monkeypatch.setattr(legacy, "_errors", errors)
    monkeypatch.setattr(old, "_finish", finish)
    r = run()
    assert calls["errors"] > 0 and calls["finish"] == 4
    assert set(legacy.METRICS) <= group(r, FAMILIES[0])["metrics"].keys()
    assert r["quantity_basis"] == "RECORDED_INBOUND_WEIGHT" and r["strict_pit_validated"] is False


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("fit_sha256", "0" * 64, "MODEL_IDENTITY_MISMATCH"),
        ("config_sha256", "0" * 64, "MODEL_IDENTITY_MISMATCH"),
        ("area_mu", "51", "AREA_IDENTITY_MISMATCH"),
        ("area_authority_sha256", "0" * 64, "AREA_IDENTITY_MISMATCH"),
        ("source_population_sha256", "0" * 64, "PREDICTION_IDENTITY_MISMATCH"),
        ("prediction_version", "SYN-UNREGISTERED", "PREDICTION_IDENTITY_MISMATCH"),
        ("input_ingested_at", "2025-03-01T09:00:00+08:00", "INPUT_AVAILABLE_AFTER_CUTOFF"),
        ("issued_at", "2025-03-01T07:00:00+08:00", "FEATURE_SNAPSHOT_CUTOFF_AFTER_ISSUANCE"),
    ],
)
def test_exact_prediction_source_version_and_time_identity(field, value, reason):
    *_, registration, predictions, labels = example()
    predictions["curves"][0][field] = value
    sealed = seal_predictions(registration, predictions)
    failures = sealed["curves"][predictions["curves"][0]["curve_id"]]["failures"]
    assert reason in [f["detail"] for f in failures]
    r = score(sealed, labels, as_of=AS_OF)
    assert group(r, FAMILIES[0])["metrics"]["DAILY_MAE"]["not_computable_count"] == 1


@pytest.mark.parametrize("field", ["label_authority_sha256", "source_version"])
def test_label_source_must_be_the_preregistered_independent_authority(field):
    *_, r, p, labels = example()
    labels[field] = "0" * 64
    with pytest.raises(ValueError, match="LABEL_AUTHORITY_OR_REGISTRATION_MISMATCH"):
        score(seal_predictions(r, p), labels, as_of=AS_OF)


@pytest.mark.parametrize(
    "field", ["base", "farm", "subfarm", "plot", "variety", "season", "production_system"]
)
def test_label_member_scope_cannot_be_substituted(field):
    *_, r, p, labels = example()
    labels["labels"][0]["scope"] = dict(labels["labels"][0]["scope"], **{field: "SYN-OTHER"})
    report = score(seal_predictions(r, p), labels, as_of=AS_OF)
    assert "LABEL_IDENTITY_MISMATCH" in [
        f["detail"] for f in report["member_ledger"][0]["failures"]
    ]


def test_actual_missing_or_fractional_precision_is_not_zero():
    *_, r, p, labels = example()
    labels["labels"][0]["rows"].pop(4)
    labels["labels"][1]["rows"][0]["kg"] = "0.0000001"
    result = score(seal_predictions(r, p), labels, as_of=AS_OF)
    assert result["candidate_count"] == 6
    for c in result["member_ledger"][:2]:
        assert c["principal_reason"] is not None and c["daily"] == [] and c["totals"] is None


def test_h7_requires_a_registered_full_h15_prediction_vector():
    s1, s2, p = inputs()
    for curve in p["curves"]:
        if curve["origin_id"].endswith("-10"):
            curve["support_end"] = "2025-03-17"
    r = register(s1, s2, p)
    h7 = next(
        c
        for c in r["cases"]
        if c["evaluation_family"] == FAMILIES[2] and c["origin"]["origin_date"] == "2025-03-10"
    )
    assert "H7_REQUIRES_H15_PREDICTION_SUPPORT" in [f["detail"] for f in h7["failures"]]


@pytest.mark.parametrize("sides", ["baseline", "candidate", "both"])
@pytest.mark.parametrize("offset", [8, 15])
@pytest.mark.parametrize("defect", ["missing", "duplicate", "invalid"])
def test_h7_requires_actual_h15_prefix_and_keeps_failed_c0(sides, offset, defect):
    *_, registration, predictions, labels = example()
    selected = ("baseline", "candidate") if sides == "both" else (sides,)
    bad_date = str(date(2025, 3, 10) + timedelta(days=offset))
    for curve in predictions["curves"]:
        if curve["curve_id"] not in {f"SYN-CURVE-0-10-{side}" for side in selected}:
            continue
        rows = curve["rows"]
        first7 = copy.deepcopy(rows[:7])
        index = next(i for i, row in enumerate(rows) if row["date"] == bad_date)
        if defect == "missing":
            rows.pop(index)
        elif defect == "duplicate":
            rows.insert(index + 1, copy.deepcopy(rows[index]))
        else:
            rows[index]["kg"] = "NaN"
        assert rows[:7] == first7
    sealed = seal_predictions(registration, predictions)
    report = score(sealed, labels, as_of=AS_OF)
    assert report["candidate_count"] == registration["candidate_count"] == 6
    assert [c["case_id"] for c in report["member_ledger"]] == registration["c0_member_ids"]
    expected_reason = (
        "INCOMPLETE_CALENDAR" if defect == "missing" else "INVALID_VALUE_OR_DUPLICATE_DATE"
    )
    for family in FAMILIES[2:]:
        bad = member(report, family, 10)
        good = member(report, family, 11)
        prediction = next(c for c in sealed["cases"] if c["case_id"] == bad["case_id"])
        assert bad["principal_reason"] == expected_reason and bad["daily"] == []
        for side in selected:
            assert prediction[side]["status"] == "NOT_COMPUTABLE"
            assert prediction[side]["peaks"] is None
        if defect == "missing" and family == FAMILIES[2]:
            assert "H7_REQUIRES_H15_PREDICTION_SUPPORT" in [f["detail"] for f in bad["failures"]]
        g = group(report, family)
        assert g["diagnosis"] == "INCONCLUSIVE"
        names = [n for n in legacy.ERROR_METRICS if n != "SEASON_TOTAL_WAPE"] + [
            "V0_21_ORIGIN_WINDOW_TOTAL_MAE",
            "V0_21_ORIGIN_WINDOW_TOTAL_WAPE",
        ]
        for name in names:
            m = g["metrics"][name]
            assert m["candidate_count"] == 2 and m["common_count"] == 1
            assert m["not_computable_count"] == 1
            assert m["common_member_ids"] == [good["case_id"]]
            assert m["exclusions"] == {bad["case_id"]: expected_reason}
        daily = g["metrics"]["DAILY_WAPE"]
        assert Decimal(daily["baseline"]["denominator"]) == (52 if family == FAMILIES[2] else 60)
        assert Decimal(daily["baseline"]["numerator"]) == (54 if family == FAMILIES[2] else 92)
        assert Decimal(daily["candidate"]["numerator"]) == 5


@pytest.mark.parametrize("sides", ["baseline", "candidate", "both"])
def test_h7_h15_do_not_require_seasonal_rows_after_the_complete_15day_prefix(sides):
    *_, registration, predictions, labels = example()
    original = score(seal_predictions(registration, predictions), labels, as_of=AS_OF)
    selected = ("baseline", "candidate") if sides == "both" else (sides,)
    for curve in predictions["curves"]:
        if curve["curve_id"] in {f"SYN-CURVE-0-10-{side}" for side in selected}:
            curve["rows"] = [r for r in curve["rows"] if r["date"] <= "2025-03-25"]
    sealed = seal_predictions(registration, predictions)
    report = score(sealed, labels, as_of=AS_OF)
    for family in FAMILIES[2:]:
        assert member(report, family, 10) == member(original, family, 10)
        assert group(report, family) == group(original, family)
    # The declared remaining season still requires its own full support to April 1.
    assert member(report, FAMILIES[1], 10)["principal_reason"] == "INCOMPLETE_CALENDAR"


def test_h7_prediction_prefix_gate_does_not_require_h15_actual_labels():
    *_, registration, predictions, labels = example()
    h15 = next(
        c
        for c in registration["cases"]
        if c["evaluation_family"] == FAMILIES[3] and c["origin"]["origin_date"] == "2025-03-10"
    )
    lab = next(c for c in labels["labels"] if c["case_id"] == h15["case_id"])
    lab["rows"] = [r for r in lab["rows"] if r["date"] != "2025-03-18"]
    report = score(seal_predictions(registration, predictions), labels, as_of=AS_OF)
    assert group(report, FAMILIES[2])["metrics"]["DAILY_MAE"]["common_count"] == 2
    assert group(report, FAMILIES[3])["metrics"]["DAILY_MAE"]["common_count"] == 1


def test_r2_preserves_every_frozen_r1_synthetic_scenario_result():
    from backend.tests.agronomic_history.v0_21_evaluation_fixture import suite

    expected = json.loads((ROOT / "docs/v0-21/s3/examples/executed-scenarios.json").read_text())
    assert suite() == expected


def test_declared_prediction_failure_remains_in_seal_and_full_c0():
    *_, r, p, labels = example()
    p["curves"][0]["failure"] = "SYNTHETIC_CALCULATOR_UNAVAILABLE"
    p["curves"][0]["rows"] = None
    seal = seal_predictions(r, p)
    assert (
        seal["curves"][p["curves"][0]["curve_id"]]["declared_failure"]
        == "SYNTHETIC_CALCULATOR_UNAVAILABLE"
    )
    result = score(seal, labels, as_of=AS_OF)
    assert result["candidate_count"] == 6
    assert group(result, FAMILIES[0])["metrics"]["DAILY_MAE"]["common_count"] == 0


def test_complete_season_exactly_15_days_keeps_structural_zero_denominator():
    s1, s2, p = inputs()
    p["cases"] = p["cases"][:1]
    p["curves"] = [c for c in p["curves"] if c["origin_id"] == p["cases"][0]["origin_id"]]
    for calendar in p["calendars"]:
        calendar["season_end"] = "2025-03-16"
    for curve in p["curves"]:
        curve["support_end"] = "2025-03-16"
    r = register(s1, s2, p)
    predictions, labels = payloads(r)
    report = score(seal_predictions(r, predictions), labels, as_of=AS_OF)
    m = group(report, FAMILIES[0])["metrics"]["V0_21_ROLLING_15DAY_PEAK_START_MAE"]
    assert m["common_count"] == 1 and m["baseline"]["value"] == "0"
    assert m["timing_skill_interpretable"] is False
    assert list(m["candidate_window_counts"].values()) == [1]


def test_earlier_season_end_or_remaining_start_cannot_change_after_registration():
    *_, r, p, labels = example()
    seal = seal_predictions(r, p)
    changed = copy.deepcopy(seal)
    changed["registration"]["protocol"]["calendars"][0]["season_end"] = "2025-03-24"
    with pytest.raises(ValueError, match="REGISTRATION_SEAL_MISMATCH"):
        score(changed, labels, as_of=AS_OF)


def test_decimal_context_cannot_change_business_results():
    *_, r, p, labels = example()
    expected = score(seal_predictions(r, p), labels, as_of=AS_OF)
    with localcontext() as ctx:
        ctx.prec = 9
        actual = score(seal_predictions(r, p), labels, as_of=AS_OF)
    assert actual == expected


def test_invalid_seal_is_rejected_before_cli_opens_labels(monkeypatch, tmp_path):
    from backend.research import v021_evaluation_readiness as module

    reads = []

    def read(path):
        reads.append(path.name)
        return {"data_class": "REAL"}

    monkeypatch.setattr(module.cycle, "_read", read)
    monkeypatch.setattr(module.Path, "read_bytes", lambda self: b"SYN-invalid-seal")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "s3",
            "score",
            "--seal",
            str(tmp_path / "seal.json"),
            "--labels",
            str(tmp_path / "labels.json"),
            "--as-of",
            AS_OF,
            "--output",
            str(tmp_path / "never-created"),
        ],
    )
    with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
        module.main()
    assert reads == ["seal.json"]
    assert not (tmp_path / "never-created").exists()


def test_three_cli_stages_are_independent_and_repeatable(tmp_path):
    s1, s2, p, r, pred, lab = example()
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    for name, value in (
        ("s1", s1),
        ("s2", s2),
        ("protocol", p),
        ("predictions", pred),
        ("labels", lab),
    ):
        (input_dir / (name + ".json")).write_bytes(cycle.canonical(value) + b"\n")
    results = []
    for i in range(2):
        a, b, c = [tmp_path / f"run-{i}-{s}" for s in ("register", "seal", "score")]

        def call(command, args):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "backend.research.v021_evaluation_readiness",
                    command,
                    *args,
                ],
                check=True,
                capture_output=True,
            )

        call(
            "register",
            [
                "--s1",
                str(input_dir / "s1.json"),
                "--s2",
                str(input_dir / "s2.json"),
                "--protocol",
                str(input_dir / "protocol.json"),
                "--output",
                str(a),
            ],
        )
        call(
            "seal",
            [
                "--registration",
                str(a / "registration.json"),
                "--predictions",
                str(input_dir / "predictions.json"),
                "--output",
                str(b),
            ],
        )
        call(
            "score",
            [
                "--seal",
                str(b / "prediction-seal.json"),
                "--labels",
                str(input_dir / "labels.json"),
                "--as-of",
                AS_OF,
                "--output",
                str(c),
            ],
        )
        results.append((a, b, c))
    for j, name in enumerate(("registration.json", "prediction-seal.json", "evaluation.json")):
        assert (results[0][j] / name).read_bytes() == (results[1][j] / name).read_bytes()
    assert (results[0][2] / "daily-errors.csv").read_bytes() == (
        results[1][2] / "daily-errors.csv"
    ).read_bytes()


ROOT = Path(__file__).resolve().parents[3]


def test_delivered_synthetic_example_is_reproducible_and_file_hashes_match():
    evidence = json.loads(
        (ROOT / "docs/v0-21/evidence/v0.21-s3-evaluation-readiness-r1.json").read_text()
    )
    for path, expected in evidence["synthetic_files_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    base = ROOT / "docs/v0-21/s3/examples"

    def read(name):
        return json.loads((base / (name + ".json")).read_text())

    registration = register(read("s1"), read("s2"), read("protocol"))
    sealed = seal_predictions(registration, read("predictions"))
    result = score(sealed, read("labels"), as_of=AS_OF)
    assert result == read("evaluation")
    assert registration["registration_sha256"] == evidence["registration_sha256"]
    assert sealed["seal_sha256"] == evidence["prediction_seal_sha256"]


def test_old_source_references_are_fixed_git_bytes_not_mutable_worktree_contracts():
    evidence = json.loads(
        (ROOT / "docs/v0-21/evidence/v0.21-s3-evaluation-readiness-r1.json").read_text()
    )
    protected = evidence["protected_sources"]
    for path, expected in protected["sha256"].items():
        raw = subprocess.check_output(
            ["git", "show", protected["git_commit"] + ":" + path], cwd=ROOT
        )
        assert hashlib.sha256(raw).hexdigest() == expected
    assert evidence["owner_authorization"]["s3_implementation"] is True
    assert evidence["owner_authorization"]["signature_created"] is False
    assert all(value is False for value in evidence["boundaries"].values())


def test_executed_scenario_file_keeps_all_declared_cases_and_real_failure_statuses():
    from backend.tests.agronomic_history.v0_21_evaluation_fixture import SCENARIOS

    value = json.loads((ROOT / "docs/v0-21/s3/examples/executed-scenarios.json").read_text())
    assert value["result_sha256"] == cycle.digest(
        {k: v for k, v in value.items() if k != "result_sha256"}
    )
    assert set(value["scenarios"]) == set(SCENARIOS)
    assert value["scenarios"]["PREFIX_MISMATCH"]["status"] == "REJECTED"
    for scenario in ("LATE_SOURCE", "DUPLICATE_DAY", "MISSING_DAY", "BASIS_MISMATCH"):
        assert value["scenarios"][scenario]["failures"]
    g = value["scenarios"]["COMMON_COHORT_FAILURES"]["groups"][
        "SYNTHETIC_VALIDATION:" + FAMILIES[2]
    ]
    assert g["candidate_count"] == 3 and g["diagnosis"] == "INCONCLUSIVE"
