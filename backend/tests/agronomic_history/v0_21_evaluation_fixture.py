"""Fixed synthetic vectors for evaluation arithmetic, not an agronomic predictor."""

import argparse
import copy
import json
from datetime import date, timedelta
from pathlib import Path

from backend.research import v021_cycle_features as cycle
from backend.research import v021_structure_scenarios as structure
from backend.tests.agronomic_history.v0_21_cycle_fixture import reseal
from backend.tests.agronomic_history.v0_21_structure_fixture import inputs as structure_inputs

SCENARIOS = (
    "COMPLETE",
    "INVALID_REMAINING",
    "PEAK_TIE",
    "SHORT_5",
    "SHORT_10",
    "MISSING_DAY",
    "DUPLICATE_DAY",
    "NEGATIVE_KG",
    "INVALID_KG",
    "ZERO_ACTUAL",
    "LATE_SOURCE",
    "LATE_ISSUANCE",
    "IMMATURE_LABELS",
    "DAILY_TOTAL_CANCELLATION",
    "COMMON_COHORT_FAILURES",
    "IMPROVED",
    "WORSENED",
    "BASIS_MISMATCH",
    "MEMBER_MISMATCH",
    "LABEL_CONFLICT",
    "UNKNOWN_CALENDAR_END",
    "PREFIX_MISMATCH",
)
FAMILIES = (
    "FULL_SEASON_PEAK",
    "DECLARED_REMAINING_SEASON_PEAK",
    "ORIGIN_H7_PREFIX",
    "ORIGIN_H15_LOCAL",
)


def inputs(scenario="COMPLETE"):
    if scenario not in SCENARIOS:
        raise ValueError("UNKNOWN_SYNTHETIC_SCENARIO")
    package, declarations, supplement = structure_inputs()
    # Explicit synthetic members share one comparison variety/system; no fuzzy mapping.
    for member in declarations["members"]:
        if member["scope"]["base"] == "SYN-BASE-1":
            original = member["scope"].copy()
            member["scope"]["production_system"] = "DECIDUOUS_NATURAL"
            for r in package["records"]:
                if all(r["scope"][k] == v for k, v in original.items()):
                    r["scope"]["production_system"] = "DECIDUOUS_NATURAL"
    for base in (0, 1):
        template = next(
            o
            for o in declarations["origins"]
            if o["base"] == f"SYN-BASE-{base}" and o["season"] == "2024-2025"
        )
        for day in (10, 11):
            origin = copy.deepcopy(template)
            origin.update(
                origin_id=f"SYN-S3-ORIGIN-{base}-{day}",
                origin_date=f"2025-03-{day:02}",
                cutoff=f"2025-03-{day:02}T08:00:00+08:00",
            )
            declarations["origins"].append(origin)
    reseal(package, declarations)
    s1 = cycle.prepare(package, declarations)
    supplement["s1_result_sha256"] = s1["result_sha256"]
    s2 = structure.prepare(s1, supplement)
    protocol = dict(
        schema_version="V0_21_S3_PROTOCOL_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        comparison_family="SYNTHETIC-REGISTERED-AGRONOMIC-COMPARISON",
        season="2024-2025",
        variety="SYN-VARIETY-0",
        production_system="DECIDUOUS_NATURAL",
        quantity_basis="RECORDED_INBOUND_WEIGHT",
        unit="kg",
        area_basis="EFFECTIVE",
        business_timezone="Asia/Shanghai",
        source_population_sha256=cycle.digest("SYNTHETIC-source-population"),
        training_scope_sha256=cycle.digest("SYNTHETIC-training-scope-NOT-A-FIT"),
        label_authority_sha256=cycle.digest("SYNTHETIC-label-authority"),
        label_source_version="SYN-LABEL-R1",
        models={
            side: dict(
                model_id="SYNTHETIC-DECLARED-VECTOR-" + side,
                fit_sha256=cycle.digest(side + "-NOT-TRAINED"),
                config_sha256=cycle.digest(side + "-FIXED-VECTOR"),
                trained_through="2023-06-30",
            )
            for side in ("baseline", "candidate")
        },
        calendars=[],
        curves=[],
        cases=[],
    )
    for base in (0, 1):
        end = (
            "2025-03-06"
            if scenario == "SHORT_5"
            else "2025-03-11"
            if scenario == "SHORT_10"
            else "2025-04-01"
        )
        protocol["calendars"].append(
            dict(
                calendar_id=f"SYN-CALENDAR-{base}",
                base_id=f"SYN-BASE-{base}",
                season="2024-2025",
                season_start="2025-03-02",
                season_end=None if scenario == "UNKNOWN_CALENDAR_END" else end,
                timezone="Asia/Shanghai",
                source_sha256=cycle.digest(f"SYN-calendar-{base}"),
                source_version="SYN-CALENDAR-R1",
                known_at="2024-12-02T08:00:00+08:00",
            )
        )

    def add(base, day, family):
        member = next(
            m for m in declarations["members"] if m["member_id"] == f"SYN-MEMBER-{base}-0-2024"
        )
        origin_id = f"SYN-ORIGIN-{base}-2024" if day == 1 else f"SYN-S3-ORIGIN-{base}-{day}"
        refs = {}
        for side in ("baseline", "candidate"):
            cid = f"SYN-CURVE-{base}-{day}-{side}"
            refs[side] = cid
            if not any(c["curve_id"] == cid for c in protocol["curves"]):
                protocol["curves"].append(
                    dict(
                        curve_id=cid,
                        member_id=member["member_id"],
                        origin_id=origin_id,
                        side=side,
                        prediction_version="SYN-PREDECLARED-V1",
                        support_start=f"2025-03-{day + 1:02}",
                        support_end=protocol["calendars"][base]["season_end"],
                    )
                )
        protocol["cases"].append(
            dict(
                case_id=f"SYN-CASE-{base}-{day}-{family}",
                scope_id=f"SYN-SCOPE-{base}-{day}-{family}",
                member_id=member["member_id"],
                scope=member["scope"],
                origin_id=origin_id,
                calendar_id=f"SYN-CALENDAR-{base}",
                evaluation_family=family,
                remaining_start="2025-03-12" if family == FAMILIES[1] else None,
                split="SYNTHETIC_VALIDATION",
                area_mu="50.000000" if base == 0 else "30.000000",
                baseline_curve_id=refs["baseline"],
                candidate_curve_id=refs["candidate"],
            )
        )

    add(0, 1, FAMILIES[0])
    if scenario not in {"SHORT_5", "SHORT_10"}:
        add(0, 10, FAMILIES[1])
        for day in (10, 11):
            add(0, day, FAMILIES[2])
            add(0, day, FAMILIES[3])
    if scenario == "COMMON_COHORT_FAILURES":
        add(1, 10, FAMILIES[2])
        add(1, 10, FAMILIES[3])
    if scenario == "INVALID_REMAINING":
        next(c for c in protocol["cases"] if c["evaluation_family"] == FAMILIES[1])[
            "remaining_start"
        ] = "2025-03-10"
    if scenario == "PREFIX_MISMATCH":
        next(c for c in protocol["cases"] if c["evaluation_family"] == FAMILIES[2])[
            "candidate_curve_id"
        ] = "SYN-CURVE-0-11-candidate"
    return s1, s2, protocol


def vectors(scenario):
    actual = [1] * 31
    actual[:7] = [3] * 7
    actual[8:15] = [10] * 7
    baseline = [2] * 31
    baseline[15:22] = [8] * 7
    candidate = [1] * 31
    candidate[:7] = [3] * 7
    candidate[8:15] = [9] * 7
    if scenario == "PEAK_TIE":
        actual = baseline = candidate = [4] * 31
    if scenario == "ZERO_ACTUAL":
        actual = [0] * 31
    if scenario == "IMPROVED":
        candidate = actual.copy()
    if scenario == "WORSENED":
        baseline = actual.copy()
        candidate = [0] * 31
    if scenario == "DAILY_TOTAL_CANCELLATION":
        actual = [20] * 31
        candidate = actual.copy()
        baseline = actual.copy()
        baseline[9] = 30
        baseline[10] = 10
    return actual, baseline, candidate


def payloads(registration, scenario="COMPLETE"):
    protocol = registration["protocol"]
    actual, baseline, candidate = vectors(scenario)
    by_member_origin = {
        (c["member_id"], c["origin"]["origin_id"]): c for c in registration["cases"]
    }
    predictions = dict(
        schema_version="V0_21_S3_PREDICTIONS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        registration_sha256=registration["registration_sha256"],
        curves=[],
    )
    for spec in protocol["curves"]:
        case = by_member_origin[(spec["member_id"], spec["origin_id"])]
        side = spec["side"]
        model = protocol["models"][side]
        start = date.fromisoformat(spec["support_start"])
        end = date.fromisoformat(spec["support_end"]) if spec["support_end"] else start
        values = baseline if side == "baseline" else candidate
        rows = [
            dict(
                date=str(start + timedelta(days=i)),
                kg=f"{values[(start - date(2025, 3, 2)).days + i]}.000000",
            )
            for i in range(max(0, (end - start).days + 1))
        ]
        predictions["curves"].append(
            dict(
                curve_id=spec["curve_id"],
                member_id=spec["member_id"],
                scope=case["scope"],
                origin_id=spec["origin_id"],
                prediction_version=spec["prediction_version"],
                model_id=model["model_id"],
                fit_sha256=model["fit_sha256"],
                config_sha256=model["config_sha256"],
                quantity_basis=protocol["quantity_basis"],
                unit="kg",
                source_population_sha256=protocol["source_population_sha256"],
                area_mu=case["area_mu"],
                area_authority_sha256=case["area_authority_sha256"],
                issued_at=case["origin"]["cutoff"],
                input_available_at=case["origin"]["origin_date"] + "T07:00:00+08:00",
                input_ingested_at=case["origin"]["origin_date"] + "T07:30:00+08:00",
                rows=rows,
                failure=None,
            )
        )
    labels = dict(
        schema_version="V0_21_S3_LABELS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        registration_sha256=registration["registration_sha256"],
        label_authority_sha256=protocol["label_authority_sha256"],
        source_version=protocol["label_source_version"],
        labels=[],
    )
    for case in registration["cases"]:
        rows = [
            dict(date=d, kg=f"{actual[(date.fromisoformat(d) - date(2025, 3, 2)).days]}.000000")
            for d in case["dates"]
        ]
        labels["labels"].append(
            dict(
                case_id=case["case_id"],
                member_id=case["member_id"],
                scope=case["scope"],
                quantity_basis=protocol["quantity_basis"],
                unit="kg",
                area_mu=case["area_mu"],
                area_authority_sha256=case["area_authority_sha256"],
                complete=True,
                mature=scenario != "IMMATURE_LABELS",
                available_at="2025-04-02T08:00:00+08:00",
                complete_at="2025-04-02T08:00:00+08:00",
                mature_at="2025-04-03T08:00:00+08:00",
                rows=rows,
            )
        )
    if scenario == "COMMON_COHORT_FAILURES":
        predictions["curves"] = [
            p for p in predictions["curves"] if p["curve_id"] != "SYN-CURVE-1-10-candidate"
        ]
    for p in predictions["curves"]:
        if scenario == "LATE_SOURCE":
            p["input_available_at"] = p["issued_at"].replace("08:00:00", "09:00:00")
        if scenario == "LATE_ISSUANCE":
            p["issued_at"] = p["issued_at"].replace("08:00:00", "09:00:00")
        if scenario == "BASIS_MISMATCH" and "candidate" in p["curve_id"]:
            p["quantity_basis"] = "FIELD_HARVEST_WEIGHT"
    if scenario == "MISSING_DAY":
        predictions["curves"][0]["rows"].pop(18)
    if scenario == "NEGATIVE_KG":
        predictions["curves"][0]["rows"][0]["kg"] = "-1"
    if scenario == "INVALID_KG":
        predictions["curves"][0]["rows"][0]["kg"] = "NaN"
    if scenario == "DUPLICATE_DAY":
        labels["labels"][0]["rows"].append(copy.deepcopy(labels["labels"][0]["rows"][0]))
    if scenario == "MEMBER_MISMATCH":
        labels["labels"][0]["scope"] = dict(labels["labels"][0]["scope"], plot="SYN-OTHER-PLOT")
    if scenario == "LABEL_CONFLICT":
        labels["labels"][0]["rows"][10]["kg"] = "99.000000"
    return predictions, labels


def example(scenario="COMPLETE"):
    from backend.research.v021_evaluation_readiness import register

    s1, s2, p = inputs(scenario)
    registration = register(s1, s2, p)
    predictions, labels = payloads(registration, scenario)
    return s1, s2, p, registration, predictions, labels


def suite():
    """Execute every predeclared fixture, retaining failures and metric arithmetic."""
    from backend.research.v021_evaluation_readiness import score, seal_predictions

    results = {}
    for scenario in SCENARIOS:
        if scenario == "PREFIX_MISMATCH":
            try:
                example(scenario)
            except ValueError as exc:
                results[scenario] = dict(status="REJECTED", reason=str(exc))
            else:
                raise AssertionError("INVALID_PREFIX_ACCEPTED")
            continue
        *_, registration, predictions, labels = example(scenario)
        sealed = seal_predictions(registration, predictions)
        report = score(sealed, labels, as_of="2025-04-04T08:00:00+08:00")
        results[scenario] = dict(
            status="SYNTHETIC_EVALUATED",
            registration_sha256=registration["registration_sha256"],
            seal_sha256=sealed["seal_sha256"],
            result_sha256=report["result_sha256"],
            candidate_count=report["candidate_count"],
            groups=report["groups"],
            failures={
                c["case_id"]: c["failures"] for c in report["member_ledger"] if c["failures"]
            },
        )
    body = dict(
        schema_version="V0_21_S3_EXECUTED_SCENARIOS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        scenarios=results,
        real_data_read=False,
        model_training=False,
        s4_implemented=False,
    )
    return dict(body, result_sha256=cycle.digest(body))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="COMPLETE")
    parser.add_argument("--suite", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.suite:
        value = suite()
        args.output.mkdir(mode=0o700)
        file = args.output / "executed-scenarios.json"
        with file.open("xb") as f:
            f.write(cycle.canonical(value) + b"\n")
        file.chmod(0o600)
        print(
            json.dumps(
                {"scenarios": len(value["scenarios"]), "result_sha256": value["result_sha256"]}
            )
        )
        return
    s1, s2, p, _, predictions, labels = example(args.scenario)
    args.output.mkdir(mode=0o700)
    for name, value in (
        ("s1.json", s1),
        ("s2.json", s2),
        ("protocol.json", p),
        ("predictions.json", predictions),
        ("labels.json", labels),
    ):
        file = args.output / name
        with file.open("xb") as f:
            f.write(cycle.canonical(value) + b"\n")
        file.chmod(0o600)
    print(json.dumps({"scenario": args.scenario, "synthetic_only": True}))


if __name__ == "__main__":
    main()
