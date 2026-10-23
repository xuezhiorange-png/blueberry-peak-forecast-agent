"""Synthetic S5 rules, before implementation; no private data used by CI."""

from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

import pytest

from backend.research import v019_accuracy_models as old
from backend.research import v019_stability as stable
from backend.research.v019_daily_curve import DailyKg, _micro
from backend.research.v019_synthetic_validation import digest


def season(year: int, actual: str, predicted: str = "1") -> dict[str, Any]:
    start, end = date(year, 7, 1), date(year + 1, 4, 15)
    days = (end - start).days + 1
    return stable.summarize_season(
        "SYNTHETIC-b",
        f"{year}-{year + 1}",
        Decimal(1),
        tuple(DailyKg(start + timedelta(days=i), Decimal(actual)) for i in range(days)),
        tuple(DailyKg(start + timedelta(days=i), Decimal(predicted)) for i in range(days)),
        source_sha256="a" * 64,
        members_sha256="b" * 64,
        profile_sha256="c" * 64,
    )


def original(years: tuple[int, ...] = (2023, 2024)) -> dict[str, Any]:
    return old.fit(
        tuple(
            old.TrainingBin(
                "SYNTHETIC-b",
                date(y, 7, 1),
                date(y, 7, 1),
                Decimal(1),
                (Decimal(1),) * 7,
                (Decimal(2 if y == 2023 else 4),) * 7,
                "a" * 64,
            )
            for y in years
        ),
        evaluation_start=date(max(years) + 1, 7, 1),
        data_class="SYNTHETIC",
    )


def fitted() -> dict[str, Any]:
    return stable.fit_consensus(
        (season(2023, "2"), season(2024, "4")),
        original(),
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b", "SYNTHETIC-unseen"),
    )


def test_fixed_formula_and_decimal_context() -> None:
    f = fitted()
    r = f["base_records"]["SYNTHETIC-b"]
    with localcontext(Context(prec=50)):
        expected = Decimal(1) + (Decimal(3) - 1) / 3
    assert Decimal(r["F1"]) == 2 and Decimal(r["F2"]) == 4
    assert Decimal(r["spread"]) == 2
    assert Decimal(r["stable_factor"]) == expected
    assert r["mode"] == "TWO_SEASON_CONSENSUS"
    assert f["method"] == "TWO_SEASON_CONSENSUS_SHRINK_V1"


def test_single_season_and_unseen_fall_back_without_validation_labels() -> None:
    f = stable.fit_consensus(
        (season(2023, "2"),),
        original((2023,)),
        evaluation_start=date(2024, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b", "SYNTHETIC-unseen"),
    )
    assert all(r["mode"] == "BASELINE_FALLBACK" for r in f["base_records"].values())
    assert all(Decimal(r["stable_factor"]) == 1 for r in f["base_records"].values())
    with pytest.raises(ValueError, match="TEMPORAL"):
        stable.fit_consensus(
            (season(2023, "2"), season(2024, "4")),
            original((2023,)),
            evaluation_start=date(2024, 7, 1),
            profile_sha256="c" * 64,
            base_ids=("SYNTHETIC-b",),
        )


def test_zero_denominator_fallback_and_all_zero_actuals() -> None:
    f = stable.fit_consensus(
        (season(2023, "2", "0"), season(2024, "4")),
        original(),
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b",),
    )
    assert f["base_records"]["SYNTHETIC-b"]["reason"] == "ZERO_BASELINE_DENOMINATOR"
    z = stable.fit_consensus(
        (season(2023, "0"), season(2024, "0")),
        original(),
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b",),
    )
    assert Decimal(z["base_records"]["SYNTHETIC-b"]["spread"]) == 0
    assert z["base_records"]["SYNTHETIC-b"]["mode"] == "TWO_SEASON_CONSENSUS"


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity", "0.0000001"])
def test_illegal_quantity_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        season(2023, value)


def test_order_determinism_duplicate_and_profile_conflict() -> None:
    ss = (season(2023, "2"), season(2024, "4"))
    kwargs = dict(
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b", "SYNTHETIC-unseen"),
    )
    assert stable.fit_consensus(ss[::-1], original(), **kwargs) == fitted()
    with pytest.raises(ValueError):
        stable.fit_consensus((ss[0], ss[0]), original(), **kwargs)
    bad = {**ss[1], "profile_sha256": "d" * 64}
    bad["sha256"] = digest({k: v for k, v in bad.items() if k != "sha256"})
    with pytest.raises(ValueError, match="PROFILE"):
        stable.fit_consensus((ss[0], bad), original(), **kwargs)


def test_prediction_determinism_bin_mass_zero_and_fallback() -> None:
    start = date(2025, 7, 1)
    rr = tuple(
        DailyKg(start + timedelta(days=i), Decimal(0 if i < 7 else "0.000001")) for i in range(16)
    )
    f = fitted()
    result = stable.predict(f, "SYNTHETIC-b", start, rr)
    assert result == stable.predict(f, "SYNTHETIC-b", start, rr)
    assert result[:7] == rr[:7]
    assert stable.predict(f, "SYNTHETIC-unseen", start, rr) == rr
    assert len(result) == len(rr) and all(
        r.kg >= 0 and r.kg.as_tuple().exponent == -6 for r in result
    )
    for i in range(0, len(rr), 7):
        with localcontext(Context(prec=50)):
            n = sum(_micro(r.kg) for r in rr[i : i + 7])
            expected = int(
                (n * Decimal(f["base_records"]["SYNTHETIC-b"]["stable_factor"])).to_integral_value(
                    rounding="ROUND_HALF_EVEN"
                )
            )
        assert sum(_micro(r.kg) for r in result[i : i + 7]) == expected
    with pytest.raises(ValueError):
        stable.predict(f, "OUTSIDE-COHORT", start, rr)
    with pytest.raises(ValueError):
        stable.predict(f, "SYNTHETIC-b", start, rr[:-2] + rr[-1:])


def test_modified_seal_and_factor_rejected() -> None:
    f = fitted()
    f["base_records"]["SYNTHETIC-b"]["stable_factor"] = "999"
    with pytest.raises(ValueError, match="SEAL"):
        stable.predict(f, "SYNTHETIC-b", date(2025, 7, 1), (DailyKg(date(2025, 7, 1), Decimal(1)),))


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_invalid_area_cannot_become_training(value: str) -> None:
    start = date(2023, 7, 1)
    rr = tuple(DailyKg(start + timedelta(days=i), Decimal(1)) for i in range(290))
    with pytest.raises(ValueError):
        stable.summarize_season(
            "SYNTHETIC-b",
            "2023-2024",
            Decimal(value),
            rr,
            rr,
            source_sha256="a" * 64,
            members_sha256="b" * 64,
            profile_sha256="c" * 64,
        )


def test_full_calendar_order_missing_duplicate_and_terminal_days() -> None:
    start = date(2023, 7, 1)
    rr = tuple(DailyKg(start + timedelta(days=i), Decimal(1)) for i in range(290))
    kwargs = dict(source_sha256="a" * 64, members_sha256="b" * 64, profile_sha256="c" * 64)
    a = stable.summarize_season("SYNTHETIC-b", "2023-2024", Decimal(1), rr, rr, **kwargs)
    b = stable.summarize_season(
        "SYNTHETIC-b", "2023-2024", Decimal(1), rr[::-1], rr[::-1], **kwargs
    )
    assert a == b and a["days"] == 290 and Decimal(a["actual_kg"]) == 290
    for bad in (rr[:-1], rr[:-1] + rr[:1]):
        with pytest.raises(ValueError, match="COMPLETE_AUTHORIZED"):
            stable.summarize_season("SYNTHETIC-b", "2023-2024", Decimal(1), bad, rr, **kwargs)


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity"])
def test_invalid_original_parameters_do_not_gain_a_new_seal(value: str) -> None:
    old_fit = original()
    old_fit["global_factor"] = value
    old_fit["sha256"] = digest({k: v for k, v in old_fit.items() if k != "sha256"})
    with pytest.raises(ValueError):
        stable.fit_consensus(
            (season(2023, "2"), season(2024, "4")),
            old_fit,
            evaluation_start=date(2025, 7, 1),
            profile_sha256="c" * 64,
            base_ids=("SYNTHETIC-b",),
        )


def test_matching_seasons_retain_original_factor_and_zero_fit_stays_zero() -> None:
    fit = stable.fit_consensus(
        (season(2023, "2"), season(2024, "2")),
        original(),
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b",),
    )
    r = fit["base_records"]["SYNTHETIC-b"]
    assert Decimal(r["weight"]) == 1 and Decimal(r["stable_factor"]) == 3
    old_fit = original()
    old_fit["global_factor"] = "0"
    old_fit["base_factors"]["SYNTHETIC-b"] = "0"
    old_fit["sha256"] = digest({k: v for k, v in old_fit.items() if k != "sha256"})
    zero = stable.fit_consensus(
        (season(2023, "0"), season(2024, "0")),
        old_fit,
        evaluation_start=date(2025, 7, 1),
        profile_sha256="c" * 64,
        base_ids=("SYNTHETIC-b",),
    )
    rr = (DailyKg(date(2025, 7, 1), Decimal(1)),)
    assert stable.predict(zero, "SYNTHETIC-b", date(2025, 7, 1), rr)[0].kg == 0
