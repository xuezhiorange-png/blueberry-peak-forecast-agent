"""Literal SYNTHETIC arithmetic and isolation, never business-data scoring."""

import ast
import hashlib
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from pathlib import Path

import pytest

from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    generate_candidate,
)
from backend.research.v019_synthetic_validation import (
    AUTHORITIES,
    BASELINE,
    CANDIDATE,
    METRICS,
    Authority,
    Forecast,
    Labels,
    Pair,
    Sample,
    evaluate_synthetic,
    freeze_predictions,
    generate_synthetic_predictions,
    real_scoring_preflight,
)
from backend.tests.historical_source import historical_bytes

pytestmark = [pytest.mark.unit, pytest.mark.contract]
D = Decimal
NOW = datetime.fromisoformat("2000-01-01T17:00:00+08:00")
SCORE_AT = datetime.fromisoformat("2001-01-01T17:00:00+08:00")
H = "a" * 64
ROOT = Path(__file__).resolve().parents[3]
BASE = "822f453d130ff1ff1b1f5aeaf8fdcf1c87e2da94"
MANIFEST = ROOT / "docs/v0-19/evidence/v0.19-s3-offline-preparation-r1.json"


def sample(key="SYNTHETIC-1", *, n=15, window="H15_LOCAL", base="SYNTHETIC-BASE"):
    return Sample(
        sample_id=key,
        base_id=base,
        organization_id="SYNTHETIC-ORG",
        subfarm_id="SYNTHETIC-SUBFARM",
        variety_id="SYNTHETIC-VARIETY",
        season="SYNTHETIC-SEASON",
        area_mu=D(10),
        area_effective_date=date(1999, 1, 1),
        origin=NOW,
        issued_at=NOW,
        cutoff=NOW,
        input_available_at=NOW,
        input_ingested_at=NOW,
        dates=tuple(date(2000, 1, 2) + timedelta(days=i) for i in range(n)),
        window=window,
        physical_basis="ACTUAL_HARVEST_KG",
        unit="kg",
        profile_sha256=H,
        input_sha256=H,
        label_authority_sha256=H,
        train_scope_sha256=H,
        split="SYNTHETIC_EXPOSED_OOT",
        full_season_registered=window == "FULL_SEASON",
        authorities=tuple(Authority(name, "AVAILABLE", H) for name in AUTHORITIES),
    )


def rows(s, values):
    return tuple(DailyKg(day, D(str(v))) for day, v in zip(s.dates, values, strict=True))


def pair(s, baseline, candidate):
    return Pair(
        s.sample_id,
        Forecast(BASELINE, s.identity_sha256, H, H, rows(s, baseline)),
        Forecast(CANDIDATE, s.identity_sha256, H, H, rows(s, candidate)),
    )


def labels(s, values):
    return Labels(s.sample_id, s.identity_sha256, H, rows(s, values), SCORE_AT, SCORE_AT, True)


def report(s, b, c, a):
    seal = freeze_predictions((s,), (pair(s, b, c),), synthetic_authorized=True)
    return evaluate_synthetic(seal, (labels(s, a),), as_of=SCORE_AT, synthetic_authorized=True)


def metric(result, name, window="H15_LOCAL"):
    return result["groups"][f"SYNTHETIC_EXPOSED_OOT:{window}"]["metrics"][name]


def test_same_total_different_timing_and_all_ten_metrics():
    s = sample(window="FULL_SEASON")
    a = [9] + [1] * 14
    c = [1, 9] + [1] * 13
    r = report(s, a, c, a)
    assert set(r["groups"]["SYNTHETIC_EXPOSED_OOT:FULL_SEASON"]["metrics"]) == set(METRICS)
    assert metric(r, "SEASON_TOTAL_WAPE", "FULL_SEASON")["candidate"]["value"] == "0"
    assert metric(r, "DAILY_MAE", "FULL_SEASON")["candidate"]["numerator"] == "16"
    assert metric(r, "SINGLE_DAY_PEAK_DATE_MAE", "FULL_SEASON")["candidate"]["value"] == "1"


@pytest.mark.parametrize(
    "b,c,quantity_better,timing_better",
    [
        ([0, 30] + [0] * 13, [0, 0, 10] + [0] * 12, True, False),
        ([0, 0, 10] + [0] * 12, [0, 30] + [0] * 13, False, True),
        ([0, 0, 30] + [0] * 12, [10] + [0] * 14, True, True),
        ([10] + [0] * 14, [0, 0, 30] + [0] * 12, False, False),
    ],
)
def test_quantity_and_timing_tradeoffs_are_not_hidden(b, c, quantity_better, timing_better):
    r = report(sample(), b, c, [10] + [0] * 14)
    for key, better in (
        ("DAILY_MAE", quantity_better),
        ("SINGLE_DAY_PEAK_DATE_MAE", timing_better),
    ):
        m = metric(r, key)
        assert (D(m["candidate"]["value"]) < D(m["baseline"]["value"])) is better
    assert r["overall_winner"] is None


def test_zero_actual_has_no_fake_timing_or_wape_but_valid_quantity():
    r = report(sample(), [1] * 15, [2] * 15, [0] * 15)
    for name in ("DAILY_WAPE", "SINGLE_DAY_PEAK_DATE_MAE", "ROLLING_7DAY_PEAK_START_MAE"):
        m = metric(r, name)
        assert m["candidate"]["value"] is None
        assert m["common_count"] == 0 and m["not_computable_count"] == 1
    assert metric(r, "DAILY_MAE")["candidate"]["value"] == "2"
    assert metric(r, "ROLLING_7DAY_PEAK_QUANTITY_MAE")["candidate"]["value"] == "14"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unsorted", "negative", "nan"])
def test_bad_prediction_calendar_or_value_retained_in_c0(mutation):
    s = sample()
    p = pair(s, [1] * 15, [2] * 15)
    original = p.candidate.rows
    if mutation == "missing":
        changed = original[:-1]
    elif mutation == "duplicate":
        changed = original[:-1] + (original[0],)
    elif mutation == "unsorted":
        changed = original[::-1]
    else:
        changed = (
            DailyKg(original[0].day, D("-1" if mutation == "negative" else "NaN")),
        ) + original[1:]
    p = replace(p, candidate=replace(p.candidate, rows=changed))
    seal = freeze_predictions((s,), (p,), synthetic_authorized=True)
    r = evaluate_synthetic(seal, (labels(s, [1] * 15),), as_of=SCORE_AT, synthetic_authorized=True)
    m = metric(r, "DAILY_MAE")
    assert m["candidate_count"] == m["not_computable_count"] == 1
    assert m["common_count"] == 0 and m["baseline"]["value"] is None


def test_short_full_season_has_daily_metrics_but_no_rolling7():
    r = report(sample(n=6, window="FULL_SEASON"), [1] * 6, [2] * 6, [1] * 6)
    m = metric(r, "ROLLING_7DAY_PEAK_QUANTITY_MAE", "FULL_SEASON")
    assert m["reasons"] == {"NO_COMPLETE_7DAY_WINDOW": 1}
    assert metric(r, "DAILY_MAE", "FULL_SEASON")["candidate"]["value"] == "1"


def test_overlapping_origins_remain_distinct_and_micro_pool_zero_rows():
    s1, s2 = (
        sample(),
        replace(
            sample("SYNTHETIC-2"),
            origin=NOW + timedelta(days=1),
            issued_at=NOW + timedelta(days=1),
            dates=tuple(d + timedelta(days=1) for d in sample().dates),
        ),
    )
    seal = freeze_predictions(
        (s1, s2),
        (pair(s1, [1] * 15, [2] * 15), pair(s2, [10] * 15, [10] * 15)),
        synthetic_authorized=True,
    )
    r = evaluate_synthetic(
        seal,
        (labels(s1, [0] * 15), labels(s2, [10] * 15)),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    m = metric(r, "DAILY_WAPE")
    assert m["candidate"]["value"] == "0.2"
    assert m["candidate"]["denominator"] == "150"
    assert metric(r, "DAILY_MAE")["candidate"]["denominator"] == "30"


@pytest.mark.parametrize(
    "change", ["identity", "model", "label_hash", "immature", "availability", "basis"]
)
def test_authority_identity_physical_and_label_failures_are_not_zero_errors(change):
    s = sample()
    if change == "availability":
        s = replace(
            s,
            authorities=tuple(
                replace(a, status="NOT_VERIFIED") if a.name == "AVAILABLE_AT_INGESTED_AT" else a
                for a in s.authorities
            ),
        )
    if change == "basis":
        s = replace(s, unit="kg/mu")
    p, lab = pair(s, [1] * 15, [1] * 15), labels(s, [1] * 15)
    if change == "identity":
        p = replace(p, candidate=replace(p.candidate, sample_identity_sha256="b" * 64))
    if change == "model":
        p = replace(p, candidate=replace(p.candidate, model_id="OTHER"))
    if change == "label_hash":
        lab = replace(lab, authority_sha256="b" * 64)
    if change == "immature":
        lab = replace(lab, mature=False)
    r = evaluate_synthetic(
        freeze_predictions((s,), (p,), synthetic_authorized=True),
        (lab,),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    assert metric(r, "DAILY_MAE")["common_count"] == 0


def test_missing_model_prediction_coverage_and_breadth_use_common_set():
    s1, s2 = sample(), sample("SYNTHETIC-2", base="SYNTHETIC-OTHER")
    missing = Pair(
        s2.sample_id, pair(s2, [1] * 15, [1] * 15).baseline, None, "SYNTHETIC_MODEL_FAILURE"
    )
    seal = freeze_predictions(
        (s1, s2), (pair(s1, [2] * 15, [1] * 15), missing), synthetic_authorized=True
    )
    r = evaluate_synthetic(
        seal,
        (labels(s1, [1] * 15), labels(s2, [1] * 15)),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    m = metric(r, "DAILY_MAE")
    assert m["sample_coverage"] == "0.5" and m["not_computable_count"] == 1
    assert m["baseline_available_count"] == 2 and m["candidate_available_count"] == 1
    assert r["conclusion_scope"] == "CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT"
    breadth = metric(r, "BASE_BREADTH")
    assert breadth["improved"] == 1 and breadth["n_base"] == 1


def test_label_permission_checked_before_iteration_and_real_scoring_stays_blocked():
    s = sample()
    seal = freeze_predictions((s,), (pair(s, [1] * 15, [1] * 15),), synthetic_authorized=True)

    class ForbiddenLabels:
        def __iter__(self):
            raise AssertionError("LABEL_ACCESS_BEFORE_PERMISSION")

    with pytest.raises(PermissionError, match="SYNTHETIC_AUTHORIZATION_REQUIRED"):
        evaluate_synthetic(seal, ForbiddenLabels(), as_of=SCORE_AT, synthetic_authorized=False)
    assert real_scoring_preflight()["S3_REAL_SCORING"] == "BLOCKED"
    assert len(real_scoring_preflight()["authorities"]) == 12
    with pytest.raises(PermissionError):
        freeze_predictions((replace(s, data_class="REAL"),), (), synthetic_authorized=True)


def test_seal_tamper_duplicate_cohort_and_unregistered_labels_rejected():
    s = sample()
    seal = freeze_predictions((s,), (pair(s, [1] * 15, [1] * 15),), synthetic_authorized=True)
    for bad in (replace(seal, sha256="0" * 64), replace(seal, raw=seal.raw + b" ")):
        with pytest.raises(ValueError, match="SEAL"):
            evaluate_synthetic(
                bad, (labels(s, [1] * 15),), as_of=SCORE_AT, synthetic_authorized=True
            )
    with pytest.raises(ValueError, match="C0"):
        freeze_predictions((s, s), (), synthetic_authorized=True)
    with pytest.raises(ValueError, match="LABEL_COHORT"):
        evaluate_synthetic(
            seal,
            (labels(sample("SYNTHETIC-OTHER"), [1] * 15),),
            as_of=SCORE_AT,
            synthetic_authorized=True,
        )


def test_determinism_across_ambient_decimal_precision_and_input_order():
    s = sample()
    outputs = []
    for precision in (6, 28, 100):
        with localcontext() as ctx:
            ctx.prec = precision
            outputs.append(report(s, [1] * 15, [2] * 15, [3] * 15))
    assert outputs[0] == outputs[1] == outputs[2]


def test_s2_frozen_candidate_is_called_without_labels_or_query_renormalization():
    full = sample(n=21, window="FULL_SEASON")
    request = CurveInput(
        full.dates[0],
        full.dates[0],
        full.dates[-1],
        rows(full, [1] * 7 + [3] * 7 + [2] * 7),
        H,
        BASELINE_POLICY,
        "Asia/Shanghai",
    )
    candidate = generate_candidate(request)
    s = replace(sample(), input_sha256=candidate.input_sha256)
    seal = generate_synthetic_predictions((s,), {s.sample_id: request}, synthetic_authorized=True)
    assert seal.pairs[0].candidate.rows == candidate.rows[:15]
    assert seal.pairs[0].baseline.rows == request.baseline[:15]
    assert seal.pairs[0].candidate.source_sha256 == candidate.result_sha256
    assert b'"labels_read": false' in seal.raw
    assert b'"label_authority_sha256"' in seal.raw  # authority identity, not label content
    r = evaluate_synthetic(seal, (labels(s, [1] * 15),), as_of=SCORE_AT, synthetic_authorized=True)
    assert metric(r, "DAILY_MAE")["common_count"] == 1


def test_generation_failures_retained_not_removed_from_cohort():
    s = sample()
    seal = generate_synthetic_predictions((s,), {}, synthetic_authorized=True)
    assert seal.pairs[0].failure == "MISSING_REGISTERED_INPUT"
    r = evaluate_synthetic(seal, (), as_of=SCORE_AT, synthetic_authorized=True)
    assert metric(r, "DAILY_MAE")["candidate_count"] == 1
    assert metric(r, "DAILY_MAE")["not_computable_count"] == 1


def test_h7_h15_and_season_are_not_pooled_and_earliest_tie_is_fixed():
    ss = [
        sample(f"SYNTHETIC-{i}", n=n, window=w)
        for i, (n, w) in enumerate(((7, "H7_PREFIX"), (15, "H15_LOCAL"), (21, "FULL_SEASON")))
    ]
    ps = tuple(pair(s, [1] * len(s.dates), [0] * len(s.dates)) for s in ss)
    ls = tuple(labels(s, [0] * (len(s.dates) - 1) + [10]) for s in ss)
    r = evaluate_synthetic(
        freeze_predictions(tuple(ss), ps, synthetic_authorized=True),
        ls,
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    assert len(r["groups"]) == 3
    for s in ss:
        assert metric(r, "SINGLE_DAY_PEAK_DATE_MAE", s.window)["candidate"]["value"] == str(
            len(s.dates) - 1
        )
        assert metric(r, "ROLLING_7DAY_PEAK_START_MAE", s.window)["candidate"]["value"] == str(
            len(s.dates) - 7
        )
    assert metric(r, "SEASON_TOTAL_WAPE")["candidate"]["value"] is None


def test_each_own_peak_quantity_and_full_nine_rolling_starts():
    r = report(sample(), [10] + [0] * 14, [0] * 14 + [20], [10] + [0] * 14)
    assert metric(r, "SINGLE_DAY_PEAK_QUANTITY_MAE")["candidate"]["value"] == "10"
    assert metric(r, "SINGLE_DAY_PEAK_DATE_MAE")["candidate"]["value"] == "14"
    assert metric(r, "ROLLING_7DAY_PEAK_START_MAE")["candidate"]["value"] == "8"
    assert metric(r, "ROLLING_7DAY_PEAK_QUANTITY_MAE")["candidate"]["value"] == "10"


@pytest.mark.parametrize("status", ["MISSING", "NOT_VERIFIED", "BLOCKED", "UNKNOWN"])
def test_every_non_available_authority_blocks_computability(status):
    s = sample()
    s = replace(s, authorities=(replace(s.authorities[0], status=status),) + s.authorities[1:])
    r = report(s, [1] * 15, [1] * 15, [1] * 15)
    assert metric(r, "DAILY_MAE")["reasons"] == {"UNVERIFIED_AUTHORITY": 1}


@pytest.mark.parametrize(
    "field", ["area_mu", "season", "profile_sha256", "input_sha256", "train_scope_sha256"]
)
def test_stale_prediction_identity_detects_changed_common_basis(field):
    s = sample()
    p = pair(s, [1] * 15, [1] * 15)
    value = D(11) if field == "area_mu" else "SYNTHETIC-OTHER" if field == "season" else "b" * 64
    changed = replace(s, **{field: value})
    r = evaluate_synthetic(
        freeze_predictions((changed,), (p,), synthetic_authorized=True),
        (labels(changed, [1] * 15),),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    assert metric(r, "DAILY_MAE")["reasons"] == {"IDENTITY_OR_SOURCE_HASH_MISMATCH": 1}


@pytest.mark.parametrize(
    "change",
    [
        "future_input",
        "future_label",
        "naive_time",
        "bad_hash",
        "wrong_horizon",
        "unregistered_season",
    ],
)
def test_time_source_and_window_contracts(change):
    s = sample()
    if change == "future_input":
        s = replace(s, input_available_at=NOW + timedelta(seconds=1))
    if change == "naive_time":
        s = replace(s, cutoff=NOW.replace(tzinfo=None))
    if change == "bad_hash":
        s = replace(s, profile_sha256="invalid")
    if change == "wrong_horizon":
        s = replace(s, window="H7_PREFIX")
    if change == "unregistered_season":
        s = replace(s, window="FULL_SEASON", full_season_registered=False)
    lab = labels(s, [1] * 15)
    if change == "future_label":
        lab = replace(lab, available_at=SCORE_AT + timedelta(seconds=1))
    r = evaluate_synthetic(
        freeze_predictions((s,), (pair(s, [1] * 15, [1] * 15),), synthetic_authorized=True),
        (lab,),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    assert metric(r, "DAILY_MAE", s.window)["common_count"] == 0


def test_empty_cohort_not_zero_error_and_single_full_season_issuance():
    seal = freeze_predictions((), (), synthetic_authorized=True)
    r = evaluate_synthetic(seal, (), as_of=SCORE_AT, synthetic_authorized=True)
    assert r["empty_cohort"] == {"reason": "EMPTY_COHORT", "count": 0, "value": None}
    ss = (
        sample(window="FULL_SEASON"),
        replace(sample("SYNTHETIC-2", window="FULL_SEASON"), origin=NOW + timedelta(days=1)),
    )
    with pytest.raises(ValueError, match="ONE_FULL_SEASON"):
        freeze_predictions(
            ss, tuple(pair(s, [1] * 15, [1] * 15) for s in ss), synthetic_authorized=True
        )


def test_precision_rounding_member_order_and_missing_labels_are_deterministic():
    s1, s2 = sample(), sample("SYNTHETIC-2", base="SYNTHETIC-OTHER")
    ps = (pair(s1, [1] * 15, [2] * 15), pair(s2, [4] * 15, [3] * 15))
    results = []
    for precision, rounding in ((6, ROUND_UP), (100, ROUND_DOWN)):
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = precision, rounding
            seal = freeze_predictions((s2, s1), ps[::-1], synthetic_authorized=True)
            results.append(
                evaluate_synthetic(
                    seal, (labels(s1, [3] * 15),), as_of=SCORE_AT, synthetic_authorized=True
                )
            )
    assert results[0] == results[1]
    assert metric(results[0], "DAILY_MAE")["reasons"] == {"UNVERIFIED_AUTHORITY": 1}


def test_s1_independent_oracle_on_complete_synthetic_curves():
    from backend.tests.area_yield.test_v0_19_s1_protocol import synthetic_errors

    b, c, a = (
        [str(i % 3) for i in range(15)],
        [str((i + 1) % 4) for i in range(15)],
        [str(i % 5) for i in range(15)],
    )
    r = report(sample(window="FULL_SEASON"), b, c, a)
    for side, values in (("baseline", b), ("candidate", c)):
        oracle = synthetic_errors([values], [a], complete_toy_season=True)
        for name in METRICS[:7]:
            assert D(metric(r, name, "FULL_SEASON")[side]["value"]) == oracle[name]


def test_duplicate_unit_cannot_be_reintroduced_with_another_sample_id():
    ss = (sample(), sample("SYNTHETIC-2"))
    with pytest.raises(ValueError, match="C0_DUPLICATE_COMPARISON_UNIT"):
        freeze_predictions(
            ss, tuple(pair(s, [1] * 15, [1] * 15) for s in ss), synthetic_authorized=True
        )


def test_breadth_three_bases_and_preregistered_whole_base_sensitivity():
    ss = tuple(sample(f"SYNTHETIC-{i}", base=f"SYNTHETIC-BASE-{i}") for i in range(3))
    # Identical toy actual masses; one improves, one ties, one worsens.
    ps = (
        pair(ss[0], [4] * 15, [1] * 15),
        pair(ss[1], [1] * 15, [1] * 15),
        pair(ss[2], [1] * 15, [2] * 15),
    )
    r = evaluate_synthetic(
        freeze_predictions(ss, ps, synthetic_authorized=True),
        tuple(labels(s, [1] * 15) for s in ss),
        as_of=SCORE_AT,
        synthetic_authorized=True,
    )
    breadth = metric(r, "BASE_BREADTH")
    assert (breadth["improved"], breadth["tied"], breadth["worsened"], breadth["n_base"]) == (
        1,
        1,
        1,
        3,
    )
    with localcontext() as ctx:
        ctx.prec = 50
        assert D(breadth["improved_actual_kg_share"]["value"]) == D(1) / D(3)
    group = r["groups"]["SYNTHETIC_EXPOSED_OOT:H15_LOCAL"]
    assert group["h15_whole_base_sensitivity"]["remove_top_1_bases"]["removed_base_ids"] == [
        "SYNTHETIC-BASE-0"
    ]
    assert group["h15_whole_base_sensitivity"]["remove_top_2_bases"]["remaining_count"] == 1
    assert group["diagnostics"]["candidate"]["signed_bias_kg"] == "15"


def test_earliest_primary_reason_is_not_double_counted():
    s = replace(sample(), unit="kg/mu", authorities=())
    r = report(s, [1] * 15, [1] * 15, [1] * 15)
    m = metric(r, "DAILY_MAE")
    assert m["reasons"] == {"UNVERIFIED_AUTHORITY": 1}
    assert sum(m["reasons"].values()) == m["not_computable_count"] == 1


def verify_historical(path, commit, expected):
    assert commit == BASE, "SOURCE_COMMIT_NOT_APPROVED"
    raw = historical_bytes(path, commit, root=ROOT)
    assert hashlib.sha256(raw).hexdigest() == expected, "HISTORICAL_HASH_MISMATCH"
    return raw


def test_local_manifest_canonical_sources_and_permissions():
    raw = MANIFEST.read_bytes()
    data = json.loads(raw)
    assert (
        raw
        == (
            json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
        ).encode()
    )
    assert data["base_main_sha"] == BASE
    assert data["baseline_id"] == BASELINE and data["candidate_id"] == CANDIDATE
    assert data["metrics"] == list(METRICS)
    assert data["real_preflight"] == real_scoring_preflight()
    assert data["governance"] == {
        "offline_preparation_authorized": True,
        "commit_authorized": False,
        "push_authorized": False,
        "formal_s3_pr_authorized": False,
        "real_data_access_authorized": False,
        "real_scoring_authorized": False,
        "model_training_authorized": False,
        "model_promotion_authorized": False,
        "s3_formal_complete": False,
        "ready_authorized": False,
        "merge_authorized": False,
    }
    for path, binding in data["historical_sources"].items():
        verify_historical(path, binding["commit"], binding["sha256"])
    for path, expected in data["frozen_documents_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    assert len(data["synthetic_matrix"]) == 17
    for path, expected in data["documents_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    assert data["scientific_limits"]["strict_pit"] is False
    assert data["scientific_limits"]["exposed_2025_2026_is_blind_oot"] is False


def test_wrong_historical_commit_or_hash_and_missing_git_source_fail():
    data = json.loads(MANIFEST.read_bytes())
    path, binding = next(iter(data["historical_sources"].items()))
    with pytest.raises(AssertionError, match="SOURCE_COMMIT_NOT_APPROVED"):
        verify_historical(path, "0" * 40, binding["sha256"])
    with pytest.raises(AssertionError, match="HISTORICAL_HASH_MISMATCH"):
        verify_historical(path, BASE, "0" * 64)
    with pytest.raises(AssertionError):
        historical_bytes(path, "0" * 40, root=ROOT)
    with pytest.raises(AssertionError):
        historical_bytes("backend/research/SYNTHETIC_missing.py", BASE, root=ROOT)


def test_research_module_has_no_private_loader_or_production_imports():
    from backend.research import v019_synthetic_validation as module

    tree = ast.parse(Path(module.__file__).read_text())
    forbidden = {"os", "subprocess", "pathlib", "socket", "httpx", "requests", "sqlalchemy"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(item.name.split(".")[0] not in forbidden for item in node.names)
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("backend.app")
            assert (node.module or "").split(".")[0] not in forbidden
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}


def test_current_test_changes_are_not_used_as_historical_source_identity():
    data = json.loads(MANIFEST.read_bytes())
    assert (
        "backend/tests/area_yield/test_v0_19_s3_synthetic_validation.py"
        not in data["historical_sources"]
    )
    assert data["new_source_commit"] == "NOT_COMMITTED_LOCAL_PREPARATION"
    assert all(binding["commit"] == BASE for binding in data["historical_sources"].values())
