"""S6 end-to-end real Ridge/scoring/report math using only synthetic records."""

import copy
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

import pytest

from backend.research import v019_origin_cli as cli
from backend.research import v019_origin_evaluation as ev
from backend.research import v019_origin_features as f
from backend.research import v019_origin_reference as reference
from backend.research import v019_origin_report as report
from backend.research import v019_origin_sources as sources
from backend.research import v019_owner_replay as owner
from backend.research.v019_daily_curve import DailyKg
from backend.research.v019_synthetic_validation import digest


def synthetic():
    history = []
    labels = []
    records = {}
    members = {"A": [], "B": []}
    actual = {}
    statics = {}
    for year in (2023, 2024, 2025):
        season = f"{year}-{year + 1}"
        for i in range(100):
            day = str(date(year, 7, 1) + timedelta(days=i))
            kg = str((i % 7 + 1) * 2)
            history.append(
                {
                    "base_id": "SYNTHETIC-a",
                    "season": season,
                    "date": day,
                    "kg": kg,
                    "state": "VALID_OBSERVED",
                    "source_sha256": "a" * 64,
                    "authority_sha256": "b" * 64,
                }
            )
            if year < 2025:
                labels.append({"base_id": "SYNTHETIC-a", "season": season, "date": day, "kg": kg})
        origins = (
            [date(2023, 8, 1) + timedelta(days=i) for i in range(5)]
            if year == 2023
            else [date(2024, 8, 1), date(2024, 8, 2)]
            if year == 2024
            else [date(2025, 8, 25), date(2025, 8, 26)]
        )
        for origin in origins:
            rr = f.snapshot("SYNTHETIC-a", season, origin, Decimal(100), history, 15)
            records[rr["row_key"]] = rr
            if year > 2023:
                e = "A" if year == 2024 else "B"
                for w, n in [("H7_PREFIX", 7), ("H15_LOCAL", 15)]:
                    members[e].append(
                        {
                            "base_id": "SYNTHETIC-a",
                            "candidate_id": digest((year, str(origin), w)),
                            "target_start": str(origin + timedelta(days=1)),
                            "target_end": str(origin + timedelta(days=n)),
                            "window": w,
                        }
                    )
        if year > 2023:
            e = "A" if year == 2024 else "B"
            actual[e] = {
                "SYNTHETIC-a": tuple(
                    DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
                    for r in history
                    if r["season"] == season
                )
            }
            statics[e] = {
                "SYNTHETIC-a": tuple(DailyKg(r.day, Decimal(5)) for r in actual[e]["SYNTHETIC-a"])
            }
    p = {
        "records": records,
        "members": members,
        "prior_bridge": {},
        "source_access_audit": {"synthetic": True},
    }
    fits, pred = cli.calculate(p, {"daily": labels}, "a" * 64)
    comparisons = {
        e: ev.evaluate(
            pred["payload"]["experiments"][e],
            members[e],
            actual[e],
            statics[e],
            "2024-2025" if e == "A" else "2025-2026",
        )
        for e in ("A", "B")
    }
    profiles = {
        e: {
            "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
            "validation_labels_used": False,
            "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
            "profile_kg_per_mu_by_7_day_bin": {"3": "1", "5": "2"}
            if e == "A"
            else {str(i): "1.5" for i in range(42)},
            "train_row_set_hash": e * 64,
        }
        for e in ["A", "B"]
    }
    trace = {
        "training-manifest.json": {
            "folds": {
                e: {
                    "train_row_set_hash": e * 64,
                    "train_seasons": ["2023-2024"] if e == "A" else ["2023-2024", "2024-2025"],
                    "train_unique_base_count": 1,
                    "train_unique_base_season_count": 1 if e == "A" else 2,
                }
                for e in ["A", "B"]
            }
        },
        "input-manifest.json": {"SYNTHETIC": True},
    }
    ref = reference.audit(
        {
            "profiles": profiles,
            "registry": {"bases": [{"base_id": "SYNTHETIC-a", "productive_area_mu": "100"}]},
            "admission": {"inventory": []},
        },
        trace,
    )
    return {
        "features": p,
        "fits": fits["payload"],
        "predictions": pred["payload"],
        "comparison": {"experiments": comparisons},
        "actual": actual,
        "reference": ref,
        "names": {"SYNTHETIC-a": "SYNTHETIC BASE"},
    }, statics


def test_end_to_end_numerical_shared_denominators_and_report(tmp_path: Path):
    run, _ = synthetic()
    for ex in run["comparison"]["experiments"].values():
        assert ex["candidate_count"] == 4 and ex["common_computed_count"] == 4
        for w, g in ex["groups"].items():
            m = g["paired"]["metrics"]["DAILY_WAPE"]
            assert (
                m["common_count"] == 2
                and m["baseline"]["denominator"] == m["candidate"]["denominator"]
            )
            assert (
                m["baseline"]["denominator"]
                == g["static_on_common"]["metrics"]["DAILY_WAPE"]["baseline"]["denominator"]
            )
            assert g["paired"]["metrics"]["SEASON_TOTAL_WAPE"]["common_count"] == 0
            if w == "H7_PREFIX":
                assert (
                    g["paired"]["metrics"]["ROLLING_7DAY_PEAK_START_MAE"]["candidate"]["value"]
                    == "0"
                )
    out = report.files(run)
    assert out == report.files(run)
    # One synthetic Base per split: one metric chart plus two split examples.
    assert len(report.examples(run)) == 2
    assert len([n for n in out if n.endswith(".svg")]) == 3
    for n, raw in out.items():
        if n.endswith(".svg"):
            assert ElementTree.fromstring(raw).tag.endswith("svg")
    owner.write_bundle(tmp_path / "private", out, {"synthetic": True})
    with pytest.raises(FileExistsError):
        owner.write_bundle(tmp_path / "private", out, {"synthetic": True})
    data = json.loads(out["dynamic-comparison.json"])
    assert all("2024-08-02" <= r["date"] <= "2024-08-17" for r in data["actual_daily"]["A"])


@pytest.mark.parametrize("rejected", [1, 2])
def test_partial_and_all_rejected_keep_c0_denominators_and_failures(rejected):
    run, static = synthetic()
    ex = run["predictions"]["experiments"]["B"]
    members = ex["members"]
    for key in sorted(ex["origins"])[:rejected]:
        ex["origins"][key] = {"status": "NOT_COMPUTABLE", "reasons": ["PAST_UNKNOWN"]}
    out = ev.evaluate(ex, members, run["actual"]["B"], static["B"], "2025-2026")
    assert out["candidate_count"] == 4 and out["not_computable_count"] == rejected * 2
    assert out["common_computed_count"] == (2 - rejected) * 2
    assert len(out["member_ledger"]) == 4
    for w, g in out["groups"].items():
        m = g["paired"]["metrics"]["DAILY_WAPE"]
        assert m["candidate_count"] == 2 and m["common_count"] == 2 - rejected
        assert g["static_full_C0"]["metrics"]["DAILY_WAPE"]["common_count"] == 2
        assert m["baseline"]["denominator"] == m["candidate"]["denominator"]
        if rejected == 2:
            assert m["baseline"]["value"] is None and out["classification"] == "NOT_COMPARABLE"
        else:
            assert Decimal(m["baseline"]["denominator"]) < Decimal(
                out["full_C0_actual_denominators"][w]["actual_kg"]
            )


def test_zero_actuals_missing_label_duplicate_c0_and_profile_hash_fail():
    run, static = synthetic()
    ex = run["predictions"]["experiments"]["A"]
    members = ex["members"]
    zero = {
        b: tuple(DailyKg(r.day, Decimal(0)) for r in rr) for b, rr in run["actual"]["A"].items()
    }
    result = ev.evaluate(ex, members, zero, static["A"], "2024-2025")
    assert (
        result["groups"]["H7_PREFIX"]["paired"]["metrics"]["SINGLE_DAY_PEAK_DATE_MAE"][
            "common_count"
        ]
        == 0
    )
    assert (
        result["groups"]["H7_PREFIX"]["paired"]["metrics"]["SINGLE_DAY_PEAK_QUANTITY_MAE"][
            "common_count"
        ]
        == 2
    )
    with pytest.raises(ValueError, match="DUPLICATE"):
        ev.evaluate(ex, members + members, zero, static["A"], "2024-2025")
    missing = copy.deepcopy(run["actual"]["A"])
    missing["SYNTHETIC-a"] = ()
    assert ev.evaluate(ex, members, missing, static["A"], "2024-2025")["not_computable_count"] == 4
    profile = {
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "validation_labels_used": False,
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {"0": "1"},
        "train_row_set_hash": "a" * 64,
    }
    trace = {
        "training-manifest.json": {
            "folds": {"A": {"train_row_set_hash": "b" * 64, "train_seasons": ["2023-2024"]}}
        }
    }
    with pytest.raises(ValueError, match="TRACE"):
        reference.audit({"profiles": {"A": profile}}, trace)


def test_scoring_receipt_failure_does_not_open_label_sources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(
        cli,
        "read",
        lambda p, n: {"sha256": "a" * 64} if n != "verification.json" else {"verified": False},
    )

    def forbidden(*a, **kw):
        raise AssertionError("TARGET_SOURCE_READ")

    monkeypatch.setattr(cli.training, "load_training", forbidden)
    with pytest.raises(ValueError, match="VERIFICATION"):
        cli.score(tmp_path, tmp_path, tmp_path, tmp_path)


def test_old_zero_authority_only_transfers_with_exact_member_set():
    current = {
        "mapping": [
            {"research_base_id": "SYNTHETIC-a", "source_identity_sha256": "a" * 64},
            {"research_base_id": "SYNTHETIC-b", "source_identity_sha256": "c" * 64},
        ]
    }
    identity = [
        {
            "season": "2025-2026",
            "mapping_status": "EXACT",
            "canonical_base_id": b,
            "source_identity_sha256": "a" * 64,
        }
        for b in ["SYNTHETIC-a", "SYNTHETIC-b"]
    ]
    ledger = []
    overlay = []
    for bid in ["SYNTHETIC-a", "SYNTHETIC-b"]:
        for i in range(14):
            r = {
                "base_id": bid,
                "season": "2025-2026",
                "date": str(date(2025, 7, 22) + timedelta(days=i)),
                "source_sha256": sources.scope.SOURCE_SHA256,
                "mapped_observed_subtotal_kg": "0",
            }
            ledger.append(r)
            overlay.append(
                {
                    **r,
                    "authority_eligible_daily": "true",
                    "identity_unresolved_conflict": "false",
                    "source_coverage_status": "VERIFIED_SEASON_SOURCE_HASH",
                    "member_expected_count": "1",
                    "new_completeness_status": "AUTHORIZED_ZERO",
                    "new_quantity_status": "CONFIRMED_ZERO",
                    "new_quantity_kg": "0",
                    "source_row_count": "0",
                    "zero_basis": "EXPLICIT_BUSINESS_RULE_NO_HARVEST_RECORD_MEANS_ZERO",
                }
            )
    h, a = sources.bridge_prior(ledger, overlay, identity, current)
    assert a["SYNTHETIC-a"]["accepted_prior_days"] == 14
    assert a["SYNTHETIC-b"]["rejected_prior_days"] == 14
    assert all(
        r["kg"] is None and r["state"] == "UNKNOWN" for r in h if r["base_id"] == "SYNTHETIC-b"
    )
    with pytest.raises(ValueError, match="DUPLICATE"):
        sources.bridge_prior(ledger + ledger[:1], overlay, identity, current)


def test_candidate_counts_cannot_substitute_for_exact_member_payloads():
    with pytest.raises(ValueError, match="MEMBER_PAYLOAD"):
        sources.validate_members({"A": [], "B": [{"candidate_id": str(i)} for i in range(19032)]})
