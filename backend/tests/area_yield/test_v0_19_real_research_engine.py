"""Same file adapters and numerical pipeline; no private object is opened."""

import subprocess
import sys
import time
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_real_phase_a_adapter as file_io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_research_evaluation as scoring
from backend.research import v019_research_execution as execution
from backend.research import v019_synthetic_validation as math
from backend.tests.area_yield.build_v019_real_shape_fixture import build, write

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_real_rejection_precedes_input_access(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        cohort.load_inputs(tmp_path / "not-opened.json", auth.Context("REAL"), {})


@pytest.mark.parametrize("forged", [True, {"owner_authorized": True}, "APPROVED", None])
def test_unsigned_owner_decision_is_not_permission(forged: object) -> None:
    with pytest.raises(PermissionError):
        auth.require(auth.Context("REAL"), forged, "A_EXECUTION", "1" * 64)


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    directory = tmp_path_factory.mktemp("SYNTHETIC-REAL-SHAPE")
    started = time.monotonic()
    mp, mh, lp, lh, signer, grants = build(directory / "inputs")
    ctx = signer.context
    inputs = cohort.load_inputs(mp, ctx, grants, mh)
    candidate = cohort.candidates(inputs, ctx)
    dispositions = {
        r["candidate_id"]: {"status": "ADMIT", "reason": ""}
        for r in candidate["payload"]["members"]
    }
    review = cohort.review_candidates(candidate, dispositions)
    grants["PROTOCOL"] = signer.decision("PROTOCOL", math.digest(auth.restrictions()))
    grants["FORMAL_C0"] = signer.decision("FORMAL_C0", review["sha256"])
    formal = cohort.formalize(candidate, review, ctx, grants)
    grants["IMPLEMENTATION_REVIEW"] = signer.decision("IMPLEMENTATION_REVIEW", auth.code_identity())
    grants["A_EXECUTION"] = signer.decision("A_EXECUTION", formal["sha256"])
    seal = execution.run_a(mp, mh, formal, ctx, grants)
    sp = directory / "phase-a.json"
    write(sp, seal)
    grants["A_SEAL_REVIEW"] = signer.decision("A_SEAL_REVIEW", seal["sha256"])
    grants["B_LABEL_READ"] = signer.decision(
        "B_LABEL_READ",
        math.digest({"a_sha256": seal["sha256"], "path": str(lp), "label_sha256": lh}),
    )
    grants["B_SCORING"] = signer.decision(
        "B_SCORING", math.digest({"a_sha256": seal["sha256"], "label_sha256": lh})
    )
    report = scoring.run_b(sp, seal["sha256"], lp, lh, ctx, grants)
    return dict(
        directory=directory,
        mp=mp,
        mh=mh,
        lp=lp,
        lh=lh,
        signer=signer,
        grants=grants,
        ctx=ctx,
        inputs=inputs,
        candidate=candidate,
        review=review,
        formal=formal,
        seal=seal,
        sp=sp,
        report=report,
        seconds=time.monotonic() - started,
    )


def test_complete_39_base_numerical_pipeline(prepared: dict[str, Any]) -> None:
    p = prepared
    content = p["seal"]["payload"]["content"]
    assert len(content["full_curves"]) == content["full_support_calculation_count"] == 39
    assert len(content["members"]) == 9672 + 9360
    assert not content["failures"] and not content["labels_read"]
    report = p["report"]
    assert report["base_count"] == 39 and report["registered_count"] == 19032
    assert report["admitted_count"] == 19032  # SYNTHETIC simulation only
    for w, count in (("H7_PREFIX", 9672), ("H15_LOCAL", 9360)):
        m = report["groups"][w]["metrics"]
        assert set(m) == set(math.METRICS)
        assert m["DAILY_MAE"]["common_count"] == count
        assert Decimal(m["DAILY_MAE"]["baseline"]["value"]) > 0
        assert m["SEASON_TOTAL_WAPE"]["baseline"]["value"] is None
        assert m["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"] < count
    assert p["seal"]["payload"]["historical_issued_at"] is None
    assert auth.aware(p["seal"]["payload"]["executed_at"]).year >= 2026
    assert report["scope"]["strict_pit"] is False


def test_content_determinism_full_support_once_and_bin_mass(prepared: dict[str, Any]) -> None:
    p = prepared
    a = execution.run_a(p["mp"], p["mh"], p["formal"], p["ctx"], p["grants"])
    assert a["payload"]["content_sha256"] == p["seal"]["payload"]["content_sha256"]
    assert a["sha256"] != p["seal"]["sha256"]  # real execution clock is NOT forged
    c = a["payload"]["content"]
    assert c["full_support_calculation_count"] == 39
    for curves in c["full_curves"].values():
        b, v = curves["baseline"], curves["candidate"]
        assert len(b) == len(v) == 289
        for i in range(0, len(b), 7):
            assert sum(Decimal(r["kg"]) for r in b[i : i + 7]) == sum(
                Decimal(r["kg"]) for r in v[i : i + 7]
            )
        assert all(Decimal(r["kg"]) >= 0 and Decimal(r["kg"]).as_tuple().exponent == -6 for r in v)


@pytest.mark.parametrize(
    "key", ["PROTOCOL", "FORMAL_C0", "IMPLEMENTATION_REVIEW", "A_EXECUTION", "A_INPUT_READ"]
)
def test_each_a_permission_prevents_input_access(
    prepared: dict[str, Any], key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = prepared
    grants = {k: v for k, v in p["grants"].items() if k != key}

    def forbidden(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("BUSINESS_INPUT_OPENED")

    monkeypatch.setattr(file_io, "_read_pinned", forbidden)
    with pytest.raises(PermissionError):
        execution.run_a(p["mp"], p["mh"], p["formal"], p["ctx"], grants)


@pytest.mark.parametrize("key", ["B_SCORING", "B_LABEL_READ", "A_SEAL_REVIEW"])
def test_each_b_permission_prevents_label_access(
    prepared: dict[str, Any], key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = prepared
    grants = {k: v for k, v in p["grants"].items() if k != key}

    def forbidden(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("LABEL_OPENED")

    monkeypatch.setattr(file_io, "_read_pinned", forbidden)
    with pytest.raises(PermissionError):
        scoring.run_b(p["sp"], p["seal"]["sha256"], p["lp"], p["lh"], p["ctx"], grants)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("subject", "0" * 64),
        ("signature", "AA=="),
        ("mode", "REAL"),
        ("code_sha256", "0" * 64),
        ("key_id", "REVIEWER"),
        ("expires_at", "2000-01-01T00:00:00Z"),
    ],
)
def test_signed_decision_scope_and_signature(
    prepared: dict[str, Any], field: str, bad: str
) -> None:
    p = prepared
    grants = deepcopy(p["grants"])
    target = grants["A_EXECUTION"] if field == "signature" else grants["A_EXECUTION"]["payload"]
    target[field] = bad
    with pytest.raises(PermissionError):
        auth.require(p["ctx"], grants, "A_EXECUTION", p["formal"]["sha256"])


def test_no_candidate_shrinking_and_independent_windows(prepared: dict[str, Any]) -> None:
    p = prepared
    d = {
        r["candidate_id"]: {"status": "ADMIT", "reason": ""}
        for r in p["candidate"]["payload"]["members"]
    }
    key = next(iter(d))
    del d[key]
    with pytest.raises(ValueError, match="ALL_CANDIDATES"):
        cohort.review_candidates(p["candidate"], d)
    d[key] = {"status": "REJECT", "reason": "SYNTHETIC_PRE_LABEL_MISSING_AUTHORITY"}
    review = cohort.review_candidates(p["candidate"], d)
    assert len(review["payload"]["members"]) == 19032
    with pytest.raises(PermissionError):
        cohort.formalize(p["candidate"], review, p["ctx"], p["grants"])


def test_actual_label_missing_duplicate_zero_and_unit_rules(prepared: dict[str, Any]) -> None:
    p = prepared
    labels = auth.read_json(p["lp"])
    content = p["seal"]["payload"]["content"]
    duplicate = {**labels, "rows": labels["rows"] + labels["rows"][:1]}
    rows, invalid = scoring._label_rows(duplicate, content, p["ctx"], clock=auth.now())
    first = labels["rows"][0]
    key = first["base_id"], first["date"]
    assert key in invalid and key not in rows
    missing = {**labels, "rows": labels["rows"][1:]}
    rows, _ = scoring._label_rows(missing, content, p["ctx"], clock=auth.now())
    assert key not in rows  # never filled with zero
    for value in ("-1", "NaN", "0.0000001", "0.0078125"):
        altered = {**labels, "rows": [{**first, "kg": value}]}
        _, invalid = scoring._label_rows(altered, content, p["ctx"], clock=auth.now())
        assert key in invalid
    for field, value in (
        ("unit", "tonnes"),
        ("physical_basis", "FACTORY_RECEIPTS"),
        ("data_class", "REAL"),
    ):
        with pytest.raises(ValueError):
            scoring._label_rows({**labels, field: value}, content, p["ctx"], clock=auth.now())


def test_original_strict_path_and_real_routes_remain_closed(
    prepared: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.research import v019_owner_scope_adapter, v019_real_phase_a_adapter

    for fn in (
        v019_owner_scope_adapter.generate_real_predictions,
        v019_real_phase_a_adapter.generate_real_predictions,
    ):
        with pytest.raises(PermissionError):
            fn(owner_authorized=True)
    for name in ("REAL_PREDICTION_AUTHORIZED", "OWNER_AUTHORIZED", "REAL_SCORING_AUTHORIZED"):
        monkeypatch.setenv(name, "true")
    with pytest.raises(PermissionError):
        auth.require(
            auth.Context("REAL", prepared["ctx"].synthetic_roots),
            prepared["grants"],
            "A_EXECUTION",
            prepared["formal"]["sha256"],
        )


def test_independent_a_b_processes_and_reports(prepared: dict[str, Any]) -> None:
    p = prepared
    root = p["directory"]
    roots = root / "synthetic-roots.json"
    write(roots, {"synthetic_only": True, "keys": p["ctx"].synthetic_roots})
    formal_path = root / "formal.json"
    write(formal_path, p["formal"])
    ga = root / "a-grants.json"
    write(ga, p["grants"])
    command = [sys.executable, "-m", "backend.research.v019_research_cli"]
    common = ["--mode", "SYNTHETIC", "--synthetic-roots", str(roots)]
    subprocess.run(
        command
        + [
            "stage-a",
            *common,
            "--grants",
            str(ga),
            "--formal",
            str(formal_path),
            "--formal-hash",
            p["formal"]["sha256"],
            "--inputs",
            str(p["mp"]),
            "--inputs-hash",
            p["mh"],
            "--output",
            str(root / "independent-a"),
        ],
        check=True,
        capture_output=True,
    )
    seal_path = root / "independent-a/phase-a.json"
    seal = auth.read_json(seal_path)
    assert seal["payload"]["content_sha256"] == p["seal"]["payload"]["content_sha256"]
    gb = dict(p["grants"])
    for kind, sub in {
        "A_SEAL_REVIEW": seal["sha256"],
        "B_SCORING": math.digest({"a_sha256": seal["sha256"], "label_sha256": p["lh"]}),
        "B_LABEL_READ": math.digest(
            {"a_sha256": seal["sha256"], "path": str(p["lp"]), "label_sha256": p["lh"]}
        ),
    }.items():
        gb[kind] = p["signer"].decision(kind, sub)
    gp = root / "b-grants.json"
    write(gp, gb)
    subprocess.run(
        command
        + [
            "stage-b",
            *common,
            "--grants",
            str(gp),
            "--seal",
            str(seal_path),
            "--seal-hash",
            seal["sha256"],
            "--labels",
            str(p["lp"]),
            "--labels-hash",
            p["lh"],
            "--output",
            str(root / "independent-b"),
        ],
        check=True,
        capture_output=True,
    )
    report = auth.read_json(root / "independent-b/report.json")
    assert report["groups"] == p["report"]["groups"]
    for suffix in ("json", "md", "html"):
        text = (root / f"independent-b/report.{suffix}").read_text()
        assert "DAILY_WAPE" in text and "SYNTHETIC" in text
    assert seal["payload"]["executed_at"] != p["seal"]["payload"]["executed_at"]


@pytest.mark.parametrize("window", ["H7_PREFIX", "H15_LOCAL"])
def test_streamed_ten_metrics_match_existing_numerical_engine(window: str) -> None:
    from datetime import datetime
    from decimal import Context, localcontext

    from backend.research import v019_retrospective_engine as existing
    from backend.research import v019_retrospective_scoring as reference

    c = existing.nominate(existing.Experiment(fixture="CLEAN"))
    adm = existing.admit(c, permit=existing.SimulationPermit("C0", c.sha256))
    a = existing.generate(adm, permit=existing.SimulationPermit("A", adm.sha256))
    pairs = {p.sample_id: p for p in a.predictions.pairs}
    labs = {lab.sample_id: lab for lab in reference._labels(a)}
    samples = tuple(s for s in a.predictions.samples if s.window == window)
    as_of = datetime.fromisoformat("2003-01-01T00:00:00Z")
    with localcontext(Context(prec=50)):
        acc = scoring._accumulator()
        for s in samples:
            p, lab = pairs[s.sample_id], labs[s.sample_id]
            why = reference._reason(s, p, lab, as_of)
            errors = {
                side: math._errors(getattr(p, side), lab) for side in ("baseline", "candidate")
            }
            actual = sum((r.kg for r in lab.rows), Decimal(0))
            scoring._add(
                acc,
                {"candidate_id": s.sample_id, "base_id": s.base_id, "window": s.window},
                why,
                actual,
                errors,
                actual > 0,
            )
        got = scoring._finish(acc)["metrics"]
        expected = reference._aggregate(samples, pairs, labs, as_of)["metrics"]
    for n in math.ERROR_METRICS:
        for field in (
            "baseline",
            "candidate",
            "common_count",
            "candidate_count",
            "not_computable_count",
            "common_member_ids",
            "reasons",
            "sample_coverage",
            "base_coverage",
            "target_row_coverage",
        ):
            assert got[n][field] == expected[n][field], (n, field)
    assert got["SAMPLE_COVERAGE"] == expected["SAMPLE_COVERAGE"]
    assert got["NOT_COMPUTABLE_COUNT"] == expected["NOT_COMPUTABLE_COUNT"]
    for field in (
        "n_base",
        "improved",
        "tied",
        "worsened",
        "per_base_delta",
        "improved_actual_kg_share",
    ):
        assert got["BASE_BREADTH"][field] == expected["BASE_BREADTH"][field]


def test_input_snapshot_and_review_tamper_rejected_before_labels(
    prepared: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    p = prepared
    a = deepcopy(p["seal"])
    c = a["payload"]["content"]
    c["input_snapshots_utf8"]["profile"] += " "
    # A malicious rewrite can recalculate plain hashes; it still cannot
    # change frozen input identity or the independently signed A review.
    a["payload"]["content_sha256"] = math.digest(c)
    a["payload"]["prediction_sha256"] = execution.prediction_hash(c)
    a = auth.sealed(a["payload"])
    path = tmp_path / "bad-a.json"
    write(path, a)
    grants = dict(p["grants"])
    # Even a fresh synthetic review of this bad seal does not skip numerical
    # source revalidation. These keys have no standing in the REAL namespace.
    grants["A_SEAL_REVIEW"] = p["signer"].decision("A_SEAL_REVIEW", a["sha256"])
    grants["B_SCORING"] = p["signer"].decision(
        "B_SCORING", math.digest({"a_sha256": a["sha256"], "label_sha256": p["lh"]})
    )
    grants["B_LABEL_READ"] = p["signer"].decision(
        "B_LABEL_READ",
        math.digest({"a_sha256": a["sha256"], "path": str(p["lp"]), "label_sha256": p["lh"]}),
    )
    read = file_io._read_pinned

    def forbidden_labels(path: Path, expected: str, filename: str) -> bytes:
        assert path != p["lp"], "LABEL_READ_BEFORE_A_VERIFICATION"
        return read(path, expected, filename)

    monkeypatch.setattr(file_io, "_read_pinned", forbidden_labels)
    with pytest.raises(ValueError, match="SNAPSHOT_HASH"):
        scoring.run_b(path, a["sha256"], p["lp"], p["lh"], p["ctx"], grants)


def test_a_opens_only_six_pinned_non_label_files(
    prepared: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    p = prepared
    opened = []
    read = file_io._read_pinned

    def tracked(path: Path, expected: str, filename: str) -> bytes:
        assert path != p["lp"]
        opened.append(path)
        return read(path, expected, filename)

    monkeypatch.setattr(file_io, "_read_pinned", tracked)
    execution.run_a(p["mp"], p["mh"], p["formal"], p["ctx"], p["grants"])
    assert set(opened) == {p["mp"]} | {
        Path(x["path"]) for x in p["inputs"].manifest["files"].values()
    }
    assert len(opened) == 6


def test_missing_label_window_failures_remain_in_full_report(
    prepared: dict[str, Any], tmp_path: Path
) -> None:
    p = prepared
    labels = auth.read_json(p["lp"])
    removed = labels["rows"].pop()
    path = tmp_path / "labels.json"
    lh = write(path, labels)
    grants = dict(p["grants"])
    sub = {"a_sha256": p["seal"]["sha256"], "label_sha256": lh}
    grants["B_SCORING"] = p["signer"].decision("B_SCORING", math.digest(sub))
    grants["B_LABEL_READ"] = p["signer"].decision(
        "B_LABEL_READ", math.digest({**sub, "path": str(path)})
    )
    r = scoring.run_b(p["sp"], p["seal"]["sha256"], path, lh, p["ctx"], grants)
    assert r["registered_count"] == 19032 and len(r["members"]) == 19032
    assert any(x["reason"] == "INCOMPLETE_CALENDAR" for x in r["failures"])
    for window in ("H7_PREFIX", "H15_LOCAL"):
        m = r["groups"][window]["metrics"]["DAILY_MAE"]
        assert m["common_count"] == m["candidate_count"] - 1
    assert removed["date"] == "2026-04-15"


def test_calculation_failure_inventory_never_drops_members(prepared: dict[str, Any]) -> None:
    p = prepared
    profile = deepcopy(p["inputs"].profile)
    profile["profile_kg_per_mu_by_7_day_bin"] = {str(i): "1e100" for i in range(42)}
    result = execution.calculate(profile, p["inputs"].registry, p["review"]["payload"]["members"])
    assert len(result["members"]) == len(result["failures"]) == 19032
    assert len(result["base_failures"]) == 39


def test_html_escapes_untrusted_report_text(prepared: dict[str, Any]) -> None:
    r = dict(prepared["report"])
    r["report_scope"] = "<script>SYNTHETIC</script>"
    page = scoring.render(r)["report.html"].decode()
    assert "<script>" not in page and "&lt;script&gt;" in page


def test_json_quantity_tokens_never_round_trip_through_float(prepared: dict[str, Any]) -> None:
    from dataclasses import replace

    inputs = replace(
        prepared["inputs"],
        raw_files={
            "profile": '{"profile_kg_per_mu_by_7_day_bin":{"0":0.12345678901234567890}}',
            "registry": '{"bases":[{"productive_area_mu":12.12345678901234567890}]}',
        },
    )
    p, r = cohort.numerical_inputs(inputs)
    assert p["profile_kg_per_mu_by_7_day_bin"]["0"] == "0.12345678901234567890"
    assert r["bases"][0]["productive_area_mu"] == "12.12345678901234567890"


def test_window_numerators_are_not_mislabeled_as_mae_or_season_scores(
    prepared: dict[str, Any],
) -> None:
    r = next(x for x in prepared["report"]["members"] if x["not_computable_reason"] is None)
    assert "errors" not in r
    assert r["error_denominators"]["DAILY_MAE"] in {"7", "15"}
    assert r["error_denominators"]["SEASON_TOTAL_WAPE"] == "0"
    assert "SEASON_TOTAL_WAPE" not in r["error_numerators"]["baseline"]
    assert r["season_total_wape_status"] == "NOT_COMPUTABLE_FULL_SEASON_NOT_ADMITTED"
