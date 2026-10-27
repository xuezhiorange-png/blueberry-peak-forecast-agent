"""V0_21 S2 real arithmetic over synthetic structural facts, no prediction."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.research import v021_cycle_features as cycle
from backend.research.v021_structure_scenarios import prepare
from backend.tests.agronomic_history.v0_21_cycle_fixture import (
    clock,
    producer_fixture,
    reseal,
    span,
)
from backend.tests.agronomic_history.v0_21_structure_fixture import SCENARIOS, example, inputs

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def first(result):
    return result["comparisons"][0]


def rebound(package, declarations, extra):
    reseal(package, declarations)
    s1 = cycle.prepare(package, declarations)
    extra["s1_result_sha256"] = s1["result_sha256"]
    return s1, extra


@pytest.mark.parametrize(
    "scenario,after,change,ratio",
    [
        ("UNCHANGED", "100.000000", "0.000000", "0"),
        ("AREA_INCREASE", "120.000000", "20.000000", "0.2"),
        ("AREA_DECREASE", "80.000000", "-20.000000", "-0.2"),
    ],
)
def test_explicit_continuity_and_separate_exact_area_arithmetic(scenario, after, change, ratio):
    s1, d = example(scenario)
    original = copy.deepcopy((s1, d))
    r = prepare(s1, d)
    a = first(r)["area_changes"]["PLANTED"]
    assert a["status"] == "COMPARABLE"
    assert (a["previous_mu"], a["next_mu"], a["delta_mu"], a["relative_change_ratio"]) == (
        "100.000000",
        after,
        change,
        ratio,
    )
    assert first(r)["area_changes"]["PRODUCTIVE"]["delta_mu"] == "0.000000"
    assert (s1, d) == original
    assert r["area_ledger"][0]["raw_record"] in s1["original_package"]["records"]
    assert r["strict_pit_validated"] is False


def test_planted_productive_effective_do_not_move_in_lockstep():
    r = first(prepare(*example("ASYNCHRONOUS_AREA_CHANGE")))
    assert [r["area_changes"][b]["delta_mu"] for b in ("PLANTED", "PRODUCTIVE", "EFFECTIVE")] == [
        "20.000000",
        "-10.000000",
        "-5.000000",
    ]


@pytest.mark.parametrize(
    "scenario,reason,status",
    [
        ("UNPROVEN_CONTINUITY", "CONTINUITY_NOT_PROVEN", "NOT_PROVEN"),
        ("MIXED_PRODUCTION_SYSTEMS", "PRODUCTION_SYSTEM_CHANGED", "NOT_COMPARABLE"),
        ("SAME_NAME_DIFFERENT_ENTITY", "ENTITY_CONTINUITY_BROKEN", "NOT_COMPARABLE"),
        ("CONFLICTING_EFFECTIVE_INTERVALS", "AREA_INTERVAL_CONFLICT", "NOT_COMPARABLE"),
        ("MISSING_AREA", "AREA_VALUE_MISSING", "NOT_PROVEN"),
        ("UNIT_MISMATCH", "AREA_UNIT_NOT_MU", "NOT_COMPARABLE"),
    ],
)
def test_reasons_preserved_instead_of_making_a_rate(scenario, reason, status):
    r = first(prepare(*example(scenario)))
    a = r["area_changes"]["PLANTED"]
    assert a["status"] == status and reason in a["reasons"]
    assert a["delta_mu"] is None and a["relative_change_ratio"] is None


def test_variety_replacement_is_exit_and_entry_not_same_variety_trend():
    r = first(prepare(*example("VARIETY_REPLACEMENT")))
    assert r["status"] == "NOT_COMPARABLE"
    assert [e["kind"] for e in r["variety_changes"]] == ["EXIT", "ENTRY"]
    assert r["variety_changes"][0]["variety"] != r["variety_changes"][1]["variety"]
    assert all(a["delta_mu"] is None for a in r["area_changes"].values())


def test_zero_is_known_but_not_a_ratio_denominator():
    a = first(prepare(*example("ZERO_PREVIOUS_AREA")))["area_changes"]["PLANTED"]
    assert (a["previous_mu"], a["delta_mu"]) == ("0.000000", "100.000000")
    assert a["status"] == "COMPARABLE" and a["relative_change_ratio"] is None
    assert a["relative_change_reason"] == "ZERO_PREVIOUS_AREA"


def test_replant_preserves_cohorts_and_does_not_infer_no_replant_when_missing():
    known = first(prepare(*example("REPLANT")))["replant"]
    assert known["status"] == "COMPARABLE"
    assert known["events"][0]["old_cohort_id"] == "SYN-OLD-COHORT"
    assert known["events"][0]["new_cohort_id"] == "SYN-NEW-COHORT"
    missing = first(prepare(*example()))["replant"]
    assert missing["status"] == "NOT_PROVEN" and missing["reason"] == "REPLANT_INFORMATION_MISSING"


def test_density_is_plants_per_mu_with_exact_independent_measurements():
    d = first(prepare(*example("DENSITY_CHANGE")))["density_change"]
    assert d["status"] == "COMPARABLE"
    assert (
        d["previous_plants_per_mu"],
        d["next_plants_per_mu"],
        d["delta_plants_per_mu"],
        d["relative_change_ratio"],
    ) == ("200.000000", "300.000000", "100.000000", "0.5")


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("plant_count", None, "PLANT_COUNT_MISSING_OR_INVALID"),
        ("measured_area", "0", "DENSITY_DENOMINATOR_NOT_POSITIVE"),
        ("area_unit", "ha", "DENSITY_UNIT_NOT_MU"),
        ("method", "UNKNOWN", "DENSITY_METHOD_NOT_PROVEN"),
        ("observed_or_planned", "PLANNED", "PLANNED_NOT_OBSERVED"),
    ],
)
def test_density_has_no_guessed_denominator_or_method(key, value, reason):
    s1, d = example("DENSITY_CHANGE")
    d["densities"][0][key] = value
    out = first(prepare(s1, d))["density_change"]
    assert out["status"] != "COMPARABLE" and reason in out["reasons"]
    assert out["delta_plants_per_mu"] is None


@pytest.mark.parametrize(
    "key,value,reason",
    [
        ("base", "SYN-OTHER", "BASE_CHANGED"),
        ("farm", "SYN-OTHER", "FARM_CHANGED"),
        ("subfarm", "SYN-OTHER", "SUBFARM_CHANGED"),
        ("plot", "SYN-OTHER", "PLOT_CHANGED"),
        ("variety", "SYN-OTHER", "VARIETY_CHANGED"),
    ],
)
def test_cross_scope_isolation_even_with_asserted_entity_id(key, value, reason):
    p, s, d = inputs()
    member = next(m for m in s["members"] if m["member_id"] == d["links"][0]["next_member_id"])
    original = member["scope"].copy()
    member["scope"][key] = value
    for r in p["records"]:
        if all(r["scope"][k] == v for k, v in original.items()):
            r["scope"][key] = value
    if key == "base":
        member["cycle_id"] = "SYN-MISSING-CYCLE"
    out = first(prepare(*rebound(p, s, d)))
    assert out["status"] != "COMPARABLE"
    assert reason in out["reasons"] or "UNMAPPED_MEMBER" in out["reasons"]
    assert out["area_changes"]["PLANTED"]["delta_mu"] is None


def test_upstream_conflict_and_all_original_values_are_retained():
    p, s, d = inputs()
    r = next(r for r in p["records"] if r["kind"] == "AREA")
    r["issues"].append(
        dict(
            code="AREA_BASIS_CONFLICT", severity="ERROR", message="SYNTHETIC-conflict", field="area"
        )
    )
    r["states"].append("CONFLICT")
    out = prepare(*rebound(p, s, d))
    assert "AREA_BASIS_CONFLICT" in first(out)["area_changes"]["PLANTED"]["reasons"]
    assert (
        next(a["raw_record"] for a in out["area_ledger"] if a["record_id"] == r["record_id"]) == r
    )


def test_future_and_late_area_revisions_cannot_pollute_origin_snapshot():
    p, s, d = inputs()
    before = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    original = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    late = copy.deepcopy(original)
    late.update(
        record_id="SYN-LATE-AREA",
        revision_id="r2",
        supersedes_revision="r1",
        source_row_id="SYN-LATE-AREA",
    )
    late["area"].update(raw_value="999", value="999.000000")
    p["records"].append(late)
    s["record_clocks"][late["record_id"]] = dict(record_sha256="", **clock("2025-03-02"))
    after = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    assert before["feature_sha256"] == after["feature_sha256"]
    assert before["comparison"] == after["comparison"]


def test_missing_area_clocks_only_block_as_of_not_historical_description():
    p, s, d = inputs()
    rid = d["links"][0]["next_member_id"] + "-area-PLANTED"
    del s["record_clocks"][rid]
    out = prepare(*rebound(p, s, d))
    assert first(out)["area_changes"]["PLANTED"]["status"] == "COMPARABLE"
    a = out["origin_snapshots"][0]["comparison"]["area_changes"]["PLANTED"]
    assert a["status"] == "NOT_PROVEN" and "CLOCK_EVIDENCE_MISSING" in a["reasons"]


@pytest.mark.parametrize("day", ["2025-03-01", "2025-03-02"])
def test_origin_day_and_future_facts_do_not_need_clocks_to_be_excluded(day):
    p, s, d = inputs()
    before = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    previous = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    future = copy.deepcopy(previous)
    future.update(
        record_id="SYN-FUTURE-AREA",
        revision_id="r2",
        supersedes_revision="r1",
        source_row_id="SYN-FUTURE-AREA",
        business_date=span(day),
    )
    future["area"].update(raw_value="INVALID", value="INVALID")
    p["records"].append(future)
    after = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    assert before["comparison"] == after["comparison"]
    assert before["feature_sha256"] == after["feature_sha256"]


def test_legal_d_minus_one_revision_changes_only_the_eligible_structure():
    p, s, d = inputs()
    before = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    previous = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    revised = copy.deepcopy(previous)
    revised.update(
        record_id="SYN-PRIOR-AREA",
        revision_id="r2",
        supersedes_revision="r1",
        source_row_id="SYN-PRIOR-AREA",
        business_date=span("2025-02-28"),
    )
    revised["area"].update(raw_value="110", value="110.000000")
    p["records"].append(revised)
    s["record_clocks"][revised["record_id"]] = dict(record_sha256="", **clock("2025-02-28"))
    after = prepare(*rebound(p, s, d))["origin_snapshots"][0]
    assert after["feature_sha256"] != before["feature_sha256"]
    assert after["comparison"]["area_changes"]["PLANTED"]["delta_mu"] == "10.000000"
    assert (
        after["comparison"]["area_changes"]["PRODUCTIVE"]
        == before["comparison"]["area_changes"]["PRODUCTIVE"]
    )


def test_integer_relative_change_and_density_rounding_do_not_use_display_values():
    p, s, d = inputs("DENSITY_CHANGE")
    r = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    r["area"].update(raw_value="1100", value="1100.000000")
    for row, count in zip(d["densities"], ["1", "2"], strict=True):
        row.update(plant_count=count, measured_area="3")
    result = first(prepare(*rebound(p, s, d)))
    assert result["area_changes"]["PLANTED"]["relative_change_ratio"] == "10"
    density = result["density_change"]
    assert density["delta_plants_per_mu"] == "0.333333"
    assert density["relative_change_ratio"] == "1"


@pytest.mark.parametrize("basis", ["PRODUCTIVE", "EFFECTIVE"])
def test_new_basis_conflict_is_detected_even_when_upstream_has_no_error(basis):
    p, s, d = inputs()
    r = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-" + basis
    )
    r["area"].update(raw_value="101", value="101.000000")
    out = first(prepare(*rebound(p, s, d)))
    assert "AREA_BASIS_CONFLICT" in out["area_changes"][basis]["reasons"]
    assert out["area_changes"][basis]["delta_mu"] is None


def test_nonoverlapping_versions_change_area_without_being_conflicts():
    p, s, d = inputs()
    first_row = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    second_row = copy.deepcopy(first_row)
    first_row["area"]["effective_to"] = span("2024-10-31")
    second_row.update(
        record_id="SYN-NONOVERLAPPING-AREA",
        logical_id="SYN-LATER-INTERVAL",
        source_row_id="SYN-NONOVERLAPPING-AREA",
        business_date=span("2024-11-01"),
    )
    second_row["area"].update(
        effective_from=span("2024-11-01"), raw_value="120", value="120.000000"
    )
    p["records"].append(second_row)
    s["record_clocks"][second_row["record_id"]] = dict(record_sha256="", **clock("2024-11-01"))
    a = first(prepare(*rebound(p, s, d)))["area_changes"]["PLANTED"]
    assert a["status"] == "COMPARABLE" and a["delta_mu"] == "20.000000"


def test_original_v020_producer_package_is_consumed_without_resealing():
    package, declarations = producer_fixture()
    original = cycle.canonical(package)
    s1 = cycle.prepare(package, declarations)
    pairs = {}
    for member in declarations["members"]:
        key = tuple(member["scope"][k] for k in cycle.SCOPE_KEYS if k != "season")
        pairs.setdefault(key, {})[member["scope"]["season"]] = member["member_id"]
    _, extra = example()
    template = copy.deepcopy(extra["links"][0])
    extra["links"] = []
    for i, pair in enumerate(pairs.values()):
        link = copy.deepcopy(template)
        link.update(
            link_id=f"SYN-PRODUCER-LINK-{i}",
            previous_member_id=pair["2023-2024"],
            next_member_id=pair["2024-2025"],
        )
        extra["links"].append(link)
    extra["s1_result_sha256"] = s1["result_sha256"]
    extra["scenarios"][0]["link_ids"] = [x["link_id"] for x in extra["links"]]
    result = prepare(s1, extra)
    assert len(result["area_ledger"]) == 18
    assert cycle.canonical(package) == original
    assert all(
        c["area_changes"]["PLANTED"]["status"] == "COMPARABLE" for c in result["comparisons"]
    )
    assert all(
        c["comparison"]["area_changes"]["PLANTED"]["status"] != "COMPARABLE"
        for c in result["origin_snapshots"]
    )


@pytest.mark.parametrize("kind", ["ENTRY", "EXIT"])
def test_individually_declared_entry_exit_does_not_turn_absence_into_zero(kind):
    s1, d = example()
    link = d["links"][0]
    link["kind"] = kind
    side = "previous" if kind == "ENTRY" else "next"
    for suffix in ("member_id", "entity_id", "as_of"):
        link[side + "_" + suffix] = None
    out = first(prepare(s1, d))
    assert [e["kind"] for e in out["variety_changes"]] == [kind]
    assert out["area_changes"]["PLANTED"]["delta_mu"] is None


def test_real_cli_marker_is_rejected_before_opening_s1_input(tmp_path):
    declaration = tmp_path / "NOT_REAL_BUSINESS_DATA.json"
    declaration.write_text('{"data_class":"REAL"}')
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.research.v021_structure_scenarios",
            "--s1",
            str(tmp_path / "NOT_OPENED"),
            "--declarations",
            str(declaration),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 and "SYNTHETIC_ONLY" in result.stderr
    assert not output.exists()


def test_s2_authorization_and_published_snapshot_are_consistent_without_rebinding_history():
    import hashlib

    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (root / "docs/v0-21/evidence/v0.21-s2-structure-scenarios-r1.json").read_text()
    )
    assert evidence["owner_authorization"]["granted"] is True
    assert evidence["owner_authorization"]["scope"] == "IMPLEMENT_S2_ONLY"
    assert all(value is False for value in evidence["restrictions"].values())
    assert set(evidence["scenario_registry"]) == set(SCENARIOS)
    example_dir = root / evidence["example"]["path"]
    for name, expected in evidence["example"]["file_sha256"].items():
        assert hashlib.sha256((example_dir / name).read_bytes()).hexdigest() == expected
    snapshot = json.loads((example_dir / "structure-scenarios.json").read_text())
    assert (
        cycle.digest({k: v for k, v in snapshot.items() if k != "result_sha256"})
        == evidence["example"]["result_sha256"]
    )
    assert snapshot["scenario_results"][0]["component_status_counts"]["density"] == {
        "COMPARABLE": 1,
        "NOT_PROVEN": 3,
    }
    for source in evidence["reused_sources"]:
        old_bytes = subprocess.check_output(
            ["git", "show", source["commit"] + ":" + source["path"]], cwd=root
        )
        assert hashlib.sha256(old_bytes).hexdigest() == source["sha256"]
    historical = json.loads(
        subprocess.check_output(
            ["git", "show", evidence["base_main_sha"] + ":docs/v0-21/evidence/v0.21-s0-scope.json"],
            cwd=root,
        )
    )
    assert (
        next(s for s in historical["stages"] if s["id"] == "S2")["status"]
        == "PLANNED_NOT_AUTHORIZED"
    )


def test_same_input_result_and_hash_are_deterministic_and_s1_remains_unmodified():
    s1, d = example("BUSINESS_EXAMPLE")
    original = cycle.canonical(s1)
    a, b = prepare(s1, d), prepare(copy.deepcopy(s1), copy.deepcopy(d))
    assert cycle.canonical(a) == cycle.canonical(b)
    assert cycle.canonical(s1) == original
    body = {k: v for k, v in a.items() if k != "result_sha256"}
    assert cycle.digest(body) == a["result_sha256"]
    assert "yield_multiplier" not in json.dumps(a) and "peak_date_shift" not in json.dumps(a)


@pytest.mark.parametrize("mutate", ["s1_hash", "s1_content", "real_class"])
def test_integrity_and_synthetic_only_fail_closed(mutate):
    s1, d = example()
    if mutate == "s1_hash":
        d["s1_result_sha256"] = "0" * 64
    elif mutate == "s1_content":
        s1["origin_snapshots"][0]["features"]["days_since_cycle_start"]["value"] = 999
        s1["result_sha256"] = cycle.digest({k: v for k, v in s1.items() if k != "result_sha256"})
        d["s1_result_sha256"] = s1["result_sha256"]
    else:
        d["data_class"] = "REAL"
    with pytest.raises(ValueError):
        prepare(s1, d)


def test_all_preregistered_scenarios_run_without_claiming_prediction_gain():
    for scenario in SCENARIOS:
        out = prepare(*example(scenario))
        assert out["scenario_results"][0]["scenario_id"] == scenario
        assert out["real_source_authority_proven"] is False
        assert out["model_use_authorized"] is False


def test_callers_decimal_context_cannot_change_structure_results():
    from decimal import ROUND_DOWN, localcontext

    s1, d = example("DENSITY_CHANGE")
    d["densities"][0].update(plant_count="1", measured_area="6")
    before = prepare(s1, d)
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_DOWN
        after = prepare(s1, d)
        assert context.prec == 6 and context.rounding == ROUND_DOWN
    assert before == after


def test_density_unknown_cohort_and_measurement_basis_are_not_silently_equivalent():
    s1, d = example("DENSITY_CHANGE")
    d["densities"][1]["cohort_id"] = "SYN-OTHER-COHORT"
    changed = first(prepare(s1, d))["density_change"]
    assert changed["status"] == "NOT_COMPARABLE"
    assert "DENSITY_COHORT_ID_CHANGED" in changed["reasons"]
    d["densities"][1]["cohort_id"] = d["densities"][0]["cohort_id"]
    d["densities"][1]["area_basis"] = "PRODUCTIVE"
    assert "DENSITY_AREA_BASIS_CHANGED" in first(prepare(s1, d))["density_change"]["reasons"]


def test_planned_replant_keeps_original_plan_without_claiming_an_observed_replacement():
    s1, d = example("REPLANT")
    event = d["replants"][0]
    event["observed_or_planned"] = "PLANNED"
    event["source"]["clocks"] = clock("2024-08-06", planned=True)
    value = first(prepare(s1, d))["replant"]
    assert value["status"] == "NOT_PROVEN" and value["events"] == []
    assert value["planned_or_unknown"][0]["record_id"] == event["record_id"]


def test_late_density_revision_is_audited_without_polluting_old_features():
    s1, d = example("DENSITY_CHANGE")
    before = prepare(s1, d)["origin_snapshots"][0]
    late = copy.deepcopy(d["densities"][1])
    late.update(
        record_id="SYN-LATE-DENSITY",
        revision_id="r2",
        supersedes_revision="r1",
        plant_count="99999",
    )
    late["source"]["clocks"] = clock("2025-03-02")
    d["densities"].append(late)
    after = prepare(s1, d)
    assert after["origin_snapshots"][0]["feature_sha256"] == before["feature_sha256"]
    assert any(row["record_id"] == late["record_id"] for row in after["supplement_ledger"])


def test_area_date_precision_and_unmapped_member_are_not_guessed():
    p, s, d = inputs()
    row = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    row["area"]["effective_from"] = span("2024-12")
    out = first(prepare(*rebound(p, s, d)))
    assert "AREA_EFFECTIVE_DATE_AMBIGUOUS" in out["area_changes"]["PLANTED"]["reasons"]
    member = next(m for m in s["members"] if m["member_id"] == d["links"][0]["next_member_id"])
    member["scope"]["plot"] = "UNMAPPED"
    out = first(prepare(*rebound(p, s, d)))
    assert out["status"] != "COMPARABLE" and out["area_changes"]["PLANTED"]["delta_mu"] is None


def test_historical_timestamp_intervals_use_the_declared_business_timezone():
    p, s, d = inputs()
    d["links"][0]["next_as_of"] = "2024-11-30"
    row = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    row["area"]["effective_from"] = dict(
        raw="2024-12-01T00:30:00+08:00",
        precision="TIMESTAMP",
        lower_date="2024-12-01",
        upper_date="2024-12-01",
        instant="2024-12-01T00:30:00+08:00",
    )
    area = first(prepare(*rebound(p, s, d)))["area_changes"]["PLANTED"]
    assert area["status"] == "NOT_PROVEN" and area["next_mu"] is None
    assert "AREA_RECORD_MISSING" in area["reasons"]


@pytest.mark.parametrize("zone", ["UNKNOWN/ZONE", "UTC"])
def test_missing_or_inconsistent_business_timezone_is_rejected(zone):
    s1, d = example()
    d["business_timezone"] = zone
    with pytest.raises(ValueError, match="STRUCTURE_TIMEZONE"):
        prepare(s1, d)


def test_non_unique_revision_cannot_be_resolved_by_picking_a_favorable_row():
    p, s, d = inputs()
    old = next(
        r
        for r in p["records"]
        if r["record_id"] == d["links"][0]["next_member_id"] + "-area-PLANTED"
    )
    for index, value in [(2, "80"), (3, "120")]:
        row = copy.deepcopy(old)
        row.update(
            record_id=f"SYN-FORK-{index}",
            revision_id=f"r{index}",
            supersedes_revision="r1",
            source_row_id=f"SYN-FORK-{index}",
        )
        row["area"].update(raw_value=value, value=value + ".000000")
        p["records"].append(row)
        s["record_clocks"][row["record_id"]] = dict(record_sha256="", **clock("2024-07-02"))
    area = first(prepare(*rebound(p, s, d)))["area_changes"]["PLANTED"]
    assert area["delta_mu"] is None and "REVISION_FORK" in area["reasons"]


def test_s1_cycle_features_and_cross_plot_results_remain_separate():
    from backend.tests.agronomic_history.v0_21_cycle_fixture import fixture

    p, s = fixture()
    original = cycle.prepare(p, s)
    with_areas, d = example("AREA_INCREASE")
    assert [r["feature_sha256"] for r in original["origin_snapshots"]] == [
        r["feature_sha256"] for r in with_areas["origin_snapshots"]
    ]
    out = prepare(with_areas, d)
    assert out["original_cycle_associations"] == original["cycle_associations"]
    assert first(out)["area_changes"]["PLANTED"]["delta_mu"] == "20.000000"
    assert all(
        row["area_changes"]["PLANTED"]["delta_mu"] == "0.000000" for row in out["comparisons"][1:]
    )


def test_members_without_explicit_continuity_are_retained_as_not_proven():
    s1, d = example()
    d["links"].pop()
    d["scenarios"][0]["link_ids"].pop()
    out = prepare(s1, d)
    assert len(out["unlinked_members"]) == 2
    assert all(row["reason"] == "CONTINUITY_NOT_DECLARED" for row in out["unlinked_members"])


def test_two_independent_cli_processes_produce_identical_business_outputs(tmp_path):
    s1, d = example("BUSINESS_EXAMPLE")
    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir()
    for name, data in (("s1.json", s1), ("declarations.json", d)):
        (inputs_dir / name).write_bytes(cycle.canonical(data) + b"\n")
    outputs = []
    for i in range(2):
        output = tmp_path / f"run-{i}"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.research.v021_structure_scenarios",
                "--s1",
                str(inputs_dir / "s1.json"),
                "--declarations",
                str(inputs_dir / "declarations.json"),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
        )
        outputs.append(output)
    for name in ("structure-scenarios.json", "area-changes.csv"):
        assert (outputs[0] / name).read_bytes() == (outputs[1] / name).read_bytes()
    assert (outputs[0] / "manifest.json").is_file()
    assert (outputs[0].stat().st_mode & 0o777) == 0o700
    assert all((p.stat().st_mode & 0o777) == 0o600 for p in outputs[0].iterdir())
