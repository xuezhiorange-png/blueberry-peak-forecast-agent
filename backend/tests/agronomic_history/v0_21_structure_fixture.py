"""Fixed SYNTHETIC S2 facts. No fitted responses or real source discovery."""

import argparse
import copy
import json
from pathlib import Path

from backend.research.v021_cycle_features import canonical, digest, prepare
from backend.tests.agronomic_history.v0_21_cycle_fixture import clock, fixture, reseal, span

SCENARIOS = (
    "UNCHANGED",
    "AREA_INCREASE",
    "AREA_DECREASE",
    "ASYNCHRONOUS_AREA_CHANGE",
    "VARIETY_REPLACEMENT",
    "REPLANT",
    "DENSITY_CHANGE",
    "MIXED_PRODUCTION_SYSTEMS",
    "UNPROVEN_CONTINUITY",
    "CONFLICTING_EFFECTIVE_INTERVALS",
    "ZERO_PREVIOUS_AREA",
    "MISSING_AREA",
    "UNIT_MISMATCH",
    "SAME_NAME_DIFFERENT_ENTITY",
    "BUSINESS_EXAMPLE",
)


def source(day="2024-09-01"):
    return dict(
        reference="SYNTHETIC-structure-declaration",
        version="SYN-R1",
        sha256=digest({"synthetic_source": "structure", "day": day}),
        clocks=clock(day),
    )


def inputs(scenario="UNCHANGED"):
    if scenario not in SCENARIOS:
        raise ValueError("UNKNOWN_SYNTHETIC_SCENARIO")
    package, declarations = fixture()
    members = declarations["members"]
    old = [m for m in members if m["scope"]["season"] == "2023-2024"]
    new = [m for m in members if m["scope"]["season"] == "2024-2025"]
    if scenario in {"VARIETY_REPLACEMENT", "MIXED_PRODUCTION_SYSTEMS"}:
        key, value = (
            ("variety", "SYN-NEW-VARIETY")
            if scenario == "VARIETY_REPLACEMENT"
            else ("production_system", "DECIDUOUS_FORCING")
        )
        original = copy.deepcopy(new[0]["scope"])
        new[0]["scope"][key] = value
        for r in package["records"]:
            if all(r["scope"][k] == v for k, v in original.items()):
                r["scope"][key] = value
    bases = [("100", "60", "50"), ("80", "50", "40"), ("50", "40", "30"), ("20", "10", "8")]
    for season_members in (old, new):
        for i, member in enumerate(season_members):
            year = int(member["scope"]["season"][:4])
            values = list(bases[i])
            if i == 0:
                if season_members is new and scenario == "AREA_INCREASE":
                    values[0] = "120"
                if season_members is new and scenario == "AREA_DECREASE":
                    values[0] = "80"
                if season_members is new and scenario in {
                    "ASYNCHRONOUS_AREA_CHANGE",
                    "BUSINESS_EXAMPLE",
                }:
                    values = ["120", "50", "45"]
                if season_members is old and scenario == "ZERO_PREVIOUS_AREA":
                    values = ["0", "0", "0"]
            template = next(
                r for r in package["records"] if r["record_id"] == member["primary_pruning"][0]
            )
            for basis, value in zip(("PLANTED", "PRODUCTIVE", "EFFECTIVE"), values, strict=True):
                rid = member["member_id"] + "-area-" + basis
                r = copy.deepcopy(template)
                r.update(
                    kind="AREA",
                    slot=None,
                    record_id=rid,
                    logical_id=rid,
                    event=None,
                    phenology=None,
                    source_row_id=rid,
                    business_date=span(f"{year}-07-02"),
                    area=dict(
                        basis=basis,
                        raw_value=value,
                        value=value + ".000000",
                        unit="mu",
                        effective_from=span(f"{year}-07-01"),
                        effective_to=span(f"{year + 1}-06-30"),
                        tree_age_years=None,
                        planting_year=None,
                    ),
                )
                if i == 0 and season_members is old and basis == "PLANTED":
                    if scenario == "MISSING_AREA":
                        r["area"].update(raw_value="", value=None)
                    if scenario == "UNIT_MISMATCH":
                        r["area"]["unit"] = "ha"
                package["records"].append(r)
                declarations["record_clocks"][rid] = dict(
                    record_sha256="", **clock(f"{year}-07-02")
                )
    if scenario == "CONFLICTING_EFFECTIVE_INTERVALS":
        r = copy.deepcopy(
            next(
                r
                for r in package["records"]
                if r["record_id"] == new[0]["member_id"] + "-area-PLANTED"
            )
        )
        r.update(
            record_id="SYN-CONFLICT",
            logical_id="SYN-OTHER-LOGICAL-ID",
            source_row_id="SYN-CONFLICT",
        )
        r["source_reference"] = "SYNTHETIC-conflicting-source"
        r["area"].update(raw_value="90", value="90.000000")
        package["records"].append(r)
        declarations["record_clocks"][r["record_id"]] = dict(
            record_sha256="", **clock("2024-07-02")
        )
    reseal(package, declarations)
    links = []
    for i, (a, b) in enumerate(zip(old, new, strict=True)):
        links.append(
            dict(
                link_id=f"SYN-LINK-{i}",
                previous_member_id=a["member_id"],
                next_member_id=b["member_id"],
                previous_entity_id=f"SYN-ENTITY-{i}",
                next_entity_id=f"SYN-ENTITY-{i}",
                previous_as_of="2023-12-01",
                next_as_of="2024-12-01",
                kind="VARIETY_REPLACEMENT"
                if i == 0 and scenario == "VARIETY_REPLACEMENT"
                else "CONTINUING_MEMBER",
                source=source(),
            )
        )
    if scenario == "UNPROVEN_CONTINUITY":
        links[0]["kind"] = "UNKNOWN"
    if scenario == "SAME_NAME_DIFFERENT_ENTITY":
        links[0]["next_entity_id"] = "SYN-DIFFERENT-ENTITY"
    extra = dict(
        schema_version="V0_21_S2_DECLARATIONS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        business_timezone="Asia/Shanghai",
        s1_result_sha256="",
        links=links,
        densities=[],
        replants=[],
        scenarios=[dict(scenario_id=scenario, link_ids=[link["link_id"] for link in links])],
    )
    if scenario in {"DENSITY_CHANGE", "BUSINESS_EXAMPLE"}:
        index = 2 if scenario == "BUSINESS_EXAMPLE" else 0
        area = "50" if index == 2 else "100"
        counts = ["10000", "15000"] if index == 2 else ["20000", "30000"]
        for member, count in zip((old[index], new[index]), counts, strict=True):
            year = member["scope"]["season"][:4]
            extra["densities"].append(
                dict(
                    record_id="SYN-DENSITY-" + member["member_id"],
                    member_id=member["member_id"],
                    logical_id="SYN-DENSITY-" + member["member_id"],
                    revision_id="r1",
                    supersedes_revision=None,
                    cohort_id="SYN-UNCHANGED-COHORT",
                    plant_count=count,
                    measured_area=area,
                    area_unit="mu",
                    area_basis="PLANTED",
                    method="SYNTHETIC-complete-plant-count",
                    effective_date=span(year + "-07-02"),
                    observed_or_planned="OBSERVED",
                    source=source(year + "-07-02"),
                )
            )
    if scenario in {"REPLANT", "BUSINESS_EXAMPLE"}:
        index = 1 if scenario == "BUSINESS_EXAMPLE" else 0
        extra["replants"].append(
            dict(
                record_id="SYN-REPLANT",
                logical_id="SYN-REPLANT",
                revision_id="r1",
                supersedes_revision=None,
                previous_member_id=old[index]["member_id"],
                next_member_id=new[index]["member_id"],
                old_cohort_id="SYN-OLD-COHORT",
                new_cohort_id="SYN-NEW-COHORT",
                business_date=span("2024-08-05"),
                observed_or_planned="OBSERVED",
                source=source("2024-08-06"),
            )
        )
    return package, declarations, extra


def example(scenario="UNCHANGED"):
    package, declarations, extra = inputs(scenario)
    s1 = prepare(package, declarations)
    extra["s1_result_sha256"] = s1["result_sha256"]
    return s1, extra


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="BUSINESS_EXAMPLE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    s1, declarations = example(args.scenario)
    args.output.mkdir(mode=0o700)
    for name, data in (
        ("s1-cycle-features.json", s1),
        ("structure-declarations.json", declarations),
    ):
        target = args.output / name
        with target.open("xb") as f:
            f.write(canonical(data) + b"\n")
        target.chmod(0o600)
    print(json.dumps({"scenario": args.scenario, "s1_result_sha256": s1["result_sha256"]}))


if __name__ == "__main__":
    main()
