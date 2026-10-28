"""Explicit synthetic S4 inputs, built through the frozen S1/S2/S3 fixtures."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from backend.research import v021_cycle_features as cycle
from backend.research import v021_evaluation_readiness as evaluation
from backend.tests.agronomic_history import v0_21_cycle_fixture as f1
from backend.tests.agronomic_history import v0_21_evaluation_fixture as f3
from backend.tests.agronomic_history import v0_21_structure_fixture as f2

AS_OF = "2025-04-04T08:00:00+08:00"


def case(stage="S3", scenario="COMPLETE"):
    spec = dict(dataset_id=f"SYN-{stage}-{scenario}", stage=stage, scenario_id=scenario)
    if stage == "S1":
        package, declarations = f1.fixture()
        return spec, dict(package=package, cycles=declarations)
    if stage == "S2":
        s1, declarations = f2.example(scenario)
        return spec, dict(
            package=s1["original_package"],
            cycles=s1["original_declarations"],
            structure=declarations,
        )
    s1, s2, protocol = f3.inputs("COMPLETE" if scenario.startswith("R2_") else scenario)
    values = dict(
        package=s1["original_package"],
        cycles=s1["original_declarations"],
        structure=s2["original_declarations"],
        protocol=protocol,
    )
    if scenario != "PREFIX_MISMATCH":
        registration = evaluation.register(s1, s2, protocol)
        predictions, labels = f3.payloads(
            registration, "COMPLETE" if scenario.startswith("R2_") else scenario
        )
        if scenario == "R2_H15_PREFIX_MISSING_D8":
            for curve in predictions["curves"]:
                if curve["curve_id"].startswith("SYN-CURVE-0-10-"):
                    curve["rows"] = [r for r in curve["rows"] if r["date"] != "2025-03-18"]
        values.update(predictions=predictions, labels=labels)
    return spec, values


def execute(stage="S3", scenario="COMPLETE"):
    from backend.research import v021_readiness_report as report

    spec, values = case(stage, scenario)
    prepared = report.prepare_case(
        spec, values["package"], values["cycles"], values.get("structure"), values.get("protocol")
    )
    if prepared.registration is not None:
        prepared = report.seal_case(prepared, values.get("predictions"))
    return report.finish_case(prepared, values.get("labels"), as_of=AS_OF)


def catalog(directory, *, full_matrix=False, evidence=None, title="V0.21 合成研究就绪报告"):
    directory = Path(directory)
    directory.mkdir(mode=0o700)
    requests = [("S1", "CYCLE_EXAMPLE")]
    requests += [("S2", s) for s in (f2.SCENARIOS if full_matrix else ("BUSINESS_EXAMPLE",))]
    requests += [("S3", s) for s in (f3.SCENARIOS if full_matrix else ("COMPLETE",))]
    if full_matrix:
        requests.append(("S3", "R2_H15_PREFIX_MISSING_D8"))
    datasets = []
    for index, (stage, scenario) in enumerate(requests):
        spec, values = case(stage, scenario)
        folder = directory / f"SYNTHETIC-{index:02}"
        folder.mkdir(mode=0o700)
        refs = {}
        for role, value in values.items():
            path = folder / (role + ".json")
            raw = cycle.canonical(copy.deepcopy(value)) + b"\n"
            path.write_bytes(raw)
            path.chmod(0o600)
            refs[role] = dict(
                path=str(path.relative_to(directory)), sha256=hashlib.sha256(raw).hexdigest()
            )
        datasets.append(dict(**spec, inputs=refs))
    evidence_ref = None
    if evidence is not None:
        raw = cycle.canonical(evidence) + b"\n"
        path = directory / "PUBLIC-s4-evidence.json"
        path.write_bytes(raw)
        path.chmod(0o600)
        evidence_ref = dict(path=path.name, sha256=hashlib.sha256(raw).hexdigest())
    value = dict(
        schema_version="V0_21_S4_CATALOG_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        title=title,
        as_of=AS_OF,
        datasets=datasets,
        evidence=evidence_ref,
    )
    path = directory / "SYNTHETIC-catalog.json"
    path.write_bytes(cycle.canonical(value) + b"\n")
    path.chmod(0o600)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--full-matrix", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    evidence = cycle._read(args.evidence) if args.evidence else None
    path = catalog(args.output, full_matrix=args.full_matrix, evidence=evidence)
    print(json.dumps({"catalog": str(path), "synthetic_only": True}))


if __name__ == "__main__":
    main()
