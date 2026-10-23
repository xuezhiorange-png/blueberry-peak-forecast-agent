"""Actual synthetic five-method arithmetic, diagnostics, isolation and report tests."""

import copy
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from backend.research import v019_accuracy_models as models
from backend.research import v019_owner_replay as owner
from backend.research import v019_real_training_cli as s4
from backend.research import v019_research_execution as engine
from backend.research import v019_stability as stable
from backend.research import v019_stability_cli as cli
from backend.research import v019_stability_diagnostics as diag
from backend.research import v019_stability_report as reporting
from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    generate_candidate,
)
from backend.research.v019_synthetic_validation import digest
from backend.tests.area_yield.test_v0_19_stability import original, season


def synthetic() -> dict[str, Any]:
    old: dict[str, Any] = {"experiments": {}, "base_names": {}}
    new: dict[str, Any] = {
        "experiments": {},
        "two_season_identity_intersection": ["SYNTHETIC-b"],
        "training_identity_sets": {s: ["SYNTHETIC-b"] for s in stable.SEASONS},
    }
    labels, refs, fits = {}, {}, {}
    inventory = [
        {
            "base_id": "SYNTHETIC-b",
            "season": s,
            "status": "ADMIT",
            "area_mu": "1",
            "members": ["a" * 64],
            "daily_count": 290 if s == "2023-2024" else 289,
        }
        for s in stable.SEASONS
    ]
    for e, year in (("A", 2024), ("B", 2025)):
        years = (2023,) if e == "A" else (2023, 2024)
        fit = original(years)
        starts = [date(y, 7, 1) for y in years]
        norm = [
            {
                "base_id": "SYNTHETIC-b",
                "season_start": str(d),
                "start": str(d),
                "area_mu": "1",
                "baseline": ["1"] * 7,
                "actual": ["2" if d.year == 2023 else "4"] * 7,
            }
            for d in starts
        ]
        fits[e] = {
            "fitted": fit,
            "normalized_training_rows": norm,
            "training_seasons": [f"{y}-{y + 1}" for y in years],
            "sha256": digest(norm),
        }
        summaries = tuple(season(y, "2" if y == 2023 else "4") for y in years)
        base_ids = ("SYNTHETIC-b", "SYNTHETIC-u", "SYNTHETIC-z")
        sf = stable.fit_consensus(
            summaries,
            fit,
            evaluation_start=date(year, 7, 1),
            profile_sha256="c" * 64,
            base_ids=base_ids,
        )
        curves: dict[str, Any] = {m: {} for m in s4.METHODS}
        new_curves, actual, members = {}, {}, []
        start = date(year, 7, 1)
        for bid in base_ids:
            value = "0.000000" if bid.endswith("z") else "1.000000"
            rr = tuple(DailyKg(start + timedelta(days=i), Decimal(value)) for i in range(21))
            curves["baseline"][bid] = rr
            curves["S2"][bid] = generate_candidate(
                CurveInput(start, start, rr[-1].day, rr, "a" * 64, BASELINE_POLICY, "Asia/Shanghai")
            ).rows
            for m, result in models.predict(fit, bid, start, rr).items():
                curves[m][bid] = result
            new_curves[bid] = engine._serialize(stable.predict(sf, bid, start, rr))
            amount = (
                "0"
                if bid.endswith("z")
                else ("1" if e == "A" else "1.5")
                if bid.endswith("b")
                else "4"
            )
            actual[bid] = tuple(DailyKg(r.day, Decimal(amount)) for r in rr)
            old["base_names"][bid] = bid
            for w, n in (("H7_PREFIX", 7), ("H15_LOCAL", 15)):
                members.append(
                    {
                        "candidate_id": digest((e, bid, w)),
                        "base_id": bid,
                        "target_start": str(start),
                        "target_end": str(start + timedelta(days=n - 1)),
                        "window": w,
                    }
                )
        refs[e] = s4.evaluate(curves, actual, members, ["SYNTHETIC-b"], "SYNTHETIC_LABELS")
        old["experiments"][e] = {
            "curves": {
                m: {b: engine._serialize(rr) for b, rr in cc.items()} for m, cc in curves.items()
            },
            "members": members,
            "training_bases": ["SYNTHETIC-b"],
        }
        new["experiments"][e] = {
            "curves": new_curves,
            "members": copy.deepcopy(members),
            "fitted": sf,
            "failures": [],
        }
        labels[e] = actual
    frozen = {"experiments": refs}
    comparison = diag.five_model_evaluation(
        old, new, labels, frozen, {e: "SYNTHETIC_LABELS" for e in refs}
    )
    factors = diag.factor_diagnostics(
        {"admission": {"inventory": inventory}}, {"experiments": fits}, new
    )
    analysis = diag.analyze(old, new, labels, comparison, factors)
    return {
        "old": old,
        "new": new,
        "labels": labels,
        "reference": frozen,
        "comparison": comparison,
        "factors": factors,
        "analysis": analysis,
        "names": old["base_names"],
        "execution_kind": "SYNTHETIC_END_TO_END",
    }


def test_complete_synthetic_five_model_run_and_exact_old_parity() -> None:
    run = synthetic()
    for e, ex in run["comparison"]["experiments"].items():
        assert ex["old_four_metric_parity"]
        assert ex["comparison_status"] == "COMPLETE_FIVE_MODEL_COMMON_COHORT"
        for _w, groups in ex["groups"].items():
            assert all(
                v["metrics"]["DAILY_WAPE"]["candidate"]["denominator"]
                == groups["baseline"]["metrics"]["DAILY_WAPE"]["candidate"]["denominator"]
                for v in groups.values()
            )
            if e == "A":
                assert groups[stable.METHOD] == groups["baseline"]
    assert run["analysis"]["experiments"]["B"]["fallback_base_count"] == 2
    assert run["factors"]["global_ratio_decomposition"]["same_2023_rows_fold_A"]["factor"] == "2"


def test_error_conservation_months_bins_weights_and_zero_base() -> None:
    run = synthetic()
    for _e, result in run["analysis"]["experiments"].items():
        assert sum(r["day_occurrences"] for r in result["unique_base_days"].values()) == 45
        for _w, audit in result["official_repeated_window_accounting"].items():
            a = audit["aggregate"]
            assert sum(Decimal(r["actual_kg"]) for r in audit["by_month"].values()) == Decimal(
                a["actual_kg"]
            )
            assert sum(
                Decimal(r["actual_kg"]) for r in audit["by_season_7day_bin"].values()
            ) == Decimal(a["actual_kg"])
            for m, v in a["models"].items():
                assert Decimal(v["absolute_error_kg"]) == Decimal(
                    v["overprediction_error_kg"]
                ) + Decimal(v["underprediction_error_kg"])
                assert Decimal(v["signed_bias_kg"]) == Decimal(
                    v["overprediction_error_kg"]
                ) - Decimal(v["underprediction_error_kg"])
                assert audit["base_equal_WAPE"][m]["computed_base_count"] == 2
                assert audit["base_equal_WAPE"][m]["not_computable"] == [
                    {"base_id": "SYNTHETIC-z", "reason": "ZERO_ACTUAL_DENOMINATOR"}
                ]
            trade = audit["observed_harm_gain"]["volume_to_stable_tradeoff"]
            assert Decimal(trade["harm_avoided_kg"]) > 0
            assert Decimal(trade["gain_forgone_kg"]) > 0


def test_missing_candidate_is_blocked_not_smaller_successful_cohort() -> None:
    run = synthetic()
    del run["new"]["experiments"]["B"]["curves"]["SYNTHETIC-b"]
    result = diag.five_model_evaluation(
        run["old"],
        run["new"],
        run["labels"],
        run["reference"],
        {e: "SYNTHETIC_LABELS" for e in ("A", "B")},
    )
    b = result["experiments"]["B"]
    assert b["comparison_status"].startswith("BLOCKED")
    assert not b["old_four_metric_parity"]
    assert b["full_C0_actual_denominators"]["H7_PREFIX"]["candidate_members"] == 3
    with pytest.raises(ValueError, match="INCOMPLETE"):
        diag.analyze(run["old"], run["new"], run["labels"], result, run["factors"])


def test_old_curve_or_members_tamper_rejected() -> None:
    run = synthetic()
    run["old"]["experiments"]["B"]["curves"]["baseline"]["SYNTHETIC-b"][0]["kg"] = "99"
    with pytest.raises(ValueError, match="METRIC_DRIFT"):
        diag.five_model_evaluation(
            run["old"],
            run["new"],
            run["labels"],
            run["reference"],
            {e: "SYNTHETIC_LABELS" for e in ("A", "B")},
        )
    run = synthetic()
    run["new"]["experiments"]["B"]["members"].pop()
    with pytest.raises(ValueError, match="C0"):
        diag.five_model_evaluation(
            run["old"],
            run["new"],
            run["labels"],
            run["reference"],
            {e: "SYNTHETIC_LABELS" for e in ("A", "B")},
        )


def test_reports_have_computed_svg_charts_and_repeatable_bytes(tmp_path: Path) -> None:
    run = synthetic()
    files = reporting.report_files(run)
    assert files == reporting.report_files(run)
    assert {
        "report.md",
        "report.html",
        "stability-analysis.json",
        "factor-diagnostics.json",
        "five-model-comparison.json",
    } <= set(files)
    charts = {n: raw for n, raw in files.items() if n.endswith(".svg")}
    assert len(charts) >= 5
    for raw in charts.values():
        assert ElementTree.fromstring(raw).tag.endswith("svg")
        assert b"data-sha256" in raw
    assert b"EXPLORATORY" in files["report.html"] and b"BASELINE_FALLBACK" in files["report.md"]
    owner.write_bundle(tmp_path / "new", files, {"synthetic": True})
    with pytest.raises(FileExistsError):
        owner.write_bundle(tmp_path / "new", files, {"synthetic": True})
    assert (tmp_path / "new/report.md").stat().st_mode & 0o777 == 0o600


def test_fixed_old_inputs_cannot_be_replaced_by_a_flag(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        cli.load_old(tmp_path)


def test_old_source_identity_is_fixed_git_not_worktree(monkeypatch: pytest.MonkeyPatch) -> None:
    before = cli.historical_s4_source_identity()
    assert len(before) == 64
    original_read = Path.read_bytes

    def changed(path: Path) -> bytes:
        if path.name == "v019_accuracy_models.py":
            return b"future legitimate research source"
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert cli.historical_s4_source_identity() == before
    monkeypatch.setattr(cli, "S4_CODE_SHA", "0" * 40)
    with pytest.raises(ValueError, match="HISTORICAL_SOURCE_UNAVAILABLE"):
        cli.historical_s4_source_identity()


@pytest.mark.parametrize("failure", ["receipt", "recompute"])
def test_verification_failures_prevent_target_report_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    p = {"sha256": "a" * 64, "payload": {"experiments": {}}}
    monkeypatch.setattr(cli, "load_new", lambda _: p)
    reads = []
    original_read = owner.read_bytes

    def observed(path: Path, sha: str) -> bytes:
        if path.name == "comparison.json":
            reads.append(path)
        return original_read(path, sha)

    monkeypatch.setattr(owner, "read_bytes", observed)
    owner.write_bundle(
        tmp_path / "v",
        {
            "verification.json": json.dumps(
                {
                    "verified": failure != "receipt",
                    "prediction_sha256": p["sha256"],
                    "code_identity": cli.code_identity(),
                }
            ).encode()
        },
        {},
    )

    def broken(*_: Any) -> None:
        raise ValueError("RECOMPUTATION_FAILED")

    monkeypatch.setattr(cli, "verify_run", broken)
    with pytest.raises(ValueError):
        cli.score_run(tmp_path, tmp_path, tmp_path / "v")
    assert reads == []
