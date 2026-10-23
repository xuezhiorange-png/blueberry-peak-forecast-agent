"""Fictional quantities only; no private artifact access in CI."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.research import v019_accuracy_models as model
from backend.research import v019_accuracy_study as study
from backend.research.v019_daily_curve import DailyKg


def training() -> tuple[model.TrainingBin, ...]:
    return tuple(
        model.TrainingBin(
            "SYNTHETIC-base",
            date(2023, 7, 1),
            date(2023, 7, 1) + timedelta(days=7 * i),
            Decimal("2"),
            (Decimal("2"),) * 7,
            tuple(Decimal(x) for x in ("1", "2", "3", "4", "5", "6", "7")),
            "a" * 64,
        )
        for i in range(6)
    )


def curve() -> tuple[DailyKg, ...]:
    return tuple(DailyKg(date(2025, 7, 1) + timedelta(days=i), Decimal("2")) for i in range(18))


def test_fit_predict_deterministic_mass_and_no_mutation() -> None:
    rows = training()
    fit = model.fit(rows, evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")
    assert fit == model.fit(rows, evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")
    before = curve()
    result = model.predict(fit, "SYNTHETIC-base", date(2025, 7, 1), before)
    assert result == model.predict(fit, "SYNTHETIC-base", date(2025, 7, 1), before)
    assert before == curve()
    volume, timing = result["VOLUME_CALIBRATION_V1"], result["VOLUME_TIMING_V1"]
    assert len(volume) == len(timing) == 18
    assert volume[0].kg == Decimal("4.000000")
    assert len({r.kg for r in timing[:7]}) > 1
    for i in range(0, 18, 7):
        assert sum(r.kg for r in volume[i : i + 7]) == sum(r.kg for r in timing[i : i + 7])
    assert all(r.kg >= 0 and r.kg.as_tuple().exponent == -6 for r in timing)
    assert timing[:7] == model.window(timing, timing[0].day, 7)


@pytest.mark.parametrize("data_class", ["REAL", "real", "UNKNOWN"])
def test_unadmitted_real_training_denied(data_class: str) -> None:
    with pytest.raises(PermissionError):
        model.fit(training(), evaluation_start=date(2025, 7, 1), data_class=data_class)


@pytest.mark.parametrize(
    "change", ["future", "duplicate", "negative", "nan", "missing", "area", "source", "identity"]
)
def test_invalid_training_rejected(change: str) -> None:
    rows = training()
    if change == "future":
        rows = (replace(rows[0], season_start=date(2025, 7, 1), start=date(2025, 7, 1)),)
    elif change == "duplicate":
        rows += (rows[0],)
    elif change in {"negative", "nan"}:
        rows = (replace(rows[0], actual=(Decimal("-1" if change == "negative" else "NaN"),) * 7),)
    elif change == "missing":
        rows = (replace(rows[0], actual=rows[0].actual[:6]),)
    elif change == "area":
        rows = (replace(rows[0], area_mu=Decimal(0)),)
    elif change == "source":
        rows = (replace(rows[0], source_sha256="bad"),)
    else:
        rows = (replace(rows[0], base_id="unproven-real-base"),)
    with pytest.raises(ValueError):
        model.fit(rows, evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")


def test_seal_tampering_and_time_leakage() -> None:
    fit = model.fit(training(), evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")
    corrupt = {**fit, "global_factor": "99"}
    with pytest.raises(ValueError, match="SEAL"):
        model.predict(corrupt, "SYNTHETIC-base", date(2025, 7, 1), curve())
    with pytest.raises(ValueError):
        model.predict(
            fit,
            "SYNTHETIC-base",
            date(2023, 7, 1),
            tuple(
                DailyKg(date(2023, 7, 1) + timedelta(days=i), r.kg) for i, r in enumerate(curve())
            ),
        )


def test_zero_fallback_and_missing_calendar() -> None:
    fit = model.fit(training(), evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")
    zero = tuple(DailyKg(r.day, Decimal(0)) for r in curve())
    result = model.predict(fit, "SYNTHETIC-unseen", date(2025, 7, 1), zero)
    assert all(r.kg == 0 for rr in result.values() for r in rr)
    with pytest.raises(ValueError):
        model.predict(fit, "SYNTHETIC-base", date(2025, 7, 1), curve()[::2])
    with pytest.raises(ValueError):
        model.window(curve(), curve()[-1].day, 7)


def test_synthetic_end_to_end_keeps_degradation_zero_and_ten_metrics() -> None:
    a, b = study.synthetic(), study.synthetic()
    assert a == b
    assert a["studies"]["2024"]["fit_sha256"] == a["studies"]["2025"]["fit_sha256"]
    comparison = a["studies"]["2025"]["comparison"]
    assert comparison["candidate_count"] == 66
    assert comparison["failures"] == []
    for window, methods in comparison["groups"].items():
        assert len(methods) == 4
        common = set()
        for value in methods.values():
            mm = value["metrics"]
            assert len(mm) == 10
            assert mm["SEASON_TOTAL_WAPE"]["candidate"]["value"] is None
            assert mm["SINGLE_DAY_PEAK_DATE_MAE"]["reasons"]["NO_POSITIVE_ACTUAL_PEAK"] > 0
            common.add(mm["DAILY_WAPE"]["common_members_sha256"])
        assert len(common) == 1
        breadth = methods["VOLUME_TIMING_V1"]["metrics"]["BASE_BREADTH"]
        assert breadth["improved"] == 1
        assert breadth["worsened"] == 2
        if window == "H7_PREFIX":
            assert (
                methods["S2"]["metrics"]["ROLLING_7DAY_PEAK_START_MAE"]["candidate"]["value"] == "0"
            )


def test_joint_cohort_missing_prediction_cannot_improve_denominator() -> None:
    rows = curve()
    member = {
        "base_id": "SYNTHETIC-A",
        "candidate_id": "x",
        "target_start": str(rows[0].day),
        "window": "H7_PREFIX",
    }
    comparison = study.compare(
        {"baseline": {"SYNTHETIC-A": rows}, "missing": {}}, {"SYNTHETIC-A": rows}, [member]
    )
    assert comparison["failures"] == [{"candidate_id": "x", "reason": "INCOMPLETE_CALENDAR"}]
    for m in comparison["groups"]["H7_PREFIX"].values():
        assert m["metrics"]["DAILY_WAPE"]["common_count"] == 0
        assert m["metrics"]["DAILY_WAPE"]["candidate_count"] == 1
        assert m["metrics"]["DAILY_WAPE"]["candidate"]["value"] is None


@pytest.mark.parametrize("total", [0, 1, 2, 7, 1000001])
def test_exact_largest_remainder_and_tie(total: int) -> None:
    result = model.allocate(total, (Decimal(1),) * 7)
    assert sum(result) == total
    assert result == tuple(total // 7 + int(i < total % 7) for i in range(7))


def test_same_fit_under_input_permutation_and_decimal_context() -> None:
    from decimal import localcontext

    fitted = model.fit(training(), evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC")
    assert fitted == model.fit(
        tuple(reversed(training())), evaluation_start=date(2025, 7, 1), data_class="SYNTHETIC"
    )
    expected = model.predict(fitted, "SYNTHETIC-base", date(2025, 7, 1), curve())
    with localcontext() as ctx:
        ctx.prec = 6
        assert expected == model.predict(fitted, "SYNTHETIC-base", date(2025, 7, 1), curve())


def test_source_hash_reader_rejects_changed_bytes(tmp_path: Path) -> None:
    from backend.research.v019_owner_replay import read_bytes

    p = tmp_path / "report.json"
    p.write_bytes(b"changed")
    with pytest.raises(ValueError, match="HASH"):
        read_bytes(p, study.S3_PINS["b/report.json"])


def test_bin_mass_lower_bound_is_not_causal_timing() -> None:
    dates = [str(date(2025, 7, 1) + timedelta(days=i)) for i in range(7)]
    report = {
        "actual_daily": [
            {"base_id": "b", "date": d, "kg": str(i % 2 * 4)} for i, d in enumerate(dates)
        ],
        "daily_predictions": {
            "b": {m: [{"date": d, "kg": "2"} for d in dates] for m in ("baseline", "candidate")}
        },
        "members": [],
        "groups": {},
        "per_base": {},
    }
    registry = {
        "bases": [{"base_id": "b", "canonical_base_name": "SYNTHETIC", "productive_area_mu": "2"}]
    }
    result = study.diagnostics(report, registry)
    r = result["per_base_ranked"][0]
    assert r["actual_kg"] == "12"
    assert r["observed_period_kg_per_mu"] == "6"
    assert r["baseline"]["absolute_error_kg"] == "14"
    assert r["baseline"]["bin_mass_error_lower_bound_kg"] == "2"
    assert r["baseline"]["noncausal_residual_kg"] == "12"
    assert any("NOT a causal" in line for line in result["limits"])


def test_prediction_interface_has_no_evaluation_label_argument() -> None:
    import inspect

    assert set(inspect.signature(model.predict).parameters) == {
        "fitted",
        "base_id",
        "season_start",
        "baseline",
    }


def test_negative_label_cannot_be_scored_and_html_escapes() -> None:
    rows = curve()
    bad = (DailyKg(rows[0].day, Decimal(-1)), *rows[1:])
    m = {
        "candidate_id": "one",
        "base_id": "SYNTHETIC-A",
        "window": "H7_PREFIX",
        "target_start": str(rows[0].day),
    }
    report = study.compare({"baseline": {"SYNTHETIC-A": rows}}, {"SYNTHETIC-A": bad}, [m])
    assert report["failures"][0]["reason"] == "INVALID_VALUE_OR_DUPLICATE_DATE"
    assert "<script>" not in study.markdown_html("# <script>\n| a | b |\n|---|---|\n| c | d |")
    assert "<table>" in study.markdown_html("| a | b |\n|---|---|\n| c | d |")
