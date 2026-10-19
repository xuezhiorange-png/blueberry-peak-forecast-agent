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
