"""S1 executable specification on SYNTHETIC values, never a historical scorer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from backend.tests.historical_source import historical_bytes

pytestmark = [pytest.mark.unit, pytest.mark.contract]
ROOT = Path(__file__).resolve().parents[3]
BASE = "47f774bfa823af9849cda7d56668ab81c73548c5"
FILE = ROOT / "docs/v0-19/evidence/v0.19-s1-model-baseline-peak-protocol-r1.json"
D = Decimal


def contract():
    return json.loads(FILE.read_bytes())


def curve(values: Sequence[str]) -> list[tuple[date, Decimal]]:
    return [(date(2000, 1, 1) + timedelta(days=i), D(v)) for i, v in enumerate(values)]


def validate(rows: Sequence[tuple[date, Decimal]], expected: Sequence[date]) -> None:
    if not expected or list(expected) != sorted(set(expected)):
        raise ValueError("INVALID_EXPECTED_CALENDAR")
    if any(b - a != timedelta(days=1) for a, b in zip(expected, expected[1:], strict=False)):
        raise ValueError("INVALID_EXPECTED_CALENDAR")
    if [d for d, _ in rows] != list(expected):
        raise ValueError("INCOMPLETE_OR_DUPLICATE_CALENDAR")
    if any(not q.is_finite() or q < 0 for _, q in rows):
        raise ValueError("INVALID_QUANTITY")


def peaks(rows: Sequence[tuple[date, Decimal]]) -> tuple[date, Decimal, date, Decimal]:
    """Test-local mathematical oracle; calendar completeness is mandatory."""
    if len(rows) < 7:
        raise ValueError("NO_COMPLETE_7DAY_WINDOW")
    validate(rows, [rows[0][0] + timedelta(days=i) for i in range(len(rows))])
    with localcontext() as ctx:
        ctx.prec = 50
        day, quantity = min(rows, key=lambda r: (-r[1], r[0]))
        windows = [
            (rows[i][0], sum((q for _, q in rows[i : i + 7]), D(0))) for i in range(len(rows) - 6)
        ]
        start, total = min(windows, key=lambda r: (-r[1], r[0]))
        return day, quantity, start, total


def synthetic_errors(
    predictions: Sequence[Sequence[str]],
    actuals: Sequence[Sequence[str]],
    *,
    complete_toy_season: bool = False,
):
    """Only literal synthetic examples call this oracle; no file or data adapters."""
    if not predictions or len(predictions) != len(actuals):
        raise ValueError("COMMON_COHORT_REQUIRED")
    with localcontext() as ctx:
        ctx.prec = 50
        absolute = D(0)
        total_error = D(0)
        actual_total = D(0)
        row_count = 0
        peak_sums = [D(0)] * 4
        timing_count = 0
        for pv, av in zip(predictions, actuals, strict=True):
            if len(pv) != len(av):
                raise ValueError("COMMON_COHORT_REQUIRED")
            p, a = curve(pv), curve(av)
            calendar = [day for day, _ in a]
            validate(p, calendar)
            validate(a, calendar)
            pd, pq, ps, pr = peaks(p)
            ad, aq, ast, ar = peaks(a)
            absolute += sum((abs(x[1] - y[1]) for x, y in zip(p, a, strict=True)), D(0))
            at = sum((q for _, q in a), D(0))
            actual_total += at
            total_error += abs(sum((q for _, q in p), D(0)) - at)
            row_count += len(a)
            peak_sums[1] += abs(pq - aq)
            peak_sums[3] += abs(pr - ar)
            if at > 0:
                timing_count += 1
                peak_sums[0] += D(abs((pd - ad).days))
                peak_sums[2] += D(abs((ps - ast).days))
        n = D(len(actuals))
        return {
            "SEASON_TOTAL_WAPE": (
                total_error / actual_total if actual_total and complete_toy_season else None
            ),
            "DAILY_WAPE": absolute / actual_total if actual_total else None,
            "DAILY_MAE": absolute / D(row_count),
            "SINGLE_DAY_PEAK_DATE_MAE": peak_sums[0] / D(timing_count) if timing_count else None,
            "SINGLE_DAY_PEAK_QUANTITY_MAE": peak_sums[1] / n,
            "ROLLING_7DAY_PEAK_START_MAE": peak_sums[2] / D(timing_count) if timing_count else None,
            "ROLLING_7DAY_PEAK_QUANTITY_MAE": peak_sums[3] / n,
            "NO_POSITIVE_ACTUAL_PEAK": len(actuals) - timing_count,
        }


def coverage(candidate: set[str], computable: set[str]) -> tuple[Decimal | None, int]:
    if not computable <= candidate:
        raise ValueError("COHORT_EXPANSION")
    with localcontext() as ctx:
        ctx.prec = 50
        return (
            D(len(computable)) / D(len(candidate)) if candidate else None,
            len(candidate - computable),
        )


def breadth(base_errors: dict[str, tuple[str, str, str]]):
    """Values: baseline absolute error, candidate absolute error, actual mass."""
    improved = sum(D(new) < D(old) for old, new, _ in base_errors.values())
    with localcontext() as ctx:
        ctx.prec = 50
        mass = sum((D(a) for _, _, a in base_errors.values()), D(0))
        good_mass = sum((D(a) for old, new, a in base_errors.values() if D(new) < D(old)), D(0))
        return {
            "bases": len(base_errors),
            "improved": improved,
            "tied": sum(D(new) == D(old) for old, new, _ in base_errors.values()),
            "worsened": sum(D(new) > D(old) for old, new, _ in base_errors.values()),
            "improved_actual_kg_share": good_mass / mass if mass else None,
        }


def test_complete_contract_canonical_and_metrics():
    data = contract()
    assert (
        FILE.read_bytes()
        == (
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode()
    )
    scope = json.loads((ROOT / "docs/v0-19/evidence/v0.19.0-scope-freeze-r1.json").read_bytes())
    assert data["version"] == scope["version"] == "0.19.0"
    assert data["version_name"] == scope["version_name"]
    assert data["new_paths"] == [
        "docs/v0-19/s1/model-baseline-and-historical-evidence-r1.md",
        "docs/v0-19/s1/peak-metrics-and-experiment-protocol-r1.md",
        "docs/v0-19/evidence/v0.19-s1-model-baseline-peak-protocol-r1.json",
        "backend/tests/area_yield/test_v0_19_s1_protocol.py",
    ]
    assert list(data["metrics"]) == sorted(scope["metrics"])
    assert set(data["model_matrix"]) == set(scope["model_families"])
    assert all(
        row["source_paths"] and row["comparability_limit"] for row in data["model_matrix"].values()
    )
    assert data["base_main_sha"] == BASE
    assert data["task_id"] == "V0_19_S1_MODEL_BASELINE_AND_PEAK_ERROR_PROTOCOL_R1"
    for metric in data["metrics"].values():
        assert metric["formula"] and metric["unit"] and metric["denominator"]
        assert metric["undefined"] and metric["aggregation"]
    assert len(data["metrics"]) == 10


def test_all_bound_sources_and_frozen_s0_bytes():
    data = contract()
    for path, expected in data["source_evidence_sha256"].items():
        raw = (
            historical_bytes(path, BASE, root=ROOT)
            if path.startswith("backend/app/")
            else (ROOT / path).read_bytes()
        )
        assert hashlib.sha256(raw).hexdigest() == expected, path
    for path, expected in data["document_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert data["source_read_policy"] == {
        "frozen_documents": "CURRENT_WORKTREE_RAW_BYTES",
        "historical_runtime_source": "FIXED_BASE_MAIN_GIT_BLOB",
    }
    assert data["s0_binding"]["merge_sha"] == BASE
    assert data["s0_binding"]["pr"] == 734
    assert data["s0_binding"]["main_ci_run_id"] == 39215132754
    gate = data["delivery_gate_observed"]
    assert gate["head_sha"] == BASE
    assert gate["run_id"] == data["s0_binding"]["main_ci_run_id"]
    assert gate["event"] == "push" and gate["attempt"] == 1
    assert gate["status"] == "completed" and gate["conclusion"] == "success"
    assert gate["successful_jobs"] == [
        "frontend-e2e",
        "frontend-static",
        "frontend-unit",
        "full-suite-canary",
    ]
    assert len(gate["skipped_jobs"]) == 8
    assert data["s0_binding"]["ci_conclusion_at_preparation"] == "IN_PROGRESS_NOT_YET_ACCEPTED"


def test_authorization_does_not_grant_experiments_or_formal_completion():
    data = contract()
    assert {k for k, v in data["governance"].items() if v is True} == {
        "owner_s1_authorized",
        "parallel_local_preparation_authorized",
        "stop_after_draft_exact_head_ci",
    }
    assert all(v is False for v in data["execution"].values())
    assert data["delivery_gate"] == "S0_POSTMERGE_CI_SUCCESS_BEFORE_COMMIT_PUSH_PR"
    assert data["scientific_limits"]["strict_pit"] is False
    assert data["scientific_limits"]["prospective_accuracy_validated"] is False
    assert data["scientific_limits"]["business_accuracy_threshold"] is None
    assert data["scientific_limits"]["m1_wape_is_operational_peak_accuracy"] is False
    assert data["scientific_limits"]["exposed_2025_2026_is_blind_oot"] is False


def test_baseline_candidate_and_comparability_are_preregistered():
    rules = contract()["preregistration"]
    assert rules["primary_baseline"] == "OPERATIONAL_PEAK:AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
    assert rules["max_candidates"] == 1
    assert rules["candidate_method"] == "NOT_SELECTED_S2_SEPARATE_AUTHORIZATION_REQUIRED"
    assert rules["parameter_search"] is False
    assert rules["selection_basis"] == "STRUCTURAL_SYNTHETIC_CONSTRAINTS_NOT_OBSERVED_ERRORS"
    assert rules["mass_conservation_scope"] == "EACH_SEASON_ANCHORED_BIN_ON_DECLARED_SUPPORT"
    assert rules["partial_query_renormalization"] is False
    assert rules["freeze_before_label_access"] is True
    assert rules["cross_family_ranking"] is False
    assert rules["missing_authority"] == "BLOCKED"
    assert rules["statistical_significance_claim"] is False
    assert rules["results"] == "NOT_EXECUTED"
    assert "origin" in contract()["comparison_key"]
    assert "physical_basis" in contract()["comparison_key"]
    assert "label_authority_hash" in contract()["comparison_key"]


def test_historical_findings_remain_separate_and_negative_results_visible():
    facts = contract()["historical_evidence"]
    assert facts["v08"]["cohorts"] == [39, 30]
    assert facts["v08"]["errors_additive"] is False
    assert facts["v13"]["peak_timing"] == "NOT_SUPPORTED"
    assert facts["v15_s3"]["leader"] == "NO_CLEAR_LEADER"
    assert facts["v15_s3"]["origin_counts"] == [4125, 6028, 9867]
    assert facts["v15_s5"]["origin_counts"] == [3705, 5412, 8775]
    assert facts["v15_s5"]["quantity"] == "SUPPORTED_SHORT_TERM_HISTORICAL_SCOPE"
    assert D(facts["v15_s5"]["oot_rolling7_start_mae_delta_days"]) > 0
    closeout = (ROOT / "docs/v0-15/v0.15.0-closeout.md").read_text()
    for key in ("oot_h7_daily_wape_m1", "oot_h15_daily_wape_m1"):
        assert facts["v15_s5"][key] in closeout
    assert facts["v18"]["engineering_acceptance_proves_accuracy"] is False


def test_temporal_shift_cancels_total_error_but_not_daily_or_peak_errors():
    a = ["9"] + ["1"] * 14
    p = ["1", "9"] + ["1"] * 13
    assert synthetic_errors([p], [a])["SEASON_TOTAL_WAPE"] is None
    result = synthetic_errors([p], [a], complete_toy_season=True)
    assert result["SEASON_TOTAL_WAPE"] == 0
    with localcontext() as ctx:
        ctx.prec = 50
        assert result["DAILY_WAPE"] == D(16) / D(23)
        assert result["DAILY_MAE"] == D(16) / D(15)
    assert result["SINGLE_DAY_PEAK_DATE_MAE"] == 1
    assert result["SINGLE_DAY_PEAK_QUANTITY_MAE"] == 0


def test_pooled_wape_is_not_mean_base_percentage_and_total_is_not_daily_wape():
    result = synthetic_errors(
        [["2"] * 7, ["10"] * 7],
        [["1"] * 7, ["10"] * 7],
        complete_toy_season=True,
    )
    with localcontext() as ctx:
        ctx.prec = 50
        assert result["DAILY_WAPE"] == D(1) / D(11)
        assert result["SEASON_TOTAL_WAPE"] == D(1) / D(11)
    assert result["DAILY_MAE"] == D("0.5")
    assert result["DAILY_WAPE"] != D("0.5")
    assert result["SINGLE_DAY_PEAK_QUANTITY_MAE"] == D("0.5")
    assert result["ROLLING_7DAY_PEAK_QUANTITY_MAE"] == D("3.5")


def test_zero_prediction_with_positive_actual_is_not_excluded_from_peak_timing():
    a = ["0"] * 8 + ["10"] + ["0"] * 6
    result = synthetic_errors([["0"] * 15], [a])
    assert result["SINGLE_DAY_PEAK_DATE_MAE"] == 8
    assert result["ROLLING_7DAY_PEAK_START_MAE"] == 2
    assert result["NO_POSITIVE_ACTUAL_PEAK"] == 0


def test_earliest_tie_and_h7_prefix_not_rolling_max():
    rows = curve(["0"] * 7 + ["10"] * 8)
    day, quantity, start, total = peaks(rows)
    assert day == date(2000, 1, 8) and quantity == 10
    assert start == date(2000, 1, 8) and total == 70
    assert sum(q for _, q in rows[:7]) == 0
    assert len(rows) - 6 == 9
    assert peaks(curve(["1"] * 15)) == (date(2000, 1, 1), D(1), date(2000, 1, 1), D(7))


def test_peak_quantity_evaluates_each_own_peak_not_quantity_on_actual_peak_date():
    a = ["10"] + ["0"] * 14
    p = ["0"] * 8 + ["20"] + ["0"] * 6
    result = synthetic_errors([p], [a])
    assert result["SINGLE_DAY_PEAK_DATE_MAE"] == 8
    assert result["SINGLE_DAY_PEAK_QUANTITY_MAE"] == 10
    assert result["ROLLING_7DAY_PEAK_START_MAE"] == 2
    assert result["ROLLING_7DAY_PEAK_QUANTITY_MAE"] == 10


def test_zero_actual_keeps_quantity_errors_but_no_fake_peak_timing_hit():
    result = synthetic_errors([["1"] * 7], [["0"] * 7])
    assert result["DAILY_WAPE"] is result["SEASON_TOTAL_WAPE"] is None
    assert result["DAILY_MAE"] == 1
    assert result["SINGLE_DAY_PEAK_DATE_MAE"] is None
    assert result["ROLLING_7DAY_PEAK_START_MAE"] is None
    assert result["SINGLE_DAY_PEAK_QUANTITY_MAE"] == 1
    assert result["ROLLING_7DAY_PEAK_QUANTITY_MAE"] == 7
    assert result["NO_POSITIVE_ACTUAL_PEAK"] == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unsorted", "nan", "negative"])
def test_invalid_calendar_or_quantity_never_silently_zero_filled(mutation):
    rows = curve(["1"] * 15)
    expected = [day for day, _ in rows]
    if mutation == "missing":
        rows.pop(7)
    elif mutation == "duplicate":
        rows[7] = rows[6]
    elif mutation == "unsorted":
        rows.reverse()
    else:
        rows[7] = (rows[7][0], D("NaN" if mutation == "nan" else "-1"))
    with pytest.raises(ValueError):
        validate(rows, expected)


def test_incomplete_seven_day_and_nonconsecutive_expected_calendar_fail():
    with pytest.raises(ValueError, match="NO_COMPLETE_7DAY_WINDOW"):
        peaks(curve(["1"] * 6))
    rows = curve(["1"] * 8)
    rows.pop(3)
    with pytest.raises(ValueError):
        validate(rows, [day for day, _ in rows])


def test_decimal_precision_no_float_intermediate_or_display_rounding():
    a = ["0.000000000001"] * 7
    p = ["0.000000000002"] * 7
    result = synthetic_errors([p], [a])
    assert result["DAILY_WAPE"] == 1
    assert result["DAILY_MAE"] == D("0.000000000001")
    high_precision = curve(["1", "1.00000000000000000000000000001"] + ["0"] * 5)
    assert peaks(high_precision)[0] == date(2000, 1, 2)
    share = breadth({"SYNTHETIC-A": ("2", "1", "1"), "SYNTHETIC-B": ("1", "2", "2")})[
        "improved_actual_kg_share"
    ]
    with localcontext() as ctx:
        ctx.prec = 50
        assert share == D(1) / D(3)


def test_coverage_empty_and_metric_specific_not_computable_counts():
    assert coverage({"SYNTHETIC-A", "SYNTHETIC-B"}, {"SYNTHETIC-A"}) == (D("0.5"), 1)
    assert coverage(set(), set()) == (None, 0)
    with pytest.raises(ValueError, match="COHORT_EXPANSION"):
        coverage({"SYNTHETIC-A"}, {"SYNTHETIC-B"})


def test_base_breadth_not_confused_with_row_count_or_volume_share():
    result = breadth(
        {
            "SYNTHETIC-A": ("10", "9", "90"),
            "SYNTHETIC-B": ("1", "2", "10"),
            "SYNTHETIC-C": ("0", "0", "0"),
        }
    )
    assert result == {
        "bases": 3,
        "improved": 1,
        "tied": 1,
        "worsened": 1,
        "improved_actual_kg_share": D("0.9"),
    }
    assert breadth({"SYNTHETIC-ZERO": ("1", "0", "0")})["improved_actual_kg_share"] is None


def test_repeated_origin_target_instances_are_not_deduplicated():
    p, a = ["2"] * 7, ["1"] * 7
    first = synthetic_errors([p], [a])
    repeated = synthetic_errors([p, p], [a, a])
    assert repeated == {**first, "NO_POSITIVE_ACTUAL_PEAK": 0}
    assert contract()["weighting"]["target_date_deduplication"] is False


def test_historical_hash_reader_fails_closed():
    with pytest.raises((ValueError, AssertionError, RuntimeError)):
        historical_bytes("../AGENTS.md", BASE, root=ROOT)


@pytest.mark.parametrize(
    "commit,path",
    [
        ("0" * 40, "AGENTS.md"),
        (BASE, "backend/ABSENT-SYNTHETIC-source.py"),
        ("HEAD", "AGENTS.md"),
    ],
)
def test_unavailable_or_mutable_historical_source_fails(commit, path):
    with pytest.raises(AssertionError):
        historical_bytes(path, commit, root=ROOT)


def test_source_digest_corruption_is_detected_without_updating_expected():
    data = contract()
    path = "backend/app/forecast_quality/operational_peak.py"
    original = historical_bytes(path, BASE, root=ROOT)
    expected = data["source_evidence_sha256"][path]
    assert hashlib.sha256(original).hexdigest() == expected
    assert hashlib.sha256(original + b"\nSYNTHETIC_CORRUPTION").hexdigest() != expected
    assert hashlib.sha256(original).hexdigest() != "0" * 64


def test_every_model_source_is_bound_and_versioned():
    data = contract()
    for family in data["model_matrix"].values():
        assert family["identity"] and family["fit_state"]
        assert all(path in data["source_evidence_sha256"] for path in family["source_paths"])


def comparable(left: dict[str, str], right: dict[str, str]) -> None:
    # Model identity is recorded on each arm, not forced equal. Shared authority
    # and an explicitly approved comparison family must agree before pairing.
    for key in (
        "comparison_family",
        "entity",
        "origin",
        "physical_basis",
        "label_hash",
        "window",
        "source_hash",
        "area_basis",
        "split",
        "training_cutoff",
    ):
        if not left.get(key) or left.get(key) != right.get(key):
            raise ValueError("INCOMPARABLE_" + key)


@pytest.mark.parametrize(
    "field",
    [
        "comparison_family",
        "entity",
        "origin",
        "physical_basis",
        "label_hash",
        "window",
        "source_hash",
        "area_basis",
        "split",
        "training_cutoff",
    ],
)
def test_cross_source_or_scope_pairing_rejected_before_metric_computation(field):
    metadata = dict.fromkeys(
        (
            "comparison_family",
            "entity",
            "origin",
            "physical_basis",
            "label_hash",
            "window",
            "source_hash",
            "area_basis",
            "split",
            "training_cutoff",
        ),
        "SYNTHETIC-APPROVED",
    )
    comparable(metadata, {**metadata, "model": "SYNTHETIC-CANDIDATE"})
    with pytest.raises(ValueError, match="INCOMPARABLE_" + field):
        comparable(metadata, {**metadata, field: "DIFFERENT"})


def test_metric_specific_missing_count_not_silent_cohort_reduction():
    candidates = {"SYNTHETIC-ZERO", "SYNTHETIC-POSITIVE", "SYNTHETIC-MISSING"}
    quantity_computable = {"SYNTHETIC-ZERO", "SYNTHETIC-POSITIVE"}
    timing_computable = {"SYNTHETIC-POSITIVE"}
    with localcontext() as ctx:
        ctx.prec = 50
        assert coverage(candidates, quantity_computable) == (D(2) / D(3), 1)
        assert coverage(candidates, timing_computable) == (D(1) / D(3), 2)


def test_origin_local_calendar_is_not_utc_date_and_cannot_stitch_origins():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    origin = datetime.fromisoformat("2000-01-01T23:30:00+00:00")
    local_day = origin.astimezone(ZoneInfo("Asia/Shanghai")).date()
    assert local_day == date(2000, 1, 2)
    assert local_day + timedelta(days=1) == date(2000, 1, 3)
    assert contract()["weighting"]["full_season_origins"] == (
        "ONE_FIXED_ISSUANCE_NOT_STITCHED_OR_BEST_ORIGIN"
    )
