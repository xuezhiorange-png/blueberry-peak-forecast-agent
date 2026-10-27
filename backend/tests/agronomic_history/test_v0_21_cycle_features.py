"""S1 synthetic data only: mathematical and temporal isolation, no prediction."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.research.v021_cycle_features import digest, prepare
from backend.tests.agronomic_history.v0_21_cycle_fixture import clock, fixture, reseal, span

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def example():
    return fixture()


def first(result):
    return result["origin_snapshots"][0]


def record(package, suffix="-prune"):
    return next(r for r in package["records"] if r["record_id"].endswith(suffix))


def test_multi_season_systems_members_and_actual_date_arithmetic():
    p, d = example()
    r = prepare(p, d)
    assert len(r["cycle_associations"]) == 6
    assert len(r["origin_snapshots"]) == 8
    snapshots = r["origin_snapshots"]
    a = next(x for x in snapshots if x["member_id"] == "SYN-MEMBER-0-0-2023")
    b = next(x for x in snapshots if x["member_id"] == "SYN-MEMBER-0-0-2024")
    assert a["features"]["days_since_cycle_start"]["value"] == 194
    assert b["features"]["days_since_cycle_start"]["value"] == 172
    assert {x["scope"]["production_system"] for x in snapshots} == {
        "DECIDUOUS_NATURAL",
        "DECIDUOUS_FORCING",
        "EVERGREEN",
    }
    assert {x["scope"]["plot"] for x in snapshots} == {"SYN-PLOT-0", "SYN-PLOT-1"}
    assert a["features"]["days_since_primary_pruning"]["value"] == 168
    blooms = a["features"]["days_since_eligible_observed_event"]
    assert any(
        e["semantic_type"] == "GENERIC_BLOOM:flowering_peak_date" and e["elapsed"]["value"] == 2
        for e in blooms
    )
    assert any(e["semantic_type"] == "PERCENT_BLOOM:BLOOM_50" for e in blooms)
    assert r["strict_pit_validated"] is False
    assert p["restrictions"]["source_authority_proven"] is False


def test_no_primary_guess_no_forcing_guess_and_planned_separate():
    p, d = example()
    d["members"][0]["primary_pruning"] = []
    r = prepare(p, d)
    assert first(r)["features"]["days_since_primary_pruning"]["value"] is None
    assert first(r)["features"]["days_since_primary_pruning"]["reason"] == "PRIMARY_PRUNING_MISSING"
    assert len(first(r)["planned_events"]) == 1
    assert all(
        e["semantic_type"] != "EVENT:HEATING_START"
        for e in first(r)["features"]["days_since_eligible_observed_event"]
    )
    d["members"][0]["primary_pruning"] = [record(p)["record_id"], record(p, "-prune2")["record_id"]]
    assert (
        first(prepare(p, d))["features"]["days_since_primary_pruning"]["reason"]
        == "PRIMARY_PRUNING_AMBIGUOUS"
    )


@pytest.mark.parametrize("raw,lo,hi", [("2023-08", 183, 213), ("2023", 61, 425)])
def test_month_year_intervals_are_not_fake_exact_days(raw, lo, hi):
    p, d = example()
    d["cycles"][0]["start"] = span(raw)
    d["cycles"][0]["clocks"] = clock(d["cycles"][0]["start"]["upper_date"])
    v = first(prepare(p, d))["features"]["days_since_cycle_start"]
    assert v == dict(status="INTERVAL", value=None, lower_days=lo, upper_days=hi, reason=None)


def test_future_origin_day_and_late_revisions_do_not_change_legal_features():
    p, d = example()
    before = first(prepare(p, d))
    base = record(p)
    late = copy.deepcopy(base)
    late.update(
        record_id="SYN-LATE-REV",
        revision_id="r2",
        supersedes_revision="r1",
        business_date=span("2023-09-20"),
    )
    p["records"].append(late)
    d["record_clocks"][late["record_id"]] = dict(record_sha256="", **clock("2024-03-02"))
    for suffix, day in [("-bloom", "2024-03-01"), ("-b50", "2024-04-01")]:
        item = record(p, suffix)
        item["business_date"] = span(day)
        d["record_clocks"][item["record_id"]] = dict(record_sha256="", **clock(day))
    reseal(p, d)
    # Compare pruning and cycle, while changed blooms correctly disappear rather than leak.
    after = first(prepare(p, d))
    assert (
        after["features"]["days_since_primary_pruning"]
        == before["features"]["days_since_primary_pruning"]
    )
    assert (
        after["features"]["days_since_cycle_start"] == before["features"]["days_since_cycle_start"]
    )
    old = copy.deepcopy((p, d))
    for suffix, day in [("-bloom", "2024-08-01"), ("-b50", "2024-05-01")]:
        record(p, suffix)["business_date"] = span(day)
    reseal(p, d)
    changed = first(prepare(p, d))
    assert changed["feature_sha256"] == after["feature_sha256"]
    assert changed["features"] == after["features"]
    assert digest(p) != digest(old[0])


def test_legal_d_minus_one_change_has_explainable_effect():
    p, d = example()
    item = record(p, "-bloom")
    item["business_date"] = span("2024-02-29")
    d["record_clocks"][item["record_id"]] = dict(record_sha256="", **clock("2024-02-29"))
    reseal(p, d)
    a = first(prepare(p, d))
    event = next(
        e
        for e in a["features"]["days_since_eligible_observed_event"]
        if e["semantic_type"].startswith("GENERIC_BLOOM")
    )
    assert event["elapsed"]["value"] == 1


@pytest.mark.parametrize("field", ["observed_at", "recorded_at", "known_at"])
def test_missing_or_day_only_clock_is_never_imputed(field):
    p, d = example()
    d["record_clocks"][record(p)["record_id"]][field] = "2023-09-15"
    r = first(prepare(p, d))
    assert r["features"]["days_since_primary_pruning"]["value"] is None


def test_unmapped_unknown_scope_never_coalesces():
    p, d = example()
    d["members"][0]["scope"]["plot"] = "UNKNOWN"
    r = prepare(p, d)
    assert first(r)["status"] == "UNMAPPED"
    assert first(r)["features"]["days_since_primary_pruning"]["value"] is None
    assert any(x["record_id"] == record(p)["record_id"] for x in r["record_ledger"])


def test_visible_revision_winner_and_fork_conflict():
    p, d = example()
    old = record(p)
    new = copy.deepcopy(old)
    new.update(
        record_id="SYN-REV",
        revision_id="r2",
        supersedes_revision="r1",
        business_date=span("2023-09-20"),
    )
    p["records"].append(new)
    d["record_clocks"][new["record_id"]] = dict(record_sha256="", **clock("2023-09-21"))
    reseal(p, d)
    assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] == 163
    fork = copy.deepcopy(new)
    fork.update(record_id="SYN-FORK", revision_id="r3")
    p["records"].append(fork)
    d["record_clocks"][fork["record_id"]] = dict(record_sha256="", **clock("2023-09-22"))
    reseal(p, d)
    assert (
        first(prepare(p, d))["features"]["days_since_primary_pruning"]["reason"] == "REVISION_FORK"
    )


def test_hash_schema_scope_and_real_input_rejections():
    p, d = example()
    d["package_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="PACKAGE_HASH_MISMATCH"):
        prepare(p, d)
    p, d = example()
    p["data_class"] = "USER_FILE_PREVIEW_UNVERIFIED"
    reseal(p, d)
    with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
        prepare(p, d)
    p, d = example()
    d["record_clocks"][record(p)["record_id"]]["record_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="RECORD_PROOF_HASH_MISMATCH"):
        prepare(p, d)


def test_pure_determinism_and_separate_process_cli(tmp_path):
    p, d = example()
    before = copy.deepcopy((p, d))
    a = prepare(p, d)
    assert prepare(p, d) == a and (p, d) == before
    package = tmp_path / "package.json"
    package.write_text(json.dumps(p))
    declarations = tmp_path / "declarations.json"
    declarations.write_text(json.dumps(d))
    for name in ("a", "b"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.research.v021_cycle_features",
                "--package",
                str(package),
                "--declarations",
                str(declarations),
                "--output",
                str(tmp_path / name),
            ],
            check=True,
            capture_output=True,
        )
    assert (tmp_path / "a/cycle-features.json").read_bytes() == (
        tmp_path / "b/cycle-features.json"
    ).read_bytes()
    assert (
        json.loads((tmp_path / "a/cycle-features.json").read_bytes())["result_sha256"]
        == a["result_sha256"]
    )


def test_future_only_revision_preserves_whole_feature_identity_not_audit_identity():
    p, d = example()
    before = first(prepare(p, d))
    late = copy.deepcopy(record(p))
    late.update(record_id="SYN-LATE", revision_id="r2", supersedes_revision="r1")
    late["issues"] = [
        dict(code="INVALID_NEW_ROW", severity="ERROR", message="synthetic", field="date")
    ]
    p["records"].append(late)
    d["record_clocks"][late["record_id"]] = dict(record_sha256="", **clock("2024-03-02"))
    reseal(p, d)
    after = first(prepare(p, d))
    assert after["features"] == before["features"]
    assert after["feature_sha256"] == before["feature_sha256"]
    assert after["lineage_sha256"] != before["lineage_sha256"]


def test_visible_unknown_revision_and_invalid_head_never_fall_back():
    for mode in ("unknown", "invalid"):
        p, d = example()
        new = copy.deepcopy(record(p))
        new.update(record_id="SYN-VISIBLE", revision_id="r2", supersedes_revision="r1")
        if mode == "unknown":
            new["observed_or_planned"] = "UNKNOWN"
        else:
            new["issues"] = [dict(code="BAD", severity="ERROR", message="synthetic", field="date")]
        p["records"].append(new)
        d["record_clocks"][new["record_id"]] = dict(record_sha256="", **clock("2023-10-01"))
        reseal(p, d)
        assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] is None


def test_cycle_observation_cannot_predate_declared_start():
    p, d = example()
    d["cycles"][0]["clocks"] = clock("2023-08-01")
    r = first(prepare(p, d))
    assert r["features"]["days_since_cycle_start"]["value"] is None
    assert r["status"] == "NOT_COMPUTABLE"


@pytest.mark.parametrize(
    "field", ["base", "farm", "subfarm", "plot", "variety", "season", "production_system"]
)
def test_primary_and_stage_references_cannot_cross_any_scope_key(field):
    p, d = example()
    member = d["members"][0]
    source = record(p)
    alien = copy.deepcopy(source)
    alien.update(record_id="SYN-ALIEN", logical_id="SYN-ALIEN-LOGIC")
    alien["scope"][field] += "-other"
    p["records"].append(alien)
    d["record_clocks"][alien["record_id"]] = dict(record_sha256="", **clock("2023-09-16"))
    member["primary_pruning"] = [alien["record_id"]]
    reseal(p, d)
    assert (
        first(prepare(p, d))["features"]["days_since_primary_pruning"]["reason"]
        == "ANCHOR_MEMBER_SCOPE_MISMATCH"
    )


def test_ambiguous_cycle_and_missing_requested_origin_are_visible_in_ledger():
    p, d = example()
    second = copy.deepcopy(d["cycles"][0])
    second["cycle_id"] = "SYN-DUPLICATE-CYCLE"
    d["cycles"].append(second)
    assert first(prepare(p, d))["status"] == "UNMAPPED"
    p, d = example()
    d["origins"].append(
        dict(
            origin_id="SYN-ORPHAN",
            base="SYN-NOT-DECLARED",
            season="2023-2024",
            origin_date="2024-03-01",
            timezone="Asia/Shanghai",
            cutoff="2024-03-01T08:00:00+08:00",
        )
    )
    r = prepare(p, d)
    assert (
        next(o for o in r["origin_requests"] if o["origin_id"] == "SYN-ORPHAN")["reason"]
        == "NO_DECLARED_MEMBER"
    )


def test_utc_day_does_not_masquerade_as_prior_local_business_day():
    p, d = example()
    r = record(p, "-bloom")
    r["business_date"] = dict(
        raw="2024-02-29T20:00:00Z",
        precision="TIMESTAMP",
        lower_date="2024-02-29",
        upper_date="2024-02-29",
        instant="2024-02-29T20:00:00Z",
    )
    d["record_clocks"][r["record_id"]] = dict(record_sha256="", **clock("2024-03-01"))
    reseal(p, d)
    out = prepare(p, d)
    assert not any(
        e["semantic_type"].startswith("GENERIC_BLOOM")
        for e in first(out)["features"]["days_since_eligible_observed_event"]
    )


def test_original_issues_states_clocks_rows_and_revision_metadata_are_preserved():
    p, d = example()
    before = copy.deepcopy(p)
    out = prepare(p, d)
    assert out["original_package"] == before
    assert [r["raw_record"] for r in out["record_ledger"]] == sorted(
        before["records"], key=lambda r: r["record_id"]
    )
    assert all(r["known_at"]["instant"] is None for r in p["records"])
    assert p == before


@pytest.mark.parametrize("method", ["UNKNOWN", "不详", "UNSPECIFIED", "待确认"])
def test_unknown_forcing_method_cannot_be_promoted_to_heating(method):
    p, d = example()
    r = record(p, "-forcing")
    r["event"].update(canonical_type="HEATING_START", method=method)
    # Use the legitimately applicable forcing system to isolate method checking.
    r["scope"]["production_system"] = "DECIDUOUS_FORCING"
    member = d["members"][0]
    member["scope"]["production_system"] = "DECIDUOUS_FORCING"
    for other in p["records"]:
        if (
            other["scope"]["plot"] == r["scope"]["plot"]
            and other["scope"]["base"] == r["scope"]["base"]
            and other["scope"]["season"] == r["scope"]["season"]
        ):
            other["scope"]["production_system"] = "DECIDUOUS_FORCING"
    reseal(p, d)
    out = first(prepare(p, d))
    assert not any(
        e["semantic_type"] == "EVENT:HEATING_START"
        for e in out["features"]["days_since_eligible_observed_event"]
    )


def test_actual_v020_producer_package_requires_no_reparse_or_identity_upgrade():
    from backend.tests.agronomic_history.v0_21_cycle_fixture import producer_fixture

    p, d = producer_fixture()
    original = copy.deepcopy(p)
    result = prepare(p, d)
    assert len(result["record_ledger"]) == 90
    assert len(result["cycle_associations"]) == 4
    assert len(result["origin_snapshots"]) == 6
    assert p["summary"]["kind_counts"] == {"AREA": 18, "EVENT": 36, "PHENOLOGY": 36}
    assert all(
        s["features"]["days_since_primary_pruning"]["status"] == "EXACT"
        for s in result["origin_snapshots"]
    )
    assert p == original and result["original_package"] == original
    assert all(r["scope"]["plot_authority_id"] is None for r in p["records"])
    assert (
        p["package_id"] == "V0_20-7ca546d45f6ce68f9a18d7ccad5b4c976eaab6e8d648510d2591aacd8d0d9e57"
    )


def test_missing_date_and_reversed_stage_interval_remain_null_with_reason():
    p, d = example()
    d["cycles"][0]["start"] = span()
    out = first(prepare(p, d))
    assert out["features"]["days_since_cycle_start"]["value"] is None
    p, d = example()
    pair = d["members"][0]["intervals"][0]
    pair["start_record_id"], pair["end_record_id"] = pair["end_record_id"], pair["start_record_id"]
    value = first(prepare(p, d))["features"]["completed_stage_intervals"][0]
    assert value["value"] is None and value["reason"] == "STAGE_ORDER_REVERSED"


def test_supplementary_clocks_cannot_contradict_existing_source_clock():
    p, d = example()
    r = record(p)
    r["known_at"] = span("2024-03-01")
    reseal(p, d)
    assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] is None


def test_unmatched_origins_and_late_member_relation_are_not_hidden():
    p, d = example()
    d["members"][0]["known_at"] = "2024-03-02T10:00:00+08:00"
    out = first(prepare(p, d))
    assert out["status"] == "NOT_COMPUTABLE"
    assert out["features"]["days_since_primary_pruning"]["value"] is None
    assert out["reason"] == "MEMBER_RELATION_NOT_VISIBLE"


def test_naive_cutoff_and_unknown_timezone_rejected():
    for field, value in [("cutoff", "2024-03-01T08:00:00"), ("timezone", "SYNTHETIC/Unknown")]:
        p, d = example()
        d["origins"][0][field] = value
        with pytest.raises(ValueError, match="ORIGIN_"):
            prepare(p, d)


def test_future_raw_labels_are_not_feature_inputs():
    from backend.tests.agronomic_history.v0_21_cycle_fixture import seal

    p, d = example()
    old = first(prepare(p, d))
    p["source_rows"][0]["cells"].append(
        dict(text="SYNTHETIC future actual harvest 999999 kg; peak 2024-04-10", kind="text")
    )
    seal(p)
    d["package_sha256"] = p["preparation_sha256"]
    new = first(prepare(p, d))
    assert new["features"] == old["features"] and new["feature_sha256"] == old["feature_sha256"]
    assert new["lineage_sha256"] != old["lineage_sha256"]


def test_missing_forcing_is_not_a_cycle_error_and_no_yield_effect_is_produced():
    p, d = example()
    before = first(prepare(p, d))
    removed = [r["record_id"] for r in p["records"] if r["record_id"].endswith("-forcing")]
    p["records"] = [r for r in p["records"] if r["record_id"] not in removed]
    for rid in removed:
        del d["record_clocks"][rid]
    reseal(p, d)
    after = first(prepare(p, d))
    assert after["features"] == before["features"]
    assert after["reason"] is None
    assert "yield_multiplier" not in json.dumps(after)
    assert "peak_date_shift" not in json.dumps(after)


def test_semantically_wrong_generic_percent_and_planned_anchor_blocked():
    p, d = example()
    r = record(p, "-bloom")
    r["phenology"]["canonical_stage"] = "BLOOM_50"
    reseal(p, d)
    assert not any(
        e["semantic_type"].startswith("GENERIC_BLOOM")
        for e in first(prepare(p, d))["features"]["days_since_eligible_observed_event"]
    )
    p, d = example()
    d["members"][0]["primary_pruning"] = [record(p, "-planned")["record_id"]]
    value = first(prepare(p, d))["features"]["days_since_primary_pruning"]
    assert value["value"] is None and value["reason"] == "ANCHOR_NOT_OBSERVED"


def test_primary_pruning_month_precision_returns_bounds_and_not_an_exact_day():
    from datetime import date

    p, d = example()
    r = record(p)
    r["business_date"] = span("2023-09")
    reseal(p, d)
    value = first(prepare(p, d))["features"]["days_since_primary_pruning"]
    assert value["value"] is None and value["status"] == "INTERVAL"
    assert value["lower_days"] == (date(2024, 3, 1) - date(2023, 9, 30)).days
    assert value["upper_days"] == (date(2024, 3, 1) - date(2023, 9, 1)).days


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("missing", "REVISION_PREDECESSOR_NOT_VISIBLE"),
        ("cycle", "REVISION_CYCLE"),
        ("duplicate", "DUPLICATE_VISIBLE_REVISION"),
    ],
)
def test_revision_graph_errors_are_retained_instead_of_selecting_a_row(problem, reason):
    p, d = example()
    old = record(p)
    new = copy.deepcopy(old)
    new["record_id"] = "SYN-BROKEN-REV"
    new["revision_id"] = "r2"
    new["supersedes_revision"] = "r1"
    if problem == "missing":
        new["supersedes_revision"] = "r404"
    if problem == "cycle":
        old["supersedes_revision"] = "r2"
    if problem == "duplicate":
        new["revision_id"] = "r1"
        new["supersedes_revision"] = None
    p["records"].append(new)
    d["record_clocks"][new["record_id"]] = dict(record_sha256="", **clock("2023-10-01"))
    reseal(p, d)
    result = prepare(p, d)
    assert first(result)["features"]["days_since_primary_pruning"]["reason"] == reason
    assert any(x["reason"] == reason for x in result["origin_decisions"])


def test_unknown_source_clock_evidence_and_local_time_do_not_become_exact_features():
    p, d = example()
    r = record(p)
    d["record_clocks"][r["record_id"]]["evidence_reference"] = "UNKNOWN"
    assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] is None
    p, d = example()
    r = record(p)
    r["business_date"] = dict(
        raw="2023-09-15 08:00:00",
        precision="LOCAL_DATETIME",
        lower_date="2023-09-15",
        upper_date="2023-09-15",
        instant=None,
    )
    reseal(p, d)
    assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] is None


def test_unrelated_report_shape_cannot_be_relabeled_as_v020_input():
    from backend.tests.agronomic_history.v0_21_cycle_fixture import seal

    p, d = example()
    p["forecast_labels"] = {"SYNTHETIC": "not an allowed V020 root field"}
    seal(p)
    d["package_sha256"] = p["preparation_sha256"]
    with pytest.raises(ValueError, match="V020_PACKAGE_SCHEMA_MISMATCH"):
        prepare(p, d)


def test_source_clock_consistency_is_checked_before_pit_predicate(monkeypatch):
    from backend.research import v021_cycle_features as module

    p, d = example()
    # All other members are removed so the spy applies only to this inconsistent proof.
    proof = copy.deepcopy(d["record_clocks"][record(p)["record_id"]])
    r = copy.deepcopy(record(p))
    r["known_at"] = span("2024-03-01")
    origin = module.Origin.model_validate(d["origins"][0])

    def must_not_be_called(*args):
        raise AssertionError("PIT called before source-clock consistency check")

    monkeypatch.setattr(module, "record_visible_at", must_not_be_called)
    assert (
        module._clock_reason(module.RecordClock.model_validate(proof), origin, raw=r)
        == "CLOCK_SOURCE_CONFLICT"
    )


def test_s1_owner_authorization_is_new_and_s0_history_is_not_rewritten():
    import hashlib

    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (root / "docs/v0-21/evidence/v0.21-s1-cycle-features-r1.json").read_bytes()
    )
    assert evidence["owner_authorization"]["scope"] == "IMPLEMENT_S1_ONLY"
    assert evidence["owner_authorization"]["s1_implementation"] is True
    assert all(value is False for value in evidence["restrictions"].values())
    for path, item in evidence["historical_source_identity"].items():
        raw = subprocess.check_output(["git", "show", f"{item['commit']}:{path}"], cwd=root)
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        if path.endswith("v0.21-s0-scope.json"):
            assert json.loads(raw)["permissions"]["s1_implementation"] is False
    for path, sha in evidence["outputs"]["example_sha256"].items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == sha


def test_source_file_hash_requires_sha256_hex_not_just_length():
    from backend.tests.agronomic_history.v0_21_cycle_fixture import seal

    p, d = example()
    p["source_file_sha256"] = "Z" * 64
    seal(p)
    d["package_sha256"] = p["preparation_sha256"]
    with pytest.raises(ValueError, match="SOURCE_HASH_FORMAT_INVALID"):
        prepare(p, d)


@pytest.mark.parametrize("field", ["method", "sample_scope", "quality_status"])
def test_unknown_bloom_observation_context_is_not_proven(field):
    p, d = example()
    item = record(p, "-b50")
    item["phenology"][field] = "UNKNOWN"
    reseal(p, d)
    out = first(prepare(p, d))
    assert not any(
        e["semantic_type"] == "PERCENT_BLOOM:BLOOM_50"
        for e in out["features"]["days_since_eligible_observed_event"]
    )


def test_unknown_source_name_does_not_become_a_verified_source_identity():
    p, d = example()
    item = record(p)
    item["source_reference"] = "UNKNOWN"
    reseal(p, d)
    assert first(prepare(p, d))["features"]["days_since_primary_pruning"]["value"] is None
