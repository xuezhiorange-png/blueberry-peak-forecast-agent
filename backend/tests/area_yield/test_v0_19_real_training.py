"""Synthetic admission and temporal isolation tests; no private files in CI."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_accuracy_models as models
from backend.research import v019_owner_replay as owner
from backend.research import v019_real_training as training
from backend.research import v019_real_training_cli as runner
from backend.research.v019_daily_curve import DailyKg


def test_fixed_real_sources_are_not_caller_flags(tmp_path: Path) -> None:
    with pytest.raises((FileNotFoundError, ValueError)):
        training.load_training(tmp_path)


def test_numerical_core_keeps_existing_synthetic_results() -> None:
    bins = (
        models.TrainingBin(
            "SYNTHETIC-A",
            date(2023, 7, 1),
            date(2023, 7, 1),
            Decimal(1),
            (Decimal(1),) * 7,
            (Decimal(2),) * 7,
            "a" * 64,
        ),
    )
    public = models.fit(bins, evaluation_start=date(2024, 7, 1), data_class="SYNTHETIC")
    assert public == models._fit_bins(
        bins, evaluation_start=date(2024, 7, 1), data_class="SYNTHETIC"
    )
    with pytest.raises(PermissionError):
        models.fit(bins, evaluation_start=date(2024, 7, 1), data_class="REAL")


def test_complete_bins_and_tail_retention() -> None:
    start = date(2023, 7, 1)
    daily = [
        {
            "base_id": "b",
            "season": "2023-2024",
            "date": str(start + timedelta(days=i)),
            "kg": "2",
            "area_mu": "1",
            "row_sha256": "a" * 64,
        }
        for i in range(10)
    ]
    profile = {
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "validation_labels_used": False,
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {"0": "1", "1": "1"},
    }
    bins, inventory = training.make_bins(daily, profile, ("2023-2024",))
    assert len(bins) == 1
    assert len(inventory) == 2
    assert inventory[-1]["reason"] == "PARTIAL_SEASON_BIN_NOT_TRAINED"
    assert len(inventory[-1]["dates"]) == 3
    assert bins[0].actual == (Decimal(2),) * 7
    assert inventory[0]["sha256"] == bins[0].source_sha256


def test_temporal_experiment_a_does_not_fit_validation_season() -> None:
    start = date(2023, 7, 1)
    a = models.TrainingBin(
        "b", start, start, Decimal(1), (Decimal(1),) * 7, (Decimal(2),) * 7, "a" * 64
    )
    fit = models._fit_bins((a,), evaluation_start=date(2024, 7, 1), data_class="REAL")
    assert fit["global_factor"] == "2"
    late = models.TrainingBin(
        "b",
        date(2024, 7, 1),
        date(2024, 7, 1),
        Decimal(1),
        (Decimal(1),) * 7,
        (Decimal(99),) * 7,
        "b" * 64,
    )
    with pytest.raises(ValueError):
        models._fit_bins((a, late), evaluation_start=date(2024, 7, 1), data_class="REAL")
    final = models._fit_bins((a, late), evaluation_start=date(2025, 7, 1), data_class="REAL")
    assert final["sha256"] != fit["sha256"]


def test_real_prediction_requires_verified_bundle() -> None:
    with pytest.raises(ValueError):
        training.predict_verified({}, {}, {})


def test_s6_retained_zero_and_new_zero_have_distinct_provenance() -> None:
    old = {
        "quantity_status": "CONFIRMED_ZERO",
        "quantity_completeness_status": "AUTHORIZED_ZERO",
        "confirmed_zero_basis": "REUSED_UNCHANGED_MEMBERSHIP_ZERO",
        "mapped_observed_subtotal_kg": "0",
    }
    retained = {
        "source_row_count": "0",
        "zero_basis": "",
        "resolution_reason": "UNCHANGED_EXISTING_AUTHORITY",
    }
    assert training._authorized_zero(old, retained, Decimal(0))
    assert not training._authorized_zero(
        {**old, "quantity_status": "UNKNOWN"}, retained, Decimal(0)
    )
    new = {**retained, "zero_basis": "EXPLICIT_BUSINESS_RULE_NO_HARVEST_RECORD_MEANS_ZERO"}
    assert training._authorized_zero(old, new, Decimal(0))
    assert not training._authorized_zero(old, new, Decimal(1))


def authority_fixture() -> dict[str, Any]:
    bid, season = "SYNTHETIC-b", "2023-2024"
    source = training.SOURCES[season]
    ledger, overlay = [], []
    for i in range(290):
        day = str(date(2023, 7, 1) + timedelta(days=i))
        ledger.append(
            {
                "base_id": bid,
                "season": season,
                "date": day,
                "source_sha256": source,
                "mapped_observed_subtotal_kg": "2",
            }
        )
        overlay.append(
            {
                "base_id": bid,
                "season": season,
                "date": day,
                "authority_eligible_daily": "true",
                "identity_unresolved_conflict": "false",
                "member_expected_count": "1",
                "new_completeness_status": "COMPLETE_MAPPED_MEMBERS",
                "new_quantity_status": "KNOWN_MAPPED_SUBTOTAL",
                "source_coverage_status": "VERIFIED_SEASON_SOURCE_HASH",
                "new_quantity_kg": "2",
            }
        )
    return {
        "ledger": ledger,
        "overlay": overlay,
        "identity": [
            {
                "canonical_base_id": bid,
                "season": season,
                "mapping_status": "EXACT",
                "raw_source_sha256": source,
                "source_identity_sha256": "a" * 64,
                "source_farm_label": "SYNTHETIC-farm",
            }
        ],
        "areas": [
            {
                "base_id": bid,
                "season": season,
                "historical_actual_area_mu": "1",
                "authority_eligible": "true",
                "identity_authority_sha256": training.PINS[
                    f"{training.S1_DIR}/cross-season-base-identity-authority-r1.csv"
                ],
            }
        ],
        "eligibility": [
            {"base_id": bid, "season": season, "strict_training_eligible": "true", "area_mu": "1"}
        ],
        "completeness": [
            {
                "base_id": bid,
                "season": season,
                "season_start_date": "2023-07-01",
                "season_end_date": "2024-04-15",
                "daily_curve_evaluation_eligible": "true",
                "source_identity_status": "IDENTITY_CONFIRMED",
                "member_coverage_complete": "true",
                "unresolved_member_label_count": "0",
                "accepted_source_label_count": "1",
                "complete_daily_sum_kg": "580",
            }
        ],
        "registry": {"bases": [{"base_id": bid, "productive_area_mu": "1"}]},
        "physical": {season: {"event": "RECORDED_INBOUND_WEIGHT", "unit": "kg", "sha256": source}},
    }


def test_exact_admission_and_row_hash_is_not_raw_source_hash() -> None:
    a = training.admit(**authority_fixture())
    assert a["admitted_base_seasons"] == 1
    assert len(a["daily"]) == 290
    assert a["daily_sha256"] != training.SOURCES["2023-2024"]
    assert a == training.admit(**authority_fixture())


@pytest.mark.parametrize(
    "bad", ["physical", "source", "area", "missing", "duplicate", "quantity", "members", "total"]
)
def test_admission_rejects_bad_authority_without_filling(bad: str) -> None:
    data = authority_fixture()
    if bad == "physical":
        data["physical"]["2023-2024"]["event"] = "UNKNOWN"
    elif bad == "source":
        data["ledger"][0]["source_sha256"] = "b" * 64
    elif bad == "area":
        data["areas"][0]["historical_actual_area_mu"] = "2"
    elif bad == "missing":
        data["ledger"].pop()
    elif bad == "duplicate":
        data["ledger"].append(data["ledger"][0])
        with pytest.raises(ValueError, match="DUPLICATE"):
            training.admit(**data)
        return
    elif bad == "quantity":
        data["overlay"][0]["new_quantity_kg"] = "3"
    elif bad == "members":
        data["completeness"][0]["unresolved_member_label_count"] = "1"
    else:
        data["completeness"][0]["complete_daily_sum_kg"] = "579"
    result = training.admit(**data)
    assert result["admitted_base_seasons"] == 0
    assert result["daily"] == []
    assert result["inventory"][0]["reason"]


def test_target_season_never_selected_and_fabricated_bundle_rejected() -> None:
    rows = training._csv(b"season,kg\n2023-2024,2\n2025-2026,SECRET_NOT_TO_DECODE\n")
    assert rows == [{"season": "2023-2024", "kg": "2"}]
    with pytest.raises(ValueError, match="FILES_REQUIRED"):
        training.fit_verified({"input_pins": training.PINS, "admission": {}}, "B")


def test_equivalent_synthetic_admission_fit_four_predictions_score_and_compaction() -> None:
    data = authority_fixture()
    admission = training.admit(**data)
    profile = {
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "validation_labels_used": False,
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {"0": "1"},
    }
    bins, inventory = training.make_bins(admission["daily"], profile, ("2023-2024",))
    assert len(bins) == 41 and inventory[-1]["reason"]
    fitted = models._fit_bins(bins, evaluation_start=date(2024, 7, 1), data_class="REAL")
    baseline = training.curves(
        profile, data["registry"], {"SYNTHETIC-b"}, date(2024, 7, 1), date(2024, 7, 21)
    )
    for m, rr in models._predict_curve(
        fitted, "SYNTHETIC-b", date(2024, 7, 1), baseline["baseline"]["SYNTHETIC-b"]
    ).items():
        baseline[m] = {"SYNTHETIC-b": rr}
    members = [
        {
            "candidate_id": "one",
            "base_id": "SYNTHETIC-b",
            "window": "H15_LOCAL",
            "target_start": "2024-07-01",
            "target_end": "2024-07-15",
        }
    ]
    actual = {
        "SYNTHETIC-b": tuple(
            DailyKg(date(2024, 7, 1) + timedelta(days=i), Decimal(2)) for i in range(21)
        )
    }
    result = runner.evaluate(baseline, actual, members, ["SYNTHETIC-b"], "a" * 64)
    values = result["groups"]["H15_LOCAL"]
    assert len(values["baseline"]["metrics"]) == 10
    assert Decimal(values["baseline"]["metrics"]["DAILY_WAPE"]["candidate"]["value"]) == Decimal(
        "0.5"
    )
    assert (
        Decimal(values["VOLUME_CALIBRATION_V1"]["metrics"]["DAILY_WAPE"]["candidate"]["value"]) == 0
    )
    assert Decimal(values["VOLUME_TIMING_V1"]["metrics"]["DAILY_WAPE"]["candidate"]["value"]) == 0
    assert all(n == 1 for n in result["model_valid_prediction_counts"].values())
    compacted = runner.compact(result)
    ref = compacted["groups"]["H15_LOCAL"]["baseline"]["metrics"]["DAILY_WAPE"][
        "common_member_ids_ref"
    ]
    assert compacted["cohort_member_sets"][ref] == ["one"]


def test_missing_model_keeps_full_actual_denominator() -> None:
    start = date(2024, 7, 1)
    rows = tuple(DailyKg(start + timedelta(days=i), Decimal(2)) for i in range(7))
    members = [
        {
            "candidate_id": "x",
            "base_id": "b",
            "window": "H7_PREFIX",
            "target_start": str(start),
            "target_end": str(start + timedelta(days=6)),
        }
    ]
    result = runner.evaluate(
        {"baseline": {"b": rows}, "missing": {}}, {"b": rows}, members, [], "a" * 64
    )
    assert result["full_C0_actual_denominators"]["H7_PREFIX"]["actual_kg"] == "14"
    assert result["comparison_status"] == "BLOCKED_INCOMPLETE_COMPARISON_NO_OVERALL_WINNER"
    assert result["groups"]["H7_PREFIX"]["baseline"]["metrics"]["DAILY_WAPE"]["common_count"] == 0
    assert result["candidate_count"] == 1


@pytest.mark.parametrize("invalid", ["receipt", "recomputation"])
def test_verification_failure_prevents_target_label_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    import json

    monkeypatch.setattr(runner, "load_a", lambda _: ({}, {}, {"sha256": "a" * 64}))
    (tmp_path / "verification.json").write_text(
        json.dumps(
            {
                "verified": True,
                "prediction_sha256": "bad" if invalid == "receipt" else "a" * 64,
                "code_identity": runner.code_identity(),
            }
        )
    )

    def fail_recomputation(*args: Any) -> None:
        raise ValueError("TAMPERED_PREDICTION")

    monkeypatch.setattr(runner, "verify_run", fail_recomputation)

    def fail_any_read(*args: Any) -> bytes:
        pytest.fail("Target label I/O happened before verification")

    monkeypatch.setattr(owner, "read_bytes", fail_any_read)
    with pytest.raises(ValueError, match="INDEPENDENT_VERIFICATION_REQUIRED|TAMPERED_PREDICTION"):
        runner.score_run(tmp_path, tmp_path, tmp_path)
