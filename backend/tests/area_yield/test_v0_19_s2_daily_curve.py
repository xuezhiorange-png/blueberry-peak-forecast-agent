"""Only literal SYNTHETIC curves: no labels, artifacts, database or scoring."""

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
    method_config,
    select_window,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]
START = date(2000, 7, 1)
ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "docs/v0-19/s2/daily-curve-method-config-r1.json"
STRUCTURE = ROOT / "docs/v0-19/evidence/v0.19-s2-synthetic-structure-r1.json"
EVIDENCE = ROOT / "docs/v0-19/evidence/v0.19-s2-daily-curve-candidate-r1.json"
START_MAIN = "a95d5596e7c25d485414fd540b17ca13920724a9"
SOURCE_SEAL = "1695fd758713e2e364493a1b368aa1504042b506"
SOURCE_COMMITS = {
    **dict.fromkeys(
        (
            "backend/app/forecast_quality/operational_peak.py",
            "backend/tests/area_yield/test_v0_19_scope_contract.py",
            "backend/tests/area_yield/test_v0_19_s1_protocol.py",
            "pyproject.toml",
            "uv.lock",
        ),
        START_MAIN,
    ),
    **dict.fromkeys(
        (
            "backend/research/__init__.py",
            "backend/research/v019_daily_curve.py",
            "backend/tests/area_yield/test_v0_19_s2_daily_curve.py",
        ),
        SOURCE_SEAL,
    ),
}


def synthetic(rates=("1", "2", "4"), *, offset=0, length=None):
    values = [Decimal(rate) for rate in rates for _ in range(7)]
    end = len(values) if length is None else offset + length
    rows = tuple(DailyKg(START + timedelta(days=i), values[i]) for i in range(offset, end))
    source = {
        "data_class": "SYNTHETIC",
        "rows": [{"date": r.day.isoformat(), "kg": format(r.kg, ".6f")} for r in rows],
        "season_start": START.isoformat(),
    }
    return CurveInput(
        season_start=START,
        support_start=rows[0].day,
        support_end=rows[-1].day,
        baseline=rows,
        baseline_source_sha256=hashlib.sha256(canonical_bytes(source)).hexdigest(),
        baseline_policy=BASELINE_POLICY,
        timezone="Asia/Shanghai",
    )


def test_frozen_method_config_is_canonical_single_candidate_without_search():
    data = json.loads(CONFIG.read_bytes())
    assert CONFIG.read_bytes() == canonical_bytes(data)
    assert data == method_config()
    assert data["candidate_count"] == 1
    assert data["parameter_search"] is False
    assert data["interpolation"] == "BIN_CENTER_LINEAR_INTERPOLATION"
    assert data["normalization"] == "PER_BIN_MASS_CONSERVING_NORMALIZATION"
    assert data["quantization"] == "LARGEST_EXACT_REMAINDER_THEN_EARLIEST_DATE"


@pytest.mark.parametrize(
    "case", json.loads(STRUCTURE.read_bytes())["cases"], ids=lambda c: c["case_id"]
)
def test_archived_synthetic_input_output_and_bin_proofs_reproduce(case):
    archive = json.loads(STRUCTURE.read_bytes())
    assert STRUCTURE.read_bytes() == canonical_bytes(archive)
    assert archive["data_class"] == "SYNTHETIC_ONLY_NO_LABELS"
    assert archive["real_accuracy_evaluated"] is False
    assert len(archive["cases"]) == 9
    assert archive["config_sha256"] == hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    data = case["input"]
    assert (
        data["baseline_source_sha256"]
        == hashlib.sha256(
            canonical_bytes(
                {
                    "data_class": "SYNTHETIC",
                    "rows": data["rows"],
                    "season_start": data["season_start"],
                }
            )
        ).hexdigest()
    )
    request = CurveInput(
        season_start=date.fromisoformat(data["season_start"]),
        support_start=date.fromisoformat(data["support_start"]),
        support_end=date.fromisoformat(data["support_end"]),
        baseline=tuple(
            DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"])) for r in data["rows"]
        ),
        baseline_source_sha256=data["baseline_source_sha256"],
        baseline_policy=data["baseline_policy"],
        timezone=data["timezone"],
    )
    first, second = generate_candidate(request), generate_candidate(request)
    assert first == second
    payload = json.loads(first.canonical_bytes)
    assert payload["input"] == data
    assert payload["rows"] == case["candidate_rows"]
    assert payload["bin_mass"] == case["bin_mass"]
    assert first.input_sha256 == case["input_sha256"]
    assert first.result_sha256 == case["result_sha256"]
    assert first.config_sha256 == archive["config_sha256"]
    assert (first.rows != request.baseline) is case["structure_changed"]


def test_research_module_has_no_runtime_or_io_dependencies():
    import ast

    tree = ast.parse((ROOT / "backend/research/v019_daily_curve.py").read_bytes())
    allowed = {
        "__future__",
        "hashlib",
        "json",
        "re",
        "bisect",
        "dataclasses",
        "datetime",
        "decimal",
        "math",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"open", "eval", "exec", "__import__"}


@pytest.mark.parametrize(
    "rates",
    [
        ("3", "3", "3"),
        ("1", "2", "4"),
        ("4", "2", "1"),
        ("1", "0", "4"),
        ("0", "0", "0"),
        ("0.000001", "9", "0.000002", "100"),
        ("0.000001", "0.000002", "0.000003"),
        ("100000000000000000000000000001.000001", "0", "1"),
    ],
)
def test_each_bin_and_total_mass_exact_nonnegative_and_baseline_unchanged(rates):
    request = synthetic(rates)
    before = request.baseline
    result = generate_candidate(request)
    assert request.baseline == before
    assert tuple(r.day for r in result.rows) == tuple(r.day for r in before)
    with localcontext() as ctx:
        ctx.prec = 100
        assert sum(r.kg for r in result.rows) == sum(r.kg for r in before)
        for bin_id in {(r.day - START).days // 7 for r in before}:
            baseline = [r.kg for r in before if (r.day - START).days // 7 == bin_id]
            candidate = [r.kg for r in result.rows if (r.day - START).days // 7 == bin_id]
            assert sum(candidate) == sum(baseline)
            assert all(q >= 0 and q.as_tuple().exponent == -6 for q in candidate)
            if not sum(baseline):
                assert not any(candidate)
    assert all(b.baseline_micro_kg == b.candidate_micro_kg for b in result.bins)


def test_constant_and_all_zero_curves_remain_constant():
    for rates in (("3", "3", "3"), ("0", "0", "0")):
        request = synthetic(rates)
        assert generate_candidate(request).rows == request.baseline


@pytest.mark.parametrize("rates,ascending", [(("1", "2", "4"), True), (("4", "2", "1"), False)])
def test_real_daily_structure_differs_without_claiming_accuracy(rates, ascending):
    request = synthetic(rates)
    result = generate_candidate(request)
    assert result.rows != request.baseline
    middle = [r.kg for r in result.rows[7:14]]
    assert len(set(middle)) > 1
    assert middle == sorted(middle, reverse=not ascending)
    assert "accuracy" not in result.canonical_bytes.decode().lower()


@pytest.mark.parametrize("offset,length", [(2, 16), (6, 2), (3, 1), (0, 3), (1, 19)])
def test_short_first_and_last_bins_use_only_actual_support(offset, length):
    request = synthetic(offset=offset, length=length)
    result = generate_candidate(request)
    assert result.rows[0].day == request.support_start
    assert result.rows[-1].day == request.support_end
    assert len(result.rows) == length
    assert result.bins[0].bin_id == offset // 7
    assert all(b.baseline_micro_kg == b.candidate_micro_kg for b in result.bins)


def test_quantization_tie_uses_earliest_date():
    # A rising neighbour gives exact quotas 49/67 (four times),70/67,91/67,112/67.
    # Four equal largest fractional remainders must go to the earliest four dates.
    result = generate_candidate(synthetic(("0.000001", "0.000004")))
    assert [r.kg for r in result.rows[:7]] == [Decimal("0.000001")] * 7
    # Now only TWO of four tied dates receive a residual micro-kg. Choosing the
    # latest dates instead would preserve mass but must fail this assertion.
    tied = generate_candidate(synthetic(("0.000001", "0.000009")))
    assert [r.kg for r in tied.rows[:7]] == [
        Decimal(value)
        for value in ("0.000001", "0.000001", "0", "0", "0.000001", "0.000002", "0.000002")
    ]


def test_independent_fraction_oracle_checks_interpolation_and_normalization():
    from fractions import Fraction

    for rates in (("1", "2", "4"), ("10", "0", "0.000001"), ("0.000001", "0.000009", "0.000003")):
        for offset, length in ((0, 21), (2, 16), (6, 2)):
            request = synthetic(rates, offset=offset, length=length)
            groups = {}
            for row in request.baseline:
                groups.setdefault((row.day - START).days // 7, []).append(row)
            anchors = [
                (
                    Fraction((rows[0].day - START).days + (rows[-1].day - START).days, 2),
                    Fraction(rows[0].kg),
                )
                for rows in groups.values()
            ]
            expected = []
            for rows in groups.values():
                shape = []
                for row in rows:
                    x = Fraction((row.day - START).days)
                    if x <= anchors[0][0]:
                        raw = anchors[0][1]
                    elif x >= anchors[-1][0]:
                        raw = anchors[-1][1]
                    else:
                        left, right = next(
                            (a, b)
                            for a, b in zip(anchors, anchors[1:], strict=False)
                            if a[0] <= x <= b[0]
                        )
                        raw = left[1] + (right[1] - left[1]) * (x - left[0]) / (right[0] - left[0])
                    shape.append(raw)
                target = sum(Fraction(row.kg) for row in rows) * 1_000_000
                assert target.denominator == 1
                if not target:
                    expected.extend([0] * len(rows))
                    continue
                quotas = [target * weight / sum(shape) for weight in shape]
                floors = [q.numerator // q.denominator for q in quotas]
                remaining = int(target) - sum(floors)
                priority = sorted(
                    range(len(rows)), key=lambda i: (-(quotas[i] - floors[i]), rows[i].day)
                )
                expected.extend(q + int(i in priority[:remaining]) for i, q in enumerate(floors))
            actual = generate_candidate(request)
            assert [Fraction(row.kg) * 1_000_000 for row in actual.rows] == expected


def test_h7_h15_are_slices_of_full_candidate_not_new_normalizations():
    result = generate_candidate(synthetic(("1", "2", "4", "8")))
    for days in (7, 15):
        origin = START + timedelta(days=2)
        selected = select_window(result, origin=origin, horizon=days)
        assert selected == result.rows[3 : 3 + days]
    with pytest.raises(ValueError, match="QUERY_OUTSIDE_SUPPORT"):
        select_window(result, origin=START + timedelta(days=25), horizon=7)
    with pytest.raises(ValueError, match="INVALID_HORIZON"):
        select_window(result, origin=START, horizon=1)


def test_same_input_has_identical_canonical_bytes_and_sha_across_decimal_contexts():
    request = synthetic(("0.000001", "11.000001", "2.000003"))
    original = generate_candidate(request)
    for precision in (6, 28, 100):
        with localcontext() as ctx:
            ctx.prec = precision
            repeated = generate_candidate(request)
        assert repeated == original
        assert len(repeated.result_sha256) == len(repeated.input_sha256) == 64
    config = method_config()
    config["bin_days"] = 99
    assert method_config()["bin_days"] == 7


def test_fixed_method_on_256_synthetic_input_shapes_without_parameter_search():
    from itertools import product

    config = method_config()
    count = 0
    for rates in product(("0", "0.000001", "0.000009", "1"), repeat=3):
        for offset, length in ((0, 21), (2, 16), (6, 2), (3, 1)):
            request = synthetic(rates, offset=offset, length=length)
            result = generate_candidate(request)
            assert all(b.baseline_micro_kg == b.candidate_micro_kg for b in result.bins)
            assert all(row.kg >= 0 for row in result.rows)
            assert result == generate_candidate(request)
            count += 1
    assert count == 256
    assert method_config() == config


def test_source_identity_changes_hash_but_not_shape_without_business_recomputation():
    from dataclasses import replace

    request = synthetic()
    first = generate_candidate(request)
    other_source = generate_candidate(replace(request, baseline_source_sha256="b" * 64))
    assert first.rows == other_source.rows
    assert first.input_sha256 != other_source.input_sha256
    assert first.result_sha256 != other_source.result_sha256


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "unsorted",
        "negative",
        "nan",
        "infinity",
        "float",
        "submicro",
        "nonflat",
        "datetime",
        "hash",
        "policy",
        "timezone",
        "before_season",
        "empty",
        "end",
    ],
)
def test_invalid_input_fails_closed_without_filling_or_rounding(mutation):
    from dataclasses import replace

    request = synthetic()
    rows = list(request.baseline)
    if mutation == "missing":
        rows.pop(5)
    elif mutation == "duplicate":
        rows[5] = rows[4]
    elif mutation == "unsorted":
        rows.reverse()
    elif mutation in {"negative", "nan", "infinity", "submicro", "float", "nonflat"}:
        value = {
            "negative": Decimal("-1"),
            "nan": Decimal("NaN"),
            "infinity": Decimal("Infinity"),
            "submicro": Decimal("0.0000001"),
            "float": 1.0,
            "nonflat": Decimal("3"),
        }[mutation]
        rows[5] = DailyKg(rows[5].day, value)
    elif mutation == "datetime":
        rows[5] = DailyKg(datetime(2000, 7, 6), rows[5].kg)
    elif mutation == "hash":
        request = replace(request, baseline_source_sha256="NOT_A_HASH")
    elif mutation == "policy":
        request = replace(request, baseline_policy="OTHER_MODEL")
    elif mutation == "timezone":
        request = replace(request, timezone="UTC")
    elif mutation == "before_season":
        request = replace(request, season_start=START + timedelta(days=1))
    elif mutation == "end":
        request = replace(request, support_end=request.support_end + timedelta(days=1))
    else:
        rows = []
    with pytest.raises(ValueError):
        generate_candidate(replace(request, baseline=tuple(rows)))


def _verified_historical_source(path, commit, expected):
    from backend.tests.historical_source import historical_bytes

    assert commit == SOURCE_COMMITS[path], "UNREVIEWED_SOURCE_COMMIT"
    raw = historical_bytes(path, commit, root=ROOT)
    assert hashlib.sha256(raw).hexdigest() == expected, "HISTORICAL_SHA256_MISMATCH"
    return raw


def _verified_frozen_file(path, expected, *, root=ROOT):
    raw = (root / path).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected, "FROZEN_SHA256_MISMATCH"
    return raw


def test_machine_evidence_identity_gates_and_authorizations():
    import ast

    data = json.loads(EVIDENCE.read_bytes())
    assert EVIDENCE.read_bytes() == canonical_bytes(data)
    assert data["task_id"] == "V0_19_S2_DAILY_CURVE_TEMPORAL_RESOLUTION_CANDIDATE_R1"
    assert data["version"] == "0.19.0" and data["stage"] == "S2"
    assert data["version_name"] == "HARVEST_CURVE_AND_PEAK_TIMING_ALGORITHM_RESEARCH"
    assert data["base_main_sha"] == START_MAIN
    assert data["candidate_source_seal_commit"] == SOURCE_SEAL
    assert data["candidate_count"] == 1
    assert data["candidate_id"] == method_config()["candidate_id"]
    assert data["method_config_sha256"] == hashlib.sha256(CONFIG.read_bytes()).hexdigest()
    gate = data["delivery_gate_observed"]
    assert gate["run_id"] == 39251108327 and gate["head_sha"] == START_MAIN
    assert gate["event"] == "push" and gate["attempt"] == 1
    assert gate["status"] == "completed" and gate["conclusion"] == "success"
    assert set(gate["successful_jobs"]) == {
        "full-suite-canary",
        "frontend-e2e",
        "frontend-static",
        "frontend-unit",
    }
    assert len(gate["skipped_jobs"]) == 8
    assert {k for k, v in data["governance"].items() if v is True} == {
        "owner_s2_implementation_authorized",
        "parallel_isolated_development_authorized",
        "formal_delivery_requires_s1_main_ci_success",
        "stop_after_draft_exact_head_ci",
    }
    assert {k for k, v in data["execution"].items() if v is True} == {
        "candidate_implemented",
        "synthetic_tests_executed",
    }
    assert all(v is False for v in data["scientific_limits"].values())
    assert data["s3_required_preconditions"] == [
        "S1_S2_FORMAL_COMPLETE",
        "SEPARATE_OWNER_S3_IMPLEMENTATION_AUTHORIZATION",
        "SEPARATE_DATA_AND_EXPERIMENT_AUTHORIZATION",
        "SOURCE_COHORT_PHYSICAL_AND_TIME_AUTHORITY",
        "PREDICTION_SEAL_BEFORE_LABEL_READ",
    ]
    test_path = "backend/tests/area_yield/test_v0_19_s2_daily_curve.py"
    sealed_tests = _verified_historical_source(
        test_path, SOURCE_SEAL, data["historical_source_sha256"][test_path]
    )
    functions = {
        n.name for n in ast.walk(ast.parse(sealed_tests)) if isinstance(n, ast.FunctionDef)
    }
    assert len(data["synthetic_test_matrix"]) == 15
    assert all(
        row["test_function"] in functions and row["status"] == "PASS_SYNTHETIC_ONLY"
        for row in data["synthetic_test_matrix"].values()
    )


def test_historical_source_and_frozen_artifact_original_bytes():
    data = json.loads(EVIDENCE.read_bytes())
    assert data["historical_source_commits"] == SOURCE_COMMITS
    assert set(data["historical_source_sha256"]) == set(SOURCE_COMMITS)
    for path, expected in data["historical_source_sha256"].items():
        _verified_historical_source(path, SOURCE_COMMITS[path], expected)
    assert len(data["frozen_history_sha256"]) == 7
    for path, expected in data["frozen_history_sha256"].items():
        _verified_frozen_file(path, expected)
    for path, expected in data["artifact_sha256"].items():
        _verified_frozen_file(path, expected)


@pytest.mark.parametrize("fault", ["wrong_existing_commit", "missing_commit", "wrong_hash"])
def test_historical_source_audit_rejects_wrong_commit_or_hash(fault):
    data = json.loads(EVIDENCE.read_bytes())
    path = "backend/research/v019_daily_curve.py"
    commit = SOURCE_SEAL
    expected = data["historical_source_sha256"][path]
    if fault == "wrong_existing_commit":
        commit = START_MAIN
    elif fault == "missing_commit":
        commit = "0" * 40
    else:
        expected = "0" * 64
    with pytest.raises(AssertionError):
        _verified_historical_source(path, commit, expected)


def test_runtime_test_source_uses_fixed_snapshot_not_future_worktree_bytes():
    data = json.loads(EVIDENCE.read_bytes())
    path = "backend/tests/area_yield/test_v0_19_s2_daily_curve.py"
    expected = data["historical_source_sha256"][path]
    original = _verified_historical_source(path, SOURCE_SEAL, expected)
    # This file itself already has legitimate additive audit tests beyond the
    # original runtime-test seal. The historical assertion still passes.
    assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != expected
    assert (
        hashlib.sha256(original + b"\n# SYNTHETIC future test addition\n").hexdigest() != expected
    )
    assert _verified_historical_source(path, SOURCE_SEAL, expected) == original


def test_frozen_document_corruption_is_still_rejected(tmp_path):
    data = json.loads(EVIDENCE.read_bytes())
    path, expected = next(iter(data["frozen_history_sha256"].items()))
    altered = tmp_path / path
    altered.parent.mkdir(parents=True, exist_ok=True)
    altered.write_bytes((ROOT / path).read_bytes() + b"\nSYNTHETIC corruption\n")
    with pytest.raises(AssertionError, match="FROZEN_SHA256_MISMATCH"):
        _verified_frozen_file(path, expected, root=tmp_path)


def test_fixed_source_delivery_interval_and_commit_gate_not_future_head():
    import subprocess

    data = json.loads(EVIDENCE.read_bytes())
    allowed = set(data["allowed_new_paths"])
    assert allowed == {
        "backend/research/__init__.py",
        "backend/research/v019_daily_curve.py",
        "backend/tests/area_yield/test_v0_19_s2_daily_curve.py",
        "docs/v0-19/s2/daily-curve-candidate-r1.md",
        "docs/v0-19/s2/daily-curve-method-config-r1.json",
        "docs/v0-19/evidence/v0.19-s2-synthetic-structure-r1.json",
        "docs/v0-19/evidence/v0.19-s2-daily-curve-candidate-r1.json",
    }
    rows = subprocess.check_output(
        ["git", "diff", "--name-status", START_MAIN, SOURCE_SEAL], cwd=ROOT, text=True
    ).splitlines()
    assert {r.split("\t")[1] for r in rows} == allowed - {str(EVIDENCE.relative_to(ROOT))}
    assert all(r.startswith("A\t") for r in rows)
    committed = subprocess.check_output(
        ["git", "show", "-s", "--format=%cI", SOURCE_SEAL], cwd=ROOT, text=True
    ).strip()
    assert datetime.fromisoformat(committed) >= datetime.fromisoformat(
        data["delivery_gate_observed"]["updated_at"]
    )
